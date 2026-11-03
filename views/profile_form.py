"""The profile form (the "Your details" dialog) and the callbacks that open, close and switch it."""

from typing import get_args

import streamlit as st

from src import account as accounts
from src import profile, units
from views import account
from views.text import label_of, lang, t

FORM_FIELDS = tuple(profile.form_values(None, "metric"))
# Set when the form opens for a signed-in gymer who has never saved a profile: the first save needs
# the opt-in box ticked (owner's choice, 2026-11-02); a gymer with saved entries agreed then.
OPT_IN_NEEDED_KEY = "profile_form_opt_in_needed"
OPT_IN_KEY = "profile_form_opt_in"


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
    st.session_state[OPT_IN_NEEDED_KEY] = _opt_in_needed()
    st.session_state[OPT_IN_KEY] = False
    st.session_state["profile_form_open"] = True


def _is_gymer() -> bool:
    """Return True if a signed-in gymer uses the session (their profile is saved)."""
    user = account.current_user()
    return user is not None and user["role"] == "gymer"


def _opt_in_needed() -> bool:
    """Return True for a signed-in gymer with no saved profile entry (or when that is unknown)."""
    if not _is_gymer():
        return False
    try:
        with accounts.open_store(account.store_path()) as conn:
            return not accounts.has_profile_entries(conn, account.current_user()["id"])
    except accounts.StoreUnavailable, accounts.AccountError:
        return True  # Save then shows why it cannot store


def _store(saved: profile.UserProfile) -> bool:
    """Save a signed-in gymer's profile, weight and target; show why not and return False."""
    if st.session_state.get(OPT_IN_NEEDED_KEY) and not st.session_state.get(OPT_IN_KEY):
        st.error(t("profile.opt_in_needed"), icon=":material/error:")
        return False
    try:
        with accounts.open_store(account.store_path()) as conn:
            accounts.save_profile(conn, account.current_user()["id"], saved, with_weight=True)
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return False
    except accounts.AccountError as error:
        st.error(t(error.code), icon=":material/error:")
        return False
    return True


def _keep(saved: profile.UserProfile, system: units.UnitSystem) -> None:
    """Keep the saved profile and its units for the session, close the dialog and rerun."""
    st.session_state["profile"] = saved
    st.session_state["units"] = system
    st.session_state["profile_form_open"] = False
    st.rerun()


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
    # The stylesheet (assets/app.css) hides "Press Enter to apply" in this dialog (T4.6, T9.23).
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
    gymer = _is_gymer()
    if gymer and st.session_state.get(OPT_IN_NEEDED_KEY):
        st.checkbox(t("profile.opt_in"), key=OPT_IN_KEY)
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
            # A gymer's profile is kept only once it is stored (a guest's or coach's at once).
            if not gymer or _store(saved):
                _keep(saved, system)
    note = "profile.saved_on_save" if gymer else "profile.kept_never_stored"
    st.caption(f":material/lock: {t(note)}")
