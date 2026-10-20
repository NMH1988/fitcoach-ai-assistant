"""Live check O5 for T3.1: the cosine distances of the nearest chunks, to set the retrieval limit.

Run by the owner from the repo root, after the index is built, with the key set up:

    python scripts/live_check_retrieval.py "How much protein per meal?" "Who won the World Cup?"

Each question goes through the input guard, then one embedding call; the script prints the
RETRIEVAL_TOP_K nearest chunks with their distance and whether they pass RETRIEVAL_MAX_DISTANCE.
Ask questions the sources cover and questions they do not, then pick a limit between the two
groups. It costs a fraction of a cent and never prints the key. Record the output in
docs/TESTING.md.
"""

import math
import sys
from collections.abc import Sequence

from src import config, guard, llm
from src.rag import store
from src.rag.retriever import retrieve

# Characters of the section title shown per chunk.
SECTION_CHARS = 60


def check_question(index, question: str, limiter: guard.RateLimiter) -> list[str]:
    """Return the result lines for one question: its nearest chunks and their distances."""
    decision = guard.check_message(question, limiter)
    if not decision.allowed:
        return [f"Q: {question!r} rejected by the guard: {decision.message}"]
    with llm.mapped_errors():
        found = retrieve(index, decision.text, max_distance=math.inf)
    lines = [f"Q: {decision.text!r}"]
    for rank, chunk in enumerate(found, start=1):
        passes = "pass" if chunk.distance <= config.RETRIEVAL_MAX_DISTANCE else "drop"
        section = chunk.metadata.get("section", "")[:SECTION_CHARS]
        lines.append(
            f"  {rank}. {chunk.distance:.3f} {passes}  #{chunk.metadata['source_id']}  {section}"
        )
    passing = sum(chunk.distance <= config.RETRIEVAL_MAX_DISTANCE for chunk in found)
    lines.append(f"  {passing} of {len(found)} within {config.RETRIEVAL_MAX_DISTANCE}")
    return lines


def main(questions: Sequence[str] | None = None) -> int:
    """Check each question given on the command line and return the exit code."""
    questions = list(sys.argv[1:] if questions is None else questions)
    if not questions:
        print("Give one or more questions in quotes.", file=sys.stderr)
        return 2
    # One run may check more questions than the app's per-minute limit allows.
    limiter = guard.RateLimiter(per_window=len(questions), per_session=len(questions))
    try:
        index = store.open_index()
        for question in questions:
            print("\n".join(check_question(index, question, limiter)))
    except (config.MissingAPIKeyError, llm.LLMError, store.IndexNotReadyError) as exc:
        print(f"Live check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
