"""The foods a coach suggests to a client (T9.34): the gymer's list on Today, the coach's form.

The gymer sees the active list (the newest one their current coach saved) on Today and logs an
item with one click, with the grams they choose; the store checks again that the item is on the
list. The coach builds a draft on Client week while the client shares nutrition (a food from the
USDA table, a meal slot and grams per row, added and removed before saving) and saves it as a new
list; an empty list clears the suggestions. Every read and write goes through the store with the
session's own user ID (`views/account.py`). The list is a choice of foods, not a meal plan: both
pages say so, and the calorie floor does not apply to its total (docs/PRD.md).
"""

from collections.abc import Callable
from datetime import date
from typing import NoReturn

import streamlit as st

from src import account as accounts
from src import chat, config, dashboard, diary, metrics, suggested_foods
from src.store import records
from src.store import suggestions as store_suggestions
from src.store.access import NotFound
from src.store.values import StoreValueError
from src.tools.food import food_names
from views import account, tables
from views.text import label_of, n, percent, plain, t

# The coach's draft: {"for": the client's ID, "rows": [{meal, fdc_id, food_name, grams}]}. Kept in
# a plain session key (no widget key holds an ID); another client starts a new draft.
DRAFT_KEY = "suggestions_draft"
# The outcome of the coach's last change, shown once on the next run: ("saved" | "error", key).
FLASH_KEY = "suggestions_flash"
ADD_FORM_KEY = "suggestions_add"


def _number(value: float | None) -> str:
    """Return a nutrient rounded to a whole number for the page, or a dash when unknown."""
    return "-" if value is None else n(round(value))


def _item_label(item: dict) -> str:
    """Return one suggested food as text: its name, grams, energy and macros when known."""
    # The name is from the USDA table, escaped all the same, as the page renders Markdown.
    food = chat.escape_markdown(item["food_name"])
    if item.get("kcal") is None:
        return t("suggestions.item_no_kcal", food=food, grams=plain(item["grams"]))
    return t(
        "suggestions.item",
        food=food,
        grams=plain(item["grams"]),
        kcal=_number(item["kcal"]),
        protein=_number(item["protein_g"]),
        carbs=_number(item["carbohydrate_g"]),
        fat=_number(item["fat_g"]),
    )


def gymer_section(user: dict, day: date, write: Callable[..., None]) -> None:
    """Show the gymer's active list on Today, each food with its grams and a Log button."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            active = store_suggestions.current_suggestions(conn, user["id"], user["id"])
    except accounts.StoreUnavailable, NotFound:
        return  # the page shows the store's own message, or signs the deleted account out
    if active is None or not active["items"]:
        return
    items = suggested_foods.with_nutrients(active["items"])
    with st.container(border=True):
        st.markdown(f"**:material/restaurant_menu: {t('suggestions.heading')}**")
        st.caption(t("suggestions.gymer_intro"))
        # The coach's advice, as their targets (T9.17): the app vouches for no coach (PRD).
        st.caption(f":material/info: {t('sharing.unverified')}")
        for meal in tables.MEALS:
            in_meal = [item for item in items if item["meal"] == meal]
            if not in_meal:
                continue
            st.markdown(f"*{label_of('my_data.meal')(meal)}*")
            for item in in_meal:
                # The food on its own line, then its grams and button, so the button keeps its
                # label in the narrow main column.
                st.markdown(_item_label(item))
                grams_column, button_column = st.columns(2, vertical_alignment="bottom")
                grams = grams_column.number_input(
                    t("suggestions.grams"),
                    min_value=config.FOOD_MIN_GRAMS,
                    max_value=float(config.FOOD_MAX_GRAMS),
                    value=float(item["grams"]),
                    step=config.DIARY_STEP_GRAMS,
                    format="%.1f",
                    key=f"suggestion_grams_{item['id']}",
                )
                if button_column.button(
                    t("suggestions.log"),
                    icon=":material/add:",
                    key=f"suggestion_log_{item['id']}",
                ):
                    write(
                        user,
                        lambda conn, user_id, item_id=item["id"], amount=grams: (
                            suggested_foods.log_suggested(
                                conn, user_id, item_id, grams=amount, day=day
                            )
                        ),
                        t("suggestions.logged"),
                        missing="account.gone",
                    )
        st.caption(t("usda.source_line"))


def _draft(user: dict, client_id: str) -> list[dict]:
    """Return the coach's draft for this client, started from their saved list."""
    kept = st.session_state.get(DRAFT_KEY)
    if kept is not None and kept["for"] == client_id:
        return kept["rows"]
    rows: list[dict] = []
    try:
        with accounts.open_store(account.store_path()) as conn:
            saved = store_suggestions.current_suggestions(conn, user["id"], client_id)
    except accounts.StoreUnavailable, NotFound:
        saved = None  # the Save then meets the same refusal, with its fixed message
    if saved is not None:
        rows = [
            {key: item[key] for key in ("meal", "fdc_id", "food_name", "grams")}
            for item in saved["items"]
        ]
    st.session_state[DRAFT_KEY] = {"for": client_id, "rows": rows}
    return rows


def _flash(outcome: str, key: str) -> NoReturn:
    """Keep the outcome of the coach's change for the next run, and rerun (never returns)."""
    st.session_state[FLASH_KEY] = (outcome, key)
    st.rerun()


def _show_flash() -> None:
    """Show the outcome of the coach's last change once."""
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is None:
        return
    outcome, key = flash
    if outcome == "saved":
        st.success(t(key), icon=":material/check:")
    else:
        st.error(t(key), icon=":material/error:")


def _add(rows: list[dict], meal: object, name: object, grams: object) -> NoReturn:
    """Add a row to the draft after checking it; keep why it was refused otherwise."""
    if len(rows) >= config.MAX_SUGGESTED_FOODS:
        _flash("error", "suggestions.full")
    try:
        food = diary.find_food(name)
        row = {
            "meal": diary.check_meal(meal),
            "fdc_id": food.fdc_id,
            "food_name": food.description,
            "grams": diary.check_grams(grams),
        }
    except diary.DiaryError as error:
        _flash("error", error.code)  # reruns: row is never read unset
    if any((r["meal"], r["fdc_id"]) == (row["meal"], row["fdc_id"]) for r in rows):
        _flash("error", "suggestions.twice")
    rows.append(row)
    st.rerun()


def _save(user: dict, client_id: str, rows: list[dict]) -> None:
    """Save the draft as the client's new list; keep the outcome for the next run."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            suggested_foods.save_suggestions(
                conn,
                user["id"],
                client_id,
                [(row["meal"], row["food_name"], row["grams"]) for row in rows],
            )
    except accounts.StoreUnavailable:
        _flash("error", "account.store_unavailable")
    except NotFound:
        # Not a client who shares nutrition with this coach (any more): one message for every case.
        _flash("error", "suggestions.refused")
    except diary.DiaryError as error:
        _flash("error", error.code)
    except StoreValueError:
        _flash("error", "suggestions.invalid")
    st.session_state.pop(DRAFT_KEY, None)  # read again from the saved list
    _flash("saved", "suggestions.saved")


def _share_line(week: dashboard.DashboardWeek) -> str:
    """Return the week's line on how much the client logged from the suggestions."""
    share = week.suggested
    if share is None or share.items == 0:
        return t("suggestions.share_none")
    if share.energy_share is None:
        return t("suggestions.share_no_energy", suggested=share.suggested_items, items=share.items)
    return t(
        "suggestions.share",
        suggested=share.suggested_items,
        items=share.items,
        share=percent(round(share.energy_share * 100)),
    )


def _target_today(user: dict, client_id: str) -> metrics.Target | None:
    """Return the client's target active today, whichever week is shown (as the target form)."""
    # Read through the store, as a coach's read of the client's targets (nutrition, audited).
    try:
        with accounts.open_store(account.store_path()) as conn:
            stored = records.list_targets(conn, user["id"], client_id)
    except accounts.StoreUnavailable, NotFound:
        return None
    return metrics.active_target(stored, accounts.today())


def _totals_lines(user: dict, client_id: str, rows: list[dict]) -> None:
    """Show the draft's total next to the client's target active today, as information."""
    if not rows:
        return  # an empty draft has no total to compare
    total = suggested_foods.totals(rows)
    st.caption(
        t(
            "suggestions.total",
            kcal=_number(total["kcal"]),
            protein=_number(total["protein_g"]),
            carbs=_number(total["carbohydrate_g"]),
            fat=_number(total["fat_g"]),
        )
    )
    target = _target_today(user, client_id)
    if target is None:
        st.caption(t("suggestions.no_target"))
        return
    st.caption(
        t(
            "suggestions.target",
            kcal=_number(target.kcal),
            protein=_number(target.protein_g),
            carbs=_number(target.carbohydrate_g),
            fat=_number(target.fat_g),
        )
    )


def coach_section(user: dict, client_id: str, week: dashboard.DashboardWeek) -> None:
    """Show the coach's list of suggested foods for the client, or why it is not offered."""
    st.subheader(f":material/restaurant_menu: {t('suggestions.coach_heading')}")
    _show_flash()
    if "nutrition" not in week.shared:
        st.caption(t("suggestions.not_shared"))
        return
    st.caption(_share_line(week))
    st.caption(t("suggestions.coach_intro"))
    rows = _draft(user, client_id)
    meal_label = label_of("my_data.meal")
    if not rows:
        st.caption(t("suggestions.draft_empty"))
    shown = suggested_foods.with_nutrients(rows)
    for meal in tables.MEALS:
        in_meal = [row for row in shown if row["meal"] == meal]
        if in_meal:
            listed = "; ".join(_item_label(row) for row in in_meal)
            st.markdown(f"*{meal_label(meal)}*: {listed}")
    _totals_lines(user, client_id, shown)
    if rows:
        st.caption(t("usda.source_line"))
    try:
        names = food_names()
    except Exception:
        # A missing or broken table: the fixed message, never the exception's text.
        st.error(t("diary.food_table"), icon=":material/error:")
        names = ()
    with st.form(ADD_FORM_KEY, clear_on_submit=True, border=True):
        food = st.selectbox(
            t("today.food"),
            names,
            index=None,
            placeholder=t("today.food_placeholder"),
            key="suggestions_food",
        )
        grams_column, meal_column = st.columns([1, 2], vertical_alignment="bottom")
        grams = grams_column.number_input(
            t("today.grams"),
            min_value=config.FOOD_MIN_GRAMS,
            max_value=float(config.FOOD_MAX_GRAMS),
            value=config.DIARY_DEFAULT_GRAMS,
            step=config.DIARY_STEP_GRAMS,
            format="%.1f",
            key="suggestions_grams",
        )
        meal = meal_column.segmented_control(
            t("today.meal"),
            tables.MEALS,
            format_func=meal_label,
            key="suggestions_meal",
            width="stretch",
        )
        added = st.form_submit_button(
            t("suggestions.add_row"), icon=":material/add:", disabled=not names
        )
    if added:
        _add(rows, meal, food, grams)
    if rows:
        remove_column, button_column = st.columns([3, 2], vertical_alignment="bottom")
        # The labels are made in this run, so the picker's format_func reads no session state.
        # Plain text (a selectbox renders no Markdown), so the name is not escaped here.
        labels = [
            f"{meal_label(row['meal'])}: {row['food_name']}, {plain(row['grams'])} g"
            for row in rows
        ]
        picked = remove_column.selectbox(
            t("suggestions.remove_pick"),
            range(len(rows)),
            format_func=labels.__getitem__,
            index=None,
            key="suggestions_remove_pick",
        )
        if button_column.button(t("suggestions.remove"), icon=":material/remove:") and (
            picked is not None
        ):
            rows.pop(picked)
            st.session_state.pop("suggestions_remove_pick", None)
            st.rerun()
    if st.button(t("suggestions.save"), type="primary", icon=":material/save:"):
        _save(user, client_id, rows)
