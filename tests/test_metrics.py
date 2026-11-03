"""Known-answer tests for the week's nutrition metrics (T9.13, AC-25, AC-26)."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from src import metrics

MONDAY = date(2026, 10, 19)  # the week of the daylight-saving change (Sunday 2026-10-25)


def _meal(day: str, kcal: float, protein: float = 0.0, fiber: float | None = 1.0) -> dict:
    """Return a stored meal item row with the given day and nutrients."""
    return {
        "consumed_on": day,
        "kcal": kcal,
        "protein_g": protein,
        "carbohydrate_g": 10.0,
        "fat_g": 5.0,
        "fiber_g": fiber,
    }


def _weight(row_id: int, day: str, kg: float) -> dict:
    """Return a stored weight row."""
    return {"id": row_id, "measured_on": day, "weight_kg": kg}


def _target(row_id: int, day: str, kcal: float) -> dict:
    """Return a stored target row."""
    return {
        "id": row_id,
        "effective_from": day,
        "kcal": kcal,
        "protein_g": 150.0,
        "carbs_g": 250.0,
        "fat_g": 70.0,
        "set_by": "system",
    }


def test_three_logged_days_out_of_seven_are_averaged_over_those_three():
    """AC-26: 3 of 7 days logged, and the average is over the three, not the seven."""
    meals = [
        _meal("2026-10-19", 2000, protein=100),
        _meal("2026-10-19", 400, protein=20),
        _meal("2026-10-21", 1800, protein=90),
        _meal("2026-10-25", 2600, protein=130),
    ]
    week = metrics.week_metrics(meals, [], [], MONDAY)
    assert (week.logged_days, week.days_in_week) == (3, 7)
    assert week.average.kcal == pytest.approx((2400 + 1800 + 2600) / 3)
    assert week.average.protein_g == pytest.approx((120 + 90 + 130) / 3)
    by_day = dict(week.days)
    assert by_day[date(2026, 10, 19)].kcal == 2400
    assert by_day[date(2026, 10, 20)] is None  # not logged, never "ate nothing"
    assert tuple(day for day, _ in week.days) == metrics.week_days(MONDAY)


def test_a_week_with_nothing_logged_has_no_average():
    """No logged day: 0 of 7, no average and no difference from the target."""
    week = metrics.week_metrics([], [], [_target(1, "2026-10-01", 2500)], MONDAY)
    assert week.logged_days == 0
    assert week.average is None
    assert week.difference is None
    assert week.target.kcal == 2500


def test_items_outside_the_week_are_left_out():
    """The Sunday before and the Monday after belong to other weeks."""
    meals = [_meal("2026-10-18", 9999), _meal("2026-10-26", 9999), _meal("2026-10-22", 2000)]
    week = metrics.week_metrics(meals, [], [], MONDAY)
    assert week.logged_days == 1
    assert week.average.kcal == 2000


def test_the_average_is_compared_with_the_target_active_on_sunday():
    """The latest target started on or before Sunday is used; a later one is not."""
    targets = [
        _target(1, "2026-10-01", 2500),
        _target(2, "2026-10-22", 2300),  # started mid-week: active by Sunday
        _target(3, "2026-10-26", 2000),  # next week
    ]
    week = metrics.week_metrics([_meal("2026-10-20", 2400)], [], targets, MONDAY)
    assert (week.target.kcal, week.target.effective_from) == (2300, date(2026, 10, 22))
    assert week.difference["kcal"] == pytest.approx(100)


def test_two_targets_on_one_day_take_the_later_row():
    """Two saves on one day: the row written last is the active target."""
    targets = [_target(5, "2026-10-20", 2400), _target(4, "2026-10-20", 2200)]
    assert metrics.week_metrics([], [], targets, MONDAY).target.kcal == 2400


def test_the_weight_change_is_the_weeks_latest_minus_the_latest_before_it():
    """Latest weight in the week minus the latest weight before its Monday (owner's choice)."""
    weights = [
        _weight(1, "2026-10-10", 81.0),
        _weight(2, "2026-10-17", 80.0),  # the latest before the week
        _weight(3, "2026-10-20", 79.8),
        _weight(4, "2026-10-24", 79.4),  # the latest in the week
        _weight(5, "2026-10-27", 70.0),  # next week
    ]
    week = metrics.week_metrics([], weights, [], MONDAY)
    assert (week.latest_weight_kg, week.latest_weight_on) == (79.4, date(2026, 10, 24))
    assert week.previous_weight_kg == 80.0
    assert week.weight_change_kg == pytest.approx(-0.6)


@pytest.mark.parametrize(
    "weights",
    [[], [_weight(1, "2026-10-17", 80.0)], [_weight(1, "2026-10-20", 80.0)]],
    ids=["none", "only before", "only in the week"],
)
def test_no_weight_change_without_a_weight_on_each_side(weights):
    """Without a weight in the week and one before it, the change is None."""
    assert metrics.week_metrics([], weights, [], MONDAY).weight_change_kg is None


def test_two_weights_on_one_day_take_the_later_row():
    """A second weigh-in on the same day is the latest."""
    weights = [_weight(1, "2026-10-17", 80.0), _weight(3, "2026-10-21", 79.0)]
    weights.append(_weight(4, "2026-10-21", 79.5))
    assert metrics.week_metrics([], weights, [], MONDAY).latest_weight_kg == 79.5


def test_fibre_not_reported_marks_the_totals_incomplete():
    """A food with no fibre value adds nothing to fibre and marks the day and the week."""
    meals = [_meal("2026-10-19", 500, fiber=None), _meal("2026-10-19", 500, fiber=4.0)]
    week = metrics.week_metrics(meals, [], [], MONDAY)
    day = dict(week.days)[MONDAY]
    assert (day.fiber_g, day.fiber_complete) == (4.0, False)
    assert week.average.fiber_complete is False


def test_a_week_must_start_on_a_monday():
    """Any other day is refused, so no view counts a shifted week."""
    with pytest.raises(ValueError):
        metrics.week_metrics([], [], [], MONDAY + timedelta(days=1))


@pytest.mark.parametrize(
    ("day", "monday"),
    [
        (date(2026, 10, 19), date(2026, 10, 19)),
        (date(2026, 10, 25), date(2026, 10, 19)),
        (date(2026, 10, 26), date(2026, 10, 26)),
        (date(2027, 1, 1), date(2026, 12, 28)),  # across a year
    ],
)
def test_the_week_starts_on_monday(day, monday):
    """week_start returns the Monday of the day's week."""
    assert metrics.week_start(day) == monday


@pytest.mark.parametrize(
    ("moment", "day"),
    [
        # Summer time (UTC+2) until 2026-10-25 03:00, then winter time (UTC+1).
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), date(2026, 10, 25)),  # Sunday 00:30 CEST
        (datetime(2026, 10, 25, 22, 30, tzinfo=UTC), date(2026, 10, 25)),  # Sunday 23:30 CET
        (datetime(2026, 10, 25, 23, 30, tzinfo=UTC), date(2026, 10, 26)),  # Monday 00:30 CET
        (datetime(2026, 3, 29, 21, 59, tzinfo=UTC), date(2026, 3, 29)),  # Sunday 23:59 CEST
        (datetime(2026, 3, 29, 22, 0, tzinfo=UTC), date(2026, 3, 30)),  # Monday 00:00 CEST
        (datetime(2026, 10, 25, 23, 30, tzinfo=timezone(timedelta(hours=-5))), date(2026, 10, 26)),
    ],
)
def test_the_day_is_berlins_across_a_daylight_saving_change(moment, day):
    """AC-25: a moment becomes Berlin's calendar day, also around both clock changes."""
    assert metrics.berlin_day(moment) == day


def test_the_dst_week_is_monday_to_sunday_in_berlin():
    """The week of the October change still runs from Monday 00:00 to Sunday 23:59 in Berlin."""
    first = metrics.berlin_day(datetime(2026, 10, 18, 22, 0, tzinfo=UTC))  # Monday 00:00 CEST
    last = metrics.berlin_day(datetime(2026, 10, 25, 22, 59, tzinfo=UTC))  # Sunday 23:59 CET
    assert metrics.week_start(first) == metrics.week_start(last) == MONDAY
    after = metrics.berlin_day(datetime(2026, 10, 25, 23, 0, tzinfo=UTC))  # Monday 00:00 CET
    assert metrics.week_start(after) == date(2026, 10, 26)


def test_a_naive_moment_is_refused():
    """A time with no zone could be any zone, so it is not read as Berlin's."""
    with pytest.raises(ValueError):
        metrics.berlin_day(datetime(2026, 10, 25, 12, 0))
