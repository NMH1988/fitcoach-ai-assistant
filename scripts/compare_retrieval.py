"""Live check O5 for T3.6: vector-only, keyword-only and hybrid retrieval on the owner's questions.

Run by the owner from the repo root, after the index is built, with the key set up:

    python scripts/compare_retrieval.py [data/eval_questions.json]

The file is the owner's evaluation questions (O2): a JSON list of objects with an "id", the
"question" and "expected_sources", the source IDs (as in data/sources.json) it should find; other
fields, such as "good_answer" for T6.1, are ignored here. Each question goes through the input
guard, then one embedding call. Each method gets the question alone, with no rewrites and no
filter, so only the way of searching differs: vector search with the distance limit, BM25, and
the app's hybrid search (BM25 joins only when a vector hit passes the limit). For each question
the script prints the rank of the first expected source in each method's top RETRIEVAL_TOP_K,
then each method's hit rate. A question with no expected source (one the sources should not
cover) is shown but not scored. It costs a fraction of a cent and never prints the key. Record
the output in docs/TESTING.md.
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from src import config, guard, llm
from src.rag import hybrid, store
from src.rag.retriever import RetrievedChunk, embed_queries, search

METHODS = ("vector", "keyword", "hybrid")


class EvalQuestion(BaseModel):
    """One of the owner's evaluation questions and the sources it should find."""

    # Other fields (e.g. the good answer, for T6.1) are allowed and ignored.
    model_config = ConfigDict(extra="ignore")

    id: str
    question: str
    expected_sources: list[str]


class QuestionsFileError(ValueError):
    """The questions file is missing or not in the expected format; `str()` says which."""


def load_questions(path: Path) -> list[EvalQuestion]:
    """Read and check the questions file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise QuestionsFileError(f"No questions file at {path}.") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestionsFileError(f"Could not read {path}: {exc}") from None
    if not isinstance(data, list) or not data:
        raise QuestionsFileError(f"{path} must hold a non-empty JSON list of questions.")
    try:
        return [EvalQuestion.model_validate(item) for item in data]
    except ValidationError as exc:
        raise QuestionsFileError(f"{path} has a question in the wrong format: {exc}") from None


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


def _sources(found: Sequence[RetrievedChunk]) -> str:
    """Return the source IDs of the chunks found, in order, e.g. '#4 #4 #10'."""
    return " ".join(f"#{chunk.metadata.get('source_id')}" for chunk in found) or "nothing"


def compare(questions: Sequence[EvalQuestion], index, limiter: guard.RateLimiter) -> list[str]:
    """Return the report lines: each question's ranks per method, then the hit rates."""
    keywords = hybrid.build_keyword_index(index)
    hits = dict.fromkeys(METHODS, 0)
    scored = 0
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
            lines.append(f"  {method:<8} first hit {shown:>2}  {_sources(found[method])}")
    lines.append(f"Hit rate in the top {config.RETRIEVAL_TOP_K}, {scored} scored questions:")
    for method in METHODS:
        share = f" ({hits[method] / scored:.0%})" if scored else ""
        lines.append(f"  {method:<8} {hits[method]} of {scored}{share}")
    return lines


def main(args: Sequence[str] | None = None) -> int:
    """Compare the three ways of searching on the questions file and return the exit code."""
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
