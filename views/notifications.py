"""In-app notifications (T9.29, D23): the sidebar's bell, the toasts and the Notifications page.

A signed-in coach or gymer sees a bell in the sidebar with the number of unread notifications (as
text), each unread notification once a session as a toast (at most `config.NOTIFICATIONS_MAX_TOASTS`
in one run, the rest as one "and N more" toast; owner's choices, 2026-11-06), and the list on the
Notifications page with "Mark all as read". Nothing is real time: a new notification shows on the
page's next run. Guests and a new account's welcome page have none.

The notifications come from the store with the session's own user ID (`views/account.py`). Which
ones were toasted is kept in `st.session_state` only (never `st.cache_data` or `st.cache_resource`,
which sessions share, never a URL or the store), so no visit time is stored. A store error leaves
the page working without the bell and shows one fixed message, never the error.
"""

from datetime import UTC, datetime

import streamlit as st

from src import account as accounts
from src import config
from src.store import notifications
from src.store.access import NotFound
from src.store.notifications import Notification
from views import account, header, tables
from views.text import lang, t

URL_PATH = "notifications"
ROLES = ("coach", "gymer")
# The keys of the notifications already shown as a toast in this session.
TOASTED_KEY = "notifications_toasted"
# Set when "Mark all as read" could not reach the store; the page says so once.
MARK_FAILED_KEY = "notifications_mark_failed"
ICON = ":material/notifications:"


def page_ref() -> st.Page:
    """Return the Notifications page as st.navigation registers it, for the menu and the bell."""
    # A link finds the page by its url_path (Streamlit hashes it), so a new st.Page works.
    return st.Page(page, title=t("page.notifications"), icon=ICON, url_path=URL_PATH)


def _load(user: dict) -> list[Notification] | None:
    """Return the user's notifications, newest first; None when the store cannot be used."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            return notifications.list_notifications(conn, user["id"])
    except accounts.StoreUnavailable:
        return None
    except NotFound:
        return []  # the account was deleted in another tab: the next run shows the start page


def _toasts(user: dict, found: list[Notification]) -> None:
    """Show each unread notification not yet toasted in this session, at most a few per run."""
    toasted: set = st.session_state.setdefault(TOASTED_KEY, set())
    new = [item for item in found if item.unread and item.key not in toasted]
    for item in new[: config.NOTIFICATIONS_MAX_TOASTS]:
        st.toast(tables.notification_text(item, user["role"], lang()), icon=ICON)
    rest = len(new) - config.NOTIFICATIONS_MAX_TOASTS
    if rest > 0:
        st.toast(t("notifications.more", count=rest), icon=ICON)
    # The ones in the summary count as shown too, so the next run does not toast them one by one.
    toasted.update(item.key for item in new)


def sidebar(user: dict | None) -> None:
    """Show the bell with the unread count in the sidebar, and this run's toasts (T9.29)."""
    if user is None or user["role"] not in ROLES:
        return
    found = _load(user)
    if found is None:
        with st.sidebar:
            st.caption(f":material/notifications_off: {t('notifications.unavailable')}")
        return
    unread = sum(item.unread for item in found)
    with st.sidebar:
        st.page_link(
            page_ref(),
            label=t("notifications.bell", count=unread),
            icon=":material/notifications_active:" if unread else ICON,
        )
    _toasts(user, found)


def mark_all_read(loaded_at: datetime) -> None:
    """Mark as read what the page showed (up to when it loaded the list), before the next run."""
    # A callback runs before the script, so the bell drawn next counts the new mark; an event
    # stored after the page loaded stays unread (code review round 1).
    user_id = account.acting_user_id()
    user = account.current_user()
    if user_id is None or user is None or user["id"] != user_id:
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            notifications.mark_all_read(conn, user_id, loaded_at)
    except accounts.StoreUnavailable:
        st.session_state[MARK_FAILED_KEY] = True
    except NotFound:
        pass  # deleted in another tab: the next run shows the start page


def page() -> None:
    """Show the Notifications page: the list, newest first, and "Mark all as read"."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] not in ROLES:
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.notifications"))
        st.markdown(t(f"notifications.intro_{user['role']}"))
        if st.session_state.pop(MARK_FAILED_KEY, False):
            st.error(t("account.store_unavailable"), icon=":material/error:")
        # Taken before the list is read, so the mark never covers an event the page did not show.
        loaded_at = datetime.now(UTC)
        found = _load(user)
        if found is None:
            st.error(t("notifications.unavailable"), icon=":material/error:")
            return
        st.button(
            t("notifications.mark_all"),
            icon=":material/done_all:",
            disabled=not any(item.unread for item in found),
            on_click=mark_all_read,
            args=(loaded_at,),
        )
        st.caption(t("notifications.read_note"))
        if not found:
            st.caption(t("notifications.none"))
            return
        for item in found[: config.NOTIFICATIONS_MAX_SHOWN]:
            st.markdown(tables.notification_line(item, user["role"], lang()))
