"""The profile form (the "Your details" dialog) and the callbacks that open, close and switch it."""

from typing import get_args

import streamlit as st

from src import config, profile, units
from views.text import label_of, lang, t

FORM_FIELDS = tuple(profile.form_values(None, "metric"))


def form_key(field: str) -> str:
    """Return the session state key of a profile form field."""
    return f"profile_form_{field}"


def open_form() -> None:
    """Fill the form with the current profile in the chosen units and open the dialog."""
    system = st.session_state["units"]
    values = profile.form_values(st.session_state.get("profile"), system)
    for field, value in values.items():
        st.session_state[form_key(field)] = value
    st.session_state["profile_form_units"] = system
    st.session_state["profile_form_units_shown"] = system
    st.session_state["profile_form_memory"] = profile.initial_form_memory(
        st.session_state.get("profile"), system
    )
    st.session_state["profile_form_open"] = True


def close_form() -> None:
    """Close the dialog without saving."""
    st.session_state["profile_form_open"] = False


def switch_units() -> None:
    """Convert the weight and height typed so far into the unit system just chosen."""
    old = st.session_state["profile_form_units_shown"]
    new = st.session_state["profile_form_units"]
    values = {field: st.session_state.get(form_key(field)) for field in FORM_FIELDS}
    converted, memory = profile.switch_form_units(
        values, old, new, st.session_state.get("profile_form_memory")
    )
    for field, value in converted.items():
        st.session_state[form_key(field)] = value
    st.session_state["profile_form_memory"] = memory
    st.session_state["profile_form_units_shown"] = new


def show() -> None:
    """Show the profile form; Save checks it and keeps the profile for this session."""
    # Drawn only while the dialog is open: a style-only st.html takes no space (T4.6).
    st.html(config.PROFILE_DIALOG_CSS)
    st.caption(f":material/info: {t('profile.form_hint')}")
    st.segmented_control(
        t("profile.units"),
        units.UNIT_SYSTEMS,
        format_func=label_of("units"),
        required=True,
        key="profile_form_units",
        on_change=switch_units,
        width="stretch",
    )
    system = st.session_state["profile_form_units"]
    st.segmented_control(
        t("profile.goal"),
        get_args(profile.Goal),
        format_func=label_of("goal"),
        key=form_key("goal"),
        width="stretch",
    )
    left, right = st.columns(2)
    with left:
        st.number_input(
            t("profile.weight_unit", unit=units.weight_unit(system)),
            min_value=0.0,
            step=10**-units.WEIGHT_DECIMALS,
            format=f"%.{units.WEIGHT_DECIMALS}f",
            key=form_key("weight"),
        )
    with right:
        st.number_input(t("profile.age_years"), min_value=0, step=1, key=form_key("age"))
    if system == "metric":
        st.number_input(t("profile.height_cm"), min_value=0, step=1, key=form_key("height_cm"))
    else:
        feet, inches = st.columns(2)
        with feet:
            st.number_input(t("profile.height_ft"), min_value=0, step=1, key=form_key("height_ft"))
        with inches:
            st.number_input(
                t("profile.height_in"),
                min_value=0,
                max_value=units.INCHES_PER_FOOT - 1,
                step=1,
                key=form_key("height_in"),
            )
    st.segmented_control(
        t("profile.sex"),
        get_args(profile.Sex),
        format_func=label_of("sex"),
        key=form_key("sex"),
        help=t("profile.sex_help"),
        width="stretch",
    )
    st.selectbox(
        t("profile.activity"),
        get_args(profile.ActivityLevel),
        index=None,
        format_func=label_of("activity"),
        placeholder=t("profile.activity_placeholder"),
        key=form_key("activity"),
    )
    if st.button(t("profile.save"), type="primary", icon=":material/check:", width="stretch"):
        values = {field: st.session_state.get(form_key(field)) for field in FORM_FIELDS}
        try:
            saved = profile.save_profile(values, system, st.session_state.get("profile"))
        except profile.ProfileError as error:
            messages = error.messages_in(lang())
            st.error(
                "\n".join(f"- {message}" for message in messages), title=t("profile.check_these")
            )
        else:
            st.session_state["profile"] = saved
            st.session_state["units"] = system
            st.session_state["profile_form_open"] = False
            st.rerun()
    st.caption(f":material/lock: {t('profile.kept_never_stored')}")
