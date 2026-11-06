"""views/tables.py: table rows, cells and text lines, built without Streamlit or AppTest (T8.1)."""

import html
import re
from datetime import date
from decimal import Decimal

import pytest

from src import chat, config, dashboard, i18n, metrics, usage
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
        ("![x](http://evil)", "!\\[x\\](http\u2060\\://evil)"),
    ],
)
def test_one_line_escapes_what_markdown_would_read_as_a_block_or_image(text, expected):
    """The text is on one line and a line start or image never becomes formatting."""
    assert tables.one_line(text) == expected


# The patterns remark-gfm's autolink step runs over the parsed text (backslash escapes already
# gone), as JavaScript reads them: \w is ASCII only, so a word joiner breaks them.
GFM_URL = re.compile(r"(https?://|www(?=\.))[-.\w]+", re.I | re.ASCII)
GFM_EMAIL = re.compile(r"[-.+\w]+@[-\w]+(?:\.[-\w]+)+", re.ASCII)
UNESCAPE = re.compile(r"\\(.)")
# A character reference Markdown decodes while it parses, unless its "&" is escaped. It
# looks at one backslash only: an escaped backslash before a reference (two, then "&")
# would be decoded by Markdown but not here; one_line() escapes every backslash and "&",
# so its output never holds one (code review round 14).
REFERENCE = re.compile(r"(?<!\\)&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")


def _parsed(markdown: str) -> str:
    """Return the text Markdown leaves for remark-gfm: references decoded, escapes removed."""
    decoded = REFERENCE.sub(lambda found: html.unescape(found.group()), markdown)
    return UNESCAPE.sub(r"\1", decoded)


@pytest.mark.parametrize(
    "text",
    [
        "see www.attacker.example/w?w=82",
        "WWW.attacker.example",
        "x@attacker.example",
        "plain https://attacker.example/x?k=1050",
        "http://attacker.example",
        "mailto:x@attacker.example",
        # Round 12: an underscore before the host or scheme (remark-gfm accepts it there).
        "x_www.attacker.example/?k=1043",
        "_https://attacker.example",
        # Round 13: a character reference Markdown would decode into the colon, dot or "@".
        "https&#58;//attacker.example?k=1043",
        "www&period;attacker.example",
        "x&#64;attacker.example",
        "x&commat;attacker.example",
    ],
)
def test_one_line_leaves_no_text_that_markdown_turns_into_a_link(text):
    """No www. host, URL or e-mail address stays linkable (checked in a browser, 2026-11-06)."""
    rendered = _parsed(tables.one_line(text))
    assert GFM_URL.search(rendered) is None and GFM_EMAIL.search(rendered) is None
    # Without one_line() the same text would be a link: the patterns above are the real ones.
    unescaped = _parsed(text)
    assert GFM_URL.search(unescaped) or GFM_EMAIL.search(unescaped)
    assert rendered.replace(tables.WORD_JOINER, "") == text  # shown as written


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


def test_distinct_filters_lists_each_filter_of_the_searches_once():
    """Topics, years and tiers of several searches come back once each, in order (T9.3)."""
    searches = [
        chat.SearchDetails("a", topics=("protein",), min_year=2020, evidence_tier=1),
        chat.SearchDetails("b", topics=("protein", "fat"), min_year=2015, evidence_tier=2),
        chat.SearchDetails("c"),
    ]
    assert tables.distinct_filters(searches) == (("protein", "fat"), (2020, 2015), (1, 2))


def test_distinct_filters_is_empty_only_when_no_search_set_one():
    """Searches with no filter give nothing; one tier filter alone still counts."""
    assert tables.distinct_filters([chat.SearchDetails("a"), chat.SearchDetails("b")]) == (
        (),
        (),
        (),
    )
    assert tables.distinct_filters([chat.SearchDetails("a", evidence_tier=1)]) == ((), (), (1,))


# --- My data's tables (T9.5) ---------------------------------------------------------------------

WEIGHT_ROW = {"id": 3, "weight_kg": 80.0, "measured_on": "2026-11-01", "recorded_at": "x"}
TARGET_ROW = {
    "id": 4,
    "kcal": 2450.0,
    "protein_g": 160.0,
    "carbs_g": 280.0,
    "fat_g": 70.0,
    "set_by": "system",
    "calc_version": "macro-targets-1",
    "effective_from": "2026-11-01",
    "created_at": "2026-11-01T08:00:00+00:00",
}


def test_every_stored_kind_has_columns_and_labels_in_both_languages():
    """Each kind of record My data lists has its columns and texts in English and German."""
    for kind in tables.STORED_KINDS:
        for lang in ("en", "de"):
            assert i18n.t(f"my_data.kind.{kind}", lang)
            for column in tables.STORED_COLUMNS[kind]:
                assert i18n.t(f"my_data.col.{column}", lang)


def test_a_weight_shows_in_the_users_units_and_language():
    """A stored weight in kg shows in pounds for imperial, with German decimal marks in German."""
    assert tables.stored_table("body_measurements", [WEIGHT_ROW], "metric", "de") == {
        "Tag": ["2026-11-01"],
        "Gewicht": ["80 kg"],
    }
    assert tables.stored_cells("body_measurements", WEIGHT_ROW, "imperial", "en")[1].endswith("lb")


def test_a_target_row_names_who_set_it():
    """A target shows its numbers with thousands marks and "The app" for set_by system."""
    cells = tables.stored_cells("nutrition_targets", TARGET_ROW, "metric", "en")
    assert cells == ["2026-11-01", "2,450", "160", "280", "70", "The app"]


def test_an_entry_label_starts_with_its_kind():
    """The delete picker names the kind first, then the record's cells."""
    label = tables.entry_label("body_measurements", WEIGHT_ROW, "metric", "en")
    assert label == "Weights · 2026-11-01 · 80 kg"


# --- The coach's client list and invitations (T9.12) --------------------------------------------

CLIENT_ROWS = [
    {
        "other_name": "Alex",
        "status": "active",
        "accepted_at": "2026-11-01T09:00:00+00:00",
        "ended_at": None,
        "scopes": ("nutrition", "body"),
    },
    {
        "other_name": "Bo",
        "status": "ended",
        "accepted_at": "2026-10-01T09:00:00+00:00",
        "ended_at": "2026-10-20T18:30:00+00:00",
        "scopes": (),
    },
]


MONDAY = date(2026, 10, 26)


def _meal(day: str, kcal: float) -> dict:
    """Return a stored meal item row of one day with the given kcal."""
    return {
        "consumed_on": day,
        "kcal": kcal,
        "protein_g": 100.0,
        "carbohydrate_g": 200.0,
        "fat_g": 50.0,
        "fiber_g": 10.0,
    }


TARGET = {
    "id": 1,
    "effective_from": "2026-10-01",
    "kcal": 2400.0,
    "protein_g": 150.0,
    "carbs_g": 250.0,
    "fat_g": 70.0,
    "set_by": "system",
}
WEIGHTS = [
    {"id": 1, "measured_on": "2026-10-20", "weight_kg": 80.0},
    {"id": 2, "measured_on": "2026-10-28", "weight_kg": 79.4},
]


def _week(
    shared=("nutrition", "body", "training"), meals=None, reviews=()
) -> dashboard.DashboardWeek:
    """Return a dashboard week of three logged days, a target, two weights and one workout."""
    if meals is None:
        meals = [_meal("2026-10-26", 2000), _meal("2026-10-27", 2200), _meal("2026-10-29", 2300)]
    nutrition = metrics.week_metrics(meals, WEIGHTS, [TARGET], MONDAY)
    session = {"id": 1, "performed_on": "2026-10-27", "sets": []}
    return dashboard.DashboardWeek(
        shared=frozenset(shared),
        nutrition=nutrition,
        training=metrics.training_week([session], MONDAY) if "training" in shared else None,
        volume_by_day=metrics.volume_by_day([session], MONDAY) if "training" in shared else None,
        weight_trend=None,
        reviews=tuple(reviews) if "nutrition" in shared else None,
    )


def test_the_logged_days_are_counted_out_of_the_whole_week():
    """AC-26: three logged days out of seven are "3 of 7 days logged"."""
    assert tables.logged_days_line(_week().nutrition, "en") == "3 of 7 days logged"
    assert tables.logged_days_line(_week().nutrition, "de") == "3 von 7 Tagen erfasst"


def test_a_week_in_progress_still_counts_out_of_seven():
    """AC-26 (owner's choice, 2026-10-30): four days logged by Friday are "4 of 7", not "4 of 5"."""
    # The week's Friday is today: nothing after it can be logged yet, and the count is still of 7.
    meals = [_meal(f"2026-10-{day}", 2000) for day in (26, 27, 28, 30)]
    week = metrics.week_metrics(meals, [], [], MONDAY)
    assert tables.logged_days_line(week, "en") == "4 of 7 days logged"


def test_the_average_kcal_is_over_the_logged_days_against_the_target():
    """The kcal cell is the average over the logged days, then the target."""
    assert tables.kcal_vs_target(_week().nutrition, "en") == "2,167 / 2,400 kcal"
    assert tables.kcal_vs_target(_week().nutrition, "de") == "2.167 / 2.400 kcal"
    no_target = metrics.week_metrics([_meal("2026-10-26", 1999.6)], [], [], MONDAY)
    assert tables.kcal_vs_target(no_target, "en") == "2,000 kcal (no target)"
    nothing = metrics.week_metrics([], [], [TARGET], MONDAY)
    assert tables.kcal_vs_target(nothing, "en") == "Nothing logged"


CLIENT = {"other_id": "gym-alex", "other_name": "Alex", "accepted_at": "2026-11-01T09:00:00+00:00"}


def test_an_active_client_s_row_holds_the_week_s_values():
    """One row: name, since, days logged, kcal against target, sessions, latest weight, review."""
    review = {"id": 7, "status": "APPROVED", "period_start": "2026-10-19"}
    cells = tables.client_cells(CLIENT, _week(reviews=[review]), "metric", "en")
    assert cells == {
        "name": "Alex",
        "since": "2026-11-01",
        "logged": "3 of 7 days logged",
        "kcal": "2,167 / 2,400 kcal",
        "sessions": "1",
        "weight": "79.4 kg (2026-10-28)",
        "review": "Approved · week of 2026-10-19",
    }
    table = tables.client_table([cells], "en")
    assert list(table) == [
        "Client",
        "Since",
        "Days logged",
        "Avg kcal / target",
        "Sessions",
        "Latest weight",
        "Weekly review",
    ]
    assert [column[0] for column in table.values()] == list(cells.values())


def test_a_scope_not_shared_says_so_in_its_cells():
    """Nutrition and training not shared: their cells say "Not shared", the weight shows."""
    cells = tables.client_cells(CLIENT, _week(shared=("body",)), "imperial", "en")
    assert cells["logged"] == cells["kcal"] == cells["review"] == "Not shared"
    assert cells["sessions"] == "Not shared"
    assert cells["weight"] == "175 lb (2026-10-28)"


def test_no_review_and_no_weight_are_shown_as_such():
    """No review yet is "None"; no weight is a dash."""
    week = _week()
    empty = type(week)(**{**week.__dict__, "nutrition": metrics.week_metrics([], [], [], MONDAY)})
    cells = tables.client_cells(CLIENT, empty, "metric", "de")
    assert (cells["review"], cells["weight"]) == ("Keiner", "–")
    assert cells["logged"] == "0 von 7 Tagen erfasst"


def test_a_card_holds_the_same_values_as_the_table_row_escaped():
    """The phone card lists every cell of the row, the name escaped as plain text."""
    cells = tables.client_cells({**CLIENT, "other_name": "1. Max_*"}, _week(), "metric", "en")
    card = tables.client_card(cells, "en")
    lines = card.split("  \n")
    assert lines[0] == r"**1\. Max\_\***"
    assert lines[1:] == [
        r"**Since:** 2026\-11-01",  # a value that starts like a list item is escaped
        "**Days logged:** 3 of 7 days logged",
        "**Avg kcal / target:** 2,167 / 2,400 kcal",
        "**Sessions:** 1",
        r"**Latest weight:** 79\.4 kg (2026-10-28)",
        "**Weekly review:** None",
    ]


def test_the_former_clients_keep_only_name_and_days():
    """An ended relationship shows its name and days, nothing of the client's data."""
    table = tables.former_client_table(CLIENT_ROWS[1:], "en")
    assert table == {"Client": ["Bo"], "Since": ["2026-10-01"], "Ended": ["2026-10-20"]}


def test_the_target_and_body_lines():
    """The target names who set it and from when; the body lines give the latest and the change."""
    week = _week()
    assert tables.target_line(week.nutrition.target, "en") == (
        "Daily target: 2,400 kcal, worked out from the profile, from 2026-10-01."
    )
    assert tables.target_line(None, "de") == "Noch kein Tagesziel."
    assert tables.body_lines(week, "metric", "en") == [
        "Latest weight: 79.4 kg (2026-10-28).",
        "Change since 2026-10-20: -0.6 kg.",
    ]
    assert tables.weight_change_text(0.45, "imperial", "de") == "+1 lb"
    assert tables.weight_change_text(-0.03, "metric", "en") == "0 kg"  # never "-0 kg"


def test_an_approved_review_is_labelled_as_an_ai_draft():
    """AC-41: each review says it is an AI draft the coach approved (or edited and approved)."""
    review = {"period_start": "2026-10-19", "reviewed_at": "2026-10-27T08:00:00+00:00"}
    assert tables.review_label({**review, "edited_by_coach": False}, "en") == (
        "AI draft, approved by the coach"
    )
    assert tables.review_label({**review, "edited_by_coach": True}, "de") == (
        "KI-Entwurf, vom Coach bearbeitet und freigegeben"
    )
    assert tables.review_heading(review, "en") == "Week of 2026-10-19 · approved on 2026-10-27"


def test_a_review_s_texts_are_listed_escaped():
    """Every text of the review is one escaped list line: no link, image or heading gets through."""
    final = {
        "observations": ["Logged 3 of 7 days.", {"text": "![x](https://evil.example/a.png)"}],
        "summary": "# Big",
        "count": 3,
    }
    assert tables.review_markdown(final).split("\n") == [
        "- Logged 3 of 7 days.",
        "- !\\[x\\](https\u2060\\://evil.example/a.png)",  # neither an image nor a link
        r"- \# Big",
    ]


def test_the_invitation_table_and_label_never_hold_a_code():
    """Unused codes are listed by their days and state only (the store returns no code)."""
    rows = [
        {
            "id": 1,
            "created_at": "2026-11-03T10:00:00+00:00",
            "expires_at": "2026-11-10T10:00:00+00:00",
            "expired": False,
        },
        {
            "id": 2,
            "created_at": "2026-10-01T10:00:00+00:00",
            "expires_at": "2026-10-08T10:00:00+00:00",
            "expired": True,
        },
    ]
    table = tables.invitation_table(rows, "en")
    assert table == {
        "Created": ["2026-11-03", "2026-10-01"],
        "Expires": ["2026-11-10", "2026-10-08"],
        "State": ["Open", "Expired"],
    }
    assert tables.invitation_label(rows[0], "en") == "Created 2026-11-03 · expires 2026-11-10"


# --- The Today page (T9.13) -----------------------------------------------------------------------


def _item(meal: str, kcal: float, fiber: float | None = 2.0, item_id: int = 1) -> dict:
    """Return a stored food entry with round numbers."""
    return {
        "id": item_id,
        "meal": meal,
        "food_name": "Oats, rolled",
        "grams": 150.0,
        "kcal": kcal,
        "protein_g": 19.8,
        "carbohydrate_g": 102.0,
        "fat_g": 9.6,
        "fiber_g": fiber,
    }


def test_meal_groups_follow_the_days_order_and_leave_out_empty_meals():
    """Breakfast, lunch, dinner, snack; a meal with no entries is not listed."""
    items = [_item("snack", 100), _item("breakfast", 300), _item("snack", 50)]
    groups = tables.meal_groups(items)
    assert [meal for meal, _ in groups] == ["breakfast", "snack"]
    assert len(groups[1][1]) == 2


def test_the_diary_table_rounds_as_the_food_lookup_does():
    """kcal whole, grams to one decimal, and a dash for fiber not reported."""
    table = tables.diary_table([_item("lunch", 570.44, fiber=None)], "de")
    assert table["Lebensmittel"] == ["Oats, rolled"]
    assert table["kcal"] == ["570"]
    assert table["Protein (g)"] == ["19,8"]
    assert table["Ballaststoffe (g)"] == ["–"]


@pytest.mark.parametrize(("complete", "text"), [(True, "4 g"), (False, "4 g or more")])
def test_a_total_marks_fiber_not_reported(complete, text):
    """A total with a food that had no fiber value is a lower bound."""
    assert tables.intake_fiber(4.0, complete, "en").startswith(text)


def test_the_meal_and_day_lines():
    """A meal's heading has its kcal; the day's line has the totals."""
    items = [_item("lunch", 300.4), _item("lunch", 200.4, fiber=None)]
    assert tables.meal_total_line("lunch", items, "en") == "**Lunch** · 501 kcal"
    line = tables.day_total_line(metrics.day_totals(items), "en")
    assert line.startswith("**Day total:** 501 kcal · protein 39.6 g")
    assert line.endswith("fiber 2 g or more (not reported for some foods)")


def test_the_entry_label_names_meal_food_grams_and_kcal():
    """The edit picker shows one entry on one line."""
    label = tables.diary_entry_label(_item("dinner", 570.4), "en")
    assert label == "Dinner · Oats, rolled · 150 g · 570 kcal"


def test_the_weights_line_is_in_the_users_units():
    """A day's weights are listed in kg or lb."""
    rows = [{"weight_kg": 80.0}, {"weight_kg": 79.5}]
    assert tables.weights_line(rows, "metric", "en") == "Logged on this day: 80 kg, 79.5 kg"
    assert "176.4 lb" in tables.weights_line(rows, "imperial", "en")


# --- The Workouts page's tables (T9.14): facts only, in the user's units --------------------------

WORKOUT_ROW = {
    "id": 1,
    "performed_on": "2026-10-26",
    "recorded_at": "2026-10-26T18:00:00+00:00",
    "sets": [
        {"exercise_id": "squat", "set_no": 1, "reps": 5, "weight_kg": 102.5, "rpe": 8.5},
        {"exercise_id": "pull_up", "set_no": 2, "reps": 10, "weight_kg": 0.0, "rpe": None},
    ],
}


def test_a_workout_s_sets_table():
    """Each set shows its number, exercise with its group, reps, weight and RPE (or a dash)."""
    table = tables.sets_table(WORKOUT_ROW["sets"], "metric", "en")
    assert table == {
        "Set": ["1", "2"],
        "Exercise": ["Squat · Legs", "Pull-up · Back"],
        "Reps": ["5", "10"],
        "Weight": ["102.5 kg", "0 kg"],
        "RPE": ["8.5", "–"],
    }


def test_the_sets_table_in_german_and_pounds():
    """German labels and decimal marks, and the weight in lb for imperial units."""
    table = tables.sets_table(WORKOUT_ROW["sets"], "imperial", "de")
    assert table["Übung"] == ["Kniebeuge · Beine", "Klimmzug · Rücken"]
    assert table["Gewicht"] == ["226 lb", "0 lb"]
    assert table["RPE"] == ["8,5", "–"]


def test_the_week_table_and_lines():
    """The week's table and lines give the sessions, sets, volume and top weight."""
    week = metrics.training_week([WORKOUT_ROW], date(2026, 10, 26))
    assert tables.training_week_table(week, "metric", "en") == {
        "Exercise": ["Squat · Legs", "Pull-up · Back"],
        "Sets": ["1", "1"],
        "Reps": ["5", "10"],
        "Volume": ["512 kg", "0 kg"],
        "Top weight": ["102.5 kg", "0 kg"],
    }
    assert tables.training_week_line(week, "metric", "de") == (
        "2026-10-26 bis 2026-11-01 · Einheiten: 1 · Sätze: 2 · Volumen: 512 kg"
    )
    assert tables.session_line(WORKOUT_ROW, "metric", "en") == (
        "**2026-10-26** · Sets: 2 · Volume: 512 kg"
    )


@pytest.mark.parametrize(
    ("volume_kg", "system", "lang", "expected"),
    [
        (2310.0, "metric", "en", "2,310 kg"),
        (2310.0, "metric", "de", "2.310 kg"),
        (1000.0, "imperial", "en", "2,205 lb"),
        (1_234_567.0, "metric", "en", "1,234,567 kg"),
    ],
)
def test_a_volume_is_a_whole_number_in_the_user_s_units(volume_kg, system, lang, expected):
    """A volume is rounded to a whole number with the language's thousands marks."""
    assert tables.volume_text(volume_kg, system, lang) == expected


def test_an_exercise_no_longer_on_the_list_is_shown_by_its_id():
    """A stored ID the list no longer has is shown as it is, never as an error."""
    assert tables.exercise_label("old_exercise", "en") == "old_exercise"


def test_my_data_shows_a_workout_s_sets_and_volume():
    """My data's workouts table has the day, the number of sets and the volume (AC-24)."""
    cells = tables.stored_cells("workout_sessions", WORKOUT_ROW, "metric", "en")
    assert cells == ["2026-10-26", "2", "512 kg"]


def _review_text() -> dict:
    """Return a T9.16 review text with a hostile observation and a training recommendation."""
    return {
        "observations": [{"text": "![x](https://evil.example/a.png) # Big", "evidence": ["S2"]}],
        "hypotheses": [],
        "recommendations": [
            {
                "kind": "training",
                "text": "Consider more leg work [S2].",
                "evidence": ["S2"],
                "model_suggestion": False,
                "direction": "increase",
                "source_range": "10-20 sets per week",
                "population": "trained adults",
            },
            {
                "kind": "nutrition",
                "text": "Log every day.",
                "evidence": [],
                "model_suggestion": True,
                "direction": None,
                "source_range": None,
                "population": None,
            },
        ],
        "language": "en",
        "sources": {"S2": {"source_id": "1", "chunk_id": "1-3"}, "S9": {"source_id": "zz"}},
    }


def test_a_review_s_sections_are_escaped_lines_under_the_app_s_headings():
    """T9.16: empty sections are left out; texts escaped; kind, suggestion and training fields."""
    sections = tables.review_sections(_review_text(), "en")
    assert [heading for heading, _ in sections] == ["Observations", "Recommendations"]
    observations = sections[0][1]
    # Neither an image nor a link; a "#" in the middle of a line is no heading.
    assert observations == "- !\\[x\\](https\u2060\\://evil.example/a.png) # Big"
    lines = sections[1][1].split("\n")
    assert lines[0] == r"- **Training:** Consider more leg work \[S2\]."
    assert r"    - Range in the source: 10\-20 sets per week" in lines  # shown as 10-20
    suggestion = "*(The model's suggestion, no source cited)*"
    assert lines[-1] == f"- **Nutrition:** Log every day. {suggestion}"
    german = tables.review_sections(_review_text(), "de")
    assert [heading for heading, _ in german] == ["Beobachtungen", "Empfehlungen"]


def test_a_review_s_sources_follow_its_labels_and_skip_what_the_app_does_not_know():
    """[S2] lists source 1's title and link; an unknown source or a review with none is left out."""
    manifest = chat.manifest_by_id()
    lines = tables.review_source_lines(_review_text(), manifest, "en")
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith(r"[\[S2\] ") and str(manifest["1"].year) in line
    assert f"]({chat.markdown_url(manifest['1'].url)})" in line
    assert tables.review_source_lines({"observations": []}, manifest, "en") == []


def test_a_review_s_sources_credit_the_authors_and_the_licence():
    """Each source line names the authors and links the licence, as the chat's card does."""
    manifest = chat.manifest_by_id()
    line = tables.review_source_lines(_review_text(), manifest, "en")[0]
    source = manifest["1"]
    assert tables.one_line(chat.format_authors(source.authors)) in line
    assert f"[{tables.one_line(source.license)}]({chat.markdown_url(source.license_url)})" in line


def test_only_a_text_with_the_three_sections_counts_as_t9_16_s_fields():
    """An older review (T9.15's free form) falls back to the plain escaped list."""
    assert tables.has_review_fields(_review_text())
    assert not tables.has_review_fields({"observations": ["x"]})
    assert not tables.has_review_fields({"observations": [], "hypotheses": []})


# --- The questions to the coach (T9.25) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        ("2026-10-27T10:05:00+00:00", "2026-10-27 11:05"),  # winter time, UTC+1
        ("2026-07-01T22:30:00+00:00", "2026-07-02 00:30"),  # summer time, the next day in Berlin
    ],
)
def test_a_stored_time_is_shown_in_berlin(stored, shown):
    """The thread's times are Berlin's, to the minute (D21)."""
    assert tables.berlin_time(stored) == shown


@pytest.mark.parametrize(
    ("kind", "viewer", "lang", "label"),
    [
        ("question", "gymer", "en", "Your question · 2026-10-27 11:05"),
        ("question", "coach", "en", "The client's question · 2026-10-27 11:05"),
        ("answer", "gymer", "en", "Written by the coach, not by AI · 2026-10-27 11:05"),
        ("answer", "coach", "en", "Your answer · 2026-10-27 11:05"),
        ("answer", "gymer", "de", "Vom Coach geschrieben, nicht von der KI · 2026-10-27 11:05"),
    ],
)
def test_a_thread_row_is_labelled_by_kind_and_reader(kind, viewer, lang, label):
    """Who wrote a row and when; the coach's answer never reads as the AI's (AC-41)."""
    row = {"kind": kind, "created_at": "2026-10-27T10:05:00+00:00", "text": "CANARY"}
    assert tables.thread_label(row, viewer, lang) == label


def test_the_weeks_waiting_for_an_answer():
    """Only a thread whose last row is a question waits; weeks oldest first, each once."""
    reviews = [
        {"id": 1, "period_start": "2026-10-19"},
        {"id": 2, "period_start": "2026-10-12"},
        {"id": 3, "period_start": "2026-10-05"},
    ]
    rows = [
        {"review_id": 1, "kind": "question"},
        {"review_id": 2, "kind": "question"},
        {"review_id": 2, "kind": "answer"},
        {"review_id": 3, "kind": "question"},
    ]
    assert tables.waiting_weeks(reviews, rows) == ["2026-10-05", "2026-10-19"]
    assert tables.waiting_weeks(reviews, []) == []
