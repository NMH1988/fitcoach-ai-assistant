"""A gymer's Workouts page (T9.14, AC-24): log a workout's sets, edit or delete it, see the week.

A workout is drafted in the session (the day and a list of sets), then saved in one store call,
for the session's own user only (`views/account.py`). Weights are typed and shown in the user's
units and stored in kg. An edit loads a saved workout into the draft and replaces it in one
transaction (`records.replace_workout_session()`). The week below shows what `src/metrics.py`
computes from the store: facts only, no advice (config.TRAINING_ADVICE_WORDS).
"""

import math
from datetime import date

import streamlit as st

from src import account as accounts
from src import config, exercises, metrics, units
from src.store import records, values
from views import account, header, my_data, tables
from views.text import lang, t

URL_PATH = "workouts"
DRAFT_KEY = "workout_draft"
EDITING_KEY = "workout_editing"
# The day field's widget key, and the day itself in a plain key: Streamlit drops a widget's state
# when another page is opened, while the draft and the edited workout's ID are kept (code review
# round 1), so the field is given the kept day again on every run.
DAY_KEY = "workout_day"
KEPT_DAY_KEY = "workout_kept_day"
WEEK_KEY = "workout_week"
NOTICE_KEY = "workout_notice"


def _draft() -> list[dict]:
    """Return the session's draft sets (exercise ID, reps, kg, RPE), creating an empty one."""
    return st.session_state.setdefault(DRAFT_KEY, [])


def _weight_max(system: units.UnitSystem) -> float:
    """Return the highest weight the field takes in the user's units, within the store's range."""
    # Rounded down, so the highest value typed in lb never converts to more than the kg limit.
    highest = config.WORKOUT_WEIGHT_KG_RANGE[1]
    value = highest if system == "metric" else units.kg_to_lb(highest)
    return math.floor(value * 10) / 10


def _add_set() -> None:
    """Add the set typed in the fields to the draft, its weight converted to kg."""
    draft = _draft()
    if len(draft) >= config.WORKOUT_MAX_SETS:
        return
    weight = st.session_state["workout_weight"]
    draft.append(
        {
            "exercise_id": st.session_state["workout_exercise"],
            "reps": int(st.session_state["workout_reps"]),
            "weight_kg": units.weight_to_kg(float(weight), st.session_state["units"]),
            "rpe": _on_scale(st.session_state["workout_rpe"]),
        }
    )


def _on_scale(rpe: float | None) -> float | None:
    """Return a typed RPE on the scale's nearest step (7.3 -> 7.5): the field does not round it."""
    if rpe is None:
        return None
    step = config.WORKOUT_RPE_STEP
    low, high = config.WORKOUT_RPE_RANGE
    return min(max(round(rpe / step) * step, low), high)


def _keep_day() -> None:
    """Keep the day the user picked in the plain key (an emptied field keeps the last day)."""
    picked = st.session_state[DAY_KEY]
    if isinstance(picked, date):
        st.session_state[KEPT_DAY_KEY] = picked


def _remove_last_set() -> None:
    """Remove the draft's last set."""
    if _draft():
        _draft().pop()


def _clear_draft() -> None:
    """Empty the draft and leave editing, with the day back on today."""
    st.session_state[DRAFT_KEY] = []
    st.session_state.pop(EDITING_KEY, None)
    st.session_state[KEPT_DAY_KEY] = accounts.today()


def _start_edit(session: dict) -> None:
    """Load a saved workout into the draft, to be saved over the stored one."""
    st.session_state[DRAFT_KEY] = [dict(item) for item in session["sets"]]
    st.session_state[EDITING_KEY] = session["id"]
    st.session_state[KEPT_DAY_KEY] = date.fromisoformat(session["performed_on"])


def _sets() -> list[records.ExerciseSet]:
    """Return the draft as the store's sets, numbered from 1 in the order they were added."""
    return [
        records.ExerciseSet(
            exercise_id=item["exercise_id"],
            set_no=number,
            reps=item["reps"],
            weight_kg=item["weight_kg"],
            rpe=item["rpe"],
        )
        for number, item in enumerate(_draft(), start=1)
    ]


def _save() -> None:
    """Save the draft as a new workout, or over the one being edited; keep a notice to show."""
    user_id = account.acting_user_id()
    user = account.current_user()
    if user_id is None or user is None or user["id"] != user_id or not _draft():
        return
    editing = st.session_state.get(EDITING_KEY)
    day = st.session_state.get(KEPT_DAY_KEY, accounts.today())
    try:
        with accounts.open_store(account.store_path()) as conn:
            if editing is None:
                records.add_workout_session(conn, user_id, performed_on=day, sets=_sets())
            else:
                records.replace_workout_session(
                    conn, user_id, editing, performed_on=day, sets=_sets()
                )
    except accounts.StoreUnavailable:
        st.session_state[NOTICE_KEY] = ("error", "account.store_unavailable")
        return
    except values.StoreValueError:
        st.session_state[NOTICE_KEY] = ("error", "workouts.not_saved")
        return
    except records.NotFound:
        if editing is None:
            # Only a missing account refuses a new workout (deleted in another tab).
            st.session_state[NOTICE_KEY] = ("error", "account.gone")
            return
        # Deleted (e.g. in another tab) since it was loaded: the draft stays, as a new workout.
        st.session_state.pop(EDITING_KEY, None)
        st.session_state[NOTICE_KEY] = ("error", "workouts.gone")
        return
    _clear_draft()
    # A prepared export no longer matches the stored workouts: it is prepared again on request.
    st.session_state.pop(my_data.EXPORT_KEY, None)
    st.session_state[NOTICE_KEY] = ("success", "workouts.saved")


def _delete(session_id: int) -> None:
    """Delete one of the user's workouts (with its sets)."""
    user_id = account.acting_user_id()
    if user_id is None:
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            records.delete_record(conn, user_id, "workout_sessions", session_id)
    except accounts.StoreUnavailable:
        st.session_state[NOTICE_KEY] = ("error", "account.store_unavailable")
        return
    except records.NotFound:
        pass  # deleted already: the list is read again
    if st.session_state.get(EDITING_KEY) == session_id:
        _clear_draft()
    st.session_state.pop(my_data.EXPORT_KEY, None)


def _notice() -> None:
    """Show the last save's or delete's message once."""
    notice = st.session_state.pop(NOTICE_KEY, None)
    if notice is None:
        return
    kind, key = notice
    if kind == "success":
        st.success(t(key), icon=":material/check_circle:")
    else:
        st.error(t(key), icon=":material/error:")


def _set_fields(system: units.UnitSystem) -> None:
    """Show the fields of one set and the button that adds it to the draft."""
    exercise, reps, weight, rpe = st.columns([3, 1, 1, 1])
    # The language is bound now: Streamlit (and AppTest) may call format_func outside the run.
    current = lang()
    exercise.selectbox(
        t("workouts.exercise"),
        exercises.exercise_ids(),
        format_func=lambda exercise_id: tables.exercise_label(exercise_id, current),
        key="workout_exercise",
    )
    low, high = config.WORKOUT_REPS_RANGE
    reps.number_input(
        t("workouts.reps"),
        min_value=low,
        max_value=high,
        value=config.WORKOUT_DEFAULT_REPS,
        key="workout_reps",
    )
    weight.number_input(
        t("workouts.weight", unit=units.weight_unit(system)),
        min_value=0.0,
        max_value=_weight_max(system),
        value=0.0,
        step=config.WORKOUT_WEIGHT_STEP[system],
        help=t("workouts.weight_help"),
        key="workout_weight",
    )
    rpe_low, rpe_high = config.WORKOUT_RPE_RANGE
    rpe.number_input(
        t("workouts.rpe"),
        min_value=rpe_low,
        max_value=rpe_high,
        value=None,
        step=config.WORKOUT_RPE_STEP,
        format="%.1f",
        help=t("workouts.rpe_help"),
        key="workout_rpe",
    )
    full = len(_draft()) >= config.WORKOUT_MAX_SETS
    st.button(t("workouts.add_set"), icon=":material/add:", disabled=full, on_click=_add_set)
    if full:
        st.caption(t("workouts.max_sets", count=config.WORKOUT_MAX_SETS))


def _log_form(system: units.UnitSystem) -> None:
    """Show the draft workout: its day, the set fields, the sets so far and Save."""
    editing = st.session_state.get(EDITING_KEY)
    day = st.session_state.setdefault(KEPT_DAY_KEY, accounts.today())
    if editing is None:
        st.subheader(t("workouts.log"))
    else:
        st.subheader(t("workouts.editing", day=day.isoformat()))
    st.session_state[DAY_KEY] = day
    # No future day: a workout is logged once it is done (the store checks it too).
    st.date_input(
        t("workouts.day"),
        max_value=accounts.today(),
        format="YYYY-MM-DD",
        key=DAY_KEY,
        on_change=_keep_day,
    )
    _set_fields(system)
    draft = _draft()
    if draft:
        st.dataframe(tables.sets_table(draft, system, lang()), hide_index=True)
    else:
        st.caption(t("workouts.no_sets_yet"))
    save, remove, cancel = st.columns(3)
    save.button(
        t("workouts.save" if editing is None else "workouts.save_edit"),
        type="primary",
        icon=":material/save:",
        disabled=not draft,
        on_click=_save,
    )
    remove.button(
        t("workouts.remove_last"),
        icon=":material/undo:",
        disabled=not draft,
        on_click=_remove_last_set,
    )
    if editing is not None:
        cancel.button(t("workouts.cancel_edit"), icon=":material/close:", on_click=_clear_draft)
    elif draft:
        cancel.button(t("workouts.discard"), icon=":material/close:", on_click=_clear_draft)


def _week(user: dict, system: units.UnitSystem) -> None:
    """Show the chosen week's totals per exercise and its workouts, each with Edit and Delete."""
    st.subheader(t("workouts.week"))
    st.session_state.setdefault(WEEK_KEY, accounts.today())
    chosen = st.date_input(t("workouts.week_of"), format="YYYY-MM-DD", key=WEEK_KEY)
    start = metrics.week_start(chosen)
    end = metrics.week_days(start)[-1]
    try:
        with accounts.open_store(account.store_path()) as conn:
            sessions = records.list_workout_sessions(conn, user["id"], user["id"], start, end)
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    week = metrics.training_week(sessions, start)
    st.markdown(tables.training_week_line(week, system, lang()))
    if not sessions:
        st.caption(t("workouts.none_this_week"))
        return
    if week.exercises:
        st.dataframe(tables.training_week_table(week, system, lang()), hide_index=True)
        st.caption(t("workouts.volume_note"))
    # Edit would replace the draft, so it waits until the draft is saved or discarded (round 2).
    drafting = bool(_draft())
    for session in sorted(sessions, key=lambda item: (item["performed_on"], item["id"])):
        with st.container(border=True):
            st.markdown(tables.session_line(session, system, lang()))
            if session["sets"]:
                st.dataframe(tables.sets_table(session["sets"], system, lang()), hide_index=True)
            edit, delete = st.columns(2)
            edit.button(
                t("workouts.edit"),
                icon=":material/edit:",
                key=f"workout_edit_{session['id']}",
                disabled=drafting,
                help=t("workouts.edit_blocked") if drafting else None,
                on_click=_start_edit,
                args=(session,),
            )
            delete.button(
                t("workouts.delete"),
                icon=":material/delete:",
                key=f"workout_delete_{session['id']}",
                on_click=_delete,
                args=(session["id"],),
            )


def page() -> None:
    """Show the Workouts page: the stored-data note, the workout being logged and the week."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "gymer":
            return  # not registered for them (views/navigation.py); never reached
        system = st.session_state["units"]
        st.subheader(t("page.workouts"))
        st.markdown(t("workouts.intro"))
        st.caption(t("workouts.stored_note"))
        _notice()
        _log_form(system)
        st.divider()
        _week(user, system)
