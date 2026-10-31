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
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from src import chat, config
from src.chat import TurnResult


class ConversationState(TypedDict):
    """The thread: the answered turns' questions and answers, oldest first."""

    messages: Annotated[list[AnyMessage], add_messages]


@dataclass(frozen=True)
class ConversationContext:
    """What one turn of the conversation runs, and where its result goes (never into state)."""

    # Runs the chat turn's graph on the thread's messages and returns its output (TurnOutput).
    turn: Callable[[list[AnyMessage]], Mapping[str, Any]]
    # The turn's result: its tool runs hold tool results, so it stays out of the checkpointer.
    results: list[TurnResult] = field(default_factory=list)
    # An error the turn raised, raised again by Conversation.run() once the run is over.
    errors: list[Exception] = field(default_factory=list)


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
        return {}
    result: TurnResult = output["result"]
    runtime.context.results.append(result)
    if result.kind != "answer":
        # A rejected, redirected, failed or "not covered" turn leaves the thread as it was.
        return {}
    messages = chat.exchange_messages(output["question"], result.text)
    # An answer that was only citations says nothing a later turn could use.
    return {"messages": messages} if messages[1].text.strip() else {}


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
    """Return the conversation graph's builder: turn, then forget."""
    builder = StateGraph(ConversationState, context_schema=ConversationContext)
    builder.add_node("turn", turn)
    builder.add_node("forget", forget)
    builder.add_edge(START, "turn")
    builder.add_edge("turn", "forget")
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

    def run(self, run_turn: Callable[[list[AnyMessage]], Mapping[str, Any]]) -> TurnResult:
        """Run one turn on the current thread and return its result."""
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
        # T9.7 discards a pending proposal here too.
        self.checkpointer.delete_thread(self.thread_id)
        self.thread_id = str(uuid.uuid4())
