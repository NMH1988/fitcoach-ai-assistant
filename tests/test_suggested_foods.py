"""The suggested foods' service (T9.34): the rows, the nutrients, the log, the week's share."""

from datetime import date, timedelta

import pytest

from src import dashboard, diary, metrics, suggested_foods
from src.store import records, suggestions, users
from src.tools.food import Food
from tests import store_world as world

TODAY = date(2026, 10, 29)
OATS = Food(
    fdc_id=11,
    description="Oats, made-up",
    kcal=380.0,
    protein_g=13.0,
    carbohydrate_g=68.0,
    fat_g=6.5,
    fiber_g=10.0,
)
RICE = Food(
    fdc_id=12,
    description="Rice, made-up",
    kcal=130.0,
    protein_g=2.7,
    carbohydrate_g=28.0,
    fat_g=0.3,
    fiber_g=None,
)
TABLE = (OATS, RICE)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    """Fix today in Berlin to Thursday 2026-10-29."""
    monkeypatch.setattr(metrics, "berlin_day", lambda moment=None: TODAY)


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def test_build_items_takes_the_table_s_food_and_checks_each_field():
    """A row becomes a SuggestedFood with the table's ID and name; a bad row names its problem."""
    [item] = suggested_foods.build_items([("lunch", "Oats, made-up", 80)], TABLE)
    assert item == suggestions.SuggestedFood("lunch", 11, "Oats, made-up", 80.0)
    for row, code in (
        (("lunch", "Oats", 80), "diary.food_needed"),
        (("brunch", "Oats, made-up", 80), "diary.meal_needed"),
        (("lunch", "Oats, made-up", 0), "diary.grams_range"),
    ):
        with pytest.raises(diary.DiaryError) as caught:
            suggested_foods.build_items([row], TABLE)
        assert caught.value.code == code
    with pytest.raises(diary.DiaryError) as caught:
        suggested_foods.build_items(
            [("lunch", "Oats, made-up", 80), ("lunch", "Oats, made-up", 40)], TABLE
        )
    assert caught.value.code == "suggestions.twice"


def test_nutrients_and_totals_follow_the_grams():
    """Each item's nutrients are the table's per 100 g times grams / 100; a missing food is None."""
    items = [
        {"fdc_id": 11, "grams": 50.0, "meal": "breakfast", "food_name": "Oats, made-up"},
        {"fdc_id": 12, "grams": 200.0, "meal": "lunch", "food_name": "Rice, made-up"},
    ]
    found = suggested_foods.with_nutrients(items, TABLE)
    assert found[0]["kcal"] == pytest.approx(190.0) and found[1]["kcal"] == pytest.approx(260.0)
    assert suggested_foods.totals(found)["kcal"] == pytest.approx(450.0)
    gone = suggested_foods.with_nutrients([{**items[0], "fdc_id": 99}], TABLE)
    assert gone[0]["kcal"] is None
    assert suggested_foods.totals(gone)["kcal"] is None
    assert suggested_foods.totals([])["kcal"] == 0


def test_log_suggested_logs_the_item_flagged_with_the_gymer_s_grams(store_conn, relationships):
    """The entry has the item's meal and food, the chosen grams and day, and the flag."""
    suggested_foods.save_suggestions(
        store_conn, world.COACH_A, world.SHARED, [("dinner", "Rice, made-up", 150)], TABLE
    )
    [item] = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["items"]
    entry = suggested_foods.log_suggested(
        store_conn, world.SHARED, item["id"], grams=200.0, day=TODAY, table=TABLE
    )
    [row] = [
        r for r in records.list_meal_items(store_conn, *[world.SHARED] * 2) if r["id"] == entry
    ]
    assert (row["meal"], row["fdc_id"], row["grams"], row["consumed_on"]) == (
        "dinner",
        12,
        200.0,
        TODAY.isoformat(),
    )
    assert row["kcal"] == pytest.approx(260.0) and row["from_suggestion"] == 1


def test_log_suggested_refuses_an_item_not_on_the_list(store_conn, relationships):
    """A stale or unknown item gives suggestions.gone and writes nothing."""
    suggested_foods.save_suggestions(
        store_conn, world.COACH_A, world.SHARED, [("dinner", "Rice, made-up", 150)], TABLE
    )
    [item] = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["items"]
    suggested_foods.save_suggestions(store_conn, world.COACH_A, world.SHARED, [], TABLE)
    before = records.list_meal_items(store_conn, world.SHARED, world.SHARED)
    for item_id in (item["id"], 999):
        with pytest.raises(diary.DiaryError) as caught:
            suggested_foods.log_suggested(
                store_conn, world.SHARED, item_id, grams=100.0, day=TODAY, table=TABLE
            )
        assert caught.value.code == "suggestions.gone"
    assert records.list_meal_items(store_conn, world.SHARED, world.SHARED) == before


def test_log_suggested_keeps_the_diary_s_checks(store_conn, relationships):
    """The grams range, the day range and a saved profile hold for a suggested food too."""
    suggested_foods.save_suggestions(
        store_conn, world.COACH_A, world.SHARED, [("dinner", "Rice, made-up", 150)], TABLE
    )
    [item] = suggestions.current_suggestions(store_conn, world.SHARED, world.SHARED)["items"]
    for grams, day, code in (
        (0, TODAY, "diary.grams_range"),
        (100.0, TODAY + timedelta(days=1), "diary.day_range"),
    ):
        with pytest.raises(diary.DiaryError) as caught:
            suggested_foods.log_suggested(
                store_conn, world.SHARED, item["id"], grams=grams, day=day, table=TABLE
            )
        assert caught.value.code == code


def test_a_gymer_without_a_profile_cannot_log_a_suggestion(store_conn):
    """The diary's rule: no entry before the first profile Save."""
    users.create_user(store_conn, world.COACH_A, "coach", "Coach A")
    users.create_user(store_conn, "gym-new", "gymer", "New")
    link = users.start_relationship(store_conn, world.COACH_A, "gym-new")
    users.set_consent(store_conn, "gym-new", link, "nutrition", True)
    suggested_foods.save_suggestions(
        store_conn, world.COACH_A, "gym-new", [("lunch", "Oats, made-up", 50)], TABLE
    )
    [item] = suggestions.current_suggestions(store_conn, "gym-new", "gym-new")["items"]
    with pytest.raises(diary.DiaryError) as caught:
        suggested_foods.log_suggested(
            store_conn, "gym-new", item["id"], grams=50.0, day=TODAY, table=TABLE
        )
    assert caught.value.code == "diary.profile_first"


def _meal(day: date, kcal: float, flagged: int) -> dict:
    """Return a stored-looking meal item with its day, energy and flag."""
    return {"consumed_on": day.isoformat(), "kcal": kcal, "from_suggestion": flagged}


def test_the_week_s_share_counts_items_and_energy_from_the_suggestions():
    """Two of three items and 600 of 1,000 kcal; the day before the Monday is left out."""
    monday = date(2026, 10, 26)
    meals = [
        _meal(monday, 400.0, 1),
        _meal(monday + timedelta(days=2), 200.0, 1),
        _meal(monday + timedelta(days=6), 400.0, 0),
        _meal(monday - timedelta(days=1), 900.0, 1),
    ]
    share = metrics.suggested_share(meals, monday)
    assert (share.items, share.suggested_items) == (3, 2)
    assert share.energy_share == pytest.approx(0.6)


def test_the_week_s_share_with_nothing_or_no_energy_logged():
    """No item: 0 of 0 and no energy share; items of 0 kcal: no energy share."""
    monday = date(2026, 10, 26)
    empty = metrics.suggested_share([], monday)
    assert (empty.items, empty.suggested_items, empty.energy_share) == (0, 0, None)
    water = metrics.suggested_share([_meal(monday, 0.0, 1)], monday)
    assert (water.items, water.suggested_items, water.energy_share) == (1, 1, None)


def test_the_share_counts_only_items_logged_since_the_relationship_began():
    """An item flagged before the current coach's start counts as an ordinary item."""
    monday = date(2026, 10, 26)
    early = {**_meal(monday, 400.0, 1), "recorded_at": "2026-10-26T08:00:00+00:00"}
    late = {**_meal(monday, 100.0, 1), "recorded_at": "2026-10-28T08:00:00+00:00"}
    share = metrics.suggested_share([early, late], monday, "2026-10-27T12:00:00+00:00")
    assert (share.items, share.suggested_items) == (2, 1)
    assert share.energy_share == pytest.approx(0.2)
    assert metrics.suggested_share([early, late], monday).suggested_items == 2


def test_a_coach_s_week_passes_the_relationship_s_start(store_conn, relationships, monkeypatch):
    """dashboard.client_week() gives the share the relationship's accepted_at."""
    seen = []
    real = metrics.suggested_share

    def spy(meals, start, since=None):
        """Record the start the share was given, then work it out."""
        seen.append(since)
        return real(meals, start, since)

    monkeypatch.setattr(metrics, "suggested_share", spy)
    week = dashboard.client_week(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 26))
    [accepted] = [
        row["accepted_at"]
        for row in users.list_relationships(store_conn, world.COACH_A)
        if row["other_id"] == world.SHARED
    ]
    assert seen == [accepted] and week.suggested is not None
