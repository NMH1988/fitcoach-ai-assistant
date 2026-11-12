"""In-app notifications (T9.29, D23): worked out from the store's rows, plus the reader's read mark.

No event is copied: a notification is read from the rows the store already holds, so it shows no
more than its reader may already see, and it goes when those rows go (a user's deletion takes the
other side's notifications about them with it, AC-34). A coach sees, for each of their
relationships, that the client connected (with the scopes shared at the start), each scope the
client started or stopped sharing later, and that the relationship ended; a gymer sees that they
are connected with their coach, each weekly review a coach approved about them (never a pending or
rejected one) and that a relationship ended. Both sides see "ended", as the store does not record
who ended it (owner's choice, 2026-11-06).

The store writes `accepted_at` and the first scopes' `granted_at` with separate clock reads, so a
scope granted within `config.NOTIFICATIONS_SAME_EVENT_SECONDS` after the code was accepted counts
as shared at the start and shows only inside "connected"; `end_relationship()` revokes the open
scopes with the end's own time, so a scope revoked at `ended_at` shows only inside "ended".

From T9.30, a coach also sees each question a client asked under a weekly review, and a gymer
each answer a coach wrote under an approved review about them, read by
`questions.list_question_events()` by the thread's own rule (T9.25): the coach while the
relationship is active and the client shares nutrition and every scope the review used; the gymer
under every approved review about them, a former coach's too. Each row is its own event (a
question and its answer are separate actions), so no same-event window applies to them.

From T9.34, a gymer also sees each list of suggested foods a coach saved about them (a former
coach's too, as with reviews): the coach's name and the time, never a food or an amount.

A notification holds its kind, its time, the other side's display name (`users.display_name_of()`,
not audited), the scope and the week; never a value, a metric, a review's text or a question's or
answer's text. Reading the relationship and review kinds is not audited (owner's choice,
2026-11-06): they come from the user's own relationship rows, which both sides see, and from the
approved reviews about a gymer, which are theirs to read. A coach's question notifications read a
client's thread, so they are audited (a `read` of `review_questions` per client), but only when
the caller passes `audited=True`, as the Notifications page does; the sidebar's count and the
toasts, which run on every page, do not (the middle way, owner's choice, 2026-11-08).

The read mark holds only the reader's own ID and a time ("read up to": when the page that was
marked had loaded the list, so nothing stored after it is marked read unseen). A notification is
unread when it happened at or after that time (`>=`): the store's times are to the second, so one
in the mark's own second shows as unread once more rather than being missed. Only the newest mark
is kept.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from src import config
from src.store import questions, users, values
from src.store.access import NotFound, role_of
from src.store.db import transaction

Kind = Literal[
    "connected",
    "scope_started",
    "scope_stopped",
    "ended",
    "review_approved",
    "question_asked",
    "question_answered",
    "suggestions_updated",
]

# The user's own relationships, either side, their status read as a value from ended_at (never a
# sharing filter, which only the open_shares view writes).
_RELATIONSHIPS = """
SELECT id, coach_id, client_id, accepted_at, ended_at FROM coach_clients
WHERE coach_id = ? OR client_id = ? ORDER BY id
"""
# Every consent of those relationships, open or revoked: the scope history both sides see.
_CONSENTS = """
SELECT consent.id, consent.relationship_id, consent.scope, consent.granted_at, consent.revoked_at
FROM consents AS consent
JOIN coach_clients AS relationship ON relationship.id = consent.relationship_id
WHERE relationship.coach_id = ? OR relationship.client_id = ? ORDER BY consent.id
"""
# The approved reviews about a gymer: who approved them, the week and when; never their text.
_APPROVED_ABOUT = """
SELECT id, coach_id, period_start, reviewed_at FROM ai_reviews
WHERE client_id = ? AND status = 'APPROVED' ORDER BY id
"""
# T9.34: each list of suggested foods a coach saved about a gymer: who saved it and when; never a
# food or an amount. A former coach's lists too, as an approved review of theirs is.
_SUGGESTIONS_ABOUT = """
SELECT id, coach_id, created_at FROM food_suggestion_lists WHERE client_id = ? ORDER BY id
"""
_LATEST_MARK = """
SELECT read_up_to FROM notification_reads WHERE user_id = ? ORDER BY id DESC LIMIT 1
"""
_ADD_MARK = "INSERT INTO notification_reads (user_id, read_up_to) VALUES (?, ?)"
_DROP_EARLIER_MARKS = "DELETE FROM notification_reads WHERE user_id = ? AND id <> ?"

# Within one second, the order a reader would expect: connected first, ended last.
_ORDER: dict[str, int] = {
    "connected": 0,
    "scope_started": 1,
    "scope_stopped": 2,
    "review_approved": 3,
    "question_asked": 4,
    "question_answered": 5,
    "suggestions_updated": 6,
    "ended": 7,
}


@dataclass(frozen=True)
class Notification:
    """One thing that changed for the reader: its kind, time, the other side, scope and week."""

    kind: Kind
    at: str
    other_name: str
    scopes: tuple[str, ...] = ()
    week: str | None = None
    unread: bool = True
    # Tells notifications apart within the session (each toast once): the kind, the row's ID and
    # its time; never shown, logged or put in a URL.
    key: tuple[str, int, str] = ("", 0, "")


def _now() -> datetime:
    """Return the current moment in UTC (tests replace it to move the clock)."""
    return datetime.now(UTC)


def _moment(text: str) -> datetime:
    """Return a stored UTC time as a datetime."""
    return datetime.fromisoformat(text)


def _granted_at_start(relationship: sqlite3.Row, consents: list[sqlite3.Row]) -> set[int]:
    """Return the IDs of the consents granted with the code: each scope's first, in the window."""
    # Only a scope's first consent can be the start's: one turned off and on again within the
    # window is a change of its own (code review round 1), so the coach is told it is shared again.
    window = timedelta(seconds=config.NOTIFICATIONS_SAME_EVENT_SECONDS)
    accepted = _moment(relationship["accepted_at"])
    first: dict[str, sqlite3.Row] = {}
    for consent in consents:  # in ID order, so the first written comes first
        first.setdefault(consent["scope"], consent)
    return {c["id"] for c in first.values() if _moment(c["granted_at"]) - accepted <= window}


def _relationship_events(
    relationship: sqlite3.Row, consents: list[sqlite3.Row], name: str, as_coach: bool
) -> list[Notification]:
    """Return one relationship's notifications for one side: connected, scope changes, ended."""
    at_start = _granted_at_start(relationship, consents)
    # A key holds the row's time too: SQLite may give a deleted row's ID to a new row, which must
    # not count as toasted already (code review round 1).
    found = [
        Notification(
            "connected",
            relationship["accepted_at"],
            name,
            scopes=tuple(c["scope"] for c in consents if c["id"] in at_start),
            key=("connected", relationship["id"], relationship["accepted_at"]),
        )
    ]
    if as_coach:
        # The scope changes are the client's, so only the coach is told of them.
        for consent in consents:
            if consent["id"] not in at_start:
                found.append(
                    Notification(
                        "scope_started",
                        consent["granted_at"],
                        name,
                        scopes=(consent["scope"],),
                        key=("scope_started", consent["id"], consent["granted_at"]),
                    )
                )
            revoked = consent["revoked_at"]
            if revoked is not None and revoked != relationship["ended_at"]:
                found.append(
                    Notification(
                        "scope_stopped",
                        revoked,
                        name,
                        scopes=(consent["scope"],),
                        key=("scope_stopped", consent["id"], revoked),
                    )
                )
    ended = relationship["ended_at"]
    if ended is not None:
        found.append(Notification("ended", ended, name, key=("ended", relationship["id"], ended)))
    return found


def _with_unread(found: list[Notification], mark: str | None) -> list[Notification]:
    """Return the notifications newest first, each marked unread when at or after the mark."""
    since = None if mark is None else _moment(mark)
    ordered = sorted(found, key=lambda n: (_moment(n.at), _ORDER[n.kind]), reverse=True)
    return [
        Notification(
            n.kind,
            n.at,
            n.other_name,
            n.scopes,
            n.week,
            since is None or _moment(n.at) >= since,
            n.key,
        )
        for n in ordered
    ]


def list_notifications(
    conn: sqlite3.Connection, user_id: str, *, audited: bool = False
) -> list[Notification]:
    """Return the user's own notifications, newest first, each marked read or unread."""
    user_id = values.user_id(user_id)
    # The thread read runs first, in its own transaction (a store read cannot open one inside
    # another); `audited` is the Notifications page's, so its coach's read leaves an audit row.
    thread_events = questions.list_question_events(conn, user_id, user_id, audited=audited)
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        names: dict[str, str] = {}

        def name_of(other_id: str) -> str:
            """Return the other side's display name, read once per user."""
            if other_id not in names:
                names[other_id] = users.display_name_of(conn, user_id, other_id)
            return names[other_id]

        relationships = conn.execute(_RELATIONSHIPS, (user_id, user_id)).fetchall()
        consents: dict[int, list[sqlite3.Row]] = {}
        for consent in conn.execute(_CONSENTS, (user_id, user_id)):
            consents.setdefault(consent["relationship_id"], []).append(consent)
        found: list[Notification] = []
        for relationship in relationships:
            as_coach = relationship["coach_id"] == user_id
            other = relationship["client_id"] if as_coach else relationship["coach_id"]
            found.extend(
                _relationship_events(
                    relationship, consents.get(relationship["id"], []), name_of(other), as_coach
                )
            )
        for review in conn.execute(_APPROVED_ABOUT, (user_id,)).fetchall():
            # A review is saved only within a relationship, and both go with a deletion, so the
            # coach's name is found; a review without one would be skipped, never shown unnamed.
            try:
                coach = name_of(review["coach_id"])
            except NotFound:
                continue
            found.append(
                Notification(
                    "review_approved",
                    review["reviewed_at"],
                    coach,
                    week=review["period_start"],
                    key=("review_approved", review["id"], review["reviewed_at"]),
                )
            )
        for event in thread_events:
            # A coach gets only their clients' questions, a gymer only their coaches' answers.
            as_coach = event["coach_id"] == user_id
            kind: Kind = "question_asked" if as_coach else "question_answered"
            # A side who deleted their data between the two reads takes the thread with them.
            try:
                other = name_of(event["client_id"] if as_coach else event["coach_id"])
            except NotFound:
                continue
            found.append(
                Notification(
                    kind,
                    event["created_at"],
                    other,
                    week=event["period_start"],
                    key=(kind, event["id"], event["created_at"]),
                )
            )
        for saved in conn.execute(_SUGGESTIONS_ABOUT, (user_id,)).fetchall():
            # Saved only within a relationship, and both go with a deletion (T9.34).
            try:
                coach = name_of(saved["coach_id"])
            except NotFound:
                continue
            found.append(
                Notification(
                    "suggestions_updated",
                    saved["created_at"],
                    coach,
                    key=("suggestions_updated", saved["id"], saved["created_at"]),
                )
            )
        mark = conn.execute(_LATEST_MARK, (user_id,)).fetchone()
    return _with_unread(found, None if mark is None else mark["read_up_to"])


def mark_all_read(conn: sqlite3.Connection, user_id: str, seen_at: datetime | None = None) -> None:
    """Mark as read what the reader saw: up to `seen_at` (when the list was loaded), or now."""
    # The page passes the time it loaded the list, so an event stored between that load and the
    # click is not marked read unseen (code review round 1); a time in the future counts as now.
    user_id = values.user_id(user_id)
    now = _now()
    read_up_to = values.utc_text(now if seen_at is None else min(seen_at, now))
    # One transaction: the new mark and the deletion of the earlier ones land together, or neither.
    with transaction(conn):
        if role_of(conn, user_id) is None:
            raise NotFound
        cursor = conn.execute(_ADD_MARK, (user_id, read_up_to))
        conn.execute(_DROP_EARLIER_MARKS, (user_id, cursor.lastrowid))
