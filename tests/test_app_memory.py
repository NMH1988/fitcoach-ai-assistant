"""UI tests for the coach's long-term memory (T9.7, AC-36): the proposal card and My data.

A coach is signed in (tests/test_app_account.py's helpers) and asks in the chat; a scripted model
proposes a preference with remember_preference. The tests click Save, Edit and Discard and read
the store, the chat and the conversation's state.
"""

import pytest
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from src import account, i18n, preferences
from src.chat import TurnResult
from src.preferences import PREFERENCE_TOOL
from src.store import db, records, users
from tests.fakes import ScriptedChatModel, tool_reply
from tests.test_app_account import USER_ID, signed_in, start, store_account, texts
from tests.test_app_chat import _use_model, fakes, index_path  # noqa: F401 (fixtures)
from tests.test_app_my_data import open_my_data
from views import chat as chat_view

pytestmark = pytest.mark.usefixtures("no_env_key")

CLIENT = "gym-client-t97"
CLIENT_NAME = "Maxine"
CANARY = "CANARYPREF keep answers short"


def _coach(monkeypatch, language: str = "en") -> AppTest:
    """Sign in a stored coach with one client and return the app on the chat page."""
    store_account("coach", "Coach Sam")
    with db.connect() as conn:
        users.create_user(conn, CLIENT, "gymer", CLIENT_NAME)
        users.start_relationship(conn, USER_ID, CLIENT)
    return start(monkeypatch, user=signed_in(), language=language)


def _model(monkeypatch, *replies) -> ScriptedChatModel:
    """Make the app use a model scripted with these replies, with no search first."""
    return _use_model(monkeypatch, ScriptedChatModel(replies=list(replies), search_first=False))


def _proposing(text: str = CANARY) -> tuple:
    """Return the replies of a turn that only proposes the text: the call, then no basis."""
    return tool_reply((PREFERENCE_TOOL, {"text": text})), AIMessage("Noted.")


def _ask(at: AppTest, text: str = "From now on, please keep answers short.") -> AppTest:
    """Send a question through the chat input."""
    return at.chat_input(key="chat_input").set_value(text).run(timeout=30)


def _proposed(monkeypatch, language: str = "en", text: str = CANARY) -> AppTest:
    """Sign in a coach and have the model propose the text; return the app after the turn."""
    at = _coach(monkeypatch, language)
    _model(monkeypatch, *_proposing(text))
    return _ask(at)


def _saved() -> list[str]:
    """Return the coach's saved preferences' texts."""
    with db.connect() as conn:
        return [row["text"] for row in records.list_preferences(conn, USER_ID, USER_ID)]


def _keys(at: AppTest) -> set[str]:
    """Return the keys of the page's buttons."""
    return {item.key for item in at.button}


def _locked(at: AppTest) -> bool:
    """Return True if the chat input is disabled."""
    return at.chat_input(key="chat_input").proto.disabled


def _all_text(at: AppTest) -> str:
    """Return the page's texts with its info, success, warning and error boxes."""
    boxes = (str(item.value) for item in (*at.info, *at.success, *at.warning, *at.error))
    return "\n".join((texts(at), *boxes))


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_card_shows_the_text_the_note_and_three_choices(monkeypatch, language):
    """The card asks "Remember: ...?" with the note on client data, in both languages."""
    at = _proposed(monkeypatch, language)
    page = _all_text(at)
    assert i18n.t("memory.remember", language, text=CANARY) in page
    assert i18n.t("memory.note", language) in page
    assert {"memory_save", "memory_edit", "memory_discard"} <= _keys(at)
    labels = {item.key: item.label for item in at.button}
    assert labels["memory_save"] == i18n.t("memory.save", language)
    assert labels["memory_edit"] == i18n.t("memory.edit", language)
    assert labels["memory_discard"] == i18n.t("memory.discard", language)
    assert i18n.t("memory.proposed", language) in page
    assert i18n.t("memory.ask_again", language) in page
    assert _saved() == []


def test_the_chat_is_locked_while_the_proposal_waits(monkeypatch):
    """The chat input is off with a line saying why at once after the turn, with no other run."""
    at = _proposed(monkeypatch)
    assert _locked(at)
    assert i18n.t("memory.locked", "en") in _all_text(at)


def test_a_question_sent_to_the_locked_input_runs_no_turn(monkeypatch):
    """Streamlit drops what the locked input sends: no turn runs, the proposal keeps waiting."""
    at = _coach(monkeypatch)
    model = _model(monkeypatch, AIMessage("Hello again."))
    # A proposal waits while the input on the page is still open, as before the lock is drawn.
    result = TurnResult("memory", "x", code="memory.proposed")
    at.session_state["conversation"].run(lambda _h: {"result": result, "proposal": CANARY})
    _ask(at, "How much protein per meal?")
    assert model.calls == []
    assert at.session_state["conversation"].pending() == CANARY
    assert _locked(at) and {"memory_save", "memory_discard"} <= _keys(at)
    assert _saved() == []


def test_save_writes_the_text_and_says_so(monkeypatch):
    """Save writes the text, removes the card, unlocks the chat and shows the saved line."""
    at = _proposed(monkeypatch)
    at.button(key="memory_save").click().run(timeout=30)
    assert _saved() == [CANARY]
    assert "memory_save" not in _keys(at)
    assert not _locked(at)
    assert i18n.t("memory.saved", "en") in _all_text(at)
    assert at.session_state["conversation"].pending() is None


def test_discard_writes_nothing_and_says_so(monkeypatch):
    """Discard writes nothing and the chat says the preference was not saved."""
    at = _proposed(monkeypatch)
    at.button(key="memory_discard").click().run(timeout=30)
    assert _saved() == []
    assert "memory_discard" not in _keys(at)
    assert i18n.t("memory.discarded", "en") in _all_text(at)
    assert CANARY not in repr(
        at.session_state["conversation"].graph.get_state(at.session_state["conversation"].config())
    )


def test_edit_saves_the_edited_text(monkeypatch):
    """Edit opens the text; Save edited checks it and saves the edited text, not the proposal."""
    at = _proposed(monkeypatch)
    at.button(key="memory_edit").click().run(timeout=30)
    at.text_area(key=chat_view.EDIT_TEXT_KEY).set_value("answer in bullet points").run(timeout=30)
    at.button(key="memory_save_edited").click().run(timeout=30)
    assert _saved() == ["answer in bullet points"]
    assert i18n.t("memory.saved", "en") in _all_text(at)


def test_an_edit_that_adds_a_clients_name_is_refused_and_the_card_stays(monkeypatch):
    """An edited text with a client's name is not saved; the reason shows and the card waits."""
    at = _proposed(monkeypatch)
    at.button(key="memory_edit").click().run(timeout=30)
    at.text_area(key=chat_view.EDIT_TEXT_KEY).set_value(f"{CLIENT_NAME} wants short answers")
    at.button(key="memory_save_edited").click().run(timeout=30)
    assert _saved() == []
    # The card's reason comes without the turn's reminder to ask again.
    assert i18n.t("memory.refused.client_name", "en") in [w.value for w in at.warning]
    assert at.session_state["conversation"].pending() == CANARY
    assert _locked(at)


def test_cancel_closes_the_edit_and_keeps_the_proposal(monkeypatch):
    """Cancel goes back to Save, Edit and Discard with nothing written."""
    at = _proposed(monkeypatch)
    at.button(key="memory_edit").click().run(timeout=30)
    at.button(key="memory_cancel_edit").click().run(timeout=30)
    assert {"memory_save", "memory_edit", "memory_discard"} <= _keys(at)
    assert _saved() == []


def test_a_pending_proposal_survives_a_rerun(monkeypatch):
    """The card is read from the conversation, so reruns keep it until the coach answers."""
    at = _proposed(monkeypatch)
    for _ in range(2):
        at.run(timeout=30)
        assert {"memory_save", "memory_edit", "memory_discard"} <= _keys(at)
    assert _saved() == []


def test_new_chat_discards_the_proposal(monkeypatch):
    """ "New chat" removes the card and the chat; nothing is saved."""
    at = _proposed(monkeypatch)
    at.button(key="new_chat").click().run(timeout=30)
    assert "memory_save" not in _keys(at)
    assert at.session_state["conversation"].pending() is None
    assert not _locked(at)
    assert _saved() == []


def test_a_client_name_is_never_proposed(monkeypatch):
    """A proposal holding a client's name shows no card, only the line saying why."""
    at = _coach(monkeypatch)
    _model(monkeypatch, *_proposing(f"{CLIENT_NAME} eats late"))
    _ask(at)
    assert "memory_save" not in _keys(at)
    assert i18n.t("memory.refused.client_name", "en") in _all_text(at)
    assert i18n.t("memory.ask_again", "en") in _all_text(at)
    assert _saved() == []


def test_a_store_failure_at_save_writes_nothing_and_says_so(monkeypatch):
    """When the store fails at Save, the chat shows the fixed line and nothing is written."""
    at = _proposed(monkeypatch)

    def unavailable(*_args, **_kwargs):
        """Fail as a store that cannot be opened."""
        raise account.StoreUnavailable

    monkeypatch.setattr(preferences, "save", unavailable)
    at.button(key="memory_save").click().run(timeout=30)
    assert i18n.t("memory.failed", "en") in _all_text(at)
    assert at.session_state["conversation"].pending() is None
    assert _saved() == []


def test_saved_preferences_reach_the_next_turns_model(monkeypatch):
    """After Save, the next question's model call holds the preference inside <memories>."""
    at = _coach(monkeypatch)
    # One model for both turns: the app keeps its client in st.cache_resource.
    model = _model(monkeypatch, *_proposing(), *_proposing("bullet points"))
    _ask(at)
    at.button(key="memory_save").click().run(timeout=30)
    _ask(at, "And answer in bullet points please.")
    assert "<memories>" not in model.calls[0][-1].text
    assert f"<memories>\n- {CANARY}\n</memories>" in model.calls[2][-1].text


def test_a_guest_is_not_offered_the_tool(monkeypatch):
    """A guest's chat binds no remember_preference and shows no card."""
    at = start(monkeypatch, auth=False)
    model = _model(monkeypatch, AIMessage("Hello."))
    _ask(at, "How much protein per meal?")
    offered = {tool["function"]["name"] for tool in model.call_kwargs[0].get("tools") or ()}
    assert PREFERENCE_TOOL not in offered
    assert "memory_save" not in _keys(at)


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_coachs_notes_say_preferences_are_stored_and_sent(monkeypatch, language):
    """The sidebar note and the card say preferences are stored and go to OpenRouter."""
    at = _proposed(monkeypatch, language)
    page = _all_text(at)
    assert i18n.t("profile.note_coach", language) in page
    for key in ("profile.note_coach", "memory.note"):
        assert "OpenRouter" in i18n.t(key, language)
    assert "preferences" in i18n.t("profile.note_coach", "en")
    assert "Vorlieben" in i18n.t("profile.note_coach", "de")


# --- My data -------------------------------------------------------------------------------------


def test_a_coachs_my_data_lists_and_deletes_a_preference(monkeypatch):
    """The coach's My data lists their preferences and deletes one (AC-34)."""
    store_account("coach", "Coach Sam")
    with db.connect() as conn:
        records.add_preference(conn, USER_ID, "keep answers short")
        records.add_preference(conn, USER_ID, "answer in bullet points")
    at = open_my_data(start(monkeypatch, user=signed_in()))
    assert "keep answers short" in repr(at.dataframe[0].value)
    [picker] = [box for box in at.selectbox if box.key == "my_data_entry"]
    picker.set_value(("preferences", _first_id())).run(timeout=30)
    [delete] = [item for item in at.button if item.label == i18n.t("my_data.delete_entry", "en")]
    delete.click().run(timeout=30)
    assert _saved() == ["answer in bullet points"]


def _first_id() -> int:
    """Return the ID of the coach's oldest preference."""
    with db.connect() as conn:
        return records.list_preferences(conn, USER_ID, USER_ID)[0]["id"]


def test_a_gymers_my_data_has_no_preferences(monkeypatch):
    """A gymer keeps no preferences since T9.7, so their page lists none."""
    store_account("gymer", "Sam")
    at = open_my_data(start(monkeypatch, user=signed_in()))
    assert i18n.t("my_data.kind.preferences", "en") not in texts(at)
