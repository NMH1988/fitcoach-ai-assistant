"""The retrieval step of a chat turn: the chunks of the index nearest to the question.

T3.2 searches the question and its rewrites with the query translation's filter; T3.3 (hybrid
search) adds keyword search and RRF.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from chromadb.errors import ChromaError
from langchain_chroma import Chroma
from langchain_core.documents import Document

from src import config
from src.rag.store import UNREADABLE, IndexNotReadyError, chunk_id


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk found for a question: its text, its metadata and its cosine distance."""

    text: str
    metadata: dict[str, Any]
    distance: float


def chunk_key(chunk: RetrievedChunk) -> str:
    """Return the chunk's ID in the index, <source_id>-<chunk_index>."""
    return chunk_id(Document(chunk.text, metadata=chunk.metadata))


def embed_queries(index: Chroma, queries: Sequence[str]) -> list[list[float]]:
    """Embed all the queries in one call, with the embeddings client the index was opened with."""
    if index.embeddings is None:
        raise IndexNotReadyError(UNREADABLE)
    # Our client embeds a query and a document the same way (no query instruction; T3.1).
    return index.embeddings.embed_documents(list(queries))


def search(
    index: Chroma,
    vectors: Sequence[Sequence[float]],
    where: dict[str, Any] | None = None,
    k: int | None = None,
    max_distance: float | None = None,
) -> list[RetrievedChunk]:
    """Search each query vector with the filter; return the k nearest distinct chunks overall."""
    k = config.RETRIEVAL_TOP_K if k is None else k
    max_distance = config.RETRIEVAL_MAX_DISTANCE if max_distance is None else max_distance
    nearest: dict[str, RetrievedChunk] = {}
    for vector in vectors:
        try:
            # The collection uses cosine space: the score is the cosine distance (lower is closer).
            found = index.similarity_search_by_vector_with_relevance_scores(
                list(vector), k=k, filter=where
            )
        except ChromaError:
            # E.g. a rebuild dropped the collection the running app holds; its message is internal.
            raise IndexNotReadyError(UNREADABLE) from None
        for doc, distance in found:
            if distance > max_distance:
                continue
            chunk = RetrievedChunk(doc.page_content, dict(doc.metadata), distance)
            key = chunk_key(chunk)
            # A chunk found by several queries counts once, at its smallest distance.
            if key not in nearest or distance < nearest[key].distance:
                nearest[key] = chunk
    # Nearest first; ties keep the order found. T3.3 replaces this merge with RRF.
    return sorted(nearest.values(), key=lambda chunk: chunk.distance)[:k]


def retrieve(
    index: Chroma,
    question: str,
    k: int | None = None,
    max_distance: float | None = None,
) -> list[RetrievedChunk]:
    """Return the k chunks nearest to the question, nearest first, dropping those too far away."""
    return search(index, embed_queries(index, [question]), k=k, max_distance=max_distance)
