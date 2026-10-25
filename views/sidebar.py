"""The sidebar's profile: the goal control, the profile tiles, and the button that edits them."""

from typing import get_args

import streamlit as st

from src import profile, units
from views import profile_form, targets
from views.text import label_of, lang, t

GOAL_ICONS = {
    "build_muscle": ":material/fitness_center:",
    "lose_fat": ":material/local_fire_department:",
    "maintain": ":material/balance:",
}


def change_goal() -> None:
    """Save the goal picked in the sidebar into the profile."""
    goal = st.session_state["sidebar_goal"]
    current = st.session_state.get("profile")
    if current is not None and goal in get_args(profile.Goal):
        st.session_state["profile"] = profile.with_goal(current, goal)


def show_profile() -> None:
    """Show the profile in the sidebar, in the chosen units, with a button to edit it."""
    st.header(f":material/person: {t('profile.your_profile')}")
    current = st.session_state.get("profile")
    if current is None:
        st.caption(t("profile.add_caption"))
        st.button(
            t("profile.add"),
            icon=":material/person_add:",
            width="stretch",
            on_click=profile_form.open_form,
        )
        return
    system = st.session_state["units"]
    st.session_state["sidebar_goal"] = current.goal
    goal_label = label_of("goal")
    st.segmented_control(
        t("profile.goal"),
        get_args(profile.Goal),
        format_func=lambda goal: f"{GOAL_ICONS[goal]} {goal_label(goal)}",
        required=True,
        key="sidebar_goal",
        on_change=change_goal,
        label_visibility="collapsed",
        width="stretch",
    )
    left, right = st.columns(2)
    weight = units.format_weight(current.weight_kg, system, lang())
    left.metric(t("profile.weight"), weight, border=True)
    right.metric(t("profile.height"), units.format_height(current.height_cm, system), border=True)
    left.metric(t("profile.age"), current.age, border=True)
    right.metric(t("profile.sex"), t(f"sex.{current.sex}"), border=True)
    st.metric(
        t("profile.activity"),
        t(f"activity_short.{current.activity}"),
        help=t(f"activity.{current.activity}"),
        border=True,
    )
    st.button(
        t("profile.edit"), icon=":material/edit:", width="stretch", on_click=profile_form.open_form
    )
    targets.sidebar_card(system)
    st.caption(f":material/lock: {t('profile.kept')}")
