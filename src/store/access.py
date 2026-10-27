"""Who may read whose data: the check every read of another user's data goes through (T9.6, D16).

A user always reads their own data. Another user's data is read only by a coach, of a gymer, while
their relationship is active and the gymer shares the scope the data belongs to: `body` (weight and
profile entries), `nutrition` (meals, targets and the coach's own reviews) or `training` (workouts).
Preferences have no scope and are never shared (owner's choices, 2026-10-27). Every other case (a
missing user, someone else's client, an ended relationship, a scope not shared, a gymer reading a
gymer) raises the same `NotFound`, so an answer never reveals whether a client exists. A coach's
read writes an audit row with no values, in the same transaction as the read.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal, get_args

from src.store import values
from src.store.db import transaction

Scope = Literal["nutrition", "training", "body"]
SCOPES: tuple[str, ...] = get_args(Scope)
Action = Literal["read", "review_approved", "review_edited", "review_rejected"]

_ROLE = "SELECT role FROM users WHERE id = ?"
_SHARED = """
SELECT 1
FROM coach_clients AS relationship
JOIN consents AS consent ON consent.relationship_id = relationship.id
WHERE relationship.coach_id = ? AND relationship.client_id = ?
  AND relationship.status = 'active'
  AND consent.scope = ? AND consent.revoked_at IS NULL
"""
_AUDIT = """
INSERT INTO audit_log (actor_id, subject_id, action, resource_type, resource_id, created_at)
VALUES (?, ?, ?, ?, ?, ?)
"""


class NotFound(LookupError):
    """Raised for a missing, foreign, ended or unshared resource, always with the same message."""

    def __init__(self) -> None:
        """Give every case the one fixed message."""
        super().__init__("not found")


def role_of(conn: sqlite3.Connection, user_id: object) -> str | None:
    """Return a user's role, or None when there is no such user."""
    try:
        user_id = values.user_id(user_id)
    except values.StoreValueError:
        return None
    row = conn.execute(_ROLE, (user_id,)).fetchone()
    return None if row is None else row["role"]


def authorise_read(
    conn: sqlite3.Connection, actor_id: object, subject_id: object, scope: Scope | None
) -> bool:
    """Return False for a user's own read and True for a coach's allowed read; else NotFound."""
    actor_role = role_of(conn, actor_id)
    if actor_role is None:
        raise NotFound
    if actor_id == subject_id:
        return False
    # The role is checked first: a gymer never reads another user, whatever the tables hold.
    if actor_role != "coach" or scope is None or role_of(conn, subject_id) != "gymer":
        raise NotFound
    if conn.execute(_SHARED, (actor_id, subject_id, scope)).fetchone() is None:
        raise NotFound
    return True


def audit(
    conn: sqlite3.Connection,
    actor_id: str,
    action: Action,
    resource_type: str,
    *,
    subject_id: str | None = None,
    resource_id: int | None = None,
) -> None:
    """Write one audit row: who did what to which kind of resource about whom, never a value."""
    conn.execute(
        _AUDIT,
        (actor_id, subject_id, action, resource_type, resource_id, values.utc_text()),
    )


@contextmanager
def authorised_read(
    conn: sqlite3.Connection,
    actor_id: object,
    subject_id: object,
    scope: Scope | None,
    resource_type: str,
) -> Iterator[None]:
    """Authorise a read for the block that runs it, and audit a coach's read, in one transaction."""
    # The caller runs its own constant query inside the block (tests/test_store_sql_scan.py).
    with transaction(conn):
        by_coach = authorise_read(conn, actor_id, subject_id, scope)
        yield
        if by_coach:
            audit(conn, actor_id, "read", resource_type, subject_id=subject_id)
