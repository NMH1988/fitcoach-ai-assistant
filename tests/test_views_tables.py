"""views/tables.py: table rows, cells and text lines, built without Streamlit or AppTest (T8.1)."""

from decimal import Decimal

import pytest

from src import config, i18n, usage
from src.tools import energy, registry
from src.tools.food import FoodLookupResult, Nutrients
from tests.fakes import PROFILE
from views import tables


@pytest.fixture
def macros() -> registry.MacroToolResult:
    """Return the macro targets of the sample profile (resting 1780, needs 2759 kcal a day)."""
    result = registry.macro_targets(PROFILE)
    assert isinstance(result, registry.MacroToolResult)
    return result


def _food(alternatives: list[str], fiber: float | None = 2.5) -> FoodLookupResult:
    """Return a found food of 150 g with the given other close names and fiber."""
    return FoodLookupResult(
        status="found",
        message="ok",
        grams=150.0,
        matched_name="Oats, rolled",
        nutrients=Nutrients(
            kcal=1234, protein_g=20.5, carbohydrate_g=99.0, fat_g=8.25, fiber_g=fiber
        ),
        alternatives=alternatives,
    )


def test_dollar_signs_are_escaped_so_markdown_never_reads_latex():
    """Two dollar signs in a cost line are escaped."""
    assert tables.dollars("$0.0014 and $0.0027") == r"\$0.0014 and \$0.0027"


def test_bold_label_bolds_only_the_label():
    """The text before the first ": " is bold; later colons stay in the value."""
    assert tables.bold_label("This answer: 1,234 tokens: x") == "**This answer:** 1,234 tokens: x"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  two   words\nnext ", "two words next"),
        ("# Big", r"\# Big"),
        ("1. step", r"1\. step"),
        ("- item", r"\- item"),
        ("> quote", r"\> quote"),
        ("![x](http://evil)", r"!\[x\](http\://evil)"),
    ],
)
def test_one_line_escapes_what_markdown_would_read_as_a_block_or_image(text, expected):
    """The text is on one line and a line start or image never becomes formatting."""
    assert tables.one_line(text) == expected


def test_columns_turns_rows_into_named_columns():
    """Rows of cells become one list per name."""
    assert tables.columns(("a", "b"), [["1", "2"], ["3", "4"]]) == {
        "a": ["1", "3"],
        "b": ["2", "4"],
    }


@pytest.mark.parametrize(
    ("tier", "lang", "expected"),
    [
        (1, "en", "ISSN position stand"),
        (1, "de", "ISSN-Positionspapier"),
        (99, "en", "Review"),
        (99, "de", "Übersichtsarbeit"),
    ],
)
def test_a_tier_is_named_in_the_language_and_an_unknown_one_is_a_review(tier, lang, expected):
    """Tier 1 has its own name; a tier the app does not know is called a review."""
    assert tables.tier_label(tier, lang) == expected


def test_a_topic_the_app_does_not_know_is_shown_as_it_is():
    """An unknown topic is its own label; a known one is translated."""
    assert tables.topic_label("not_a_topic", "en") == "not_a_topic"
    topic = next(iter(config.TOPICS))
    assert tables.topic_label(topic, "de") == i18n.t(f"topic.{topic}", "de")


@pytest.mark.parametrize(
    ("fiber", "lang", "expected"),
    [
        (None, "en", "not reported"),
        (None, "de", "nicht angegeben"),
        (2.5, "en", "2.5 g"),
        (2.5, "de", "2,5 g"),
    ],
)
def test_fiber_is_a_number_with_the_languages_decimal_mark_or_not_reported(fiber, lang, expected):
    """Fiber reads "2.5 g" or "2,5 g"; USDA giving no value reads "not reported"."""
    assert tables.fiber_text(fiber, lang) == expected


def test_the_macros_come_in_the_colour_order_and_a_missing_one_is_left_out(macros):
    """Protein, carbohydrate, fat; a target the tool did not set is not listed."""
    assert list(tables.macro_parts(macros.targets)) == ["Protein", "Carbohydrate", "Fat"]
    partial = macros.targets.model_copy(update={"fat": None})
    assert list(tables.macro_parts(partial)) == ["Protein", "Carbohydrate"]


def test_the_kcal_of_each_macro_is_its_grams_times_its_energy_per_gram(macros):
    """Each macro's kcal is grams x kcal per gram (4, 4 and 9)."""
    targets = macros.targets
    assert tables.macro_kcal(targets) == {
        "Protein": targets.protein.grams * config.KCAL_PER_G_PROTEIN,
        "Carbohydrate": targets.carbohydrate.grams * config.KCAL_PER_G_CARBOHYDRATE,
        "Fat": targets.fat.grams * config.KCAL_PER_G_FAT,
    }


def test_complete_targets_are_recognised(macros):
    """A result with a target, a weight, daily needs and all three macros is complete."""
    assert tables.has_targets(macros)


@pytest.mark.parametrize("missing", ["kcal_target", "weight_kg", "fat"])
def test_targets_missing_a_part_are_not_complete(macros, missing):
    """No target, no weight or no fat target means there is nothing complete to show."""
    targets = macros.targets.model_copy(update={missing: None})
    assert not tables.has_targets(macros.model_copy(update={"targets": targets}))


def test_something_that_is_not_a_macro_result_has_no_targets():
    """Other results and plain values are never complete targets."""
    assert not tables.has_targets(None)
    assert not tables.has_targets(energy.TdeeResult(status="invalid", message="x"))


def test_the_daily_needs_missing_means_the_targets_are_not_complete(macros):
    """Without daily energy needs the result is not complete."""
    needs = macros.energy_needs.model_copy(update={"tdee_kcal": None})
    assert not tables.has_targets(macros.model_copy(update={"energy_needs": needs}))


def test_grams_per_body_weight_follow_the_unit_system(macros):
    """The same macro reads g/kg in metric and g/lb in imperial, from the unrounded weight."""
    macro = macros.targets.protein
    # 152 g of protein at 80 kg (176.4 lb), rounded once from the grams and the weight.
    assert tables.per_body_weight(macro, macros.targets, "metric", "en") == "1.9 g/kg"
    assert tables.per_body_weight(macro, macros.targets, "imperial", "en") == "0.86 g/lb"
    assert tables.per_body_weight(macro, macros.targets, "metric", "de") == "1,9 g/kg"


def test_a_macro_row_has_grams_share_and_grams_per_weight(macros):
    """The cells are "<n> g", "<p>%" and the per body weight text, in that order."""
    macro = macros.targets.protein
    assert tables.macro_cells(macro, macros.targets, "metric", "en") == ["152 g", "20%", "1.9 g/kg"]


def test_german_cells_use_the_german_percent_and_number_marks(macros):
    """German writes "20 %" with a space and a comma or point as its number marks."""
    macro = macros.targets.protein
    assert tables.macro_cells(macro, macros.targets, "metric", "de") == [
        "152 g",
        "20 %",
        "1,9 g/kg",
    ]


def test_the_protein_range_names_grams_and_grams_per_body_weight(macros):
    """The range line holds both ends in grams and per body weight."""
    text = tables.protein_range(macros.targets, "metric", "en")
    # The sources' range for 80 kg is 128-176 g (1.6-2.2 g/kg).
    assert macros.targets.protein_g_range == (128, 176)
    assert "128" in text
    assert "176" in text
    assert "1.6" in text
    assert "2.2" in text


@pytest.mark.parametrize(
    ("difference", "expected"), [(0, None), (500, "+500 kcal"), (-1500, "-1,500 kcal")]
)
def test_the_kcal_delta_is_signed_and_absent_at_maintenance(difference, expected):
    """A surplus has a plus, a deficit a minus with thousands marks, and zero has no delta."""
    assert tables.kcal_delta(difference, "en") == expected


def test_the_german_kcal_delta_uses_the_german_thousands_mark():
    """German writes "-1.500 kcal"."""
    assert tables.kcal_delta(-1500, "de") == "-1.500 kcal"


@pytest.mark.parametrize(
    ("difference", "lang", "expected"),
    [
        (0, "en", "Build muscle: at maintenance"),
        (300, "en", "Build muscle: 300 kcal above maintenance"),
        (-1500, "en", "Build muscle: 1,500 kcal below maintenance"),
        (0, "de", "Muskeln aufbauen: auf Erhaltungsbedarf"),
        (300, "de", "Muskeln aufbauen: 300 kcal über dem Erhaltungsbedarf"),
        (-1500, "de", "Muskeln aufbauen: 1.500 kcal unter dem Erhaltungsbedarf"),
    ],
)
def test_the_goal_line_says_where_the_target_is_against_maintenance(difference, lang, expected):
    """The goal line names the goal and says at, above or below maintenance, by how much."""
    assert tables.goal_line("build_muscle", difference, lang) == expected


def test_the_tdee_rows_hold_resting_energy_factor_and_daily_needs():
    """Three rows, with the numbers as the language writes them."""
    result = registry.macro_targets(PROFILE).energy_needs
    rows = tables.tdee_rows(result, "en")
    assert list(rows.values())[0].startswith("1,780")
    assert list(rows.values())[2].startswith("2,759")
    german = tables.tdee_rows(result, "de")
    assert list(german.values())[0].startswith("1.780")
    assert list(german) != list(rows)


def test_the_macro_summary_rows_hold_target_range_needs_and_protein_range(macros):
    """Four rows: the daily target, its range, the energy needs and the protein range."""
    assert tables.macro_summary_rows(macros, "en") == {
        "Daily target": "3,035 kcal",
        "Range for the goal": "3,035-3,311 kcal",
        "Daily energy needs": "2,759 kcal",
        "Protein range": "128-176 g",
    }
    german = tables.macro_summary_rows(macros, "de")
    assert list(german.values()) == ["3.035 kcal", "3.035-3.311 kcal", "2.759 kcal", "128-176 g"]


def test_the_macro_table_has_a_row_per_macro_in_the_chosen_units(macros):
    """Macro, per day, share and per body weight, as columns; g/lb in imperial."""
    assert tables.macro_table(macros.targets, "imperial", "en") == {
        "Macro": ["Protein", "Carbohydrate", "Fat"],
        "Per day": ["152 g", "418 g", "84 g"],
        "Share of kcal": ["20%", "55%", "25%"],
        "Per lb of body weight": ["0.86 g/lb", "2.37 g/lb", "0.48 g/lb"],
    }
    german = list(tables.macro_table(macros.targets, "metric", "de").values())
    assert german[2] == ["20 %", "55 %", "25 %"]
    assert german[3] == ["1,9 g/kg", "5,2 g/kg", "1,1 g/kg"]


def test_a_found_food_is_a_table_of_its_amount_and_nutrients():
    """Seven rows, and the other close names as an eighth row only when there are some."""
    rows = tables.food_rows(_food([]), "en")
    assert list(rows.values()) == [
        "Oats, rolled",
        "150 g",
        "1,234 kcal",
        "20.5 g",
        "99 g",
        "8.25 g",
        "2.5 g",
    ]
    more = tables.food_rows(_food(["Oats, instant", "Oats, steel cut"]), "en")
    assert list(more.values())[-1] == "Oats, instant; Oats, steel cut"
    assert len(more) == 8


def test_a_food_without_a_fiber_value_says_not_reported():
    """USDA reporting no fiber shows the "not reported" text in the table."""
    rows = tables.food_rows(_food([], fiber=None), "de")
    assert list(rows.values())[6] == i18n.t("food.not_reported", "de")


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", ["Rewrite the question", "Embed the searches", "Answer, round 3"]),
        ("de", ["Frage umformulieren", "Suchanfragen einbetten", "Antwort, Runde 3"]),
    ],
)
def test_a_call_step_is_named_in_the_language(lang, expected):
    """The rewrite, search and answer steps have names; an unknown step is shown as it is."""
    steps = [
        config.USAGE_STEP_REWRITE,
        config.USAGE_STEP_SEARCH,
        config.USAGE_STEP_ANSWER.format(round=3),
    ]
    assert [tables.usage_step(step, lang) for step in steps] == expected
    assert tables.usage_step("Something else", lang) == "Something else"


def test_the_usage_rows_list_each_call_with_its_tokens_and_cost():
    """One row per call: step, model, input, cached, output, reasoning and the cost."""
    calls = (
        usage.CallUsage(config.USAGE_STEP_REWRITE, "m/a", 100, 20, 10, 5),
        usage.CallUsage(config.USAGE_STEP_ANSWER.format(round=1), "m/b", 2000, 400),
    )
    turn = usage.TurnUsage(calls, (Decimal("0.0001"), None))
    rows = tables.usage_rows(turn, "en")
    assert len(rows) == len(tables.USAGE_COLUMNS)
    columns = list(rows.values())
    assert columns[1] == ["m/a", "m/b"]
    assert columns[2] == [100, 2000]
    assert columns[3] == [10, 0]
    assert columns[0][1] == i18n.t("usage.step.answer", "en", round=1)
    assert columns[6][0] == usage.format_cost(Decimal("0.0001"), "en")
    assert columns[6][1] == usage.format_cost(None, "en")
