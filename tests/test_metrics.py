"""A week's training metrics (T9.14): known-answer tests on src/metrics.py."""

from datetime import date

import pytest

from src import metrics

MONDAY = date(2026, 10, 26)


def _session(session_id: int, day: str, *sets: tuple) -> dict:
    """Return a workout as the store lists it, from (exercise, reps, kg) tuples."""
    return {
        "id": session_id,
        "performed_on": day,
        "recorded_at": f"{day}T18:00:00+00:00",
        "sets": [
            {"exercise_id": ex, "set_no": n, "reps": reps, "weight_kg": kg, "rpe": None}
            for n, (ex, reps, kg) in enumerate(sets, start=1)
        ],
    }


# Worked out by hand: squat 5x100 + 5x100 + 3x110 = 1330 kg, top 110; bench 8x60 + 8x62.5 = 980 kg,
# top 62.5; pull-ups at body weight 10x0 = 0 kg; a session the Sunday before and one the Monday
# after are not in the week; a session with no sets counts as a session.
WEEK = [
    _session(1, "2026-10-25", ("squat", 5, 200.0)),
    _session(2, "2026-10-26", ("squat", 5, 100.0), ("squat", 5, 100.0), ("bench_press", 8, 60.0)),
    _session(3, "2026-10-29", ("bench_press", 8, 62.5), ("pull_up", 10, 0.0), ("squat", 3, 110.0)),
    _session(4, "2026-11-01"),
    _session(5, "2026-11-02", ("deadlift", 5, 180.0)),
]


def test_the_week_s_sessions_sets_volume_and_top_weights():
    """Sessions, sets, volume per exercise and top weight per exercise match the hand count."""
    week = metrics.training_week(WEEK, MONDAY)
    assert (week.start, week.end) == (date(2026, 10, 26), date(2026, 11, 1))
    assert (week.sessions, week.sets, week.volume_kg) == (3, 6, 2310.0)
    assert week.exercises == (
        metrics.ExerciseWeek("squat", sets=3, reps=13, volume_kg=1330.0, top_weight_kg=110.0),
        metrics.ExerciseWeek("bench_press", sets=2, reps=16, volume_kg=980.0, top_weight_kg=62.5),
        metrics.ExerciseWeek("pull_up", sets=1, reps=10, volume_kg=0.0, top_weight_kg=0.0),
    )


def test_a_week_with_no_workout_is_all_zero():
    """A week with nothing logged has no session, no set and no exercise."""
    week = metrics.training_week(WEEK, date(2026, 10, 12))
    assert (week.sessions, week.sets, week.volume_kg, week.exercises) == (0, 0, 0, ())


def test_the_order_of_the_store_s_list_does_not_change_the_numbers():
    """The same workouts in another order give the same week."""
    assert metrics.training_week(reversed(WEEK), MONDAY) == metrics.training_week(WEEK, MONDAY)


def test_a_session_s_volume():
    """A workout's volume is the sum of reps x kg over its sets."""
    assert metrics.session_volume(WEEK[2]) == 8 * 62.5 + 10 * 0.0 + 3 * 110.0
    assert metrics.session_volume(WEEK[3]) == 0


@pytest.mark.parametrize(
    ("day", "monday"),
    [
        (date(2026, 10, 26), date(2026, 10, 26)),
        (date(2026, 11, 1), date(2026, 10, 26)),
        # The week of the change from summer time (2026-10-25, a Sunday) and the week after it.
        (date(2026, 10, 25), date(2026, 10, 19)),
        (date(2026, 10, 27), date(2026, 10, 26)),
        # Across a year's end.
        (date(2027, 1, 1), date(2026, 12, 28)),
    ],
)
def test_a_week_runs_monday_to_sunday(day, monday):
    """week_start gives the Monday of the day's week, Sunday included in the week before."""
    assert metrics.week_start(day) == monday
    assert metrics.week_days(monday)[0] == monday
    assert metrics.week_days(monday)[-1].weekday() == 6


def test_a_week_must_start_on_a_monday():
    """training_week refuses a start that is not a Monday, so no week is cut in two."""
    with pytest.raises(ValueError):
        metrics.training_week(WEEK, date(2026, 10, 27))
