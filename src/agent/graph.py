"""One chat turn as a LangGraph `StateGraph` (T9.2, D9), with agentic retrieval (T9.3, D10).

guard -> prepare -> agent <-> tools -> end_round -> finish. The guard runs first and a rejected
input goes straight to the end, so it opens no index and calls no model (security-privacy.md,
"Guards"). The agent node and a `ToolNode` loop for at most `MAX_TOOL_ROUNDS` rounds; the
`ToolNode` runs each call within the per-round limits, a knowledge base search through
`search.run_search()` and every other call through `registry.run_tool_call()` (validated
arguments, fixed messages). The agent decides whether to search: a food or calculator question
needs no research passage (the Sprint 2 review, point 3).

Its replies stay hidden until the answer has a basis: a search found a relevant chunk or a tool
really ran. A reply with no tool call before that, or a round whose searches found nothing with no
tool run, ends the turn with the "not covered" message and no further model call (AC-2; owner's
choice in T9.3, 2026-10-29).

The caller passes the text and gets back only the `TurnResult`: the messages and the tool runs are
private state. What cannot live in state (the index, the model clients, the UI's callbacks, the
rate limiter, the turn's `UsageRecorder` and its `SearchLog`) is the run's context (`TurnContext`).
The recorder is there, not in state, because a node that raises loses its state update, and an
error result must keep the tokens spent before it (T5.1, T1.8); the search log, because a round's
searches must number their chunks one after another before the round's updates are applied. The
profile is in neither: only the tools have it (`TurnContext.tools`). Errors are raised as before
and mapped to a fixed message by `chat.run_turn()`.
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
from src.agent import search
from src.agent.search import SearchLog
from src.chat import Step, TurnResult
from src.rag import hybrid
from src.rag.hybrid import KeywordIndex
from src.rag.retriever import RetrievedChunk
from src.rag.sources import Source
from src.tools import registry
from src.tools.registry import ToolRun
from src.usage import UsageRecorder

logger = logging.getLogger(__name__)

# The most supersteps a turn can take: guard and prepare, then one agent call more than there are
# tool rounds, a tools and an end_round step per round, and finish. A graph that loops past it is
# a bug, which the turn's catch-all reports (T1.8).
MAX_STEPS = 3 * config.MAX_TOOL_ROUNDS + 4


class TurnInput(TypedDict):
    """What the caller gives the graph: the user's raw text (the profile is the tools' alone)."""

    text: str


class TurnOutput(TypedDict):
    """What the caller gets back: the turn's result, nothing else."""

    result: TurnResult


class LoopInput(TypedDict):
    """What the answer loop starts from: the messages and whether replies wait for a basis."""

    messages: Annotated[list[AnyMessage], add_messages]
    # True: replies stay hidden until a search finds a relevant chunk or a tool really runs (T4.4,
    # T9.3). A whole turn always starts so; the answer loop alone may not.
    tools_only: bool


class LoopOutput(TypedDict):
    """What the answer loop ends with: the answer (None: not covered) and the tool runs."""

    answer: str | None
    runs: Annotated[list[ToolRun], operator.add]


class TurnState(TurnInput, TurnOutput, LoopInput, LoopOutput, total=False):
    """The whole state of a turn; every key but text, profile and result is private."""

    # The cleaned text the guard accepted; the model gets it, never a search's rewrites.
    question: str
    system_prompt: str
    # The query translation prompt, read before any API call and used by every search.
    translation_prompt: str
    # Tool rounds done so far.
    rounds: int
    # True when a round's searches found nothing and nothing else gave the answer a basis (AC-2).
    stopped: bool


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
    # The turn's searches and their labelled chunks (T9.3); None for the answer loop alone, which
    # is then not offered the search tool.
    search_log: SearchLog | None = None
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


def _has_basis(runs: Sequence[ToolRun], log: SearchLog | None) -> bool:
    """Return True once an answer has something to rest on: a relevant chunk or a real tool run."""
    # A refused call (an unknown tool, bad arguments, over a limit) does not count.
    return any(run.status != "invalid" for run in runs) or bool(log is not None and log.chunks)


def _tools(context: TurnContext) -> list[StructuredTool]:
    """Return the tools the model is given: the turn's own, and the search for a whole turn."""
    tools = list(context.tools().values())
    if context.search_log is not None:
        tools.append(search.search_tool_definition())
    return tools


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
    """Read the prompts, open the index and the clients, and build the request's messages."""
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
    # The index is opened first: a missing index is reported even when the key is missing. All
    # three are opened before the first model call, as before T9.3, so a turn that would search
    # meets a missing index or key before it spends anything.
    context.open_index()
    context.translation_model()
    context.chat_model()
    context.on_step(Step.PLAN)
    system = chat.answer_system_prompt(system_prompt, language_part)
    return {
        "system_prompt": system,
        "translation_prompt": translation_prompt,
        # The user's own question only; the chunks come in a search's tool message (T9.3).
        "messages": chat.build_messages(state["question"], system),
        "tools_only": True,
    }


def agent(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Ask the model; keep its tool calls for the tools node, or its text as the answer."""
    # tools_only: replies are not shown until the answer has a basis (a search found a relevant
    # chunk or a tool really ran; _has_basis()), and a reply with no tool call before that gives
    # None, so the turn shows NO_SOURCES_MESSAGE, never an answer with no basis (AC-2).
    context = runtime.context
    round_number = state.get("rounds", 0)
    last = round_number >= config.MAX_TOOL_ROUNDS
    hidden = state.get("tools_only", False) and not _has_basis(
        state.get("runs", []), context.search_log
    )
    chat_model = context.chat_model()
    # Only the tools are bound (never the model or max_tokens; security-privacy.md). After the
    # last round the model must answer from the results it has.
    bound = chat_model.bind_tools(_tools(context), tool_choice="none" if last else None)
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
    if on_text is not None:
        # Text written before the tool calls is not the answer (a hidden reply showed none).
        on_text("")
    # Reported here, on the caller's thread: the ToolNode runs the calls in a worker thread, and
    # Streamlit draws only from the script's thread.
    names = [call["name"] for call in (*reply.tool_calls, *reply.invalid_tool_calls)]
    if search.SEARCH_TOOL in names:
        context.on_step(Step.SEARCH)
    if any(name != search.SEARCH_TOOL for name in names):
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
    run: ToolRun | None
    if refusal is not None:
        # OpenAI models always send call ids; a call without one gets "", which the API would
        # refuse on the next request (shown as a service error).
        message, run = registry.refused_call(call["id"] or "", refusal)
    elif call["name"] == search.SEARCH_TOOL and context.search_log is not None:
        # A search that runs is no tool run: it goes into the turn's SearchLog (T9.3).
        message, run = search.run_search(context, call, request.state["translation_prompt"])
    else:
        message, run = registry.run_tool_call(context.tools(), call)
    if run is None:
        return Command(update={"messages": [message]})
    # Each run is reported as it ends, so a turn that fails later still logs it (T8.2).
    if context.on_tool_run is not None:
        context.on_tool_run(run)
    return Command(update={"messages": [message], "runs": [run]})


def tool_node() -> ToolNode:
    """Return the ToolNode of the loop: every call goes through run_checked_call()."""
    # The tools it is built with give it the names and schemas; the turn's own tools (bound to
    # its profile) come from the context. handle_tool_errors=False: an error of ours is raised
    # to the turn's catch-all (T1.8), never written to the model.
    definitions = [*registry.build_tools(None).values(), search.search_tool_definition()]
    return ToolNode(definitions, wrap_tool_call=run_checked_call, handle_tool_errors=False)


def end_round(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Answer the round's calls that were not valid JSON; stop if a search found no basis (AC-2)."""
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
    update: dict[str, Any] = {
        "messages": [message for message, _ in refused],
        "runs": [run for _, run in refused],
        "rounds": state.get("rounds", 0) + 1,
    }
    log = context.search_log
    runs = [*state.get("runs", []), *update["runs"]]
    if state.get("tools_only", False) and log is not None and log.searches:
        if not _has_basis(runs, log):
            # The searches found nothing and no tool ran: "not covered", with no further model
            # call (AC-2). A round of refused calls alone goes back to the model instead.
            return {**update, "stopped": True, "answer": None}
    context.on_step(Step.ANSWER)
    return update


def finish(state: TurnState, runtime: Runtime[TurnContext]) -> dict[str, Any]:
    """Build the turn's result: the answer with its cited sources, or "not covered"."""
    answer = state.get("answer")
    log = runtime.context.search_log or SearchLog()
    searches = tuple(log.searches)
    if answer is None:
        result = TurnResult(
            "no_sources", config.NO_SOURCES_MESSAGE, searches=searches, code="answer.no_sources"
        )
        return {"result": result}
    manifest = runtime.context.manifest or {}
    cards = chat.source_cards(log.chunks, chat.cited_labels(answer, len(log.chunks)), manifest)
    result = TurnResult(
        "answer",
        answer,
        cards,
        searches=searches,
        tool_runs=tuple(state.get("runs", [])),
    )
    return {"result": result}


# --- Edges -----------------------------------------------------------------------------------


def after_guard(state: TurnState) -> str:
    """Go on with an accepted question; end the turn for a rejected one."""
    return END if "result" in state else "prepare"


def after_agent(state: TurnState) -> str:
    """Run the tools when the model's last reply called any (even with bad JSON); else finish."""
    # Like LangGraph's tools_condition, but a reply whose only calls are not valid JSON is a
    # round too: each still gets a fixed answer (end_round).
    last = state["messages"][-1] if state.get("messages") else None
    if isinstance(last, AIMessage) and (last.tool_calls or last.invalid_tool_calls):
        return "tools"
    return "finish"


def after_round(state: TurnState) -> str:
    """Go back to the model after a round, unless its searches ended the turn (AC-2)."""
    return "finish" if state.get("stopped") else "agent"


def _add_answer_loop(builder: StateGraph, done: str) -> None:
    """Add the agent, the ToolNode and end_round in a loop that leaves to `done`."""
    builder.add_node("agent", agent)
    builder.add_node("tools", tool_node())
    builder.add_node("end_round", end_round)
    builder.add_conditional_edges("agent", after_agent, {"tools": "tools", "finish": done})
    builder.add_edge("tools", "end_round")
    builder.add_conditional_edges("end_round", after_round, {"agent": "agent", "finish": done})


@cache
def chat_graph() -> CompiledStateGraph:
    """Return the compiled graph of one chat turn; the caller gets only its result."""
    builder = StateGraph(
        TurnState, context_schema=TurnContext, input_schema=TurnInput, output_schema=TurnOutput
    )
    builder.add_node("guard", guard_node)
    builder.add_node("prepare", prepare)
    builder.add_node("finish", finish)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", after_guard, ["prepare", END])
    builder.add_edge("prepare", "agent")
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
