"""The foods a coach suggests to a client (T9.34): a list the client logs from in one click.

A list is written only by the client's coach while the client shares nutrition
(`add_client_suggestions()`): the share check, the insert and an audit row with no values
(`suggestions_set`) run in one transaction, and every other case is the same `NotFound`, with no row
and no audit row, as a coach's target is (T9.17). A coach changes the suggestions by saving a new
list; an empty list clears them. Items keep the food log's gram range, at most
`config.MAX_SUGGESTED_FOODS` of them, a food at most once per meal slot.

`current_suggestions()` reads the active list. For the gymer it is the newest list written by the
coach they are connected with now, so a former coach's list is hidden once the relationship ends,
though kept until either side deletes their data (owner's choices, 2026-11-12). For a coach it is
the newest list they wrote for the client, read through `access.authorised_read()` (nutrition, an
audited read). A relationship's status is read as a value (`ended_at`), never as a sharing filter,
which only the `open_shares` view writes.

The list is the coach's suggestion, never a meal plan: the calorie floor does not apply to its
total, and the gymer still logs any other food. A gymer's item logged from the active list carries
the `meal_items.from_suggestion` flag, which only `records.add_meal_item()` sets, after
`is_active_item()` checked the item inside its write transaction.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from src import config
from src.store import values
from src.store.access import NotFound, audit, authorise_read, authorised_read, role_of
from src.store.db import transaction

# The meal slots, as meal_items has them (records.Meal); a test checks they are the same.
MEALS: tuple[str, ...] = ("breakfast", "lunch", "dinner", "snack")

_ADD_LIST = "INSERT INTO food_suggestion_lists (client_id, coach_id, created_at) VALUES (?, ?, ?)"
_ADD_ITEM = """
INSERT INTO food_suggestion_items (list_id, meal, fdc_id, food_name, grams)
VALUES (?, ?, ?, ?, ?)
"""
# The client's relationships, their status read as a value (never a sharing filter).
_CLIENT_RELATIONSHIPS = (
    "SELECT coach_id, ended_at FROM coach_clients WHERE client_id = ? ORDER BY id"
)
_NEWEST_LIST = """
SELECT id, coach_id, created_at FROM food_suggestion_lists
WHERE client_id = ? AND coach_id = ? ORDER BY id DESC LIMIT 1
"""
_ITEMS = """
SELECT id, meal, fdc_id, food_name, grams FROM food_suggestion_items WHERE list_id = ? ORDER BY id
"""


@dataclass(frozen=True)
class SuggestedFood:
    """One suggested food: the meal slot, the USDA food (its ID and name) and the grams."""

    meal: str
    fdc_id: int
    food_name: str
    grams: float


def _checked_items(items: object) -> list[tuple]:
    """Return the items as checked rows (meal, fdc_id, name, grams), refusing a bad list."""
    if isinstance(items, str | bytes) or not isinstance(items, Sequence):
        raise values.StoreValueError("items", "must be a list of suggested foods")
    if len(items) > config.MAX_SUGGESTED_FOODS:
        raise values.StoreValueError("items", "holds more foods than allowed")
    rows: list[tuple] = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        if not isinstance(item, SuggestedFood):
            raise values.StoreValueError("items", "must be a list of suggested foods")
        meal = values.choice(item.meal, "meal", MEALS)
        fdc_id = values.whole_number(item.fdc_id, "fdc_id", minimum=1)
        if (meal, fdc_id) in seen:
            raise values.StoreValueError("items", "names a food twice for one meal")
        seen.add((meal, fdc_id))
        rows.append(
            (
                meal,
                fdc_id,
                values.text(item.food_name, "food_name"),
                values.in_range(
                    item.grams, "grams", (config.FOOD_MIN_GRAMS, config.FOOD_MAX_GRAMS)
                ),
            )
        )
    return rows


def add_client_suggestions(
    conn: sqlite3.Connection, coach_id: str, client_id: str, items: Sequence[SuggestedFood]
) -> int:
    """Save a coach's new list of suggested foods for a client sharing nutrition; return its ID."""
    # The items are checked before the transaction, so a bad value writes nothing. The share check,
    # the inserts and the audit row are one transaction; anything but a coach of a gymer with an
    # active relationship and nutrition shared (the coach's own ID included, for which
    # authorise_read() returns False) is the same NotFound, with no row and no audit row.
    try:
        values.user_id(client_id)
    except values.StoreValueError:
        raise NotFound from None  # as a read of a subject that is not an ID
    rows = _checked_items(items)
    with transaction(conn):
        if authorise_read(conn, coach_id, client_id, "nutrition") is not True:
            raise NotFound
        list_id = conn.execute(_ADD_LIST, (client_id, coach_id, values.utc_text())).lastrowid
        for row in rows:
            conn.execute(_ADD_ITEM, (list_id, *row))
        # Who wrote what kind of record about whom and when, never a value (PRD, Audit).
        audit(
            conn,
            coach_id,
            "suggestions_set",
            "food_suggestion_lists",
            subject_id=client_id,
            resource_id=list_id,
        )
        return list_id


def _current_coach(conn: sqlite3.Connection, client_id: str) -> str | None:
    """Return the coach the client is connected with now, or None."""
    for row in conn.execute(_CLIENT_RELATIONSHIPS, (client_id,)).fetchall():
        if row["ended_at"] is None:
            return row["coach_id"]
    return None


def _list_with_items(conn: sqlite3.Connection, client_id: str, coach_id: str) -> dict | None:
    """Return the newest list a coach wrote for a client, with its items, or None."""
    found = conn.execute(_NEWEST_LIST, (client_id, coach_id)).fetchone()
    if found is None:
        return None
    items = [dict(row) for row in conn.execute(_ITEMS, (found["id"],))]
    return {**dict(found), "items": items}


def current_suggestions(conn: sqlite3.Connection, actor_id: str, subject_id: str) -> dict | None:
    """Return the active list (id, coach_id, created_at, items) a user may read, or None."""
    with authorised_read(conn, actor_id, subject_id, "nutrition", "food_suggestion_lists"):
        if actor_id != subject_id:
            # A coach, allowed by authorised_read(): the newest list they wrote for this client.
            return _list_with_items(conn, subject_id, actor_id)
        # The user's own: the list of the coach they are connected with now, if any.
        coach_id = _current_coach(conn, subject_id)
        return None if coach_id is None else _list_with_items(conn, subject_id, coach_id)


def is_active_item(
    conn: sqlite3.Connection, user_id: str, item_id: object, meal: str, fdc_id: int
) -> bool:
    """Return True if the item is on the user's active list with this meal slot and food."""
    # Runs inside the caller's write transaction (records.add_meal_item()); it opens none.
    if role_of(conn, user_id) != "gymer" or not values.is_row_id(item_id):
        return False
    coach_id = _current_coach(conn, user_id)
    active = None if coach_id is None else _list_with_items(conn, user_id, coach_id)
    if active is None:
        return False
    return any(
        item["id"] == item_id and item["meal"] == meal and item["fdc_id"] == fdc_id
        for item in active["items"]
    )
