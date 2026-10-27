"""Accounts, coach-client relationships and the scopes a client shares (T9.6; D14-D16).

The functions that change shared data take the acting user and check that the change is theirs
to make: a client turns their own scopes on or off, and either side ends a relationship. Two take
no acting user, so only their callers may decide when they run: `create_user()` (T9.5, at the
first sign-in) and `start_relationship()`, the low-level step T9.12 runs once a valid invitation
code is accepted (it checks the two roles but not the code). `find_user()` checks no access and
must get only the signed-in user's own ID.
"""

import sqlite3
from typing import Literal, get_args

from src.store import values
from src.store.access import SCOPES, NotFound, Scope, role_of
from src.store.db import transaction

Role = Literal["coach", "gymer"]
ROLES: tuple[str, ...] = get_args(Role)

_INSERT_USER = "INSERT INTO users (id, role, display_name, created_at) VALUES (?, ?, ?, ?)"
_USER = "SELECT id, role, display_name, created_at FROM users WHERE id = ?"
_INSERT_RELATIONSHIP = """
INSERT INTO coach_clients (coach_id, client_id, status, accepted_at)
VALUES (?, ?, 'active', ?)
"""
_RELATIONSHIP = "SELECT coach_id, client_id, status FROM coach_clients WHERE id = ?"
_OPEN_CONSENT = """
SELECT id FROM consents WHERE relationship_id = ? AND scope = ? AND revoked_at IS NULL
"""
_GRANT = "INSERT INTO consents (relationship_id, scope, granted_at) VALUES (?, ?, ?)"
_REVOKE = "UPDATE consents SET revoked_at = ? WHERE id = ?"
_REVOKE_ALL = "UPDATE consents SET revoked_at = ? WHERE relationship_id = ? AND revoked_at IS NULL"
_END = "UPDATE coach_clients SET status = 'ended', ended_at = ? WHERE id = ?"


def create_user(conn: sqlite3.Connection, user_id: str, role: Role, display_name: str) -> None:
    """Add an account with its one role (chosen once at the first sign-in, D14)."""
    row = (
        values.user_id(user_id),
        values.choice(role, "role", ROLES),
        values.text(display_name, "display_name"),
        values.utc_text(),
    )
    with transaction(conn):
        conn.execute(_INSERT_USER, row)


def find_user(conn: sqlite3.Connection, user_id: str) -> dict | None:
    """Return an account by ID; pass only the signed-in user's own ID (it checks no access)."""
    row = conn.execute(_USER, (values.user_id(user_id),)).fetchone()
    return None if row is None else dict(row)


def start_relationship(conn: sqlite3.Connection, coach_id: str, client_id: str) -> int:
    """Pair a coach and a gymer with no scope shared; only a valid code may lead here (T9.12)."""
    with transaction(conn):
        if role_of(conn, coach_id) != "coach" or role_of(conn, client_id) != "gymer":
            raise values.StoreValueError("relationship", "needs a coach and a gymer")
        cursor = conn.execute(_INSERT_RELATIONSHIP, (coach_id, client_id, values.utc_text()))
    return cursor.lastrowid


def _relationship(conn: sqlite3.Connection, relationship_id: object) -> sqlite3.Row:
    """Return an active relationship's row, or raise NotFound."""
    if not values.is_row_id(relationship_id):
        raise NotFound
    row = conn.execute(_RELATIONSHIP, (relationship_id,)).fetchone()
    if row is None or row["status"] != "active":
        raise NotFound
    return row


def set_consent(
    conn: sqlite3.Connection, client_id: str, relationship_id: int, scope: Scope, shared: bool
) -> None:
    """Let the client share a scope with their coach, or stop sharing it (the next read fails)."""
    values.choice(scope, "scope", SCOPES)
    # A form value or a model-written argument such as "False" must never share a scope.
    if not isinstance(shared, bool):
        raise values.StoreValueError("shared", "must be true or false")
    with transaction(conn):
        if _relationship(conn, relationship_id)["client_id"] != client_id:
            raise NotFound
        open_consent = conn.execute(_OPEN_CONSENT, (relationship_id, scope)).fetchone()
        if shared and open_consent is None:
            conn.execute(_GRANT, (relationship_id, scope, values.utc_text()))
        elif not shared and open_consent is not None:
            conn.execute(_REVOKE, (values.utc_text(), open_consent["id"]))


def end_relationship(conn: sqlite3.Connection, actor_id: str, relationship_id: int) -> None:
    """End a relationship (either side may) and revoke every scope it shared."""
    with transaction(conn):
        row = _relationship(conn, relationship_id)
        if actor_id not in (row["coach_id"], row["client_id"]):
            raise NotFound
        now = values.utc_text()
        conn.execute(_REVOKE_ALL, (now, relationship_id))
        conn.execute(_END, (now, relationship_id))
