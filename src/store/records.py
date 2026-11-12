"""Gymers' health records (profile, weights, targets, meals, workouts), coaches' preferences (T9.6).

A preference is a coach's own working preference since T9.7 (it was a gymer's before T9.24).

Each `add_*` writes a row for the acting user only, who must be a gymer, or for `add_preference()` a
coach; weight, height and age keep the profile form's ranges and a target the calorie floor. The
one write into another user's records is a coach's target for a client (`add_client_target()`,
T9.17): only while the client shares nutrition with that coach, audited as `target_set`. A
coach-set target is the gymer's to read, never to delete alone (`delete_record()` refuses it; only
`my_data.delete_user_data()` removes it), and a profile Save keeps it while the gymer shares
nutrition with a coach (`add_profile_with_target()`; owner's choices, 2026-11-06). The other one
is a coach's list of suggested foods (`suggestions.add_client_suggestions()`, T9.34); a meal item
the gymer logs from it is flagged `from_suggestion` here, after the store checked the item is on
the gymer's active list, and an edit keeps the flag only for the same food.

Each `list_*` takes the acting user and the user whose data it reads and goes through
`access.authorised_read()`: the user's own data, or a coach's read within the scope the data
belongs to (body, nutrition, training); preferences are never shared. Records are never changed in
place (a trigger refuses it): a new profile entry or target is a new row, and an
edit is `delete_record()` and a new row, so a meal's nutrient snapshot stays as it was taken (T9.13
takes it from the foods table); a workout's edit is both in one transaction
(`replace_workout_session()`, T9.14). A set names an exercise of T9.14's list and keeps the ranges
in config. Days are calendar days the user chose (`Europe/Berlin`, D21); the time a row was written
is UTC.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, get_args

from src import config, exercises, metrics
from src.profile import ActivityLevel, Goal, Sex
from src.store import suggestions, values
from src.store.access import NotFound, audit, authorise_read, authorised_read, role_of
from src.store.db import transaction

Meal = Literal["breakfast", "lunch", "dinner", "snack"]
# Who may set a target through add_target() and the profile Save: the app or the gymer. A coach's
# target is written only by add_client_target(), which sets "coach" itself (T9.17).
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
# Who set the gymer's latest target (by day, then row ID, as metrics picks the active one).
_LATEST_TARGET_SOURCE = """
SELECT set_by FROM nutrition_targets WHERE user_id = ?
ORDER BY effective_from DESC, id DESC LIMIT 1
"""
# Whether the gymer shares nutrition with a coach now, read from the sharing rule's one view, so an
# ended relationship, or a new coach the gymer does not share nutrition with, does not count
# (owner's choice, 2026-11-06, code review round 1).
_SHARES_NUTRITION = "SELECT 1 FROM open_shares WHERE client_id = ? AND scope = 'nutrition'"
_ADD_MEAL = """
INSERT INTO meal_items (
    user_id, consumed_on, meal, fdc_id, food_name, grams,
    kcal, protein_g, carbohydrate_g, fat_g, fiber_g, recorded_at, from_suggestion
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
# An edited item keeps its from_suggestion flag only with the same food (T9.34).
_MEAL_FOOD = "SELECT fdc_id, from_suggestion FROM meal_items WHERE id = ? AND user_id = ?"
_MEALS = """
SELECT id, consumed_on, meal, fdc_id, food_name, grams,
    kcal, protein_g, carbohydrate_g, fat_g, fiber_g, recorded_at, from_suggestion
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
# A coach-set target is never deleted by the gymer alone (T9.17); delete_user_data() removes it.
_DELETE_TARGET = "DELETE FROM nutrition_targets WHERE id = ? AND user_id = ? AND set_by <> 'coach'"
_DELETE_MEAL = "DELETE FROM meal_items WHERE id = ? AND user_id = ?"
_DELETE_SETS = """
DELETE FROM exercise_sets
WHERE session_id IN (SELECT id FROM workout_sessions WHERE id = ? AND user_id = ?)
"""
_DELETE_SESSION = "DELETE FROM workout_sessions WHERE id = ? AND user_id = ?"
_DELETE_PREFERENCE = "DELETE FROM preferences WHERE id = ? AND user_id = ?"


@dataclass(frozen=True)
class ExerciseSet:
    """One set of a workout: the exercise (an ID of `src/exercises.py`), reps, kg, optional RPE."""

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


def _profile_row(
    user_id: str, height_cm: float, age: int, sex: Sex, activity: ActivityLevel, goal: Goal
) -> tuple:
    """Return a checked profile entry row, ready for _ADD_PROFILE."""
    return (
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
    row = _profile_row(user_id, height_cm, age, sex, activity, goal)
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_PROFILE, row).lastrowid


def list_profile_entries(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return a user's profile entries, oldest first (scope: body)."""
    with authorised_read(conn, actor_id, subject_id, "body", "profile_entries"):
        rows = conn.execute(_PROFILES, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def _weight_row(user_id: str, weight_kg: float, measured_on: date) -> tuple:
    """Return a checked weight row, ready for _ADD_WEIGHT."""
    return (
        values.user_id(user_id),
        values.in_range(weight_kg, "weight_kg", config.PROFILE_WEIGHT_KG_RANGE),
        values.date_text(measured_on, "measured_on"),
        values.utc_text(),
    )


def add_body_measurement(
    conn: sqlite3.Connection, user_id: str, *, weight_kg: float, measured_on: date
) -> int:
    """Add a dated weight in kg for the user; return its ID."""
    row = _weight_row(user_id, weight_kg, measured_on)
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
    # Only "system" or "user": a coach's target goes through add_client_target() (T9.17).
    source = values.choice(set_by, "set_by", get_args(TargetSource))
    row = _target_row(
        user_id, kcal, protein_g, carbs_g, fat_g, source, effective_from, calc_version
    )
    with transaction(conn):
        _check_gymer(conn, user_id)
        return conn.execute(_ADD_TARGET, row).lastrowid


def add_client_target(
    conn: sqlite3.Connection,
    coach_id: str,
    client_id: str,
    *,
    kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    effective_from: date,
) -> int:
    """Add a coach's daily target for a client who shares nutrition with them; return its ID."""
    # The row is checked before the transaction, so a bad value writes nothing. The share check,
    # the insert and the audit row are one transaction: a coach of a gymer, an active relationship
    # and nutrition shared (open_shares); anything else, the coach's own ID included (for which
    # authorise_read() returns False), is the same NotFound, with no row and no audit row.
    try:
        values.user_id(client_id)
    except values.StoreValueError:
        raise NotFound from None  # as a read of a subject that is not an ID
    row = _target_row(client_id, kcal, protein_g, carbs_g, fat_g, "coach", effective_from, None)
    # From today at the latest: a target set for later would keep a Save from writing the gymer's
    # own target while it is not yet the active one (code review round 1).
    if effective_from > metrics.berlin_day():
        raise values.StoreValueError("effective_from", "must not be after today")
    with transaction(conn):
        if authorise_read(conn, coach_id, client_id, "nutrition") is not True:
            raise NotFound
        target_id = conn.execute(_ADD_TARGET, row).lastrowid
        # Who set what kind of record about whom and when, never a value (PRD, Audit).
        audit(
            conn,
            coach_id,
            "target_set",
            "nutrition_targets",
            subject_id=client_id,
            resource_id=target_id,
        )
        return target_id


def _target_row(
    user_id: str,
    kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    set_by: str,
    effective_from: date,
    calc_version: str | None,
) -> tuple:
    """Return a checked target row, ready for _ADD_TARGET; the caller has checked set_by."""
    return (
        values.user_id(user_id),
        # The calorie floor holds in code, whoever sets the target (docs/PRD.md, guardrails).
        values.in_range(kcal, "kcal", (config.CALORIE_FLOOR_KCAL, float("inf"))),
        values.number(protein_g, "protein_g"),
        values.number(carbs_g, "carbs_g"),
        values.number(fat_g, "fat_g"),
        set_by,
        None if calc_version is None else values.text(calc_version, "calc_version"),
        values.date_text(effective_from, "effective_from"),
        values.utc_text(),
    )


def _keeps_coach_target(conn: sqlite3.Connection, user_id: str) -> bool:
    """Return True if the latest target is a coach's and the gymer shares nutrition with a coach."""
    latest = conn.execute(_LATEST_TARGET_SOURCE, (user_id,)).fetchone()
    if latest is None or latest["set_by"] != "coach":
        return False
    return conn.execute(_SHARES_NUTRITION, (user_id,)).fetchone() is not None


def add_profile_with_target(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    height_cm: float,
    age: int,
    sex: Sex,
    activity: ActivityLevel,
    goal: Goal,
    weight_kg: float | None,
    kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    set_by: TargetSource,
    day: date,
    calc_version: str | None = None,
) -> bool:
    """Add a profile entry, its weight and its target in one transaction; False: target kept."""
    # One transaction, so a profile entry never stays without the target worked out from it,
    # except while the gymer shares nutrition with a coach and the latest target was set by a
    # coach: that target then stays the active one and no target is written (T9.17, owner's
    # choices, 2026-11-06). Otherwise (no coach, or nutrition not shared) a Save writes its
    # target, which then replaces the coach's.
    profile = _profile_row(user_id, height_cm, age, sex, activity, goal)
    weight = None if weight_kg is None else _weight_row(user_id, weight_kg, day)
    source = values.choice(set_by, "set_by", get_args(TargetSource))
    target = _target_row(user_id, kcal, protein_g, carbs_g, fat_g, source, day, calc_version)
    with transaction(conn):
        _check_gymer(conn, user_id)
        conn.execute(_ADD_PROFILE, profile)
        if weight is not None:
            conn.execute(_ADD_WEIGHT, weight)
        if _keeps_coach_target(conn, user_id):
            return False
        conn.execute(_ADD_TARGET, target)
        return True


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
    suggestion_item_id: int | None = None,
) -> int:
    """Add a food eaten with its nutrient snapshot for the grams eaten; return its ID."""
    # With suggestion_item_id (T9.34), the item must be on the gymer's active list with this meal
    # slot and food, checked in the write transaction; the row is then flagged from_suggestion.
    row = _meal_row(
        user_id,
        consumed_on,
        meal,
        fdc_id,
        food_name,
        grams,
        kcal,
        protein_g,
        carbohydrate_g,
        fat_g,
        fiber_g,
    )
    with transaction(conn):
        _check_gymer(conn, user_id)
        flag = 0
        if suggestion_item_id is not None:
            # row[2] and row[3] are the checked meal slot and food ID (_meal_row()).
            if not suggestions.is_active_item(conn, user_id, suggestion_item_id, row[2], row[3]):
                raise NotFound
            flag = 1
        return conn.execute(_ADD_MEAL, (*row, flag)).lastrowid


def replace_meal_item(
    conn: sqlite3.Connection,
    user_id: str,
    record_id: int,
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
    """Replace one of the user's meal items with a new row in one transaction; return its ID."""
    # An edit is a delete and a new row, so no snapshot changes in place; NotFound if not theirs.
    row = _meal_row(
        user_id,
        consumed_on,
        meal,
        fdc_id,
        food_name,
        grams,
        kcal,
        protein_g,
        carbohydrate_g,
        fat_g,
        fiber_g,
    )
    if not values.is_row_id(record_id):
        raise NotFound
    with transaction(conn):
        _check_gymer(conn, user_id)
        old = conn.execute(_MEAL_FOOD, (record_id, user_id)).fetchone()
        if old is None or conn.execute(_DELETE_MEAL, (record_id, user_id)).rowcount != 1:
            raise NotFound
        # A food logged from the coach's suggestions keeps the flag while it stays the same food
        # (the grams, day or meal slot changed); another food no longer counts (T9.34).
        flag = old["from_suggestion"] if old["fdc_id"] == row[3] else 0
        return conn.execute(_ADD_MEAL, (*row, flag)).lastrowid


def _meal_row(
    user_id: str,
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
) -> tuple:
    """Return a checked meal item row, ready for _ADD_MEAL."""
    return (
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


def _rpe(value: object) -> float:
    """Return an RPE on the scale of config (1 to 10, in steps of 0.5)."""
    rpe = values.in_range(value, "rpe", config.WORKOUT_RPE_RANGE)
    if not (rpe / config.WORKOUT_RPE_STEP).is_integer():
        raise values.StoreValueError("rpe", "is not a step of the scale")
    return rpe


def _workout_day(user_id: str, performed_on: date) -> tuple[str, str]:
    """Return a workout's checked user ID and day; a day after today (Berlin) is refused."""
    day = values.date_text(performed_on, "performed_on")
    # A workout is logged once it is done, whoever the caller (the owner's choice, T9.14); today is
    # the app's one Berlin day, as for `src/account.today()` and the diary (T9.13).
    if performed_on > metrics.berlin_day():
        raise values.StoreValueError("performed_on", "must not be after today")
    return (values.user_id(user_id), day)


def _checked_sets(sets: Sequence[ExerciseSet]) -> list[tuple]:
    """Return a workout's sets as checked rows for _ADD_SET (T9.14's list and ranges)."""
    if isinstance(sets, str | bytes) or not isinstance(sets, Sequence):
        raise values.StoreValueError("sets", "must be a list of exercise sets")
    if not all(isinstance(item, ExerciseSet) for item in sets):
        raise values.StoreValueError("sets", "must be a list of exercise sets")
    if len(sets) > config.WORKOUT_MAX_SETS:
        raise values.StoreValueError("sets", "are more than a workout may have")
    low, high = config.WORKOUT_REPS_RANGE
    known = exercises.exercise_ids()
    return [
        (
            values.choice(item.exercise_id, "exercise_id", known),
            values.whole_number(item.set_no, "set_no", minimum=1),
            values.whole_number(item.reps, "reps", minimum=low, maximum=high),
            values.in_range(item.weight_kg, "weight_kg", config.WORKOUT_WEIGHT_KG_RANGE),
            None if item.rpe is None else _rpe(item.rpe),
        )
        for item in sets
    ]


def _write_session(conn: sqlite3.Connection, session: tuple[str, str], checked: list[tuple]) -> int:
    """Write a checked session and its sets inside the caller's transaction; return its ID."""
    session_id = conn.execute(_ADD_SESSION, (*session, values.utc_text())).lastrowid
    for item in checked:
        conn.execute(_ADD_SET, (session_id, *item))
    return session_id


def add_workout_session(
    conn: sqlite3.Connection, user_id: str, *, performed_on: date, sets: Sequence[ExerciseSet]
) -> int:
    """Add a workout with its sets in one transaction; return the session's ID."""
    session = _workout_day(user_id, performed_on)
    checked = _checked_sets(sets)
    with transaction(conn):
        _check_gymer(conn, user_id)
        return _write_session(conn, session, checked)


def replace_workout_session(
    conn: sqlite3.Connection,
    user_id: str,
    session_id: int,
    *,
    performed_on: date,
    sets: Sequence[ExerciseSet],
) -> int:
    """Replace one of the user's workouts (an edit) in one transaction; return the new ID."""
    # Records are never changed in place (a trigger refuses it): the old session and its sets are
    # deleted and the edited one written as new rows, all or nothing, so a failed edit keeps the
    # old workout. NotFound if the session is not the user's.
    session = _workout_day(user_id, performed_on)
    checked = _checked_sets(sets)
    if not values.is_row_id(session_id):
        raise NotFound
    with transaction(conn):
        _check_gymer(conn, user_id)
        conn.execute(_DELETE_SETS, (session_id, user_id))
        if conn.execute(_DELETE_SESSION, (session_id, user_id)).rowcount != 1:
            raise NotFound
        return _write_session(conn, session, checked)


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
    """Add a working preference a coach approved (T9.7); return its ID; NotFound if no coach."""
    # Only coaches keep preferences since T9.24 (a gymer has no chat); the text was checked before
    # it was shown to the coach and again at the save (src/preferences.py).
    row = (
        values.user_id(user_id),
        values.text(text, "text", config.PREFERENCE_MAX_CHARS),
        values.utc_text(),
    )
    with transaction(conn):
        if role_of(conn, user_id) != "coach":
            raise NotFound
        return conn.execute(_ADD_PREFERENCE, row).lastrowid


def list_preferences(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> list[dict]:
    """Return a user's preferences, oldest first; only the user reads them, never a coach."""
    with authorised_read(conn, actor_id, subject_id, None, "preferences"):
        rows = conn.execute(_PREFERENCES, (subject_id,)).fetchall()
    return [dict(row) for row in rows]


def delete_record(conn: sqlite3.Connection, user_id: str, kind: RecordKind, record_id: int) -> None:
    """Delete one of the user's own records (a workout with its sets); NotFound if not theirs."""
    # A target their coach set is NotFound too (T9.17): _DELETE_TARGET leaves it in place.
    values.choice(kind, "kind", RECORD_KINDS)
    if not values.is_row_id(record_id):
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
