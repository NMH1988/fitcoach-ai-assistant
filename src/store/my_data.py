"""Everything the store holds about a user: exported as JSON, or deleted (T9.6, AC-34).

The export holds the user's own rows in every table, the relationships and scopes they are part
of, the reviews they may read (a gymer's approved reviews about them without the model's draft, a
coach's own reviews of clients who still share nutrition) and the audit rows by or about them.
The delete removes the user's rows in every table, their relationships and scopes, the
reviews about them and those they wrote as a coach (with their evidence), the invitations and code
attempts, and the audit rows by or about them: the app is local and keeps no audit duty (the owner
may change this). It runs in one transaction with foreign keys on, and no reference cascades, so a
table this list forgets makes the delete fail instead of leaving rows behind. T9.16 adds the review
threads of its checkpointer.
"""

import json
import sqlite3

from src.store import values
from src.store.access import NotFound, role_of
from src.store.db import transaction

_USER = "SELECT * FROM users WHERE id = ?"
_PROFILES = "SELECT * FROM profile_entries WHERE user_id = ? ORDER BY id"
_WEIGHTS = "SELECT * FROM body_measurements WHERE user_id = ? ORDER BY id"
_TARGETS = "SELECT * FROM nutrition_targets WHERE user_id = ? ORDER BY id"
_MEALS = "SELECT * FROM meal_items WHERE user_id = ? ORDER BY id"
_SESSIONS = "SELECT * FROM workout_sessions WHERE user_id = ? ORDER BY id"
_SETS = """
SELECT exercise_set.* FROM exercise_sets AS exercise_set
JOIN workout_sessions AS session ON session.id = exercise_set.session_id
WHERE session.user_id = ? ORDER BY exercise_set.id
"""
_PREFERENCES = "SELECT * FROM preferences WHERE user_id = ? ORDER BY id"
_INVITATIONS = "SELECT * FROM invitations WHERE coach_id = ? ORDER BY id"
_ATTEMPTS = "SELECT * FROM invite_attempts WHERE user_id = ? ORDER BY day"
_RELATIONSHIPS = """
SELECT * FROM coach_clients WHERE coach_id = ? OR client_id = ? ORDER BY id
"""
_CONSENTS = """
SELECT consent.* FROM consents AS consent
JOIN coach_clients AS relationship ON relationship.id = consent.relationship_id
WHERE relationship.coach_id = ? OR relationship.client_id = ? ORDER BY consent.id
"""
# What each reads (reviews.list_reviews()): a gymer the approved reviews about them without the
# model's draft, a coach the reviews they wrote about clients who still share nutrition with them
# (owner's choices, 2026-10-27).
_APPROVED_ABOUT = """
SELECT id, client_id, coach_id, period_start, metrics, data_quality, NULL AS draft, final, status,
    edited_by_coach, model_version, created_at, reviewed_by, reviewed_at
FROM ai_reviews WHERE client_id = ? AND status = 'APPROVED' ORDER BY id
"""
_WRITTEN_FOR_SHARED = """
SELECT review.* FROM ai_reviews AS review
WHERE review.coach_id = ? AND EXISTS (
    SELECT 1
    FROM coach_clients AS relationship
    JOIN consents AS consent ON consent.relationship_id = relationship.id
    WHERE relationship.coach_id = review.coach_id AND relationship.client_id = review.client_id
      AND relationship.status = 'active'
      AND consent.scope = 'nutrition' AND consent.revoked_at IS NULL
)
ORDER BY review.id
"""
_EVIDENCE = """
SELECT ref.* FROM ai_evidence_refs AS ref
JOIN ai_reviews AS review ON review.id = ref.review_id
WHERE (review.client_id = ? AND review.status = 'APPROVED')
    OR (review.coach_id = ? AND EXISTS (
    SELECT 1
    FROM coach_clients AS relationship
    JOIN consents AS consent ON consent.relationship_id = relationship.id
    WHERE relationship.coach_id = review.coach_id AND relationship.client_id = review.client_id
      AND relationship.status = 'active'
      AND consent.scope = 'nutrition' AND consent.revoked_at IS NULL
))
ORDER BY ref.id
"""
_AUDIT = "SELECT * FROM audit_log WHERE actor_id = ? OR subject_id = ? ORDER BY id"

# The delete, children before parents.
_DELETE_EVIDENCE = """
DELETE FROM ai_evidence_refs
WHERE review_id IN (SELECT id FROM ai_reviews WHERE client_id = ? OR coach_id = ?)
"""
_DELETE_REVIEWS = "DELETE FROM ai_reviews WHERE client_id = ? OR coach_id = ?"
_DELETE_AUDIT = "DELETE FROM audit_log WHERE actor_id = ? OR subject_id = ?"
_DELETE_CONSENTS = """
DELETE FROM consents
WHERE relationship_id IN (SELECT id FROM coach_clients WHERE coach_id = ? OR client_id = ?)
"""
_DELETE_RELATIONSHIPS = "DELETE FROM coach_clients WHERE coach_id = ? OR client_id = ?"
_DELETE_INVITATIONS = "DELETE FROM invitations WHERE coach_id = ?"
_DELETE_ATTEMPTS = "DELETE FROM invite_attempts WHERE user_id = ?"
_DELETE_SETS = """
DELETE FROM exercise_sets
WHERE session_id IN (SELECT id FROM workout_sessions WHERE user_id = ?)
"""
_DELETE_SESSIONS = "DELETE FROM workout_sessions WHERE user_id = ?"
_DELETE_MEALS = "DELETE FROM meal_items WHERE user_id = ?"
_DELETE_TARGETS = "DELETE FROM nutrition_targets WHERE user_id = ?"
_DELETE_WEIGHTS = "DELETE FROM body_measurements WHERE user_id = ?"
_DELETE_PROFILES = "DELETE FROM profile_entries WHERE user_id = ?"
_DELETE_PREFERENCES = "DELETE FROM preferences WHERE user_id = ?"
_DELETE_USER = "DELETE FROM users WHERE id = ?"
_REVIEW_JSON = ("metrics", "data_quality", "draft", "final")


def _review(row: sqlite3.Row) -> dict:
    """Return a review row with its JSON fields decoded, so the export is one JSON document."""
    review = dict(row)
    for field in _REVIEW_JSON:
        if review[field] is not None:
            review[field] = json.loads(review[field])
    return review


def export_user_data(conn: sqlite3.Connection, user_id: str) -> str:
    """Return every row the store holds for the user as one JSON document."""
    user_id = values.user_id(user_id)
    one = (user_id,)
    both = (user_id, user_id)
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        document = {
            "user": dict(conn.execute(_USER, one).fetchone()),
            "profile_entries": [dict(r) for r in conn.execute(_PROFILES, one)],
            "body_measurements": [dict(r) for r in conn.execute(_WEIGHTS, one)],
            "nutrition_targets": [dict(r) for r in conn.execute(_TARGETS, one)],
            "meal_items": [dict(r) for r in conn.execute(_MEALS, one)],
            "workout_sessions": [dict(r) for r in conn.execute(_SESSIONS, one)],
            "exercise_sets": [dict(r) for r in conn.execute(_SETS, one)],
            "preferences": [dict(r) for r in conn.execute(_PREFERENCES, one)],
            "invitations": [dict(r) for r in conn.execute(_INVITATIONS, one)],
            "invite_attempts": [dict(r) for r in conn.execute(_ATTEMPTS, one)],
            "coach_clients": [dict(r) for r in conn.execute(_RELATIONSHIPS, both)],
            "consents": [dict(r) for r in conn.execute(_CONSENTS, both)],
            "ai_reviews": [
                *(_review(r) for r in conn.execute(_APPROVED_ABOUT, one)),
                *(_review(r) for r in conn.execute(_WRITTEN_FOR_SHARED, one)),
            ],
            "ai_evidence_refs": [dict(r) for r in conn.execute(_EVIDENCE, both)],
            "audit_log": [dict(r) for r in conn.execute(_AUDIT, both)],
        }
    return json.dumps(document, ensure_ascii=False, indent=2)


def delete_user_data(conn: sqlite3.Connection, user_id: str) -> None:
    """Delete the user and every row about them, in one transaction; NotFound if there is none."""
    user_id = values.user_id(user_id)
    one = (user_id,)
    both = (user_id, user_id)
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        conn.execute(_DELETE_EVIDENCE, both)
        conn.execute(_DELETE_REVIEWS, both)
        conn.execute(_DELETE_AUDIT, both)
        conn.execute(_DELETE_CONSENTS, both)
        conn.execute(_DELETE_RELATIONSHIPS, both)
        conn.execute(_DELETE_INVITATIONS, one)
        conn.execute(_DELETE_ATTEMPTS, one)
        conn.execute(_DELETE_SETS, one)
        conn.execute(_DELETE_SESSIONS, one)
        conn.execute(_DELETE_MEALS, one)
        conn.execute(_DELETE_TARGETS, one)
        conn.execute(_DELETE_WEIGHTS, one)
        conn.execute(_DELETE_PROFILES, one)
        conn.execute(_DELETE_PREFERENCES, one)
        conn.execute(_DELETE_USER, one)
