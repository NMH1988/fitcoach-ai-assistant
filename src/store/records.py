"""A gymer's health records: profile entries, weights, targets, meals, workouts, preferences (T9.6).

Each `add_*` writes a row for the acting user only, who must be a gymer (a coach-set target
arrives with T9.17); weight, height and age keep the profile form's ranges and a target the
calorie floor. Each `list_*` takes the acting user and the user whose data it reads and goes
through `access.authorised_read()`: the user's own data, or a coach's read within the scope the data
belongs to (body, nutrition, training); preferences are never shared. Records are never changed in
place (a trigger refuses it): a new profile entry or target is a new row, and an edit is
`delete_record()` and a new row, so a meal's nutrient snapshot stays as it was taken (T9.13 takes
it from the foods table). Days are calendar days the user chose (`Europe/Berlin`, D21); the time a
row was written is UTC.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, get_args

from src import config
from src.profile import ActivityLevel, Goal, Sex
from src.store import values
from src.store.access import NotFound, authorised_read, role_of
from src.store.db import transaction

Meal = Literal["breakfast", "lunch", "dinner", "snack"]
TargetSource = Literal["system", "user"]
RecordKind = Literal[
    "profile_entries",
    "body_measurements",
    "nutrition_targets",
    "meal_items",
    "workout_sessions",
    "preferences",
]
RECORD_KINDS: tuple[str, ...] = get_args(RecordKind)

_ADD_PROFILE = """
INSERT INTO profile_entries (user_id, height_cm, age, sex, activity, goal, recorded_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""
_PROFILES = """
SELECT id, height_cm, age, sex, activity, goal, recorded_at
FROM profile_entries WHERE user_id = ? ORDER BY recorded_at, id
"""
_ADD_WEIGHT = """
INSERT INTO body_measurements (user_id, weight_kg, measured_on, recorded_at) VALUES (?, ?, ?, ?)
"""
_WEIGHTS = """
SELECT id, weight_kg, measured_on, recorded_at FROM body_measurements
WHERE user_id = ? AND (? IS NULL OR measured_on >= ?) AND (? IS NULL OR measured_on <= ?)
ORDER BY measured_on, id
"""
_ADD_TARGET = """
INSERT INTO nutrition_targets
    (user_id, kcal, protein_g, carbs_g, fat_g, set_by, calc_version, effective_from, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_TARGETS = """
SELECT id, kcal, protein_g, carbs_g, fat_g, set_by, calc_version, effective_from, created_at
FROM nutrition_targets WHERE user_id = ? ORDER BY effective_from, id
"""
_ADD_MEAL = """
INSERT INTO meal_items (
    user_id, consumed_on, meal, fdc_id, food_name, grams,
    kcal, protein_g, carbohydrate_g, fat_g, fiber_g, recorded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_MEALS = """
SELECT id, consumed_on, meal, fdc_id, food_name, grams,
    kcal, protein_g, carbohydrate_g, fat_g, fiber_g, recorded_at
FROM meal_items
WHERE user_id = ? AND (? IS NULL OR consumed_on >= ?) AND (? IS NULL OR consumed_on <= ?)
ORDER BY consumed_on, id
"""
_ADD_SESSION = """
INSERT INTO workout_sessions (user_id, performed_on, recorded_at) VALUES (?, ?, ?)
"""
_ADD_SET = """
INSERT INTO exercise_sets (session_id, exercise_id, set_no, reps, weight_kg, rpe)
VALUES (?, ?, ?, ?, ?, ?)
"""
_SESSIONS = """
SELECT session.id AS session_id, session.performed_on, session.recorded_at,
    exercise_set.exercise_id, exercise_set.set_no, exercise_set.reps, exercise_set.weight_kg,
    exercise_set.rpe
FROM workout_sessions AS session
LEFT JOIN exercise_sets AS exercise_set ON exercise_set.session_id = session.id
WHERE session.user_id = ?
    AND (? IS NULL OR session.performed_on >= ?) AND (? IS NULL OR session.performed_on <= ?)
ORDER BY session.performed_on, session.id, exercise_set.set_no
"""
_ADD_PREFERENCE = "INSERT INTO preferences (user_id, text, created_at) VALUES (?, ?, ?)"
_PREFERENCES = "SELECT id, text, created_at FROM preferences WHERE user_id = ? ORDER BY id"
_DELETE_PROFILE = "DELETE FROM profile_entries WHERE id = ? AND user_id = ?"
_DELETE_WEIGHT = "DELETE FROM body_measurements WHERE id = ? AND user_id = ?"
_DELETE_TARGET = "DELETE FROM nutrition_targets WHERE id = ? AND user_id = ?"
_DELETE_MEAL = "DELETE FROM meal_items WHERE id = ? AND user_id = ?"
_DELETE_SETS = """
DELETE FROM exercise_sets
WHERE session_id IN (SELECT id FROM workout_sessions WHERE id = ? AND user_id = ?)
"""
_DELETE_SESSION = "DELETE FROM workout_sessions WHERE id = ? AND user_id = ?"
_DELETE_PREFERENCE = "DELETE FROM preferences WHERE id = ? AND user_id = ?"


@dataclass(frozen=True)
class ExerciseSet:
    """One set of a workout: the exercise (an ID from T9.14's list), reps, kg and optional RPE."""

    exercise_id: str
    set_no: int
    reps: int
    weight_kg: float
    rpe: float | None = None


def _check_gymer(conn: sqlite3.Connection, user_id: str) -> None:
    """Raise NotFound unless the user exists and is a gymer (only gymers keep records)."""
    if role_of(conn, user_id) != "gymer":
        raise NotFound


def _period(start: date | None, end: date | None) -> tuple[str | None, ...]:
    """Return the parameters of an optional inclusive day range, each bound twice."""
    first = None if start is None else values.date_text(start, "start")
    last = None if end is None else values.date_text(end, "end")
    return (first, first, last, last)


def add_profile_entry(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    height_cm: float,
    age: int,
    sex: Sex,
    activity: ActivityLevel,
    goal: Goal,
) -> int:
    """Add a dated profile entry for the user (weight is a body measurement); return its ID."""
    row = (
        values.user_id(user_id),
        values.in_range(height_cm, "height_cm", config.PROFILE_HEIGHT_CM_RANGE),
        values.whole_number(
            age, "age", minimum=config.PROFILE_AGE_RANGE[0], maximum=config.PROFILE_AGE_RANGE[1]
        ),
        values.choice(sex, "sex", get_args(Sex)),
        values.choice(activity, "activity", get_args(ActivityLevel)),
        values.choice(goal, "goal", get_args(Goal)),
        values.utc_text(),
    )
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_PROFILE, row).lastrowid


def list_profile_entries(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return a user's profile entries, oldest first (scope: body)."""
    with authorised_read(conn, actor_id, subject_id, "body", "profile_entries"):
        rows = conn.execute(_PROFILES, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def add_body_measurement(
    conn: sqlite3.Connection, user_id: str, *, weight_kg: float, measured_on: date
) -> int:
    """Add a dated weight in kg for the user; return its ID."""
    row = (
        values.user_id(user_id),
        values.in_range(weight_kg, "weight_kg", config.PROFILE_WEIGHT_KG_RANGE),
        values.date_text(measured_on, "measured_on"),
        values.utc_text(),
    )
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_WEIGHT, row).lastrowid


def list_body_measurements(
    conn: sqlite3.Connection,
    actor_id: str,
    subject_id: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict]:
    """Return a user's weights, by day, within an optional inclusive range (scope: body)."""
    params = (subject_id, *_period(start, end))
    with authorised_read(conn, actor_id, subject_id, "body", "body_measurements"):
        rows = conn.execute(_WEIGHTS, params).fetchall()
    return [dict(row) for row in rows]


def add_target(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    set_by: TargetSource,
    effective_from: date,
    calc_version: str | None = None,
) -> int:
    """Add a new daily target row for the user (a target is never changed); return its ID."""
    row = (
        values.user_id(user_id),
        # The calorie floor holds in code, whoever sets the target (docs/PRD.md, guardrails).
        values.in_range(kcal, "kcal", (config.CALORIE_FLOOR_KCAL, float("inf"))),
        values.number(protein_g, "protein_g"),
        values.number(carbs_g, "carbs_g"),
        values.number(fat_g, "fat_g"),
        values.choice(set_by, "set_by", get_args(TargetSource)),
        None if calc_version is None else values.text(calc_version, "calc_version"),
        values.date_text(effective_from, "effective_from"),
        values.utc_text(),
    )
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_TARGET, row).lastrowid


def list_targets(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return a user's targets, oldest first; the active one is the latest started (nutrition)."""
    with authorised_read(conn, actor_id, subject_id, "nutrition", "nutrition_targets"):
        rows = conn.execute(_TARGETS, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def add_meal_item(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    consumed_on: date,
    meal: Meal,
    fdc_id: int,
    food_name: str,
    grams: float,
    kcal: float,
    protein_g: float,
    carbohydrate_g: float,
    fat_g: float,
    fiber_g: float | None,
) -> int:
    """Add a food eaten with its nutrient snapshot for the grams eaten; return its ID."""
    row = (
        values.user_id(user_id),
        values.date_text(consumed_on, "consumed_on"),
        values.choice(meal, "meal", get_args(Meal)),
        values.whole_number(fdc_id, "fdc_id", minimum=1),
        values.text(food_name, "food_name"),
        values.number(grams, "grams", positive=True),
        values.number(kcal, "kcal"),
        values.number(protein_g, "protein_g"),
        values.number(carbohydrate_g, "carbohydrate_g"),
        values.number(fat_g, "fat_g"),
        # USDA leaves fibre empty when it was not reported.
        None if fiber_g is None else values.number(fiber_g, "fiber_g"),
        values.utc_text(),
    )
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_MEAL, row).lastrowid


def list_meal_items(
    conn: sqlite3.Connection,
    actor_id: str,
    subject_id: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict]:
    """Return a user's meal items, by day, within an optional inclusive range (nutrition)."""
    params = (subject_id, *_period(start, end))
    with authorised_read(conn, actor_id, subject_id, "nutrition", "meal_items"):
        rows = conn.execute(_MEALS, params).fetchall()
    return [dict(row) for row in rows]


def add_workout_session(
    conn: sqlite3.Connection, user_id: str, *, performed_on: date, sets: Sequence[ExerciseSet]
) -> int:
    """Add a workout with its sets in one transaction; return the session's ID."""
    session = (values.user_id(user_id), values.date_text(performed_on, "performed_on"))
    checked = [
        (
            values.text(item.exercise_id, "exercise_id"),
            values.whole_number(item.set_no, "set_no", minimum=1),
            values.whole_number(item.reps, "reps"),
            values.number(item.weight_kg, "weight_kg"),
            None if item.rpe is None else values.number(item.rpe, "rpe"),
        )
        for item in sets
    ]
    with transaction(conn):
        _check_gymer(conn, user_id)
        session_id = conn.execute(_ADD_SESSION, (*session, values.utc_text())).lastrowid
        for item in checked:
            conn.execute(_ADD_SET, (session_id, *item))
    return session_id


def list_workout_sessions(
    conn: sqlite3.Connection,
    actor_id: str,
    subject_id: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict]:
    """Return a user's workouts with their sets, by day, in an optional range (training)."""
    params = (subject_id, *_period(start, end))
    with authorised_read(conn, actor_id, subject_id, "training", "workout_sessions"):
        rows = conn.execute(_SESSIONS, params).fetchall()
    sessions: dict[int, dict] = {}
    for row in rows:
        session = sessions.setdefault(
            row["session_id"],
            {
                "id": row["session_id"],
                "performed_on": row["performed_on"],
                "recorded_at": row["recorded_at"],
                "sets": [],
            },
        )
        if row["set_no"] is not None:  # a session saved with no sets has one row of NULLs
            # Plain dicts, like every other list, so a caller can put them in JSON.
            session["sets"].append(
                {name: row[name] for name in ("exercise_id", "set_no", "reps", "weight_kg", "rpe")}
            )
    return list(sessions.values())


def add_preference(conn: sqlite3.Connection, user_id: str, text: str) -> int:
    """Add a preference the user approved (T9.7 proposes it); return its ID."""
    row = (values.user_id(user_id), values.text(text, "text"), values.utc_text())
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_PREFERENCE, row).lastrowid


def list_preferences(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return a user's preferences, oldest first; only the user reads them, never a coach."""
    with authorised_read(conn, actor_id, subject_id, None, "preferences"):
        rows = conn.execute(_PREFERENCES, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def delete_record(conn: sqlite3.Connection, user_id: str, kind: RecordKind, record_id: int) -> None:
    """Delete one of the user's own records (a workout with its sets); NotFound if not theirs."""
    values.choice(kind, "kind", RECORD_KINDS)
    if isinstance(record_id, bool) or not isinstance(record_id, int):
        raise NotFound
    params = (record_id, values.user_id(user_id))
    with transaction(conn):
        # One constant statement per kind: no table name is ever put into SQL.
        match kind:
            case "profile_entries":
                cursor = conn.execute(_DELETE_PROFILE, params)
            case "body_measurements":
                cursor = conn.execute(_DELETE_WEIGHT, params)
            case "nutrition_targets":
                cursor = conn.execute(_DELETE_TARGET, params)
            case "meal_items":
                cursor = conn.execute(_DELETE_MEAL, params)
            case "workout_sessions":
                conn.execute(_DELETE_SETS, params)
                cursor = conn.execute(_DELETE_SESSION, params)
            case "preferences":
                cursor = conn.execute(_DELETE_PREFERENCE, params)
        if cursor.rowcount != 1:
            raise NotFound
