"""The gymer's Coach and sharing page (T9.12, AC-20, AC-22): accept a code, share, revoke, end.

Every read and write goes through the store with the session's own user ID (`views/account.py`).
A gymer has one coach at a time (owner's choice, 2026-11-03). With no coach, the page asks for
the coach's code and the scopes to share (all off until the gymer ticks them); a refused code gets
one fixed message per reason, never which of missing, used or expired it was. With a coach, it
shows the coach's display name (read through `users.display_name_of()`, so the gymer knows who
sees their data), the scopes to turn on or off, and a way to end the relationship. The coach's
next read follows each change at once, as the store checks the sharing on every read (D16).
"""

import streamlit as st

from src import account as accounts
from src import chat, config, sharing
from src.store import invitations, users
from src.store.access import SCOPES, NotFound
from views import account, header
from views.text import t

URL_PATH = "sharing"
CODE_KEY = "sharing_code"
# A message for the next run, after a change the page reruns for: an i18n key and its kind.
NOTICE_KEY = "sharing_notice"
CONFIRM_END_KEY = "sharing_confirm_end"
# Set after a failed save: the next run sets the scope boxes from the store before drawing them.
RESET_KEY = "sharing_reset"


def _scope_label(scope: str) -> str:
    """Return a scope's checkbox label: its name and what it holds."""
    return f"**{t(f'scope.{scope}')}** · {t(f'scope_help.{scope}')}"


def _done(notice: str, kind: str = "success") -> None:
    """Leave a message (success, info or error) for the next run and rerun, to show the store."""
    st.session_state[NOTICE_KEY] = (notice, kind)
    st.rerun()


def _notice() -> None:
    """Show the message the previous run left, once."""
    found = st.session_state.pop(NOTICE_KEY, None)
    if found is None:
        return
    notice, kind = found
    if kind == "error":
        st.error(t(notice), icon=":material/error:")
    elif kind == "info":
        st.info(t(notice), icon=":material/info:")
    else:
        st.success(t(notice), icon=":material/check_circle:")


def _accept(user: dict) -> None:
    """Ask for the coach's code and the scopes to share, and accept it."""
    st.markdown(t("sharing.no_coach"))
    with st.form("sharing_accept"):
        st.text_input(
            t("sharing.code"),
            max_chars=config.INVITE_CODE_INPUT_MAX_CHARS,
            help=t("sharing.code_help", length=config.INVITE_CODE_LENGTH),
            key=CODE_KEY,
        )
        st.caption(t("sharing.choose"))
        chosen = [scope for scope in SCOPES if st.checkbox(_scope_label(scope), value=False)]
        submitted = st.form_submit_button(
            t("sharing.accept"), type="primary", icon=":material/handshake:"
        )
    if not submitted:
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            sharing.accept_code(conn, user["id"], st.session_state.get(CODE_KEY), chosen)
    except invitations.InvitationRefused as refused:
        message = t(f"sharing.refused.{refused.reason}", attempts=config.INVITE_MAX_ATTEMPTS)
        st.error(message, icon=":material/error:")
        return
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    except NotFound:
        return  # the account was deleted in another tab: the next run shows the welcome page
    _done("sharing.accepted")


def _share(user: dict, relationship: dict) -> None:
    """Show the scopes the gymer shares, to turn each on or off."""
    st.subheader(t("sharing.what"))
    st.caption(t("sharing.choose"))
    # Keyed by the relationship, so a new coach's form never starts from an old one's ticks.
    keys = {scope: f"sharing_{relationship['id']}_{scope}" for scope in SCOPES}
    reset = st.session_state.pop(RESET_KEY, False)
    for scope, key in keys.items():
        # The boxes start from the store, and after a failed save take the stored scopes again.
        # Assigned before the boxes are drawn, so Streamlit sends the browser the new values;
        # dropping the keys would not, and the browser would keep (and later send back) the
        # unsaved ticks (code review round 2). A submitted value is never overwritten.
        if reset or key not in st.session_state:
            st.session_state[key] = scope in relationship["scopes"]
    with st.form("sharing_scopes"):
        wanted = {scope: st.checkbox(_scope_label(scope), key=keys[scope]) for scope in SCOPES}
        submitted = st.form_submit_button(t("sharing.save"), icon=":material/save:")
    if not submitted:
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            # One transaction: every scope changes, or none does.
            users.set_scopes(conn, user["id"], relationship["id"], wanted)
    except accounts.StoreUnavailable:
        # Nothing was saved: the next run sets the boxes from the store, so they never show a
        # choice the coach's reads do not follow (code review rounds 1 and 2).
        st.session_state[RESET_KEY] = True
        _done("account.store_unavailable", "error")
        return
    except NotFound:
        # Ended in another tab (by either side) since this page was drawn.
        _done("sharing.changed", "info")
        return
    _done("sharing.saved")


def _end(user: dict, relationship: dict) -> None:
    """Offer to end the relationship, after a confirmation."""
    st.subheader(t("sharing.end"))
    st.caption(t("sharing.end_note"))
    confirmed = st.checkbox(t("sharing.confirm_end"), key=CONFIRM_END_KEY)
    if not st.button(t("sharing.end_button"), icon=":material/link_off:", disabled=not confirmed):
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            users.end_relationship(conn, user["id"], relationship["id"])
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    except NotFound:
        pass  # ended already, e.g. by the coach: the page shows it as it is now
    st.session_state.pop(CONFIRM_END_KEY, None)
    _done("sharing.ended")


def page() -> None:
    """Show the gymer's Coach and sharing page: the coach and the scopes, or a code to accept."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "gymer":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.sharing"))
        _notice()
        try:
            with accounts.open_store(account.store_path()) as conn:
                relationships = users.list_relationships(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        active = next((row for row in relationships if row["status"] == "active"), None)
        if active is None:
            _accept(user)
        else:
            name = chat.escape_markdown(active["other_name"])
            st.markdown(t("sharing.coach", name=name, since=active["accepted_at"][:10]))
            _share(user, active)
            _end(user, active)
        st.caption(f":material/info: {t('sharing.unverified')}")
