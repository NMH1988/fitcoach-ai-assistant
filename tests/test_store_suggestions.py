"""The foods a coach suggests to a client (T9.34): the list, who reads it, and the one-click log."""

from typing import get_args

import pytest

from src import config
from src.store import access, records, suggestions, users, values
from tests import store_world as world

OATS = suggestions.SuggestedFood("breakfast", 9001, "Oats, rolled", 80.0)
RICE = suggestions.SuggestedFood("lunch", 9002, "Rice, white, cooked", 200.0)


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def _audit(conn):
    """Return every audit row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


def _log(conn, user_id, item, *, item_id, meal=None, fdc_id=None):
    """Log a suggested food for the gymer through the one-click path; return the row's ID."""
    return records.add_meal_item(
        conn,
        user_id,
        consumed_on=world.DAY,
        meal=meal or item.meal,
        fdc_id=fdc_id or item.fdc_id,
        food_name=item.food_name,
        grams=item.grams,
        kcal=300.0,
        protein_g=10.0,
        carbohydrate_g=50.0,
        fat_g=5.0,
        fiber_g=None,
        suggestion_item_id=item_id,
    )


def _flags(conn, user_id):
    """Return the gymer's meal items' from_suggestion flags by ID."""
    rows = records.list_meal_items(conn, user_id, user_id)
    return {row["id"]: row["from_suggestion"] for row in rows}


def test_the_meal_slots_are_the_food_log_s():
    """A suggestion's meal slots are meal_items' (records.Meal)."""
    assert suggestions.MEALS == get_args(records.Meal)


def test_a_coach_saves_a_list_and_both_sides_read_it(store_conn, relationships):
    """The list's items come back in order for the client and the coach, with one audit row."""
    list_id = suggestions.add_client_suggestions(
        store_conn, world.COACH_A, world.SHARED, [OATS, RICE]
    )
    [written] = _audit(store_conn)
    assert written["action"] == "suggestions_set"
    assert written["resource_type"] == "food_suggestion_lists"
    assert (written["actor_id"], written["subject_id"]) == (world.COACH_A, world.SHARED)
    assert written["resource_id"] == list_id
    own = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)
    assert own["id"] == list_id and own["coach_id"] == world.COACH_A
    assert [(i["meal"], i["fdc_id"], i["food_name"], i["grams"]) for i in own["items"]] == [
        ("breakfast", 9001, "Oats, rolled", 80.0),
        ("lunch", 9002, "Rice, white, cooked", 200.0),
    ]
    assert len(_audit(store_conn)) == 1  # the gymer's own read is not audited
    by_coach = suggestions.current_suggestions(store_conn, world.COACH_A, world.SHARED)
    assert by_coach == own
    read = _audit(store_conn)[-1]
    assert (read["action"], read["resource_type"]) == ("read", "food_suggestion_lists")
    assert read["resource_id"] is None


def test_the_newest_list_is_the_active_one_and_an_empty_list_clears_it(store_conn, relationships):
    """A coach changes the suggestions by saving a new list; no row is changed in place."""
    first = suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    second = suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [RICE])
    active = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)
    assert active["id"] == second and [i["fdc_id"] for i in active["items"]] == [9002]
    cleared = suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [])
    active = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)
    assert active["id"] == cleared and active["items"] == []
    count = store_conn.execute("SELECT count(*) FROM food_suggestion_lists").fetchone()[0]
    assert count == 3 and first < second < cleared


def test_a_user_with_no_list_reads_none(store_conn, relationships):
    """No list yet: None for the gymer and for their coach."""
    assert suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED) is None
    assert suggestions.current_suggestions(store_conn, world.COACH_A, world.SHARED) is None


def test_a_former_coach_s_list_is_hidden_from_the_gymer_but_kept(store_conn, relationships):
    """Once the relationship ends, the gymer's active list is None; the rows stay (owner, T9.34)."""
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    users.end_relationship(store_conn, world.SHARED, relationships[world.SHARED])
    assert suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED) is None
    with pytest.raises(access.NotFound):
        suggestions.current_suggestions(store_conn, world.COACH_A, world.SHARED)
    assert store_conn.execute("SELECT count(*) FROM food_suggestion_items").fetchone()[0] == 1


def test_a_new_coach_does_not_see_or_show_the_former_coach_s_list(store_conn, relationships):
    """With a new coach, the gymer sees only the new coach's list, and that coach only their own."""
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    users.end_relationship(store_conn, world.SHARED, relationships[world.SHARED])
    again = users.start_relationship(store_conn, world.COACH_B, world.SHARED)
    users.set_consent(store_conn, world.SHARED, again, "nutrition", True)
    assert suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED) is None
    assert suggestions.current_suggestions(store_conn, world.COACH_B, world.SHARED) is None
    list_id = suggestions.add_client_suggestions(store_conn, world.COACH_B, world.SHARED, [RICE])
    assert suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["id"] == list_id


def test_revoking_nutrition_keeps_the_gymer_s_list_but_stops_the_coach(store_conn, relationships):
    """The gymer still sees the list while connected; the coach's read and write are refused."""
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], "nutrition", False)
    assert suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED) is not None
    with pytest.raises(access.NotFound):
        suggestions.current_suggestions(store_conn, world.COACH_A, world.SHARED)
    with pytest.raises(access.NotFound):
        suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [RICE])


@pytest.mark.parametrize(
    ("items", "field"),
    [
        ([suggestions.SuggestedFood("brunch", 1, "Oats", 80.0)], "meal"),
        ([suggestions.SuggestedFood("lunch", 0, "Oats", 80.0)], "fdc_id"),
        ([suggestions.SuggestedFood("lunch", 1, " ", 80.0)], "food_name"),
        ([suggestions.SuggestedFood("lunch", 1, "Oats", 0.0)], "grams"),
        ([suggestions.SuggestedFood("lunch", 1, "Oats", config.FOOD_MAX_GRAMS + 1)], "grams"),
        ([suggestions.SuggestedFood("lunch", 1, "Oats", float("nan"))], "grams"),
        ([OATS, OATS], "items"),
        ([("breakfast", 1, "Oats", 80.0)], "items"),
        ("oats", "items"),
        (
            [
                suggestions.SuggestedFood("snack", n, "Food", 10.0)
                for n in range(1, config.MAX_SUGGESTED_FOODS + 2)
            ],
            "items",
        ),
    ],
)
def test_a_bad_list_is_refused_naming_the_field_and_writes_nothing(
    store_conn, relationships, items, field
):
    """A value out of range names its field, never the value; no row and no audit row."""
    with pytest.raises(values.StoreValueError) as caught:
        suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, items)
    assert caught.value.field == field
    assert "Oats" not in str(caught.value) and "80" not in str(caught.value)
    assert store_conn.execute("SELECT count(*) FROM food_suggestion_lists").fetchone()[0] == 0
    assert _audit(store_conn) == []


def test_the_longest_list_and_one_food_in_two_meals_are_allowed(store_conn, relationships):
    """MAX_SUGGESTED_FOODS items fit, and a food may be suggested for two meal slots."""
    longest = [
        suggestions.SuggestedFood("snack", n, "Food", 10.0)
        for n in range(1, config.MAX_SUGGESTED_FOODS + 1)
    ]
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, longest)
    twice = [OATS, suggestions.SuggestedFood("snack", OATS.fdc_id, OATS.food_name, 40.0)]
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, twice)


def test_a_food_logged_from_the_active_list_is_flagged(store_conn, relationships):
    """The one-click path flags the item; an ordinary log does not."""
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    [item] = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["items"]
    flagged = _log(store_conn, world.SHARED, OATS, item_id=item["id"])
    flags = _flags(store_conn, world.SHARED)
    assert flags[flagged] == 1
    assert sorted(flags.values()) == [0, 1]  # the world's own meal item is not flagged


@pytest.mark.parametrize(
    "case", ["another meal", "another food", "an unknown item", "not an ID", "a hidden list"]
)
def test_a_food_not_on_the_active_list_is_refused(store_conn, relationships, case):
    """The flag needs the item on the gymer's active list with its meal and food; else NotFound."""
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    [item] = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["items"]
    kwargs = {"item_id": item["id"]}
    match case:
        case "another meal":
            kwargs["meal"] = "dinner"
        case "another food":
            kwargs["fdc_id"] = 4242
        case "an unknown item":
            kwargs["item_id"] = item["id"] + 100
        case "not an ID":
            kwargs["item_id"] = True
        case "a hidden list":
            users.end_relationship(store_conn, world.SHARED, relationships[world.SHARED])
    before = _flags(store_conn, world.SHARED)
    with pytest.raises(access.NotFound):
        _log(store_conn, world.SHARED, OATS, **kwargs)
    assert _flags(store_conn, world.SHARED) == before


def test_another_gymer_cannot_log_from_a_list_that_is_not_theirs(store_conn, relationships):
    """An item of another client's list is refused for this gymer."""
    suggestions.add_client_suggestions(store_conn, world.COACH_B, world.OTHERS, [OATS])
    [item] = suggestions.current_suggestions(store_conn, world.OTHERS, world.OTHERS)["items"]
    with pytest.raises(access.NotFound):
        _log(store_conn, world.SHARED, OATS, item_id=item["id"])


def test_an_edit_keeps_the_flag_for_the_same_food_and_drops_it_for_another(
    store_conn, relationships
):
    """Changing grams or meal keeps from_suggestion; changing the food clears it."""
    suggestions.add_client_suggestions(store_conn, world.COACH_A, world.SHARED, [OATS])
    [item] = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["items"]
    logged = _log(store_conn, world.SHARED, OATS, item_id=item["id"])
    edit = {
        "consumed_on": world.DAY,
        "food_name": OATS.food_name,
        "kcal": 1.0,
        "protein_g": 1.0,
        "carbohydrate_g": 1.0,
        "fat_g": 1.0,
        "fiber_g": None,
    }
    same = records.replace_meal_item(
        store_conn,
        world.SHARED,
        logged,
        meal="snack",
        fdc_id=OATS.fdc_id,
        grams=120.0,
        **edit,
    )
    assert _flags(store_conn, world.SHARED)[same] == 1
    other = records.replace_meal_item(
        store_conn, world.SHARED, same, meal="snack", fdc_id=4242, grams=120.0, **edit
    )
    assert _flags(store_conn, world.SHARED)[other] == 0


def test_a_gymer_has_no_way_to_delete_a_list(store_conn, relationships):
    """delete_record() has no kind for the lists, so a gymer cannot delete their coach's list."""
    assert not any("suggestion" in kind for kind in records.RECORD_KINDS)
    with pytest.raises(values.StoreValueError):
        records.delete_record(store_conn, world.SHARED, "food_suggestion_lists", 1)
