"""UI tests for the Today page: the gymer's food and weight diary (T9.13, AC-23)."""

from datetime import timedelta

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import config, diary, metrics, units
from src.store import db, records
from src.tools.food import load_food_table
from tests.test_app_account import (
    PROFILE,
    USER_ID,
    button,
    signed_in,
    start,
    store_account,
    texts,
)
from views import navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

POLLOCK = "Alaska Pollock, raw"  # a row of the committed USDA table


def open_today(at: AppTest) -> AppTest:
    """Open the Today page by its URL path."""
    at._page_hash = calc_hash(navigation.TODAY)
    return at.run(timeout=30)


def _meals() -> list[dict]:
    """Return the canary gymer's food entries."""
    with db.connect() as conn:
        return records.list_meal_items(conn, USER_ID, USER_ID)


def _food(name: str):
    """Return the committed table's row of a food."""
    return next(food for food in load_food_table() if food.description == name)


def _add(at: AppTest, food: str = POLLOCK, grams: float = 150.0, meal: str = "lunch") -> AppTest:
    """Fill the add-food form and press Add."""
    at.selectbox(key="today_food").set_value(food)
    at.number_input(key="today_grams").set_value(grams)
    at.segmented_control(key="today_meal").set_value(meal)
    return button(at, "Add").click().run(timeout=30)


def _log(grams: float, meal: str, food: str = POLLOCK) -> int:
    """Log a food for the canary gymer today, straight through the diary."""
    with db.connect() as conn:
        return diary.log_food(conn, USER_ID, food_name=food, grams=grams, meal=meal, day=_today())


def _today():
    """Return today in Berlin, as the page does."""
    return metrics.berlin_day()


@pytest.fixture
def gymer(monkeypatch):
    """Store the canary gymer with a saved profile and open the Today page."""
    store_account("gymer", profile=PROFILE)
    return open_today(start(monkeypatch, user=signed_in()))


def test_today_is_in_the_gymers_menu_after_the_home(monkeypatch):
    """A gymer's pages are My profile (the home), Today, Coach and sharing (T9.12) and My data."""
    assert navigation.PAGES_BY_ROLE["gymer"] == (
        navigation.PROFILE,
        navigation.TODAY,
        navigation.SHARING,
        navigation.MY_DATA,
    )


def test_a_gymer_logs_150_g_and_the_entry_stores_1_5_times_the_values(gymer):
    """AC-23 in the UI: food, grams, meal and today's date; the snapshot is 1.5 x per 100 g."""
    at = _add(gymer)
    [meal] = _meals()
    food = _food(POLLOCK)
    assert (meal["food_name"], meal["grams"], meal["meal"]) == (POLLOCK, 150.0, "lunch")
    assert meal["consumed_on"] == _today().isoformat()
    assert meal["kcal"] == food.kcal * 1.5
    assert meal["protein_g"] == food.protein_g * 1.5
    assert "Food added." in [str(item.value) for item in at.success]
    page = texts(at)
    assert "**Lunch** · 118 kcal" in page
    assert "**Day total:** 118 kcal" in page


def test_the_day_is_today_in_berlin_by_default_and_no_future_day_can_be_picked(gymer):
    """The date field starts on today in Berlin; its range is today back DIARY_MAX_DAYS_BACK."""
    field = gymer.date_input(key="today_day")
    assert field.value == _today()
    assert field.proto.max == _today().isoformat()
    oldest = _today() - timedelta(days=config.DIARY_MAX_DAYS_BACK)
    assert field.proto.min == oldest.isoformat()


def test_a_food_logged_on_an_earlier_day_is_listed_on_that_day(gymer):
    """Choosing yesterday logs the food on yesterday and lists it there, not today."""
    yesterday = _today() - timedelta(days=1)
    gymer.date_input(key="today_day").set_value(yesterday).run(timeout=30)
    at = _add(gymer, meal="dinner")
    [meal] = _meals()
    assert meal["consumed_on"] == yesterday.isoformat()
    assert "**Dinner**" in texts(at)


def test_no_meal_chosen_is_refused_and_nothing_is_written(gymer):
    """Add without a meal shows the fixed message and stores nothing."""
    gymer.selectbox(key="today_food").set_value(POLLOCK)
    at = button(gymer, "Add").click().run(timeout=30)
    assert "Choose a meal" in texts(at)
    assert _meals() == []


def test_the_day_is_listed_by_meal_with_totals(monkeypatch):
    """Breakfast before dinner, each with its kcal, then the day's totals."""
    store_account("gymer", profile=PROFILE)
    _log(100.0, "dinner")
    _log(200.0, "breakfast")
    at = open_today(start(monkeypatch, user=signed_in()))
    page = texts(at)
    food = _food(POLLOCK)
    breakfast = f"**Breakfast** · {round(food.kcal * 2)} kcal"
    dinner = f"**Dinner** · {round(food.kcal)} kcal"
    assert page.index(breakfast) < page.index(dinner)
    assert f"**Day total:** {round(food.kcal * 3)} kcal" in page
    assert len(at.dataframe) == 2


def test_an_empty_day_says_nothing_is_logged(gymer):
    """A day with no entries says so (not logged, never zero eaten)."""
    assert "Nothing logged on this day." in texts(gymer)


def _pick(at: AppTest, record_id: int) -> AppTest:
    """Pick an entry in the change-or-delete picker."""
    return at.selectbox(key="today_entry").set_value(record_id).run(timeout=30)


def test_an_entry_is_edited_into_a_new_row(monkeypatch):
    """Save changes replaces the entry with a new row; the old row is gone."""
    store_account("gymer", profile=PROFILE)
    old = _log(100.0, "lunch")
    at = _pick(open_today(start(monkeypatch, user=signed_in())), old)
    at.number_input(key=f"today_edit_grams_{old}").set_value(50.0)
    at.segmented_control(key=f"today_edit_meal_{old}").set_value("snack")
    at = button(at, "Save changes").click().run(timeout=30)
    [meal] = _meals()
    assert (meal["grams"], meal["meal"]) == (50.0, "snack")
    assert meal["kcal"] == _food(POLLOCK).kcal * 0.5
    assert "Entry changed." in [str(item.value) for item in at.success]


def test_an_entry_is_deleted(monkeypatch):
    """Delete entry removes it, and the day says nothing is logged."""
    store_account("gymer", profile=PROFILE)
    old = _log(100.0, "lunch")
    at = _pick(open_today(start(monkeypatch, user=signed_in())), old)
    at = button(at, "Delete entry").click().run(timeout=30)
    assert _meals() == []
    assert "Nothing logged on this day." in texts(at)


def test_an_entry_deleted_in_another_tab_is_reported_and_the_list_read_again(monkeypatch):
    """An entry gone between the page's read and Save changes: the fixed note, nothing written."""
    store_account("gymer", profile=PROFILE)
    old = _log(100.0, "lunch")
    at = _pick(open_today(start(monkeypatch, user=signed_in())), old)

    def deleted_meanwhile(conn, user_id, record_id, **item):
        """Delete the entry first, as another tab would, then replace it as the store does."""
        records.delete_record(conn, user_id, "meal_items", record_id)
        return replace(conn, user_id, record_id, **item)

    replace = records.replace_meal_item
    monkeypatch.setattr(records, "replace_meal_item", deleted_meanwhile)
    at = button(at, "Save changes").click().run(timeout=30)
    assert _meals() == []
    assert "This entry no longer exists." in str(at.info[0].value)


def test_adding_food_after_the_account_was_deleted_says_so(gymer, monkeypatch):
    """An add that gets NotFound (the account deleted in another tab) names the account."""

    def account_gone(*args, **kwargs):
        """Fail as the store does for a user who no longer exists."""
        raise records.NotFound

    monkeypatch.setattr(records, "add_meal_item", account_gone)
    gymer.selectbox(key="today_food").set_value(POLLOCK)
    gymer.segmented_control(key="today_meal").set_value("lunch")
    at = button(gymer, "Add").click().run(timeout=30)
    assert "Your account no longer exists" in str(at.info[0].value)
    assert "This entry no longer exists." not in texts(at)


@pytest.mark.parametrize(
    ("system", "value", "kg"),
    [("metric", 79.5, 79.5), ("imperial", 175.0, 175.0 * 0.45359237)],
)
def test_a_weight_in_the_chosen_units_is_stored_in_kg(monkeypatch, system, value, kg):
    """A weight typed in kg or lb is stored in kg on the chosen day and listed in the units."""
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in())
    at.session_state["units"] = system
    at = open_today(at)
    at.number_input(key=f"today_weight_{system}").set_value(value).run(timeout=30)
    at = button(at, "Save weight").click().run(timeout=30)
    with db.connect() as conn:
        weights = records.list_body_measurements(conn, USER_ID, USER_ID, start=_today())
    assert [row["weight_kg"] for row in weights][-1] == pytest.approx(kg)
    # Shown back in the units it was typed in (both ways, within rounding).
    assert units.format_weight(kg, system, "en") in texts(at)
    assert units.weight_in(weights[-1]["weight_kg"], system) == value


def test_a_weight_out_of_range_is_refused(gymer):
    """A weight outside the profile's range shows the fixed message and stores nothing more."""
    gymer.number_input(key="today_weight_metric").set_value(5.0).run(timeout=30)
    at = button(gymer, "Save weight").click().run(timeout=30)
    assert "Enter a weight from 30 to 300 kg" in texts(at)
    with db.connect() as conn:
        assert len(records.list_body_measurements(conn, USER_ID, USER_ID)) == 1  # the profile's


def test_the_page_speaks_german(monkeypatch):
    """The page's texts follow the language."""
    store_account("gymer", profile=PROFILE)
    at = open_today(start(monkeypatch, user=signed_in(), language="de"))
    page = texts(at)
    assert "An diesem Tag ist nichts eingetragen." in page
    assert "Gewicht" in page


def test_a_store_that_fails_on_the_page_shows_the_fixed_message(monkeypatch, gymer):
    """connect() failing after the page opened: the fixed message, nothing written."""

    def failing(path=None):
        """Fail as connect() does for a folder it cannot make."""
        raise db.StoreError("C:/private/folder could not be made")

    monkeypatch.setattr(db, "connect", failing)
    gymer.selectbox(key="today_food").set_value(POLLOCK)
    gymer.segmented_control(key="today_meal").set_value("lunch")
    at = button(gymer, "Add").click().run(timeout=30)
    page = texts(at)
    assert "cannot be opened right now" in page
    assert "private" not in page


@pytest.mark.parametrize("role", [None, "coach"])
def test_a_guest_and_a_coach_have_no_diary(monkeypatch, role):
    """Today is not registered for a guest or a coach: its URL shows their home instead."""
    if role is None:
        at = start(monkeypatch, auth=False)
    else:
        store_account(role)
        at = start(monkeypatch, user=signed_in())
    at = open_today(at)
    assert navigation.TODAY not in navigation.PAGES_BY_ROLE[role]
    assert len(at.tabs) == 4  # the chat page, their home
    assert not [item for item in at.button if item.label == "Add"]
    assert "Nothing logged on this day." not in texts(at)


def test_a_day_left_out_of_range_overnight_goes_back_to_today(monkeypatch):
    """A tab open past midnight on the oldest day: the day becomes today and nothing breaks."""
    store_account("gymer", profile=PROFILE)
    stale = _today() - timedelta(days=config.DIARY_MAX_DAYS_BACK + 1)
    at = start(monkeypatch, user=signed_in())
    at.session_state["today_day"] = stale
    at = open_today(at)
    assert not at.exception
    assert at.date_input(key="today_day").value == _today()
    assert at.session_state["today_day"] == _today()


def test_a_bad_edit_keeps_the_picked_entry(monkeypatch):
    """An edit refused by the diary (no meal) leaves the entry picked, so the gymer can fix it."""
    store_account("gymer", profile=PROFILE)
    old = _log(100.0, "lunch")
    at = _pick(open_today(start(monkeypatch, user=signed_in())), old)
    at.segmented_control(key=f"today_edit_meal_{old}").set_value(None)
    at = button(at, "Save changes").click().run(timeout=30)
    assert "Choose a meal" in texts(at)
    assert at.selectbox(key="today_entry").value == old
    assert [meal["meal"] for meal in _meals()] == ["lunch"]


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_gymer_with_no_saved_profile_is_sent_to_my_profile_first(monkeypatch, language):
    """No saved profile (so no opt-in or 18+ check): no form, a fixed note, nothing stored."""
    store_account("gymer")
    at = open_today(start(monkeypatch, user=signed_in(), language=language))
    note = {"en": "Save your details on My profile first", "de": "Speichern Sie zuerst"}
    assert note[language] in str(at.info[0].value)
    assert not [item for item in at.button if item.label in ("Add", "Hinzufügen")]
    assert not at.date_input
    assert _meals() == []


def test_the_page_says_made_up_data_only_and_names_the_usda_source(gymer):
    """The made-up data note is at the top, and the form credits USDA FoodData Central."""
    page = texts(gymer)
    assert "Use made-up data only: do not enter real health data." in page
    assert "USDA FoodData Central" in page
