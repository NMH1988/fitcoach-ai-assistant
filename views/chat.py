"""The Ask tab: the chat history, the input and one chat turn with its progress (core 5)."""

import streamlit as st

# src.chat is imported as `turns`: this module is views.chat, and the name `chat` would hide it.
from src import chat as turns
from src import config, guard, usage
from views import resources, sources, tool_results, usage_view
from views.text import lang, t

ASSISTANT_AVATAR = ":material/nutrition:"


def status_label(result: turns.TurnResult) -> str:
    """Return the label a turn's status box ends with."""
    if result.kind == "answer" and not result.sources:
        return t("status.answer_uncited")
    return t(f"status.{result.kind}")


def final_state(result: turns.TurnResult) -> str:
    """Return the status state that ends a turn: error if rejected or failed, else complete."""
    # A guardrail redirect ends "complete": the app did what it should, nothing went wrong.
    return "error" if result.kind in ("rejected", "error") else "complete"


def step_label(step: turns.Step) -> str:
    """Return the name of a turn's step in the session's language."""
    return t(f"step.{step.name.lower()}")


def step_box(step: turns.Step, state: str):
    """Show one step of a turn with a line on what it does, and return its status box."""
    box = st.status(step_label(step), type="step", state=state)
    # A step without content ends Streamlit's timeline and hides the steps after it.
    box.caption(t(f"step.{step.name.lower()}.detail"))
    return box


def show_steps(result: turns.TurnResult) -> None:
    """Show the steps of a past turn as a collapsed status, as they ended."""
    state = final_state(result)
    with st.status(status_label(result), type="compact", state=state):
        for number, step in enumerate(result.steps, start=1):
            step_box(step, state if number == len(result.steps) else "complete")


def fixed_text(result: turns.TurnResult) -> str:
    """Return a turn's fixed message in the language chosen now, or the model's own answer."""
    # Past turns follow the language too; the answer stays in the language it was written in.
    return turns.fixed_text(result, lang())


def show_result(result: turns.TurnResult, turn: int) -> None:
    """Show a turn's answer with its sources and tool results, or its fixed message."""
    if result.kind == "rejected":
        st.warning(fixed_text(result), icon=":material/block:")
    elif result.kind == "guardrail":
        # A refusal or a pointer to a professional (AC-12), not an error.
        st.info(fixed_text(result), icon=":material/health_and_safety:")
    elif result.kind == "error":
        st.error(fixed_text(result), icon=":material/error:")
    else:
        # Model output as Markdown, never with unsafe_allow_html (docs/SECURITY.md).
        st.markdown(fixed_text(result))
        if result.sources:
            with st.expander(
                t("sources.count", count=len(result.sources)), icon=":material/menu_book:"
            ):
                for card in result.sources:
                    sources.card(card)
        if result.tool_runs:
            tool_results.show_tool_runs(result.tool_runs, turn)


def show_message(message: dict, turn: int) -> None:
    """Show one message of the chat history; `turn` is its place, for unique widget keys."""
    if message["role"] == "user":
        with st.chat_message("user"):
            # Plain text: the user's own words are shown as typed, not read as Markdown.
            st.text(message["text"])
        return
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        show_steps(message["result"])
        show_result(message["result"], turn)
        usage_view.caption(message.get("usage"))


def run_turn(question: str, turn: int) -> None:
    """Run one chat turn: steps in a status box, the answer as it streams in, then the result."""
    status = st.status(f":shimmer[{step_label(turns.Step.CHECK)}]", type="compact")
    # Below the status: the answer while it streams, replaced by the full result at the end.
    answer_slot = st.empty()
    # Under the answer: the turn's tokens and cost, once it is priced (T5.1).
    usage_slot = st.empty()
    boxes = []

    def on_step(step: turns.Step) -> None:
        """Close the previous step and show the one starting now (core 5, AC-10)."""
        if boxes:
            boxes[-1].update(state="complete")
        with status:
            boxes.append(step_box(step, "running"))
        status.update(label=f":shimmer[{step_label(step)}]")

    def show_text(text: str) -> None:
        """Show the answer so far, so the user reads it while the model is still writing."""
        # Model output as Markdown, never with unsafe_allow_html (docs/SECURITY.md).
        answer_slot.markdown(text)

    # The model sends its answer in fast bursts; reveal it at a steady, readable pace.
    on_text = turns.PacedWriter(show_text, config.ANSWER_WORDS_PER_SECOND)

    result = turns.run_turn(
        question,
        guard.session_limiter(st.session_state),
        open_index=resources.index,
        chat_model=resources.chat_model,
        translation_model=resources.translation_model,
        manifest=resources.manifest(),
        on_step=on_step,
        on_text=on_text,
        # The energy tools read the session's profile; the model cannot change it.
        user=st.session_state.get("profile"),
        keyword_index=resources.keyword_index,
        # The answer is written in the language chosen in the sidebar when the question is asked
        # (T7.2); the question's own language does not change it.
        language=lang(),
        # Only the prices already read, so the turn's log line never waits for the network.
        prices=usage.PRICES.peek,
        # The session's own memory: the turn sees this chat's earlier questions and answers (T9.4).
        conversation=st.session_state["conversation"],
    )
    if result.index_not_ready:
        # Open the index again on the next turn, e.g. once the owner has rebuilt it.
        resources.index.clear()
        resources.keyword_index.clear()
    state = final_state(result)
    if boxes:
        boxes[-1].update(state=state)
    status.update(label=status_label(result), state=state)
    with answer_slot.container():
        show_result(result, turn)
    # In the history before the price read: a click during that network call reruns the script,
    # which would otherwise drop the answer from the chat.
    message = {"role": "assistant", "result": result, "usage": None}
    st.session_state["messages"].append(message)
    # Priced once, after the answer is shown, when the turn ends: a rerun shows the stored cost
    # and makes no network call. Its own slot, as a slot drawn twice in one run keeps stale parts.
    message["usage"] = usage_view.price(result)
    with usage_slot.container():
        usage_view.caption(message["usage"])


def new_chat() -> None:
    """Forget the conversation and clear the chat, so the summary and the cost start again."""
    # The old thread is deleted from the session's checkpointer (T9.4, AC-31); the rate limit is
    # kept, so a new chat is no way around it.
    st.session_state["conversation"].new_chat()
    st.session_state["messages"].clear()


def tab() -> None:
    """Show the chat: the history, then the input; a new question runs one turn."""
    history = st.session_state["messages"]
    # Filled once, after a new question's turn, so the button is on as soon as the chat has one.
    button_slot = st.empty()
    box = st.container(height=config.CHAT_HEIGHT_PX)
    with box:
        invitation = st.empty()
        if not history:
            invitation.caption(t("ask.invitation"))
        for turn, message in enumerate(history):
            show_message(message, turn)
    question = st.chat_input(t("ask.placeholder"), key="chat_input")
    if question:
        invitation.empty()
        history.append({"role": "user", "text": question})
        with box:
            show_message(history[-1], len(history) - 1)
            with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                run_turn(question, len(history))
    button_slot.button(
        t("ask.new_chat"),
        key="new_chat",
        icon=":material/add_comment:",
        help=t("ask.new_chat_help"),
        on_click=new_chat,
        disabled=not history,
    )
