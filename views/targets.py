"""The daily targets: the My targets tab, the sidebar card and the macro charts' drawing (T4.7)."""

import streamlit as st

from src import config, units
from src.tools import registry
from src.tools.energy import protein_lowered_note
from views import charts, profile_form, tables
from views.text import lang, n, percent, t


def draw_chart(chart: charts.Chart, height: int) -> None:
    """Draw a chart spec in the full width, with its text alternative."""
    st.vega_lite_chart(chart.data, chart.spec, width="stretch", height=height, alt=chart.alt)


def macro_bar(kcal: dict[str, int]) -> None:
    """Draw the kcal of each macro as one horizontal stacked bar, in the macro colours."""
    draw_chart(charts.macro_bar(kcal, lang()), config.MACRO_CHART_HEIGHT_PX)


def macro_donut(kcal: dict[str, int], total: int) -> None:
    """Draw the energy split as a donut in the macro colours, with the daily kcal in the middle."""
    draw_chart(charts.macro_donut(kcal, total, lang()), config.MACRO_DONUT_HEIGHT_PX)


def session_targets() -> registry.MacroToolResult | None:
    """Return the daily targets for the session's profile, or None without a profile."""
    # Computed from the profile on every run (no model call), so they follow the goal and details.
    current = st.session_state.get("profile")
    if current is None:
        return None
    result = registry.macro_targets(current)
    if isinstance(result, registry.MacroToolResult) and tables.has_targets(result):
        return result
    return None


def sidebar_card(system: units.UnitSystem) -> None:
    """Show the daily target and a summary card of the energy split in the sidebar (T4.7)."""
    result = session_targets()
    if result is None:
        return
    targets = result.targets
    st.metric(t("targets.daily_target"), f"{n(targets.kcal_target)} kcal", border=True)
    with st.container(border=True):
        st.markdown(f"**:material/target: {t('targets.my_targets')}**")
        macro_donut(tables.macro_kcal(targets), targets.kcal_target or 0)
        # The values as text, so the colours are never the only signal.
        for name, (macro, _) in tables.macro_parts(targets).items():
            per_weight = tables.per_body_weight(macro, targets, system, lang())
            share = percent(macro.percent)
            label = tables.macro_label(name, lang())
            st.caption(f"**{label}** {n(macro.grams)} g · {share} · {per_weight}")
        if targets.protein_lowered:
            st.caption(f":material/warning: {t('targets.protein_lowered')}")
        st.caption(t("targets.more"))


def tab() -> None:
    """Show the daily targets: four metrics, the energy split and how they were set (T4.7)."""
    st.subheader(f":material/target: {t('targets.my_targets')}")
    result = session_targets()
    if result is None:
        st.caption(t("targets.empty"))
        st.button(
            t("profile.add"),
            icon=":material/person_add:",
            key="targets_add_details",
            on_click=profile_form.open_form,
        )
        return
    system = st.session_state["units"]
    targets, needs = result.targets, result.energy_needs
    difference = (targets.kcal_target or 0) - (needs.tdee_kcal or 0)
    kcal_column, *macro_columns = st.columns(1 + len(config.MACRO_COLORS))
    kcal_column.metric(
        t("targets.daily_target"),
        f"{n(targets.kcal_target)} kcal",
        # Grey with its sign: a deficit for fat loss is the plan, not a warning.
        delta=tables.kcal_delta(difference, lang()),
        delta_color="off",
        border=True,
    )
    if targets.goal is not None:
        kcal_column.caption(tables.goal_line(targets.goal, difference, lang()))
    macros = tables.macro_parts(targets).items()
    for column, (name, (macro, _)) in zip(macro_columns, macros, strict=True):
        column.metric(tables.macro_label(name, lang()), f"{n(macro.grams)} g", border=True)
        per_weight = tables.per_body_weight(macro, targets, system, lang())
        column.caption(t("targets.share", percent=macro.percent, per_weight=per_weight))
    lowered = protein_lowered_note(targets.goal) if targets.goal is not None else None
    if targets.protein_lowered and lowered:
        st.warning(
            t(
                "targets.protein_warning",
                note=lowered,
                range=tables.protein_range(targets, system, lang()),
            ),
            icon=":material/warning:",
        )
    macro_bar(tables.macro_kcal(targets))
    maintenance = t("targets.maintenance", kcal=n(needs.tdee_kcal), method=needs.method)
    st.caption(f":material/local_fire_department: {maintenance}")
    # The tool's own message, notes and sources, the same the model received (English).
    st.caption(result.message)
    for note in targets.notes:
        if note != lowered:
            st.caption(f":material/info: {note}")
    sources = "\n".join(f"- {source}" for source in [*needs.sources, *targets.sources])
    st.caption(f":material/menu_book: {t('targets.sources')}\n{sources}")
