"""The coach's Clients page (T9.12): the client list with what each shares, and invitations.

Every read and write goes through the store with the session's own user ID (`views/account.py`):
the coach's own relationships (each client's display name read through
`users.display_name_of()`, which checks the relationship) and the coach's own codes. A new code is
returned once by the store, which keeps only its hash; the page keeps it in the session until the
coach says it is noted (or cancels it, or signs out), and it is never shown again (D15).
"""

import streamlit as st

from src import account as accounts
from src import config
from src.store import invitations, users
from src.store.access import NotFound
from views import account, header, tables
from views.text import lang, t

URL_PATH = "clients"
# The code just created: {"id", "code", "expires_at"}, in this session only, until it is noted.
NEW_CODE_KEY = "clients_new_code"
CANCEL_KEY = "clients_cancel_pick"


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


def page() -> None:
    """Show the coach's Clients page: the clients and what they share, then the invitations."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "coach":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.clients"))
        st.markdown(t("clients.intro"))
        try:
            with accounts.open_store(account.store_path()) as conn:
                clients = users.list_relationships(conn, user["id"])
                codes = invitations.list_invitations(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        if clients:
            st.dataframe(tables.client_table(clients, lang()), hide_index=True)
        else:
            st.caption(t("clients.none"))
        _invitations(user, codes)
