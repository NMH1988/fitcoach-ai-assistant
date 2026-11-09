"""Notifications of a new question or answer in the store (T9.30, AC-43, feature 28).

A coach is told of each question a client asked under a weekly review, a gymer of each answer a
coach wrote under an approved review about them, by the thread's own rule (T9.25); no text is in a
notification; a coach's read of one client is always audited, and the coach's own list only when
the caller says so (the Notifications page), one `read` row of `review_questions` per client
found; a deletion takes the notifications with it.
"""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from src.store import access, my_data, notifications, questions, reviews, users
from tests.store_world import no_threads

COACH, OTHER_COACH = "coach-q", "coach-q-other"
GYM, SECOND_GYM, OTHER_GYM = "gym-q", "gym-q-second", "gym-q-other"
QUESTION = "CANARY-QUESTION why fewer carbs on rest days?"
ANSWER = "CANARY-ANSWER because you train less then."
WEEK = date(2026, 10, 19)
QUESTION_KINDS = ("question_asked", "question_answered")


@pytest.fixture
def world(store_conn):
    """Coach Quinn with two clients sharing every scope; another coach with their own client."""
    for user_id, role, name in (
        (COACH, "coach", "Coach Quinn"),
        (OTHER_COACH, "coach", "Coach Rae"),
        (GYM, "gymer", "Gym Quade"),
        (SECOND_GYM, "gymer", "Gym Sami"),
        (OTHER_GYM, "gymer", "Gym Otto"),
    ):
        users.create_user(store_conn, user_id, role, name)
    found = {}
    for coach, client in ((COACH, GYM), (COACH, SECOND_GYM), (OTHER_COACH, OTHER_GYM)):
        found[client] = users.start_relationship(store_conn, coach, client)
        for scope in access.SCOPES:
            users.set_consent(store_conn, client, found[client], scope, True)
    return found


def _approved(conn, coach, client, week=WEEK, scopes=("nutrition", "training")) -> int:
    """Save a made-up review of the week with the scopes and approve it; return its ID."""
    review = reviews.save_review(
        conn,
        coach,
        client,
        period_start=week,
        metrics={"logged_days": 3},
        data_quality={},
        draft={"observations": ["CANARY-REVIEW-TEXT"]},
        model_version="m",
        scopes=scopes,
    )
    reviews.decide_review(conn, coach, review, "approve")
    return review


def _thread(conn, coach, client, week=WEEK, scopes=("nutrition", "training")) -> int:
    """Approve a review, ask under it and answer; return the review's ID."""
    review = _approved(conn, coach, client, week, scopes)
    questions.ask_question(conn, client, review, QUESTION)
    questions.answer_question(conn, coach, review, ANSWER)
    return review


def _told(conn, user_id: str, **kwargs) -> list[tuple]:
    """Return the user's question notifications as (kind, other side, scopes, week)."""
    return [
        (n.kind, n.other_name, n.scopes, n.week)
        for n in notifications.list_notifications(conn, user_id, **kwargs)
        if n.kind in QUESTION_KINDS
    ]


def _audit(conn) -> list[dict]:
    """Return every audit row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


# --- Criterion 1: the two kinds, with no text ----------------------------------------------------


def test_a_coach_is_told_of_a_question_and_a_gymer_of_an_answer(store_conn, world):
    """The coach sees "asked" with the client and week; the gymer "answered" with the coach."""
    _thread(store_conn, COACH, GYM)
    assert _told(store_conn, COACH) == [("question_asked", "Gym Quade", (), "2026-10-19")]
    assert _told(store_conn, GYM) == [("question_answered", "Coach Quinn", (), "2026-10-19")]


def test_a_question_waiting_for_its_answer_is_told_to_the_coach_only(store_conn, world):
    """Before the answer the gymer is told nothing; the coach is told of the question once."""
    review = _approved(store_conn, COACH, GYM)
    questions.ask_question(store_conn, GYM, review, QUESTION)
    assert _told(store_conn, COACH) == [("question_asked", "Gym Quade", (), "2026-10-19")]
    assert _told(store_conn, GYM) == []


def test_each_question_and_answer_is_its_own_event(store_conn, world):
    """Two turns of a thread give two notifications on each side, each with its own key."""
    review = _thread(store_conn, COACH, GYM)
    questions.ask_question(store_conn, GYM, review, QUESTION + " again")
    questions.answer_question(store_conn, COACH, review, ANSWER + " again")
    coach_keys = [n.key for n in notifications.list_notifications(store_conn, COACH)]
    asked = [key for key in coach_keys if key[0] == "question_asked"]
    assert len(asked) == len(set(asked)) == 2
    assert len(_told(store_conn, GYM)) == 2


def test_a_question_notification_holds_no_text(store_conn, world):
    """Neither side's notifications hold the question's, the answer's or the review's text."""
    _thread(store_conn, COACH, GYM)
    for user_id in (COACH, GYM):
        for found in notifications.list_notifications(store_conn, user_id, audited=True):
            assert "CANARY" not in repr(found)
    for event in questions.list_question_events(store_conn, COACH, GYM):
        assert set(event) == {"id", "coach_id", "client_id", "period_start", "created_at"}


# --- Criterion 2: only a side who may read the thread --------------------------------------------


def test_an_ended_relationship_hides_the_coach_s_but_not_the_gymer_s(store_conn, world):
    """Once ended, the coach is told nothing of the thread; the gymer still sees the answer."""
    _thread(store_conn, COACH, GYM)
    users.end_relationship(store_conn, GYM, world[GYM])
    assert _told(store_conn, COACH) == []
    assert _told(store_conn, GYM) == [("question_answered", "Coach Quinn", (), "2026-10-19")]


@pytest.mark.parametrize("scope", ["nutrition", "training"])
def test_a_scope_the_review_used_turned_off_hides_the_coach_s(store_conn, world, scope):
    """With nutrition or a scope the review used off, the coach's notification is hidden."""
    _thread(store_conn, COACH, GYM)
    _thread(store_conn, COACH, GYM, date(2026, 10, 12), scopes=("nutrition", "body"))
    users.set_consent(store_conn, GYM, world[GYM], scope, False)
    weeks = [week for *_, week in _told(store_conn, COACH)]
    assert weeks == ([] if scope == "nutrition" else ["2026-10-12"])
    assert len(_told(store_conn, GYM)) == 2


def test_a_second_coach_or_gymer_sees_none_of_them(store_conn, world):
    """Another coach, that coach's client and the coach's other client are told nothing of it."""
    _thread(store_conn, COACH, GYM)
    for user_id in (OTHER_COACH, OTHER_GYM, SECOND_GYM):
        assert _told(store_conn, user_id) == []


def test_another_coach_s_client_is_not_found(store_conn, world):
    """A coach's read of another coach's client is refused with the one NotFound and no audit."""
    _thread(store_conn, OTHER_COACH, OTHER_GYM)
    with pytest.raises(access.NotFound):
        questions.list_question_events(store_conn, COACH, OTHER_GYM)
    assert all(row["action"] != "read" for row in _audit(store_conn))


# --- Criterion 2: the audit (the middle way, owner's choice, 2026-11-08) -------------------------


def test_the_count_and_the_toasts_write_no_audit_row(store_conn, world):
    """The sidebar's read (audited not passed) leaves the audit log as it was."""
    _thread(store_conn, COACH, GYM)
    before = _audit(store_conn)
    assert _told(store_conn, COACH)
    assert _audit(store_conn) == before


def test_the_page_writes_one_read_row_per_client_listed(store_conn, world):
    """audited=True: a `read` of review_questions per client with a question, none for the rest."""
    _thread(store_conn, COACH, GYM)
    _thread(store_conn, COACH, GYM, date(2026, 10, 12))
    review = _approved(store_conn, COACH, SECOND_GYM, date(2026, 10, 12))
    questions.ask_question(store_conn, SECOND_GYM, review, QUESTION)
    _thread(store_conn, OTHER_COACH, OTHER_GYM)
    before = len(_audit(store_conn))
    assert len(_told(store_conn, COACH, audited=True)) == 3
    rows = _audit(store_conn)[before:]
    assert [(row["actor_id"], row["action"], row["resource_type"]) for row in rows] == [
        (COACH, "read", "review_questions")
    ] * 2
    assert {row["subject_id"] for row in rows} == {GYM, SECOND_GYM}
    assert all(row["resource_id"] is None and "CANARY" not in str(row) for row in rows)


def test_a_coach_with_no_question_or_a_gymer_writes_no_audit_row(store_conn, world):
    """The page's read for a coach with nothing to tell, or a gymer's own, audits nothing."""
    _thread(store_conn, COACH, GYM)
    before = _audit(store_conn)
    notifications.list_notifications(store_conn, OTHER_COACH, audited=True)
    notifications.list_notifications(store_conn, GYM, audited=True)
    assert _audit(store_conn) == before


def test_the_client_sees_the_page_s_audit_row_in_their_export(store_conn, world):
    """The read row names the client as its subject, so it is in the client's export."""
    _thread(store_conn, COACH, GYM)
    notifications.list_notifications(store_conn, COACH, audited=True)
    rows = json.loads(my_data.export_user_data(store_conn, GYM))["audit_log"]
    assert any(
        (row["actor_id"], row["action"], row["resource_type"])
        == (COACH, "read", "review_questions")
        for row in rows
    )


def test_a_coach_reading_one_client_is_always_audited(store_conn, world):
    """Code review round 1: a named client's read writes its row, audited=False or not."""
    _thread(store_conn, COACH, GYM)
    before = len(_audit(store_conn))
    assert len(questions.list_question_events(store_conn, COACH, GYM, audited=False)) == 1
    assert len(questions.list_question_events(store_conn, COACH, GYM)) == 1
    rows = _audit(store_conn)[before:]
    assert [(row["action"], row["subject_id"]) for row in rows] == [("read", GYM)] * 2


# --- Criterion 3: the read marks and a deletion --------------------------------------------------


def _unread_kinds(conn, user_id: str) -> list[str]:
    """Return the kinds of the user's unread question notifications."""
    found = notifications.list_notifications(conn, user_id)
    return [n.kind for n in found if n.unread and n.kind in QUESTION_KINDS]


@pytest.mark.parametrize("user_id", [COACH, GYM])
def test_the_question_kinds_use_the_read_mark(store_conn, world, monkeypatch, user_id):
    """A question or answer after the reader's mark is unread; one before a later mark is read."""
    _thread(store_conn, COACH, GYM)
    kind = "question_asked" if user_id == COACH else "question_answered"
    now = datetime.now(UTC)
    monkeypatch.setattr(notifications, "_now", lambda: now - timedelta(hours=1))
    notifications.mark_all_read(store_conn, user_id)
    assert _unread_kinds(store_conn, user_id) == [kind]
    monkeypatch.setattr(notifications, "_now", lambda: now + timedelta(hours=1))
    notifications.mark_all_read(store_conn, user_id)
    assert _unread_kinds(store_conn, user_id) == []


def test_a_gymer_s_deletion_takes_the_coach_s_question_notifications(store_conn, world):
    """After the gymer deletes their data, the coach is told nothing of their questions."""
    _thread(store_conn, COACH, GYM)
    _thread(store_conn, COACH, SECOND_GYM)
    my_data.delete_user_data(store_conn, GYM, no_threads)
    assert {name for _, name, *_ in _told(store_conn, COACH)} == {"Gym Sami"}


def test_a_coach_s_deletion_takes_the_gymer_s_answer_notifications(store_conn, world):
    """After the coach deletes their data, the gymer's answers from that coach are gone."""
    _thread(store_conn, COACH, GYM)
    my_data.delete_user_data(store_conn, COACH, no_threads)
    assert _told(store_conn, GYM) == []
