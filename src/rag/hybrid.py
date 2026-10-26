"""Keyword (BM25) search over the chunks, and Reciprocal Rank Fusion of ranked lists (T3.3).

Vector search finds passages by meaning; BM25 finds exact terms a vector can miss ("HMB", a food
name). RRF merges the ranked lists without comparing their scores: each chunk scores the sum of
1 / (RRF_K + rank) over the lists it is in (docs/ARCHITECTURE.md, D4).
"""

import math
import re
from collections.abc import Callable, Collection, Sequence
from typing import Any

from chromadb.errors import ChromaError
from langchain_chroma import Chroma
from rank_bm25 import BM25Okapi

from src import config
from src.rag.retriever import RetrievedChunk, chunk_key, vector_lists
from src.rag.store import UNREADABLE, IndexNotReadyError

# ASCII letters and digits, enough for the English sources: "omega-3" gives "omega" and "3",
# "B12" gives "b12". An accented letter splits a word ("naïve"), and a lone letter such as the
# "D" of "vitamin D" is dropped by tokenize().
_TOKEN = re.compile(r"[a-z0-9]+")
# Common English words that say nothing about the topic, so a question's "how much should I" does
# not rank passages by how often they use those words. Written for this project.
STOPWORDS = frozenset(
    """
    a about after all also am an and any are as at be been before being but by can could did do
    does doing during each for from had has have having he her his how i if in into is it its
    just many me more most much my no not of on or our out over per she should so some such than
    that the their them then there these they this those through to too under up very was we
    were what when where which while who whom why will with would you your
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Return the text's search words: lower case, letters and digits, no stopwords."""
    # Single characters ("g", "3") match too much to help.
    return [
        word for word in _TOKEN.findall(text.casefold()) if len(word) > 1 and word not in STOPWORDS
    ]


class KeywordIndex:
    """A BM25 index over every chunk of the knowledge base, kept in memory."""

    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        """Index the chunks' texts; a chunk found by keyword has no distance (None)."""
        self.chunks = tuple(chunks)
        self.ids = tuple(chunk_key(chunk) for chunk in self.chunks)
        corpus = [tokenize(chunk.text) for chunk in self.chunks]
        # BM25Okapi divides by the corpus size and the vocabulary size, so both must be non-zero.
        self._bm25 = BM25Okapi(corpus) if any(corpus) else None

    def search(
        self, query: str, allowed: Collection[str] | None = None, k: int | None = None
    ) -> list[RetrievedChunk]:
        """Return the k chunks that match the query's words best, among the allowed IDs if given."""
        k = config.RETRIEVAL_TOP_K if k is None else k
        words = tokenize(query)
        if self._bm25 is None or not words:
            return []
        scores = self._bm25.get_scores(words)
        ranked = [
            (score, number)
            for number, score in enumerate(scores)
            # A score of 0 or less shares no useful word with the query (rank_bm25 can give a word
            # in more than half of a small corpus a negative weight).
            if score > 0 and (allowed is None or self.ids[number] in allowed)
        ]
        # Best first; ties keep the index order, so the result does not depend on the sort.
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [self.chunks[number] for _, number in ranked[:k]]


def build_keyword_index(index: Chroma) -> KeywordIndex:
    """Read every chunk's text and metadata from the Chroma index and build the BM25 index."""
    try:
        stored = index.get(include=["documents", "metadatas"])
    except ChromaError:
        raise IndexNotReadyError(UNREADABLE) from None
    chunks = [
        RetrievedChunk(text or "", dict(metadata or {}), None)
        for text, metadata in zip(stored["documents"], stored["metadatas"], strict=True)
    ]
    return KeywordIndex(chunks)


def filter_ids(index: Chroma, where: dict[str, Any] | None) -> set[str] | None:
    """Return the IDs of the chunks that pass the Chroma filter, or None when there is none."""
    # Chroma applies the filter itself, so keyword search uses exactly the vector search's filter.
    if where is None:
        return None
    try:
        return set(index.get(where=where, include=[])["ids"])
    except ChromaError:
        raise IndexNotReadyError(UNREADABLE) from None


def hybrid_search(
    index: Chroma,
    queries: Sequence[str],
    vectors: Sequence[Sequence[float]],
    where: dict[str, Any] | None,
    keyword_index: Callable[[Chroma], KeywordIndex],
) -> list[RetrievedChunk]:
    """Return [] unless the question (queries[0]) has a vector hit; else RRF of all query lists."""
    # queries[0] is the question as asked, the rest its rewrites, in the order of `vectors`.
    by_meaning = vector_lists(index, vectors, where)
    # Vector search decides whether the sources cover the question at all (RETRIEVAL_MAX_DISTANCE):
    # a keyword match has no distance, and a shared word alone would let an off-topic question
    # through (owner's choice in T3.3). Only the question's own list decides: the limit was
    # measured on questions as asked, and one rewrite alone ("VAR and offside rule in football")
    # can come within it for an off-topic question (owner's choice in T3.8). Once the question is
    # covered, the rewrites' vector lists and keyword search add their chunks.
    if not by_meaning or not by_meaning[0]:
        return []
    allowed = filter_ids(index, where)
    keywords = keyword_index(index)
    by_keyword = [keywords.search(query, allowed) for query in queries]
    return rrf([*by_meaning, *by_keyword])


def _distance_order(chunk: RetrievedChunk) -> float:
    """Return the chunk's distance for sorting; a chunk found by keyword only sorts last."""
    return float("inf") if chunk.distance is None else chunk.distance


def rrf_scores(lists: Sequence[Sequence[RetrievedChunk]]) -> dict[str, float]:
    """Return each chunk's RRF score by chunk ID, in the order the chunks were first found."""
    terms: dict[str, list[float]] = {}
    for ranked in lists:
        for rank, chunk in enumerate(ranked, start=1):
            terms.setdefault(chunk_key(chunk), []).append(1 / (config.RRF_K + rank))
    # fsum is correctly rounded, so the same ranks in another order give the same float and a
    # true tie stays a tie (plain + gave 1/61 + 1/61 + 1/66 and 1/66 + 1/61 + 1/61 one ulp apart).
    return {key: math.fsum(values) for key, values in terms.items()}


def rrf(
    lists: Sequence[Sequence[RetrievedChunk]],
    k: int | None = None,
    max_per_source: int | None = None,
) -> list[RetrievedChunk]:
    """Merge ranked lists with RRF; return k chunks, a source's extras over the cap come last."""
    k = config.RETRIEVAL_TOP_K if k is None else k
    max_per_source = config.MAX_CHUNKS_PER_SOURCE if max_per_source is None else max_per_source
    scores = rrf_scores(lists)
    best: dict[str, RetrievedChunk] = {}
    for ranked in lists:
        for chunk in ranked:
            key = chunk_key(chunk)
            # Kept at its smallest distance, so a chunk vectors found keeps its distance.
            if key not in best or _distance_order(chunk) < _distance_order(best[key]):
                best[key] = chunk
    # Highest score first; ties go to the nearer chunk, then to the first found (dicts keep order).
    order = {key: number for number, key in enumerate(scores)}
    keys = sorted(scores, key=lambda key: (-scores[key], _distance_order(best[key]), order[key]))
    # Every candidate is ranked first; then a source keeps its best max_per_source chunks, so one
    # article cannot fill the list (T8.3). The chunks over the cap wait in fused order and fill the
    # places only when the other sources run out, so a single-source list is still k long.
    kept: list[str] = []
    skipped: list[str] = []
    per_source: dict[str, int] = {}
    for key in keys:
        source = str(best[key].metadata.get("source_id"))
        if per_source.get(source, 0) < max_per_source:
            per_source[source] = per_source.get(source, 0) + 1
            kept.append(key)
        else:
            skipped.append(key)
    return [best[key] for key in [*kept[:k], *skipped][:k]]
