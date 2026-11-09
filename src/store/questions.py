"""Questions to the coach under an approved weekly review, and the coach's answers (T9.25).

A thread belongs to its review (PRD feature 27, AC-42), so it follows the review's own rule
(T9.16): the coach reads and answers it only while the relationship is active and the client shares
nutrition and every scope the review's metrics used; the gymer asks under an approved review about
them by the same rule, so no question is written that its coach could not read. Every other case (a
pending or rejected review, another gymer's or another coach's review, an ended relationship, a
scope turned off) gets the same `NotFound`, and nothing is written. The gymer reads the threads
under the approved reviews about them, also once the relationship has ended, as they read those
reviews (owner's choice, 2026-11-06). The thread takes turns: a question, the coach's answer, then
the next question, at most `config.REVIEW_THREAD_MAX_QUESTIONS` per review; there is no edit and no
delete of one row (rows are never changed in place; "delete everything" removes them). A coach's
read is audited by `authorised_read()` and an answer writes a `review_answered` audit row, both
without the text. The text is never sent to a model and is shown as plain text (views/questions.py).

The notifications of a new question or answer (T9.30) read the same threads by the same rule
through `list_question_events()`, which returns only IDs, the week and the time, never the text.
A coach's read of one client is always audited; the coach's own list is audited only when the
caller says so: the Notifications page does, the sidebar's count and the toasts, which run on
every page, do not (the middle way, owner's choice, 2026-11-08).
"""

import sqlite3

from src import config
from src.store import values
from src.store.access import NotFound, audit, authorise_read, authorised_read, role_of
from src.store.db import transaction


class NotYourTurn(ValueError):
    """Raised when the thread waits for the other side, or holds the most questions it takes."""

    def __init__(self) -> None:
        """Give the one fixed message (only a side who may write gets it)."""
        super().__init__("the thread waits for the other side")


_REVIEW = "SELECT client_id, coach_id, status FROM ai_reviews WHERE id = ?"
_USED_SCOPES = "SELECT scope FROM ai_review_scopes WHERE review_id = ?"
_KINDS = "SELECT id, kind FROM review_questions WHERE review_id = ? ORDER BY id"
_INSERT = """
INSERT INTO review_questions (review_id, author_id, kind, text, created_at) VALUES (?, ?, ?, ?, ?)
"""
# The review's sharing rule (nutrition and every scope in ai_review_scopes, from open_shares) is
# written out in each query below, as in reviews._WRITTEN_ABOUT and _WRITTEN_FOR_SHARED and
# my_data._COACH_QUESTIONS: a read cannot call another store function inside its transaction, so a
# change to the rule changes all of them (code review round 1), the notifications' three below too.
# The threads a coach reads about one client, after access.authorise_read() allowed nutrition:
# those under the approved reviews they wrote whose every scope the client still shares.
_OF_COACH_ABOUT = """
SELECT question.id, question.review_id, review.client_id, question.author_id, question.kind,
    question.text, question.created_at
FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.coach_id = ? AND review.client_id = ? AND review.status = 'APPROVED'
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY question.review_id, question.id
"""
# A coach's own read: the threads of every client who still shares nutrition and every scope of
# the review (the same rule as reviews._WRITTEN_FOR_SHARED).
_OF_COACH_ALL = """
SELECT question.id, question.review_id, review.client_id, question.author_id, question.kind,
    question.text, question.created_at
FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.coach_id = ? AND review.status = 'APPROVED' AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY question.review_id, question.id
"""
# A gymer's own read: the threads under every approved review about them, a former coach's too.
_ABOUT_GYMER = """
SELECT question.id, question.review_id, review.client_id, question.author_id, question.kind,
    question.text, question.created_at
FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.client_id = ? AND review.status = 'APPROVED'
ORDER BY question.review_id, question.id
"""
# The notifications' reads (T9.30): the same rules as the three reads above, the questions for a
# coach and the answers for a gymer, with the review's coach, client and week and the row's time;
# never the text. A coach reading one client, after access.authorise_read() allowed nutrition:
_ASKED_ABOUT = """
SELECT question.id, review.coach_id, review.client_id, review.period_start, question.created_at
FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.coach_id = ? AND review.client_id = ? AND review.status = 'APPROVED'
    AND question.kind = 'question'
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY question.id
"""
# A coach's own: the questions of every client who still shares nutrition and every review scope.
_ASKED_OF_COACH = """
SELECT question.id, review.coach_id, review.client_id, review.period_start, question.created_at
FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.coach_id = ? AND review.status = 'APPROVED' AND question.kind = 'question'
    AND EXISTS (
        SELECT 1 FROM open_shares AS share
        WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
          AND share.scope = 'nutrition'
    )
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY question.id
"""
# A gymer's own: the answers under every approved review about them, a former coach's too.
_ANSWERED_ABOUT_GYMER = """
SELECT question.id, review.coach_id, review.client_id, review.period_start, question.created_at
FROM review_questions AS question
JOIN ai_reviews AS review ON review.id = question.review_id
WHERE review.client_id = ? AND review.status = 'APPROVED' AND question.kind = 'answer'
ORDER BY question.id
"""
# The approved reviews about a gymer whose coach may read them now: those the gymer may ask under.
_ASKABLE = """
SELECT review.id FROM ai_reviews AS review
WHERE review.client_id = ? AND review.status = 'APPROVED' AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY review.id
"""


def _approved_review(conn: sqlite3.Connection, review_id: int) -> sqlite3.Row:
    """Return an approved review's row, or raise NotFound."""
    review = conn.execute(_REVIEW, (review_id,)).fetchone()
    if review is None or review["status"] != "APPROVED":
        raise NotFound
    return review


def _check_coach_reads(conn: sqlite3.Connection, review: sqlite3.Row, review_id: int) -> None:
    """Raise NotFound unless the review's coach may read nutrition and every scope it used."""
    # authorise_read returns True for a coach's allowed read and raises NotFound otherwise; the
    # review's coach and client always differ (the table's CHECK), so it never returns False here.
    used = [row["scope"] for row in conn.execute(_USED_SCOPES, (review_id,))]
    for scope in dict.fromkeys(("nutrition", *used)):
        if not authorise_read(conn, review["coach_id"], review["client_id"], scope):
            raise NotFound


def _thread(conn: sqlite3.Connection, review_id: int) -> list[sqlite3.Row]:
    """Return the IDs and kinds of the thread's rows, oldest first."""
    return conn.execute(_KINDS, (review_id,)).fetchall()


def ask_question(conn: sqlite3.Connection, gymer_id: str, review_id: int, text: str) -> int:
    """Write the gymer's question under an approved review about them; return its ID."""
    body = values.text(text, "text", config.REVIEW_THREAD_MAX_CHARS)
    if not values.is_row_id(review_id):
        raise NotFound
    with transaction(conn):
        review = _approved_review(conn, review_id)
        if review["client_id"] != gymer_id or role_of(conn, gymer_id) != "gymer":
            raise NotFound
        _check_coach_reads(conn, review, review_id)
        kinds = [row["kind"] for row in _thread(conn, review_id)]
        waiting = bool(kinds) and kinds[-1] == "question"
        if waiting or kinds.count("question") >= config.REVIEW_THREAD_MAX_QUESTIONS:
            raise NotYourTurn
        # Asking about one's own review reads nothing of another user, so it is not audited.
        cursor = conn.execute(_INSERT, (review_id, gymer_id, "question", body, values.utc_text()))
    return cursor.lastrowid


def answer_question(
    conn: sqlite3.Connection,
    coach_id: str,
    review_id: int,
    text: str,
    question_id: int | None = None,
) -> int:
    """Write the coach's answer to the open question under a review they wrote; return its ID."""
    # question_id names the question the coach saw: if another has become the open one since
    # (answered in another tab, then a new question asked), the answer is refused, not stored
    # under a question it does not answer (code review round 2).
    body = values.text(text, "text", config.REVIEW_THREAD_MAX_CHARS)
    if not values.is_row_id(review_id):
        raise NotFound
    with transaction(conn):
        review = _approved_review(conn, review_id)
        if review["coach_id"] != coach_id:
            raise NotFound
        _check_coach_reads(conn, review, review_id)
        rows = _thread(conn, review_id)
        if not rows or rows[-1]["kind"] != "question":
            raise NotYourTurn
        if question_id is not None and rows[-1]["id"] != question_id:
            raise NotYourTurn
        cursor = conn.execute(_INSERT, (review_id, coach_id, "answer", body, values.utc_text()))
        # IDs, the action, the kind of data and the time; never the text (AC-29, AC-42).
        audit(
            conn,
            coach_id,
            "review_answered",
            "review_questions",
            subject_id=review["client_id"],
            resource_id=cursor.lastrowid,
        )
    return cursor.lastrowid


def list_questions(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return the thread rows the actor may read about the subject, by review, oldest first."""
    # A coach reading a client gets the threads under the reviews they wrote about that client
    # whose every scope is still shared (audited by authorised_read); a coach reading their own
    # gets those of every client who still shares (one audit row per client); a gymer reading
    # their own gets the threads under every approved review about them.
    with authorised_read(conn, actor_id, subject_id, "nutrition", "review_questions"):
        if actor_id != subject_id:
            rows = conn.execute(_OF_COACH_ABOUT, (actor_id, subject_id)).fetchall()
        elif role_of(conn, actor_id) == "coach":
            rows = conn.execute(_OF_COACH_ALL, (actor_id,)).fetchall()
            for client_id in dict.fromkeys(row["client_id"] for row in rows):
                audit(conn, actor_id, "read", "review_questions", subject_id=client_id)
        else:
            rows = conn.execute(_ABOUT_GYMER, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def list_question_events(
    conn: sqlite3.Connection, actor_id: str, subject_id: str, *, audited: bool = True
) -> list[dict]:
    """Return the question or answer events the actor may be told of about the subject, no text."""
    # The same three cases as list_questions: a coach reading a client gets that client's
    # questions under the reviews they wrote whose every scope is still shared (NotFound
    # otherwise); a coach reading their own gets those of every client who still shares; a gymer
    # reading their own gets the coach's answers under every approved review about them. A coach's
    # read of one named client is always audited, as every read of another user's data is. Only
    # the coach's own list, which the sidebar's count and the toasts read on every page, skips its
    # audit rows (one `read` per client found) unless `audited` (the Notifications page): the
    # middle way, owner's choice, 2026-11-08, and the one exception (code review round 1).
    with transaction(conn):
        by_coach = authorise_read(conn, actor_id, subject_id, "nutrition")
        if by_coach:
            rows = conn.execute(_ASKED_ABOUT, (actor_id, subject_id)).fetchall()
            audit(conn, actor_id, "read", "review_questions", subject_id=subject_id)
        elif role_of(conn, actor_id) == "coach":
            rows = conn.execute(_ASKED_OF_COACH, (actor_id,)).fetchall()
            if audited:
                for client_id in dict.fromkeys(row["client_id"] for row in rows):
                    audit(conn, actor_id, "read", "review_questions", subject_id=client_id)
        else:
            rows = conn.execute(_ANSWERED_ABOUT_GYMER, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def askable_reviews(conn: sqlite3.Connection, gymer_id: str) -> frozenset[int]:
    """Return the IDs of the approved reviews the gymer may ask under now (none for a coach)."""
    # Only the gymer's own reviews' IDs: what the page needs to show a box or the fixed message.
    with transaction(conn):
        role = role_of(conn, gymer_id)
        if role is None:
            raise NotFound
        if role != "gymer":
            return frozenset()
        return frozenset(row["id"] for row in conn.execute(_ASKABLE, (gymer_id,)))
