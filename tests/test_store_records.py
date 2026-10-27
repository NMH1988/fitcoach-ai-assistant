"""A gymer's records in the store (T9.6): written, read back, never changed in place, deleted."""

import sqlite3
from datetime import date

import pytest

from src import config
from src.store import access, records, users, values
from tests import store_world as world

GYMER = "gym-1"
OTHER = "gym-2"
DAY = date(2026, 10, 26)


@pytest.fixture
def gymers(store_conn):
    """Create two gymers with no records."""
    users.create_user(store_conn, GYMER, "gymer", "One")
    users.create_user(store_conn, OTHER, "gymer", "Two")
    return store_conn


def _count(conn, table):
    """Return the number of rows in a table."""
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_records_are_read_back_as_written(gymers):
    """Every kind of record is returned with the values it was written with."""
    world.add_records(gymers, GYMER)
    [entry] = records.list_profile_entries(gymers, GYMER, GYMER)
    assert (entry["height_cm"], entry["age"], entry["sex"]) == (world.HEIGHT, 37, "male")
    assert entry["recorded_at"].endswith("+00:00")
    [weight] = records.list_body_measurements(gymers, GYMER, GYMER)
    assert (weight["weight_kg"], weight["measured_on"]) == (world.WEIGHT, "2026-10-26")
    [target] = records.list_targets(gymers, GYMER, GYMER)
    assert (target["kcal"], target["set_by"], target["calc_version"]) == (2345.0, "system", "t9.5")
    [meal] = records.list_meal_items(gymers, GYMER, GYMER)
    assert (meal["food_name"], meal["grams"], meal["kcal"], meal["fiber_g"]) == (
        "Oats, rolled",
        150.0,
        571.5,
        15.0,
    )
    [session] = records.list_workout_sessions(gymers, GYMER, GYMER)
    assert session["performed_on"] == "2026-10-26"
    assert session["sets"] == [
        {"exercise_id": "squat", "set_no": 1, "reps": 5, "weight_kg": 100.0, "rpe": 8.0},
        {"exercise_id": "squat", "set_no": 2, "reps": 5, "weight_kg": 100.0, "rpe": None},
    ]
    [preference] = records.list_preferences(gymers, GYMER, GYMER)
    assert preference["text"] == "vegetarian"


def test_a_user_sees_only_their_own_rows(gymers):
    """Another gymer's records never appear in a user's lists."""
    world.add_records(gymers, OTHER)
    assert records.list_meal_items(gymers, GYMER, GYMER) == []
    assert records.list_workout_sessions(gymers, GYMER, GYMER) == []


def test_day_ranges_are_inclusive(gymers):
    """start and end keep the days between them, both included."""
    for day in (25, 26, 27, 28):
        records.add_body_measurement(
            gymers, GYMER, weight_kg=80 + day / 100, measured_on=date(2026, 10, day)
        )
    rows = records.list_body_measurements(
        gymers, GYMER, GYMER, start=date(2026, 10, 26), end=date(2026, 10, 27)
    )
    assert [row["measured_on"] for row in rows] == ["2026-10-26", "2026-10-27"]
    assert len(records.list_body_measurements(gymers, GYMER, GYMER, start=date(2026, 10, 28))) == 1
    assert len(records.list_body_measurements(gymers, GYMER, GYMER, end=date(2026, 10, 25))) == 1


def test_a_session_with_no_sets_is_listed_with_none(gymers):
    """A workout saved without sets comes back with an empty list of sets."""
    records.add_workout_session(gymers, GYMER, performed_on=DAY, sets=[])
    [session] = records.list_workout_sessions(gymers, GYMER, GYMER)
    assert session["sets"] == []


def test_a_new_target_is_a_new_row_and_the_old_one_stays(gymers):
    """Setting a target twice keeps both rows; the latest started is the active one."""
    for kcal, day in ((2500.0, date(2026, 10, 1)), (2300.0, date(2026, 10, 20))):
        records.add_target(
            gymers,
            GYMER,
            kcal=kcal,
            protein_g=150,
            carbs_g=250,
            fat_g=70,
            set_by="system",
            effective_from=day,
        )
    assert [t["kcal"] for t in records.list_targets(gymers, GYMER, GYMER)] == [2500.0, 2300.0]


def test_a_new_profile_entry_is_a_new_row_and_the_old_one_stays(gymers):
    """Saving the profile again adds an entry; the earlier one is kept as history."""
    for age in (36, 37):
        records.add_profile_entry(
            gymers, GYMER, height_cm=180, age=age, sex="female", activity="light", goal="maintain"
        )
    assert [e["age"] for e in records.list_profile_entries(gymers, GYMER, GYMER)] == [36, 37]


@pytest.mark.parametrize(
    ("table", "statement"),
    [
        ("meal_items", "UPDATE meal_items SET kcal = 1, grams = 1"),
        ("profile_entries", "UPDATE profile_entries SET age = 99"),
        ("nutrition_targets", "UPDATE nutrition_targets SET kcal = 1"),
    ],
)
def test_snapshots_profile_entries_and_targets_are_never_changed_in_place(gymers, table, statement):
    """An UPDATE on a snapshot, a profile entry or a target fails and changes nothing."""
    world.add_records(gymers, GYMER)
    before = [dict(r) for r in gymers.execute(f"SELECT * FROM {table}")]
    with pytest.raises(sqlite3.IntegrityError, match="never changed in place"):
        gymers.execute(statement)
    assert [dict(r) for r in gymers.execute(f"SELECT * FROM {table}")] == before


def test_the_record_functions_offer_no_update():
    """The modules have no function that changes a stored record (an edit is delete and add)."""
    names = [name for name in dir(records) if not name.startswith("_")]
    assert not [name for name in names if name.startswith(("update", "edit", "set_", "change"))]


@pytest.mark.parametrize("kind", records.RECORD_KINDS)
def test_a_user_deletes_one_of_their_own_records(gymers, kind):
    """delete_record removes the one row (a workout with its sets) and nothing else."""
    world.add_records(gymers, GYMER)
    world.add_records(gymers, OTHER)
    [mine] = [
        row["id"] for row in gymers.execute(f"SELECT id FROM {kind} WHERE user_id = ?", (GYMER,))
    ]
    records.delete_record(gymers, GYMER, kind, mine)
    assert (
        gymers.execute(f"SELECT count(*) FROM {kind} WHERE user_id = ?", (GYMER,)).fetchone()[0]
        == 0
    )
    assert (
        gymers.execute(f"SELECT count(*) FROM {kind} WHERE user_id = ?", (OTHER,)).fetchone()[0]
        == 1
    )
    if kind == "workout_sessions":
        assert _count(gymers, "exercise_sets") == 2  # the other gymer's two sets


@pytest.mark.parametrize("kind", records.RECORD_KINDS)
def test_deleting_someone_elses_or_a_missing_record_is_not_found(gymers, kind):
    """Another user's record, or an ID that does not exist, gives NotFound and deletes nothing."""
    world.add_records(gymers, OTHER)
    [theirs] = [row["id"] for row in gymers.execute(f"SELECT id FROM {kind}")]
    for record_id in (theirs, 999, None, "1"):
        with pytest.raises(access.NotFound):
            records.delete_record(gymers, GYMER, kind, record_id)
    assert _count(gymers, kind) == 1


def test_an_unknown_kind_is_refused(gymers):
    """delete_record takes only the record tables, never another name."""
    with pytest.raises(values.StoreValueError):
        records.delete_record(gymers, GYMER, "users", 1)


@pytest.mark.parametrize(
    ("function", "kwargs"),
    [
        (records.add_body_measurement, {"weight_kg": -80.0, "measured_on": DAY}),
        (records.add_body_measurement, {"weight_kg": float("nan"), "measured_on": DAY}),
        (records.add_body_measurement, {"weight_kg": 80.0, "measured_on": "2026-10-26"}),
        (
            records.add_profile_entry,
            {"height_cm": 180, "age": 30, "sex": "other", "activity": "light", "goal": "maintain"},
        ),
        (
            records.add_profile_entry,
            {"height_cm": 180, "age": 30.5, "sex": "male", "activity": "light", "goal": "maintain"},
        ),
        (
            records.add_target,
            {
                "kcal": -1,
                "protein_g": 1,
                "carbs_g": 1,
                "fat_g": 1,
                "set_by": "system",
                "effective_from": DAY,
            },
        ),
        (
            records.add_target,
            {
                "kcal": 1,
                "protein_g": 1,
                "carbs_g": 1,
                "fat_g": 1,
                "set_by": "model",
                "effective_from": DAY,
            },
        ),
        (records.add_preference, {"text": "   "}),
    ],
)
def test_invalid_values_are_refused_before_anything_is_written(gymers, function, kwargs):
    """A bad value raises StoreValueError and leaves every table empty."""
    with pytest.raises(values.StoreValueError):
        function(gymers, GYMER, **kwargs)
    total = sum(_count(gymers, t) for t in records.RECORD_KINDS)
    assert total == 0


@pytest.mark.parametrize(
    "change",
    [
        {"grams": 0},
        {"kcal": -1},
        {"fiber_g": -0.5},
        {"fdc_id": 0},
        {"meal": "brunch"},
        {"food_name": ""},
    ],
)
def test_a_meal_item_with_a_bad_value_is_refused(gymers, change):
    """grams above zero, nutrients zero or more, a known meal and a food are required."""
    item = {
        "consumed_on": DAY,
        "meal": "lunch",
        "fdc_id": 1,
        "food_name": "Oats",
        "grams": 100.0,
        "kcal": 381.0,
        "protein_g": 13.3,
        "carbohydrate_g": 67.6,
        "fat_g": 6.5,
        "fiber_g": None,
    }
    with pytest.raises(values.StoreValueError):
        records.add_meal_item(gymers, GYMER, **{**item, **change})
    assert _count(gymers, "meal_items") == 0


def test_a_workout_with_one_bad_set_writes_nothing(gymers):
    """A session and its sets are written together or not at all."""
    sets = [records.ExerciseSet("squat", 1, 5, 100.0), records.ExerciseSet("squat", 2, -5, 100.0)]
    with pytest.raises(values.StoreValueError):
        records.add_workout_session(gymers, GYMER, performed_on=DAY, sets=sets)
    duplicate = [
        records.ExerciseSet("squat", 1, 5, 100.0),
        records.ExerciseSet("squat", 1, 5, 90.0),
    ]
    with pytest.raises(sqlite3.IntegrityError):
        records.add_workout_session(gymers, GYMER, performed_on=DAY, sets=duplicate)
    assert _count(gymers, "workout_sessions") == _count(gymers, "exercise_sets") == 0


# One valid call of every add_* function, for a given owner.
ADDS = {
    "add_profile_entry": lambda conn, owner: records.add_profile_entry(
        conn, owner, height_cm=180, age=30, sex="male", activity="light", goal="maintain"
    ),
    "add_body_measurement": lambda conn, owner: records.add_body_measurement(
        conn, owner, weight_kg=80.0, measured_on=DAY
    ),
    "add_target": lambda conn, owner: records.add_target(
        conn,
        owner,
        kcal=2500,
        protein_g=150,
        carbs_g=250,
        fat_g=70,
        set_by="system",
        effective_from=DAY,
    ),
    "add_meal_item": lambda conn, owner: records.add_meal_item(
        conn,
        owner,
        consumed_on=DAY,
        meal="lunch",
        fdc_id=1,
        food_name="Oats",
        grams=100.0,
        kcal=381.0,
        protein_g=13.3,
        carbohydrate_g=67.6,
        fat_g=6.5,
        fiber_g=None,
    ),
    "add_workout_session": lambda conn, owner: records.add_workout_session(
        conn, owner, performed_on=DAY, sets=[]
    ),
    "add_preference": lambda conn, owner: records.add_preference(conn, owner, "vegetarian"),
}


def test_every_add_function_is_in_the_gymer_only_test():
    """ADDS lists every add_* function of records, so none escapes the test below."""
    assert {name for name in dir(records) if name.startswith("add_")} == set(ADDS)


@pytest.mark.parametrize("add", ADDS)
@pytest.mark.parametrize("owner", [world.MISSING, "a-coach"])
def test_only_a_gymer_keeps_records(gymers, owner, add):
    """A missing user or a coach gets NotFound from every add_* function, and nothing is written."""
    users.create_user(gymers, "a-coach", "coach", "Coach")
    with pytest.raises(access.NotFound):
        ADDS[add](gymers, owner)
    total = sum(_count(gymers, t) for t in records.RECORD_KINDS)
    assert total == 0
    ADDS[add](gymers, GYMER)  # the same call works for a gymer


def test_a_target_cannot_claim_to_be_set_by_a_coach(gymers):
    """Until T9.17 adds the coach's path, a gymer's own target is set by the system or the user."""
    with pytest.raises(values.StoreValueError, match="set_by"):
        records.add_target(
            gymers,
            GYMER,
            kcal=2500,
            protein_g=150,
            carbs_g=250,
            fat_g=70,
            set_by="coach",
            effective_from=DAY,
        )


@pytest.mark.parametrize("field", ["fdc_id", "grams"])
def test_a_number_too_large_for_sqlite_is_a_store_value_error(gymers, field):
    """10**30 is refused with the field's name, not an OverflowError from sqlite3."""
    item = {
        "consumed_on": DAY,
        "meal": "lunch",
        "fdc_id": 1,
        "food_name": "Oats",
        "grams": 100.0,
        "kcal": 381.0,
        "protein_g": 13.3,
        "carbohydrate_g": 67.6,
        "fat_g": 6.5,
        "fiber_g": None,
    }
    if field == "fdc_id":
        with pytest.raises(values.StoreValueError, match="fdc_id"):
            records.add_meal_item(gymers, GYMER, **{**item, "fdc_id": 10**30})
    else:
        records.add_meal_item(gymers, GYMER, **{**item, "grams": 10**30})  # a REAL holds it


@pytest.mark.parametrize(
    ("function", "kwargs"),
    [
        (
            records.add_profile_entry,
            {"height_cm": 180, "age": 15, "sex": "male", "activity": "light", "goal": "maintain"},
        ),
        (
            records.add_profile_entry,
            {"height_cm": 180, "age": 101, "sex": "male", "activity": "light", "goal": "maintain"},
        ),
        (
            records.add_profile_entry,
            {"height_cm": 50, "age": 30, "sex": "male", "activity": "light", "goal": "maintain"},
        ),
        (records.add_body_measurement, {"weight_kg": 1e300, "measured_on": DAY}),
        (records.add_body_measurement, {"weight_kg": 10.0, "measured_on": DAY}),
        (
            records.add_target,
            {
                "kcal": config.CALORIE_FLOOR_KCAL - 1,
                "protein_g": 1,
                "carbs_g": 1,
                "fat_g": 1,
                "set_by": "user",
                "effective_from": DAY,
            },
        ),
    ],
)
def test_the_profile_ranges_and_the_calorie_floor_hold_in_the_store(gymers, function, kwargs):
    """A minor, a height or weight out of the form's ranges, or a target under the floor fails."""
    with pytest.raises(values.StoreValueError):
        function(gymers, GYMER, **kwargs)
    total = sum(_count(gymers, t) for t in records.RECORD_KINDS)
    assert total == 0


def test_a_target_at_the_calorie_floor_is_accepted(gymers):
    """The floor itself is allowed."""
    records.add_target(
        gymers,
        GYMER,
        kcal=config.CALORIE_FLOOR_KCAL,
        protein_g=1,
        carbs_g=1,
        fat_g=1,
        set_by="user",
        effective_from=DAY,
    )
    assert len(records.list_targets(gymers, GYMER, GYMER)) == 1


def test_a_user_is_created_once_with_one_role(store_conn):
    """create_user stores the role; a second account with the same ID is refused."""
    users.create_user(store_conn, GYMER, "gymer", "One")
    assert users.find_user(store_conn, GYMER)["role"] == "gymer"
    assert users.find_user(store_conn, OTHER) is None
    with pytest.raises(sqlite3.IntegrityError):
        users.create_user(store_conn, GYMER, "coach", "One")
    with pytest.raises(values.StoreValueError):
        users.create_user(store_conn, OTHER, "admin", "Two")
