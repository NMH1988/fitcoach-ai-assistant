"""Invitations: a coach's single-use code, and a gymer accepting it (T9.12, D15, AC-20).

A coach creates a code: drawn with the `secrets` module, returned once and stored only as its
SHA-256 hash, valid for `config.INVITE_TTL_DAYS` days; the coach may cancel it while it is unused
(the row is deleted). The coach passes it on by hand; no email is sent. A gymer with no coach
enters it and chooses the scopes to share: a valid, unexpired, unused code starts an active
relationship with those scopes, in one transaction, and is marked used. A missing, cancelled, used
or expired code gets one refusal that does not say which. Every try counts against the gymer's
daily limit (`config.INVITE_MAX_ATTEMPTS`, a day in `config.TIME_ZONE`), counted in the store and
committed before the code is checked, so neither a reload nor a refused code resets it.
"""

import hashlib
import secrets
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from src import config
from src.store import users, values
from src.store.access import SCOPES, NotFound, role_of
from src.store.db import transaction

Refusal = Literal["not_valid", "limit", "has_coach"]

_ADD = """
INSERT INTO invitations (coach_id, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)
"""
_UNUSED = """
SELECT id, created_at, expires_at FROM invitations
WHERE coach_id = ? AND used_at IS NULL ORDER BY id
"""
_CANCEL = "DELETE FROM invitations WHERE id = ? AND coach_id = ? AND used_at IS NULL"
_BY_HASH = "SELECT id, coach_id, expires_at, used_at FROM invitations WHERE code_hash = ?"
_USE = "UPDATE invitations SET used_at = ? WHERE id = ? AND used_at IS NULL"
_ATTEMPTS = "SELECT count FROM invite_attempts WHERE user_id = ? AND day = ?"
_COUNT_ATTEMPT = """
INSERT INTO invite_attempts (user_id, day, count) VALUES (?, ?, 1)
ON CONFLICT (user_id, day) DO UPDATE SET count = count + 1
"""


class InvitationRefused(Exception):
    """A code that cannot be accepted: `reason` says only which of three fixed refusals it is."""

    def __init__(self, reason: Refusal) -> None:
        """Keep the reason; the message never holds the code."""
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class NewInvitation:
    """A code just created: shown once to the coach, then only its row (never the code) is kept."""

    id: int
    code: str
    expires_at: str


def _now() -> datetime:
    """Return the current moment in UTC (tests replace it to move the clock)."""
    return datetime.now(UTC)


def _today() -> date:
    """Return today's date in the app's time zone, the day attempts are counted in (D21)."""
    return _now().astimezone(ZoneInfo(config.TIME_ZONE)).date()


def _hash(code: str) -> str:
    """Return the SHA-256 hash of a normalised code, in hex: the only form the store keeps."""
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def normalise_code(text: object) -> str | None:
    """Return a typed code without spaces or hyphens, in capitals; None if it cannot be a code."""
    if not isinstance(text, str) or len(text) > config.INVITE_CODE_INPUT_MAX_CHARS:
        return None
    code = "".join(text.split()).replace("-", "").upper()
    if len(code) != config.INVITE_CODE_LENGTH:
        return None
    if any(character not in config.INVITE_CODE_ALPHABET for character in code):
        return None
    return code


def _shown(code: str) -> str:
    """Return a code in hyphenated groups, as the coach reads it out: ABCD-EFGH-JKLM."""
    size = config.INVITE_CODE_GROUP
    return "-".join(code[start : start + size] for start in range(0, len(code), size))


def create_invitation(conn: sqlite3.Connection, coach_id: str) -> NewInvitation:
    """Create a coach's code and return it once; the store keeps only its hash and expiry."""
    coach_id = values.user_id(coach_id)
    code = "".join(
        secrets.choice(config.INVITE_CODE_ALPHABET) for _ in range(config.INVITE_CODE_LENGTH)
    )
    now = _now()
    expires_at = values.utc_text(now + timedelta(days=config.INVITE_TTL_DAYS))
    with transaction(conn):
        if role_of(conn, coach_id) != "coach":
            raise NotFound
        # code_hash is UNIQUE: a repeated code (about one in 2**60 per pair) is refused, not shared.
        cursor = conn.execute(_ADD, (coach_id, _hash(code), values.utc_text(now), expires_at))
    return NewInvitation(cursor.lastrowid, _shown(code), expires_at)


def list_invitations(conn: sqlite3.Connection, coach_id: str) -> list[dict]:
    """Return the coach's own unused codes (never the code): created, expires, and if expired."""
    coach_id = values.user_id(coach_id)
    now = _now()
    with transaction(conn):
        if role_of(conn, coach_id) != "coach":
            raise NotFound
        rows = conn.execute(_UNUSED, (coach_id,)).fetchall()
    return [
        {**dict(row), "expired": datetime.fromisoformat(row["expires_at"]) <= now} for row in rows
    ]


def cancel_invitation(conn: sqlite3.Connection, coach_id: str, invitation_id: object) -> None:
    """Delete one of the coach's unused codes, so it can no longer be accepted; else NotFound."""
    if not values.is_row_id(invitation_id):
        raise NotFound
    with transaction(conn):
        if conn.execute(_CANCEL, (invitation_id, values.user_id(coach_id))).rowcount != 1:
            raise NotFound


def _count_attempt(conn: sqlite3.Connection, gymer_id: str) -> None:
    """Count one try for today, or refuse with "limit" once the day's tries are used up."""
    day = values.date_text(_today(), "day")
    with transaction(conn):
        if role_of(conn, gymer_id) != "gymer":
            raise NotFound
        row = conn.execute(_ATTEMPTS, (gymer_id, day)).fetchone()
        if row is not None and row["count"] >= config.INVITE_MAX_ATTEMPTS:
            raise InvitationRefused("limit")
        conn.execute(_COUNT_ATTEMPT, (gymer_id, day))


def accept_invitation(
    conn: sqlite3.Connection, gymer_id: str, code: object, scopes: Iterable[str]
) -> int:
    """Accept a code for the gymer, sharing the chosen scopes; return the new relationship's ID."""
    gymer_id = values.user_id(gymer_id)
    chosen = {values.choice(scope, "scope", SCOPES) for scope in scopes}
    # Committed on its own, before the code is checked: a refused code still counts.
    _count_attempt(conn, gymer_id)
    normalised = normalise_code(code)
    with transaction(conn):
        if users._has_coach(conn, gymer_id):
            raise InvitationRefused("has_coach")
        row = None
        if normalised is not None:
            row = conn.execute(_BY_HASH, (_hash(normalised),)).fetchone()
        # Missing (or cancelled), used and expired give the same refusal (AC-20).
        if (
            row is None
            or row["used_at"] is not None
            or datetime.fromisoformat(row["expires_at"]) <= _now()
        ):
            raise InvitationRefused("not_valid")
        conn.execute(_USE, (values.utc_text(_now()), row["id"]))
        relationship_id = users._open_relationship(conn, row["coach_id"], gymer_id)
        for scope in SCOPES:
            if scope in chosen:
                users._grant(conn, relationship_id, scope)
    return relationship_id
