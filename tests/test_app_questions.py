"""UI tests for the questions to the coach under an approved review (T9.25, AC-41, AC-42).

The gymer asks on My week, the coach answers on Client week; the store decides every write by the
review's own rule, and the pages show one fixed message, naming no scope, when it refuses.
"""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from src import account as accounts
from src import config, i18n, metrics
from src.store import db, questions, reviews, users
from tests.test_app_account import PROFILE, USER_ID, signed_in, start, store_account
from tests.test_app_sharing import open_page, page_text
from views import client_week, navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

TODAY = date(2026, 11, 5)
TRAINED_WEEK = date(2026, 10, 19)  # its review used nutrition and training
PLAIN_WEEK = date(2026, 10, 12)  # its review used nutrition only
COACH = "coach-kai"
CLIENT = "gym-alex"
OTHER = "gym-bo"
# Markdown, HTML and a link: shown as typed, never read as any of them.
RAW = "**Bold** <b>tag</b> [link](https://example.com) # heading"
QUESTION = "Why fewer carbs on rest days?"
ANSWER = "Rest days need less fuel, so the target is lower."
CLOSED = "Questions can no longer be asked or answered under this review."
CLOSED_DE = "Unter diesem Wochenbericht können keine Fragen mehr gestellt oder beantwortet werden."


@pytest.fixture(autouse=True)
def today(monkeypatch):
    """Fix today in Berlin, so both weeks are over."""
    monkeypatch.setattr(metrics, "berlin_day", lambda moment=None: TODAY)


def _review(conn, coach, client, monday, scopes=("nutrition",)) -> int:
    """Save a made-up review that used the scopes and approve it; return its ID."""
    found = reviews.save_review(
        conn,
        coach,
        client,
        period_start=monday,
        metrics={"logged_days": 3},
        data_quality={},
        draft={"observations": [f"Draft of {monday.isoformat()}."]},
        model_version="test-model",
        scopes=scopes,
    )
    reviews.decide_review(conn, coach, found, "approve")
    return found


def _pair(conn, coach, client, scopes) -> int:
    """Start a relationship with the scopes on; return its ID."""
    found = users.start_relationship(conn, coach, client)
    for scope in scopes:
        users.set_consent(conn, client, found, scope, True)
    return found


def _rows() -> list[dict]:
    """Return every stored thread row, oldest first."""
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM review_questions ORDER BY id")]


def _plain_texts(at: AppTest) -> list[str]:
    """Return the values of the page's st.text elements."""
    return [item.value for item in at.text]


def _ask(at: AppTest, review_id: int, text: str) -> AppTest:
    """Type a question under a review and send it."""
    at.text_area(key=f"questions_ask_text_{review_id}").input(text)
    [send] = [item for item in at.button if item.proto.form_id == f"questions_ask_{review_id}"]
    send.click()
    return at.run(timeout=30)


def _answer(at: AppTest, review_id: int, text: str) -> AppTest:
    """Type an answer under a review and send it."""
    at.text_area(key=f"questions_answer_text_{review_id}").input(text)
    [send] = [item for item in at.button if item.proto.form_id == f"questions_answer_{review_id}"]
    send.click()
    return at.run(timeout=30)


# --- The gymer on My week ------------------------------------------------------------------------


@pytest.fixture
def gymer_world() -> dict:
    """Store the canary gymer with coach Kai (nutrition, training) and two approved reviews."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = _pair(conn, COACH, USER_ID, ("nutrition", "training"))
        trained = _review(conn, COACH, USER_ID, TRAINED_WEEK, ("nutrition", "training"))
        plain = _review(conn, COACH, USER_ID, PLAIN_WEEK)
    return {"relationship": relationship, "trained": trained, "plain": plain}


def _my_week(monkeypatch, language="en") -> AppTest:
    """Open My week as the canary gymer."""
    return open_page(start(monkeypatch, user=signed_in(), language=language), navigation.MY_WEEK)


def test_the_gymer_asks_and_the_question_shows_as_plain_text(monkeypatch, gymer_world):
    """The question is stored and shown as typed, never as Markdown, HTML or a link."""
    at = _ask(_my_week(monkeypatch), gymer_world["trained"], RAW)
    [row] = _rows()
    assert (row["review_id"], row["author_id"], row["kind"], row["text"]) == (
        gymer_world["trained"],
        USER_ID,
        "question",
        RAW,
    )
    assert RAW in _plain_texts(at)
    assert all("example.com" not in str(item.value) for item in at.markdown)
    page = page_text(at)
    assert "Your question was sent." in page
    assert "Your question is waiting for the coach's answer." in page
    assert not [item for item in at.text_area if item.key.endswith(str(gymer_world["trained"]))]


@pytest.mark.parametrize(
    ("language", "note", "stored", "label", "ai_label"),
    [
        (
            "en",
            "the app does not check coaches' qualifications",
            "until you delete everything on My data. Use made-up data only",
            "Written by the coach, not by AI",
            "AI draft, approved by the coach",
        ),
        (
            "de",
            "die App prüft die Qualifikationen von Coaches nicht",
            "bis Sie unter Meine Daten alles löschen. Verwenden Sie nur erfundene Daten",
            "Vom Coach geschrieben, nicht von der KI",
            "KI-Entwurf",
        ),
    ],
)
def test_the_note_and_the_coach_s_label_in_both_languages(
    monkeypatch, gymer_world, language, note, stored, label, ai_label
):
    """Beside the box: no medical advice, coach not checked, 112, stored, made-up data only."""
    with db.connect() as conn:
        questions.ask_question(conn, USER_ID, gymer_world["plain"], QUESTION)
        questions.answer_question(conn, COACH, gymer_world["plain"], ANSWER)
    at = _my_week(monkeypatch, language)
    page = page_text(at)
    assert note in page and "112" in page
    # Where the question is kept, until when, and made-up data only (compliance run 1, Low).
    assert stored in page
    assert label in page
    assert ai_label in page
    assert [QUESTION, ANSWER] == [text for text in _plain_texts(at) if text in (QUESTION, ANSWER)]


def test_a_guardrail_question_is_refused_and_nothing_is_stored(monkeypatch, gymer_world):
    """A question about pain gets the guard's fixed message; no row is written."""
    at = _ask(_my_week(monkeypatch), gymer_world["trained"], "My knee hurts when I squat, why?")
    page = page_text(at)
    assert "This question was not sent." in page
    assert "Please see a doctor or a physiotherapist." in page
    assert "112" in page
    assert _rows() == []


def test_an_empty_question_is_refused(monkeypatch, gymer_world):
    """Blank text writes nothing and says so."""
    at = _ask(_my_week(monkeypatch), gymer_world["trained"], "   ")
    assert "Please type some text first." in page_text(at)
    assert _rows() == []


@pytest.mark.parametrize("case", ["ended", "nutrition", "training"])
def test_the_fixed_message_replaces_the_box(monkeypatch, gymer_world, case):
    """An ended relationship, or nutrition or a used scope off: one message, naming no scope."""
    with db.connect() as conn:
        if case == "ended":
            users.end_relationship(conn, USER_ID, gymer_world["relationship"])
        else:
            users.set_consent(conn, USER_ID, gymer_world["relationship"], case, False)
    at = _my_week(monkeypatch)
    keys = {item.key for item in at.text_area}
    assert f"questions_ask_text_{gymer_world['trained']}" not in keys
    assert CLOSED in page_text(at)
    # Training off leaves the review that used nutrition only open.
    assert (f"questions_ask_text_{gymer_world['plain']}" in keys) == (case == "training")


@pytest.mark.parametrize("language", ["en", "de"])
def test_the_fixed_message_names_no_scope(language):
    """The one message for every refusal names none of the scopes, in either language."""
    text = i18n.t("questions.closed", language).casefold()
    for scope in ("nutrition", "training", "body", "ernährung", "körper", "freigabe"):
        assert scope not in text


@pytest.mark.parametrize("case", ["ended", "nutrition", "training"])
def test_a_question_refused_after_the_page_was_drawn(monkeypatch, gymer_world, case):
    """The coach ends it, or a scope goes off, in between: nothing written, the same message."""
    at = _my_week(monkeypatch)
    with db.connect() as conn:
        if case == "ended":
            users.end_relationship(conn, COACH, gymer_world["relationship"])
        else:
            users.set_consent(conn, USER_ID, gymer_world["relationship"], case, False)
    at = _ask(at, gymer_world["trained"], QUESTION)
    assert _rows() == []
    assert not at.exception
    assert CLOSED in page_text(at)


def test_the_thread_stays_readable_after_the_end(monkeypatch, gymer_world):
    """Once the relationship ends, the gymer still reads the question and the answer."""
    with db.connect() as conn:
        questions.ask_question(conn, USER_ID, gymer_world["plain"], QUESTION)
        questions.answer_question(conn, COACH, gymer_world["plain"], ANSWER)
        users.end_relationship(conn, USER_ID, gymer_world["relationship"])
    at = _my_week(monkeypatch)
    assert QUESTION in _plain_texts(at) and ANSWER in _plain_texts(at)
    assert CLOSED in page_text(at)


def test_the_most_questions_a_review_takes(monkeypatch, gymer_world):
    """After the last answered question, the box gives way to a line saying so."""
    with db.connect() as conn:
        for _ in range(config.REVIEW_THREAD_MAX_QUESTIONS):
            questions.ask_question(conn, USER_ID, gymer_world["plain"], QUESTION)
            questions.answer_question(conn, COACH, gymer_world["plain"], ANSWER)
    at = _my_week(monkeypatch)
    expected = f"You have asked {config.REVIEW_THREAD_MAX_QUESTIONS} questions under this review"
    assert expected in page_text(at)
    assert f"questions_ask_text_{gymer_world['plain']}" not in {item.key for item in at.text_area}


def test_a_gymer_never_sees_another_gymer_s_thread(monkeypatch, gymer_world):
    """A second gymer's question under their own review is not on the canary gymer's page."""
    with db.connect() as conn:
        users.create_user(conn, OTHER, "gymer", "Bo")
        coach_b = "coach-b"
        users.create_user(conn, coach_b, "coach", "Coach B")
        _pair(conn, coach_b, OTHER, ("nutrition",))
        other_review = _review(conn, coach_b, OTHER, PLAIN_WEEK)
        questions.ask_question(conn, OTHER, other_review, "CANARY-OTHER question")
    at = _my_week(monkeypatch)
    assert "CANARY-OTHER question" not in "\n".join((page_text(at), *_plain_texts(at)))


def test_the_gymer_page_in_german(monkeypatch, gymer_world):
    """The heading, the box and the fixed message are in German."""
    at = _my_week(monkeypatch, "de")
    page = page_text(at)
    assert "Fragen an den Coach" in page
    assert "Ihre Frage an den Coach" in [item.label for item in at.text_area]
    with db.connect() as conn:
        users.end_relationship(conn, USER_ID, gymer_world["relationship"])
    at = _my_week(monkeypatch, "de")
    assert CLOSED_DE in page_text(at)


# --- The coach on Client week --------------------------------------------------------------------


@pytest.fixture
def coach_world() -> dict:
    """Store the canary coach with Alex (every scope), two approved reviews and Alex's question."""
    store_account("coach", name="Coach Sam")
    with db.connect() as conn:
        users.create_user(conn, CLIENT, "gymer", "Alex")
        relationship = _pair(conn, USER_ID, CLIENT, ("nutrition", "training", "body"))
        trained = _review(conn, USER_ID, CLIENT, TRAINED_WEEK, ("nutrition", "training"))
        plain = _review(conn, USER_ID, CLIENT, PLAIN_WEEK)
        questions.ask_question(conn, CLIENT, trained, RAW)
    return {"relationship": relationship, "trained": trained, "plain": plain}


def _client_week(monkeypatch, monday=TRAINED_WEEK, language="en") -> AppTest:
    """Open Alex's week on Client week as the canary coach."""
    at = open_page(start(monkeypatch, user=signed_in(), language=language), navigation.CLIENT_WEEK)
    at.selectbox(key=client_week.PICK_KEY).set_value(CLIENT).run(timeout=30)
    at.date_input(key=client_week.WEEK_KEY).set_value(monday).run(timeout=30)
    return at


def test_the_coach_reads_the_question_as_plain_text_and_answers(monkeypatch, coach_world):
    """The question shows as typed; the answer is stored and audited without its text."""
    at = _client_week(monkeypatch)
    assert RAW in _plain_texts(at)
    assert all("example.com" not in str(item.value) for item in at.markdown)
    assert "The client's question" in page_text(at)
    at = _answer(at, coach_world["trained"], ANSWER)
    assert [row["kind"] for row in _rows()] == ["question", "answer"]
    assert "Your answer was sent." in page_text(at)
    assert ANSWER in _plain_texts(at)
    with db.connect() as conn:
        actions = [
            (row["action"], row["resource_type"])
            for row in conn.execute("SELECT action, resource_type FROM audit_log")
        ]
    assert ("review_answered", "review_questions") in actions
    assert ("read", "review_questions") in actions


def test_the_coach_is_told_which_weeks_wait_for_an_answer(monkeypatch, coach_world):
    """On another week, a line names the week whose question waits."""
    at = _client_week(monkeypatch, monday=PLAIN_WEEK)
    assert "weeks of 2026-10-19" in page_text(at)
    assert "The client has not asked a question under this review." in page_text(at)


@pytest.mark.parametrize("scope", ["nutrition", "training"])
def test_a_client_who_turned_a_used_scope_off_hides_the_thread(monkeypatch, coach_world, scope):
    """Nutrition off, or training off under a review that used it: the thread is not shown."""
    with db.connect() as conn:
        users.set_consent(conn, CLIENT, coach_world["relationship"], scope, False)
    at = _client_week(monkeypatch)
    assert RAW not in _plain_texts(at)
    assert not [item for item in at.text_area if item.key.startswith("questions_answer_")]


@pytest.mark.parametrize("case", ["ended", "nutrition", "training"])
def test_an_answer_refused_while_the_page_is_open(monkeypatch, coach_world, case):
    """Ended, or nutrition or a used scope off, in between: nothing written, the fixed message."""
    at = _client_week(monkeypatch)
    with db.connect() as conn:
        if case == "ended":
            users.end_relationship(conn, CLIENT, coach_world["relationship"])
        else:
            users.set_consent(conn, CLIENT, coach_world["relationship"], case, False)
    at = _answer(at, coach_world["trained"], ANSWER)
    assert [row["kind"] for row in _rows()] == ["question"]
    assert not at.exception
    assert CLOSED in page_text(at)


def test_the_coach_page_in_german(monkeypatch, coach_world):
    """The heading, the label and the answer box are in German."""
    at = _client_week(monkeypatch, language="de")
    page = page_text(at)
    assert "Fragen an den Coach" in page and "Frage Ihres Klienten" in page
    assert "Ihre Antwort" in [item.label for item in at.text_area]


# --- The other ways a send can fail (code review round 1) ---------------------------------------


def test_a_question_asked_in_another_tab_meanwhile_shows_the_waiting_line(monkeypatch, gymer_world):
    """A second question while one waits: nothing written, one line says the thread waits."""
    at = _my_week(monkeypatch)
    with db.connect() as conn:
        questions.ask_question(conn, USER_ID, gymer_world["plain"], QUESTION)
    at = _ask(at, gymer_world["plain"], "A second question")
    assert [row["text"] for row in _rows()] == [QUESTION]
    assert page_text(at).count("Your question is waiting for the coach's answer.") == 1
    assert not at.exception


def test_the_last_question_asked_in_another_tab_shows_the_used_up_line(monkeypatch, gymer_world):
    """The thread used up in between: nothing written, no contradicting line."""
    with db.connect() as conn:
        for _ in range(config.REVIEW_THREAD_MAX_QUESTIONS - 1):
            questions.ask_question(conn, USER_ID, gymer_world["plain"], QUESTION)
            questions.answer_question(conn, COACH, gymer_world["plain"], ANSWER)
    at = _my_week(monkeypatch)
    with db.connect() as conn:
        questions.ask_question(conn, USER_ID, gymer_world["plain"], QUESTION)
        questions.answer_question(conn, COACH, gymer_world["plain"], ANSWER)
    at = _ask(at, gymer_world["plain"], "One too many")
    assert len(_rows()) == 2 * config.REVIEW_THREAD_MAX_QUESTIONS
    page = page_text(at)
    assert "the most it takes" in page
    assert "waiting for the coach's answer" not in page


def test_an_empty_answer_is_refused(monkeypatch, coach_world):
    """A blank answer writes nothing and says why."""
    at = _answer(_client_week(monkeypatch), coach_world["trained"], "   ")
    assert [row["kind"] for row in _rows()] == ["question"]
    assert "Please type some text first." in page_text(at)
    assert not at.exception


def test_an_answer_the_store_finds_too_long_is_refused(monkeypatch, coach_world):
    """Over the store's limit (the box's own limit stops it first, so the limit drops here)."""
    at = _client_week(monkeypatch)
    at.text_area(key=f"questions_answer_text_{coach_world['trained']}").input(ANSWER)
    monkeypatch.setattr(config, "REVIEW_THREAD_MAX_CHARS", 10)
    [send] = [
        item
        for item in at.button
        if item.proto.form_id == f"questions_answer_{coach_world['trained']}"
    ]
    send.click()
    at.run(timeout=30)
    assert [row["kind"] for row in _rows()] == ["question"]
    assert "Please keep it to at most 10 characters." in page_text(at)
    assert not at.exception


def test_a_question_answered_in_another_tab_meanwhile(monkeypatch, coach_world):
    """The coach answered in another tab: the second answer is refused and said so."""
    at = _client_week(monkeypatch)
    with db.connect() as conn:
        questions.answer_question(conn, USER_ID, coach_world["trained"], ANSWER)
    at = _answer(at, coach_world["trained"], "A second answer")
    assert [row["text"] for row in _rows()][1:] == [ANSWER]
    assert "This question has an answer already." in page_text(at)


def _store_fails_on_send(monkeypatch):
    """Make only the send fail, as a store locked at that moment would; the page still draws."""

    def broken(*args):
        """Raise the app's store error instead of writing."""
        raise accounts.StoreUnavailable

    monkeypatch.setattr(questions, "ask_question", broken)
    monkeypatch.setattr(questions, "answer_question", broken)


@pytest.mark.parametrize("role", ["gymer", "coach"])
def test_a_store_that_fails_on_send_shows_its_fixed_message(monkeypatch, request, role):
    """The store failing as a question or an answer is sent: its message once, the page drawn."""
    if role == "gymer":
        world = request.getfixturevalue("gymer_world")
        at = _my_week(monkeypatch)
        at.text_area(key=f"questions_ask_text_{world['trained']}").input(QUESTION)
        form = f"questions_ask_{world['trained']}"
    else:
        world = request.getfixturevalue("coach_world")
        at = _client_week(monkeypatch)
        at.text_area(key=f"questions_answer_text_{world['trained']}").input(ANSWER)
        form = f"questions_answer_{world['trained']}"
    _store_fails_on_send(monkeypatch)
    [send] = [item for item in at.button if item.proto.form_id == form]
    send.click()
    at.run(timeout=30)
    assert not at.exception
    unavailable = i18n.t("account.store_unavailable", "en")
    assert [item.value for item in at.warning].count(unavailable) == 1
    assert "Questions to the coach" in page_text(at)  # the page itself was drawn
    assert [row["kind"] for row in _rows()] == (["question"] if role == "coach" else [])
    assert _flash_left(at) is None


def _flash_left(at: AppTest):
    """Return an outcome still waiting in the session (None once shown)."""
    return at.session_state["questions_flash"] if "questions_flash" in at.session_state else None


def test_a_stale_answer_is_not_stored_under_a_newer_question(monkeypatch, coach_world):
    """Answered in another tab and a new question asked: the old page's answer is refused."""
    at = _client_week(monkeypatch)
    with db.connect() as conn:
        questions.answer_question(conn, USER_ID, coach_world["trained"], ANSWER)
        questions.ask_question(conn, CLIENT, coach_world["trained"], QUESTION)
    at = _answer(at, coach_world["trained"], "An answer to the first question")
    assert [row["kind"] for row in _rows()] == ["question", "answer", "question"]
    assert "This question has an answer already." in page_text(at)
