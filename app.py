"""Streamlit entry point: composes the page; the views are in views/, the logic in src/."""

import streamlit as st

from src import config, i18n
from views import about, chat, details, export, food, header, profile_form, sidebar, targets
from views.text import t

# The language: the browser's at the start of a session, then the user's choice from the header
# (T7.1). Written once, before the control is drawn, so it is kept for the session.
if i18n.SESSION_KEY not in st.session_state:
    st.session_state[i18n.SESSION_KEY] = i18n.language_for_locale(i18n.browser_locale())

st.set_page_config(
    page_title=i18n.t("app.title", st.session_state[i18n.SESSION_KEY]),
    page_icon=":material/nutrition:",
    layout="wide",
)

# Session state: "profile" holds the UserProfile (kg and cm), "units" the unit system the user
# chose, "language" the UI language (T7.1) and "messages" the chat history (questions, and
# TurnResults with their priced TurnUsage under "usage", T5.1); "food_result" the Food lookup
# tab's last result (USDA data only), with its inputs under "food_query" and "food_grams". All
# live for the session only and are never logged (docs/SECURITY.md).
st.session_state.setdefault("units", config.DEFAULT_UNIT_SYSTEM)
st.session_state.setdefault("messages", [])


def _main_area() -> None:
    """Show the header, the disclaimer and the four tabs."""
    header.show()
    ask, targets_tab, food_tab, details_tab = st.tabs(
        [
            f":material/chat: **{t('tab.ask')}**",
            f":material/target: **{t('tab.targets')}**",
            f":material/search: **{t('tab.food')}**",
            f":material/list: **{t('tab.details')}**",
        ]
    )
    with ask:
        chat.tab()
    with targets_tab:
        targets.tab()
    with food_tab:
        food.tab()
    with details_tab:
        details.tab()


with st.sidebar:
    sidebar.show_profile()
    st.caption(t("theme.hint"))
    # Both slots are filled after the main area, so they hold the turn that just ran (the PDF too);
    # until then the page keeps the previous run's card. Drawn once per run: a slot drawn twice in
    # one run keeps the first draw's extra elements (e.g. a badge the new turn does not have).
    download_slot = st.empty()
    last_answer_slot = st.empty()
    about.sidebar_button()
if st.session_state.get("profile_form_open"):
    # Built on each run, so the dialog's title is in the language chosen now.
    st.dialog(t("profile.dialog_title"), on_dismiss=profile_form.close_form)(profile_form.show)()


# The content sits in the middle column of the wide layout (config.PAGE_COLUMN_WEIGHTS).
_, main, _ = st.columns(config.PAGE_COLUMN_WEIGHTS)
with main:
    _main_area()
with download_slot.container():
    export.summary_download()
with last_answer_slot.container():
    details.last_answer_card()
