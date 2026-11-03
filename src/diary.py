"""A gymer's food and weight diary (T9.13): food logged with a nutrient snapshot, dated weights.

A food is one of the USDA table's own names (the Today page's dropdown, T4.8), so it is looked up
exactly, never matched. Its snapshot is the per-100 g values x grams / 100, unrounded (the views
round), taken from the table when the entry is written, so a later table never changes it (AC-23);
an edit writes a new row with a snapshot from the current table. A weight is typed in the user's
units and stored in kg. The day is today in `Europe/Berlin` or up to `config.DIARY_MAX_DAYS_BACK`
days back, never a future day. A gymer logs only after saving a profile (owner's choice,
2026-11-03, compliance review of T9.13): that first Save carries the opt-in tick and the profile's
18+ check, so the diary never holds data from someone who skipped them. Each error is a
`DiaryError` whose code is the i18n key of its message, which never repeats what was typed.
"""

import sqlite3
from collections.abc import Sequence
from datetime import date, timedelta
from typing import get_args

from src import config, metrics, units
from src.store import records
from src.tools.food import Food, FoodTableError, load_food_table


class DiaryError(ValueError):
    """A diary entry that cannot be written; `code` is the i18n key of its message."""

    def __init__(self, code: str) -> None:
        """Keep the message's key (the message never holds the value)."""
        super().__init__(code)
        self.code = code


def snapshot(food: Food, grams: float) -> dict[str, float | None]:
    """Return the nutrients of the grams eaten: each per-100 g value x grams / 100, unrounded."""
    # grams / 100 first: 150 g is a factor of exactly 1.5, so the snapshot is exactly 1.5 times
    # the table's values (AC-23).
    factor = grams / 100
    return {
        "kcal": food.kcal * factor,
        "protein_g": food.protein_g * factor,
        "carbohydrate_g": food.carbohydrate_g * factor,
        "fat_g": food.fat_g * factor,
        "fiber_g": None if food.fiber_g is None else food.fiber_g * factor,
    }


def check_day(day: object, today: date) -> date:
    """Return the day if it is today or up to DIARY_MAX_DAYS_BACK days back."""
    if not isinstance(day, date) or not (
        today - timedelta(days=config.DIARY_MAX_DAYS_BACK) <= day <= today
    ):
        raise DiaryError("diary.day_range")
    return day


def check_grams(grams: object) -> float:
    """Return the grams if they are a number from FOOD_MIN_GRAMS to FOOD_MAX_GRAMS."""
    # A number only (no strings or booleans); NaN fails both comparisons.
    if (
        isinstance(grams, bool)
        or not isinstance(grams, int | float)
        or not config.FOOD_MIN_GRAMS <= grams <= config.FOOD_MAX_GRAMS
    ):
        raise DiaryError("diary.grams_range")
    return float(grams)


def check_meal(meal: object) -> records.Meal:
    """Return the meal if it is breakfast, lunch, dinner or snack."""
    if meal not in get_args(records.Meal):
        raise DiaryError("diary.meal_needed")
    return meal


def check_profile_saved(conn: sqlite3.Connection, user_id: str) -> None:
    """Raise DiaryError unless the gymer has saved a profile (with its opt-in and 18+ check)."""
    if not records.list_profile_entries(conn, user_id, user_id):
        raise DiaryError("diary.profile_first")


def find_food(name: object, table: Sequence[Food] | None = None) -> Food:
    """Return the food with exactly this name in the USDA table."""
    try:
        foods = load_food_table() if table is None else table
    except FoodTableError, OSError, UnicodeDecodeError:
        # Missing, broken, unreadable (e.g. a permission error) or not UTF-8: one fixed code.
        raise DiaryError("diary.food_table") from None
    found = next((food for food in foods if food.description == name), None)
    if found is None:
        raise DiaryError("diary.food_needed")
    return found


def _meal_item(
    food_name: object,
    grams: object,
    meal: object,
    day: object,
    today: date,
    table: Sequence[Food] | None,
) -> dict:
    """Return the checked fields of a meal item, with the snapshot from the table."""
    checked_grams = check_grams(grams)
    checked_meal = check_meal(meal)
    checked_day = check_day(day, today)
    food = find_food(food_name, table)
    return {
        "consumed_on": checked_day,
        "meal": checked_meal,
        "fdc_id": food.fdc_id,
        "food_name": food.description,
        "grams": checked_grams,
        **snapshot(food, checked_grams),
    }


def log_food(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    food_name: object,
    grams: object,
    meal: object,
    day: object,
    table: Sequence[Food] | None = None,
) -> int:
    """Log a food eaten by the gymer with its snapshot; return the new entry's ID."""
    item = _meal_item(food_name, grams, meal, day, metrics.berlin_day(), table)
    check_profile_saved(conn, user_id)
    return records.add_meal_item(conn, user_id, **item)


def edit_food(
    conn: sqlite3.Connection,
    user_id: str,
    record_id: int,
    *,
    food_name: object,
    grams: object,
    meal: object,
    day: object,
    table: Sequence[Food] | None = None,
) -> int:
    """Replace one of the gymer's entries with a new row, its snapshot from the current table."""
    item = _meal_item(food_name, grams, meal, day, metrics.berlin_day(), table)
    check_profile_saved(conn, user_id)
    return records.replace_meal_item(conn, user_id, record_id, **item)


def log_weight(
    conn: sqlite3.Connection, user_id: str, *, value: object, system: units.UnitSystem, day: object
) -> int:
    """Log a weight typed in the user's units, stored in kg; return the new entry's ID."""
    checked_day = check_day(day, metrics.berlin_day())
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DiaryError("diary.weight_range")
    weight_kg = units.weight_to_kg(float(value), system)
    low, high = config.PROFILE_WEIGHT_KG_RANGE
    if not low <= weight_kg <= high:  # NaN fails it too
        raise DiaryError("diary.weight_range")
    check_profile_saved(conn, user_id)
    return records.add_body_measurement(conn, user_id, weight_kg=weight_kg, measured_on=checked_day)


def day_items(conn: sqlite3.Connection, user_id: str, day: date) -> list[dict]:
    """Return the gymer's own food entries of one day, in the order they were logged."""
    return records.list_meal_items(conn, user_id, user_id, start=day, end=day)


def day_weights(conn: sqlite3.Connection, user_id: str, day: date) -> list[dict]:
    """Return the gymer's own weights of one day, in the order they were logged."""
    return records.list_body_measurements(conn, user_id, user_id, start=day, end=day)


def read_week(
    conn: sqlite3.Connection, actor_id: str, subject_id: str, monday: date
) -> metrics.WeekMetrics:
    """Return a user's week metrics, read through the store's access checks (T9.15, T9.16)."""
    # Each read is authorised for the acting user (a coach: the scope must be shared, and the read
    # is audited), so a coach without both nutrition and body gets NotFound here; a view that shows
    # "not shared" per scope (T9.15) reads the scopes it may and passes [] for the others to
    # metrics.week_metrics(). Weights before the Monday are read for the week's change.
    sunday = metrics.week_days(monday)[-1]
    meals = records.list_meal_items(conn, actor_id, subject_id, start=monday, end=sunday)
    weights = records.list_body_measurements(conn, actor_id, subject_id, end=sunday)
    targets = records.list_targets(conn, actor_id, subject_id)
    return metrics.week_metrics(meals, weights, targets, monday)
