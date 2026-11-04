"""The chat's short-term memory (T9.4, D12): one conversation per browser session, in memory only.

The conversation graph, `turn -> forget`, is compiled with an `InMemorySaver` and keeps one thread
of messages per `thread_id`. Its `turn` node runs the chat turn's own graph (`src/agent/graph.py`),
which is never checkpointed, on the thread's messages; when the turn is answered, the thread keeps
the question as the model got it (inside <user_input>) and the answer without its [S#] citations
(owner's choices, 2026-10-30). The turn's raw text, its tool calls and results and its <sources>
never reach the checkpointer, so a rejected message, a profile value and a chunk are not in memory.
`forget` deletes the oldest messages beyond `config.HISTORY_MAX_MESSAGES` with `RemoveMessage`,
cutting only before a question; the model sees at most `config.HISTORY_MAX_TOKENS` of them
(`chat.trim_history()`, in the turn's `prepare` node). The earlier checkpoints of the thread keep
removed messages until "New chat" deletes the thread (`Conversation.new_chat()`).

Each browser session holds its own `Conversation` in `st.session_state` (never `st.cache_resource`),
so sessions share nothing and a closed session's memory goes with it; nothing is written to disk.

A coach's turn may end with a proposed preference (T9.7): `turn -> approve -> forget`, where
`approve` pauses the graph with `interrupt()` before anything is written, carrying the text. The
coach's answer on the card resumes it with `Command(resume=...)` (`Conversation.decide()`): Save
checks the text again and writes it through the caller's `save`, Discard writes nothing. Either
way the state's proposal is then replaced with `config.ANSWERED_PROPOSAL`, so the thread's latest
state holds no proposed text; "New chat" deletes a pending one with the thread.
"""

import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src import chat, config
from src.chat import TurnResult
from src.preferences import PreferenceCheck

logger = logging.getLogger(__name__)

Choice = Literal["save", "discard"]


class ConversationState(TypedDict):
    """The thread: the answered turns' questions and answers, oldest first."""

    messages: Annotated[list[AnyMessage], add_messages]
    # The latest turn's proposed preference while it waits for the coach (T9.7), then
    # config.ANSWERED_PROPOSAL; None after a turn that proposed nothing.
    proposal: NotRequired[str | None]
    # True while the latest turn's proposal waits for the coach's answer (routes to `approve`).
    awaiting: NotRequired[bool]


@dataclass(frozen=True)
class ConversationContext:
    """What one turn of the conversation runs, and where its result goes (never into state)."""

    # Runs the chat turn's graph on the thread's messages and returns its output (TurnOutput).
    turn: Callable[[list[AnyMessage]], Mapping[str, Any]]
    # The turn's result: its tool runs hold tool results, so it stays out of the checkpointer.
    results: list[TurnResult] = field(default_factory=list)
    # An error the turn raised, raised again by Conversation.run() once the run is over.
    errors: list[Exception] = field(default_factory=list)
    # Saves a preference the coach approved (T9.7): checks it again and writes it to the store.
    save: Callable[[str], PreferenceCheck] | None = None
    # The outcome of the coach's answer: "saved", "discarded", "failed" or "refused.<code>".
    outcomes: list[str] = field(default_factory=list)


def turn(state: ConversationState, runtime: Runtime[ConversationContext]) -> dict[str, Any]:
    """Run the chat turn on the thread; keep its question and answer only if it was answered."""
    try:
        output = runtime.context.turn(list(state["messages"]))
    except GraphBubbleUp:
        # LangGraph's own signals (an interrupt() pause, T9.7) must reach the graph unchanged.
        raise
    except Exception as exc:
        # Not raised here: LangGraph would save the error as the task's pending write, with its
        # text, which may hold the question, a chunk or a server's reply (code review, round 1).
        # BaseException (Streamlit's rerun and stop) is not caught.
        runtime.context.errors.append(exc)
        return {"proposal": None, "awaiting": False}
    result: TurnResult = output["result"]
    runtime.context.results.append(result)
    # A proposal waits for the coach in `approve`, whatever the turn's answer (T9.7).
    proposal = output.get("proposal")
    update: dict[str, Any] = {"proposal": proposal, "awaiting": proposal is not None}
    if result.kind != "answer":
        # A rejected, redirected, failed or "not covered" turn leaves the thread as it was.
        return update
    messages = chat.exchange_messages(output["question"], result.text)
    # An answer that was only citations says nothing a later turn could use.
    return {**update, "messages": messages} if messages[1].text.strip() else update


def after_turn(state: ConversationState) -> str:
    """Pause for the coach's answer when the turn proposed a preference; else go on."""
    return "approve" if state.get("awaiting") else "forget"


def _outcome(answer: object, context: ConversationContext) -> str:
    """Carry out the coach's answer: save the (edited) text after checking it again, or not."""
    if not isinstance(answer, Mapping) or answer.get("choice") != "save" or context.save is None:
        # Discard, or anything that is not a clear Save: nothing is written.
        return "discarded"
    try:
        checked = context.save(answer.get("text"))
    except Exception as exc:
        # Kept out of the checkpoint, as in `turn`; Conversation.decide() raises it again.
        context.errors.append(exc)
        return "failed"
    return "saved" if checked.allowed else f"refused.{checked.code}"


def approve(state: ConversationState, runtime: Runtime[ConversationContext]) -> dict[str, Any]:
    """Pause with the proposed text until the coach answers; then save it or not (T9.7)."""
    # The node runs again from the start on resume, when interrupt() returns the coach's answer;
    # nothing is written before that.
    answer = interrupt({"text": state["proposal"]})
    runtime.context.outcomes.append(_outcome(answer, runtime.context))
    # The proposed text leaves the thread's latest state, whatever the answer.
    return {"proposal": config.ANSWERED_PROPOSAL, "awaiting": False}


def _no_turn(_: list[AnyMessage]) -> Mapping[str, Any]:
    """Stand for the turn while the graph resumes from `approve`, which never runs a turn."""
    raise RuntimeError("A resumed conversation runs no turn.")


def first_kept(messages: Sequence[AnyMessage], cap: int) -> int:
    """Return the place of the oldest message to keep: at most cap kept, starting on a question."""
    start = max(len(messages) - cap, 0)
    # Never cut between a question and its answer: an answer kept alone would be cut from what it
    # answers.
    while start < len(messages) and not isinstance(messages[start], HumanMessage):
        start += 1
    return start


def forget(state: ConversationState) -> dict[str, Any]:
    """Delete the thread's oldest messages beyond config.HISTORY_MAX_MESSAGES (what is stored)."""
    messages = state["messages"]
    old = messages[: first_kept(messages, config.HISTORY_MAX_MESSAGES)]
    return {"messages": [RemoveMessage(id=message.id) for message in old]} if old else {}


@cache
def conversation_builder() -> StateGraph:
    """Return the conversation graph's builder: turn, approve a proposal if any, then forget."""
    builder = StateGraph(ConversationState, context_schema=ConversationContext)
    builder.add_node("turn", turn)
    builder.add_node("approve", approve)
    builder.add_node("forget", forget)
    builder.add_edge(START, "turn")
    builder.add_conditional_edges("turn", after_turn, ["approve", "forget"])
    builder.add_edge("approve", "forget")
    builder.add_edge("forget", END)
    return builder


def mermaid() -> str:
    """Return the conversation graph as a Mermaid diagram, as docs/ARCHITECTURE.md shows it."""
    return conversation_builder().compile().get_graph().draw_mermaid()


class Conversation:
    """One browser session's chat memory: its own InMemorySaver, graph and thread_id."""

    def __init__(self) -> None:
        """Start an empty conversation with its own checkpointer and a new thread."""
        self.checkpointer = InMemorySaver()
        self.graph: CompiledStateGraph = conversation_builder().compile(
            checkpointer=self.checkpointer
        )
        self.thread_id = str(uuid.uuid4())

    def config(self) -> RunnableConfig:
        """Return the run config of the current thread."""
        return {"configurable": {"thread_id": self.thread_id}}

    def messages(self) -> list[AnyMessage]:
        """Return the current thread's messages, oldest first."""
        return list(self.graph.get_state(self.config()).values.get("messages", []))

    def pending(self) -> str | None:
        """Return the proposed preference waiting for the coach's answer, or None (T9.7)."""
        for paused in self.graph.get_state(self.config()).interrupts:
            if isinstance(paused.value, Mapping) and isinstance(paused.value.get("text"), str):
                return paused.value["text"]
        return None

    def decide(
        self,
        choice: Choice,
        text: str | None,
        save: Callable[[str], PreferenceCheck] | None,
        turn_id: str = "",
    ) -> str | None:
        """Resume the paused graph with the coach's answer; return its outcome, or None."""
        if self.pending() is None:
            return None
        context = ConversationContext(turn=_no_turn, save=save)
        self.graph.invoke(
            Command(resume={"choice": choice, "text": text}), self.config(), context=context
        )
        outcome = context.outcomes[0] if context.outcomes else None
        # The outcome's code only, never the text; the turn's ID when a turn discards it.
        logger.info("preference_decided", extra={"turn_id": turn_id or None, "code": outcome})
        if context.errors:
            raise context.errors[0]
        return outcome

    def run(
        self, run_turn: Callable[[list[AnyMessage]], Mapping[str, Any]], turn_id: str = ""
    ) -> TurnResult:
        """Run one turn on the current thread and return its result."""
        if self.pending() is not None:
            # The chat is locked while a proposal waits (views/chat.py); should a turn come all the
            # same, the proposal is discarded first, so nothing is saved without an answer.
            self.decide("discard", None, None, turn_id)
        context = ConversationContext(turn=run_turn)
        # LangGraph's default durability saves in the background, but the run waits for those
        # saves before invoke() returns, so the next turn sees this one. "sync" is not used: the
        # turn's graph inherits it and, having no checkpointer, fails on it (langgraph 1.2.17).
        self.graph.invoke({"messages": []}, self.config(), context=context)
        if context.errors:
            # run_turn() maps it to a fixed message, as for a turn without a conversation.
            raise context.errors[0]
        return context.results[0]

    def new_chat(self) -> None:
        """Delete the current thread from memory and start a new one ("New chat")."""
        # A pending proposal goes with the thread: it is discarded, never saved (T9.7).
        self.checkpointer.delete_thread(self.thread_id)
        self.thread_id = str(uuid.uuid4())
