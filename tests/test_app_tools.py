"""UI tests for tool results in the Ask tab: tables, the macro chart, the profile (T4.4, AC-6)."""

import json
from pathlib import Path

import pytest
import streamlit as st
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from src import chat, config, llm
from src.rag import store
from src.tools.registry import FOOD_TOOL, MACRO_TOOL, MEAL_PLAN_TOOL, TDEE_TOOL
from tests.fakes import (
    HOSTILE_FOOD_NAME,
    PROFILE,
    ScriptedChatModel,
    ScriptedTranslator,
    build_fixture_index,
    open_fixture_index,
    tool_reply,
    write_food_table,
)

APP = Path(__file__).resolve().parent.parent / "app.py"
QUESTION = "How much protein per meal?"
ANSWER = "Spread it over four meals [S1]."
OATS = {"food": "rolled oats", "grams": 80}

pytestmark = pytest.mark.usefixtures("no_env_key")


@pytest.fixture(scope="module")
def index_path(tmp_path_factory):
    """Build the fixture index once for the module and return its directory."""
    return build_fixture_index(tmp_path_factory.mktemp("index") / "chroma")


@pytest.fixture(autouse=True)
def fakes(tmp_path, monkeypatch, index_path):
    """Give the app the fixture index, a test prompt, the fixture foods and fresh caches."""
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Test system prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_PROMPT_PATH", prompt)
    translation = tmp_path / "translation_prompt.md"
    translation.write_text("Test query translation prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "QUERY_TRANSLATION_PROMPT_PATH", translation)
    monkeypatch.setattr(config, "ANSWER_WORDS_PER_SECOND", 0)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", write_food_table(tmp_path / "foods.csv"))
    monkeypatch.setattr(store, "open_index", lambda: open_fixture_index(index_path))
    monkeypatch.setattr(chat, "manifest_by_id", lambda: {})
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _use_model(monkeypatch, *replies: AIMessage) -> ScriptedChatModel:
    """Make the app build a model scripted with these replies (rewrites repeat the question)."""
    model = ScriptedChatModel(replies=list(replies))
    translator = ScriptedTranslator()

    def build(name: str = config.DEFAULT_ANSWER_MODEL, *args, **kwargs):
        """Return the fake translator for the query translation model, else the answer fake."""
        return translator if name == config.QUERY_TRANSLATION_MODEL else model

    monkeypatch.setattr(llm, "build_chat_model", build)
    return model


def _ask(question: str = QUESTION, profile=PROFILE) -> AppTest:
    """Run the app with the profile in the session (None: no profile), then ask a question."""
    at = AppTest.from_file(str(APP))
    at.secrets["UNRELATED"] = "x"
    if profile is not None:
        at.session_state["profile"] = profile
    at.run(timeout=30)
    return at.chat_input(key="chat_input").set_value(question).run(timeout=30)


def _assistant(at: AppTest, turn: int = -1):
    """Return the assistant message of a turn (the last by default)."""
    return [m for m in at.chat_message if m.name == "assistant"][turn]


def _tool_results(at: AppTest, turn: int = -1):
    """Return the "Tool results" expander of a turn."""
    [expander] = [e for e in _assistant(at, turn).expander if e.label.startswith("Tool results")]
    return expander


def _rows(table) -> dict[str, str]:
    """Return a two-column table's items and values."""
    frame = table.value
    return dict(zip(frame["Item"], frame["Value"], strict=True))


# --- Each tool result as a table; macro targets also as a chart (AC 3) ----------------------------


def test_each_tool_result_appears_in_the_tool_results_expander_as_a_table(monkeypatch):
    """Three calls give one "Tool results (3)" expander with a heading and a table for each."""
    _use_model(
        monkeypatch,
        tool_reply((TDEE_TOOL, {}), (MACRO_TOOL, {}), (FOOD_TOOL, OATS)),
        AIMessage(ANSWER),
    )
    at = _ask()
    assert not at.exception
    expander = _tool_results(at)
    assert expander.label == "Tool results (3)"
    # Closed like "Sources" when no result needs the profile.
    assert expander.proto.expanded is False
    headings = [m.value for m in expander.markdown if m.value.startswith("**")]
    assert headings == [
        "**:material/local_fire_department: Daily energy needs**",
        "**:material/target: Daily targets**",
        "**:material/restaurant: Food lookup**",
    ]
    tdee, summary, macros, food = expander.dataframe
    assert _rows(tdee) == {
        "Resting energy (BMR)": "1,780 kcal/day",
        "Activity factor": "1.55",
        "Daily energy needs (TDEE)": "2,759 kcal/day",
    }
    assert _rows(summary)["Daily target"] == "3,035 kcal"
    assert list(macros.value["Macro"]) == ["Protein", "Carbohydrate", "Fat"]
    assert list(macros.value["Per day"]) == ["152 g", "418 g", "84 g"]
    assert _rows(food)["USDA food"] == "Oats, whole grain, rolled, old fashioned"
    assert _rows(food)["Energy"] == "304 kcal"


def test_macro_targets_also_appear_as_a_chart_in_the_macro_colours(monkeypatch):
    """The macro result has a stacked bar of the energy split, in the design's colours, from 0."""
    _use_model(monkeypatch, tool_reply((MACRO_TOOL, {})), AIMessage(ANSWER))
    [chart] = _tool_results(_ask()).get("vega_lite_chart")
    spec = json.loads(chart.proto.spec)
    color = spec["encoding"]["color"]["scale"]
    assert color == {
        "domain": list(config.MACRO_COLORS),
        "range": list(config.MACRO_COLORS.values()),
    }
    # The tooltip shows kcal as a formatted number ("1,672"), which needs the quantitative type.
    assert {"field": "kcal", "type": "quantitative", "format": ","} in spec["encoding"]["tooltip"]
    # The value axis starts at 0 (st.bar_chart's started at -500 in a narrow window).
    assert spec["encoding"]["x"]["scale"] == {"domainMin": 0, "nice": True}
    # The text alternative names every value, so the colours are never the only signal.
    assert chart.proto.alt == (
        "Energy split per day: Protein 608 kcal, Carbohydrate 1,672 kcal, Fat 756 kcal"
    )


def test_a_food_lookup_alone_draws_no_chart(monkeypatch):
    """Only macro targets get a chart; a food lookup is a table."""
    _use_model(monkeypatch, tool_reply((FOOD_TOOL, OATS)), AIMessage(ANSWER))
    expander = _tool_results(_ask())
    assert not expander.get("vega_lite_chart")
    assert len(expander.dataframe) == 1


def test_a_food_not_found_shows_the_message_and_suggestions(monkeypatch):
    """A food not in the table shows the fixed message, and suggestions as a table."""
    _use_model(
        monkeypatch, tool_reply((FOOD_TOOL, {"food": "pizza", "grams": 100})), AIMessage(ANSWER)
    )
    expander = _tool_results(_ask())
    assert expander.caption[0].value.startswith(
        "No close match in the USDA Foundation Foods table."
    )


def test_a_refused_call_shows_its_fixed_message(monkeypatch):
    """A call to a tool that does not exist shows the fixed message under "not run"."""
    _use_model(monkeypatch, tool_reply(("delete_files", {})), AIMessage(ANSWER))
    expander = _tool_results(_ask())
    assert "**:material/block: Tool call not run**" in [m.value for m in expander.markdown]
    assert [c.value for c in expander.caption] == [config.UNKNOWN_TOOL_MESSAGE]


def test_the_tool_step_shows_in_the_status(monkeypatch):
    """A tool round adds "Using the tools", with its caption, between the answer steps."""
    _use_model(monkeypatch, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER))
    message = _assistant(_ask())
    assert [s.label for s in message.status][1:] == [
        chat.Step.CHECK.value,
        chat.Step.REWRITE.value,
        chat.Step.SEARCH.value,
        chat.Step.ANSWER.value,
        chat.Step.TOOLS.value,
        chat.Step.ANSWER.value,
    ]
    for step in message.status[1:]:
        assert len(step.caption) == 1


def test_tool_results_stay_with_their_answer_in_the_history(monkeypatch):
    """A later turn keeps the earlier turn's tool results; a turn without tools has none."""
    _use_model(monkeypatch, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER), AIMessage(ANSWER))
    at = _ask()
    at = at.chat_input(key="chat_input").set_value("And per day?").run(timeout=30)
    assert _tool_results(at, 0).label == "Tool results (1)"
    assert not [e for e in _assistant(at, 1).expander if e.label.startswith("Tool results")]


# --- The profile comes from the session (AC 2) ----------------------------------------------------


def test_the_energy_tools_read_the_profile_from_the_session(monkeypatch):
    """The numbers follow the profile saved in the session."""
    _use_model(monkeypatch, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER))
    at = _ask(profile=PROFILE.model_copy(update={"weight_kg": 60.0}))
    [tdee] = _tool_results(at).dataframe
    assert _rows(tdee)["Resting energy (BMR)"] == "1,580 kcal/day"


def test_the_model_gets_the_session_profile(monkeypatch):
    """The session's profile reaches the model in the <profile> block."""
    model = _use_model(monkeypatch, AIMessage(ANSWER))
    _ask()
    [[_, user]] = model.calls
    assert "Weight: 80 kg" in user.content and "Goal: Build muscle" in user.content


def test_without_a_profile_the_result_points_to_the_form(monkeypatch):
    """With no profile the result says the details are needed; its button opens the dialog."""
    _use_model(monkeypatch, tool_reply((MACRO_TOOL, {})), AIMessage(ANSWER))
    at = _ask(profile=None)
    expander = _tool_results(at)
    # Open, so the button is in view without a click.
    assert expander.proto.expanded is True
    assert [i.value for i in expander.info] == [config.PROFILE_NEEDED_HINT]
    [button] = expander.button
    assert button.label == "Add your details"
    at = button.click().run(timeout=30)
    assert at.session_state["profile_form_open"] is True
    assert at.get("dialog")
    assert not at.exception


# --- USDA names as plain text (AC 5) --------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        # The hostile name is the match.
        {"food": HOSTILE_FOOD_NAME, "grams": 100},
        # The hostile name is one of the close alternatives.
        {"food": "oats", "grams": 100},
    ],
)
def test_usda_names_appear_only_as_plain_text(monkeypatch, args):
    """A USDA name with a link, an image and a delimiter is only ever a table cell."""
    _use_model(monkeypatch, tool_reply((FOOD_TOOL, args)), AIMessage(ANSWER))
    at = _ask()
    expander = _tool_results(at)
    [food] = expander.dataframe
    assert HOSTILE_FOOD_NAME in " ".join(_rows(food).values())
    # Nowhere read as Markdown: not in the Markdown, captions, labels or alerts of the page.
    shown = [m.value for m in at.markdown] + [c.value for c in at.caption]
    shown += [e.label for e in at.expander] + [i.value for i in at.info]
    assert not [text for text in shown if "example.com" in text]


# --- The meal plan check (T4.5) -------------------------------------------------------------------

PLAN = {
    "items": [OATS, {"food": "chicken breast", "grams": 200}, {"food": "zzzz qqqq", "grams": 50}]
}


def _column(table, name: str) -> list[str]:
    """Return one column of a table as a list."""
    return list(table.value[name])


def test_a_meal_plan_shows_its_foods_and_the_totals_against_the_targets(monkeypatch):
    """The meal plan check shows a table of the foods and one of the totals, targets and gaps."""
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, PLAN)), AIMessage(ANSWER))
    at = _ask()
    assert not at.exception
    expander = _tool_results(at)
    headings = [m.value for m in expander.markdown if m.value.startswith("**")]
    assert headings == ["**:material/fact_check: Meal plan check**"]
    foods, totals = expander.dataframe
    assert _column(foods, "Food asked") == ["rolled oats", "chicken breast", "zzzz qqqq"]
    assert _column(foods, "USDA food") == [
        "Oats, whole grain, rolled, old fashioned",
        "Chicken, breast, boneless, skinless, raw",
        "Not found",
    ]
    assert _column(foods, "Energy") == ["304 kcal", "240 kcal", "-"]
    assert _column(foods, "Fiber") == ["8 g", "not reported", "-"]
    assert _column(totals, "Nutrient") == ["Energy", "Protein", "Carbohydrate", "Fat", "Fiber"]
    assert _column(totals, "Plan total") == ["544 kcal", "55.6 g", "54.4 g", "10.3 g", "8 g"]
    assert _column(totals, "Daily target") == [
        "3,035 kcal",
        "152 g",
        "418 g",
        "84 g",
        "No target",
    ]
    assert _column(totals, "Difference")[:2] == [
        "2,491 kcal below the target",
        "96.4 g below the target",
    ]
    assert _column(totals, "Range from the sources") == [
        "Below 3,035-3,311 kcal",
        "Below 128-176 g",
        "-",
        "-",
        "-",
    ]
    captions = [c.value for c in expander.caption]
    assert captions[0].startswith("2 of 3 foods found;")
    assert any("1 of 3 foods were not found" in caption for caption in captions)
    assert any("below the calorie floor" in caption for caption in captions)
    assert captions[-1].startswith("Source: USDA FoodData Central")
    # Tables only, no chart (owner's choice, T4.5).
    assert not expander.get("vega_lite_chart")


def test_a_meal_plan_above_the_target_says_so(monkeypatch):
    """A total over the target reads "above the target"."""
    plan = {"items": [{"food": "rolled oats", "grams": 900}]}
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, plan)), AIMessage(ANSWER))
    _, totals = _tool_results(_ask()).dataframe
    assert _column(totals, "Difference")[0] == "385 kcal above the target"
    assert _column(totals, "Range from the sources")[0] == "Above 3,035-3,311 kcal"


def test_a_meal_plan_with_no_food_found_shows_only_the_foods(monkeypatch):
    """With no food found there is no totals table, only the foods and the message."""
    plan = {"items": [{"food": "zzzz qqqq", "grams": 50}]}
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, plan)), AIMessage(ANSWER))
    expander = _tool_results(_ask())
    [foods] = expander.dataframe
    assert _column(foods, "USDA food") == ["Not found"]
    assert expander.caption[0].value.startswith("None of the foods was found")


def test_a_meal_plan_without_a_profile_points_to_the_form(monkeypatch):
    """Without a profile the meal plan check asks for the details, with the button."""
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, PLAN)), AIMessage(ANSWER))
    expander = _tool_results(_ask(profile=None))
    assert [i.value for i in expander.info] == [config.PROFILE_NEEDED_HINT]
    assert [b.label for b in expander.button] == ["Add your details"]
    assert not expander.dataframe


def test_an_invalid_meal_plan_shows_its_fixed_message(monkeypatch):
    """An invalid plan shows the fixed message and no table."""
    plan = {"items": [{"food": "rolled oats", "grams": "SECRET"}]}
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, plan)), AIMessage(ANSWER))
    expander = _tool_results(_ask())
    assert [c.value for c in expander.caption] == [
        "Invalid meal plan: item 1: the amount must be a number of grams from 0.1 to 2000."
    ]
    assert not expander.dataframe


@pytest.mark.parametrize(
    "food",
    [
        # The hostile name is the match, and the name asked for.
        HOSTILE_FOOD_NAME,
        # The hostile name is one of the close alternatives.
        "oats",
    ],
)
def test_meal_plan_names_appear_only_as_plain_text(monkeypatch, food):
    """USDA names and the names asked for are only ever table cells in the meal plan check."""
    plan = {"items": [{"food": food, "grams": 100}]}
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, plan)), AIMessage(ANSWER))
    at = _ask()
    foods, _ = _tool_results(at).dataframe
    cells = " ".join(" ".join(map(str, foods.value[column])) for column in foods.value.columns)
    assert HOSTILE_FOOD_NAME in cells
    shown = [m.value for m in at.markdown] + [c.value for c in at.caption]
    shown += [e.label for e in at.expander] + [i.value for i in at.info]
    assert not [text for text in shown if "example.com" in text]


def test_a_one_value_range_shows_one_value(monkeypatch):
    """For "maintain" the kcal range is one value, shown once (code review, T4.5)."""
    _use_model(monkeypatch, tool_reply((MEAL_PLAN_TOOL, PLAN)), AIMessage(ANSWER))
    _, totals = _tool_results(
        _ask(profile=PROFILE.model_copy(update={"goal": "maintain"}))
    ).dataframe
    assert _column(totals, "Range from the sources")[0] == "Below 2,759 kcal"
