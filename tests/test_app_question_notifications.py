"""UI tests for the notifications of a new question or answer (T9.30, AC-43, feature 28).

A new question raises the coach's count and an answer the gymer's (criterion 3); the line names
the other side and the week, never the text (criterion 1); only the Notifications page writes the
coach's `read` audit row, the bell and the toasts none (criterion 2, the middle way); German
(criterion 5); the sharing page tells the gymer the coach is told of a question (criterion 6).
"""

from datetime import date

import pytest

from src.store import db, questions, reviews, users
from tests.test_app_account import PROFILE, USER_ID, store_account, texts
from tests.test_app_notifications import _bell, _lines, _signed_in, _toasts
from tests.test_app_sharing import open_page
from views import navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

ALEX, KAI = "gym-alex-q", "coach-kai-q"
QUESTION = "CANARY-QUESTION why fewer carbs on rest days?"
ANSWER = "CANARY-ANSWER because you train less then."
WEEK = date(2026, 10, 19)


def _approved(conn, coach: str, client: str) -> int:
    """Save a made-up review of WEEK that used nutrition and approve it; return its ID."""
    review = reviews.save_review(
        conn,
        coach,
        client,
        period_start=WEEK,
        metrics={"logged_days": 3},
        data_quality={},
        draft={"observations": ["CANARY-REVIEW-TEXT"]},
        model_version="m",
    )
    reviews.decide_review(conn, coach, review, "approve")
    return review


def _connect(conn, coach: str, client: str) -> None:
    """Pair the coach and the client with nutrition shared."""
    relationship = users.start_relationship(conn, coach, client)
    users.set_consent(conn, client, relationship, "nutrition", True)


@pytest.fixture
def coach_review():
    """Store the canary coach with Alex (nutrition shared) and an approved review; return its ID."""
    store_account("coach", name="Coach Sam")
    with db.connect() as conn:
        users.create_user(conn, ALEX, "gymer", "Alex")
        _connect(conn, USER_ID, ALEX)
        return _approved(conn, USER_ID, ALEX)


@pytest.fixture
def gymer_review():
    """Store the canary gymer with Coach Kai, an approved review and a question; return its ID."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, KAI, "coach", "Coach Kai")
        _connect(conn, KAI, USER_ID)
        review = _approved(conn, KAI, USER_ID)
        questions.ask_question(conn, USER_ID, review, QUESTION)
        return review


def _question_reads() -> list[str]:
    """Return the subjects of the coach's `read` audit rows of review_questions."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT subject_id FROM audit_log WHERE action = 'read'"
            " AND resource_type = 'review_questions' ORDER BY id"
        ).fetchall()
    return [row["subject_id"] for row in rows]


def _count(at) -> int:
    """Return the unread count the bell shows."""
    [label] = _bell(at)
    return int(label.split(" · ", 1)[1].split()[0])


def test_a_new_question_raises_the_coach_s_count_and_toasts(monkeypatch, coach_review):
    """Criterion 3: a question stored meanwhile shows on the next run, without its text."""
    at = _signed_in(monkeypatch)
    before = _count(at)
    with db.connect() as conn:
        questions.ask_question(conn, ALEX, coach_review, QUESTION)
    at.run(timeout=30)
    assert _count(at) == before + 1
    told = "Alex asked a question under the weekly review for the week of 2026-10-19."
    assert _toasts(at) == [told]
    assert "CANARY" not in " ".join(_toasts(at)) + texts(at)


def test_an_answer_raises_the_gymer_s_count_and_toasts(monkeypatch, gymer_review):
    """Criterion 3: the coach's answer shows on the gymer's next run, without its text."""
    at = _signed_in(monkeypatch)
    before = _count(at)
    with db.connect() as conn:
        questions.answer_question(conn, KAI, gymer_review, ANSWER)
    at.run(timeout=30)
    assert _count(at) == before + 1
    told = "Coach Kai answered your question under the weekly review for the week of 2026-10-19."
    assert _toasts(at) == [told]
    at = open_page(at, navigation.NOTIFICATIONS)
    assert any(line.endswith(told) for line in _lines(at))
    assert "CANARY" not in texts(at)


def test_only_the_page_writes_the_coach_s_read_audit_row(monkeypatch, coach_review):
    """Criterion 2: the bell and the toasts write none; each run of the page one row for Alex."""
    with db.connect() as conn:
        questions.ask_question(conn, ALEX, coach_review, QUESTION)
    at = _signed_in(monkeypatch)
    at.run(timeout=30)
    assert _toasts(at) == [] and _count(at) >= 1  # toasted on the first run, counted on both
    assert _question_reads() == []
    at = open_page(at, navigation.NOTIFICATIONS)
    assert any("Alex asked a question" in line for line in _lines(at))
    assert _question_reads() == [ALEX]
    at.run(timeout=30)  # a rerun of the page (owner's choice, 2026-11-08: each run)
    assert _question_reads() == [ALEX, ALEX]


def test_a_gymer_s_page_writes_no_audit_row(monkeypatch, gymer_review):
    """Criterion 2: the gymer reads their own answers, which is never audited."""
    with db.connect() as conn:
        questions.answer_question(conn, KAI, gymer_review, ANSWER)
    open_page(_signed_in(monkeypatch), navigation.NOTIFICATIONS)
    assert _question_reads() == []


def test_the_question_and_answer_lines_in_german(monkeypatch, gymer_review):
    """Criterion 5: the answer's line and the toast read in German."""
    with db.connect() as conn:
        questions.answer_question(conn, KAI, gymer_review, ANSWER)
    at = _signed_in(monkeypatch, language="de")
    told = "Coach Kai hat Ihre Frage zum Wochenbericht für die Woche vom 2026-10-19 beantwortet."
    assert told in _toasts(at)
    at = open_page(at, navigation.NOTIFICATIONS)
    assert any(line.endswith(told) for line in _lines(at))
    assert "oder Ihre Frage dazu beantwortet hat" in texts(at)  # the gymer's intro


def test_the_coach_s_question_line_and_intro_in_german(monkeypatch, coach_review):
    """Criterion 5: the coach's line and the intro naming the audit read, in German."""
    with db.connect() as conn:
        questions.ask_question(conn, ALEX, coach_review, QUESTION)
    at = open_page(_signed_in(monkeypatch, language="de"), navigation.NOTIFICATIONS)
    told = "Alex hat eine Frage zum Wochenbericht für die Woche vom 2026-10-19 gestellt."
    assert any(line.endswith(told) for line in _lines(at))
    assert "gilt das als Zugriff auf die Fragen dieser Kunden" in texts(at)


@pytest.mark.parametrize(
    ("language", "told", "recorded"),
    [
        (
            "en",
            "Your coach is also told when you ask a question under a weekly review, while they "
            "may read it.",
            "Your export records it as a read of your questions when your coach opens their "
            "Notifications page, not when the sidebar count or a pop-up tells them.",
        ),
        (
            "de",
            "Ihr Coach wird auch benachrichtigt, wenn Sie eine Frage zu einem Wochenbericht "
            "stellen, solange er sie lesen darf.",
            "Ihr Export verzeichnet es als Zugriff auf Ihre Fragen, wenn Ihr Coach seine "
            "Benachrichtigungsseite öffnet, nicht wenn die Anzeige in der Seitenleiste oder ein "
            "Hinweisfenster es ihm mitteilt.",
        ),
    ],
)
def test_the_sharing_page_says_the_coach_is_told_of_a_question(
    monkeypatch, gymer_review, language, told, recorded
):
    """Criterion 6: the sharing text names the notification and what the export records."""
    at = open_page(_signed_in(monkeypatch, language), navigation.SHARING)
    assert told in texts(at)
    # Compliance run 1 (Low): only the Notifications page leaves a read in the export.
    assert recorded in texts(at)
