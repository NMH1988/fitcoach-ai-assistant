"""The Food lookup tab: nutrients of a USDA food and amount, with no model call (T4.7, T4.8)."""

import streamlit as st

from src import config
from src.tools import registry
from src.tools.food import FoodLookupResult, food_names
from views import tables
from views.text import lang, n, plain, t


def tab_message(result: registry.ToolResult) -> str:
    """Return why a Food lookup tab lookup gave no result, in the session's language."""
    # The tab calls no model, so its messages follow the language (owner's choice in the review
    # of PR #74); English keeps the lookup's own fixed text. The dropdown and the grams widget
    # keep both in range, so an invalid lookup is not expected; a food is never "not found".
    if lang() == "en":
        return result.message
    return t("food.tab.invalid" if result.status == "invalid" else "food.tab.error")


def show_result(result: registry.ToolResult) -> None:
    """Show a lookup from the Food lookup tab: the food and its nutrients, or why not."""
    # Every message is fixed text that never repeats the input.
    if result.status == "invalid":
        st.warning(tab_message(result), icon=":material/edit:")
        return
    if not isinstance(result, FoodLookupResult) or result.nutrients is None:
        # The foods table is missing or broken.
        st.error(tab_message(result), icon=":material/error:")
        return
    nutrients = result.nutrients
    st.caption(t("food.matched", grams=result.grams))
    # Plain text: a USDA name is never read as Markdown (docs/SECURITY.md). USDA names stay English.
    st.text(result.matched_name or "")
    energy, protein, carbohydrate, fat = st.columns(4)
    energy.metric(t("nutrient.energy"), f"{n(nutrients.kcal)} kcal", border=True)
    protein.metric(t("nutrient.protein"), f"{plain(nutrients.protein_g)} g", border=True)
    carbohydrate.metric(
        t("nutrient.carbohydrate"), f"{plain(nutrients.carbohydrate_g)} g", border=True
    )
    fat.metric(t("nutrient.fat"), f"{plain(nutrients.fat_g)} g", border=True)
    st.caption(t("food.fiber_line", fiber=tables.fiber_text(nutrients.fiber_g, lang())))
    st.caption(t("usda.source_line"))


def tab() -> None:
    """Look up the nutrients of a food and amount in the USDA table, with no model call (T4.7)."""
    st.subheader(f":material/search: {t('food.title')}")
    # The dropdown lists the table's own foods, so a visitor sees what can be looked up (T4.8).
    try:
        names = food_names()
    except Exception:
        # A missing or broken table (FoodTableError) or one that cannot be read at all (e.g. not
        # UTF-8): the fixed message, never the exception's text, and the rest of the page still
        # draws (the Details tab and the sidebar come after this tab).
        names = ()
        st.error(t("food.tab.error"), icon=":material/error:")
    food_column, grams_column, button_column = st.columns([4, 1, 1], vertical_alignment="bottom")
    food = food_column.selectbox(
        t("food.food"),
        names,
        index=None,
        key="food_query",
        placeholder=t("food.placeholder"),
        disabled=not names,
    )
    grams = grams_column.number_input(
        t("food.grams"),
        min_value=config.FOOD_MIN_GRAMS,
        max_value=float(config.FOOD_MAX_GRAMS),
        value=config.FOOD_LOOKUP_DEFAULT_GRAMS,
        step=config.FOOD_LOOKUP_STEP_GRAMS,
        format="%.1f",
        key="food_grams",
    )
    if button_column.button(
        t("food.look_up"),
        icon=":material/search:",
        key="food_lookup",
        type="primary",
        width="stretch",
        disabled=food is None,
    ):
        # Kept for the session, so the result stays while other widgets rerun the page.
        st.session_state["food_result"] = registry.run_chosen_food_lookup(food, grams)
    # The caption also says the food names are English: the USDA table has English names only.
    st.caption(t("food.caption"))
    result = st.session_state.get("food_result")
    if result is not None:
        show_result(result)
