"""Streamlit entry point: composes the page; the views are in views/, the logic in src/."""

import streamlit as st

from src import config, i18n, observability
from src.agent import memory
from views import about, chat, details, export, food, header, profile_form, sidebar, targets
from views.text import t

# One JSON log handler for the app's lines, set up on every rerun (it keeps a single handler, T8.2).
observability.configure_logging()

# The language: the browser's at the start of a session, then the user's choice in the sidebar
# (T7.1, moved from the header in T9.23). Written once, before the control is drawn, so it is kept
# for the session.
if i18n.SESSION_KEY not in st.session_state:
    st.session_state[i18n.SESSION_KEY] = i18n.language_for_locale(i18n.browser_locale())

st.set_page_config(
    page_title=i18n.t("app.title", st.session_state[i18n.SESSION_KEY]),
    page_icon=":material/nutrition:",
    layout="wide",
)
# The app's own stylesheet, once per run: fixed CSS from the repo, never user or model text (T9.23).
st.html(config.APP_CSS_PATH)
# The logo at the top of the sidebar (and in the header when it is collapsed): a Material Symbols
# icon as a literal, so no image file is opened (docs/SECURITY.md, Pillow) (T9.23).
st.logo(":material/nutrition:")

# Session state: "profile" holds the UserProfile (kg and cm), "units" the unit system the user
# chose, "language" the UI language (T7.1) and "messages" the chat history (questions, and
# TurnResults with their priced TurnUsage under "usage", T5.1); "food_result" the Food lookup
# tab's last result (USDA data only), with its inputs under "food_query" and "food_grams";
# "conversation" the chat's memory, the session's own checkpointer and thread (T9.4; never in
# st.cache_resource, so sessions share nothing). All live for the session only and are never
# logged (docs/SECURITY.md).
st.session_state.setdefault("units", config.DEFAULT_UNIT_SYSTEM)
st.session_state.setdefault("messages", [])
if "conversation" not in st.session_state:
    st.session_state["conversation"] = memory.Conversation()


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
    sidebar.language_control()
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
