"""The coach's Clients page: each active client's week, the former clients, and invitations.

Every read and write goes through the store with the session's own user ID (`views/account.py`):
the coach's own relationships (each client's display name read through
`users.display_name_of()`, which checks the relationship) and the coach's own codes (T9.12). Since
T9.15 each active client's row shows this week's numbers, read scope by scope through
`src/dashboard.py`, so a scope the client does not share says "Not shared"; a former client keeps
only the name and the days. The list is drawn twice, as a table and as one card per client, and the
stylesheet shows the cards on phones only (assets/app.css), as Streamlit cannot read the screen
width. A new code is returned once by the store, which keeps only its hash; the page keeps it in
the session until the coach says it is noted (or cancels it, or signs out), and it is never shown
again (D15).
"""

from datetime import date

import streamlit as st

from src import account as accounts
from src import config, dashboard, metrics
from src.store import invitations, users
from src.store.access import NotFound
from views import account, client_week, header, tables
from views.text import lang, t

URL_PATH = "clients"
# The code just created: {"id", "code", "expires_at"}, in this session only, until it is noted.
NEW_CODE_KEY = "clients_new_code"
CANCEL_KEY = "clients_cancel_pick"
OPEN_KEY = "clients_open_pick"
# The containers' keys give them the st-key-client_table and st-key-client_cards classes that
# assets/app.css shows or hides by the screen's width (T9.15).
TABLE_KEY = "client_table"
CARDS_KEY = "client_cards"


def _expiry(stamp: str) -> str:
    """Return a stored UTC timestamp as "2026-11-10 10:00", for the new code's message."""
    return stamp[:16].replace("T", " ")


def _new_code() -> None:
    """Show the code just created, once, with the button that hides it for good."""
    new = st.session_state.get(NEW_CODE_KEY)
    if new is None:
        return
    st.success(t("clients.new_code", expires=_expiry(new["expires_at"])), icon=":material/key:")
    st.code(new["code"], language=None)
    if st.button(t("clients.noted"), icon=":material/check:"):
        st.session_state.pop(NEW_CODE_KEY, None)
        st.rerun()


def _create(user: dict) -> None:
    """Create a code for the coach and keep it in the session to be shown once."""
    try:
        with accounts.open_store(account.store_path()) as conn:
            new = invitations.create_invitation(conn, user["id"])
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    except NotFound:
        return  # the account was deleted in another tab: the next run shows the welcome page
    st.session_state[NEW_CODE_KEY] = {"id": new.id, "code": new.code, "expires_at": new.expires_at}
    st.rerun()


def _cancel(user: dict, codes: list[dict]) -> None:
    """Let the coach pick one unused code and cancel it."""
    labels = {row["id"]: tables.invitation_label(row, lang()) for row in codes}
    picked = st.selectbox(
        t("clients.cancel_pick"),
        list(labels),
        index=None,
        format_func=labels.get,
        placeholder=t("clients.cancel_placeholder"),
        key=CANCEL_KEY,
    )
    if st.button(t("clients.cancel"), icon=":material/cancel:", disabled=picked is None):
        try:
            with accounts.open_store(account.store_path()) as conn:
                invitations.cancel_invitation(conn, user["id"], picked)
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            pass  # used or cancelled in the meantime: the list below is read again
        shown = st.session_state.get(NEW_CODE_KEY)
        if shown is not None and shown["id"] == picked:
            st.session_state.pop(NEW_CODE_KEY, None)
        st.session_state.pop(CANCEL_KEY, None)
        st.rerun()


def _invitations(user: dict, codes: list[dict]) -> None:
    """Show the invitations: create a code, the code just made, and the unused codes."""
    st.subheader(t("clients.invitations"))
    st.caption(t("clients.invitations_note", days=config.INVITE_TTL_DAYS))
    _new_code()
    if st.button(t("clients.create"), type="primary", icon=":material/person_add:"):
        _create(user)
    st.markdown(f"**{t('clients.open_codes')}**")
    if not codes:
        st.caption(t("clients.no_codes"))
        return
    st.dataframe(tables.invitation_table(codes, lang()), hide_index=True)
    _cancel(user, codes)


def _keep_open_pick() -> None:
    """Keep the client picked here as the Client week page's pick."""
    # The Client week page checks the pick against the coach's active clients on every run.
    st.session_state[client_week.CLIENT_KEY] = st.session_state[OPEN_KEY]


def _open_week(rows: list[tuple[dict, dict[str, str]]]) -> None:
    """Let the coach pick an active client, with a link to their week on the Client week page."""
    names = {relationship["other_id"]: cells["name"] for relationship, cells in rows}
    # The picker shows the client the link opens: the kept pick, when still an active client
    # (Streamlit drops this widget's state when another page opens; code review round 1).
    kept = st.session_state.get(client_week.CLIENT_KEY)
    st.session_state[OPEN_KEY] = kept if kept in names else None
    st.selectbox(
        t("clients.open_pick"),
        list(names),
        index=None,
        format_func=names.get,
        placeholder=t("clients.open_placeholder"),
        key=OPEN_KEY,
        on_change=_keep_open_pick,
    )
    # A link, as the menu's: st.switch_page reran with no widget states and lost the sidebar's
    # demo pick in the browser (checked on 2026-11-03), which AppTest does not show.
    st.page_link(
        client_week.page_ref(), label=t("clients.open_week"), icon=":material/calendar_month:"
    )


def _active(rows: list[tuple[dict, dict[str, str]]], monday: date) -> None:
    """Show the active clients' week as a table (wide screens) and as cards (phones)."""
    start, end = monday, metrics.week_days(monday)[-1]
    st.caption(t("clients.this_week", start=start.isoformat(), end=end.isoformat()))
    cells = [row for _, row in rows]
    with st.container(key=TABLE_KEY):
        st.dataframe(tables.client_table(cells, lang()), hide_index=True)
    with st.container(key=CARDS_KEY):
        for row in cells:
            with st.container(border=True):
                st.markdown(tables.client_card(row, lang()))
    _open_week(rows)


def _former(former: list[dict]) -> None:
    """Show the ended relationships: the name and the days only."""
    st.subheader(t("clients.former"))
    st.caption(t("clients.former_note"))
    st.dataframe(tables.former_client_table(former, lang()), hide_index=True)


def page() -> None:
    """Show the coach's Clients page: this week per client, the former ones, the invitations."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "coach":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.clients"))
        st.markdown(t("clients.intro"))
        st.caption(f":material/info: {t('clients.unverified')}")
        monday = metrics.week_start(accounts.today())
        system = st.session_state["units"]
        try:
            with accounts.open_store(account.store_path()) as conn:
                relationships = users.list_relationships(conn, user["id"])
                rows = [
                    (
                        relationship,
                        tables.client_cells(
                            relationship,
                            dashboard.relationship_week(conn, user["id"], relationship, monday),
                            system,
                            lang(),
                        ),
                    )
                    for relationship in relationships
                    if relationship["status"] == "active"
                ]
                codes = invitations.list_invitations(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        former = [row for row in relationships if row["status"] != "active"]
        if rows:
            _active(rows, monday)
        else:
            st.caption(t("clients.none"))
        if former:
            _former(former)
        _invitations(user, codes)
