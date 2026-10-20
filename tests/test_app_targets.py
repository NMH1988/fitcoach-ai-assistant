"""UI tests for the targets views and the Food lookup tab: no model call, units, plain text."""

import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src import config, llm
from src.profile import UserProfile
from src.tools.energy import TDEE_METHOD, protein_lowered_note
from tests.fakes import HOSTILE_FOOD_NAME, PROFILE, write_food_table

APP = Path(__file__).resolve().parent.parent / "app.py"
TARGETS_TAB, FOOD_TAB = 1, 2
# A made-up profile whose protein by body weight and fat do not fit its target (2,054 kcal), so
# protein is lowered; the sources' range for 300 kg is 480-660 g.
HEAVY = UserProfile(
    weight_kg=300.0, height_cm=120.0, age=100, sex="female", activity="sedentary", goal="lose_fat"
)

pytestmark = pytest.mark.usefixtures("no_env_key")


@pytest.fixture(autouse=True)
def no_model(tmp_path, monkeypatch):
    """Give the app the fixture foods and make any model client fail the test if it is built."""

    def fail(*args, **kwargs):
        """Fail: the targets and the food lookup must not call a model."""
        raise AssertionError("a model client was built")

    monkeypatch.setattr(llm, "build_chat_model", fail)
    monkeypatch.setattr(llm, "build_embeddings", fail)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", write_food_table(tmp_path / "foods.csv"))
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _start(profile=PROFILE, system: str = "metric") -> AppTest:
    """Run the app with this profile (None: no profile) and unit system in the session."""
    at = AppTest.from_file(str(APP))
    at.secrets["UNRELATED"] = "x"
    if profile is not None:
        at.session_state["profile"] = profile
    at.session_state["units"] = system
    at.run(timeout=30)
    assert not at.exception
    return at


def _sidebar_metric(at: AppTest, label: str):
    """Return the sidebar metrics with this label."""
    return [metric for metric in at.sidebar.metric if metric.label == label]


def _card_captions(at: AppTest) -> list[str]:
    """Return the sidebar captions of the My targets card's macro lines."""
    return [c.value for c in at.sidebar.caption if c.value.startswith("**")]


def _spec(chart) -> dict:
    """Return a chart's Vega-Lite spec."""
    return json.loads(chart.proto.spec)


def _look_up(at: AppTest, food: str, grams: float) -> AppTest:
    """Type a food and grams in the Food lookup tab and press Look up."""
    at.text_input(key="food_query").set_value(food)
    at.number_input(key="food_grams").set_value(grams)
    return at.button(key="food_lookup").click().run(timeout=30)


# --- Sidebar: daily target and My targets card (AC 1) ---------------------------------------------


def test_with_a_profile_the_sidebar_shows_the_daily_target_and_the_card():
    """The sidebar has the daily target, a donut with the kcal in the middle and each macro."""
    at = _start()
    [target] = _sidebar_metric(at, "Daily target")
    assert target.value == "3,035 kcal"
    assert "**:material/target: My targets**" in [m.value for m in at.sidebar.markdown]
    [donut] = at.sidebar.get("vega_lite_chart")
    spec = _spec(donut)
    arc, *centre = spec["layer"]
    assert arc["mark"]["type"] == "arc" and arc["mark"]["innerRadius"] > 0
    assert [layer["data"]["values"][0]["line"] for layer in centre] == ["3,035", "kcal"]
    # Streamlit's chart theme leaves text marks black; currentColor follows the page's text colour
    # in both modes, even right after a theme switch (checked in the browser).
    assert {layer["mark"]["color"] for layer in centre} == {"currentColor"}
    assert _card_captions(at) == [
        "**Protein** 152 g · 20% · 1.9 g/kg",
        "**Carbohydrate** 418 g · 55% · 5.2 g/kg",
        "**Fat** 84 g · 25% · 1.1 g/kg",
    ]


def test_without_a_profile_the_sidebar_has_no_target_and_no_card():
    """Before a profile exists, neither the daily target nor the card is shown."""
    at = _start(profile=None)
    assert not _sidebar_metric(at, "Daily target")
    assert not at.sidebar.get("vega_lite_chart")
    assert not _card_captions(at)


# --- From calculate_macro_targets, no model call, following the profile (AC 2) --------------------


def test_the_targets_follow_the_sidebar_goal_without_a_model_call():
    """Changing the goal recalculates the target at once; the fixture fails if a model is built."""
    at = _start()
    at.sidebar.segmented_control(key="sidebar_goal").set_value("maintain").run(timeout=30)
    assert not at.exception
    [target] = _sidebar_metric(at, "Daily target")
    assert target.value == "2,759 kcal"
    assert at.tabs[TARGETS_TAB].metric[0].value == "2,759 kcal"


def test_the_targets_follow_the_profile():
    """Changing the profile in the session changes the targets on the next run."""
    at = _start()
    assert _sidebar_metric(at, "Daily target")[0].value == "3,035 kcal"
    at.session_state["profile"] = PROFILE.model_copy(update={"weight_kg": 60.0})
    at.run(timeout=30)
    assert not at.exception
    # Resting energy 1,580 kcal/day x 1.55 = 2,449; build muscle +10% = 2,694.
    assert _sidebar_metric(at, "Daily target")[0].value == "2,694 kcal"
    assert at.tabs[TARGETS_TAB].metric[0].value == "2,694 kcal"


# --- My targets tab (AC 3) ------------------------------------------------------------------------


def test_the_targets_tab_shows_four_metrics_a_bar_and_how_they_were_set():
    """Daily kcal with the surplus as delta, the three macros, the bar and the caption."""
    tab = _start().tabs[TARGETS_TAB]
    metrics = [(m.label, m.value) for m in tab.metric]
    assert metrics == [
        ("Daily target", "3,035 kcal"),
        ("Protein", "152 g"),
        ("Carbohydrate", "418 g"),
        ("Fat", "84 g"),
    ]
    # 3,035 - 2,759 = 276 kcal above maintenance, in grey (delta_color "off").
    assert tab.metric[0].proto.delta == "+276 kcal"
    assert "Build muscle: 276 kcal above maintenance" in [c.value for c in tab.caption]
    [bar] = tab.get("vega_lite_chart")
    assert _spec(bar)["mark"]["type"] == "bar"
    captions = " ".join(c.value for c in tab.caption)
    assert "about 2,759 kcal/day" in captions
    assert TDEE_METHOD in captions
    assert "Sources:" in captions and "Mifflin-St Jeor" in captions and "Aragon et al." in captions


def test_a_deficit_shows_as_a_negative_delta():
    """For fat loss the delta is the deficit, with its minus sign."""
    at = _start(profile=PROFILE.model_copy(update={"goal": "lose_fat"}))
    tab = at.tabs[TARGETS_TAB]
    assert tab.metric[0].proto.delta.startswith("-")
    assert any(
        c.value.startswith("Lose fat: ") and "below maintenance" in c.value for c in tab.caption
    )


def test_maintenance_shows_no_delta():
    """At maintenance there is no surplus or deficit to show."""
    at = _start(profile=PROFILE.model_copy(update={"goal": "maintain"}))
    tab = at.tabs[TARGETS_TAB]
    assert not tab.metric[0].proto.delta
    assert "Maintain: at maintenance" in [c.value for c in tab.caption]


def test_without_a_profile_the_targets_tab_opens_the_same_dialog():
    """The tab invites the user to add their details; its button opens the profile dialog."""
    at = _start(profile=None)
    tab = at.tabs[TARGETS_TAB]
    assert not tab.metric
    assert "Add your details" in tab.caption[0].value
    at = at.button(key="targets_add_details").click().run(timeout=30)
    assert at.session_state["profile_form_open"] is True
    assert at.get("dialog")


# --- Protein lowered (AC 5) -----------------------------------------------------------------------


def test_lowered_protein_shows_the_note_and_the_range_next_to_the_target():
    """A very heavy body with a low target: the tab warns with the note and the protein range."""
    at = _start(profile=HEAVY)
    tab = at.tabs[TARGETS_TAB]
    [warning] = tab.warning
    assert protein_lowered_note("lose_fat") in warning.value
    assert "480-660 g a day (1.6 g/kg to 2.2 g/kg)" in warning.value
    # The note is not repeated as a caption, and the sidebar card points to the tab.
    assert not [c for c in tab.caption if protein_lowered_note("lose_fat") in c.value]
    assert any("Protein was lowered" in c.value for c in at.sidebar.caption)


def test_ordinary_targets_show_no_protein_warning():
    """When protein fits, there is no warning."""
    at = _start()
    assert not at.tabs[TARGETS_TAB].warning
    assert not any("Protein was lowered" in c.value for c in at.sidebar.caption)


# --- Text alternatives; colour never the only signal (AC 7) ---------------------------------------


def test_every_targets_chart_has_a_text_alternative_naming_its_values():
    """The donut and the bar carry alt text with every value; the values are also shown as text."""
    at = _start()
    [donut] = at.sidebar.get("vega_lite_chart")
    assert donut.proto.alt == (
        "Daily target 3,035 kcal, energy split: Protein 608 kcal, Carbohydrate 1,672 kcal, "
        "Fat 756 kcal"
    )
    [bar] = at.tabs[TARGETS_TAB].get("vega_lite_chart")
    assert bar.proto.alt == (
        "Energy split per day: Protein 608 kcal, Carbohydrate 1,672 kcal, Fat 756 kcal"
    )
    captions = [c.value for c in at.tabs[TARGETS_TAB].caption]
    assert "20% of kcal · 1.9 g/kg" in captions


def test_the_targets_charts_use_the_macro_colours():
    """The donut and the bar take their colours from config.MACRO_COLORS."""
    at = _start()
    [donut] = at.sidebar.get("vega_lite_chart")
    [bar] = at.tabs[TARGETS_TAB].get("vega_lite_chart")
    expected = {"domain": list(config.MACRO_COLORS), "range": list(config.MACRO_COLORS.values())}
    assert _spec(donut)["layer"][0]["encoding"]["color"]["scale"] == expected
    assert _spec(bar)["encoding"]["color"]["scale"] == expected


# --- Per body weight in the chosen units (AC 8) ---------------------------------------------------


def test_imperial_users_see_grams_per_lb_in_the_card_and_the_tab():
    """In imperial the card and the tab show g/lb, from the grams and the weight, rounded once."""
    at = _start(system="imperial")
    assert _card_captions(at) == [
        "**Protein** 152 g · 20% · 0.86 g/lb",
        "**Carbohydrate** 418 g · 55% · 2.37 g/lb",
        "**Fat** 84 g · 25% · 0.48 g/lb",
    ]
    captions = [c.value for c in at.tabs[TARGETS_TAB].caption]
    assert "20% of kcal · 0.86 g/lb" in captions
    # 418 g and 84 g at 80 kg: from the rounded g/kg (5.2, 1.1) they would show 2.36 and 0.50.
    assert "55% of kcal · 2.37 g/lb" in captions
    assert "25% of kcal · 0.48 g/lb" in captions
    assert not [c for c in captions if "g/kg" in c and "% of kcal" in c]


def test_imperial_users_see_the_protein_range_in_grams_per_lb():
    """The protein range next to a lowered target follows the unit system too."""
    at = _start(profile=HEAVY, system="imperial")
    [warning] = at.tabs[TARGETS_TAB].warning
    assert "480-660 g a day (0.73 g/lb to 1.00 g/lb)" in warning.value


# --- Food lookup tab (AC 4) -----------------------------------------------------------------------


def test_the_food_lookup_tab_shows_the_food_and_its_nutrients_without_a_model_call():
    """A lookup shows the USDA name, the four values, fibre and the source; no model is built."""
    at = _look_up(_start(), "rolled oats", 80.0)
    assert not at.exception
    tab = at.tabs[FOOD_TAB]
    assert [t.value for t in tab.text] == ["Oats, whole grain, rolled, old fashioned"]
    assert [(m.label, m.value) for m in tab.metric] == [
        ("Energy", "304 kcal"),
        ("Protein", "10.6 g"),
        ("Carbohydrate", "54.4 g"),
        ("Fat", "5.1 g"),
    ]
    captions = [c.value for c in tab.caption]
    assert "Fiber: 8 g" in captions
    assert any(c.startswith("Source: USDA FoodData Central") for c in captions)


def test_the_food_lookup_works_without_a_profile():
    """The lookup needs no personal data."""
    at = _look_up(_start(profile=None), "chicken breast", 100.0)
    assert at.tabs[FOOD_TAB].metric[0].value == "120 kcal"


def test_missing_fibre_is_shown_as_not_reported():
    """A food without a USDA fibre value says so, rather than 0 g."""
    at = _look_up(_start(), "chicken breast", 100.0)
    assert "Fiber: not reported" in [c.value for c in at.tabs[FOOD_TAB].caption]


def test_a_food_not_found_shows_the_message_and_the_suggestions():
    """A misspelt food shows the fixed message and the close names as a table."""
    tab = _look_up(_start(), "chicken brest", 100.0).tabs[FOOD_TAB]
    [info] = tab.info
    assert info.value.startswith("No close match in the USDA Foundation Foods table.")
    [suggestions] = tab.dataframe
    assert list(suggestions.value["Did you mean"]) == ["Chicken, breast, boneless, skinless, raw"]
    assert not tab.metric


def test_an_invalid_lookup_shows_the_fixed_message():
    """A name with no real word gives the tool's fixed message, not an error page."""
    tab = _look_up(_start(), "a", 100.0).tabs[FOOD_TAB]
    [warning] = tab.warning
    assert warning.value.startswith("Invalid food lookup:")


def test_a_missing_foods_table_shows_the_fixed_error(monkeypatch, tmp_path):
    """Without the foods table the tab shows the fixed message, never a traceback."""
    at = _start()
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "missing.csv")
    at = _look_up(at, "rolled oats", 100.0)
    assert not at.exception
    assert [e.value for e in at.tabs[FOOD_TAB].error] == [config.TOOL_FAILED_MESSAGE]


def test_the_result_stays_after_another_rerun():
    """The last lookup stays on the page while other widgets rerun it."""
    at = _look_up(_start(), "rolled oats", 80.0)
    at.sidebar.segmented_control(key="sidebar_goal").set_value("maintain").run(timeout=30)
    assert [t.value for t in at.tabs[FOOD_TAB].text] == ["Oats, whole grain, rolled, old fashioned"]


@pytest.mark.parametrize("food", [HOSTILE_FOOD_NAME, "oats"])
def test_usda_names_in_the_food_tab_are_plain_text(food):
    """A USDA name with a link, an image and a delimiter is shown only as plain text."""
    # As the match, and as a close alternative of "oats".
    at = _look_up(_start(), food, 100.0)
    tab = at.tabs[FOOD_TAB]
    shown_plain = [t.value for t in tab.text] + [
        name for frame in tab.dataframe for column in frame.value for name in frame.value[column]
    ]
    assert HOSTILE_FOOD_NAME in shown_plain
    shown = [m.value for m in at.markdown] + [c.value for c in at.caption]
    shown += [i.value for i in at.info] + [w.value for w in at.warning]
    shown += [m.label for m in at.metric]
    assert not [text for text in shown if "example.com" in text]
