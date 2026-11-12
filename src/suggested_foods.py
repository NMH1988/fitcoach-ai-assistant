"""The foods a coach suggests to a client (T9.34): the list, its nutrients, the one-click log.

The store keeps the list and decides who may write and read it (`src/store/suggestions.py`); this
module turns the coach's rows (meal slot, a USDA food name, grams) into the store's items, works
out each item's nutrients from the USDA table for the pages, and logs an item for the gymer. Foods
are the USDA table's own names (T4.8), looked up exactly, never matched, as the diary does.

A list is the coach's suggestion, not a meal plan: its total is shown next to the client's target
as information, and the calorie floor does not apply to it (the gymer still logs any other food,
and the floor holds for targets, docs/PRD.md). Nothing here reaches a model.

Each error is a `diary.DiaryError` whose code is the i18n key of its message, which never repeats
what was typed or stored.
"""

import sqlite3
from collections.abc import Iterable, Sequence

from src import diary, metrics
from src.store import records, suggestions
from src.store.access import NotFound
from src.tools.food import Food, FoodTableError, load_food_table

NUTRIENTS = ("kcal", "protein_g", "carbohydrate_g", "fat_g")


def build_items(
    rows: Iterable[tuple[object, object, object]], table: Sequence[Food] | None = None
) -> list[suggestions.SuggestedFood]:
    """Return the coach's rows (meal slot, food name, grams) as the store's suggested foods."""
    items = []
    for meal, name, grams in rows:
        food = diary.find_food(name, table)
        items.append(
            suggestions.SuggestedFood(
                meal=diary.check_meal(meal),
                fdc_id=food.fdc_id,
                food_name=food.description,
                grams=diary.check_grams(grams),
            )
        )
    keys = [(item.meal, item.fdc_id) for item in items]
    if len(set(keys)) != len(keys):
        raise diary.DiaryError("suggestions.twice")
    return items


def save_suggestions(
    conn: sqlite3.Connection,
    coach_id: str,
    client_id: str,
    rows: Iterable[tuple[object, object, object]],
    table: Sequence[Food] | None = None,
) -> int:
    """Save the coach's rows as the client's new list (the store checks access); return its ID."""
    return suggestions.add_client_suggestions(conn, coach_id, client_id, build_items(rows, table))


def _table(table: Sequence[Food] | None) -> Sequence[Food] | None:
    """Return the USDA table, or None when it cannot be read (the nutrients are then left out)."""
    if table is not None:
        return table
    try:
        return load_food_table()
    except FoodTableError, OSError, UnicodeDecodeError:
        return None


def with_nutrients(items: Sequence[dict], table: Sequence[Food] | None = None) -> list[dict]:
    """Return each item with its nutrients for its grams, from the current USDA table (or None)."""
    foods = _table(table)
    by_id = {} if foods is None else {food.fdc_id: food for food in foods}
    found = []
    for item in items:
        food = by_id.get(item["fdc_id"])
        nutrients = (
            dict.fromkeys(NUTRIENTS)
            if food is None
            else {key: diary.snapshot(food, item["grams"])[key] for key in NUTRIENTS}
        )
        found.append({**item, **nutrients})
    return found


def totals(items: Sequence[dict]) -> dict[str, float | None]:
    """Return the items' total nutrients; a nutrient is None if any item lacks it."""
    return {
        key: (
            None if any(item[key] is None for item in items) else sum(item[key] for item in items)
        )
        for key in NUTRIENTS
    }


def log_suggested(
    conn: sqlite3.Connection,
    user_id: str,
    item_id: object,
    *,
    grams: object,
    day: object,
    table: Sequence[Food] | None = None,
) -> int:
    """Log an item of the gymer's active list with the grams chosen; return the new entry's ID."""
    # The store checks again, in its write transaction, that the item is on the active list.
    checked_grams = diary.check_grams(grams)
    checked_day = diary.check_day(day, metrics.berlin_day())
    diary.check_profile_saved(conn, user_id)
    active = suggestions.current_suggestions(conn, user_id, user_id)
    item = next(
        (found for found in (active or {}).get("items", []) if found["id"] == item_id), None
    )
    if item is None:
        raise diary.DiaryError("suggestions.gone")
    food = diary.find_food(item["food_name"], table)
    if food.fdc_id != item["fdc_id"]:
        raise diary.DiaryError("diary.food_needed")
    try:
        return records.add_meal_item(
            conn,
            user_id,
            consumed_on=checked_day,
            meal=item["meal"],
            fdc_id=food.fdc_id,
            food_name=food.description,
            grams=checked_grams,
            **diary.snapshot(food, checked_grams),
            suggestion_item_id=item["id"],
        )
    except NotFound:
        # The list changed or the relationship ended between the read and the write.
        raise diary.DiaryError("suggestions.gone") from None
