"""The tool results shown under an answer: one table (and chart) per tool call (AC-6)."""

import streamlit as st

from src.tools import meal_plan, registry
from src.tools.energy import TdeeResult
from src.tools.food import FoodLookupResult
from src.tools.meal_plan import MealPlanResult
from views import profile_form, tables
from views import targets as daily_targets
from views.text import lang, t

# The icon before each tool result's heading; None is a refused call.
TOOL_ICONS = {
    registry.TDEE_TOOL: ":material/local_fire_department:",
    registry.MACRO_TOOL: ":material/target:",
    registry.FOOD_TOOL: ":material/restaurant:",
    registry.MEAL_PLAN_TOOL: ":material/fact_check:",
    None: ":material/block:",
}


def table(rows: dict[str, str]) -> None:
    """Show label and value pairs as a two-column table of plain text (AC-6)."""
    # st.dataframe shows cells as plain text; st.table would read Markdown in them, so a USDA name
    # could add a link or an image (docs/SECURITY.md).
    st.dataframe(
        {t("table.item"): list(rows), t("table.value"): list(rows.values())},
        hide_index=True,
        width="stretch",
    )


def show_tdee(result: TdeeResult) -> None:
    """Show calculate_tdee's result: resting energy, activity factor and daily needs."""
    table(tables.tdee_rows(result, lang()))
    # The method is the tool's own text, the same the model received (English).
    st.caption(result.method)


def show_macros(result: registry.MacroToolResult) -> None:
    """Show the daily targets as a table and the energy split as a stacked bar (AC-6)."""
    targets = result.targets
    # The second test only narrows the type: has_targets() already checked it.
    if not tables.has_targets(result) or targets.kcal_target is None:
        st.caption(result.message)
        return
    system = st.session_state["units"]
    table(tables.macro_summary_rows(result, lang()))
    st.dataframe(tables.macro_table(targets, system, lang()), hide_index=True, width="stretch")
    # The energy split as one stacked bar; the numbers are in the table above, so colour is never
    # the only signal (docs/UI_DESIGN.md, Accessibility).
    daily_targets.macro_bar(tables.macro_kcal(targets))
    # The tool's own message and notes, the same the model received (English).
    st.caption(result.message)
    for note in targets.notes:
        st.caption(f":material/info: {note}")


def show_food(result: FoodLookupResult) -> None:
    """Show a food lookup: the matched USDA food and its nutrients, or the suggestions."""
    if result.status != "found" or result.nutrients is None:
        st.caption(result.message)
        if result.alternatives:
            # USDA names as table cells: plain text, never Markdown.
            st.dataframe(
                {t("food.did_you_mean"): result.alternatives}, hide_index=True, width="stretch"
            )
        return
    table(tables.food_rows(result, lang()))
    st.caption(t("usda.source_line"))


def show_meal_plan(result: MealPlanResult) -> None:
    """Show a meal plan check: each food, then the totals against the daily targets (T4.5)."""
    current = lang()
    # The names asked for and the USDA names as table cells: plain text, never Markdown.
    columns = meal_plan.food_columns(current)
    foods = tables.columns(columns, [meal_plan.food_row(item, current) for item in result.items])
    other_names = t("meal.other_names")
    foods[other_names] = ["; ".join(item.alternatives) for item in result.items]
    # A long name would take the whole width and push the values out of view; a capped column
    # cuts it and shows it in full on hover.
    names = {
        column: st.column_config.TextColumn(width="medium")
        for column in (columns[0], columns[1], other_names)
    }
    st.dataframe(foods, hide_index=True, width="stretch", column_config=names)
    comparison = meal_plan.comparison_rows(result, current)
    if comparison:
        st.dataframe(
            tables.columns(meal_plan.comparison_columns(current), comparison),
            hide_index=True,
            width="stretch",
        )
    # The tool's own message and notes, the same the model received (English).
    st.caption(result.message)
    for note in result.notes:
        st.caption(f":material/info: {note}")
    st.caption(t("meal.source_line"))


def show_tool_run(run: registry.ToolRun, key: str) -> None:
    """Show one tool result under its heading; without a profile, a button opens the form."""
    name = run.name if run.name in registry.TOOL_TITLES else None
    st.markdown(f"**{TOOL_ICONS[name]} {t(f'tool.title.{name or "none"}')}**")
    result = run.result
    if run.status == "profile_needed":
        st.info(t("tool.profile_needed"), icon=":material/person_add:")
        st.button(
            t("profile.add"), icon=":material/person_add:", key=key, on_click=profile_form.open_form
        )
    elif isinstance(result, TdeeResult) and result.status == "ok":
        show_tdee(result)
    elif isinstance(result, registry.MacroToolResult) and result.status == "ok":
        show_macros(result)
    elif isinstance(result, FoodLookupResult) and result.status != "invalid":
        show_food(result)
    elif isinstance(result, MealPlanResult) and result.status != "invalid":
        show_meal_plan(result)
    else:
        # A refused or failed call: the fixed message the model got, never what it sent.
        st.caption(result.message)


def show_tool_runs(runs: tuple[registry.ToolRun, ...], turn: int) -> None:
    """Show each tool result of a turn in one "Tool results" expander (AC-6)."""
    # Open when a result needs the profile, so the "Add your details" button is in view.
    needs_profile = any(run.status == "profile_needed" for run in runs)
    with st.expander(
        t("tool.results", count=len(runs)), icon=":material/calculate:", expanded=needs_profile
    ):
        for number, run in enumerate(runs):
            if number:
                st.divider()
            show_tool_run(run, key=f"tool_profile_{turn}_{number}")
