"""Tests for src/tools/meal_plan.py: a day's foods totalled and compared with the targets (T4.5)."""

import pytest

from src import config
from src.tools import meal_plan
from src.tools.energy import calculate_macro_targets
from src.tools.meal_plan import evaluate_meal_plan
from tests.fakes import FOODS, HOSTILE_FOOD_NAME

OATS = "Oats, whole grain, rolled, old fashioned"
CHICKEN = "Chicken, breast, boneless, skinless, raw"
# The fixture profile's targets (tests/fakes.py PROFILE): 80 kg, build muscle, TDEE 2759 kcal/day:
# 3035 kcal (range 3035-3311), protein 152 g (range 128-176), carbohydrate 418 g, fat 84 g.
TARGETS = calculate_macro_targets(80.0, "build_muscle", 2759)
DAY = [{"food": "rolled oats", "grams": 80}, {"food": "chicken breast", "grams": 200}]
UNKNOWN = {"food": "zzzz qqqq", "grams": 50}


def _evaluate(items, targets=TARGETS):
    """Evaluate the items against the targets with the fixture foods table."""
    return evaluate_meal_plan(items, targets, FOODS)


def _checks(result) -> dict:
    """Return the comparison rows by nutrient."""
    return {check.nutrient: check for check in result.comparison}


@pytest.fixture
def no_lookups(monkeypatch):
    """Make every food lookup fail the test if it is reached."""

    def fail(*args, **kwargs):
        """Fail: an invalid plan must not look anything up."""
        raise AssertionError("a food was looked up")

    monkeypatch.setattr(meal_plan, "lookup_food_nutrition", fail)


# --- Totals of the foods found (criterion 2) ------------------------------------------------------


def test_each_food_is_looked_up_with_its_match_and_nutrients():
    """Every food keeps the name asked for, its grams, the USDA match and the scaled values."""
    result = _evaluate(DAY)
    assert result.status == "ok"
    oats, chicken = result.items
    assert (oats.requested, oats.grams, oats.status) == ("rolled oats", 80, "found")
    assert oats.matched_name == OATS
    assert (oats.nutrients.kcal, oats.nutrients.protein_g) == (304, 10.6)
    assert chicken.matched_name == CHICKEN
    assert chicken.nutrients.fiber_g is None


def test_the_totals_add_up_the_foods_as_shown():
    """The totals are the sums of each food's shown values, so the table adds up."""
    result = _evaluate(DAY)
    totals = result.totals
    assert (totals.kcal, totals.protein_g, totals.carbohydrate_g, totals.fat_g) == (
        544,
        55.6,
        54.4,
        10.3,
    )
    assert totals.kcal == sum(item.nutrients.kcal for item in result.items)
    assert result.partial is False


def test_the_fiber_total_leaves_out_foods_without_a_fiber_value():
    """Chicken has no USDA fiber value: the total is the oats' fiber, and a note says so."""
    result = _evaluate(DAY)
    assert result.totals.fiber_g == 8.0
    assert (
        "USDA reports no fiber value for 1 of the foods found, so the fiber total leaves them out."
        in result.notes
    )


def test_without_any_fiber_value_the_fiber_total_is_not_reported():
    """Only foods without a fiber value give no fiber total, not zero."""
    result = _evaluate([{"food": "chicken breast", "grams": 100}])
    assert result.totals.fiber_g is None


def test_a_food_not_found_is_listed_and_left_out_of_the_totals():
    """The unknown food is listed as not found; the totals are those of the others."""
    result = _evaluate([*DAY, UNKNOWN])
    assert result.status == "ok"
    assert result.partial is True
    unknown = result.items[2]
    assert (unknown.requested, unknown.status, unknown.nutrients) == (
        "zzzz qqqq",
        "not_found",
        None,
    )
    assert result.totals == _evaluate(DAY).totals
    assert (
        "1 of 3 foods were not found in the USDA table, so the totals leave them out."
        in result.notes
    )
    assert result.message.startswith("2 of 3 foods found;")


def test_when_no_food_is_found_there_are_no_totals():
    """With no food found the result is "not found", with each food and no comparison."""
    result = _evaluate([UNKNOWN])
    assert result.status == "not_found"
    assert (result.totals, result.comparison, result.partial) == (None, [], True)
    assert [item.status for item in result.items] == ["not_found"]


def test_alternatives_come_back_for_each_food():
    """A found food carries its other close USDA names, as in the food lookup."""
    result = _evaluate([{"food": "oats", "grams": 100}])
    assert HOSTILE_FOOD_NAME in result.items[0].alternatives + [result.items[0].matched_name]


# --- Gaps and ranges (criterion 3) ----------------------------------------------------------------


def test_each_gap_is_the_target_minus_the_plans_total():
    """kcal, protein, carbohydrate and fat each have their total, target and gap, in that order."""
    result = _evaluate(DAY)
    assert [c.nutrient for c in result.comparison] == ["kcal", "protein", "carbohydrate", "fat"]
    checks = _checks(result)
    assert (checks["kcal"].plan_total, checks["kcal"].target, checks["kcal"].gap) == (
        544,
        3035,
        2491,
    )
    assert (checks["protein"].target, checks["protein"].gap) == (152, 96.4)
    assert (checks["carbohydrate"].target, checks["carbohydrate"].gap) == (418, 363.6)
    assert (checks["fat"].target, checks["fat"].gap) == (84, 73.7)
    assert checks["kcal"].unit == "kcal"
    assert {checks[n].unit for n in ("protein", "carbohydrate", "fat")} == {"g"}


def test_a_plan_above_the_target_has_a_negative_gap():
    """Eating more than the target gives a negative gap."""
    result = _evaluate([{"food": "rolled oats", "grams": 900}])
    assert _checks(result)["kcal"].gap == 3035 - 3420


@pytest.mark.parametrize(
    ("grams", "position"),
    # Oats, 380 kcal per 100 g, against 3035-3311 kcal.
    [(100, "below"), (800, "within"), (900, "above")],
)
def test_the_kcal_total_is_placed_against_the_goals_range(grams, position):
    """The kcal total is below, within or above the goal's kcal range from the sources."""
    kcal = _checks(_evaluate([{"food": "rolled oats", "grams": grams}]))["kcal"]
    assert kcal.target_range == TARGETS.kcal_range == (3035, 3311)
    assert kcal.range_position == position


@pytest.mark.parametrize(
    ("grams", "position"),
    # Chicken, 22.5 g protein per 100 g, against 128-176 g.
    [(400, "below"), (700, "within"), (1000, "above")],
)
def test_the_protein_total_is_placed_against_the_sources_range(grams, position):
    """The protein total is below, within or above the 1.6-2.2 g/kg range at this body weight."""
    protein = _checks(_evaluate([{"food": "chicken breast", "grams": grams}]))["protein"]
    assert protein.target_range == TARGETS.protein_g_range == (128, 176)
    assert protein.range_position == position


def test_the_ends_of_a_range_are_within_it():
    """A total equal to the lowest kcal of the range is within it."""
    targets = TARGETS.model_copy(update={"kcal_range": (304, 400)})
    assert _checks(_evaluate(DAY[:1], targets))["kcal"].range_position == "within"


def test_carbohydrate_and_fat_have_no_range_and_fiber_no_target():
    """No threshold is invented: carbohydrate and fat get only a gap, fiber is not compared."""
    checks = _checks(_evaluate(DAY))
    for nutrient in ("carbohydrate", "fat"):
        assert (checks[nutrient].target_range, checks[nutrient].range_position) == (None, None)
    assert "fiber" not in checks


# --- The calorie floor and the targets' notes (criterion 4) ---------------------------------------


def test_a_plan_below_the_calorie_floor_says_so():
    """A day's total under the floor gets a note with the total, the floor and a dietitian."""
    result = _evaluate(DAY)
    assert (
        f"The plan's total of 544 kcal is below the calorie floor of {config.CALORIE_FLOOR_KCAL} "
        "kcal/day. The app does not suggest eating below the floor; ask a registered dietitian "
        "for personal advice." in result.notes
    )


def test_a_plan_at_or_above_the_floor_has_no_floor_note():
    """A total from the floor up gets no floor note."""
    result = _evaluate([{"food": "rolled oats", "grams": 800}])
    assert not [note for note in result.notes if "calorie floor" in note]


def test_the_floor_is_read_from_config(monkeypatch):
    """The floor note follows config.CALORIE_FLOOR_KCAL."""
    monkeypatch.setattr(config, "CALORIE_FLOOR_KCAL", 500)
    assert not [note for note in _evaluate(DAY).notes if "calorie floor" in note]


def test_the_targets_notes_are_passed_on():
    """When the targets were raised to the floor, their notes come with the comparison."""
    targets = calculate_macro_targets(45.0, "lose_fat", 1300)
    assert targets.floor_applied and targets.notes
    result = _evaluate(DAY, targets)
    assert result.notes[-len(targets.notes) :] == targets.notes


# --- Invalid arguments (criteria 1 and 6) ---------------------------------------------------------


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"food": "rolled oats", "grams": 10}] * (config.MEAL_PLAN_MAX_ITEMS + 1),
        "rolled oats",
        None,
        [{"food": "rolled oats", "grams": 80, "table": []}],
        [{"food": "rolled oats", "grams": 80, "weight_kg": 80}],
        [{"food": "a", "grams": 80}],
        [{"food": "rolled oats", "grams": "80"}],
        [{"food": "rolled oats", "grams": 0}],
        [{"food": "rolled oats", "grams": float("inf")}],
        [{"food": "rolled oats"}],
        ["rolled oats 80 g"],
        [{"food": "rolled oats", "grams": 80}, {"food": "x" * 101, "grams": 80}],
    ],
)
def test_invalid_items_are_refused_before_any_lookup(no_lookups, items):
    """An empty or too long list, a bad item or an extra field gives "invalid" and no lookup."""
    result = _evaluate(items)
    assert result.status == "invalid"
    assert result.message.startswith("Invalid meal plan: ")
    assert (result.items, result.totals) == ([], None)


def test_the_invalid_message_names_the_items_and_never_echoes_them(no_lookups):
    """The message gives item numbers and the rules, not the food names or fields sent."""
    items = [
        {"food": "rolled oats", "grams": 80},
        {"food": "SECRET a", "grams": "SECRET"},
        {"food": "rolled oats", "grams": 80, "SECRET_FIELD": 1},
        "SECRET",
    ]
    result = _evaluate(items)
    assert result.message == (
        "Invalid meal plan: item 2: the amount must be a number of grams from 0.1 to 2000; "
        "item 3: only the arguments food and grams are accepted; "
        "item 4: each item must be an object with food and grams."
    )
    assert "SECRET" not in result.message


def test_a_list_problem_gets_the_list_rule(no_lookups):
    """Too many foods give the list rule with the limit from config."""
    result = _evaluate([{"food": "rolled oats", "grams": 10}] * (config.MEAL_PLAN_MAX_ITEMS + 1))
    assert result.message == (
        f"Invalid meal plan: items must be a list of 1 to {config.MEAL_PLAN_MAX_ITEMS} foods, "
        "each with food and grams."
    )


def test_the_limit_of_foods_is_accepted():
    """Exactly the most foods allowed is a valid plan."""
    result = _evaluate([{"food": "rolled oats", "grams": 10}] * config.MEAL_PLAN_MAX_ITEMS)
    assert result.status == "ok"
    assert result.totals.kcal == 38 * config.MEAL_PLAN_MAX_ITEMS


def test_the_requested_name_is_the_cleaned_food_name():
    """Spaces around a food name are dropped, as in the food lookup."""
    result = _evaluate([{"food": "  rolled oats  ", "grams": 80}])
    assert result.items[0].requested == "rolled oats"


def test_targets_that_are_not_valid_are_a_programming_error():
    """The wrapper only passes valid targets; anything else raises instead of comparing."""
    invalid = calculate_macro_targets(10.0, "maintain", 2000)
    assert invalid.status == "invalid"
    with pytest.raises(ValueError, match="valid profile"):
        _evaluate(DAY, invalid)


def test_with_no_similar_name_the_message_says_how_the_table_names_foods():
    """When no food has a suggestion, the message points to plainer names, as the lookup does."""
    result = _evaluate([UNKNOWN])
    assert result.message.endswith(
        "No similar name: the table holds single, unprocessed foods under plainer names "
        "(e.g. 'rolled oats')."
    )
