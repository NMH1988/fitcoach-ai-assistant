"""The coach's target form on Client week (T9.17): a client's daily targets, set from today.

Shown only while the client shares nutrition (the week was read with it). The write goes through
`records.add_client_target()` with the session's own user ID (`views/account.py`): the store checks
the share again in the write's transaction, keeps the calorie floor and writes the audit row, so a
client who stopped sharing (or ended the relationship) since the page was drawn is refused there,
with one fixed message whatever the reason. The form never edits a target: each Save is a new row,
which the client reads as set by their coach and cannot change or delete alone.
"""

import streamlit as st

from src import account as accounts
from src import config, dashboard
from src.store import records
from src.store.access import NotFound
from src.store.values import StoreValueError
from views import account
from views.text import n, t

FORM_KEY = "client_targets_form"
# The outcome of the last Save, shown once on the next run: ("saved", day) or ("refused", code).
FLASH_KEY = "client_targets_flash"
# The (client, Monday) the form's fields were last filled for: a keyed number input keeps its value
# across runs, so another client or week clears the fields and they start from that week's target
# (code review round 1). The key holds no ID: Streamlit writes widget keys into the page.
SHOWN_FOR_KEY = "client_targets_shown_for"
FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g")
_LABELS = {
    "kcal": "client_targets.kcal",
    "protein_g": "client_targets.protein",
    "carbs_g": "client_targets.carbohydrate",
    "fat_g": "client_targets.fat",
}


def _current(week: dashboard.DashboardWeek) -> dict[str, float | None]:
    """Return the week's active target by field, to start the form from; None without one."""
    target = week.nutrition.target
    if target is None:
        return dict.fromkeys(FIELDS)
    return {
        "kcal": target.kcal,
        "protein_g": target.protein_g,
        "carbs_g": target.carbohydrate_g,
        "fat_g": target.fat_g,
    }


def _save(user: dict, client_id: str, chosen: dict[str, float | None]) -> None:
    """Write the coach's new target for the client; keep the outcome for the next run."""
    if any(value is None for value in chosen.values()):
        st.session_state[FLASH_KEY] = ("refused", "client_targets.invalid")
        return
    day = accounts.today()
    try:
        with accounts.open_store(account.store_path()) as conn:
            records.add_client_target(conn, user["id"], client_id, **chosen, effective_from=day)
    except accounts.StoreUnavailable:
        st.session_state[FLASH_KEY] = ("refused", "account.store_unavailable")
        return
    except NotFound:
        # Not a client who shares nutrition with this coach (any more): one message for every case.
        st.session_state[FLASH_KEY] = ("refused", "client_targets.refused")
        return
    except StoreValueError:
        st.session_state[FLASH_KEY] = ("refused", "client_targets.invalid")
        return
    st.session_state[FLASH_KEY] = ("saved", day.isoformat())


def _show_flash() -> None:
    """Show the outcome of the last Save once."""
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is None:
        return
    outcome, value = flash
    if outcome == "saved":
        st.success(t("client_targets.saved", day=value), icon=":material/check:")
    else:
        st.error(t(value), icon=":material/error:")


def _start_over_for(client_id: str, week: dashboard.DashboardWeek) -> None:
    """Clear the fields when the client or the week differs from the one they were filled for."""
    shown_for = (client_id, week.nutrition.week_start)
    if st.session_state.get(SHOWN_FOR_KEY) != shown_for:
        for field in FIELDS:
            st.session_state.pop(f"client_targets_{field}", None)
        st.session_state[SHOWN_FOR_KEY] = shown_for


def coach_section(user: dict, client_id: str, week: dashboard.DashboardWeek) -> None:
    """Show the form that sets the client's daily targets, or why it is not offered."""
    st.subheader(f":material/target: {t('client_targets.heading')}")
    _show_flash()
    if "nutrition" not in week.shared:
        st.caption(t("client_targets.not_shared"))
        return
    st.caption(t("client_targets.intro", floor=n(config.CALORIE_FLOOR_KCAL)))
    _start_over_for(client_id, week)
    current = _current(week)
    with st.form(FORM_KEY, enter_to_submit=False):
        chosen = {}
        for field in FIELDS:
            kcal = field == "kcal"
            chosen[field] = st.number_input(
                t(_LABELS[field]),
                min_value=float(config.CALORIE_FLOOR_KCAL) if kcal else 0.0,
                max_value=float(
                    config.TARGET_INPUT_MAX_KCAL if kcal else config.TARGET_INPUT_MAX_GRAMS
                ),
                value=current[field],
                step=10.0 if kcal else 1.0,
                format="%.0f",
                key=f"client_targets_{field}",
            )
        submitted = st.form_submit_button(
            t("client_targets.save"), type="primary", icon=":material/target:"
        )
    if submitted:
        _save(user, client_id, chosen)
        st.rerun()
