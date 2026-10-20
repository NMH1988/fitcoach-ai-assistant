"""The answer step's tools for LangChain, and the running of the model's tool calls (T4.4).

Each tool is a `StructuredTool` with an explicit `args_schema` that holds only what the model may
send: `lookup_food_nutrition` takes `food` and `grams` (`FoodLookupArgs`), the energy tools take
nothing (`NoArgs`): the app gives them the user's profile when the tools are built, so the model
can neither read nor change it. `run_tool_call()` checks the arguments against the schema itself
before a tool runs (LangChain skips the check for a schema without fields), and every refusal or
failure comes back as a fixed message the model reads as the tool result, never as an exception.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, ValidationError

from src import config
from src.profile import UserProfile
from src.tools.energy import (
    MacroTargetsResult,
    TdeeResult,
    calculate_macro_targets,
    calculate_tdee,
)
from src.tools.food import (
    Food,
    FoodLookupArgs,
    FoodLookupResult,
    invalid_lookup_message,
    lookup_food_nutrition,
)

TDEE_TOOL = "calculate_tdee"
MACRO_TOOL = "calculate_macro_targets"
FOOD_TOOL = "lookup_food_nutrition"

# What the model reads about each tool. The profile is never an argument.
TDEE_DESCRIPTION = (
    "Estimate the user's resting energy (BMR) and daily energy needs (TDEE) in kcal/day from the "
    "profile they entered in the app (Mifflin-St Jeor equation times an activity factor). Takes no "
    "arguments: the app supplies the profile. If the user has not added their details, the result "
    "says so."
)
MACRO_DESCRIPTION = (
    "Daily targets for the user's goal from the profile they entered in the app: kcal (never below "
    f"{config.CALORIE_FLOOR_KCAL} kcal/day), protein, carbohydrate and fat in g, % of kcal and "
    "g/kg, with the daily energy needs, the sources' ranges and notes. Takes no arguments: the app "
    "supplies the profile and the goal. If the user has not added their details, the result says "
    "so."
)
FOOD_DESCRIPTION = (
    "Nutrients (kcal, protein, carbohydrate, fat, fiber) in an amount of one food, from the USDA "
    "FoodData Central Foundation Foods table. Check matched_name before using the values: the "
    "closest USDA food may not be the one asked for (e.g. 'pasta' can match a pasta sauce); if it "
    "differs, say so or look up one of the alternatives by its exact name."
)

ToolStatus = Literal["ok", "found", "not_found", "invalid", "profile_needed", "error"]


class NoArgs(BaseModel):
    """The arguments of a tool that takes none: any field the model sends is refused."""

    model_config = ConfigDict(extra="forbid")


class ToolNotice(BaseModel):
    """A tool result without values: the profile is needed, the call was invalid or failed."""

    status: Literal["profile_needed", "invalid", "error"]
    message: str


class MacroToolResult(BaseModel):
    """calculate_macro_targets' result: the daily energy needs and the targets for the goal."""

    status: Literal["ok", "invalid"]
    message: str
    energy_needs: TdeeResult
    targets: MacroTargetsResult


ToolResult = TdeeResult | MacroToolResult | FoodLookupResult | ToolNotice


@dataclass(frozen=True)
class ToolRun:
    """One tool call of the model and its result, as the UI shows it."""

    # The tool's name, or None when the model named a tool that does not exist.
    name: str | None
    status: ToolStatus
    result: ToolResult


def _profile_needed() -> ToolNotice:
    """Return the result of an energy tool called before the user added their details."""
    return ToolNotice(status="profile_needed", message=config.PROFILE_NEEDED_MESSAGE)


def _energy_needs(profile: UserProfile) -> TdeeResult:
    """Return calculate_tdee's result for the profile."""
    return calculate_tdee(
        profile.weight_kg, profile.height_cm, profile.age, profile.sex, profile.activity
    )


def _no_arguments_message(_: ValidationError) -> str:
    """Return the fixed message for an energy tool called with any argument."""
    return config.NO_ARGUMENTS_MESSAGE


def build_tools(
    profile: UserProfile | None, table: Sequence[Food] | None = None
) -> dict[str, StructuredTool]:
    """Return the tools by name, with the energy tools bound to this profile (None: no profile)."""
    # `table` replaces the committed foods table (tests); the model can never set it. Run the
    # model's calls only through run_tool_call(): LangChain's own `tool.invoke()` skips the check
    # for the NoArgs tools and would run them with the model's extra fields dropped.

    def tdee() -> TdeeResult | ToolNotice:
        """Return the energy needs of the profile, or "profile needed"."""
        return _profile_needed() if profile is None else _energy_needs(profile)

    def macros() -> MacroToolResult | ToolNotice:
        """Return the daily targets for the profile's goal, or "profile needed"."""
        if profile is None:
            return _profile_needed()
        needs = _energy_needs(profile)
        if needs.tdee_kcal is None:
            # Not reached for a validated profile: its ranges are the tools' ranges.
            return ToolNotice(status="error", message=config.TOOL_FAILED_MESSAGE)
        targets = calculate_macro_targets(profile.weight_kg, profile.goal, needs.tdee_kcal)
        return MacroToolResult(
            status=targets.status, message=targets.message, energy_needs=needs, targets=targets
        )

    def food(food: str, grams: float) -> FoodLookupResult:
        """Return the nutrients of the food for the grams."""
        return lookup_food_nutrition(food, grams, table)

    return {
        TDEE_TOOL: StructuredTool.from_function(
            func=tdee,
            name=TDEE_TOOL,
            description=TDEE_DESCRIPTION,
            args_schema=NoArgs,
            handle_validation_error=_no_arguments_message,
        ),
        MACRO_TOOL: StructuredTool.from_function(
            func=macros,
            name=MACRO_TOOL,
            description=MACRO_DESCRIPTION,
            args_schema=NoArgs,
            handle_validation_error=_no_arguments_message,
        ),
        FOOD_TOOL: StructuredTool.from_function(
            func=food,
            name=FOOD_TOOL,
            description=FOOD_DESCRIPTION,
            args_schema=FoodLookupArgs,
            handle_validation_error=invalid_lookup_message,
        ),
    }


# The fixed message for arguments that fail a tool's schema; none repeats what was sent.
_INVALID_MESSAGES: dict[str, Callable[[ValidationError], str]] = {
    TDEE_TOOL: _no_arguments_message,
    MACRO_TOOL: _no_arguments_message,
    FOOD_TOOL: invalid_lookup_message,
}


def _run(tool: StructuredTool, args: object) -> ToolResult:
    """Check the arguments against the tool's schema, then run it; refuse or fail with a notice."""
    # Every tool from build_tools() has a Pydantic schema and a function.
    schema = cast(type[BaseModel], tool.args_schema)
    func = cast(Callable[..., ToolResult], tool.func)
    try:
        checked = schema.model_validate(args)
    except ValidationError as exc:
        return ToolNotice(status="invalid", message=_INVALID_MESSAGES[tool.name](exc))
    try:
        result = func(**checked.model_dump())
    except Exception:
        # A missing or broken foods table (FoodTableError) or a bug: the model and the user get
        # the fixed message, never the exception's text.
        return ToolNotice(status="error", message=config.TOOL_FAILED_MESSAGE)
    return result


def tool_message(call_id: str, result: ToolResult, name: str | None = None) -> ToolMessage:
    """Return the message that gives the model a tool result as JSON."""
    failed = result.status in ("invalid", "error")
    return ToolMessage(
        result.model_dump_json(),
        tool_call_id=call_id,
        name=name,
        status="error" if failed else "success",
    )


def run_tool_call(
    tools: Mapping[str, StructuredTool], call: ToolCall
) -> tuple[ToolMessage, ToolRun]:
    """Run one tool call of the model; return the message for the model and the run for the UI."""
    tool = tools.get(call["name"])
    if tool is None:
        result: ToolResult = ToolNotice(status="invalid", message=config.UNKNOWN_TOOL_MESSAGE)
    else:
        result = _run(tool, call["args"])
    name = tool.name if tool is not None else None
    return tool_message(call["id"] or "", result, name), ToolRun(name, result.status, result)


def refused_call(call_id: str, message: str) -> tuple[ToolMessage, ToolRun]:
    """Answer a tool call that is not run (bad JSON, too many calls) with a fixed message."""
    result = ToolNotice(status="invalid", message=message)
    return tool_message(call_id, result), ToolRun(None, "invalid", result)
