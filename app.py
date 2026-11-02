"""Streamlit entry point: composes the page; the views are in views/, the logic in src/."""

import streamlit as st

from src import config, i18n, observability
from src.agent import memory
from views import about, account, navigation, sidebar

# One JSON log handler for the app's lines, set up on every rerun (it keeps a single handler, T8.2).
observability.configure_logging()

# The language: the browser's at the start of a session, then the user's choice in the sidebar
# (T7.1, moved from the header in T9.23). Written once, before the control is drawn, so it is kept
# for the session.
if i18n.SESSION_KEY not in st.session_state:
    st.session_state[i18n.SESSION_KEY] = i18n.language_for_locale(i18n.browser_locale())
# Kept as the session's own value, so a run that draws no language control (the start page) does
# not drop it with the widget's state (T9.5).
st.session_state[i18n.SESSION_KEY] = st.session_state[i18n.SESSION_KEY]

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
# st.cache_resource, so sessions share nothing); "account" this run's signed-in user (ID, role,
# display name), worked out again on every run from the sign-in or the demo picker (T9.5). All
# live for the session only and are never logged (docs/SECURITY.md).
st.session_state.setdefault("units", config.DEFAULT_UNIT_SYSTEM)
st.session_state.setdefault("messages", [])
if "conversation" not in st.session_state:
    st.session_state["conversation"] = memory.Conversation()

# The user decides which pages exist in this run (D20): a guest's chat, a new account's welcome
# page, or a role's pages. The account block sits at the top of the sidebar, under the menu.
user = account.resolve()
# The start page has no sidebar (owner's choice, 2026-11-02): it shows its own language link.
on_start = account.needs_start(user)
if not on_start:
    with st.sidebar:
        account.sidebar_block(user)
st.navigation(navigation.pages_for(user)).run()
# Last in the sidebar on every other page: About, then the language control directly below it
# (the answer prompt's language parts say so, T9.23).
if not on_start:
    with st.sidebar:
        about.sidebar_button()
        sidebar.language_control()
