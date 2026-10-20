"""Tests for src/tools/registry.py: the tools' schemas, the profile and running calls (T4.4)."""

import html
import json

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from src import config
from src.tools import registry
from src.tools.energy import calculate_macro_targets, calculate_tdee
from src.tools.food import FoodLookupArgs
from src.tools.registry import FOOD_TOOL, MACRO_TOOL, TDEE_TOOL, NoArgs
from tests.fakes import FOODS, HOSTILE_FOOD_NAME, PROFILE

PROFILE_FIELDS = {"weight_kg", "height_cm", "age", "sex", "activity", "goal", "tdee_kcal"}


def _call(name: str, args: dict, call_id: str = "call-1") -> dict:
    """Return a tool call as the model sends it."""
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _run(name: str, args: dict, profile=PROFILE):
    """Run one tool call with tools built for the profile and the fixture foods."""
    return registry.run_tool_call(registry.build_tools(profile, FOODS), _call(name, args))


@pytest.fixture
def no_tool_runs(monkeypatch):
    """Make every tool function fail the test if it is reached."""

    def fail(*args, **kwargs):
        """Fail: a refused call must not reach the tool."""
        raise AssertionError("the tool ran")

    for name in ("lookup_food_nutrition", "calculate_tdee", "calculate_macro_targets"):
        monkeypatch.setattr(registry, name, fail)


# --- Schemas: only the model's fields (AC 4) ------------------------------------------------------


def test_each_tool_is_built_with_an_explicit_schema_of_the_models_fields():
    """The food tool takes food and grams only; the energy tools take nothing."""
    tools = registry.build_tools(PROFILE)
    assert set(tools) == {TDEE_TOOL, MACRO_TOOL, FOOD_TOOL}
    assert tools[FOOD_TOOL].args_schema is FoodLookupArgs
    assert set(tools[FOOD_TOOL].args) == {"food", "grams"}
    for name in (TDEE_TOOL, MACRO_TOOL):
        assert tools[name].args_schema is NoArgs
        assert tools[name].args == {}


def test_the_schemas_refuse_any_extra_field():
    """FoodLookupArgs and NoArgs forbid fields they do not declare."""
    assert FoodLookupArgs.model_config["extra"] == "forbid"
    assert NoArgs.model_config["extra"] == "forbid"


@pytest.mark.parametrize("profile", [PROFILE, None])
def test_what_the_model_sees_has_no_table_and_no_profile_field(profile):
    """The schemas sent to the model hold no `table` and no profile field."""
    for tool in registry.build_tools(profile).values():
        properties = set(convert_to_openai_tool(tool)["function"]["parameters"]["properties"])
        assert "table" not in properties
        assert not properties & PROFILE_FIELDS


@pytest.mark.parametrize(
    ("name", "args", "message"),
    [
        (FOOD_TOOL, {"food": "rolled oats", "grams": 100, "table": []}, "food and grams"),
        (FOOD_TOOL, {"food": "rolled oats", "grams": 100, "weight_kg": 80}, "food and grams"),
        (FOOD_TOOL, {"food": "rolled oats", "grams": 100, "note": "x"}, "food and grams"),
        (TDEE_TOOL, {"weight_kg": 80}, config.NO_ARGUMENTS_MESSAGE),
        (TDEE_TOOL, {"age": 12, "sex": "female"}, config.NO_ARGUMENTS_MESSAGE),
        (MACRO_TOOL, {"goal": "lose_fat"}, config.NO_ARGUMENTS_MESSAGE),
        (MACRO_TOOL, {"tdee_kcal": 400}, config.NO_ARGUMENTS_MESSAGE),
        (MACRO_TOOL, {"anything": None}, config.NO_ARGUMENTS_MESSAGE),
    ],
)
def test_a_call_with_an_extra_field_is_refused_and_runs_nothing(no_tool_runs, name, args, message):
    """`table`, a profile field or any extra field gives the fixed message; no tool runs."""
    tool_message, run = _run(name, args)
    result = json.loads(tool_message.content)
    assert result["status"] == "invalid" == run.status
    assert message in result["message"]
    assert tool_message.status == "error"


def test_the_extra_field_message_is_fixed():
    """The food refusal names the allowed arguments and nothing the model sent."""
    tool_message, _ = _run(FOOD_TOOL, {"food": "rolled oats", "grams": 100, "SECRET_KEY": "SECRET"})
    assert json.loads(tool_message.content)["message"] == (
        "Invalid food lookup: only the arguments food and grams are accepted."
    )
    assert "SECRET" not in tool_message.content


def test_a_call_through_langchain_is_refused_too(no_tool_runs):
    """Invoked directly, the food tool still refuses `table` with the fixed message."""
    tool = registry.build_tools(PROFILE)[FOOD_TOOL]
    reply = tool.invoke({"food": "rolled oats", "grams": 100, "table": []})
    assert reply == "Invalid food lookup: only the arguments food and grams are accepted."


@pytest.mark.parametrize(
    "args",
    [{"food": "rolled oats", "grams": "100"}, {"food": "a", "grams": 100}, {"grams": 100}, {}],
)
def test_invalid_food_arguments_give_the_lookup_message(no_tool_runs, args):
    """Wrong types, a name without a real word or missing fields are refused before a lookup."""
    tool_message, run = _run(FOOD_TOOL, args)
    assert run.status == "invalid"
    assert json.loads(tool_message.content)["message"].startswith("Invalid food lookup: ")


# --- The profile comes from the app (AC 2) --------------------------------------------------------


@pytest.mark.parametrize("name", [TDEE_TOOL, MACRO_TOOL])
def test_without_a_profile_the_energy_tools_say_profile_needed(no_tool_runs, name):
    """With no profile the tool returns "profile needed" and calculates nothing."""
    tool_message, run = _run(name, {}, profile=None)
    assert run.status == "profile_needed"
    assert json.loads(tool_message.content) == {
        "status": "profile_needed",
        "message": config.PROFILE_NEEDED_MESSAGE,
    }
    assert tool_message.status == "success"


def test_the_energy_needs_come_from_the_profile():
    """calculate_tdee gives the profile's resting energy and daily needs."""
    tool_message, run = _run(TDEE_TOOL, {})
    assert run.status == "ok"
    assert run.result == calculate_tdee(80.0, 180.0, 30, "male", "moderate")
    assert (run.result.bmr_kcal, run.result.tdee_kcal) == (1780, 2759)
    assert json.loads(tool_message.content)["tdee_kcal"] == 2759


@pytest.mark.parametrize("goal", ["build_muscle", "lose_fat", "maintain"])
def test_the_macro_targets_use_the_profiles_goal_and_energy_needs(goal):
    """calculate_macro_targets chains the profile's TDEE into the targets for its goal."""
    profile = PROFILE.model_copy(update={"goal": goal})
    _, run = _run(MACRO_TOOL, {}, profile=profile)
    assert run.status == "ok"
    assert run.result.energy_needs.tdee_kcal == 2759
    assert run.result.targets == calculate_macro_targets(80.0, goal, 2759)
    assert run.result.message == run.result.targets.message


# --- Food lookup, failures and USDA names (AC 1 and 5) --------------------------------------------


def test_a_food_lookup_returns_the_scaled_values():
    """The food tool looks up the fixture table and scales to the grams."""
    tool_message, run = _run(FOOD_TOOL, {"food": "rolled oats", "grams": 50})
    assert run.status == "found"
    assert run.result.matched_name == "Oats, whole grain, rolled, old fashioned"
    assert run.result.nutrients.kcal == 190
    assert tool_message.name == FOOD_TOOL
    assert tool_message.tool_call_id == "call-1"


def test_a_missing_foods_table_gives_the_fixed_tool_error(monkeypatch, tmp_path):
    """FoodTableError becomes the fixed failure message, without the file's name."""
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "secret_name.csv")
    tools = registry.build_tools(PROFILE)
    tool_message, run = registry.run_tool_call(
        tools, _call(FOOD_TOOL, {"food": "oats", "grams": 1})
    )
    assert run.status == "error"
    assert json.loads(tool_message.content)["message"] == config.TOOL_FAILED_MESSAGE
    assert "secret_name" not in tool_message.content


def test_an_unexpected_error_gives_the_fixed_tool_error(monkeypatch):
    """A bug in a tool becomes the fixed failure message; its text never reaches the model."""

    def broken(*args, **kwargs):
        """Raise an error whose text must not leak."""
        raise RuntimeError("internal detail 80 kg")

    monkeypatch.setattr(registry, "calculate_tdee", broken)
    tool_message, run = _run(TDEE_TOOL, {})
    assert run.status == "error"
    assert "internal detail" not in tool_message.content
    assert tool_message.status == "error"


def test_an_unknown_tool_is_refused():
    """A name that is not one of the tools gets a fixed message and no name in the run."""
    tool_message, run = _run("delete_all_files", {"path": "/"})
    assert (run.name, run.status) == (None, "invalid")
    assert json.loads(tool_message.content)["message"] == config.UNKNOWN_TOOL_MESSAGE
    assert "delete_all_files" not in tool_message.content


def test_a_refused_call_gets_its_message():
    """refused_call answers a call that is not run with the given fixed message."""
    tool_message, run = registry.refused_call("call-9", config.TOO_MANY_TOOL_CALLS_MESSAGE)
    assert tool_message.tool_call_id == "call-9"
    assert json.loads(tool_message.content)["message"] == config.TOO_MANY_TOOL_CALLS_MESSAGE
    assert run.status == "invalid"


def test_usda_names_are_returned_inside_the_tool_message_as_data():
    """A USDA name with Markdown and a delimiter comes back unchanged inside the JSON result."""
    tool_message, run = _run(FOOD_TOOL, {"food": HOSTILE_FOOD_NAME, "grams": 100})
    assert run.result.matched_name == HOSTILE_FOOD_NAME
    content = json.loads(tool_message.content)["matched_name"]
    # Escaped like the prompt blocks (T3.4): the name comes back exact once unescaped.
    assert html.unescape(content) == HOSTILE_FOOD_NAME
    assert "<" not in tool_message.content and ">" not in tool_message.content
