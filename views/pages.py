"""The chat page (a guest's and a coach's home) and a gymer's My profile page (T9.5)."""

import streamlit as st

from views import account, chat, details, export, food, header, profile_form, sidebar, targets
from views.text import t

PROFILE_URL_PATH = "profile"


def _tabs() -> None:
    """Show the four tabs: Ask, My targets, Food lookup and Details."""
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


def _profile_dialog() -> None:
    """Open the "Your details" dialog when the profile form is open."""
    if st.session_state.get("profile_form_open"):
        # Built on each run, so the dialog's title is in the language chosen now.
        st.dialog(t("profile.dialog_title"), on_dismiss=profile_form.close_form)(
            profile_form.show
        )()


def profile_page_ref() -> st.Page:
    """Return a gymer's My profile page as st.navigation registers it, for links to it."""
    # A link finds the page by its url_path (Streamlit hashes it), so a new st.Page works.
    return st.Page(
        profile_page, title=t("page.profile"), icon=":material/person:", url_path=PROFILE_URL_PATH
    )


def profile_page() -> None:
    """Show a gymer's home: the profile in the sidebar and the daily targets (no chat, T9.5)."""
    # A gymer does not talk to the AI (owner's choice, 2026-11-02): the coach's AI drafts reviews,
    # and the gymer reads what the coach approved (T9.15, T9.16).
    with st.sidebar:
        st.divider()
        sidebar.show_profile()
        st.caption(t("theme.hint"))
    _profile_dialog()
    with header.main_column():
        header.show()
        account.store_notice()
        # The target the gymer's coach set, if it is the active one (T9.17): read-only.
        targets.coach_target_notice()
        targets.tab()


def chat_page() -> None:
    """Show the chat page: profile and last answer in the sidebar, the tabs in the middle."""
    with st.sidebar:
        # Below the account block; on the other pages About's own divider follows it.
        st.divider()
        sidebar.show_profile()
        st.caption(t("theme.hint"))
        # Both slots are filled after the main area, so they hold the turn that just ran (the PDF
        # too); until then the page keeps the previous run's card. Drawn once per run: a slot drawn
        # twice in one run keeps the first draw's extra elements (e.g. a badge the new turn lacks).
        download_slot = st.empty()
        last_answer_slot = st.empty()
    _profile_dialog()
    with header.main_column():
        header.show()
        account.store_notice()
        _tabs()
    with download_slot.container():
        export.summary_download()
    with last_answer_slot.container():
        details.last_answer_card()
