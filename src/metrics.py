"""A week's metrics from a user's records, with no model and no streamlit (T9.13, T9.14).

`week_metrics()` is the one function every view of a week reads: T9.15's dashboards (the coach's
client list and client week, the gymer's "My week") and T9.16's weekly review, so they all show the
same numbers. It takes the records (rows as the store returns them) and the week's Monday, never a
user ID, so the caller decides whose records it may read (`src/diary.read_week()`).

A week runs Monday to Sunday in `Europe/Berlin` (D21). Days are calendar days the user chose, so a
daylight-saving change does not move a day; only "today" depends on the clock (`berlin_day()`). A
day is logged when it has at least one food; averages are over the logged days only, so a day with
no entries is "not logged", never a day without eating (AC-26). The active target is the latest one
started on or before the week's Sunday. The weight change is the week's latest weight minus the
latest weight before its Monday (owner's choice, 2026-11-03).

The training metrics (`training_week()`, T9.14) take the workouts as
`records.list_workout_sessions()` returns them: the week's sessions and sets, and per exercise the
sets, reps, volume (reps x kg) and top weight. They are facts only: no target, no judgement.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src import config

DAYS_IN_WEEK = 7
# The nutrients of a meal item's snapshot, in the store's names.
NUTRIENTS: tuple[str, ...] = ("kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g")


@dataclass(frozen=True)
class Intake:
    """Nutrient totals (a day's) or averages (a week's); fibre may count only the foods with one."""

    kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    fiber_g: float
    # False when a food had no fibre value (USDA: not reported), so fiber_g is a lower bound.
    fiber_complete: bool


@dataclass(frozen=True)
class Target:
    """The daily target active in a week, as stored."""

    kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    effective_from: date
    set_by: str


@dataclass(frozen=True)
class WeekMetrics:
    """One week's nutrition and weight metrics, Monday to Sunday."""

    week_start: date
    week_end: date
    # Each day of the week, Monday first, with its totals; None when nothing was logged that day.
    days: tuple[tuple[date, Intake | None], ...]
    # The averages over the logged days; None when no day was logged.
    average: Intake | None
    target: Target | None
    # The average minus the target, per nutrient; None without a logged day or a target.
    difference: dict[str, float] | None
    latest_weight_kg: float | None
    latest_weight_on: date | None
    previous_weight_kg: float | None
    weight_change_kg: float | None

    @property
    def logged_days(self) -> int:
        """Return how many days of the week have at least one food logged."""
        return sum(totals is not None for _, totals in self.days)

    @property
    def days_in_week(self) -> int:
        """Return the number of days the logged days are counted out of (always seven)."""
        return DAYS_IN_WEEK


def berlin_day(moment: datetime | None = None) -> date:
    """Return the calendar day in Europe/Berlin at a moment (now by default)."""
    zone = ZoneInfo(config.TIME_ZONE)
    if moment is None:
        return datetime.now(zone).date()
    if moment.tzinfo is None:
        # A naive time could be any zone; reading it as Berlin's would shift the day silently.
        raise ValueError("moment needs a time zone")
    return moment.astimezone(zone).date()


def week_start(day: date) -> date:
    """Return the Monday of the week the day is in."""
    return day - timedelta(days=day.weekday())


def week_days(monday: date) -> tuple[date, ...]:
    """Return the seven days of the week that starts on this Monday."""
    return tuple(monday + timedelta(days=offset) for offset in range(DAYS_IN_WEEK))


def _day(text: str) -> date:
    """Return a stored ISO day ("2026-11-02") as a date."""
    return date.fromisoformat(text)


def day_totals(items: Iterable[dict]) -> Intake | None:
    """Return the nutrient totals of a set of meal items; None when there are none."""
    items = list(items)
    if not items:
        return None
    sums = {name: sum(item[name] or 0.0 for item in items) for name in NUTRIENTS}
    return Intake(**sums, fiber_complete=all(item["fiber_g"] is not None for item in items))


def _average(totals: list[Intake]) -> Intake | None:
    """Return the average of the logged days' totals; None when no day was logged."""
    if not totals:
        return None
    count = len(totals)
    sums = {name: sum(getattr(day, name) for day in totals) / count for name in NUTRIENTS}
    return Intake(**sums, fiber_complete=all(day.fiber_complete for day in totals))


def _active_target(targets: Iterable[dict], sunday: date) -> Target | None:
    """Return the latest target started on or before the Sunday (by day, then by row ID)."""
    started = [row for row in targets if _day(row["effective_from"]) <= sunday]
    if not started:
        return None
    row = max(started, key=lambda row: (row["effective_from"], row["id"]))
    return Target(
        kcal=row["kcal"],
        protein_g=row["protein_g"],
        carbohydrate_g=row["carbs_g"],
        fat_g=row["fat_g"],
        effective_from=_day(row["effective_from"]),
        set_by=row["set_by"],
    )


def _latest_weight(weights: Iterable[dict]) -> dict | None:
    """Return the latest weight row (by day, then by row ID); None when there is none."""
    weights = list(weights)
    return max(weights, key=lambda row: (row["measured_on"], row["id"])) if weights else None


def week_metrics(
    meals: Iterable[dict], weights: Iterable[dict], targets: Iterable[dict], monday: date
) -> WeekMetrics:
    """Return the metrics of the week starting on the Monday from the user's stored records."""
    if monday.weekday() != 0:
        raise ValueError("a week starts on a Monday")
    days = week_days(monday)
    sunday = days[-1]
    by_day: dict[date, list[dict]] = {day: [] for day in days}
    for item in meals:
        day = _day(item["consumed_on"])
        if day in by_day:
            by_day[day].append(item)
    totals = tuple((day, day_totals(by_day[day])) for day in days)
    average = _average([day_total for _, day_total in totals if day_total is not None])
    target = _active_target(targets, sunday)
    difference = None
    if average is not None and target is not None:
        difference = {
            name: getattr(average, name) - getattr(target, name)
            for name in ("kcal", "protein_g", "carbohydrate_g", "fat_g")
        }
    weights = list(weights)
    latest = _latest_weight(row for row in weights if monday <= _day(row["measured_on"]) <= sunday)
    previous = _latest_weight(row for row in weights if _day(row["measured_on"]) < monday)
    change = None
    if latest is not None and previous is not None:
        change = latest["weight_kg"] - previous["weight_kg"]
    return WeekMetrics(
        week_start=monday,
        week_end=sunday,
        days=totals,
        average=average,
        target=target,
        difference=difference,
        latest_weight_kg=None if latest is None else latest["weight_kg"],
        latest_weight_on=None if latest is None else _day(latest["measured_on"]),
        previous_weight_kg=None if previous is None else previous["weight_kg"],
        weight_change_kg=change,
    )


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
