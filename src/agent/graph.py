"""One chat turn as a LangGraph `StateGraph` (T9.2, D9): the same steps as before, as nodes.

guard -> prepare -> translate -> retrieve -> agent <-> tools -> end_round -> finish. The guard runs
first and a rejected input goes straight to the end, so it opens no index and calls no model
(security-privacy.md, "Guards"); a question the sources do not cover ends after retrieval, as
before (AC-2, T3.5). The agent node and a `ToolNode` loop for at most `MAX_TOOL_ROUNDS` rounds;
the `ToolNode` runs each call through `registry.run_tool_call()` (validated arguments, fixed
messages) within the per-round limits.

The caller passes the text and the profile and gets back only the `TurnResult`: the messages,
the chunks, the plan and the tool runs are private state. What cannot live in state (the index,
the model clients, the UI's callbacks, the rate limiter and the turn's `UsageRecorder`) is the
run's context (`TurnContext`). The recorder is there, not in state, because a node that raises
loses its state update, and an error result must keep the tokens spent before it (T5.1, T1.8).
Errors are raised as before and mapped to a fixed message by `chat.run_turn()`.
"""

import logging
import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache, partial
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_core.tools.base import ToolCall
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from src import chat, config, guard, i18n, llm, usage
from src.chat import Step, TurnResult
from src.profile import UserProfile
from src.rag import hybrid, query_translation
from src.rag.hybrid import KeywordIndex
from src.rag.query_translation import QueryPlan
from src.rag.retriever import RetrievedChunk
from src.rag.sources import Source
from src.tools import registry
from src.tools.registry import ToolRun
from src.usage import UsageRecorder

logger = logging.getLogger(__name__)

# The most supersteps a turn can take: guard, prepare, translate and retrieve, then one agent call
# more than there are tool rounds, a tools and an end_round step per round, and finish. A graph
# that loops past it is a bug, which the turn's catch-all reports (T1.8).
MAX_STEPS = 3 * config.MAX_TOOL_ROUNDS + 6


class TurnInput(TypedDict):
    """What the caller gives the graph: the user's raw text and the session's profile."""

    text: str
    profile: UserProfile | None


class TurnOutput(TypedDict):
    """What the caller gets back: the turn's result, nothing else."""

    result: TurnResult


class LoopInput(TypedDict):
    """What the answer loop starts from: the request's messages and whether no source was found."""

    messages: Annotated[list[AnyMessage], add_messages]
    # True when no chunk is relevant: replies stay hidden until a tool really runs (T4.4).
    tools_only: bool


class LoopOutput(TypedDict):
    """What the answer loop ends with: the answer (None: not covered) and the tool runs."""

    answer: str | None
    runs: Annotated[list[ToolRun], operator.add]


class TurnState(TurnInput, TurnOutput, LoopInput, LoopOutput, total=False):
    """The whole state of a turn; every key but text, profile and result is private."""

    # The cleaned text the guard accepted; the answer model gets it, never the rewrites.
    question: str
    system_prompt: str
    translation_prompt: str
    plan: QueryPlan | None
    details: chat.SearchDetails
    chunks: list[RetrievedChunk]
    # True when the answer request carries the <profile> block (T3.5).
    include_profile: bool
    # Tool rounds done so far.
    rounds: int


@dataclass(frozen=True)
class TurnContext:
    """What a turn's nodes use but never keep in state: clients, callbacks, limiter, recorder."""

    # Each factory is called once per turn (run_turn() caches them), only after the guard.
    chat_model: Callable[[], BaseChatModel]
    tools: Callable[[], Mapping[str, StructuredTool]]
    on_step: Callable[[Step], None]
    on_text: Callable[[str], None] | None = None
    recorder: UsageRecorder | None = None
    on_tool_run: Callable[[ToolRun], None] | None = None
    # Only the whole turn uses these; the answer loop alone (chat.answer_with_tools()) does not.
    limiter: guard.RateLimiter | None = None
    open_index: Callable[[], Chroma] | None = None
    translation_model: Callable[[], BaseChatModel] | None = None
    manifest: Mapping[str, Source] | None = None
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index
    language: i18n.Language = "en"
    on_chunks: Callable[[Sequence[RetrievedChunk]], None] | None = None
    on_profile_sent: Callable[[], None] | None = None
    turn_id: str = ""


def run_config() -> RunnableConfig:
    """Return the config every turn runs with: the step limit, and tool calls one at a time."""
    # ToolNode runs a round's calls in worker threads; one at a time keeps them in order, as before.
    # LangGraph counts the input as a step too, so the limit is one more than the node steps.
    return {"recursion_limit": MAX_STEPS + 1, "max_concurrency": 1}


def load_prompt(path: Path, message: str, code: str) -> str:
    """Return a prompt file's text; raise PromptMissingError with message if it is unusable."""
    try:
        return chat.load_system_prompt(path)
    except OSError, ValueError:
        raise chat.PromptMissingError(message, code) from None


def _last_reply(messages: Sequence[AnyMessage]) -> AIMessage:
    """Return the latest model reply in the messages."""
    return next(message for message in reversed(messages) if isinstance(message, AIMessage))


def _answer_text(reply: AIMessage) -> str:
    """Return the text of the model's reply; raise LLMError if it is empty."""
    text = chat.remove_images(reply.text).strip()
    if not text:
        raise llm.LLMError(diagnostic="empty answer")
    return text


# --- Nodes -----------------------------------------------------------------------------------


def guard_node(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Check the input before anything else; a rejected one ends the turn with its message."""
    context = runtime.context
    context.on_step(Step.CHECK)
    decision = guard.check_message(state["text"], context.limiter)
    if decision.allowed:
        return {"question": decision.text}
    reason = decision.reason.value if decision.reason is not None else None
    logger.warning(
        "guard_rejected",
        extra={"turn_id": context.turn_id, "reason": reason, "code": decision.code},
    )
    kind = "guardrail" if decision.reason is guard.Rejection.GUARDRAIL else "rejected"
    result = TurnResult(kind, decision.message or "", code=decision.code, params=decision.params)
    return {"result": result}


def prepare(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Read the prompts, then open the index and the clients, for an accepted question only."""
    context = runtime.context
    # Read before any API call, so a missing or empty prompt file costs nothing.
    system_prompt = load_prompt(
        config.ANSWER_PROMPT_PATH, config.PROMPT_MISSING_MESSAGE, "prompt.answer_missing"
    )
    translation_prompt = load_prompt(
        config.QUERY_TRANSLATION_PROMPT_PATH,
        config.QUERY_PROMPT_MISSING_MESSAGE,
        "prompt.query_missing",
    )
    language_part = load_prompt(
        config.ANSWER_LANGUAGE_PROMPT_PATHS[context.language],
        config.LANGUAGE_PROMPT_MISSING_MESSAGE,
        "prompt.language_missing",
    )
    # The index is opened first: a missing index is reported even when the key is missing.
    context.open_index()
    context.translation_model()
    context.chat_model()
    return {
        "system_prompt": chat.answer_system_prompt(system_prompt, language_part),
        "translation_prompt": translation_prompt,
    }


def translate(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Rewrite the question and pick its filters (None when the reply is unusable, T3.2)."""
    context = runtime.context
    context.on_step(Step.REWRITE)
    plan = query_translation.translate(
        state["question"],
        context.translation_model(),
        state["translation_prompt"],
        context.recorder,
    )
    return {"plan": plan}


def retrieve(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Search the question and its rewrites; end the turn if the sources do not cover it."""
    context = runtime.context
    question, plan = state["question"], state["plan"]
    context.on_step(Step.SEARCH)
    with llm.mapped_errors():
        chunks, details = chat.find_chunks(
            question,
            plan,
            context.open_index(),
            keyword_index=context.keyword_index,
            recorder=context.recorder,
        )
    # When nothing passed a training-only plan's filters (its topic, year or tier), the search
    # without them keeps only training chunks: a nutrition chunk never stands in for a missing
    # training source (PRD feature 26; T9.20, security review finding 3).
    training_only = plan is not None and plan.topics == (config.TRAINING_TOPIC,)
    if training_only and details.filter_dropped:
        chunks = [c for c in chunks if config.TRAINING_TOPIC in c.metadata.get("topics", ())]
    if context.on_chunks is not None:
        context.on_chunks(tuple(chunks))
    # With no relevant chunk the model may still answer from a tool (a food lookup rarely matches
    # a research passage; owner's choice in T4.4), but only when the plan says a tool could: an
    # off-topic question, or one with no usable plan, costs no answer call (AC-2; T3.5).
    if not chunks and not (plan is not None and plan.needs_tool):
        result = TurnResult(
            "no_sources", config.NO_SOURCES_MESSAGE, search=details, code="answer.no_sources"
        )
        return {"details": details, "result": result}
    context.on_step(Step.ANSWER)
    # The user's own question, never the rewrites, goes to the answer model. The profile goes
    # only when the plan says the answer needs the user's numbers (security-privacy.md; T3.5).
    include_profile = plan is not None and plan.needs_profile
    messages = chat.build_messages(
        question,
        chunks,
        state["system_prompt"],
        state.get("profile"),
        include_profile=include_profile,
    )
    if include_profile and context.on_profile_sent is not None:
        context.on_profile_sent()
    return {
        "details": details,
        "chunks": chunks,
        "include_profile": include_profile,
        # With no relevant chunk, replies stay hidden until a tool really runs.
        "tools_only": not chunks,
        "messages": messages,
    }


def agent(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Ask the model; keep its tool calls for the tools node, or its text as the answer."""
    # tools_only (no relevant source): replies are not shown until a tool has really run (a
    # refused call, e.g. an unknown tool or bad arguments, does not count), and a reply with no
    # tool call before that gives None, so the turn shows NO_SOURCES_MESSAGE, never an answer
    # with no basis.
    context = runtime.context
    round_number = state.get("rounds", 0)
    last = round_number >= config.MAX_TOOL_ROUNDS
    runs = state.get("runs", [])
    hidden = state.get("tools_only", False) and all(run.status == "invalid" for run in runs)
    chat_model = context.chat_model()
    # Only the tools are bound (never the model or max_tokens; security-privacy.md). After the
    # last round the model must answer from the results it has.
    tools = list(context.tools().values())
    bound = chat_model.bind_tools(tools, tool_choice="none" if last else None)
    record = None
    if context.recorder is not None:
        step = config.USAGE_STEP_ANSWER.format(round=round_number + 1)
        record = partial(context.recorder.add_chat, step, usage.model_name(chat_model))
    on_text = None if hidden else context.on_text
    try:
        reply = chat.stream_reply(bound, state["messages"], on_text, record)
    except llm.ReplyCutOffError:
        if hidden:
            # Nothing was shown and no tool ran: the turn ends as "not covered".
            return {"answer": None}
        raise
    if not reply.tool_calls and not reply.invalid_tool_calls:
        return {"answer": None if hidden else _answer_text(reply)}
    if last:
        raise chat.ToolLoopError(diagnostic="tool calls after the last round")
    if context.on_text is not None:
        # Text written before the tool calls is not the answer.
        context.on_text("")
    context.on_step(Step.TOOLS)
    request = AIMessage(
        reply.content, tool_calls=reply.tool_calls, invalid_tool_calls=reply.invalid_tool_calls
    )
    return {"messages": [request]}


def round_refusal(calls: Sequence[ToolCall], position: int) -> str | None:
    """Return the fixed message for a call over a round's limits, or None if it may run."""
    if position >= config.MAX_TOOL_CALLS_PER_ROUND:
        return config.TOO_MANY_TOOL_CALLS_MESSAGE
    # A meal plan's result is long (up to MEAL_PLAN_MAX_ITEMS foods), so fewer of them run (T4.5).
    if calls[position]["name"] == registry.MEAL_PLAN_TOOL:
        meal_plans = sum(call["name"] == registry.MEAL_PLAN_TOOL for call in calls[: position + 1])
        if meal_plans > config.MAX_MEAL_PLAN_CALLS_PER_ROUND:
            return config.TOO_MANY_MEAL_PLANS_MESSAGE
    return None


def run_checked_call(request: ToolCallRequest, execute: Callable[..., Any]) -> Command:
    """Run one call of the ToolNode's round through the registry, within the round's limits."""
    # `execute` (LangChain's own tool.invoke()) is never used: it skips the argument check for
    # tools without fields, and its error messages repeat what the model sent. run_tool_call()
    # validates every call and answers a failure with a fixed message (T4.4).
    context: TurnContext = request.runtime.context
    call = request.tool_call
    calls = _last_reply(request.state["messages"]).tool_calls
    # ToolNode passes the reply's own call objects, so the call's place in the round is found by
    # identity (two calls may share an id). A call not found there (a ToolNode that passed a copy)
    # is a bug the turn's catch-all reports, named here rather than as a StopIteration.
    position = next((number for number, other in enumerate(calls) if other is call), None)
    if position is None:
        raise RuntimeError("The tool call is not in the model's last reply.")
    refusal = round_refusal(calls, position)
    if refusal is not None:
        # OpenAI models always send call ids; a call without one gets "", which the API would
        # refuse on the next request (shown as a service error).
        message, run = registry.refused_call(call["id"] or "", refusal)
    else:
        message, run = registry.run_tool_call(context.tools(), call)
    # Each run is reported as it ends, so a turn that fails later still logs it (T8.2).
    if context.on_tool_run is not None:
        context.on_tool_run(run)
    return Command(update={"messages": [message], "runs": [run]})


def tool_node() -> ToolNode:
    """Return the ToolNode of the loop: every call goes through run_checked_call()."""
    # The tools it is built with give it the names and schemas; the turn's own tools (bound to
    # its profile) come from the context. handle_tool_errors=False: an error of ours is raised
    # to the turn's catch-all (T1.8), never written to the model.
    definitions = list(registry.build_tools(None).values())
    return ToolNode(definitions, wrap_tool_call=run_checked_call, handle_tool_errors=False)


def end_round(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Answer the round's calls that were not valid JSON, then go back to the model."""
    # Every call needs an answer; ToolNode reads only the parsed calls, so these come after the
    # round's results, as before.
    context = runtime.context
    refused = [
        registry.refused_call(call["id"] or "", config.INVALID_TOOL_JSON_MESSAGE)
        for call in _last_reply(state["messages"]).invalid_tool_calls
    ]
    if context.on_tool_run is not None:
        for _, run in refused:
            context.on_tool_run(run)
    context.on_step(Step.ANSWER)
    return {
        "messages": [message for message, _ in refused],
        "runs": [run for _, run in refused],
        "rounds": state.get("rounds", 0) + 1,
    }


def finish(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Build the turn's result: the answer with its cited sources, or "not covered"."""
    answer = state.get("answer")
    if answer is None:
        result = TurnResult(
            "no_sources",
            config.NO_SOURCES_MESSAGE,
            search=state["details"],
            profile_sent=state["include_profile"],
            code="answer.no_sources",
        )
        return {"result": result}
    chunks = state["chunks"]
    manifest = runtime.context.manifest or {}
    cards = chat.source_cards(chunks, chat.cited_labels(answer, len(chunks)), manifest)
    result = TurnResult(
        "answer",
        answer,
        cards,
        search=state["details"],
        tool_runs=tuple(state.get("runs", [])),
        profile_sent=state["include_profile"],
    )
    return {"result": result}


# --- Edges -----------------------------------------------------------------------------------


def after_guard(state: TurnState) -> str:
    """Go on with an accepted question; end the turn for a rejected one."""
    return END if "result" in state else "prepare"


def after_retrieve(state: TurnState) -> str:
    """Go on to the model; end the turn when the sources do not cover the question."""
    return END if "result" in state else "agent"


def after_agent(state: TurnState) -> str:
    """Run the tools when the model's last reply called any (even with bad JSON); else finish."""
    # Like LangGraph's tools_condition, but a reply whose only calls are not valid JSON is a
    # round too: each still gets a fixed answer (end_round).
    last = state["messages"][-1] if state.get("messages") else None
    if isinstance(last, AIMessage) and (last.tool_calls or last.invalid_tool_calls):
        return "tools"
    return "finish"


def _add_answer_loop(builder: StateGraph, done: str) -> None:
    """Add the agent, the ToolNode and end_round in a loop that leaves to `done`."""
    builder.add_node("agent", agent)
    builder.add_node("tools", tool_node())
    builder.add_node("end_round", end_round)
    builder.add_conditional_edges("agent", after_agent, {"tools": "tools", "finish": done})
    builder.add_edge("tools", "end_round")
    builder.add_edge("end_round", "agent")


@cache
def chat_graph() -> CompiledStateGraph:
    """Return the compiled graph of one chat turn; the caller gets only its result."""
    builder = StateGraph(
        TurnState, context_schema=TurnContext, input_schema=TurnInput, output_schema=TurnOutput
    )
    builder.add_node("guard", guard_node)
    builder.add_node("prepare", prepare)
    builder.add_node("translate", translate)
    builder.add_node("retrieve", retrieve)
    builder.add_node("finish", finish)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", after_guard, ["prepare", END])
    builder.add_edge("prepare", "translate")
    builder.add_edge("translate", "retrieve")
    builder.add_conditional_edges("retrieve", after_retrieve, ["agent", END])
    _add_answer_loop(builder, "finish")
    builder.add_edge("finish", END)
    return builder.compile()


@cache
def answer_loop_graph() -> CompiledStateGraph:
    """Return the compiled answer loop alone (the agent and the tools), for given messages."""
    builder = StateGraph(
        TurnState, context_schema=TurnContext, input_schema=LoopInput, output_schema=LoopOutput
    )
    builder.add_edge(START, "agent")
    _add_answer_loop(builder, END)
    return builder.compile()


def mermaid() -> str:
    """Return the chat graph as a Mermaid diagram, as docs/ARCHITECTURE.md shows it."""
    return chat_graph().get_graph().draw_mermaid()
