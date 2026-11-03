"""Accepting an invitation code for the pages, with a log line when it is refused (T9.12).

The store writes no log lines (T9.6), and `views/` writes none either (tests/test_observability.py),
so the refusal is logged here: the event and the reason only ("not_valid", "limit" or
"has_coach"), never the typed code, the user or a scope (.claude/rules/security-privacy.md).
"""

import logging
import sqlite3
from collections.abc import Iterable

from src.store import invitations

logger = logging.getLogger(__name__)


def accept_code(
    conn: sqlite3.Connection, gymer_id: str, typed: object, scopes: Iterable[str]
) -> int:
    """Accept a typed code for the gymer with the chosen scopes; log and re-raise a refusal."""
    try:
        return invitations.accept_invitation(conn, gymer_id, typed, scopes)
    except invitations.InvitationRefused as refused:
        logger.warning("invite_refused", extra={"reason": refused.reason})
        raise
