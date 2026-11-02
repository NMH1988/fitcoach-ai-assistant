"""The sidebar: the profile (goal control, tiles, Edit details), its privacy note, the language."""

from typing import get_args

import streamlit as st

from src import account as accounts
from src import i18n, profile, units
from views import account, my_data, profile_form, targets
from views.text import label_of, lang, t

GOAL_ICONS = {
    "build_muscle": ":material/fitness_center:",
    "lose_fat": ":material/local_fire_department:",
    "maintain": ":material/balance:",
}


SAVE_FAILED_KEY = "profile_save_failed"


def change_goal() -> None:
    """Keep the goal picked in the sidebar; a signed-in gymer's goes to the store too (T9.5)."""
    goal = st.session_state["sidebar_goal"]
    current = st.session_state.get("profile")
    if current is None or goal not in get_args(profile.Goal):
        return
    updated = profile.with_goal(current, goal)
    user = account.current_user()
    if user is not None and user["role"] == "gymer":
        # A new profile entry and target, no new weight; the session keeps the old goal if the
        # store fails, so the screen never shows a goal that was not saved. A gymer with no saved
        # entry (none yet, or all deleted on My data) has not ticked the first-save box: the goal
        # stays in the session only (compliance run 1 on T9.5).
        try:
            with accounts.open_store(account.store_path()) as conn:
                if not accounts.has_profile_entries(conn, user["id"]):
                    st.session_state[SAVE_FAILED_KEY] = "profile.goal_not_saved"
                    st.session_state["profile"] = updated
                    return
                accounts.save_profile(conn, user["id"], updated, with_weight=False)
        except accounts.StoreUnavailable:
            st.session_state[SAVE_FAILED_KEY] = "account.store_unavailable"
            return
        except accounts.AccountError as error:
            st.session_state[SAVE_FAILED_KEY] = error.code
            return
    st.session_state["profile"] = updated


def privacy_note() -> None:
    """Say what happens to the profile: kept for the session, or saved for a gymer (T9.5)."""
    user = account.current_user()
    if user is None or user["role"] not in ("coach", "gymer"):
        # A guest's text is unchanged (it fits the profile card's last line).
        st.caption(f":material/lock: {t('profile.kept')}")
        return
    st.caption(f":material/lock: {t(f'profile.note_{user["role"]}')}")
    st.page_link(
        my_data.page_ref(), label=t("profile.my_data_link"), icon=":material/folder_shared:"
    )


def show_profile() -> None:
    """Show the profile in the sidebar, in the chosen units, with a button to edit it."""
    st.header(f":material/person: {t('profile.your_profile')}")
    failed = st.session_state.pop(SAVE_FAILED_KEY, None)
    if failed is not None:
        st.error(t(failed), icon=":material/error:")
    current = st.session_state.get("profile")
    if current is None:
        st.caption(t("profile.add_caption"))
        st.button(
            t("profile.add"),
            icon=":material/person_add:",
            width="stretch",
            on_click=profile_form.open_form,
        )
        if account.current_user() is not None:
            privacy_note()
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
    privacy_note()


def language_control() -> None:
    """Show the language control: "Language" ("Sprache"), with English and Deutsch (T9.23)."""
    # required=True: a click on the chosen language cannot deselect it to None. The value is the
    # session's language, written before the control is drawn (no default here); the stored values
    # stay "en" and "de", and the options read the same in both UIs.
    st.segmented_control(
        t("language.label"),
        i18n.LANGUAGES,
        format_func=i18n.LANGUAGE_LABELS.get,
        required=True,
        key=i18n.SESSION_KEY,
        width="stretch",
    )
