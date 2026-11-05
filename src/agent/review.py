"""The weekly review as a fixed LangGraph workflow with the coach's decision (T9.16, D17).

authorise -> compute -> retrieve -> draft -> validate -> save -> decide (interrupt) -> release or
reject. Unlike the chat (D9), where the model picks its next step, every step here is fixed and the
model only writes the draft; the numbers are computed in Python and the citations checked in code,
and a person decides before anything reaches the client: the course's human-in-the-loop pattern.

- **authorise** asks the store (`reviews.prepare_review()`): the coach's active client, sharing
  nutrition, for a finished week with no pending or approved review; else the run ends with "not
  found" (AC-21), "exists" or "not finished", and no model or embedding call is made.
- **compute** reads the week through `dashboard.client_week()` (the store authorises and audits
  each scope) and builds the aggregates of `src/metrics.py` for "the client" (never a name).
- **retrieve** searches only the topics the metrics raise, with fixed queries (no client text).
- **draft** asks the model for `WeeklyReview` with structured output; **validate** runs the checks
  of `src/weekly_review.py` and sends the failed checks back once; a second failure ends the run
  with no review.
- **save** stores the draft as PENDING_REVIEW with its scopes, evidence and thread (AC-28), then
  **decide** pauses with `interrupt()`. The coach's Approve, Edit or Reject resumes it with
  `Command(resume=...)`: an edit must pass the safety checks first (AC-35); **release** and
  **reject** decide in the store, which checks again that every scope the review used is still
  shared (AC-22). A refusal there pauses the run again, so the review waits until the client shares
  again (or either side's data is deleted).

The run is checkpointed in the SqliteSaver file of `review_threads` (D12), one thread per run, with
the coach's and the client's IDs as metadata. The thread is deleted when the run ends; only a
review waiting for the coach keeps one. A model or embedding error ends the run with no review and
no thread (AC-30); the error is logged as a diagnostic and the caller shows a fixed message.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any, Literal, TypedDict

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src import account, config, dashboard, llm, metrics
from src import weekly_review as wr
from src.agent import review_threads
from src.rag import hybrid
from src.rag.hybrid import KeywordIndex
from src.rag.retriever import RetrievedChunk, chunk_key, embed_queries
from src.rag.store import IndexNotReadyError
from src.store import reviews
from src.store.access import NotFound

logger = logging.getLogger(__name__)

# How a run ended (or why it waits); the UI shows a fixed text for each (src/i18n.py, review.*).
Outcome = Literal[
    "pending",
    "not_found",
    "exists",
    "not_finished",
    "invalid",
    "edit_invalid",
    "approved",
    "edited",
    "rejected",
    "error",
    "gone",
]
# Every attempt at a draft: the first and the one retry (D17).
MAX_DRAFTS = 2
# The most supersteps a run can take: one per node with two drafts, plus the decision loops a
# coach can cause by refused edits, which each wait for the coach; LangGraph counts per invoke.
MAX_STEPS = 12
_DECISIONS = ("approve", "edit", "reject")
# The errors that end a run with a fixed message: the model or embedding service, the index, the
# key. Each has (or gets here) the key of its message in src/i18n.py.
_RUN_ERRORS = (
    llm.LLMError,
    IndexNotReadyError,
    config.MissingAPIKeyError,
)
_SETUP_CODES: dict[type, str] = {
    config.SecretsFileError: "key.secrets_file",
    config.MissingAPIKeyError: "key.missing",
}
_ENDED = frozenset({"approved", "edited", "rejected"})


class ReviewState(TypedDict, total=False):
    """A run's state, checkpointed while it waits: IDs, the week's aggregates, evidence, draft."""

    coach_id: str
    client_id: str
    week: str
    language: str
    thread_id: str
    scopes: list[str]
    metrics: dict
    data_quality: dict
    # The retrieved chunks as plain values (text and metadata), labelled [S1]... in this order.
    chunks: list[dict]
    draft: dict | None
    errors: list[str]
    attempts: int
    review_id: int | None
    decision: dict | None
    outcome: Outcome


@dataclass(frozen=True)
class ReviewContext:
    """What the nodes use but never keep in state: the store file, the index, the model, prompt."""

    store_path: Path
    # Called only after authorise and compute pass, so a refused run builds no client.
    chat_model: Callable[[], BaseChatModel] = field(
        default=lambda: llm.build_chat_model(config.REVIEW_MODEL, config.REVIEW_MAX_TOKENS)
    )
    open_index: Callable[[], Chroma] | None = None
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index
    prompt: str = ""
    # The day the run counts as today (Europe/Berlin); None for the real day. Tests set it.
    today: date | None = None


@dataclass(frozen=True)
class RunResult:
    """What a start or a decision gives the UI: the outcome, the review, the failed checks."""

    outcome: Outcome
    review_id: int | None = None
    errors: tuple[str, ...] = ()
    # The LLMError's diagnostic code for an "error" outcome (never its message).
    error_code: str | None = None


def _chunk_values(chunk: RetrievedChunk) -> dict:
    """Return a chunk as plain values for the checkpointed state."""
    return {"text": chunk.text, "metadata": dict(chunk.metadata), "distance": chunk.distance}


def chunks_of(state: Mapping) -> list[RetrievedChunk]:
    """Return the run's chunks from its state, in label order."""
    return [
        RetrievedChunk(item["text"], dict(item["metadata"]), item["distance"])
        for item in state.get("chunks", ())
    ]


def _monday(state: Mapping) -> date:
    """Return the run's week as its Monday."""
    return date.fromisoformat(state["week"])


def authorise(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """End with not found, exists or not finished; else keep the scopes the review may use."""
    monday = _monday(state)
    today = runtime.context.today or metrics.berlin_day()
    if monday.weekday() != 0 or monday + timedelta(days=6) >= today:
        return {"outcome": "not_finished"}
    try:
        with account.open_store(runtime.context.store_path) as conn:
            scopes = reviews.prepare_review(conn, state["coach_id"], state["client_id"], monday)
    except NotFound:
        return {"outcome": "not_found"}
    except reviews.ReviewExists:
        return {"outcome": "exists"}
    return {"scopes": list(scopes)}


def compute(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """Read the week through the store's checks and turn it into aggregates for the model."""
    try:
        with account.open_store(runtime.context.store_path) as conn:
            week = dashboard.client_week(
                conn, state["coach_id"], state["client_id"], _monday(state)
            )
    except NotFound:
        return {"outcome": "not_found"}
    # A scope revoked since authorise was not read, so the review does not use it.
    scopes = [scope for scope in state["scopes"] if scope in week.shared]
    if "nutrition" not in scopes:
        return {"outcome": "not_found"}
    found = wr.aggregates(week, scopes)
    return {"scopes": scopes, "metrics": found, "data_quality": wr.data_quality(found, scopes)}


def _search(context: ReviewContext, topics: Sequence[str]) -> list[RetrievedChunk]:
    """Search each topic's fixed query within that topic; at most REVIEW_MAX_CHUNKS in all."""
    if not topics or context.open_index is None:
        return []
    index = context.open_index()
    queries = [config.REVIEW_EVIDENCE_QUERIES[topic] for topic in topics]
    with llm.mapped_errors():
        vectors = embed_queries(index, queries)
    per_topic = []
    for topic, query, vector in zip(topics, queries, vectors, strict=True):
        where = {"topics": {"$contains": topic}}
        per_topic.append(
            hybrid.hybrid_search(index, [query], [vector], where, context.keyword_index)
        )
    # Taken in turns, one per topic, so every raised topic gets a place before any gets a second.
    chosen: dict[str, RetrievedChunk] = {}
    for rank in range(config.REVIEW_MAX_CHUNKS):
        for found in per_topic:
            if rank < len(found) and len(chosen) < config.REVIEW_MAX_CHUNKS:
                chosen.setdefault(chunk_key(found[rank]), found[rank])
    return list(chosen.values())


def retrieve(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """Find the evidence for the topics the metrics raise, with no client text in the queries."""
    found = _search(runtime.context, wr.evidence_topics(state["metrics"]))
    return {"chunks": [_chunk_values(chunk) for chunk in found], "attempts": 0, "errors": []}


def draft(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """Ask the model for the review with structured output; an unusable reply fails the schema."""
    messages = wr.build_messages(
        runtime.context.prompt,
        state["metrics"],
        chunks_of(state),
        state["language"],
        state.get("errors", ()),
    )
    model = runtime.context.chat_model()
    structured = model.with_structured_output(
        wr.WeeklyReview, method="json_schema", include_raw=True
    )
    attempts = state.get("attempts", 0) + 1
    try:
        with llm.mapped_errors():
            reply = structured.invoke(messages)
    except llm.InvalidReplyError, llm.ReplyCutOffError:
        # A reply off the schema or cut off: a failed check like any other, retried once.
        return {"draft": None, "attempts": attempts}
    parsed = reply.get("parsed") if isinstance(reply, Mapping) else None
    if reply.get("parsing_error") is not None or not isinstance(parsed, wr.WeeklyReview):
        return {"draft": None, "attempts": attempts}
    raw = reply.get("raw")
    version = raw.response_metadata.get("model_name") if isinstance(raw, AIMessage) else None
    return {
        "draft": {**wr.as_draft(parsed, state["language"]), "model": version or ""},
        "attempts": attempts,
    }


def validate(state: ReviewState) -> dict[str, Any]:
    """Run the draft's checks; the codes of the failed ones go back to the model once."""
    found = state.get("draft")
    if found is None:
        return {"errors": ["schema"]}
    return {"errors": wr.validate(wr.without_language(found), chunks_of(state), state["metrics"])}


def after_validate(state: ReviewState) -> str:
    """Save a valid draft, retry once, then end with no review."""
    if not state.get("errors"):
        return "save"
    return "draft" if state.get("attempts", 0) < MAX_DRAFTS else "invalid"


def invalid(state: ReviewState) -> dict[str, Any]:
    """End a run whose draft failed its checks twice: no review is saved."""
    return {"outcome": "invalid"}


def save(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """Store the draft as PENDING_REVIEW with its scopes, evidence and thread (AC-28)."""
    stored = dict(state["draft"])
    version = stored.pop("model", "") or config.REVIEW_MODEL
    stored["sources"] = wr.cited_sources(stored, chunks_of(state))
    try:
        with account.open_store(runtime.context.store_path) as conn:
            review_id = reviews.save_review(
                conn,
                state["coach_id"],
                state["client_id"],
                period_start=_monday(state),
                metrics=state["metrics"],
                data_quality=state["data_quality"],
                draft=stored,
                model_version=version,
                evidence_refs=wr.evidence_refs(stored, chunks_of(state)),
                scopes=state["scopes"],
                thread_id=state["thread_id"],
            )
    except NotFound:
        return {"outcome": "not_found"}
    except reviews.ReviewExists:
        return {"outcome": "exists"}
    return {"review_id": review_id, "outcome": "pending", "errors": []}


def after_save(state: ReviewState) -> str:
    """Wait for the coach once the review is saved; else end."""
    return "decide" if state.get("outcome") == "pending" else END


def _decision(answer: object) -> dict | None:
    """Return the coach's answer as {decision, final} if it has that shape; else None."""
    if not isinstance(answer, Mapping) or answer.get("decision") not in _DECISIONS:
        return None
    final = answer.get("final")
    if (answer["decision"] == "edit") != isinstance(final, Mapping):
        return None
    return {"decision": answer["decision"], "final": dict(final) if final is not None else None}


def decide(state: ReviewState) -> dict[str, Any]:
    """Pause for the coach's Approve, Edit or Reject; an edit must pass the safety checks."""
    answer = _decision(interrupt({"review_id": state["review_id"]}))
    if answer is None:
        return {"decision": None, "errors": ["schema"], "outcome": "edit_invalid"}
    if answer["decision"] == "edit":
        errors = wr.check_edit(answer["final"], chunks_of(state))
        if errors:
            return {"decision": None, "errors": errors, "outcome": "edit_invalid"}
    return {"decision": answer, "errors": []}


def after_decide(state: ReviewState) -> str:
    """Release an approval or an edit, reject a rejection, ask again after a refused edit."""
    answer = state.get("decision")
    if answer is None:
        return "decide"
    return "reject" if answer["decision"] == "reject" else "release"


def _decide_in_store(state: ReviewState, context: ReviewContext) -> dict[str, Any]:
    """Store the decision; NotFound (a scope revoked, AC-22) leaves the review waiting."""
    answer = state["decision"]
    final = None
    if answer["decision"] == "edit":
        edited = wr.without_language(answer["final"])
        final = {
            **edited,
            "language": state["language"],
            "sources": wr.cited_sources(edited, chunks_of(state)),
        }
    try:
        with account.open_store(context.store_path) as conn:
            reviews.decide_review(
                conn, state["coach_id"], state["review_id"], answer["decision"], final
            )
    except NotFound:
        return {"decision": None, "outcome": "not_found"}
    outcome = {"approve": "approved", "edit": "edited", "reject": "rejected"}[answer["decision"]]
    return {"outcome": outcome}


def release(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """Approve the draft, or the coach's edit, so it reaches the client (AC-29)."""
    return _decide_in_store(state, runtime.context)


def reject(state: ReviewState, runtime: Runtime[ReviewContext]) -> dict[str, Any]:
    """Reject the draft: it never reaches the client, and the week may be run again."""
    return _decide_in_store(state, runtime.context)


def after_decision(state: ReviewState) -> str:
    """End once decided; wait again when the store refused (a scope revoked)."""
    return END if state.get("outcome") in _ENDED else "decide"


def after_check(state: ReviewState) -> str:
    """Go on unless a step ended the run (not found, exists, not finished)."""
    return END if state.get("outcome") else "next"


def _builder() -> StateGraph:
    """Return the review's graph builder: the nodes and edges of D17."""
    builder = StateGraph(ReviewState, context_schema=ReviewContext)
    for name, node in (
        ("authorise", authorise),
        ("compute", compute),
        ("retrieve", retrieve),
        ("draft", draft),
        ("validate", validate),
        ("invalid", invalid),
        ("save", save),
        ("decide", decide),
        ("release", release),
        ("reject", reject),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "authorise")
    builder.add_conditional_edges("authorise", after_check, {"next": "compute", END: END})
    builder.add_conditional_edges("compute", after_check, {"next": "retrieve", END: END})
    builder.add_edge("retrieve", "draft")
    builder.add_edge("draft", "validate")
    builder.add_conditional_edges("validate", after_validate, ["save", "draft", "invalid"])
    builder.add_edge("invalid", END)
    builder.add_conditional_edges("save", after_save, ["decide", END])
    builder.add_conditional_edges("decide", after_decide, ["release", "reject", "decide"])
    builder.add_conditional_edges("release", after_decision, ["decide", END])
    builder.add_conditional_edges("reject", after_decision, ["decide", END])
    return builder


def review_graph(saver: SqliteSaver) -> CompiledStateGraph:
    """Return the review graph compiled with the run's checkpointer."""
    return _builder().compile(checkpointer=saver)


@cache
def mermaid() -> str:
    """Return the review graph as a Mermaid diagram, as docs/ARCHITECTURE.md shows it."""
    return _builder().compile().get_graph().draw_mermaid()


def _run_config(thread_id: str, coach_id: str, client_id: str) -> RunnableConfig:
    """Return a run's config: its thread, the IDs as checkpoint metadata, the step limit."""
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            review_threads.COACH_KEY: coach_id,
            review_threads.CLIENT_KEY: client_id,
        },
        "recursion_limit": MAX_STEPS,
    }


def _result(values: Mapping) -> RunResult:
    """Return the outcome a run's state ends or waits with."""
    return RunResult(
        outcome=values.get("outcome") or "invalid",
        review_id=values.get("review_id"),
        errors=tuple(values.get("errors") or ()),
    )


def _failed(exc: Exception) -> RunResult:
    """Log a failed run by its codes only and return the error outcome with the message's key."""
    code = getattr(exc, "code", None) or _SETUP_CODES.get(type(exc), "llm.error")
    logger.warning(
        "llm_error",
        extra={
            "kind": "weekly_review",
            "code": code,
            "status_code": getattr(exc, "status_code", None),
            "diagnostic": getattr(exc, "diagnostic", None) or llm.error_diagnostic(exc),
        },
    )
    return RunResult(outcome="error", error_code=code)


def start_review(
    context: ReviewContext, coach_id: str, client_id: str, monday: date, language: str
) -> RunResult:
    """Run a new review up to the coach's decision; a run that ends keeps no thread."""
    thread_id = review_threads.new_thread_id()
    run = _run_config(thread_id, coach_id, client_id)
    start: ReviewState = {
        "coach_id": coach_id,
        "client_id": client_id,
        "week": monday.isoformat(),
        "language": language,
        "thread_id": thread_id,
    }
    with review_threads.open_saver(context.store_path) as saver:
        graph = review_graph(saver)
        try:
            graph.invoke(start, run, context=context)
        except _RUN_ERRORS as exc:
            # No review is saved and nothing of the client's logs changes (AC-30).
            review_threads.delete_threads(saver, [thread_id])
            return _failed(exc)
        except BaseException:
            review_threads.delete_threads(saver, [thread_id])
            raise
        values = graph.get_state(run).values
        result = _result(values)
        if result.outcome != "pending":
            review_threads.delete_threads(saver, [thread_id])
        _log(result, values)
    return result


def _log(result: RunResult, values: Mapping) -> None:
    """Write one line per run or decision: the outcome, counts and codes, never a value."""
    logger.info(
        "weekly_review",
        extra={
            "code": result.outcome,
            "attempts": values.get("attempts", 0),
            "chunks": len(values.get("chunks", ())),
            "checks": list(result.errors),
        },
    )


def waiting(context: ReviewContext, thread_id: str) -> Mapping | None:
    """Return the state of a run that waits for the coach; None if there is no such run."""
    with review_threads.open_saver(context.store_path) as saver:
        snapshot = review_graph(saver).get_state({"configurable": {"thread_id": thread_id}})
    if not snapshot.next or snapshot.next != ("decide",):
        return None
    return snapshot.values


def decide_review(
    context: ReviewContext,
    coach_id: str,
    review_id: int,
    thread_id: str,
    decision: str,
    final: Mapping | None = None,
) -> RunResult:
    """Resume a waiting review with the coach's decision; the thread goes once it is decided."""
    with review_threads.open_saver(context.store_path) as saver:
        graph = review_graph(saver)
        snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
        values = snapshot.values
        # Only the coach who started this run, for this review, may resume it.
        if snapshot.next != ("decide",) or values.get("review_id") != review_id:
            return RunResult(outcome="gone")
        if values.get("coach_id") != coach_id:
            return RunResult(outcome="not_found")
        run = _run_config(thread_id, coach_id, values["client_id"])
        answer = {"decision": decision, "final": None if final is None else dict(final)}
        graph.invoke(Command(resume=answer), run, context=context)
        values = graph.get_state(run).values
        result = _result(values)
        if result.outcome in _ENDED:
            review_threads.delete_threads(saver, [thread_id])
        _log(result, values)
    return result
