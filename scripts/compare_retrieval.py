"""Live check O5 for T3.6: vector-only, keyword-only and hybrid retrieval on the owner's questions.

Run by the owner from the repo root, after the index is built, with the key set up:

    python scripts/compare_retrieval.py [data/eval_questions.json]

The file is the owner's evaluation questions (O2): a JSON list of objects with an "id", the
"question" and "expected_sources", the source IDs (as in data/sources.json) it should find; other
fields, such as "good_answer" for T6.1, are ignored here. Each question goes through the input
guard, then one embedding call. Each method gets the question alone, with no rewrites and no
filter, so only the way of searching differs: vector search with the distance limit, BM25, and
the app's hybrid search (BM25 joins only when a vector hit passes the limit; at most
MAX_CHUNKS_PER_SOURCE chunks of one source come first, T8.3, so only the hybrid row is capped).
For each question the script prints the rank of the first expected source in each method's top
RETRIEVAL_TOP_K, then each method's hit rate and how many hybrid chunks were found by keyword
only (marked "*" in the hybrid row). A question with no expected source (one the sources
should not cover) is shown but not scored. It costs a fraction of a cent and never prints the
key. Record the output in docs/TESTING.md.
"""

import sys
from collections.abc import Sequence
from pathlib import Path

from src import config, guard, llm, observability
from src.eval_questions import EvalQuestion, QuestionsFileError, load_questions
from src.rag import hybrid, store
from src.rag.retriever import RetrievedChunk, embed_queries, search

METHODS = ("vector", "keyword", "hybrid")


def first_hit(found: Sequence[RetrievedChunk], expected: Sequence[str]) -> int | None:
    """Return the rank (from 1) of the first chunk from an expected source, or None."""
    for rank, chunk in enumerate(found, start=1):
        if str(chunk.metadata.get("source_id")) in expected:
            return rank
    return None


def retrieve_all(
    index, keywords: hybrid.KeywordIndex, question: str
) -> dict[str, list[RetrievedChunk]]:
    """Return each method's top chunks for the question, with one embedding call."""
    vectors = embed_queries(index, [question])
    return {
        "vector": search(index, vectors),
        "keyword": keywords.search(question),
        "hybrid": hybrid.hybrid_search(index, [question], vectors, None, lambda _: keywords),
    }


def _sources(found: Sequence[RetrievedChunk], mark_keyword_only: bool = False) -> str:
    """Return the source IDs of the chunks found, in order, e.g. '#4 #4* #10'."""
    # In the hybrid row a "*" marks a chunk found by keyword search only (no vector distance),
    # so T3.6 can see how often such chunks reach the top (PR #52 review).
    return (
        " ".join(
            f"#{chunk.metadata.get('source_id')}"
            + ("*" if mark_keyword_only and chunk.distance is None else "")
            for chunk in found
        )
        or "nothing"
    )


def compare(questions: Sequence[EvalQuestion], index, limiter: guard.RateLimiter) -> list[str]:
    """Return the report lines: each question's ranks per method, then the hit rates."""
    keywords = hybrid.build_keyword_index(index)
    hits = dict.fromkeys(METHODS, 0)
    scored = 0
    # Over every question searched, scored or not: hybrid chunks and those found by keyword only.
    hybrid_chunks = keyword_only = 0
    lines = []
    for item in questions:
        decision = guard.check_message(item.question, limiter)
        if not decision.allowed:
            lines.append(f"{item.id}: rejected by the guard, not scored: {decision.message}")
            continue
        with llm.mapped_errors():
            found = retrieve_all(index, keywords, decision.text)
        if not item.expected_sources:
            lines.append(f"{item.id}: no expected source, not scored")
        else:
            scored += 1
            expected = ", ".join(f"#{source}" for source in item.expected_sources)
            lines.append(f"{item.id}: expects {expected}")
        for method in METHODS:
            rank = first_hit(found[method], item.expected_sources)
            if rank is not None:
                hits[method] += 1
            shown = "-" if rank is None else str(rank)
            sources = _sources(found[method], mark_keyword_only=method == "hybrid")
            lines.append(f"  {method:<8} first hit {shown:>2}  {sources}")
        hybrid_chunks += len(found["hybrid"])
        keyword_only += sum(chunk.distance is None for chunk in found["hybrid"])
    lines.append(f"Hit rate in the top {config.RETRIEVAL_TOP_K}, {scored} scored questions:")
    for method in METHODS:
        share = f" ({hits[method] / scored:.0%})" if scored else ""
        lines.append(f"  {method:<8} {hits[method]} of {scored}{share}")
    lines.append(
        f"Hybrid chunks found by keyword only (* above): {keyword_only} of {hybrid_chunks}, "
        "over all questions searched"
    )
    # So a recorded run shows which code made it (T8.3): a run on code without the cap has no line.
    lines.append(f"Hybrid row: at most {config.MAX_CHUNKS_PER_SOURCE} chunks per source come first")
    return lines


def main(args: Sequence[str] | None = None) -> int:
    """Compare the three ways of searching on the questions file and return the exit code."""
    observability.configure_logging()
    args = list(sys.argv[1:] if args is None else args)
    if len(args) > 1:
        print("Give at most one path: the questions file.", file=sys.stderr)
        return 2
    path = Path(args[0]) if args else config.EVAL_QUESTIONS_PATH
    try:
        questions = load_questions(path)
    except QuestionsFileError as exc:
        print(exc, file=sys.stderr)
        return 2
    # One run may check more questions than the app's per-minute limit allows.
    limiter = guard.RateLimiter(per_window=len(questions), per_session=len(questions))
    try:
        index = store.open_index()
        print("\n".join(compare(questions, index, limiter)))
    except (config.MissingAPIKeyError, llm.LLMError, store.IndexNotReadyError) as exc:
        print(f"Comparison failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
