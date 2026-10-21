"""evaluate_meal_plan: one day's foods and amounts, totalled and compared with the daily targets.

Each food is looked up like lookup_food_nutrition (USDA Foundation Foods, CC0; docs/SOURCES.md
#21). The targets are calculate_macro_targets' result for the user's profile, which the app
supplies: the model sends only the foods (T4.5). Each gap is the daily target minus the plan's
total; kcal and protein are also placed against the ranges from the sources that the targets come
with. No other threshold is set: carbohydrate and fat have no range from the sources, and fiber
has no target. Invalid arguments give a result with status "invalid" and a fixed message, never an
exception and never an echo of what was sent.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src import config, i18n
from src.i18n import Language
from src.profile import GOAL_LABELS
from src.tools.energy import MacroTargetsResult
from src.tools.food import (
    SOURCE,
    Food,
    FoodLookupArgs,
    Nutrients,
    lookup_food_nutrition,
    lookup_problems,
)

RangePosition = Literal["below", "within", "above"]


class MealItemArgs(FoodLookupArgs):
    """One food of the plan and its amount in grams, with the food lookup's rules."""

    # A subclass only for this docstring, which the model reads as the item's description.


class MealPlanArgs(BaseModel):
    """The tool's arguments, as the model sends them; checked before any lookup."""

    model_config = ConfigDict(extra="forbid")

    items: list[MealItemArgs] = Field(
        min_length=1,
        max_length=config.MEAL_PLAN_MAX_ITEMS,
        description=(
            "The day's foods, each with its amount in grams: one entry per food, named as for "
            "the food lookup (e.g. 'rolled oats', 'chicken breast skinless raw')."
        ),
    )


class MealItem(BaseModel):
    """One food of the plan: the name asked for, and its USDA match and nutrients when found."""

    requested: str
    grams: float
    status: Literal["found", "not_found"]
    matched_name: str | None = None
    nutrients: Nutrients | None = None
    # Other close USDA names when found; "did you mean" suggestions when not found.
    alternatives: list[str] = Field(default_factory=list)


class NutrientCheck(BaseModel):
    """One nutrient of the plan against its daily target."""

    nutrient: Literal["kcal", "protein", "carbohydrate", "fat"]
    unit: Literal["kcal", "g"]
    plan_total: int | float
    target: int
    # The daily target minus the plan's total: positive is below the target, negative above it.
    gap: int | float
    # The range from the sources for kcal and protein (lowest, highest); None for the others.
    target_range: tuple[int, int] | None = None
    range_position: RangePosition | None = None


class MealPlanResult(BaseModel):
    """What evaluate_meal_plan returns: the foods, totals and gaps, or why there are none."""

    status: Literal["ok", "not_found", "invalid"]
    message: str
    items: list[MealItem] = Field(default_factory=list)
    totals: Nutrients | None = None
    comparison: list[NutrientCheck] = Field(default_factory=list)
    # True when some foods were not found, so the totals leave them out.
    partial: bool = False
    notes: list[str] = Field(default_factory=list)
    source: str = SOURCE


def invalid_meal_plan_message(error: ValidationError) -> str:
    """State which arguments or foods are wrong, by item number, without repeating what was sent."""
    list_problem, extra = False, False
    items: dict[int, set[str]] = {}
    for detail in error.errors():
        loc = detail["loc"]
        if not loc:
            continue
        if loc[0] != "items":
            extra = True
        elif len(loc) >= 2 and isinstance(loc[1], int):
            # ("items", 2, "grams"); ("items", 2) alone when the item is not an object.
            items.setdefault(loc[1], set()).add(str(loc[2]) if len(loc) > 2 else "")
        else:
            list_problem = True
    parts = []
    if extra:
        # Never names the extra field: it is the model's text.
        parts.append("only the argument items is accepted")
    if list_problem:
        parts.append(
            f"items must be a list of 1 to {config.MEAL_PLAN_MAX_ITEMS} foods, each with food "
            "and grams"
        )
    for index in sorted(items):
        problems = lookup_problems(items[index] - {""})
        what = "; ".join(problems) or "each item must be an object with food and grams"
        parts.append(f"item {index + 1}: {what}")
    return "Invalid meal plan: " + ("; ".join(parts) or "the arguments do not fit the schema") + "."


def _item(args: FoodLookupArgs, table: Sequence[Food] | None) -> MealItem:
    """Look up one food of the plan and return it with its match and nutrients."""
    found = lookup_food_nutrition(args.food, args.grams, table)
    return MealItem(
        requested=args.food,
        grams=args.grams,
        status="found" if found.status == "found" else "not_found",
        matched_name=found.matched_name,
        nutrients=found.nutrients,
        alternatives=found.alternatives,
    )


def _totals(nutrients: list[Nutrients]) -> Nutrients:
    """Add up the foods' nutrients; fiber only over the foods with a reported value."""
    digits = config.FOOD_DECIMALS
    fibers = [n.fiber_g for n in nutrients if n.fiber_g is not None]
    return Nutrients(
        kcal=sum(n.kcal for n in nutrients),
        protein_g=round(sum(n.protein_g for n in nutrients), digits),
        carbohydrate_g=round(sum(n.carbohydrate_g for n in nutrients), digits),
        fat_g=round(sum(n.fat_g for n in nutrients), digits),
        fiber_g=round(sum(fibers), digits) if fibers else None,
    )


def _position(total: float, low: int, high: int) -> RangePosition:
    """Return where the total lies against the range."""
    if total < low:
        return "below"
    return "above" if total > high else "within"


def _check(
    nutrient: Literal["kcal", "protein", "carbohydrate", "fat"],
    total: int | float,
    target: int,
    target_range: tuple[int, int] | None = None,
) -> NutrientCheck:
    """Return one nutrient's total against its target, with the gap and the range position."""
    gap = target - total if nutrient == "kcal" else round(target - total, config.FOOD_DECIMALS)
    return NutrientCheck(
        nutrient=nutrient,
        unit="kcal" if nutrient == "kcal" else "g",
        plan_total=total,
        target=target,
        gap=gap,
        target_range=target_range,
        range_position=None if target_range is None else _position(total, *target_range),
    )


def evaluate_meal_plan(
    items: object, targets: MacroTargetsResult, table: Sequence[Food] | None = None
) -> MealPlanResult:
    """Return the plan's foods, totals and gaps to the daily targets, or a clear message why not."""
    # `targets` must be an "ok" result of calculate_macro_targets (the tool wrapper in
    # src/tools/registry.py makes it from the profile); `table` replaces the committed foods table
    # (tests). Neither is ever a model argument (the tool's args_schema is MealPlanArgs).
    try:
        args = MealPlanArgs.model_validate({"items": items})
    except ValidationError as exc:
        return MealPlanResult(status="invalid", message=invalid_meal_plan_message(exc))
    goal, kcal_target = targets.goal, targets.kcal_target
    protein, carbohydrate, fat = targets.protein, targets.carbohydrate, targets.fat
    if (
        targets.status != "ok"
        or goal is None
        or kcal_target is None
        or protein is None
        or carbohydrate is None
        or fat is None
    ):
        raise ValueError("evaluate_meal_plan needs the daily targets of a valid profile")

    meal = [_item(item, table) for item in args.items]
    found = [item.nutrients for item in meal if item.nutrients is not None]
    missing = len(meal) - len(found)
    if not found:
        message = "None of the foods was found in the USDA Foundation Foods table, so no totals."
        if any(item.alternatives for item in meal):
            message += " The alternatives of a food are the closest names in it."
        else:
            message += (
                " No similar name: the table holds single, unprocessed foods under plainer names "
                "(e.g. 'rolled oats')."
            )
        return MealPlanResult(
            status="not_found",
            message=message,
            items=meal,
            partial=True,
        )

    totals = _totals(found)
    comparison = [
        _check("kcal", totals.kcal, kcal_target, targets.kcal_range),
        _check("protein", totals.protein_g, protein.grams, targets.protein_g_range),
        _check("carbohydrate", totals.carbohydrate_g, carbohydrate.grams),
        _check("fat", totals.fat_g, fat.grams),
    ]
    notes = []
    if missing:
        notes.append(
            f"{missing} of {len(meal)} foods were not found in the USDA table, so the totals "
            "leave them out."
        )
    no_fiber = sum(1 for n in found if n.fiber_g is None)
    if no_fiber:
        notes.append(
            f"USDA reports no fiber value for {no_fiber} of the foods found, so the fiber total "
            "leaves them out."
        )
    if totals.kcal < config.CALORIE_FLOOR_KCAL:
        # The same pointer as the targets' floor notes (owner's choice after PR #56's review): the
        # tool cannot tell a low day from a partial list, so it notes and points, not refuses.
        notes.append(
            f"The plan's total of {totals.kcal} kcal is below the calorie floor of "
            f"{config.CALORIE_FLOOR_KCAL} kcal/day. The app does not suggest eating below the "
            "floor; ask a registered dietitian for personal advice."
        )
    # The targets' own notes (the floor applied, protein lowered) hold for this comparison too.
    notes += targets.notes
    return MealPlanResult(
        status="ok",
        message=(
            f"{len(found)} of {len(meal)} foods found; totals from per-100 g USDA values, "
            f"compared with the daily targets for the goal '{GOAL_LABELS[goal]}'. "
            "The gap is the daily target minus the plan's total: positive is below the target, "
            "negative above it."
        ),
        items=meal,
        totals=totals,
        comparison=comparison,
        partial=bool(missing),
        notes=notes,
    )


# --- Text for the tables in the app and the summary PDF ------------------------------------------

# The texts come from src/i18n.py; the summary PDF uses the English ones (the defaults), the app
# the language chosen (T7.1).
_FOOD_COLUMN_KEYS = (
    "meal.food_asked",
    "food.usda_food",
    "food.amount",
    "nutrient.energy",
    "nutrient.protein",
    "nutrient.carbohydrate",
    "nutrient.fat",
    "nutrient.fiber",
)
_COMPARISON_COLUMN_KEYS = (
    "meal.nutrient",
    "meal.plan_total",
    "meal.daily_target",
    "meal.difference",
    "meal.range",
)


def food_columns(lang: Language = "en") -> tuple[str, ...]:
    """Return the headers of the foods table in a language."""
    return tuple(i18n.t(key, lang) for key in _FOOD_COLUMN_KEYS)


def comparison_columns(lang: Language = "en") -> tuple[str, ...]:
    """Return the headers of the plan-against-targets table in a language."""
    return tuple(i18n.t(key, lang) for key in _COMPARISON_COLUMN_KEYS)


FOOD_COLUMNS = food_columns()
COMPARISON_COLUMNS = comparison_columns()


def nutrient_name(nutrient: str, lang: Language = "en") -> str:
    """Return a nutrient's name ("kcal" is "Energy") in a language."""
    return i18n.t("nutrient.energy" if nutrient == "kcal" else f"nutrient.{nutrient}", lang)


def amount(value: float, unit: str, lang: Language = "en") -> str:
    """Return an amount with its unit, e.g. "3,035 kcal" or "55.6 g" (German "3.035 kcal")."""
    return f"{i18n.number(value, lang)} {unit}"


def food_row(item: MealItem, lang: Language = "en") -> list[str]:
    """Return one food of the plan as cells under FOOD_COLUMNS; a food not found has no values."""
    nutrients = item.nutrients
    grams = amount(item.grams, "g", lang)
    if nutrients is None:
        return [item.requested, i18n.t("meal.not_found", lang), grams, "-", "-", "-", "-", "-"]
    fiber = (
        i18n.t("food.not_reported", lang)
        if nutrients.fiber_g is None
        else amount(nutrients.fiber_g, "g", lang)
    )
    return [
        item.requested,
        item.matched_name or "",
        grams,
        amount(nutrients.kcal, "kcal", lang),
        amount(nutrients.protein_g, "g", lang),
        amount(nutrients.carbohydrate_g, "g", lang),
        amount(nutrients.fat_g, "g", lang),
        fiber,
    ]


def difference_text(check: NutrientCheck, lang: Language = "en") -> str:
    """Return the gap in words: how far the plan's total is below or above the target."""
    if check.gap > 0:
        return i18n.t("meal.below_target", lang, amount=amount(check.gap, check.unit, lang))
    if check.gap < 0:
        return i18n.t("meal.above_target", lang, amount=amount(-check.gap, check.unit, lang))
    return i18n.t("meal.on_target", lang)


def range_text(check: NutrientCheck, lang: Language = "en") -> str:
    """Return where the total lies against the sources' range, or "-" without a range."""
    if check.target_range is None or check.range_position is None:
        return "-"
    low, high = (i18n.number(value, lang) for value in check.target_range)
    # "Maintain" has one value, not a range: "Below 2,759 kcal", not "Below 2,759-2,759 kcal".
    span = low if low == high else f"{low}-{high}"
    return i18n.t(f"meal.range.{check.range_position}", lang, span=span, unit=check.unit)


def comparison_rows(result: MealPlanResult, lang: Language = "en") -> list[list[str]]:
    """Return the plan against the daily targets as cells under COMPARISON_COLUMNS, fiber last."""
    if result.totals is None:
        return []
    rows = [
        [
            nutrient_name(check.nutrient, lang),
            amount(check.plan_total, check.unit, lang),
            amount(check.target, check.unit, lang),
            difference_text(check, lang),
            range_text(check, lang),
        ]
        for check in result.comparison
    ]
    fiber = result.totals.fiber_g
    plan_fiber = i18n.t("food.not_reported", lang) if fiber is None else amount(fiber, "g", lang)
    no_target = i18n.t("meal.no_target", lang)
    return [*rows, [nutrient_name("fiber", lang), plan_fiber, no_target, "-", "-"]]
