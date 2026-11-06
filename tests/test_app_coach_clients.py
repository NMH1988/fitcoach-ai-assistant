"""UI tests for the coach assistant's client tools in the chat (T9.17, criterion 2).

A coach is signed in with one client; a scripted model lists the clients and answers by the
chat's reference. The page shows the client's display name in place of the reference, in the
answer and in the tool results, while the model and the conversation keep the reference.
"""

import pytest
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from src.store import db, users
from src.tools.coach_clients import LIST_TOOL
from tests.fakes import ScriptedChatModel, tool_reply
from tests.test_app_account import USER_ID, signed_in, start, store_account
from tests.test_app_chat import _use_model, fakes, index_path  # noqa: F401 (fixtures)
from views import chat as chat_view

pytestmark = pytest.mark.usefixtures("no_env_key")

CLIENT = "gym-client-t917"
# A display name with Markdown in it: shown as written, never as formatting or a link.
CLIENT_NAME = "Maxi_* www.example.com"
ANSWER = "client-1 logged no day this week."


def _coach(monkeypatch, language: str = "en") -> AppTest:
    """Sign in a stored coach with one client sharing nutrition; return the chat page."""
    store_account("coach", "Coach Sam")
    with db.connect() as conn:
        users.create_user(conn, CLIENT, "gymer", CLIENT_NAME)
        relationship = users.start_relationship(conn, USER_ID, CLIENT)
        users.set_consent(conn, CLIENT, relationship, "nutrition", True)
    return start(monkeypatch, user=signed_in(), language=language)


def _asked(monkeypatch) -> tuple[AppTest, ScriptedChatModel]:
    """Ask who logged too little; the model lists the clients and answers by reference."""
    at = _coach(monkeypatch)
    model = ScriptedChatModel(
        replies=[tool_reply((LIST_TOOL, {})), AIMessage(ANSWER)], search_first=False
    )
    _use_model(monkeypatch, model)
    at = at.chat_input(key="chat_input").set_value("Who logged fewer than 4 days?").run(timeout=30)
    return at, model


def _answer_markdown(at: AppTest) -> list[str]:
    """Return the Markdown blocks of the page that hold the answer's sentence."""
    return [item.value for item in at.markdown if "logged no day this week" in item.value]


def test_the_page_shows_the_client_s_name_in_place_of_the_reference(monkeypatch):
    """The answer shows the display name, escaped; the model's text keeps the reference."""
    at, model = _asked(monkeypatch)
    [shown] = _answer_markdown(at)
    assert "client-1" not in shown
    assert shown.startswith(r"Maxi\_\*")
    assert "www\u2060" in shown  # no link is made from the name (views/tables.one_line)
    [message] = [m for m in at.session_state["messages"] if m["role"] == "assistant"]
    assert message["result"].text == ANSWER
    for call in model.calls:
        assert all(CLIENT_NAME not in str(item.content) for item in call)


def test_the_tool_results_show_the_name(monkeypatch):
    """The client list under the answer names the client, as plain text in a table."""
    at, _ = _asked(monkeypatch)
    [table] = [frame.value for frame in at.dataframe if "Follow up" in frame.value.columns]
    assert list(table["Client"]) == [CLIENT_NAME]
    assert list(table["Days logged"]) == ["0 of 7 days logged"]


def test_the_name_still_shows_after_a_rerun(monkeypatch):
    """The references live in the session, so a past answer keeps the name on the next run."""
    at, _ = _asked(monkeypatch)
    at = at.run(timeout=30)
    [shown] = _answer_markdown(at)
    assert shown.startswith(r"Maxi\_\*")


def test_new_chat_forgets_the_references(monkeypatch):
    """ "New chat" clears the chat and its references."""
    at, _ = _asked(monkeypatch)
    assert at.session_state[chat_view.CLIENT_REFS_KEY][1].names() == {"client-1": CLIENT_NAME}
    at.button(key="new_chat").click().run(timeout=30)
    kept = (
        at.session_state[chat_view.CLIENT_REFS_KEY]
        if chat_view.CLIENT_REFS_KEY in at.session_state
        else None
    )
    assert kept is None or kept[1].names() == {}
