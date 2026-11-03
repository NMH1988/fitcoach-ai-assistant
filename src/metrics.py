"""A week's metrics, computed in Python with no model (D17); pure, no streamlit (T9.14).

A week runs Monday to Sunday (D21). The days are the calendar days the user chose in
`Europe/Berlin` (the store keeps them as dates), so a daylight-saving change moves no workout to
another week. The training metrics take the workouts as `records.list_workout_sessions()` returns
them: the week's sessions and sets, and per exercise the sets, reps, volume (reps x kg) and top
weight. They are facts only: no target, no judgement. The dashboards (T9.15) and the weekly review
(T9.16) read the same functions, so every view shows the same numbers; T9.13 adds the nutrition
metrics here.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

DAYS_IN_WEEK = 7


def week_start(day: date) -> date:
    """Return the Monday of the week the day is in."""
    return day - timedelta(days=day.weekday())


def week_days(start: date) -> tuple[date, ...]:
    """Return the seven days of the week that starts on the given Monday."""
    return tuple(start + timedelta(days=offset) for offset in range(DAYS_IN_WEEK))


def set_volume(exercise_set: dict) -> float:
    """Return a set's volume: reps x kg (0 for a body-weight set with no added load)."""
    return exercise_set["reps"] * exercise_set["weight_kg"]


def session_volume(session: dict) -> float:
    """Return a workout's volume: the sum of its sets' volumes."""
    return sum(set_volume(item) for item in session["sets"])


@dataclass(frozen=True)
class ExerciseWeek:
    """One exercise's week: its sets, reps, volume (reps x kg) and the top weight of any set."""

    exercise_id: str
    sets: int
    reps: int
    volume_kg: float
    top_weight_kg: float


@dataclass(frozen=True)
class TrainingWeek:
    """A week's training facts: the sessions and sets, the volume and each exercise's week."""

    start: date
    sessions: int
    sets: int
    volume_kg: float
    exercises: tuple[ExerciseWeek, ...]

    @property
    def end(self) -> date:
        """Return the week's Sunday."""
        return self.start + timedelta(days=DAYS_IN_WEEK - 1)


def training_week(sessions: Iterable[dict], start: date) -> TrainingWeek:
    """Return the training facts of the week that starts on `start`, from a user's workouts."""
    if start.weekday() != 0:
        raise ValueError("a week starts on a Monday")
    days = {day.isoformat() for day in week_days(start)}
    in_week = sorted(
        (session for session in sessions if session["performed_on"] in days),
        key=lambda session: (session["performed_on"], session["id"]),
    )
    # Each exercise in the order it was first logged in the week.
    by_exercise: dict[str, list[dict]] = {}
    for session in in_week:
        for item in sorted(session["sets"], key=lambda item: item["set_no"]):
            by_exercise.setdefault(item["exercise_id"], []).append(item)
    per_exercise = tuple(
        ExerciseWeek(
            exercise_id=exercise_id,
            sets=len(sets),
            reps=sum(item["reps"] for item in sets),
            volume_kg=sum(set_volume(item) for item in sets),
            top_weight_kg=max(item["weight_kg"] for item in sets),
        )
        for exercise_id, sets in by_exercise.items()
    )
    return TrainingWeek(
        start=start,
        sessions=len(in_week),
        sets=sum(exercise.sets for exercise in per_exercise),
        volume_kg=sum(exercise.volume_kg for exercise in per_exercise),
        exercises=per_exercise,
    )
