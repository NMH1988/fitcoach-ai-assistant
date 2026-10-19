"""Streamlit entry point: page layout only; the logic lives in src/."""

from typing import get_args

import streamlit as st

from src import config, profile, units

st.set_page_config(page_title=config.APP_TITLE, page_icon=":material/fitness_center:")

# Session state: "profile" holds the UserProfile (kg and cm) and "units" the unit system the
# user chose. Both live for the session only and are never logged (docs/SECURITY.md).
st.session_state.setdefault("units", config.DEFAULT_UNIT_SYSTEM)

FORM_FIELDS = tuple(profile.form_values(None, "metric"))
GOAL_ICONS = {
    "build_muscle": ":material/fitness_center:",
    "lose_fat": ":material/local_fire_department:",
    "maintain": ":material/balance:",
}


def _form_key(field: str) -> str:
    """Return the session state key of a profile form field."""
    return f"profile_form_{field}"


def _open_profile_form() -> None:
    """Fill the form with the current profile in the chosen units and open the dialog."""
    system = st.session_state["units"]
    values = profile.form_values(st.session_state.get("profile"), system)
    for field, value in values.items():
        st.session_state[_form_key(field)] = value
    st.session_state["profile_form_units"] = system
    st.session_state["profile_form_units_shown"] = system
    st.session_state["profile_form_memory"] = profile.initial_form_memory(
        st.session_state.get("profile"), system
    )
    st.session_state["profile_form_open"] = True


def _close_profile_form() -> None:
    """Close the dialog without saving."""
    st.session_state["profile_form_open"] = False


def _switch_form_units() -> None:
    """Convert the weight and height typed so far into the unit system just chosen."""
    old = st.session_state["profile_form_units_shown"]
    new = st.session_state["profile_form_units"]
    values = {field: st.session_state.get(_form_key(field)) for field in FORM_FIELDS}
    converted, memory = profile.switch_form_units(
        values, old, new, st.session_state.get("profile_form_memory")
    )
    for field, value in converted.items():
        st.session_state[_form_key(field)] = value
    st.session_state["profile_form_memory"] = memory
    st.session_state["profile_form_units_shown"] = new


def _change_goal() -> None:
    """Save the goal picked in the sidebar into the profile."""
    goal = st.session_state["sidebar_goal"]
    current = st.session_state.get("profile")
    if current is not None and goal in get_args(profile.Goal):
        st.session_state["profile"] = profile.with_goal(current, goal)


@st.dialog("Your details", on_dismiss=_close_profile_form)
def _profile_form() -> None:
    """Show the profile form; Save checks it and keeps the profile for this session."""
    st.segmented_control(
        "Units",
        units.UNIT_SYSTEMS,
        format_func=units.UNIT_SYSTEM_LABELS.get,
        required=True,
        key="profile_form_units",
        on_change=_switch_form_units,
        width="stretch",
    )
    system = st.session_state["profile_form_units"]
    st.segmented_control(
        "Goal",
        get_args(profile.Goal),
        format_func=profile.GOAL_LABELS.get,
        key=_form_key("goal"),
        width="stretch",
    )
    left, right = st.columns(2)
    with left:
        st.number_input(
            f"Weight ({units.weight_unit(system)})",
            min_value=0.0,
            step=10**-units.WEIGHT_DECIMALS,
            format=f"%.{units.WEIGHT_DECIMALS}f",
            key=_form_key("weight"),
        )
    with right:
        st.number_input("Age (years)", min_value=0, step=1, key=_form_key("age"))
    if system == "metric":
        st.number_input("Height (cm)", min_value=0, step=1, key=_form_key("height_cm"))
    else:
        feet, inches = st.columns(2)
        with feet:
            st.number_input("Height (ft)", min_value=0, step=1, key=_form_key("height_ft"))
        with inches:
            st.number_input(
                "Height (in)",
                min_value=0,
                max_value=units.INCHES_PER_FOOT - 1,
                step=1,
                key=_form_key("height_in"),
            )
    st.segmented_control(
        "Sex",
        get_args(profile.Sex),
        format_func=profile.SEX_LABELS.get,
        key=_form_key("sex"),
        help="Used by the energy equation, which has a male and a female form.",
        width="stretch",
    )
    st.selectbox(
        "Activity",
        get_args(profile.ActivityLevel),
        index=None,
        format_func=profile.ACTIVITY_LABELS.get,
        placeholder="Choose your activity level",
        key=_form_key("activity"),
    )
    if st.button("Save", type="primary", icon=":material/check:", width="stretch"):
        values = {field: st.session_state.get(_form_key(field)) for field in FORM_FIELDS}
        try:
            saved = profile.save_profile(values, system, st.session_state.get("profile"))
        except profile.ProfileError as error:
            st.error("\n".join(f"- {message}" for message in error.messages), title="Check these")
        else:
            st.session_state["profile"] = saved
            st.session_state["units"] = system
            st.session_state["profile_form_open"] = False
            st.rerun()
    st.caption(":material/lock: Kept for this session only, never stored.")


def _profile_sidebar() -> None:
    """Show the profile in the sidebar, in the chosen units, with a button to edit it."""
    st.subheader(":material/person: Your profile")
    current = st.session_state.get("profile")
    if current is None:
        st.caption("Add your details to get personal targets.")
        st.button(
            "Add your details",
            icon=":material/person_add:",
            width="stretch",
            on_click=_open_profile_form,
        )
        return
    system = st.session_state["units"]
    st.session_state["sidebar_goal"] = current.goal
    st.segmented_control(
        "Goal",
        get_args(profile.Goal),
        format_func=lambda goal: f"{GOAL_ICONS[goal]} {profile.GOAL_LABELS[goal]}",
        required=True,
        key="sidebar_goal",
        on_change=_change_goal,
        label_visibility="collapsed",
        width="stretch",
    )
    left, right = st.columns(2)
    left.metric("Weight", units.format_weight(current.weight_kg, system), border=True)
    right.metric("Height", units.format_height(current.height_cm, system), border=True)
    left.metric("Age", current.age, border=True)
    right.metric("Sex", profile.SEX_LABELS[current.sex], border=True)
    st.metric(
        "Activity",
        profile.ACTIVITY_SHORT_LABELS[current.activity],
        help=profile.ACTIVITY_LABELS[current.activity],
        border=True,
    )
    st.button("Edit details", icon=":material/edit:", width="stretch", on_click=_open_profile_form)
    st.caption(":material/lock: Kept for this session only")


with st.sidebar:
    _profile_sidebar()
if st.session_state.get("profile_form_open"):
    _profile_form()

st.title(config.APP_TITLE)
st.write(config.APP_INTRO)
st.info(config.DISCLAIMER, icon=":material/info:")
