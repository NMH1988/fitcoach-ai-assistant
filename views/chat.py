"""The Ask tab: the chat history, the input and one chat turn with its progress (core 5).

In a coach's chat (T9.7) a turn may end with a proposed preference: the conversation is paused
(`Conversation.pending()`), and a card under the answer offers Save, Edit and Discard with a note
that a preference must not hold a client's personal or health data. The chat input is locked
until the coach answers (the page reruns after the turn, so at once); the answer resumes the
conversation (`Conversation.decide()`), which checks the text again and writes it to the store
only on Save, and a fixed line in the chat says what happened. The card is read from the
conversation on every run, so it survives a rerun, and "New chat" discards it with the thread.

A coach's chat also reads the coach's clients (T9.17): the model names a client by the chat's
reference (`client-1`), kept in the session with the user ID and display name it stands for, and
this page shows the display name in its place, in the answer as it streams, in the answer and in
the tool results; the conversation's memory keeps the reference. "New chat" forgets them.
"""

import streamlit as st

from src import account as accounts

# src.chat is imported as `turns`: this module is views.chat, and the name `chat` would hide it.
from src import chat as turns
from src import config, guard, preferences, usage
from src.store.access import NotFound
from src.tools import coach_clients
from src.tools import food_api as fdc
from views import account, resources, sources, tables, tool_results, usage_view
from views.text import lang, t

ASSISTANT_AVATAR = ":material/nutrition:"
# The proposal card's session keys (T9.7): Edit is open, the edited text, why an edit was refused.
EDITING_KEY = "memory_editing"
EDIT_TEXT_KEY = "memory_edit_text"
EDIT_REFUSED_KEY = "memory_edit_refused"
# The coach's client references for this chat (T9.17), with the coach they belong to.
CLIENT_REFS_KEY = "client_refs"


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
    text = turns.fixed_text(result, lang())
    return with_client_names(text) if result.kind == "answer" else text


def client_refs() -> coach_clients.ClientRefs | None:
    """Return the session coach's client references for this chat; None for anyone else."""
    user_id = coach_id()
    if user_id is None:
        return None
    kept = st.session_state.get(CLIENT_REFS_KEY)
    if kept is None or kept[0] != user_id:
        # Another user in this session (clear_session() drops them too): start again.
        kept = (user_id, coach_clients.ClientRefs())
        st.session_state[CLIENT_REFS_KEY] = kept
    return kept[1]


def with_client_names(text: str) -> str:
    """Return the model's text with each client reference shown as the client's display name."""
    refs = client_refs()
    if refs is None:
        return text
    # A display name is a user's own text: shown as written, never as Markdown or a link.
    return coach_clients.name_references(text, refs.names(), tables.one_line)


def coach_clients_for_turn() -> coach_clients.CoachClients | None:
    """Return what a coach's client tools need for one turn; None for anyone else (T9.17)."""
    user_id = coach_id()
    refs = client_refs()
    if user_id is None or refs is None:
        return None
    path = account.store_path()
    return coach_clients.CoachClients(
        coach_id=user_id,
        open_store=lambda: accounts.open_store(path),
        refs=refs,
        today=accounts.today,
    )


def show_result(result: turns.TurnResult, turn: int) -> None:
    """Show a turn's answer with its sources and tool results, or its fixed message."""
    if result.kind == "rejected":
        st.warning(fixed_text(result), icon=":material/block:")
    elif result.kind == "guardrail":
        # A refusal or a pointer to a professional (AC-12), not an error.
        st.info(fixed_text(result), icon=":material/health_and_safety:")
    elif result.kind == "error":
        st.error(fixed_text(result), icon=":material/error:")
    elif result.kind == "memory":
        # A coach's turn that only proposed a preference, or said why it could not (T9.7).
        st.info(fixed_text(result), icon=":material/bookmark:")
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
            refs = client_refs()
            names = refs.names() if refs is not None else None
            tool_results.show_tool_runs(result.tool_runs, turn, names)


def show_note(code: str) -> None:
    """Show the fixed line that follows the coach's answer to a proposal, in the language now."""
    if code == "memory.saved":
        st.success(t(code), icon=":material/bookmark_added:")
    elif code == "memory.failed":
        st.error(t(code), icon=":material/error:")
    else:
        st.info(t(code), icon=":material/bookmark_remove:")


def show_message(message: dict, turn: int) -> None:
    """Show one message of the chat history; `turn` is its place, for unique widget keys."""
    if message["role"] == "note":
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            show_note(message["code"])
        return
    if message["role"] == "user":
        with st.chat_message("user"):
            # Plain text: the user's own words are shown as typed, not read as Markdown.
            st.text(message["text"])
        return
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        show_steps(message["result"])
        show_result(message["result"], turn)
        usage_view.caption(message.get("usage"))


def coach_id() -> str | None:
    """Return the session's user ID if they are a coach (the only role with long-term memory)."""
    user = account.current_user()
    return user["id"] if user is not None and user["role"] == "coach" else None


def coach_memory() -> preferences.CoachMemory | None:
    """Read a coach's client names and saved preferences for one turn; None for anyone else."""
    user_id = coach_id()
    if user_id is None:
        return None
    try:
        with accounts.open_store(account.store_path()) as conn:
            return preferences.load(conn, user_id)
    except accounts.StoreUnavailable, NotFound:
        # The turn runs without the tool and <memories>; nothing is proposed without the names.
        return None


def _save(text: str) -> preferences.PreferenceCheck:
    """Check a preference against the coach's clients again and save it for the coach."""
    user_id = coach_id()
    if user_id is None:
        raise NotFound
    with accounts.open_store(account.store_path()) as conn:
        return preferences.save(conn, user_id, text)


def _note(code: str) -> None:
    """Add the fixed line about the coach's answer to the chat history."""
    st.session_state["messages"].append({"role": "note", "code": code})


def _open_edit() -> None:
    """Open the card's Edit field."""
    st.session_state[EDITING_KEY] = True


def _close_edit() -> None:
    """Close the card's Edit field and forget its text and refusal."""
    for key in (EDITING_KEY, EDIT_TEXT_KEY, EDIT_REFUSED_KEY):
        st.session_state.pop(key, None)


def decide(choice: str, text: str | None) -> None:
    """Resume the conversation with the coach's answer and add the line that says what happened."""
    _close_edit()
    try:
        outcome = st.session_state["conversation"].decide(choice, text, _save)
    except accounts.StoreUnavailable, NotFound:
        # The proposal is answered and nothing was written (the store is down, or the account
        # was deleted in another tab).
        _note("memory.failed")
        return
    if outcome is not None:
        _note(f"memory.{outcome}")


def save_proposal(text: str) -> None:
    """Save the proposed text as it was shown."""
    decide("save", text)


def save_edited() -> None:
    """Check the edited text before resuming; a refused edit keeps the card with the reason."""
    text = st.session_state.get(EDIT_TEXT_KEY)
    memory = coach_memory()
    names = memory.client_names if memory is not None else ()
    checked = preferences.check_preference(text, names)
    if not checked.allowed:
        st.session_state[EDIT_REFUSED_KEY] = checked.code
        return
    # Checked again at the save, against the names read then (src/agent/memory.py).
    decide("save", checked.text)


def discard_proposal() -> None:
    """Discard the proposal: nothing is written."""
    decide("discard", None)


def proposal_card(text: str) -> None:
    """Show the proposed preference with Save, Edit and Discard and the note on what it may hold."""
    with st.container(border=True, key="memory_card"):
        # The text is the model's: shown as written, never read as Markdown (docs/SECURITY.md).
        st.markdown(t("memory.remember", text=turns.escape_markdown(text)))
        st.caption(t("memory.note"))
        if st.session_state.get(EDITING_KEY):
            st.text_area(
                t("memory.edit_label"),
                value=text,
                max_chars=config.PREFERENCE_MAX_CHARS,
                key=EDIT_TEXT_KEY,
            )
            refused = st.session_state.get(EDIT_REFUSED_KEY)
            if refused is not None:
                st.warning(t(f"memory.refused.{refused}"), icon=":material/block:")
            save, cancel = st.columns(2)
            save.button(
                t("memory.save_edited"),
                key="memory_save_edited",
                icon=":material/bookmark_added:",
                type="primary",
                on_click=save_edited,
            )
            cancel.button(t("memory.cancel_edit"), key="memory_cancel_edit", on_click=_close_edit)
            return
        save, edit, discard = st.columns(3)
        save.button(
            t("memory.save"),
            key="memory_save",
            icon=":material/bookmark_added:",
            type="primary",
            on_click=save_proposal,
            args=(text,),
        )
        edit.button(
            t("memory.edit"),
            key="memory_edit",
            icon=":material/edit:",
            on_click=_open_edit,
        )
        discard.button(
            t("memory.discard"),
            key="memory_discard",
            icon=":material/bookmark_remove:",
            on_click=discard_proposal,
        )


def pending_proposal() -> str | None:
    """Return the proposal waiting for the session's coach, or None."""
    if coach_id() is None:
        return None
    return st.session_state["conversation"].pending()


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
        # Model output as Markdown, never with unsafe_allow_html (docs/SECURITY.md); a client's
        # reference shows as their name (T9.17).
        answer_slot.markdown(with_client_names(text))

    # The model sends its answer in fast bursts; reveal it at a steady, readable pace.
    on_text = turns.PacedWriter(show_text, config.ANSWER_WORDS_PER_SECOND)
    memory = coach_memory()

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
        # A coach's client names and saved preferences (T9.7); None for a guest.
        coach=memory,
        # The USDA FoodData Central API for foods the table lacks (T9.9); None without the key.
        # Read each turn, so a key added to the secrets works without a restart.
        food_api=fdc.build_food_api(),
        # A coach's client tools and this chat's references (T9.17); None for a guest. Offered
        # only with the coach's part of the prompt, which explains them: when the store fails and
        # the coach's memory cannot be read, the turn has neither (code review round 7).
        clients=coach_clients_for_turn() if memory is not None else None,
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
    # A pending proposal went with the thread (T9.7), and its Edit field goes with it.
    _close_edit()
    # The client references go with the chat (T9.17): the next chat lists the clients again.
    st.session_state.pop(CLIENT_REFS_KEY, None)


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
    pending = pending_proposal()
    if pending is not None:
        # Locked until the coach answers the proposal (T9.7). Streamlit ignores what a disabled
        # widget sends, so no question reaches a paused conversation from here (should one come
        # all the same, Conversation.run() discards the proposal first).
        st.caption(t("memory.locked"))
    question = st.chat_input(t("ask.placeholder"), key="chat_input", disabled=pending is not None)
    if question:
        invitation.empty()
        history.append({"role": "user", "text": question})
        with box:
            show_message(history[-1], len(history) - 1)
            with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                run_turn(question, len(history))
        if pending_proposal() is not None:
            # Drawn again at once, so the chat input is locked while the card waits (the turn's
            # result and its cost are in the history already, and the input was drawn before it).
            st.rerun()
    if pending is not None:
        # Under the last message: the answer of the turn that proposed it.
        with box, st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            proposal_card(pending)
    button_slot.button(
        t("ask.new_chat"),
        key="new_chat",
        icon=":material/add_comment:",
        help=t("ask.new_chat_help"),
        on_click=new_chat,
        disabled=not history,
    )
