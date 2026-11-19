"""The answer step: one streamed reply, and the answer loop with its tools."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool

from src import llm
from src.chat.markdown import remove_images
from src.chat.results import Step
from src.tools.registry import ToolRun
from src.usage import UsageRecorder


def stream_reply(
    chat_model: Runnable[Any, BaseMessage],
    messages: Sequence[BaseMessage],
    on_text: Callable[[str], None] | None = None,
    record: Callable[[UsageMetadata | None], None] | None = None,
) -> AIMessageChunk:
    """Stream one model reply, reporting its text so far as it grows; return the whole reply."""
    # record(usage) gets the reply's token use, which comes with the last chunk (T5.1).
    reply: AIMessageChunk | None = None
    with llm.mapped_errors():
        for chunk in chat_model.stream(messages):
            reply = chunk if reply is None else reply + chunk
            if on_text is not None and chunk.text:
                # Images are removed on every update: one completed mid-stream would load at once.
                on_text(remove_images(reply.text))
    if reply is None:
        raise llm.LLMError(diagnostic="no answer chunks")
    if record is not None:
        # Before the check below: a cut-off reply was paid for too.
        record(reply.usage_metadata)
    if reply.response_metadata.get("finish_reason") == "length":
        # A cut-off answer is not shown half-written, and cut-off tool arguments are not run.
        raise llm.ReplyCutOffError(diagnostic="finish_reason length in the answer step")
    return reply


def answer_with_tools(
    chat_model: BaseChatModel,
    messages: Sequence[BaseMessage],
    tools: Mapping[str, StructuredTool],
    on_step: Callable[[Step], None],
    on_text: Callable[[str], None] | None = None,
    *,
    tools_only: bool = False,
    recorder: UsageRecorder | None = None,
    on_tool_run: Callable[[ToolRun], None] | None = None,
) -> tuple[str | None, tuple[ToolRun, ...]]:
    """Let the model call tools for at most MAX_TOOL_ROUNDS rounds; return its answer and runs."""
    # The chat graph's own answer loop (its agent and ToolNode), run on the given messages; a
    # turn runs it inside the whole graph (src/agent/graph.py). tools_only: replies stay hidden
    # until a tool gives a result (config.BASIS_TOOL_STATUSES), and an answer of None means "not
    # covered", returned with no runs (a whole turn keeps them with "not covered"). The messages
    # must come from a guarded turn: this loop has no guard of its own. on_tool_run gets a valid
    # call's run from the ToolNode's worker thread and a refused bad-JSON call's from the caller's.
    from src.agent import graph  # The graph builds its nodes from this package's helpers.

    context = graph.TurnContext(
        chat_model=lambda: chat_model,
        tools=lambda: tools,
        on_step=on_step,
        on_text=on_text,
        recorder=recorder,
        on_tool_run=on_tool_run,
    )
    state = graph.answer_loop_graph().invoke(
        {"messages": list(messages), "tools_only": tools_only},
        context=context,
        config=graph.run_config(),
    )
    if state["answer"] is None:
        return None, ()
    return state["answer"], tuple(state.get("runs", ()))
