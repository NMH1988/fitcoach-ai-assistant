"""Table rows, cells and text lines the views show, built from results in a given language.

Imports no streamlit (T8.1): each function takes the language as a parameter, so it is unit-tested
without AppTest.
"""

import re

from src import chat, config, i18n, units, usage
from src.i18n import Language
from src.profile import Goal
from src.tools import registry
from src.tools.energy import Macro, MacroTargetsResult, TdeeResult
from src.tools.food import FoodLookupResult

# The start of a line Markdown would read as a block: "#", "-", "+", "=" or "1." / "1)". A ">"
# (quote) is not here: chat.escape_markdown() escapes it first, so keep both in step.
LINE_START = re.compile(r"^(\d*)([#+=.)-])")
# The columns of the Details tab's table of a turn's calls (T5.1), as keys in src/i18n.py.
USAGE_COLUMNS = ("step", "model", "input", "cached", "output", "reasoning", "cost")
# A call of the answer step is named with its round ("Answer, round 2"), read back for the UI.
ANSWER_STEP = re.compile(
    re.escape(config.USAGE_STEP_ANSWER).replace(re.escape("{round}"), r"(\d+)")
)


def dollars(text: str) -> str:
    """Escape the dollar signs of a cost line, so Markdown never reads two as LaTeX."""
    return text.replace("$", r"\$")


def bold_label(line: str) -> str:
    """Return "Label: value" with the label in bold: "**This answer:** 1,234 tokens"."""
    label, value = line.split(": ", 1)
    return f"**{label}:** {value}"


def one_line(text: str) -> str:
    """Return text on one line, escaped, so it adds no formatting, image or link to a list."""
    # GFM still links a bare "www." or e-mail address (no scheme, nothing to escape); it is shown,
    # never loaded, and no raw HTML gets through.
    line = chat.escape_markdown(" ".join(text.split()))
    # A line start Markdown reads as a heading, quote, list or rule ("# Big", "> x", "1. x").
    return LINE_START.sub(r"\1\\\2", line)


def columns(names: tuple[str, ...], rows: list[list[str]]) -> dict[str, list[str]]:
    """Return rows of cells as columns by name, for st.dataframe."""
    return {name: [row[i] for row in rows] for i, name in enumerate(names)}


def tier_label(tier: int, lang: Language) -> str:
    """Return the name of an evidence tier, or "Review" for a tier the app does not know."""
    return (
        i18n.t(f"tier.{tier}", lang)
        if tier in config.EVIDENCE_TIERS
        else i18n.t("tier.unknown", lang)
    )


def topic_label(topic: str, lang: Language) -> str:
    """Return a topic filter's name, or the topic itself if the app does not know it."""
    return i18n.t(f"topic.{topic}", lang) if topic in config.TOPICS else topic


def fiber_text(fiber_g: float | None, lang: Language) -> str:
    """Return a food's fiber in grams, or "not reported" when USDA gives no value."""
    if fiber_g is None:
        return i18n.t("food.not_reported", lang)
    return f"{i18n.plain(fiber_g, lang)} g"


def macro_label(name: str, lang: Language) -> str:
    """Return a macro's name ("Protein", "Carbohydrate", "Fat") in the given language."""
    return i18n.t(f"macro.{name.lower()}", lang)


def macro_parts(targets: MacroTargetsResult) -> dict[str, tuple[Macro, int]]:
    """Return each macro's target and its kcal per gram, by name, in the macro colours' order."""
    parts = {
        "Protein": (targets.protein, config.KCAL_PER_G_PROTEIN),
        "Carbohydrate": (targets.carbohydrate, config.KCAL_PER_G_CARBOHYDRATE),
        "Fat": (targets.fat, config.KCAL_PER_G_FAT),
    }
    return {name: (macro, kcal) for name, (macro, kcal) in parts.items() if macro is not None}


def macro_kcal(targets: MacroTargetsResult) -> dict[str, int]:
    """Return the kcal a day each macro's target gives, by name."""
    return {name: macro.grams * kcal for name, (macro, kcal) in macro_parts(targets).items()}


def has_targets(result: object) -> bool:
    """Return whether a result holds complete daily targets to show."""
    return (
        isinstance(result, registry.MacroToolResult)
        and result.status == "ok"
        and result.targets.kcal_target is not None
        and bool(result.targets.weight_kg)
        and result.energy_needs.tdee_kcal is not None
        and len(macro_parts(result.targets)) == len(config.MACRO_COLORS)
    )


def per_body_weight(
    macro: Macro, targets: MacroTargetsResult, system: units.UnitSystem, lang: Language
) -> str:
    """Show a macro's grams per body weight in the user's units, rounded once."""
    # From the grams and the weight, not Macro.g_per_kg, which is already rounded to 0.1: rounding
    # it again showed 1.1 g/kg for 42 g at 40.1 kg (1.047; code review on PR #53).
    return units.format_grams_per_body_weight(macro.grams, targets.weight_kg or 0, system, lang)


def macro_cells(
    macro: Macro, targets: MacroTargetsResult, system: units.UnitSystem, lang: Language
) -> list[str]:
    """Return one macro's grams, share of the kcal and grams per body weight, as table cells."""
    return [
        f"{i18n.number(macro.grams, lang)} g",
        i18n.percent(macro.percent, lang),
        per_body_weight(macro, targets, system, lang),
    ]


def protein_range(targets: MacroTargetsResult, system: units.UnitSystem, lang: Language) -> str:
    """Return the sources' protein range for this body weight, in grams and per body weight."""
    # Always set with status "ok"; the fallback only satisfies the type.
    low, high = targets.protein_g_range or (0, 0)
    per_low, per_high = (
        units.format_per_body_weight(value, system, lang) for value in config.PROTEIN_G_PER_KG_RANGE
    )
    return i18n.t(
        "targets.protein_range",
        lang,
        low=i18n.number(low, lang),
        high=i18n.number(high, lang),
        per_low=per_low,
        per_high=per_high,
    )


def kcal_delta(difference: int, lang: Language) -> str | None:
    """Return the daily target's surplus or deficit against daily energy needs, or None."""
    # Short, as a longer delta is cut off in a quarter of the tab; the caption below says more.
    if difference == 0:
        return None
    return f"{'+' if difference > 0 else '-'}{i18n.number(abs(difference), lang)} kcal"


def goal_line(goal: Goal, difference: int, lang: Language) -> str:
    """Say the goal and how far the daily target is from daily energy needs."""
    name = i18n.t(f"goal.{goal}", lang)
    if difference == 0:
        return i18n.t("targets.at_maintenance", lang, goal=name)
    key = "targets.above_maintenance" if difference > 0 else "targets.below_maintenance"
    return i18n.t(key, lang, goal=name, kcal=i18n.number(abs(difference), lang))


def tdee_rows(result: TdeeResult, lang: Language) -> dict[str, str]:
    """Return calculate_tdee's result as label and value pairs: resting energy, factor, needs."""
    per_day = i18n.t("unit.kcal_per_day", lang)
    return {
        i18n.t("tdee.bmr", lang): f"{i18n.number(result.bmr_kcal, lang)} {per_day}",
        i18n.t("tdee.factor", lang): i18n.plain(result.activity_factor, lang),
        i18n.t("tdee.tdee", lang): f"{i18n.number(result.tdee_kcal, lang)} {per_day}",
    }


def macro_summary_rows(result: registry.MacroToolResult, lang: Language) -> dict[str, str]:
    """Return the daily target, its range, energy needs and protein range as label/value pairs."""
    targets = result.targets
    low, high = targets.kcal_range or (targets.kcal_target, targets.kcal_target)
    protein_low, protein_high = targets.protein_g_range or (0, 0)
    return {
        i18n.t("targets.daily_target", lang): f"{i18n.number(targets.kcal_target, lang)} kcal",
        i18n.t("macros.range", lang): f"{i18n.number(low, lang)}-{i18n.number(high, lang)} kcal",
        i18n.t("macros.needs", lang): f"{i18n.number(result.energy_needs.tdee_kcal, lang)} kcal",
        i18n.t("macros.protein_range", lang): (
            f"{i18n.number(protein_low, lang)}-{i18n.number(protein_high, lang)} g"
        ),
    }


def macro_table(
    targets: MacroTargetsResult, system: units.UnitSystem, lang: Language
) -> dict[str, list[str]]:
    """Return each macro's grams a day, share and grams per body weight, as table columns."""
    macros = macro_parts(targets)
    # Per body weight in the units the user chose now (g/kg or g/lb; AC-8).
    cells = [macro_cells(macro, targets, system, lang) for macro, _ in macros.values()]
    return {
        i18n.t("macros.macro", lang): [macro_label(name, lang) for name in macros],
        i18n.t("macros.per_day", lang): [row[0] for row in cells],
        i18n.t("macros.share", lang): [row[1] for row in cells],
        i18n.t("macros.per_weight", lang, unit=units.weight_unit(system)): [
            row[2] for row in cells
        ],
    }


def food_rows(result: FoodLookupResult, lang: Language) -> dict[str, str]:
    """Return a found food as label and value pairs: the USDA food, amount and nutrients."""
    nutrients = result.nutrients
    rows = {
        i18n.t("food.usda_food", lang): result.matched_name or "",
        i18n.t("food.amount", lang): f"{i18n.plain(result.grams, lang)} g",
        i18n.t("nutrient.energy", lang): f"{i18n.number(nutrients.kcal, lang)} kcal",
        i18n.t("nutrient.protein", lang): f"{i18n.plain(nutrients.protein_g, lang)} g",
        i18n.t("nutrient.carbohydrate", lang): f"{i18n.plain(nutrients.carbohydrate_g, lang)} g",
        i18n.t("nutrient.fat", lang): f"{i18n.plain(nutrients.fat_g, lang)} g",
        i18n.t("nutrient.fiber", lang): fiber_text(nutrients.fiber_g, lang),
    }
    if result.alternatives:
        rows[i18n.t("food.close_alternatives", lang)] = "; ".join(result.alternatives)
    return rows


def usage_step(step: str, lang: Language) -> str:
    """Return the name of a call's step in the given language."""
    if step == config.USAGE_STEP_REWRITE:
        return i18n.t("usage.step.rewrite", lang)
    if step == config.USAGE_STEP_SEARCH:
        return i18n.t("usage.step.search", lang)
    answer = ANSWER_STEP.fullmatch(step)
    return i18n.t("usage.step.answer", lang, round=int(answer[1])) if answer else step


def usage_rows(turn_usage: usage.TurnUsage, lang: Language) -> dict[str, list]:
    """Return a turn's calls as table columns: step, model, the token counts and the cost."""
    rows = [
        [
            usage_step(call.step, lang),
            call.model,
            call.input_tokens,
            call.cached_tokens,
            call.output_tokens,
            call.reasoning_tokens,
            usage.format_cost(cost, lang),
        ]
        for call, cost in zip(turn_usage.calls, turn_usage.costs, strict=True)
    ]
    names = [i18n.t(f"usage.col.{column}", lang) for column in USAGE_COLUMNS]
    return {name: [row[i] for row in rows] for i, name in enumerate(names)}
