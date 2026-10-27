"""Weekly reviews in the store: saved as PENDING_REVIEW, then approved, edited or rejected (T9.6).

T9.16's workflow drafts a review and calls these functions; the checks on its content (schema,
citations, calorie floor, no diagnosis or training advice) are T9.16's. Here: a review is saved and
decided only by the client's coach, while the relationship is active and the client shares the
nutrition scope, so revoking it blocks a pending review (AC-22); every decision stores the reviewer
and the time and writes an audit row with no values (AC-29). A gymer reads only the approved
reviews about them, never the model's draft; a coach reads the reviews they wrote, only about
clients who still share nutrition with them (owner's choices, 2026-10-27).
"""

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from src import config
from src.store import values
from src.store.access import NotFound, audit, authorise_read, authorised_read, role_of
from src.store.db import transaction

Decision = Literal["approve", "edit", "reject"]
# The status and audit action each decision leads to.
_OUTCOMES: dict[str, tuple[str, str]] = {
    "approve": ("APPROVED", "review_approved"),
    "edit": ("APPROVED", "review_edited"),
    "reject": ("REJECTED", "review_rejected"),
}

_INSERT_REVIEW = """
INSERT INTO ai_reviews (
    client_id, coach_id, period_start, metrics, data_quality, draft,
    status, edited_by_coach, model_version, created_at
) VALUES (?, ?, ?, ?, ?, ?, 'PENDING_REVIEW', 0, ?, ?)
"""
_INSERT_REF = "INSERT INTO ai_evidence_refs (review_id, source_id, chunk_id) VALUES (?, ?, ?)"
_REVIEW = "SELECT client_id, coach_id, status, draft FROM ai_reviews WHERE id = ?"
_DECIDE = """
UPDATE ai_reviews
SET status = ?, final = ?, edited_by_coach = ?, reviewed_by = ?, reviewed_at = ?
WHERE id = ? AND status = 'PENDING_REVIEW'
"""
# The columns every list returns; evidence_refs as a JSON array built by SQLite. A gymer never
# gets the model's draft: an edited review's draft holds text the coach replaced (AC-29).
_APPROVED_ABOUT = """
SELECT review.id, review.client_id, review.coach_id, review.period_start, review.metrics,
    review.data_quality, NULL AS draft, review.final, review.status, review.edited_by_coach,
    review.model_version, review.created_at, review.reviewed_by, review.reviewed_at,
    (SELECT json_group_array(json_object('source_id', ref.source_id, 'chunk_id', ref.chunk_id))
     FROM ai_evidence_refs AS ref WHERE ref.review_id = review.id) AS evidence_refs
FROM ai_reviews AS review
WHERE review.client_id = ? AND review.status = 'APPROVED'
ORDER BY review.period_start, review.id
"""
# A coach's reviews of one client, read after access.authorise_read() allowed it.
_WRITTEN_ABOUT = """
SELECT review.id, review.client_id, review.coach_id, review.period_start, review.metrics,
    review.data_quality, review.draft, review.final, review.status, review.edited_by_coach,
    review.model_version, review.created_at, review.reviewed_by, review.reviewed_at,
    (SELECT json_group_array(json_object('source_id', ref.source_id, 'chunk_id', ref.chunk_id))
     FROM ai_evidence_refs AS ref WHERE ref.review_id = review.id) AS evidence_refs
FROM ai_reviews AS review
WHERE review.coach_id = ? AND review.client_id = ?
ORDER BY review.period_start, review.id
"""
# A coach's reviews of every client who still shares nutrition with them: the same rule as
# access.authorise_read(), so an ended relationship or a revoked scope hides the review (AC-22).
_WRITTEN_FOR_SHARED = """
SELECT review.id, review.client_id, review.coach_id, review.period_start, review.metrics,
    review.data_quality, review.draft, review.final, review.status, review.edited_by_coach,
    review.model_version, review.created_at, review.reviewed_by, review.reviewed_at,
    (SELECT json_group_array(json_object('source_id', ref.source_id, 'chunk_id', ref.chunk_id))
     FROM ai_evidence_refs AS ref WHERE ref.review_id = review.id) AS evidence_refs
FROM ai_reviews AS review
WHERE review.coach_id = ? AND EXISTS (
    SELECT 1 FROM open_shares AS share
    WHERE share.coach_id = review.coach_id AND share.client_id = review.client_id
      AND share.scope = 'nutrition'
)
ORDER BY review.period_start, review.id
"""
_JSON_FIELDS = ("metrics", "data_quality", "draft", "final", "evidence_refs")


def _json_text(value: object, field: str) -> str:
    """Return a mapping as JSON text within the size limit, or raise StoreValueError."""
    if not isinstance(value, Mapping):
        raise values.StoreValueError(field, "must be a mapping")
    try:
        # allow_nan=False: NaN and infinities are not JSON and SQLite's json_valid() refuses them.
        text = json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
    except TypeError, ValueError:
        raise values.StoreValueError(field, "must hold JSON values only") from None
    if len(text) > config.STORE_JSON_MAX_CHARS:
        raise values.StoreValueError(field, "is too long")
    return text


def _decoded(row: sqlite3.Row) -> dict:
    """Return a review row as a dict with its JSON fields decoded."""
    review = dict(row)
    for field in _JSON_FIELDS:
        if review[field] is not None:
            review[field] = json.loads(review[field])
    review["edited_by_coach"] = bool(review["edited_by_coach"])
    return review


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
) -> int:
    """Save a drafted review as PENDING_REVIEW with its evidence; return its ID."""
    row = (
        values.date_text(period_start, "period_start"),
        _json_text(metrics, "metrics"),
        _json_text(data_quality, "data_quality"),
        _json_text(draft, "draft"),
        values.text(model_version, "model_version"),
        values.utc_text(),
    )
    refs = [
        (values.text(source_id, "source_id"), values.text(chunk_id, "chunk_id"))
        for source_id, chunk_id in evidence_refs
    ]
    with transaction(conn):
        # Only a coach's allowed read of the client passes; a user reviewing themselves does not.
        if not authorise_read(conn, coach_id, client_id, "nutrition"):
            raise NotFound
        review_id = conn.execute(_INSERT_REVIEW, (client_id, coach_id, *row)).lastrowid
        for ref in refs:
            conn.execute(_INSERT_REF, (review_id, *ref))
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
    if isinstance(review_id, bool) or not isinstance(review_id, int):
        raise NotFound
    status, action = _OUTCOMES[decision]
    with transaction(conn):
        review = conn.execute(_REVIEW, (review_id,)).fetchone()
        if review is None or review["coach_id"] != coach_id or review["status"] != "PENDING_REVIEW":
            raise NotFound
        # The scope may have been revoked or the relationship ended while the review waited.
        authorise_read(conn, coach_id, review["client_id"], "nutrition")
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


def list_reviews(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return the reviews the actor may read about the subject (scope: nutrition)."""
    # A coach reading a client gets the reviews they wrote about that client (audited by
    # authorised_read); a coach reading their own gets the reviews they wrote about every client who
    # still shares nutrition with them (one audit row per client); a gymer reading their own gets
    # the approved reviews about them, without the model's draft.
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
