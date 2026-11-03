"""Accounts, coach-client relationships and the scopes a client shares (T9.6, T9.12; D14-D16).

The functions that change shared data take the acting user and check that the change is theirs
to make: a client turns their own scopes on or off, and either side ends a relationship. Two take
no acting user, so only their callers may decide when they run: `create_user()` (T9.5, at the
first sign-in) and `start_relationship()`, the low-level step behind an accepted invitation code
(`invitations.accept_invitation()` runs the same steps in its own transaction; it checks the two
roles and that the gymer has no coach yet, but not a code). A gymer has one coach at a time
(owner's choice, 2026-11-03, T9.12). `find_user()` checks no access and must get only the
signed-in user's own ID. `display_name_of()` is the one read of another user's data that does not
go through `access.authorised_read()`: it checks the relationship itself and is not audited (T9.12).
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
# A gymer's own relationships, their status read as a value (never a sharing filter, which only
# the open_shares view writes): a gymer with an active one has a coach already.
_CLIENT_STATUSES = "SELECT status FROM coach_clients WHERE client_id = ?"
_OWN_RELATIONSHIPS = """
SELECT id, coach_id, client_id, status, accepted_at, ended_at FROM coach_clients
WHERE coach_id = ? OR client_id = ? ORDER BY id
"""
_OWN_SHARES = """
SELECT coach_id, client_id, scope FROM open_shares WHERE coach_id = ? OR client_id = ?
"""
# The other side's name, only when a relationship (active or ended) joins the two users.
_RELATED_NAME = """
SELECT other.display_name FROM users AS other
WHERE other.id = ? AND EXISTS (
    SELECT 1 FROM coach_clients AS relationship
    WHERE (relationship.coach_id = ? AND relationship.client_id = other.id)
       OR (relationship.client_id = ? AND relationship.coach_id = other.id)
)
"""
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


def _has_coach(conn: sqlite3.Connection, client_id: str) -> bool:
    """Return True if the gymer has an active relationship (a coach) now."""
    rows = conn.execute(_CLIENT_STATUSES, (client_id,)).fetchall()
    return any(row["status"] == "active" for row in rows)


def _open_relationship(conn: sqlite3.Connection, coach_id: str, client_id: str) -> int:
    """Pair a coach and a gymer with no coach yet, inside the caller's transaction."""
    if role_of(conn, coach_id) != "coach" or role_of(conn, client_id) != "gymer":
        raise values.StoreValueError("relationship", "needs a coach and a gymer")
    if _has_coach(conn, client_id):
        # One coach at a time (owner's choice, 2026-11-03): the gymer ends the first one before.
        raise values.StoreValueError("relationship", "the gymer has a coach already")
    cursor = conn.execute(_INSERT_RELATIONSHIP, (coach_id, client_id, values.utc_text()))
    return cursor.lastrowid


def _grant(conn: sqlite3.Connection, relationship_id: int, scope: Scope) -> None:
    """Open a consent for a scope of a relationship, inside the caller's transaction."""
    scope = values.choice(scope, "scope", SCOPES)
    conn.execute(_GRANT, (relationship_id, scope, values.utc_text()))


def start_relationship(conn: sqlite3.Connection, coach_id: str, client_id: str) -> int:
    """Pair a coach and a gymer with no scope shared; only a valid code may lead here (T9.12)."""
    with transaction(conn):
        return _open_relationship(conn, coach_id, client_id)


def display_name_of(conn: sqlite3.Connection, actor_id: object, other_id: object) -> str:
    """Return the other side's display name in a relationship (active or ended); else NotFound."""
    # Both sides of a relationship see each other's name, so a gymer knows who sees their data and
    # a coach whom they coach (owner's choice, 2026-10-28). Not audited (owner's choice,
    # 2026-11-03): the name is part of the relationship, which both sides see in their exports.
    for value in (actor_id, other_id):
        try:
            values.user_id(value)
        except values.StoreValueError:
            raise NotFound from None
    row = conn.execute(_RELATED_NAME, (other_id, actor_id, actor_id)).fetchone()
    if row is None:
        raise NotFound
    return row["display_name"]


def list_relationships(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """Return the user's own relationships: the other side, its name, status, dates and scopes."""
    user_id = values.user_id(user_id)
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        rows = conn.execute(_OWN_RELATIONSHIPS, (user_id, user_id)).fetchall()
        shared: dict[tuple[str, str], set[str]] = {}
        for share in conn.execute(_OWN_SHARES, (user_id, user_id)):
            shared.setdefault((share["coach_id"], share["client_id"]), set()).add(share["scope"])
        found = []
        for row in rows:
            other = row["client_id"] if row["coach_id"] == user_id else row["coach_id"]
            # open_shares holds the pair's active relationship only; an ended one with the same
            # pair shares nothing.
            on = shared.get((row["coach_id"], row["client_id"]), set())
            found.append(
                {
                    "id": row["id"],
                    "other_id": other,
                    "other_name": display_name_of(conn, user_id, other),
                    "status": row["status"],
                    "accepted_at": row["accepted_at"],
                    "ended_at": row["ended_at"],
                    "scopes": tuple(s for s in SCOPES if row["status"] == "active" and s in on),
                }
            )
    return found


def _relationship(conn: sqlite3.Connection, relationship_id: object) -> sqlite3.Row:
    """Return an active relationship's row, or raise NotFound."""
    if not values.is_row_id(relationship_id):
        raise NotFound
    row = conn.execute(_RELATIONSHIP, (relationship_id,)).fetchone()
    if row is None or row["status"] != "active":
        raise NotFound
    return row


def _checked_choices(shared_by_scope: dict) -> dict[str, bool]:
    """Return the scope choices if every key is a scope and every value a real bool."""
    for scope, shared in shared_by_scope.items():
        values.choice(scope, "scope", SCOPES)
        # A form value or a model-written argument such as "False" must never share a scope.
        if not isinstance(shared, bool):
            raise values.StoreValueError("shared", "must be true or false")
    return shared_by_scope


def _set(conn: sqlite3.Connection, relationship_id: int, scope: str, shared: bool) -> None:
    """Open or revoke one scope's consent, inside the caller's transaction."""
    open_consent = conn.execute(_OPEN_CONSENT, (relationship_id, scope)).fetchone()
    if shared and open_consent is None:
        _grant(conn, relationship_id, scope)
    elif not shared and open_consent is not None:
        conn.execute(_REVOKE, (values.utc_text(), open_consent["id"]))


def set_consent(
    conn: sqlite3.Connection, client_id: str, relationship_id: int, scope: Scope, shared: bool
) -> None:
    """Let the client share a scope with their coach, or stop sharing it (the next read fails)."""
    set_scopes(conn, client_id, relationship_id, {scope: shared})


def set_scopes(
    conn: sqlite3.Connection, client_id: str, relationship_id: int, shared_by_scope: dict
) -> None:
    """Set several of the client's scopes at once, in one transaction (all of them or none)."""
    choices = _checked_choices(shared_by_scope)
    with transaction(conn):
        if _relationship(conn, relationship_id)["client_id"] != client_id:
            raise NotFound
        for scope, shared in choices.items():
            _set(conn, relationship_id, scope, shared)


def end_relationship(conn: sqlite3.Connection, actor_id: str, relationship_id: int) -> None:
    """End a relationship (either side may) and revoke every scope it shared."""
    with transaction(conn):
        row = _relationship(conn, relationship_id)
        if actor_id not in (row["coach_id"], row["client_id"]):
            raise NotFound
        now = values.utc_text()
        conn.execute(_REVOKE_ALL, (now, relationship_id))
        conn.execute(_END, (now, relationship_id))
