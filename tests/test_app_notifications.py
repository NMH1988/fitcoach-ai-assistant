"""UI tests for the in-app notifications (T9.29, AC-43): the bell, the page, the toasts.

Criteria 4 (the bell with the unread count as text, the list newest first, "Mark all as read",
each unread notification toasted once a session), 5 (no bell for a guest, demo mode, a store
error), 7 (German) and 8 (the My data intro names the read marks), on a seeded store.
"""

import ast
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from src import config, demo
from src.store import db, my_data, notifications, reviews, users
from tests.store_world import no_threads
from tests.test_app_account import PROFILE, USER_ID, signed_in, start, store_account, texts
from tests.test_app_my_data import (  # noqa: F401 (a fixture)
    STORE_UNAVAILABLE,
    demo_store_is_fresh,
    start_demo,
)
from tests.test_app_sharing import open_page
from views import navigation
from views import notifications as view

pytestmark = pytest.mark.usefixtures("no_env_key")

ALEX, BO, DEE = "gym-alex", "gym-bo", "gym-dee"
KAI = "coach-kai"


def _relationship(conn, coach: str, client: str, accepted: str, ended: str | None = None) -> int:
    """Insert a relationship with seeded UTC times; return its ID."""
    status = "active" if ended is None else "ended"
    cursor = conn.execute(
        "INSERT INTO coach_clients (coach_id, client_id, status, accepted_at, ended_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (coach, client, status, accepted, ended),
    )
    return cursor.lastrowid


def _consent(conn, rel: int, scope: str, granted: str, revoked: str | None = None) -> None:
    """Insert a consent with seeded UTC times."""
    conn.execute(
        "INSERT INTO consents (relationship_id, scope, granted_at, revoked_at) VALUES (?, ?, ?, ?)",
        (rel, scope, granted, revoked),
    )


@pytest.fixture
def coach_world():
    """Store the canary coach with Alex (connected, then training) and Bo (ended); Dee is Kai's."""
    store_account("coach", name="Coach Sam")
    with db.connect() as conn:
        for user_id, name in ((ALEX, "Alex"), (BO, "Bo"), (DEE, "Dee")):
            users.create_user(conn, user_id, "gymer", name)
        users.create_user(conn, KAI, "coach", "Coach Kai")
        alex = _relationship(conn, USER_ID, ALEX, "2026-11-01T08:00:00+00:00")
        _consent(conn, alex, "nutrition", "2026-11-01T08:00:00+00:00")
        _consent(conn, alex, "body", "2026-11-01T08:00:01+00:00")
        _consent(conn, alex, "training", "2026-11-02T10:00:00+00:00")
        bo = _relationship(
            conn, USER_ID, BO, "2026-11-03T09:00:00+00:00", "2026-11-04T12:00:00+00:00"
        )
        _consent(conn, bo, "body", "2026-11-03T09:00:00+00:00", "2026-11-04T12:00:00+00:00")
        dee = _relationship(conn, KAI, DEE, "2026-11-05T09:00:00+00:00")
        _consent(conn, dee, "training", "2026-11-05T09:00:00+00:00")


# The coach's list, newest first, as the page writes it (Berlin time).
COACH_LINES = [
    "2026-11-04 13:00 · Your relationship with Bo ended.",
    "2026-11-03 10:00 · Bo connected and shares: Body.",
    "2026-11-02 11:00 · Alex started sharing Training.",
    "2026-11-01 09:00 · Alex connected and shares: Nutrition, Body.",
]


def _signed_in(monkeypatch, language: str = "en"):
    """Run the app as the canary user, on their home page."""
    return start(monkeypatch, user=signed_in(), language=language)


def _bell(at) -> list[str]:
    """Return the labels of the sidebar's links to the Notifications page."""
    return [
        link.proto.label
        for link in at.sidebar.get("page_link")
        if link.proto.label.startswith(("Notifications", "Benachrichtigungen"))
    ]


def _lines(at) -> list[str]:
    """Return the Notifications page's Markdown lines that hold a notification."""
    return [str(item.value) for item in at.main.markdown if " · " in str(item.value)]


def _toasts(at) -> list[str]:
    """Return the text of this run's toasts."""
    return [str(item.value) for item in at.toast]


def test_a_coach_s_sidebar_shows_the_bell_with_the_unread_count(monkeypatch, coach_world):
    """Criterion 4: the bell's text says how many are unread, on any page."""
    at = _signed_in(monkeypatch)
    assert _bell(at) == ["Notifications · 4 unread"]
    assert navigation.NOTIFICATIONS in navigation.PAGES_BY_ROLE["coach"]


def test_the_coach_s_page_lists_them_newest_first_marked_new(monkeypatch, coach_world):
    """Criterion 4: newest first, each unread one marked "New" in words; never Kai's client Dee."""
    at = open_page(_signed_in(monkeypatch), navigation.NOTIFICATIONS)
    lines = _lines(at)
    assert [line.split("**New** · ", 1)[1] for line in lines] == COACH_LINES
    assert "Dee" not in texts(at)


def test_mark_all_as_read_clears_the_count_and_keeps_one_mark(monkeypatch, coach_world):
    """Criterion 4: the button marks all as read; the bell drawn in the same run says 0."""
    at = open_page(_signed_in(monkeypatch), navigation.NOTIFICATIONS)
    next(b for b in at.button if b.label == "Mark all as read").click().run(timeout=30)
    assert _bell(at) == ["Notifications · 0 unread"]
    assert _lines(at) == COACH_LINES
    with db.connect() as conn:
        marks = conn.execute("SELECT user_id FROM notification_reads").fetchall()
    assert [row["user_id"] for row in marks] == [USER_ID]


def test_unread_notifications_are_toasted_once_a_session_at_most_three(monkeypatch, coach_world):
    """Criterion 4: the first run toasts three and one summary; the next run toasts nothing."""
    shown = config.NOTIFICATIONS_MAX_TOASTS
    assert shown == 3
    at = _signed_in(monkeypatch)
    toasts = _toasts(at)
    assert toasts[:shown] == [line.split(" · ", 1)[1] for line in COACH_LINES[:shown]]
    assert toasts[shown:] == ["Unread notifications not shown here: 1. See Notifications."]
    at.run(timeout=30)
    assert _toasts(at) == []


def test_a_new_notification_is_toasted_on_the_next_run(monkeypatch, coach_world):
    """Criterion 4: no real time; an event stored meanwhile shows as a toast on the next run."""
    at = _signed_in(monkeypatch)
    with db.connect() as conn:
        users.end_relationship(conn, USER_ID, 1)  # Alex's relationship
    at.run(timeout=30)
    assert _toasts(at) == ["Your relationship with Alex ended."]
    assert _bell(at) == ["Notifications · 5 unread"]


def test_a_new_connection_on_a_reused_row_id_is_toasted(monkeypatch, coach_world):
    """Code review round 1: a deleted gymer's relationship ID given to a new one still toasts."""
    with db.connect() as conn:
        users.create_user(conn, "gym-cy", "gymer", "Cy")
        users.create_user(conn, "gym-eve", "gymer", "Eve")
        # The newest relationship row, at a fixed past time, so Eve's (now) never shares its key.
        cy = _relationship(conn, USER_ID, "gym-cy", "2026-11-05T10:00:00+00:00")
    at = _signed_in(monkeypatch)
    assert "Cy connected and shares nothing yet." in _toasts(at)
    with db.connect() as conn:
        my_data.delete_user_data(conn, "gym-cy", no_threads)
        reused = users.start_relationship(conn, USER_ID, "gym-eve")
    assert reused == cy  # SQLite gave Eve's relationship Cy's old ID
    at.run(timeout=30)
    assert _toasts(at) == ["Eve connected and shares nothing yet."]


def test_the_page_shows_at_most_the_configured_number(monkeypatch, coach_world):
    """Criterion 4: the page lists the newest NOTIFICATIONS_MAX_SHOWN; the bell counts them all."""
    monkeypatch.setattr(config, "NOTIFICATIONS_MAX_SHOWN", 2)
    at = open_page(_signed_in(monkeypatch), navigation.NOTIFICATIONS)
    assert [line.split("**New** · ", 1)[1] for line in _lines(at)] == COACH_LINES[:2]
    assert _bell(at) == ["Notifications · 4 unread"]


@pytest.fixture
def gymer_world():
    """Store the canary gymer, connected with Coach Kai, with reviews of every status."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, KAI, "coach", "Coach Kai")
        rel = _relationship(conn, KAI, USER_ID, "2026-11-01T08:00:00+00:00")
        _consent(conn, rel, "nutrition", "2026-11-01T08:00:00+00:00")
        for monday, decision in (
            (date(2026, 10, 5), "approve"),
            (date(2026, 10, 12), "reject"),
            (date(2026, 10, 19), None),
        ):
            found = reviews.save_review(
                conn,
                KAI,
                USER_ID,
                period_start=monday,
                metrics={"logged_days": 3},
                data_quality={"logged_days": 3},
                draft={"observations": ["CANARY-REVIEW-TEXT"]},
                model_version="test-model",
            )
            if decision is not None:
                reviews.decide_review(conn, KAI, found, decision)


def test_a_gymer_sees_the_connection_and_only_the_approved_review(monkeypatch, gymer_world):
    """Criterion 1 in the UI: the approved review's week, never a rejected or pending one."""
    at = open_page(_signed_in(monkeypatch), navigation.NOTIFICATIONS)
    lines = [line.split(" · ", 2)[-1] for line in _lines(at)]
    assert lines == [
        "Coach Kai approved your weekly review for the week of 2026-10-05.",
        "You are connected with Coach Kai.",
    ]
    assert "CANARY-REVIEW-TEXT" not in texts(at)
    assert _bell(at) == ["Notifications · 2 unread"]


def test_a_guest_has_no_bell_and_no_page(monkeypatch):
    """Criterion 5: a guest (no [auth]) sees no bell, and the page is not registered."""
    at = start(monkeypatch, auth=False)
    assert _bell(at) == []
    assert navigation.NOTIFICATIONS not in navigation.PAGES_BY_ROLE[None]
    assert _toasts(at) == []


def test_a_store_error_leaves_the_page_working_without_the_bell(monkeypatch, coach_world):
    """Criterion 5: one fixed message, never the error's text; the rest of the page works."""

    def failing(conn, user_id, **kwargs):
        """Fail as a broken store file does."""
        raise sqlite3.OperationalError("CANARY C:/private/fitcoach.sqlite3 is locked")

    monkeypatch.setattr(notifications, "list_notifications", failing)
    at = _signed_in(monkeypatch)
    assert _bell(at) == []
    assert "Notifications could not be loaded just now." in texts(at)
    assert "CANARY" not in texts(at)
    assert len(at.tabs) == 4  # the coach's chat page still draws
    at = open_page(at, navigation.NOTIFICATIONS)
    assert "CANARY" not in texts(at) + " ".join(str(e.value) for e in at.error)
    assert [str(e.value) for e in at.error] == ["Notifications could not be loaded just now."]


def test_a_failed_mark_all_as_read_shows_the_fixed_message_once(monkeypatch, coach_world):
    """T9.11: a mark the store refuses shows the fixed message once; all stay unread."""

    def failing(conn, user_id, loaded_at):
        """Fail as a locked store file does."""
        raise sqlite3.OperationalError("CANARY C:/private/fitcoach.sqlite3 is locked")

    at = open_page(_signed_in(monkeypatch), navigation.NOTIFICATIONS)
    monkeypatch.setattr(notifications, "mark_all_read", failing)
    next(b for b in at.button if b.label == "Mark all as read").click().run(timeout=30)
    assert [str(e.value) for e in at.error] == [STORE_UNAVAILABLE]
    assert "CANARY" not in texts(at)
    assert _bell(at) == ["Notifications · 4 unread"]
    assert [line.split("**New** · ", 1)[1] for line in _lines(at)] == COACH_LINES
    at.run(timeout=30)
    assert [str(e.value) for e in at.error] == []
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM notification_reads").fetchone()[0] == 0


def test_demo_users_have_their_notifications(monkeypatch, demo_store_is_fresh):  # noqa: F811
    """Criterion 5: the demo coach sees Sam's connection from the synthetic seed."""
    at = start_demo(monkeypatch)
    at.selectbox(key="demo_user_start").set_value(demo.COACH.id).run(timeout=30)
    assert _bell(at) == ["Notifications · 1 unread"]
    at = open_page(at, navigation.NOTIFICATIONS)
    assert any(
        "Demo gymer Sam connected and shares: Body, Nutrition." in line for line in _lines(at)
    )


def test_the_bell_page_and_toasts_in_german(monkeypatch, coach_world):
    """Criterion 7: every notification text in German."""
    at = _signed_in(monkeypatch, language="de")
    assert _bell(at) == ["Benachrichtigungen · 4 ungelesen"]
    summary = "Hier nicht gezeigte ungelesene Benachrichtigungen: 1. Siehe Benachrichtigungen."
    assert summary in _toasts(at)
    at = open_page(at, navigation.NOTIFICATIONS)
    lines = [line.split("**Neu** · ", 1)[1] for line in _lines(at)]
    assert lines == [
        "2026-11-04 13:00 · Ihre Verbindung mit Bo ist beendet.",
        "2026-11-03 10:00 · Bo hat sich verbunden und teilt: Körper.",
        "2026-11-02 11:00 · Alex teilt jetzt Training.",
        "2026-11-01 09:00 · Alex hat sich verbunden und teilt: Ernährung, Körper.",
    ]
    assert [b.label for b in at.button if b.label == "Alle als gelesen markieren"]


@pytest.mark.parametrize(
    ("role", "language", "named"),
    [
        ("coach", "en", "your notification read mark"),
        ("gymer", "en", "your notification read mark"),
        ("coach", "de", "Ihre Lesemarkierung der Benachrichtigungen"),
        ("gymer", "de", "Ihre Lesemarkierung der Benachrichtigungen"),
    ],
)
def test_the_my_data_intro_names_the_read_mark(monkeypatch, role, language, named):
    """Criterion 8: both roles' My data intro says the read mark is stored, in both languages."""
    store_account(role, profile=PROFILE if role == "gymer" else None)
    at = open_page(_signed_in(monkeypatch, language), navigation.MY_DATA)
    assert named in texts(at)


def test_the_toast_state_stays_in_the_session_and_no_id_reaches_a_url():
    """Compliance run 1's build notes: the view uses no shared cache and no query parameter."""
    tree = ast.parse(Path(view.__file__).read_text(encoding="utf-8"))
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not used & {"cache_data", "cache_resource", "query_params", "experimental_set_query"}
    assert "session_state" in used
