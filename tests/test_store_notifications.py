"""In-app notifications from the store's rows, and the reader's read mark (T9.29, D23, AC-43).

What each side sees (criterion 1), what a deletion does to the other side's list (criterion 2),
that nobody sees another user's notifications or read marks (criterion 3), and that only the
newest read mark is kept (criterion 4, the store's part). Times are seeded or the clock is fixed.
"""

import ast
import dataclasses
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src import config
from src.store import invitations, my_data, notifications, reviews, users
from src.store.access import NotFound
from src.store.values import StoreValueError, utc_text
from tests.store_world import no_threads

COACH, OTHER_COACH = "coach-n", "coach-other"
GYM, OTHER_GYM = "gym-n", "gym-other"
T0 = datetime(2026, 11, 2, 9, 0, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def _at(seconds: int) -> str:
    """Return the stored UTC text of T0 plus some seconds."""
    return utc_text(T0 + timedelta(seconds=seconds))


@pytest.fixture
def people(store_conn):
    """Create two coaches and two gymers with recognisable display names."""
    for user_id, role, name in (
        (COACH, "coach", "Coach Nia"),
        (OTHER_COACH, "coach", "Coach Ola"),
        (GYM, "gymer", "Gym Noor"),
        (OTHER_GYM, "gymer", "Gym Oskar"),
    ):
        users.create_user(store_conn, user_id, role, name)
    return store_conn


def _relationship(conn, coach: str, client: str, accepted: int, ended: int | None = None) -> int:
    """Insert a relationship with seeded times (seconds after T0); return its ID."""
    status, ended_at = ("active", None) if ended is None else ("ended", _at(ended))
    cursor = conn.execute(
        "INSERT INTO coach_clients (coach_id, client_id, status, accepted_at, ended_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (coach, client, status, _at(accepted), ended_at),
    )
    return cursor.lastrowid


def _consent(conn, relationship: int, scope: str, granted: int, revoked: int | None = None) -> None:
    """Insert a consent with seeded times (seconds after T0)."""
    conn.execute(
        "INSERT INTO consents (relationship_id, scope, granted_at, revoked_at) VALUES (?, ?, ?, ?)",
        (relationship, scope, _at(granted), None if revoked is None else _at(revoked)),
    )


def _seen(conn, user_id: str) -> list[tuple]:
    """Return the user's notifications as (kind, other side, scopes, week), newest first."""
    return [
        (n.kind, n.other_name, n.scopes, n.week)
        for n in notifications.list_notifications(conn, user_id)
    ]


def _review(conn, coach: str, client: str, monday: date, decision: str | None) -> int:
    """Save a made-up review and decide it as asked (None leaves it pending)."""
    found = reviews.save_review(
        conn,
        coach,
        client,
        period_start=monday,
        metrics={"logged_days": 3},
        data_quality={"logged_days": 3},
        draft={"observations": ["CANARY-REVIEW-TEXT"]},
        model_version="test-model",
    )
    if decision is not None:
        reviews.decide_review(conn, coach, found, decision)
    return found


# --- Criterion 1: what each side sees ------------------------------------------------------------


def test_the_scopes_granted_on_accept_show_only_inside_connected(people):
    """Two scopes granted with the code (one a second after accepted_at) are no "started" event."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "nutrition", granted=0)
    _consent(people, rel, "body", granted=1)
    assert _seen(people, COACH) == [("connected", "Gym Noor", ("nutrition", "body"), None)]
    assert _seen(people, GYM) == [("connected", "Coach Nia", ("nutrition", "body"), None)]


def test_the_same_event_window_is_the_config_s(people):
    """A scope granted just after the window is a change of its own; at its edge, the start."""
    window = config.NOTIFICATIONS_SAME_EVENT_SECONDS
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "nutrition", granted=window)
    _consent(people, rel, "body", granted=window + 1)
    assert _seen(people, COACH) == [
        ("scope_started", "Gym Noor", ("body",), None),
        ("connected", "Gym Noor", ("nutrition",), None),
    ]


def test_a_real_accept_with_two_scopes_shows_one_connected(people):
    """accept_invitation's own writes give the coach one "connected" with both scopes."""
    code = invitations.create_invitation(people, COACH).code
    invitations.accept_invitation(people, GYM, code, ["body", "nutrition"])
    assert _seen(people, COACH) == [("connected", "Gym Noor", ("nutrition", "body"), None)]


def test_a_scope_turned_on_or_off_later_is_told_to_the_coach_only(people):
    """After the start, each scope the client starts or stops sharing is the coach's to see."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "nutrition", granted=0, revoked=120)
    _consent(people, rel, "training", granted=60)
    assert _seen(people, COACH) == [
        ("scope_stopped", "Gym Noor", ("nutrition",), None),
        ("scope_started", "Gym Noor", ("training",), None),
        ("connected", "Gym Noor", ("nutrition",), None),
    ]
    assert _seen(people, GYM) == [("connected", "Coach Nia", ("nutrition",), None)]


def test_an_end_with_two_shared_scopes_shows_only_ended(people):
    """end_relationship revokes the scopes with its own time: they show only inside "ended"."""
    rel = users.start_relationship(people, COACH, GYM)
    for scope in ("nutrition", "body"):
        users.set_consent(people, GYM, rel, scope, True)
    users.end_relationship(people, COACH, rel)
    kinds = [kind for kind, *_ in _seen(people, COACH)]
    assert kinds == ["ended", "connected"]
    assert [kind for kind, *_ in _seen(people, GYM)] == ["ended", "connected"]


def test_a_scope_turned_off_and_on_within_the_window_is_told(people):
    """Code review round 1: only a scope's first consent is the start's; a re-grant is a change."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "nutrition", granted=0, revoked=2)
    _consent(people, rel, "nutrition", granted=4)
    assert _seen(people, COACH) == [
        ("scope_started", "Gym Noor", ("nutrition",), None),
        ("scope_stopped", "Gym Noor", ("nutrition",), None),
        ("connected", "Gym Noor", ("nutrition",), None),
    ]


def test_a_pair_that_connects_again_after_an_end_gets_new_events(people):
    """An ended relationship keeps its events; the same pair's new one has its own."""
    first = users.start_relationship(people, COACH, GYM)
    users.set_consent(people, GYM, first, "body", True)
    users.end_relationship(people, GYM, first)
    code = invitations.create_invitation(people, COACH).code
    invitations.accept_invitation(people, GYM, code, ["training"])
    kinds = [(kind, scopes) for kind, _, scopes, _ in _seen(people, COACH)]
    assert sorted(kinds) == sorted(
        [("connected", ("training",)), ("ended", ()), ("connected", ("body",))]
    )
    assert len({n.key for n in notifications.list_notifications(people, COACH)}) == 3


def test_a_scope_stopped_before_the_end_is_its_own_event(people):
    """A revoke a minute before the end is a "stopped sharing"; the end revokes the rest."""
    rel = _relationship(people, COACH, GYM, accepted=0, ended=600)
    _consent(people, rel, "nutrition", granted=0, revoked=540)
    _consent(people, rel, "body", granted=0, revoked=600)
    assert _seen(people, COACH) == [
        ("ended", "Gym Noor", (), None),
        ("scope_stopped", "Gym Noor", ("nutrition",), None),
        ("connected", "Gym Noor", ("nutrition", "body"), None),
    ]


def test_a_gymer_sees_only_the_approved_reviews_about_them(people):
    """An approved or edited review is told with its week; pending and rejected ones never."""
    rel = users.start_relationship(people, COACH, GYM)
    users.set_consent(people, GYM, rel, "nutrition", True)
    _review(people, COACH, GYM, date(2026, 10, 5), "approve")
    _review(people, COACH, GYM, date(2026, 10, 12), "reject")
    _review(people, COACH, GYM, date(2026, 10, 19), None)
    approved = [row for row in _seen(people, GYM) if row[0] == "review_approved"]
    assert approved == [("review_approved", "Coach Nia", (), "2026-10-05")]
    # The coach is told nothing of their own decisions.
    assert all(kind != "review_approved" for kind, *_ in _seen(people, COACH))


def test_a_former_coach_s_approved_review_keeps_their_name(people):
    """After the relationship ends, the review stays told under the coach who approved it."""
    rel = users.start_relationship(people, COACH, GYM)
    users.set_consent(people, GYM, rel, "nutrition", True)
    _review(people, COACH, GYM, date(2026, 10, 5), "approve")
    users.end_relationship(people, GYM, rel)
    assert ("review_approved", "Coach Nia", (), "2026-10-05") in _seen(people, GYM)


def test_a_notification_holds_no_value_or_review_text(people):
    """Only kind, time, the other side's name, scopes, week, unread and the session key."""
    rel = users.start_relationship(people, COACH, GYM)
    users.set_consent(people, GYM, rel, "nutrition", True)
    _review(people, COACH, GYM, date(2026, 10, 5), "approve")
    fields = {field.name for field in dataclasses.fields(notifications.Notification)}
    assert fields == {"kind", "at", "other_name", "scopes", "week", "unread", "key"}
    for found in notifications.list_notifications(people, GYM):
        assert "CANARY-REVIEW-TEXT" not in repr(found)


def test_the_list_is_newest_first(people):
    """Events from two relationships and a review come newest first."""
    _relationship(people, COACH, GYM, accepted=0, ended=100)
    _relationship(people, OTHER_COACH, GYM, accepted=200)
    times = [n.at for n in notifications.list_notifications(people, GYM)]
    assert times == sorted(times, reverse=True)
    assert _seen(people, GYM)[0] == ("connected", "Coach Ola", (), None)


# --- Criterion 3: nobody sees another user's notifications ---------------------------------------


def test_a_second_coach_or_gymer_sees_none_of_them(people):
    """Each user sees only the relationships they are a side of, ended ones included."""
    rel = _relationship(people, COACH, GYM, accepted=0, ended=100)
    _consent(people, rel, "body", granted=50, revoked=100)
    other = _relationship(people, OTHER_COACH, OTHER_GYM, accepted=10)
    _consent(people, other, "training", granted=70)
    assert {name for _, name, *_ in _seen(people, COACH)} == {"Gym Noor"}
    assert {name for _, name, *_ in _seen(people, GYM)} == {"Coach Nia"}
    assert {name for _, name, *_ in _seen(people, OTHER_COACH)} == {"Gym Oskar"}
    assert {name for _, name, *_ in _seen(people, OTHER_GYM)} == {"Coach Ola"}


def test_a_missing_user_or_a_bad_id_is_refused(people):
    """A user with no account gets NotFound; an ID that is not text a value error."""
    with pytest.raises(NotFound):
        notifications.list_notifications(people, "no-such-user")
    with pytest.raises(NotFound):
        notifications.mark_all_read(people, "no-such-user")
    with pytest.raises(StoreValueError):
        notifications.list_notifications(people, 5)


def test_a_user_with_nothing_has_an_empty_list(people):
    """A coach with no client has no notification."""
    assert notifications.list_notifications(people, OTHER_COACH) == []


# --- Criterion 4 (the store's part): the read mark -----------------------------------------------


def _clock(monkeypatch, seconds: int) -> None:
    """Fix the read mark's clock to T0 plus some seconds."""
    monkeypatch.setattr(notifications, "_now", lambda: T0 + timedelta(seconds=seconds))


def _unread(conn, user_id: str) -> list[str]:
    """Return the kinds of the user's unread notifications."""
    return [n.kind for n in notifications.list_notifications(conn, user_id) if n.unread]


def _marks(conn) -> list[tuple]:
    """Return every read mark as (user, time)."""
    return [tuple(r) for r in conn.execute("SELECT user_id, read_up_to FROM notification_reads")]


def test_everything_is_unread_until_marked_then_only_what_came_after(people, monkeypatch):
    """With no mark all is unread; after the mark only later events are."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "body", granted=60)
    assert _unread(people, COACH) == ["scope_started", "connected"]
    _clock(monkeypatch, 100)
    notifications.mark_all_read(people, COACH)
    assert _unread(people, COACH) == []
    _consent(people, rel, "training", granted=160)
    assert _unread(people, COACH) == ["scope_started"]


def test_an_event_in_the_mark_s_own_second_shows_unread_once_more(people, monkeypatch):
    """Times are to the second, so the mark compares with >=: nothing in its second is missed."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "body", granted=100)
    _clock(monkeypatch, 100)
    notifications.mark_all_read(people, COACH)
    assert _unread(people, COACH) == ["scope_started"]
    _clock(monkeypatch, 101)
    notifications.mark_all_read(people, COACH)
    assert _unread(people, COACH) == []


def test_marking_twice_keeps_one_mark_with_the_later_time(people, monkeypatch):
    """Only the newest mark is kept, holding the reader's ID and a time."""
    _clock(monkeypatch, 100)
    notifications.mark_all_read(people, COACH)
    _clock(monkeypatch, 200)
    notifications.mark_all_read(people, COACH)
    assert _marks(people) == [(COACH, _at(200))]
    columns = [row["name"] for row in people.execute("PRAGMA table_info(notification_reads)")]
    assert columns == ["id", "user_id", "read_up_to"]


def test_a_failed_second_mark_keeps_the_first(people, monkeypatch):
    """If dropping the earlier marks fails, the new mark is rolled back with it."""
    _clock(monkeypatch, 100)
    notifications.mark_all_read(people, COACH)
    monkeypatch.setattr(notifications, "_DROP_EARLIER_MARKS", "DELETE FROM no_such_table")
    _clock(monkeypatch, 200)
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        notifications.mark_all_read(people, COACH)
    assert _marks(people) == [(COACH, _at(100))]


def test_the_mark_covers_only_what_the_page_had_loaded(people, monkeypatch):
    """Code review round 1: an event stored after the page loaded stays unread after the click."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "body", granted=150)  # after the load at 100, before the click at 200
    _clock(monkeypatch, 200)
    notifications.mark_all_read(people, COACH, T0 + timedelta(seconds=100))
    assert _marks(people) == [(COACH, _at(100))]
    assert _unread(people, COACH) == ["scope_started"]


def test_a_load_time_in_the_future_counts_as_now(people, monkeypatch):
    """A mark never lies ahead of the clock, so no later event is read before it happens."""
    _clock(monkeypatch, 200)
    notifications.mark_all_read(people, COACH, T0 + timedelta(days=1))
    assert _marks(people) == [(COACH, _at(200))]


def test_a_read_mark_is_the_reader_s_alone(people, monkeypatch):
    """The gymer's mark changes nothing for the coach and is only in the gymer's export."""
    rel = _relationship(people, COACH, GYM, accepted=0)
    _consent(people, rel, "body", granted=0)
    _clock(monkeypatch, 100)
    notifications.mark_all_read(people, GYM)
    assert _unread(people, GYM) == []
    assert _unread(people, COACH) == ["connected"]
    coach_export = json.loads(my_data.export_user_data(people, COACH))
    gym_export = json.loads(my_data.export_user_data(people, GYM))
    assert coach_export["notification_reads"] == []
    assert [row["user_id"] for row in gym_export["notification_reads"]] == [GYM]
    assert _at(100) not in json.dumps(coach_export)


# --- Criterion 6: nothing about a notification goes to a model -----------------------------------


def _importers(root: Path) -> set[str]:
    """Return the modules under root that import the notifications module."""
    found = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [f"{node.module}.{alias.name}" for alias in node.names] + [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if "src.store.notifications" in names:
                found.add(path.relative_to(ROOT).as_posix())
    return found


def test_only_the_notification_views_read_the_notifications():
    """No module that builds a model's messages (src/ outside the store) reads a notification."""
    assert _importers(ROOT / "src") == set()
    assert _importers(ROOT / "views") == {"views/notifications.py", "views/tables.py"}


# --- Criterion 2: a deletion takes the other side's notifications with it ------------------------


def test_a_gymer_s_deletion_takes_the_coach_s_notifications_about_them(people, monkeypatch):
    """No "ended" and nothing left about the gymer; the coach's unread count still works."""
    rel = users.start_relationship(people, COACH, GYM)
    users.set_consent(people, GYM, rel, "body", True)
    oskar = _relationship(people, COACH, OTHER_GYM, accepted=0)
    # After Gym Oskar's event, so it is read; Gym Noor's events (the real clock) stay unread.
    _clock(monkeypatch, 1)
    notifications.mark_all_read(people, COACH)
    notifications.mark_all_read(people, GYM)
    my_data.delete_user_data(people, GYM, no_threads)
    seen = _seen(people, COACH)
    assert {name for _, name, *_ in seen} == {"Gym Oskar"}
    assert all(kind != "ended" for kind, *_ in seen)
    assert all(user != GYM for user, _ in _marks(people))
    assert _unread(people, COACH) == []
    # The count still works after the deletion: a new event is unread.
    _consent(people, oskar, "training", granted=10)
    assert _unread(people, COACH) == ["scope_started"]


def test_a_coach_s_deletion_takes_the_gymer_s_notifications_about_them(people, monkeypatch):
    """The gymer's list holds nothing about the deleted coach, reviews included; nothing raises."""
    rel = users.start_relationship(people, COACH, GYM)
    users.set_consent(people, GYM, rel, "nutrition", True)
    _review(people, COACH, GYM, date(2026, 10, 5), "approve")
    users.end_relationship(people, GYM, rel)
    _relationship(people, OTHER_COACH, GYM, accepted=0)
    _clock(monkeypatch, 0)
    notifications.mark_all_read(people, COACH)
    my_data.delete_user_data(people, COACH, no_threads)
    assert {name for _, name, *_ in _seen(people, GYM)} == {"Coach Ola"}
    assert all(user != COACH for user, _ in _marks(people))
    assert len(_unread(people, GYM)) == 1
