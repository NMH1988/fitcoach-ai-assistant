"""The dashboards' week read scope by scope through the store's checks (T9.15, AC-21, AC-22)."""

from datetime import date, timedelta

import pytest

from src import dashboard, i18n
from src.store import records, reviews, users
from src.store.access import NotFound
from tests import store_world as world

MONDAY = world.DAY  # 2026-10-26, the day every world record is on


@pytest.fixture
def store(store_conn):
    """Return a store holding the made-up world, and its relationship IDs."""
    return store_conn, world.build(store_conn)


def _audit_rows(conn) -> list[tuple]:
    """Return every audit row as (actor, subject, action, resource type)."""
    rows = conn.execute("SELECT actor_id, subject_id, action, resource_type FROM audit_log")
    return [tuple(row) for row in rows]


def _review(conn, client: str, monday: date, decision: str | None = None) -> int:
    """Save a made-up review by coach A about a client, decided or left pending."""
    found = reviews.save_review(
        conn,
        world.COACH_A,
        client,
        period_start=monday,
        metrics={"logged_days": 1},
        data_quality={"logged_days": 1},
        draft={"observations": ["Made-up observation."]},
        model_version="test-model",
    )
    if decision is not None:
        reviews.decide_review(conn, world.COACH_A, found, decision)
    return found


def test_a_coach_reads_every_scope_a_client_shares(store):
    """A client sharing all three scopes shows nutrition, body, training and the reviews."""
    conn, _ = store
    week = dashboard.client_week(conn, world.COACH_A, world.SHARED, MONDAY)
    assert week.shared == {"nutrition", "body", "training"}
    assert week.nutrition.logged_days == 1
    assert week.nutrition.target is not None
    assert dashboard.latest_weight(week) == (world.DAY, world.WEIGHT)
    assert week.training.sessions == 1
    assert dict(week.volume_by_day)[world.DAY] == 1000.0
    assert week.weight_trend == ((world.DAY, world.WEIGHT),)
    assert week.reviews == ()


def test_a_client_sharing_nothing_shows_nothing_and_is_not_read(store):
    """No scope shared: nothing is read (no audit row) and nothing passes as "not logged"."""
    conn, _ = store
    before = _audit_rows(conn)
    week = dashboard.client_week(conn, world.COACH_A, world.UNSHARED, MONDAY)
    assert week.shared == frozenset()
    assert week.training is None and week.volume_by_day is None
    assert week.weight_trend is None and week.reviews is None
    assert week.nutrition.logged_days == 0 and week.nutrition.target is None
    assert _audit_rows(conn) == before


def test_each_scope_shared_is_read_and_audited_alone(store):
    """Only training shared: training is read with one audit row, and nothing else."""
    conn, relationships = store
    users.set_consent(conn, world.UNSHARED, relationships[world.UNSHARED], "training", True)
    before = len(_audit_rows(conn))
    week = dashboard.client_week(conn, world.COACH_A, world.UNSHARED, MONDAY)
    assert week.shared == {"training"}
    assert week.training.sessions == 1
    assert week.weight_trend is None and week.nutrition.target is None
    assert _audit_rows(conn)[before:] == [
        (world.COACH_A, world.UNSHARED, "read", "workout_sessions")
    ]


@pytest.mark.parametrize(
    ("coach", "client"),
    [
        (world.COACH_A, world.ENDED),  # the relationship ended
        (world.COACH_A, world.OTHERS),  # another coach's client
        (world.COACH_A, world.MISSING),  # no such user
        (world.COACH_A, world.COACH_B),  # a coach, not a client
        (world.SHARED, world.COACH_A),  # a gymer reading their own coach
        (world.SHARED, world.SHARED),  # a gymer through the coach's function
        (world.COACH_A, 42),  # not even an ID
    ],
)
def test_anyone_but_an_active_client_is_not_found(store, coach, client):
    """AC-21: the same NotFound for an ended, foreign, missing or wrong-role reader or subject."""
    conn, _ = store
    before = _audit_rows(conn)
    with pytest.raises(NotFound):
        dashboard.client_week(conn, coach, client, MONDAY)
    assert _audit_rows(conn) == before


def test_a_scope_revoked_while_reading_shows_as_not_shared(store, monkeypatch):
    """AC-22: a scope revoked between the relationship's read and the scope's is not shared."""
    conn, relationships = store
    found = dashboard.active_clients

    def then_revoke(conn_, coach_id):
        """List the relationships, then let the client revoke body before the reads."""
        rows = found(conn_, coach_id)
        users.set_consent(conn_, world.SHARED, relationships[world.SHARED], "body", False)
        return rows

    monkeypatch.setattr(dashboard, "active_clients", then_revoke)
    week = dashboard.client_week(conn, world.COACH_A, world.SHARED, MONDAY)
    assert week.shared == {"nutrition", "training"}
    assert week.weight_trend is None and dashboard.latest_weight(week) is None


def test_a_gymer_reads_their_own_week_with_only_approved_reviews(store):
    """A gymer's own week has every scope, and of the reviews only the approved one."""
    conn, _ = store
    _review(conn, world.SHARED, MONDAY - timedelta(weeks=2), "reject")
    approved = _review(conn, world.SHARED, MONDAY - timedelta(weeks=1), "approve")
    _review(conn, world.SHARED, MONDAY)  # pending
    week = dashboard.own_week(conn, world.SHARED, MONDAY)
    assert week.shared == {"nutrition", "body", "training"}
    assert [review["id"] for review in week.reviews] == [approved]
    assert week.reviews[0]["draft"] is None  # never the model's draft


def test_an_own_week_of_a_deleted_account_is_not_found_not_unshared(store):
    """A user's own week whose account is gone raises NotFound, never "not shared" (round 1)."""
    conn, _ = store
    for user_id in (world.MISSING, 42):
        with pytest.raises(NotFound):
            dashboard.own_week(conn, user_id, MONDAY)


def test_the_latest_review_is_the_coachs_newest_by_week(store):
    """The coach's latest review is the newest week's, whatever its status."""
    conn, _ = store
    _review(conn, world.SHARED, MONDAY - timedelta(weeks=1), "approve")
    newest = _review(conn, world.SHARED, MONDAY)
    week = dashboard.client_week(conn, world.COACH_A, world.SHARED, MONDAY)
    latest = dashboard.latest_review(week)
    assert (latest["id"], latest["status"]) == (newest, "PENDING_REVIEW")


def test_no_review_and_no_weight_give_none(store):
    """Without reviews or weights the latest of each is None."""
    conn, _ = store
    users.create_user(conn, "gym-new", "gymer", "New")
    week = dashboard.own_week(conn, "gym-new", MONDAY)
    assert dashboard.latest_review(week) is None
    assert dashboard.latest_weight(week) is None


def test_the_latest_weight_falls_back_to_the_one_before_the_week(store):
    """With no weight in the week, the latest weight is the latest before it, with its day."""
    conn, _ = store
    week = dashboard.own_week(conn, world.SHARED, MONDAY + timedelta(weeks=1))
    assert week.nutrition.latest_weight_kg is None
    assert dashboard.latest_weight(week) == (world.DAY, world.WEIGHT)


def test_the_trend_keeps_the_configured_weeks_up_to_sunday(store, monkeypatch):
    """The weight trend holds the weights of the last WEIGHT_TREND_WEEKS weeks to the Sunday."""
    conn, _ = store
    monkeypatch.setattr(dashboard.config, "WEIGHT_TREND_WEEKS", 2)
    for days_back, kg in ((8, 88.0), (7, 87.9), (1, 87.5)):
        records.add_body_measurement(
            conn, world.SHARED, weight_kg=kg, measured_on=MONDAY - timedelta(days=days_back)
        )
    week = dashboard.own_week(conn, world.SHARED, MONDAY)
    # Two weeks back from Sunday 2026-11-01 starts on Monday 2026-10-19: 10-18 is left out.
    assert [kg for _, kg in week.weight_trend] == [87.9, 87.5, world.WEIGHT]


# --- T9.17: the follow-up flag ------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "de"])
def test_every_follow_up_reason_has_a_text(lang):
    """The client list can name each reason in both languages."""
    for reason in dashboard.FOLLOW_UP_REASONS:
        assert f"clients.follow_up.{reason}" in i18n.TEXT[lang]


def _shared_only(conn, relationships, scopes) -> None:
    """Leave only these scopes shared by the SHARED client."""
    for scope in ("nutrition", "training", "body"):
        users.set_consent(conn, world.SHARED, relationships[world.SHARED], scope, scope in scopes)


def test_few_logged_days_and_no_workout_both_flag_a_client(store):
    """One logged day and a week with no workout: both reasons (a week after the records)."""
    conn, _ = store
    week = dashboard.client_week(conn, world.COACH_A, world.SHARED, MONDAY + timedelta(weeks=1))
    assert dashboard.follow_up_reasons(week) == ("few_logged_days", "no_session")


def test_the_limit_comes_from_config(store, monkeypatch):
    """With the limit at one day, the one logged day is enough; the workout clears the other."""
    conn, _ = store
    monkeypatch.setattr(dashboard.config, "FOLLOW_UP_MIN_LOGGED_DAYS", 1)
    week = dashboard.client_week(conn, world.COACH_A, world.SHARED, MONDAY)
    assert dashboard.follow_up_reasons(week) == ()
    monkeypatch.setattr(dashboard.config, "FOLLOW_UP_MIN_LOGGED_DAYS", 2)
    assert dashboard.follow_up_reasons(week) == ("few_logged_days",)


@pytest.mark.parametrize(
    ("scopes", "reasons"),
    [
        ({"nutrition"}, ("few_logged_days",)),
        ({"training", "body"}, ("no_session",)),
        ({"body"}, ()),
    ],
)
def test_a_scope_not_shared_never_flags_a_client(store, scopes, reasons):
    """Each reason is judged only on a scope the client shares."""
    conn, relationships = store
    _shared_only(conn, relationships, scopes)
    week = dashboard.client_week(conn, world.COACH_A, world.SHARED, MONDAY + timedelta(weeks=1))
    assert dashboard.follow_up_reasons(week) == reasons
