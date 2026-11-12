"""A week as the dashboards show it, read scope by scope through the store's checks (T9.15).

The coach's client list and client week and the gymer's My week read a week here, so they all show
the numbers of `src/metrics.py`. A coach reads a client only while their relationship is active
(else `NotFound`, AC-21), and only the scopes the client shares: each scope's records are read
through the store, which authorises and audits every read, and a scope the client does not share
(or revokes while the page reads) is left unread and shown as "not shared"; it is never passed on as
"nothing logged". A gymer reads their own week, every scope. No streamlit here, so it is
unit-tested on a real store.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, get_args

from src import config, metrics
from src.store import records, reviews, users
from src.store.access import SCOPES, NotFound, role_of


@dataclass(frozen=True)
class DashboardWeek:
    """One week of a user's data, with the scopes it could be read for."""

    # The scopes read; the others were not shared (always all three for the user's own week).
    shared: frozenset[str]
    # Nutrition and body metrics; a scope not shared contributed no records.
    nutrition: metrics.WeekMetrics
    # None when training is not shared.
    training: metrics.TrainingWeek | None
    volume_by_day: tuple[tuple[date, float | None], ...] | None
    # The weights of the trend (config.WEIGHT_TREND_WEEKS up to the Sunday); None when body is not
    # shared.
    weight_trend: tuple[tuple[date, float], ...] | None
    # The reviews the reader may read (a gymer: the approved ones; a coach: the ones they wrote);
    # None when nutrition is not shared.
    reviews: tuple[dict, ...] | None
    # How much of the week's food was logged from the coach's suggestions (T9.34); None when
    # nutrition is not shared. Shown on the pages only: never in a tool result or a review.
    suggested: metrics.SuggestedShare | None = None


def _read(conn: sqlite3.Connection, actor_id: str, subject_id: str, monday: date, scopes) -> dict:
    """Read each scope's records for the week; a scope a coach is refused is left out."""
    sunday = metrics.week_days(monday)[-1]
    reads = {
        "nutrition": lambda: (
            records.list_meal_items(conn, actor_id, subject_id, start=monday, end=sunday),
            records.list_targets(conn, actor_id, subject_id),
            reviews.list_reviews(conn, actor_id, subject_id),
        ),
        # Weights before the Monday too, for the week's change and the trend.
        "body": lambda: records.list_body_measurements(conn, actor_id, subject_id, end=sunday),
        "training": lambda: records.list_workout_sessions(
            conn, actor_id, subject_id, start=monday, end=sunday
        ),
    }
    found = {}
    for scope in SCOPES:
        if scope not in scopes:
            continue
        try:
            found[scope] = reads[scope]()
        except NotFound:
            # A user's own read is refused only when the account is gone (deleted in another
            # tab): that is the caller's NotFound, never "not shared" (code review round 1).
            if actor_id == subject_id:
                raise
            # Revoked between the relationship's read and this one (AC-22): not shared.
            continue
    return found


def _week(found: dict, monday: date, since: str | None = None) -> DashboardWeek:
    """Build the week from the records read, leaving out what was not read."""
    meals, targets, written = found.get("nutrition", ([], [], None))
    weights = found.get("body", [])
    sessions = found.get("training")
    sunday = metrics.week_days(monday)[-1]
    trend_start = sunday - timedelta(weeks=config.WEIGHT_TREND_WEEKS) + timedelta(days=1)
    return DashboardWeek(
        shared=frozenset(found),
        nutrition=metrics.week_metrics(meals, weights, targets, monday),
        training=None if sessions is None else metrics.training_week(sessions, monday),
        volume_by_day=None if sessions is None else metrics.volume_by_day(sessions, monday),
        weight_trend=(
            None if "body" not in found else metrics.weights_between(weights, trend_start, sunday)
        ),
        reviews=None if written is None else tuple(written),
        # A coach's share counts only items logged since their relationship began (T9.34).
        suggested=(
            None if "nutrition" not in found else metrics.suggested_share(meals, monday, since)
        ),
    )


def active_clients(conn: sqlite3.Connection, coach_id: str) -> list[dict]:
    """Return the coach's active relationships (the client, its name, since when, its scopes)."""
    return [row for row in users.list_relationships(conn, coach_id) if row["status"] == "active"]


def client_week(
    conn: sqlite3.Connection, coach_id: str, client_id: object, monday: date
) -> DashboardWeek:
    """Return a client's week for their coach, the scopes shared only; else NotFound (AC-21)."""
    # A gymer's relationship names their coach too; only the coach's side may read the other.
    if role_of(conn, coach_id) != "coach":
        raise NotFound
    for relationship in active_clients(conn, coach_id):
        if relationship["other_id"] == client_id:
            return relationship_week(conn, coach_id, relationship, monday)
    raise NotFound


def relationship_week(
    conn: sqlite3.Connection, coach_id: str, relationship: dict, monday: date
) -> DashboardWeek:
    """Return the week of one of active_clients()'s rows, the scopes it shares only."""
    # The row comes from the coach's own list; each read still goes through the store's checks.
    return _week(
        _read(conn, coach_id, relationship["other_id"], monday, relationship["scopes"]),
        monday,
        relationship["accepted_at"],
    )


def own_week(conn: sqlite3.Connection, user_id: str, monday: date) -> DashboardWeek:
    """Return a gymer's own week, every scope."""
    return _week(_read(conn, user_id, user_id, monday, SCOPES), monday)


# Why a client is flagged for follow-up (T9.17): fewer logged days than
# config.FOLLOW_UP_MIN_LOGGED_DAYS, or no workout in the week. Each is judged only on a scope the
# client shares; a scope not shared never flags them.
FollowUp = Literal["few_logged_days", "no_session"]
FOLLOW_UP_REASONS: tuple[FollowUp, ...] = get_args(FollowUp)


def follow_up_reasons(week: DashboardWeek) -> tuple[FollowUp, ...]:
    """Return why the client needs a follow-up this week (empty: none), from the scopes shared."""
    reasons: list[FollowUp] = []
    if "nutrition" in week.shared and week.nutrition.logged_days < config.FOLLOW_UP_MIN_LOGGED_DAYS:
        reasons.append("few_logged_days")
    if week.training is not None and week.training.sessions == 0:
        reasons.append("no_session")
    return tuple(reasons)


def latest_review(week: DashboardWeek) -> dict | None:
    """Return the latest review read with the week (by its week, then its ID); None when none."""
    if not week.reviews:
        return None
    return max(week.reviews, key=lambda review: (review["period_start"], review["id"]))


def latest_weight(week: DashboardWeek) -> tuple[date, float] | None:
    """Return the latest weight up to the week's Sunday, from the week or before it."""
    found = week.nutrition
    if found.latest_weight_kg is not None:
        return found.latest_weight_on, found.latest_weight_kg
    if found.previous_weight_kg is not None:
        return found.previous_weight_on, found.previous_weight_kg
    return None
