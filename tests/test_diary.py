"""The food and weight diary (T9.13): snapshots, edits, weights and the week read (AC-23)."""

from datetime import date, timedelta

import pytest

from src import config, diary, metrics
from src.store import access, records, users
from src.tools.food import Food
from tests.fakes import FOODS

GYMER = "gym-diary"
OATS, CHICKEN = FOODS[0], FOODS[1]
TODAY = date(2026, 10, 28)


def _with_profile(conn, user_id: str, name: str) -> None:
    """Create a gymer who has saved a profile entry (the diary needs one)."""
    users.create_user(conn, user_id, "gymer", name)
    records.add_profile_entry(
        conn, user_id, height_cm=180, age=30, sex="male", activity="light", goal="maintain"
    )


@pytest.fixture
def gymer(store_conn, monkeypatch):
    """Create a gymer with a saved profile and fix today to 2026-10-28 in Berlin."""
    _with_profile(store_conn, GYMER, "Diary")
    monkeypatch.setattr(metrics, "berlin_day", lambda moment=None: TODAY)
    return store_conn


def _log(conn, **change) -> int:
    """Log 150 g of the test oats at lunch today, with any field changed."""
    entry = {
        "food_name": OATS.description,
        "grams": 150,
        "meal": "lunch",
        "day": TODAY,
        "table": FOODS,
    }
    return diary.log_food(conn, GYMER, **{**entry, **change})


def test_150_g_stores_exactly_one_and_a_half_times_the_per_100_g_values(gymer):
    """AC-23: each nutrient of 150 g is exactly 1.5 times the table's per-100 g value."""
    _log(gymer)
    [item] = records.list_meal_items(gymer, GYMER, GYMER)
    for name in ("kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g"):
        assert item[name] == getattr(OATS, name) * 1.5, name
    assert (item["fdc_id"], item["food_name"], item["grams"]) == (1, OATS.description, 150.0)


@pytest.mark.parametrize("grams", [1.0, 37.5, 250.0, 2000.0])
def test_the_snapshot_is_per_100_g_values_times_grams_over_100(grams):
    """The snapshot is unrounded: per-100 g value x grams / 100."""
    values = diary.snapshot(OATS, grams)
    assert values["kcal"] == OATS.kcal * (grams / 100)
    assert values["protein_g"] == OATS.protein_g * (grams / 100)


def test_fibre_not_reported_stays_empty(gymer):
    """A food USDA reports no fibre for keeps an empty fibre value, never 0."""
    _log(gymer, food_name=CHICKEN.description)
    [item] = records.list_meal_items(gymer, GYMER, GYMER)
    assert item["fiber_g"] is None


def test_the_snapshot_stays_the_same_when_the_foods_table_changes(gymer):
    """An entry keeps the values of the table it was logged with; a new table changes nothing."""
    _log(gymer)
    changed = (OATS.model_copy(update={"kcal": 999.0, "protein_g": 1.0}),)
    _log(gymer, meal="dinner", table=changed)
    first, second = records.list_meal_items(gymer, GYMER, GYMER)
    assert (first["kcal"], first["protein_g"]) == (570.0, OATS.protein_g * 1.5)
    assert (second["kcal"], second["protein_g"]) == (999.0 * 1.5, 1.5)


def test_an_edit_replaces_the_row_with_a_snapshot_from_the_current_table(gymer):
    """Editing food, grams, meal and day writes a new row from today's table; the old one goes."""
    old = _log(gymer)
    changed = (OATS, CHICKEN.model_copy(update={"kcal": 200.0}))
    yesterday = TODAY - timedelta(days=1)
    diary.edit_food(
        gymer,
        GYMER,
        old,
        food_name=CHICKEN.description,
        grams=50,
        meal="dinner",
        day=yesterday,
        table=changed,
    )
    [item] = records.list_meal_items(gymer, GYMER, GYMER)
    assert (item["food_name"], item["grams"], item["meal"]) == (CHICKEN.description, 50.0, "dinner")
    assert (item["consumed_on"], item["kcal"]) == (yesterday.isoformat(), 100.0)


def test_editing_another_users_entry_is_not_found(gymer):
    """An entry that is not the user's cannot be edited."""
    _with_profile(gymer, "gym-other", "Other")
    theirs = diary.log_food(
        gymer, "gym-other", food_name=OATS.description, grams=100, meal="lunch", day=TODAY,
        table=FOODS,
    )  # fmt: skip
    with pytest.raises(access.NotFound):
        diary.edit_food(
            gymer, GYMER, theirs, food_name=OATS.description, grams=1, meal="lunch", day=TODAY,
            table=FOODS,
        )  # fmt: skip
    [item] = records.list_meal_items(gymer, "gym-other", "gym-other")
    assert item["grams"] == 100.0


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"grams": 0.0}, "diary.grams_range"),
        ({"grams": config.FOOD_MAX_GRAMS + 1}, "diary.grams_range"),
        ({"grams": float("nan")}, "diary.grams_range"),
        ({"grams": "150"}, "diary.grams_range"),
        ({"grams": True}, "diary.grams_range"),
        ({"meal": "brunch"}, "diary.meal_needed"),
        ({"meal": None}, "diary.meal_needed"),
        ({"food_name": "Oats"}, "diary.food_needed"),
        ({"food_name": None}, "diary.food_needed"),
        ({"day": TODAY + timedelta(days=1)}, "diary.day_range"),
        ({"day": TODAY - timedelta(days=config.DIARY_MAX_DAYS_BACK + 1)}, "diary.day_range"),
        ({"day": "2026-10-28"}, "diary.day_range"),
    ],
)
def test_a_bad_entry_is_refused_with_a_fixed_code_and_writes_nothing(gymer, change, code):
    """Grams out of range, an unknown meal or food, or a day out of range: a code, no row."""
    with pytest.raises(diary.DiaryError) as caught:
        _log(gymer, **change)
    assert caught.value.code == code
    assert records.list_meal_items(gymer, GYMER, GYMER) == []


@pytest.mark.parametrize("days_back", [0, config.DIARY_MAX_DAYS_BACK])
def test_today_and_the_oldest_day_allowed_are_accepted(gymer, days_back):
    """The range's two ends are both allowed."""
    _log(gymer, day=TODAY - timedelta(days=days_back))
    assert len(records.list_meal_items(gymer, GYMER, GYMER)) == 1


def test_a_missing_foods_table_is_a_diary_error(gymer, tmp_path, monkeypatch):
    """No foods table: the fixed code, never the table error's text (which names the path)."""
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "missing.csv")
    with pytest.raises(diary.DiaryError) as caught:
        diary.log_food(gymer, GYMER, food_name="x", grams=100, meal="lunch", day=TODAY)
    assert caught.value.code == "diary.food_table"
    assert str(tmp_path) not in str(caught.value)
    assert caught.value.__suppress_context__


def test_an_unreadable_foods_table_is_a_diary_error(gymer, monkeypatch):
    """A permission error on the table: the fixed code, not the OS error and its path."""

    def unreadable(path=None):
        """Fail as reading a file the app may not open does."""
        raise PermissionError("C:/secret/path/usda_foods.csv")

    monkeypatch.setattr(diary, "load_food_table", unreadable)
    with pytest.raises(diary.DiaryError) as caught:
        diary.log_food(gymer, GYMER, food_name="x", grams=100, meal="lunch", day=TODAY)
    assert caught.value.code == "diary.food_table"
    assert "secret" not in str(caught.value) + repr(caught.value)
    assert records.list_meal_items(gymer, GYMER, GYMER) == []


def test_the_real_foods_table_gives_a_snapshot(gymer):
    """A name from the committed USDA table is found exactly."""
    food = diary.find_food("Alaska Pollock, raw")
    assert isinstance(food, Food)
    assert food.fdc_id == 2768188


@pytest.mark.parametrize(
    ("value", "system", "kg"),
    [(80.0, "metric", 80.0), (176.4, "imperial", 176.4 * 0.45359237)],
)
def test_a_weight_in_the_chosen_units_is_stored_in_kg(gymer, value, system, kg):
    """A weight typed in kg or lb is stored in kg, on the chosen day."""
    diary.log_weight(gymer, GYMER, value=value, system=system, day=TODAY)
    [weight] = records.list_body_measurements(gymer, GYMER, GYMER)
    assert weight["weight_kg"] == pytest.approx(kg)
    assert weight["measured_on"] == TODAY.isoformat()


def test_a_stored_weight_reads_back_in_pounds():
    """Both ways: 80 kg typed in lb and read back gives the same lb (within rounding)."""
    from src import units

    pounds = units.weight_in(80.0, "imperial")
    assert units.weight_in(units.weight_to_kg(pounds, "imperial"), "imperial") == pounds


@pytest.mark.parametrize(
    "value", [10.0, 400.0, float("nan"), "80", True, None], ids=str
)  # fmt: skip
def test_a_weight_out_of_range_is_refused(gymer, value):
    """A weight outside the profile's range, or not a number, gives the fixed code."""
    with pytest.raises(diary.DiaryError) as caught:
        diary.log_weight(gymer, GYMER, value=value, system="metric", day=TODAY)
    assert caught.value.code == "diary.weight_range"
    assert records.list_body_measurements(gymer, GYMER, GYMER) == []


def test_a_weight_on_a_future_day_is_refused(gymer):
    """The weight's day keeps the diary's range too."""
    with pytest.raises(diary.DiaryError):
        diary.log_weight(gymer, GYMER, value=80.0, system="metric", day=TODAY + timedelta(days=1))


def test_the_day_lists_hold_only_that_day(gymer):
    """day_items and day_weights read one day of the user's own entries."""
    _log(gymer)
    _log(gymer, day=TODAY - timedelta(days=1))
    diary.log_weight(gymer, GYMER, value=80.0, system="metric", day=TODAY)
    assert [item["consumed_on"] for item in diary.day_items(gymer, GYMER, TODAY)] == ["2026-10-28"]
    assert len(diary.day_weights(gymer, GYMER, TODAY - timedelta(days=1))) == 0


def test_read_week_gives_the_metrics_of_the_stored_records(gymer):
    """The week read from the store is what week_metrics gives for the same rows."""
    monday = metrics.week_start(TODAY)
    _log(gymer, day=monday)
    _log(gymer, day=TODAY, grams=100)
    diary.log_weight(gymer, GYMER, value=80.0, system="metric", day=monday - timedelta(days=2))
    diary.log_weight(gymer, GYMER, value=79.0, system="metric", day=TODAY)
    records.add_target(
        gymer,
        GYMER,
        kcal=2500,
        protein_g=150,
        carbs_g=250,
        fat_g=70,
        set_by="system",
        effective_from=monday,
    )
    week = diary.read_week(gymer, GYMER, GYMER, monday)
    assert (week.logged_days, week.days_in_week) == (2, 7)
    assert week.average.kcal == pytest.approx((570 + 380) / 2)
    assert week.difference["kcal"] == pytest.approx(475 - 2500)
    assert week.weight_change_kg == pytest.approx(-1.0)


def test_read_week_goes_through_the_access_checks(gymer):
    """A user who may not read the records gets NotFound, as from any store read."""
    users.create_user(gymer, "a-coach", "coach", "Coach")
    with pytest.raises(access.NotFound):
        diary.read_week(gymer, "a-coach", GYMER, metrics.week_start(TODAY))


@pytest.mark.parametrize("write", ["food", "weight", "edit"])
def test_a_gymer_with_no_saved_profile_logs_nothing(gymer, write):
    """No profile entry (no opt-in, no 18+ check): every diary write is refused, nothing stored."""
    old = _log(gymer)
    [entry] = records.list_profile_entries(gymer, GYMER, GYMER)
    records.delete_record(gymer, GYMER, "profile_entries", entry["id"])
    calls = {
        "food": lambda: _log(gymer),
        "weight": lambda: diary.log_weight(gymer, GYMER, value=80.0, system="metric", day=TODAY),
        "edit": lambda: diary.edit_food(
            gymer,
            GYMER,
            old,
            food_name=OATS.description,
            grams=1,
            meal="lunch",
            day=TODAY,
            table=FOODS,
        ),  # fmt: skip
    }
    with pytest.raises(diary.DiaryError) as caught:
        calls[write]()
    assert caught.value.code == "diary.profile_first"
    [meal] = records.list_meal_items(gymer, GYMER, GYMER)
    assert (meal["id"], meal["grams"]) == (old, 150.0)
    assert records.list_body_measurements(gymer, GYMER, GYMER) == []
