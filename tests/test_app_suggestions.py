"""UI tests for the foods a coach suggests (T9.34): the gymer's list on Today, the coach's form.

The gymer sees the active list of their current coach on Today and logs a food with one click
(the grams may be changed first); the entry is flagged as logged from a suggestion. The coach
builds the list on Client week only while the client shares nutrition, and sees the week's share
logged from it. Both pages say the list is not a meal plan.
"""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from src import metrics, suggested_foods
from src.store import db, records, suggestions, users
from src.store.access import NotFound
from src.tools.food import load_food_table
from tests.test_app_account import PROFILE, USER_ID, button, signed_in, start, store_account
from tests.test_app_dashboards import (  # noqa: F401 (fixtures used by name)
    ALEX,
    BO,
    _client_week,
    coach_world,
    today,
)
from tests.test_app_sharing import open_page
from tests.test_app_today import POLLOCK, open_today
from views import client_week, navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

COACH = "coach-kai-t934"


def _food(name: str):
    """Return the committed USDA table's row of a food."""
    return next(food for food in load_food_table() if food.description == name)


def _other_food():
    """Return a committed table food other than POLLOCK."""
    return next(food for food in load_food_table() if food.description != POLLOCK)


def _suggest(conn, coach: str, client: str, *rows: tuple[str, str, float]) -> int:
    """Save a list of (meal, food name, grams) for the client as the coach; return its ID."""
    items = [
        suggestions.SuggestedFood(meal, _food(name).fdc_id, name, grams)
        for meal, name, grams in rows
    ]
    return suggestions.add_client_suggestions(conn, coach, client, items)


def _page_text(at: AppTest) -> str:
    """Return every caption, Markdown, message and subheader of the page as one text."""
    parts = [*at.caption, *at.markdown, *at.error, *at.subheader, *at.info, *at.success]
    return "\n".join(str(part.value) for part in parts)


def _meals(user_id: str = USER_ID) -> list[dict]:
    """Return a user's food entries, read as the user."""
    with db.connect() as conn:
        return records.list_meal_items(conn, user_id, user_id)


@pytest.fixture
def coached():
    """Store the canary gymer with a profile and a coach sharing nutrition; return the link's ID."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = users.start_relationship(conn, COACH, USER_ID)
        users.set_consent(conn, USER_ID, relationship, "nutrition", True)
        _suggest(conn, COACH, USER_ID, ("lunch", POLLOCK, 120.0))
    return relationship


def _item_id() -> int:
    """Return the ID of the canary gymer's first suggested item."""
    with db.connect() as conn:
        return suggestions.current_suggestions(conn, USER_ID, USER_ID)["items"][0]["id"]


# --- The gymer's list on Today -------------------------------------------------------------------


def test_the_gymer_sees_the_suggestions_as_a_choice_not_a_plan(monkeypatch, coached):
    """The section lists the food with grams and energy, and says it is not a meal plan."""
    at = open_today(start(monkeypatch, user=signed_in()))
    text = _page_text(at)
    assert "Suggested by your coach" in text
    assert "This is not a meal plan, and the foods together are not a day's intake" in text
    assert "you may eat other foods too." in text
    # The app does not vouch for the coach (compliance run 1 of T9.34).
    assert "The app does not check a coach's qualifications." in text
    food = _food(POLLOCK)
    kcal, protein = round(food.kcal * 1.2), round(food.protein_g * 1.2)
    carbs, fat = round(food.carbohydrate_g * 1.2), round(food.fat_g * 1.2)
    # Grams, energy and macros from the USDA table (criterion 4, code review round 1).
    assert (
        f"{POLLOCK}, 120 g · {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, {fat} g fat"
    ) in text
    # The gymer's own form is still there.
    assert at.selectbox(key="today_food") is not None


def test_one_click_logs_the_suggested_food_flagged(monkeypatch, coached):
    """Log adds the food with its meal and grams, flagged from_suggestion (criteria 4 and 5)."""
    at = open_today(start(monkeypatch, user=signed_in()))
    before = len(_meals())
    at.button(key=f"suggestion_log_{_item_id()}").click().run(timeout=30)
    meals = _meals()
    assert len(meals) == before + 1
    added = meals[-1]
    assert (added["food_name"], added["meal"], added["grams"]) == (POLLOCK, "lunch", 120.0)
    assert added["from_suggestion"] == 1
    assert added["kcal"] == pytest.approx(_food(POLLOCK).kcal * 1.2)
    assert "Food added from your coach's suggestions." in _page_text(at)


def test_the_gymer_changes_the_grams_before_logging(monkeypatch, coached):
    """The grams field starts at the coach's amount and the gymer's own amount is stored."""
    at = open_today(start(monkeypatch, user=signed_in()))
    item_id = _item_id()
    assert at.number_input(key=f"suggestion_grams_{item_id}").value == 120.0
    at.number_input(key=f"suggestion_grams_{item_id}").set_value(90.0)
    at.button(key=f"suggestion_log_{item_id}").click().run(timeout=30)
    assert _meals()[-1]["grams"] == 90.0 and _meals()[-1]["from_suggestion"] == 1


def test_a_list_changed_since_the_page_was_drawn_saves_nothing(monkeypatch, coached):
    """The coach's new list removed the item: no entry, and the page shows the new list."""
    at = open_today(start(monkeypatch, user=signed_in()))
    item_id = _item_id()
    other = _other_food().description
    with db.connect() as conn:
        _suggest(conn, COACH, USER_ID, ("dinner", other, 50.0))
    before = len(_meals())
    at.button(key=f"suggestion_log_{item_id}").click().run(timeout=30)
    # The old item's button is not drawn on the next run, so its click writes nothing.
    assert len(_meals()) == before
    text = _page_text(at)
    assert f"{other}, 50 g" in text and f"{POLLOCK}, 120 g" not in text


def test_no_section_without_a_list_or_after_the_relationship_ended(monkeypatch, coached):
    """An ended relationship hides the former coach's list (owner's choice, 2026-11-12)."""
    with db.connect() as conn:
        users.end_relationship(conn, USER_ID, coached)
    at = open_today(start(monkeypatch, user=signed_in()))
    assert "Suggested by your coach" not in _page_text(at)


def test_an_empty_list_shows_no_section(monkeypatch, coached):
    """A coach who saved an empty list cleared the suggestions."""
    with db.connect() as conn:
        suggestions.add_client_suggestions(conn, COACH, USER_ID, [])
    at = open_today(start(monkeypatch, user=signed_in()))
    assert "Suggested by your coach" not in _page_text(at)


def test_the_gymer_s_section_in_german(monkeypatch, coached):
    """The heading and the note are German when German is chosen."""
    at = open_today(start(monkeypatch, user=signed_in(), language="de"))
    text = _page_text(at)
    assert "Von Ihrem Coach vorgeschlagen" in text
    assert "Das ist kein Ernährungsplan" in text
    assert [item for item in at.button if item.label == "Erfassen"]


# --- The coach's form on Client week -------------------------------------------------------------


def _add_row(at: AppTest, food: str, grams: float, meal: str) -> AppTest:
    """Fill the coach's add form and press Add to the list."""
    at.selectbox(key="suggestions_food").set_value(food)
    at.number_input(key="suggestions_grams").set_value(grams)
    at.segmented_control(key="suggestions_meal").set_value(meal)
    return button(at, "Add to the list").click().run(timeout=30)


@pytest.mark.usefixtures("coach_world")
def test_a_coach_builds_and_saves_a_list(monkeypatch):
    """Rows are added before saving; Save writes one list with a suggestions_set audit row."""
    at = _client_week(monkeypatch, chosen=ALEX)
    text = _page_text(at)
    assert "Suggested foods" in text and "No foods in the list." in text
    assert "the calorie floor does not apply to the list's total" in text
    at = _add_row(at, POLLOCK, 150.0, "dinner")
    assert f"{POLLOCK}, 150 g" in _page_text(at)
    at = button(at, "Save the list").click().run(timeout=30)
    assert "The suggested foods were saved; the client sees them on Today." in _page_text(at)
    with db.connect() as conn:
        saved = suggestions.current_suggestions(conn, ALEX, ALEX)
        actions = [row[0] for row in conn.execute("SELECT action FROM audit_log")]
    assert [(i["meal"], i["food_name"], i["grams"]) for i in saved["items"]] == [
        ("dinner", POLLOCK, 150.0)
    ]
    assert saved["coach_id"] == USER_ID
    assert actions.count("suggestions_set") == 1


@pytest.mark.usefixtures("coach_world")
def test_the_draft_starts_from_the_saved_list_and_a_row_can_be_removed(monkeypatch):
    """The saved list fills the draft; removing its only row and saving clears the list."""
    with db.connect() as conn:
        _suggest(conn, USER_ID, ALEX, ("breakfast", POLLOCK, 100.0))
    at = _client_week(monkeypatch, chosen=ALEX)
    assert f"{POLLOCK}, 100 g" in _page_text(at)
    at.selectbox(key="suggestions_remove_pick").set_value(0)
    at = button(at, "Remove from the list").click().run(timeout=30)
    assert "No foods in the list." in _page_text(at)
    button(at, "Save the list").click().run(timeout=30)
    with db.connect() as conn:
        assert suggestions.current_suggestions(conn, ALEX, ALEX)["items"] == []


@pytest.mark.usefixtures("coach_world")
def test_a_food_twice_in_one_meal_is_refused_in_the_draft(monkeypatch):
    """The second identical row is not added and the page says why."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, POLLOCK, 150.0, "dinner")
    at = _add_row(at, POLLOCK, 80.0, "dinner")
    assert "A food is in one meal twice; remove one of them." in _page_text(at)
    assert _page_text(at).count(f"{POLLOCK}, ") == 1


@pytest.mark.usefixtures("coach_world")
def test_no_form_without_nutrition(monkeypatch):
    """Bo shares training only: the section says why and offers no form (criterion 2)."""
    at = _client_week(monkeypatch, chosen=BO)
    assert "Foods can be suggested only while the client shares nutrition." in _page_text(at)
    assert not [item for item in at.button if item.label == "Save the list"]


@pytest.mark.usefixtures("coach_world")
def test_a_save_refused_after_the_page_was_drawn_shows_one_message(monkeypatch):
    """A share revoked between the page's read and the store's write: one fixed message."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, POLLOCK, 150.0, "dinner")

    def refused(*_args, **_kwargs):
        """Stand in for the store's refusal of a write after the page read the week."""
        raise NotFound

    monkeypatch.setattr(suggested_foods, "save_suggestions", refused)
    at = button(at, "Save the list").click().run(timeout=30)
    assert "The list was not saved: you cannot suggest foods to this client now." in _page_text(at)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM food_suggestion_lists").fetchone()[0] == 0


@pytest.mark.usefixtures("coach_world")
def test_a_revoked_share_hides_the_form_on_the_next_run(monkeypatch):
    """Nutrition revoked while the page was open: the click's run shows why, nothing written."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, POLLOCK, 150.0, "dinner")
    with db.connect() as conn:
        [relationship] = [
            row["id"] for row in users.list_relationships(conn, ALEX) if row["status"] == "active"
        ]
        users.set_consent(conn, ALEX, relationship, "nutrition", False)
    at = button(at, "Save the list").click().run(timeout=30)
    assert "Foods can be suggested only while the client shares nutrition." in _page_text(at)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM food_suggestion_lists").fetchone()[0] == 0


@pytest.mark.usefixtures("coach_world")
def test_the_week_shows_the_share_logged_from_the_suggestions(monkeypatch):
    """Alex logged three foods; one more from the list makes it 1 of 4 (criterion 6)."""
    with db.connect() as conn:
        _suggest(conn, USER_ID, ALEX, ("lunch", POLLOCK, 100.0))
        [item] = suggestions.current_suggestions(conn, ALEX, ALEX)["items"]
        food = _food(POLLOCK)
        records.add_meal_item(
            conn,
            ALEX,
            consumed_on=metrics.berlin_day(),
            meal="lunch",
            fdc_id=food.fdc_id,
            food_name=POLLOCK,
            grams=100.0,
            kcal=food.kcal,
            protein_g=food.protein_g,
            carbohydrate_g=food.carbohydrate_g,
            fat_g=food.fat_g,
            fiber_g=None,
            suggestion_item_id=item["id"],
        )
    at = _client_week(monkeypatch, chosen=ALEX)
    text = _page_text(at)
    assert "In the week shown, the client logged 1 of 4 foods from a coach's suggestions (" in text


@pytest.mark.usefixtures("coach_world")
def test_the_total_is_shown_next_to_the_target(monkeypatch):
    """The draft's total and the client's target active today are both on the page."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _add_row(at, POLLOCK, 100.0, "lunch")
    text = _page_text(at)
    assert f"List total: {round(_food(POLLOCK).kcal)} kcal" in text
    assert "The client's targets today:" in text


@pytest.mark.usefixtures("coach_world")
def test_the_coach_s_section_in_german(monkeypatch):
    """The coach's heading and note are German when German is chosen."""
    at = open_page(start(monkeypatch, user=signed_in(), language="de"), navigation.CLIENT_WEEK)
    at.selectbox(key=client_week.PICK_KEY).set_value(ALEX).run(timeout=30)
    text = _page_text(at)
    assert "Vorgeschlagene Lebensmittel" in text
    assert "daher gilt die Kaloriengrenze nicht für die Summe der Liste" in text


@pytest.mark.usefixtures("coach_world")
def test_the_total_is_compared_with_today_s_target_whatever_the_week(monkeypatch):
    """A past week with another target still shows today's target (code review round 1)."""
    with db.connect() as conn:
        records.add_target(
            conn,
            ALEX,
            kcal=4321.0,
            protein_g=111.0,
            carbs_g=222.0,
            fat_g=33.0,
            set_by="user",
            effective_from=date(2026, 10, 1),
        )
    today_kcal = round(metrics.active_target(_targets(ALEX), metrics.berlin_day()).kcal)
    at = _client_week(monkeypatch, chosen=ALEX)
    at.date_input(key=client_week.WEEK_KEY).set_value(date(2026, 10, 7)).run(timeout=30)
    at = _add_row(at, POLLOCK, 100.0, "lunch")
    text = _page_text(at)
    assert f"The client's targets today: {today_kcal:,} kcal" in text
    assert "The client's targets today: 4,321 kcal" not in text


def _targets(user_id: str) -> list[dict]:
    """Return a user's stored targets, read as the user."""
    with db.connect() as conn:
        return records.list_targets(conn, user_id, user_id)


def test_the_gymer_is_told_of_a_new_list_on_the_notifications_page(monkeypatch, coached):
    """The notification names the coach, never a food or an amount (criterion 10)."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.NOTIFICATIONS)
    text = _page_text(at)
    assert "Coach Kai updated the foods they suggest to you." in text
    assert POLLOCK not in text and "120 g" not in text


def test_the_nutrition_scope_and_the_notifications_page_name_the_suggestions(monkeypatch, coached):
    """The consent text and the Notifications intro say what the coach's suggestions are."""
    sharing_page = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    labels = " ".join(str(box.label) for box in sharing_page.checkbox)
    assert "the foods your coach suggests (and how much you log from them while you share)" in (
        labels
    )
    page = open_page(start(monkeypatch, user=signed_in()), navigation.NOTIFICATIONS)
    assert "when your coach updated the foods they suggest" in _page_text(page)
