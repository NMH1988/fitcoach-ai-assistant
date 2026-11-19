"""The knowledge base search: the query and its rewrites, the filters and their retry."""

from collections.abc import Callable

from langchain_chroma import Chroma

from src import config
from src.chat.results import SearchDetails
from src.rag import hybrid, query_translation
from src.rag.hybrid import KeywordIndex
from src.rag.query_translation import QueryPlan
from src.rag.retriever import RetrievedChunk, embed_queries
from src.usage import UsageRecorder


def search_queries(query: str, plan: QueryPlan | None) -> tuple[str, ...]:
    """Return the plan's rewrites that differ from the query and from each other."""
    seen = {query.casefold()}
    rewrites = []
    for rewrite in plan.queries if plan is not None else ():
        if rewrite.casefold() not in seen:
            seen.add(rewrite.casefold())
            rewrites.append(rewrite)
    return tuple(rewrites)


# The retry filter of a plan whose topics are all nutrition: any topic but training (T9.20).
_NUTRITION_ONLY = {
    "$or": [{"topics": {"$contains": t}} for t in config.TOPICS if t != config.TRAINING_TOPIC]
}


def find_chunks(
    query: str,
    plan: QueryPlan | None,
    index: Chroma,
    *,
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index,
    recorder: UsageRecorder | None = None,
) -> tuple[list[RetrievedChunk], SearchDetails]:
    """Search the query and its rewrites by meaning and by keyword, merged with RRF (T3.3)."""
    rewrites = search_queries(query, plan)
    queries = (query, *rewrites)
    where = query_translation.build_filter(plan)
    # One embedding call for all the queries; the vectors serve the retry too.
    vectors = embed_queries(index, queries, recorder=recorder)
    chunks = hybrid.hybrid_search(index, queries, vectors, where, keyword_index)
    # Empty only when the query itself has no chunk within the distance limit (T3.8), even if a
    # rewrite has one; a filter that keeps fewer but relevant chunks stays.
    filter_dropped = not chunks and where is not None
    if filter_dropped:
        if plan is not None and plan.topics == (config.TRAINING_TOPIC,):
            # A training-only plan keeps its topic and drops only its year and tier, so the retry
            # passes the same distance gate on training chunks alone: neither a nutrition chunk nor
            # a training chunk that only shares a word stands in for a missing training source
            # (PRD feature 26; T9.20).
            topic_only = {"topics": {"$contains": config.TRAINING_TOPIC}}
            chunks = (
                []
                if where == topic_only
                else hybrid.hybrid_search(index, queries, vectors, topic_only, keyword_index)
            )
        elif plan is not None and plan.topics and config.TRAINING_TOPIC not in plan.topics:
            # Mirrored: a plan whose topics are all nutrition runs again over the nutrition topics,
            # so a training chunk never joins a nutrition answer (T9.20).
            chunks = hybrid.hybrid_search(index, queries, vectors, _NUTRITION_ONLY, keyword_index)
        else:
            # No topic, no usable plan, or both domains: search everything.
            chunks = hybrid.hybrid_search(index, queries, vectors, None, keyword_index)
    details = SearchDetails(
        query=query,
        rewrites=rewrites,
        topics=plan.topics if plan is not None else (),
        min_year=plan.min_year if plan is not None else None,
        evidence_tier=plan.evidence_tier if plan is not None else None,
        fell_back=plan is None,
        filter_dropped=filter_dropped,
        labels=tuple(range(1, len(chunks) + 1)),
    )
    return chunks, details
