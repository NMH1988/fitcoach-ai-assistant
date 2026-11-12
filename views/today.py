"""The Today page (T9.13): a gymer logs food and weight for a day and sees the day by meal.

Every write and read goes through `src/diary.py` and the store with the session's own user ID
(`views/account.py`), so a gymer only ever logs, sees, edits and deletes their own entries. A food
is chosen from the USDA table's own names (T4.8); the entry keeps the nutrients for the grams
logged. The day is today in Berlin by default, or up to `config.DIARY_MAX_DAYS_BACK` days back.
"""

from datetime import date, timedelta

import streamlit as st

from src import account as accounts
from src import config, diary, metrics, units
from src.store import records
from src.tools.food import food_names
from views import account, header, my_data, suggestions, tables
from views.text import label_of, lang, t

URL_PATH = "today"
DAY_KEY = "today_day"
ENTRY_KEY = "today_entry"
# The message of the last write, shown once after the rerun that lists it.
FLASH_KEY = "today_flash"


def _names() -> tuple[str, ...]:
    """Return the USDA table's food names, or none (with the fixed message) if it cannot be read."""
    try:
        return food_names()
    except Exception:
        # A missing or broken table: the fixed message, never the exception's text.
        st.error(t("diary.food_table"), icon=":material/error:")
        return ()


def _written(message: str, done: bool = True) -> None:
    """Keep the message (done: a success) and rerun, so the day's list is read again."""
    st.session_state[FLASH_KEY] = (message, done)
    # The picked entry was changed, deleted or is gone: the picker starts empty again.
    st.session_state.pop(ENTRY_KEY, None)
    # The sidebar profile (its latest weight) and a prepared export are read again next run.
    st.session_state.pop("account_loaded_for", None)
    st.session_state.pop("profile", None)
    st.session_state.pop(my_data.EXPORT_KEY, None)
    st.rerun()


def _write(user: dict, write, message: str, missing: str = "today.gone") -> None:
    """Run one diary write; show why it failed, or keep its message (or `missing`'s) and rerun."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            write(conn, user["id"])
    except diary.DiaryError as error:
        st.error(t(error.code), icon=":material/error:")
        return
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    except records.NotFound:
        # Deleted in another tab: the entry for an edit or delete, the account for an add.
        _written(t(missing), done=False)
    _written(message)


def _food_form(user: dict, day: date, names: tuple[str, ...]) -> None:
    """Show the form that adds a food, grams and meal to the chosen day."""
    with st.form("today_add_food", clear_on_submit=True, border=True):
        st.markdown(f"**{t('today.add_food')}**")
        food = st.selectbox(
            t("today.food"),
            names,
            index=None,
            placeholder=t("today.food_placeholder"),
            disabled=not names,
            key="today_food",
        )
        grams_column, meal_column = st.columns([1, 2], vertical_alignment="bottom")
        grams = grams_column.number_input(
            t("today.grams"),
            min_value=config.FOOD_MIN_GRAMS,
            max_value=float(config.FOOD_MAX_GRAMS),
            value=config.DIARY_DEFAULT_GRAMS,
            step=config.DIARY_STEP_GRAMS,
            format="%.1f",
            key="today_grams",
        )
        meal = meal_column.segmented_control(
            t("today.meal"),
            tables.MEALS,
            format_func=label_of("my_data.meal"),
            key="today_meal",
            width="stretch",
        )
        added = st.form_submit_button(
            t("today.add"), icon=":material/add:", type="primary", disabled=not names
        )
        st.caption(t("today.food_caption"))
        st.caption(t("usda.source_line"))
    if added:
        _write(
            user,
            lambda conn, user_id: diary.log_food(
                conn, user_id, food_name=food, grams=grams, meal=meal, day=day
            ),
            t("today.added"),
            missing="account.gone",
        )


def _day_list(day: date, items: list[dict]) -> None:
    """Show the day's entries by meal, each meal's kcal and the day's totals."""
    st.subheader(t("today.day_title", day=day.isoformat()))
    if not items:
        st.caption(t("today.nothing_logged"))
        return
    for meal, meal_items in tables.meal_groups(items):
        st.markdown(tables.meal_total_line(meal, meal_items, lang()))
        # A USDA name is shown as a table cell, never read as Markdown (docs/SECURITY.md).
        st.dataframe(tables.diary_table(meal_items, lang()), hide_index=True)
    st.markdown(tables.day_total_line(metrics.day_totals(items), lang()))


def _edit(user: dict, items: list[dict], names: tuple[str, ...], today: date) -> None:
    """Let the gymer pick one of the day's entries and change or delete it."""
    if not items:
        return
    entries = {item["id"]: item for item in items}
    # The language is bound now: Streamlit (and AppTest) may call format_func outside the run.
    current = lang()
    with st.expander(t("today.edit_title"), icon=":material/edit:"):
        picked = st.selectbox(
            t("today.entry"),
            list(entries),
            index=None,
            format_func=lambda record_id: tables.diary_entry_label(entries[record_id], current),
            placeholder=t("today.entry_placeholder"),
            key=ENTRY_KEY,
        )
        if picked is None:
            return
        item = entries[picked]
        # Keyed by the entry, so each entry's fields start from its own values.
        food = st.selectbox(
            t("today.food"),
            names,
            index=names.index(item["food_name"]) if item["food_name"] in names else None,
            placeholder=t("today.food_placeholder"),
            key=f"today_edit_food_{picked}",
        )
        grams = st.number_input(
            t("today.grams"),
            min_value=config.FOOD_MIN_GRAMS,
            max_value=float(config.FOOD_MAX_GRAMS),
            value=min(max(item["grams"], config.FOOD_MIN_GRAMS), float(config.FOOD_MAX_GRAMS)),
            step=config.DIARY_STEP_GRAMS,
            format="%.1f",
            key=f"today_edit_grams_{picked}",
        )
        meal = st.segmented_control(
            t("today.meal"),
            tables.MEALS,
            default=item["meal"],
            format_func=label_of("my_data.meal"),
            key=f"today_edit_meal_{picked}",
            width="stretch",
        )
        day = st.date_input(
            t("today.day"),
            value=date.fromisoformat(item["consumed_on"]),
            min_value=today - timedelta(days=config.DIARY_MAX_DAYS_BACK),
            max_value=today,
            format="YYYY-MM-DD",
            key=f"today_edit_day_{picked}",
        )
        save_column, delete_column = st.columns(2)
        if save_column.button(
            t("today.save_changes"), icon=":material/check:", type="primary", width="stretch"
        ):
            _write(
                user,
                lambda conn, user_id: diary.edit_food(
                    conn, user_id, picked, food_name=food, grams=grams, meal=meal, day=day
                ),
                t("today.changed"),
            )
        if delete_column.button(t("today.delete"), icon=":material/delete:", width="stretch"):
            _write(
                user,
                lambda conn, user_id: records.delete_record(conn, user_id, "meal_items", picked),
                t("today.deleted"),
            )


def _weight(user: dict, day: date, weights: list[dict]) -> None:
    """Show the day's weights and a field that logs one more in the chosen units."""
    system = st.session_state["units"]
    st.subheader(t("today.weight_title"))
    if weights:
        st.caption(tables.weights_line(weights, system, lang()))
    value_column, button_column = st.columns([2, 1], vertical_alignment="bottom")
    value = value_column.number_input(
        t("today.weight_unit", unit=units.weight_unit(system)),
        min_value=0.0,
        value=None,
        step=10**-units.WEIGHT_DECIMALS,
        format=f"%.{units.WEIGHT_DECIMALS}f",
        key=f"today_weight_{system}",
    )
    if button_column.button(
        t("today.save_weight"), icon=":material/monitor_weight:", disabled=value is None
    ):
        _write(
            user,
            lambda conn, user_id: diary.log_weight(
                conn, user_id, value=value, system=system, day=day
            ),
            t("today.weight_saved"),
            missing="account.gone",
        )


def page() -> None:
    """Show the Today page: the day, the food form, the day's list, edits and the weight."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "gymer":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.today"))
        st.caption(t("today.intro"))
        st.caption(f":material/lock: {t('today.made_up_only')}")
        try:
            with accounts.open_store(account.store_path()) as conn:
                saved = accounts.has_profile_entries(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except accounts.AccountError:
            return  # the account was deleted in another tab; the next run signs it out
        if not saved:
            # The first Save on My profile carries the opt-in tick and the 18+ check, so no food
            # or weight is stored before them (owner's choice, 2026-11-03; diary checks it too).
            st.info(t("today.profile_first"), icon=":material/person:")
            return
        flash = st.session_state.pop(FLASH_KEY, None)
        if flash is not None:
            message, done = flash
            if done:
                st.success(message, icon=":material/check_circle:")
            else:
                st.info(message, icon=":material/info:")
        today = metrics.berlin_day()
        oldest = today - timedelta(days=config.DIARY_MAX_DAYS_BACK)
        kept = st.session_state.get(DAY_KEY)
        if kept is not None and not oldest <= kept <= today:
            # A tab left open past midnight keeps its day, which may now be out of range: a keyed
            # date_input keeps its value when min_value changes, and an entry of that day would
            # then make the edit field's value fall below its own min_value (an exception). Popped,
            # not set: the widget then starts from value=today with no Session State warning.
            st.session_state.pop(DAY_KEY, None)
        day = st.date_input(
            t("today.day"),
            value=today,
            min_value=oldest,
            max_value=today,
            format="YYYY-MM-DD",
            help=t("today.day_help"),
            key=DAY_KEY,
        )
        names = _names()
        # The foods the gymer's coach suggests, each logged in one click (T9.34).
        suggestions.gymer_section(user, day, _write)
        _food_form(user, day, names)
        try:
            with accounts.open_store(account.store_path()) as conn:
                items = diary.day_items(conn, user["id"], day)
                weights = diary.day_weights(conn, user["id"], day)
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except records.NotFound:
            return  # the account was deleted in another tab; the next run signs it out
        _day_list(day, items)
        _edit(user, items, names, today)
        _weight(user, day, weights)
        st.caption(f":material/lock: {t('today.stored_note')}")
