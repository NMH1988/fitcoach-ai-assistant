"""The coach's Client week page (T9.15): one active client's week, what they share only.

The client is picked from the coach's active clients, read from the store on every run; the page
reads no query parameter, so no URL can name a client, and a client whose relationship ended (or
another coach's client) is never offered and never read: `dashboard.client_week()` refuses them
with the store's `NotFound` (AC-21). The pick is kept in a plain session key, as Streamlit drops a
widget's state when another page is opened, so the Clients page can open a client's week here.
"""

import streamlit as st

from src import account as accounts
from src import dashboard
from src.store.access import NotFound
from views import account, client_targets, header, week_view, weekly_review
from views.text import t

URL_PATH = "client-week"
# The picked client's ID, kept across pages; checked against the active clients on every run.
CLIENT_KEY = "client_week_client"
PICK_KEY = "client_week_pick"
WEEK_KEY = "client_week_week"


def page_ref() -> st.Page:
    """Return the Client week page as st.navigation registers it, for switching to it."""
    # A page is found by its url_path (Streamlit hashes it), so a new st.Page works.
    return st.Page(
        page, title=t("page.client_week"), icon=":material/calendar_month:", url_path=URL_PATH
    )


def _keep_pick() -> None:
    """Keep the client picked in the plain key."""
    st.session_state[CLIENT_KEY] = st.session_state[PICK_KEY]


def _pick(clients: list[dict]) -> str | None:
    """Draw the client picker over the coach's active clients and return the picked ID."""
    names = {row["other_id"]: row["other_name"] for row in clients}
    kept = st.session_state.get(CLIENT_KEY)
    # A pick that is no longer an active client (ended, or never one) is dropped.
    st.session_state[PICK_KEY] = kept if kept in names else None
    return st.selectbox(
        t("client_week.pick"),
        list(names),
        format_func=names.get,
        placeholder=t("clients.open_placeholder"),
        key=PICK_KEY,
        on_change=_keep_pick,
    )


def page() -> None:
    """Show the Client week page: the client and week pickers, then the week's views."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "coach":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.client_week"))
        st.markdown(t("client_week.intro"))
        st.caption(f":material/info: {t('clients.unverified')}")
        try:
            with accounts.open_store(account.store_path()) as conn:
                clients = dashboard.active_clients(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        if not clients:
            st.caption(t("client_week.no_clients"))
            return
        picked = _pick(clients)
        monday = week_view.week_picker(WEEK_KEY)
        if picked is None:
            return
        try:
            with accounts.open_store(account.store_path()) as conn:
                week = dashboard.client_week(conn, user["id"], picked, monday)
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            # Ended between the picker's read and this one: the next run no longer offers them.
            st.caption(t("client_week.gone"))
            return
        week_view.show(week, st.session_state["units"])
        # The client's daily targets, set by the coach while nutrition is shared (T9.17).
        client_targets.coach_section(user, picked, week)
        # The week's review: start it, decide it, or read it (T9.16).
        weekly_review.coach_section(user, picked, monday, week)
