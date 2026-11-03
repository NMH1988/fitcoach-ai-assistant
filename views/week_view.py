"""A week as the dashboards draw it: the coach's Client week and the gymer's My week (T9.15).

Both pages show the same views of a `dashboard.DashboardWeek`: nutrition (how many days were
logged out of seven, the averages against the target, kcal per day and the macros), body (the
latest weight, the week's change and the weight trend) and training (the week's facts, the volume
per day and the table per exercise). A scope the reader may not read says "Not shared with you";
a day with nothing logged is "not logged", never zero eaten (AC-26). Only the week picker is a
control here: nothing on these views edits a record.
"""

from datetime import date

import streamlit as st

from src import account as accounts
from src import config, dashboard, metrics, units
from views import charts, tables
from views.text import lang, t


def week_picker(key: str) -> date:
    """Draw the week picker (any day of the week) and return the chosen week's Monday."""
    st.session_state.setdefault(key, accounts.today())
    chosen = st.date_input(t("week.week_of"), format="YYYY-MM-DD", key=key)
    return metrics.week_start(chosen)


def _draw(chart: charts.Chart | None) -> None:
    """Draw a chart spec in the full width, with its text alternative."""
    if chart is not None:
        st.vega_lite_chart(
            chart.data,
            chart.spec,
            width="stretch",
            height=config.DASHBOARD_CHART_HEIGHT_PX,
            alt=chart.alt,
        )


def _nutrition(week: dashboard.DashboardWeek) -> None:
    """Show the nutrition views: days logged, averages, target, kcal per day and the macros."""
    found = week.nutrition
    st.markdown(f"**{tables.logged_days_line(found, lang())}**")
    if found.average is not None:
        st.markdown(tables.average_line(found.average, lang()))
    st.markdown(tables.target_line(found.target, lang()))
    st.markdown(f"**{t('week.kcal_heading')}**")
    _draw(charts.kcal_per_day(found, lang()))
    if found.average is not None:
        st.markdown(f"**{t('week.macros_heading')}**")
        _draw(charts.macros_vs_target(found, lang()))


def _body(week: dashboard.DashboardWeek, system: units.UnitSystem) -> None:
    """Show the body views: the latest weight, the week's change and the weight trend."""
    st.markdown("  \n".join(tables.body_lines(week, system, lang())))
    if week.weight_trend:
        st.markdown(f"**{t('week.weight_heading', weeks=config.WEIGHT_TREND_WEEKS)}**")
        _draw(charts.weight_trend(week.weight_trend, system, lang()))


def _training(week: dashboard.DashboardWeek, system: units.UnitSystem) -> None:
    """Show the training views: the week's facts, the volume per day and the exercises."""
    found = week.training
    st.markdown(tables.training_week_line(found, system, lang()))
    if found.sessions == 0:
        st.caption(t("workouts.none_this_week"))
        return
    st.markdown(f"**{t('week.volume_heading')}**")
    _draw(charts.volume_per_day(week.volume_by_day, system, lang()))
    if found.exercises:
        st.dataframe(tables.training_week_table(found, system, lang()), hide_index=True)
        st.caption(t("workouts.volume_note"))


def show(week: dashboard.DashboardWeek, system: units.UnitSystem) -> None:
    """Show a week's nutrition, body and training views, each scope "not shared" when it is."""
    end = metrics.week_days(week.nutrition.week_start)[-1]
    st.markdown(
        f"**{t('week.range', start=week.nutrition.week_start.isoformat(), end=end.isoformat())}**"
    )
    for scope, draw in (
        ("nutrition", lambda: _nutrition(week)),
        ("body", lambda: _body(week, system)),
        ("training", lambda: _training(week, system)),
    ):
        st.subheader(t(f"scope.{scope}"))
        if scope in week.shared:
            draw()
        else:
            st.caption(t("week.not_shared"))
