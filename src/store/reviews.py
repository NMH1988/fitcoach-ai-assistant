"""Weekly reviews in the store: saved as PENDING_REVIEW, then approved, edited or rejected (T9.6).

T9.16's workflow (`src/agent/review.py`) drafts a review and calls these functions; the checks on
its content (schema, citations, calorie floor, no diagnosis, the training rules) are in
`src/weekly_review.py`. Here: a review is saved and decided only by the client's coach, while the
relationship is active and the client shares every scope the review's metrics used (nutrition
always; body or training when the weight trend or the training week is in it, T9.16), so revoking
any of them hides a review and blocks a pending one (AC-22); every decision stores the reviewer and
the time and writes an audit row with no values (AC-29). While a review of a client and week is
pending or approved, the coach cannot save another one for that week; a rejected one may be run
again (T9.16). A gymer reads only the approved reviews about them, never the model's draft; a coach
reads the reviews they wrote, only about clients who still share every scope each one used (owner's
choices, 2026-10-27).
"""

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from src import config
from src.store import values
from src.store.access import SCOPES, NotFound, audit, authorise_read, authorised_read, role_of
from src.store.db import transaction

Decision = Literal["approve", "edit", "reject"]
# The status and audit action each decision leads to.
_OUTCOMES: dict[str, tuple[str, str]] = {
    "approve": ("APPROVED", "review_approved"),
    "edit": ("APPROVED", "review_edited"),
    "reject": ("REJECTED", "review_rejected"),
}


class ReviewExists(ValueError):
    """Raised when the coach already has a pending or approved review of that client's week."""

    def __init__(self) -> None:
        """Give the one fixed message (the coach may read their own review, so it is no secret)."""
        super().__init__("a review of this week is pending or approved")


_INSERT_REVIEW = """
INSERT INTO ai_reviews (
    client_id, coach_id, period_start, metrics, data_quality, draft,
    status, edited_by_coach, model_version, created_at, thread_id
) VALUES (?, ?, ?, ?, ?, ?, 'PENDING_REVIEW', 0, ?, ?, ?)
"""
_INSERT_REF = "INSERT INTO ai_evidence_refs (review_id, source_id, chunk_id) VALUES (?, ?, ?)"
_INSERT_SCOPE = "INSERT INTO ai_review_scopes (review_id, scope) VALUES (?, ?)"
_OPEN_FOR_WEEK = """
SELECT 1 FROM ai_reviews
WHERE coach_id = ? AND client_id = ? AND period_start = ?
  AND status IN ('PENDING_REVIEW', 'APPROVED')
"""
# The scopes a coach may use for a client right now (the sharing rule is the open_shares view).
_SHARED_SCOPES = "SELECT scope FROM open_shares WHERE coach_id = ? AND client_id = ?"
_REVIEW = "SELECT client_id, coach_id, status, draft FROM ai_reviews WHERE id = ?"
_STATUS = "SELECT status FROM ai_reviews WHERE id = ? AND coach_id = ?"
_PENDING_OF_THREAD = """
SELECT id FROM ai_reviews WHERE coach_id = ? AND thread_id = ? AND status = 'PENDING_REVIEW'
"""
_DISCARD_REFS = "DELETE FROM ai_evidence_refs WHERE review_id = ?"
_DISCARD_SCOPES = "DELETE FROM ai_review_scopes WHERE review_id = ?"
_DISCARD = "DELETE FROM ai_reviews WHERE id = ? AND status = 'PENDING_REVIEW'"
_USED_SCOPES = "SELECT scope FROM ai_review_scopes WHERE review_id = ?"
_DECIDE = """
UPDATE ai_reviews
SET status = ?, final = ?, edited_by_coach = ?, reviewed_by = ?, reviewed_at = ?
WHERE id = ? AND status = 'PENDING_REVIEW'
"""
# The columns every list returns; evidence_refs and scopes as JSON arrays built by SQLite. A gymer
# never gets the model's draft (an edited review's draft holds text the coach replaced, AC-29) or
# the workflow's thread.
_APPROVED_ABOUT = """
SELECT review.id, review.client_id, review.coach_id, review.period_start, review.metrics,
    review.data_quality, NULL AS draft, review.final, review.status, review.edited_by_coach,
    review.model_version, review.created_at, review.reviewed_by, review.reviewed_at,
    NULL AS thread_id,
    (SELECT json_group_array(json_object('source_id', ref.source_id, 'chunk_id', ref.chunk_id))
     FROM ai_evidence_refs AS ref WHERE ref.review_id = review.id) AS evidence_refs,
    (SELECT json_group_array(used.scope)
     FROM ai_review_scopes AS used WHERE used.review_id = review.id) AS scopes
FROM ai_reviews AS review
WHERE review.client_id = ? AND review.status = 'APPROVED'
ORDER BY review.period_start, review.id
"""
# A coach's reviews of one client, read after access.authorise_read() allowed nutrition: only those
# whose every scope the client still shares (T9.16).
_WRITTEN_ABOUT = """
SELECT review.id, review.client_id, review.coach_id, review.period_start, review.metrics,
    review.data_quality, review.draft, review.final, review.status, review.edited_by_coach,
    review.model_version, review.created_at, review.reviewed_by, review.reviewed_at,
    review.thread_id,
    (SELECT json_group_array(json_object('source_id', ref.source_id, 'chunk_id', ref.chunk_id))
     FROM ai_evidence_refs AS ref WHERE ref.review_id = review.id) AS evidence_refs,
    (SELECT json_group_array(used.scope)
     FROM ai_review_scopes AS used WHERE used.review_id = review.id) AS scopes
FROM ai_reviews AS review
WHERE review.coach_id = ? AND review.client_id = ?
    AND NOT EXISTS (
        SELECT 1 FROM ai_review_scopes AS used
        WHERE used.review_id = review.id AND NOT EXISTS (
            SELECT 1 FROM open_shares AS share
            WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
              AND share.scope = used.scope
        )
    )
ORDER BY review.period_start, review.id
"""
# A coach's reviews of every client who still shares nutrition and every scope the review used:
# the same rule as access.authorise_read(), so an ended relationship or a revoked scope hides the
# review (AC-22).
_WRITTEN_FOR_SHARED = """
SELECT review.id, review.client_id, review.coach_id, review.period_start, review.metrics,
    review.data_quality, review.draft, review.final, review.status, review.edited_by_coach,
    review.model_version, review.created_at, review.reviewed_by, review.reviewed_at,
    review.thread_id,
    (SELECT json_group_array(json_object('source_id', ref.source_id, 'chunk_id', ref.chunk_id))
     FROM ai_evidence_refs AS ref WHERE ref.review_id = review.id) AS evidence_refs,
    (SELECT json_group_array(used.scope)
     FROM ai_review_scopes AS used WHERE used.review_id = review.id) AS scopes
FROM ai_reviews AS review
WHERE review.coach_id = ? AND EXISTS (
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
ORDER BY review.period_start, review.id
"""
_JSON_FIELDS = ("metrics", "data_quality", "draft", "final", "evidence_refs", "scopes")


def _json_text(value: object, field: str) -> str:
    """Return a mapping as JSON text within the size limit, or raise StoreValueError."""
    if not isinstance(value, Mapping):
        raise values.StoreValueError(field, "must be a mapping")
    try:
        # allow_nan=False: NaN and infinities are not JSON and SQLite's json_valid() refuses them.
        text = json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
    except TypeError, ValueError:
        text = None
    # Raised outside the `except`, so the error from json (which can quote a value) is not kept.
    if text is None:
        raise values.StoreValueError(field, "must hold JSON values only")
    if not values.is_utf8(text):
        raise values.StoreValueError(field, "must be text the store can encode")
    if len(text) > config.STORE_JSON_MAX_CHARS:
        raise values.StoreValueError(field, "is too long")
    return text


def _ordered_scopes(scopes: object) -> tuple[str, ...]:
    """Return the scopes in SCOPES order, each once; nutrition must be one of them."""
    if isinstance(scopes, str) or not isinstance(scopes, Sequence | frozenset | set):
        raise values.StoreValueError("scopes", "must be a list of scopes")
    for scope in scopes:
        values.choice(scope, "scopes", SCOPES)
    if "nutrition" not in scopes:
        raise values.StoreValueError("scopes", "must include nutrition")
    return tuple(scope for scope in SCOPES if scope in scopes)


def _decoded(row: sqlite3.Row) -> dict:
    """Return a review row as a dict with its JSON fields decoded, its scopes in SCOPES order."""
    review = dict(row)
    for field in _JSON_FIELDS:
        if review[field] is not None:
            review[field] = json.loads(review[field])
    review["scopes"] = [scope for scope in SCOPES if scope in (review["scopes"] or ())]
    review["edited_by_coach"] = bool(review["edited_by_coach"])
    return review


def _check_no_open_review(
    conn: sqlite3.Connection, coach_id: str, client_id: str, period_start: str
) -> None:
    """Raise ReviewExists while the coach's review of that client's week is pending or approved."""
    if conn.execute(_OPEN_FOR_WEEK, (coach_id, client_id, period_start)).fetchone() is not None:
        raise ReviewExists


def prepare_review(
    conn: sqlite3.Connection, coach_id: str, client_id: str, period_start: date
) -> tuple[str, ...]:
    """Return the scopes a new review of the client's week may use; NotFound or ReviewExists."""
    # The workflow's first step (authorise): a coach with nutrition access and no open review of
    # that week gets the scopes the client shares now, in SCOPES order. Nothing is read from the
    # client's records, so nothing is audited.
    week = values.date_text(period_start, "period_start")
    with transaction(conn):
        if not authorise_read(conn, coach_id, client_id, "nutrition"):
            raise NotFound  # a user reviewing themselves
        _check_no_open_review(conn, coach_id, client_id, week)
        shared = {row["scope"] for row in conn.execute(_SHARED_SCOPES, (coach_id, client_id))}
    return tuple(scope for scope in SCOPES if scope in shared)


def save_review(
    conn: sqlite3.Connection,
    coach_id: str,
    client_id: str,
    *,
    period_start: date,
    metrics: Mapping,
    data_quality: Mapping,
    draft: Mapping,
    model_version: str,
    evidence_refs: Sequence[tuple[str, str]] = (),
    scopes: Sequence[str] = ("nutrition",),
    thread_id: str | None = None,
) -> int:
    """Save a drafted review as PENDING_REVIEW with its evidence and scopes; return its ID."""
    used = _ordered_scopes(scopes)
    week = values.date_text(period_start, "period_start")
    row = (
        week,
        _json_text(metrics, "metrics"),
        _json_text(data_quality, "data_quality"),
        _json_text(draft, "draft"),
        values.text(model_version, "model_version"),
        values.utc_text(),
        None if thread_id is None else values.text(thread_id, "thread_id"),
    )
    refs = [
        (values.text(source_id, "source_id"), values.text(chunk_id, "chunk_id"))
        for source_id, chunk_id in evidence_refs
    ]
    with transaction(conn):
        # Only a coach's allowed read of the client, for every scope used, passes; a user reviewing
        # themselves does not (authorise_read returns False for them).
        for scope in used:
            if not authorise_read(conn, coach_id, client_id, scope):
                raise NotFound
        _check_no_open_review(conn, coach_id, client_id, week)
        review_id = conn.execute(_INSERT_REVIEW, (client_id, coach_id, *row)).lastrowid
        for ref in refs:
            conn.execute(_INSERT_REF, (review_id, *ref))
        for scope in used:
            conn.execute(_INSERT_SCOPE, (review_id, scope))
    return review_id


def decide_review(
    conn: sqlite3.Connection,
    coach_id: str,
    review_id: int,
    decision: Decision,
    final: Mapping | None = None,
) -> None:
    """Approve, edit (with the coach's final text) or reject a pending review, with an audit row."""
    values.choice(decision, "decision", tuple(_OUTCOMES))
    if (decision == "edit") != (final is not None):
        raise values.StoreValueError("final", "is given with an edit and only then")
    edited = None if final is None else _json_text(final, "final")
    if not values.is_row_id(review_id):
        raise NotFound
    status, action = _OUTCOMES[decision]
    with transaction(conn):
        review = conn.execute(_REVIEW, (review_id,)).fetchone()
        if review is None or review["coach_id"] != coach_id or review["status"] != "PENDING_REVIEW":
            raise NotFound
        # A scope may have been revoked, or the relationship ended, while the review waited: every
        # scope the review used must still be shared (AC-22).
        authorise_read(conn, coach_id, review["client_id"], "nutrition")
        for used in conn.execute(_USED_SCOPES, (review_id,)).fetchall():
            authorise_read(conn, coach_id, review["client_id"], used["scope"])
        final_text = {"approve": review["draft"], "edit": edited, "reject": None}[decision]
        conn.execute(
            _DECIDE,
            (status, final_text, int(decision == "edit"), coach_id, values.utc_text(), review_id),
        )
        audit(
            conn,
            coach_id,
            action,
            "ai_reviews",
            subject_id=review["client_id"],
            resource_id=review_id,
        )


def is_pending(conn: sqlite3.Connection, coach_id: str, review_id: object) -> bool:
    """Return True while the coach's own review is pending (its status only, no client data)."""
    # The workflow asks after the store refused a decision: a review decided in another tab is no
    # longer pending, while one whose client revoked a scope still is (T9.16, code review round 1).
    if not values.is_row_id(review_id):
        return False
    row = conn.execute(_STATUS, (review_id, coach_id)).fetchone()
    return row is not None and row["status"] == "PENDING_REVIEW"


def discard_pending(conn: sqlite3.Connection, coach_id: str, thread_id: str) -> None:
    """Delete the coach's pending review of a run that failed after saving it, if there is one."""
    # The review was saved but its run cannot wait for the coach (its thread could not be
    # written); no one has seen or decided it, so it goes with its evidence and scopes, and the
    # week can be run again (T9.16, code review round 1). No audit row: nothing was decided.
    thread = values.text(thread_id, "thread_id")
    with transaction(conn):
        for row in conn.execute(_PENDING_OF_THREAD, (coach_id, thread)).fetchall():
            conn.execute(_DISCARD_REFS, (row["id"],))
            conn.execute(_DISCARD_SCOPES, (row["id"],))
            conn.execute(_DISCARD, (row["id"],))


def list_reviews(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return the reviews the actor may read about the subject (scope: nutrition, and the rest)."""
    # A coach reading a client gets the reviews they wrote about that client whose every scope is
    # still shared (audited by authorised_read); a coach reading their own gets the reviews they
    # wrote about every client who still shares each one's scopes (one audit row per client); a
    # gymer reading their own gets the approved reviews about them, without the model's draft.
    with authorised_read(conn, actor_id, subject_id, "nutrition", "ai_reviews"):
        if actor_id != subject_id:
            rows = conn.execute(_WRITTEN_ABOUT, (actor_id, subject_id)).fetchall()
        elif role_of(conn, actor_id) == "coach":
            rows = conn.execute(_WRITTEN_FOR_SHARED, (actor_id,)).fetchall()
            for client_id in dict.fromkeys(row["client_id"] for row in rows):
                audit(conn, actor_id, "read", "ai_reviews", subject_id=client_id)
        else:
            rows = conn.execute(_APPROVED_ABOUT, (subject_id,)).fetchall()
    return [_decoded(row) for row in rows]
