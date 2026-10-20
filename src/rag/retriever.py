"""The retrieval step of a chat turn: the chunks of the index nearest to the question.

T3.1 runs one vector search; T3.2 (query translation, filters) and T3.3 (hybrid search) extend it.
"""

from dataclasses import dataclass
from typing import Any

from chromadb.errors import ChromaError
from langchain_chroma import Chroma

from src import config
from src.rag.store import UNREADABLE, IndexNotReadyError


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk found for a question: its text, its metadata and its cosine distance."""

    text: str
    metadata: dict[str, Any]
    distance: float


def retrieve(
    index: Chroma,
    question: str,
    k: int | None = None,
    max_distance: float | None = None,
) -> list[RetrievedChunk]:
    """Return the k chunks nearest to the question, nearest first, dropping those too far away."""
    k = config.RETRIEVAL_TOP_K if k is None else k
    max_distance = config.RETRIEVAL_MAX_DISTANCE if max_distance is None else max_distance
    try:
        # The collection uses cosine space, so the score is the cosine distance (lower is closer).
        found = index.similarity_search_with_score(question, k=k)
    except ChromaError:
        # E.g. a rebuild dropped the collection the running app holds; its message is internal.
        raise IndexNotReadyError(UNREADABLE) from None
    return [
        RetrievedChunk(doc.page_content, dict(doc.metadata), distance)
        for doc, distance in found
        if distance <= max_distance
    ]
