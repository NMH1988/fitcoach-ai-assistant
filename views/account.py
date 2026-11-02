"""The account block in the sidebar, the welcome page of a first sign-in, and the session's user.

The session's user is worked out again on every run (`resolve()`): from the signed-in Google
account (`st.user`, hashed with the secret into the user ID; its name, email and picture are
never read) or, in demo mode, from the demo user picked in the sidebar (a closed list). It is never
taken from a form, a URL or a model argument (docs/SECURITY.md). A guest never opens the store.
"""

from pathlib import Path

import streamlit as st

from src import account, chat, config, demo, guard, i18n
from src.store import users
from views import header, resources
from views.text import label_of, t

DEMO_KEY = "demo_user"
# Kept when the user changes: the language and the session's rate limit (a sign-out is no way
# around it), and the demo picker's own value.
KEPT_KEYS = frozenset({i18n.SESSION_KEY, guard.SESSION_LIMITER_KEY, DEMO_KEY})
# The display name's length limits, for the texts that name them.
NAME_LIMITS = {"low": config.DISPLAY_NAME_CHARS[0], "high": config.DISPLAY_NAME_CHARS[1]}


def store_path() -> Path:
    """Return the store's file: the demo database in demo mode, else config.STORE_PATH."""
    return resources.demo_store() if config.demo_mode() else config.STORE_PATH


def identity() -> tuple[str, str] | None:
    """Return the signed-in Google account's issuer and subject, or None for a guest."""
    if not config.sign_in_ready():
        return None
    user = st.user
    if not user.get("is_logged_in"):
        return None
    issuer, subject = user.get("iss"), user.get("sub")
    if not (isinstance(issuer, str) and issuer and isinstance(subject, str) and subject):
        return None
    return issuer, subject


def acting_user_id() -> str | None:
    """Return the session's user ID: the keyed hash of the Google identity, or the demo user."""
    if config.demo_mode():
        picked = st.session_state.get(DEMO_KEY)
        return picked if picked in demo.USER_IDS else None
    found = identity()
    secret = config.user_key_secret()
    if found is None or secret is None:
        return None
    return account.user_key(*found, secret)


def resolve() -> dict | None:
    """Work out the session's user for this run; None for a guest or when the store fails."""
    st.session_state.pop("account", None)
    st.session_state["store_unavailable"] = False
    user_id = acting_user_id()
    if user_id is None:
        return None
    try:
        with account.open_store(store_path()) as conn:
            found = account.find_account(conn, user_id)
            if found is None and config.demo_mode():
                # A demo user deleted through My data: a guest until the app restarts, so no
                # visitor can make a new account under a demo ID.
                return None
            loaded = st.session_state.get("account_loaded_for")
            if found is not None and found["role"] == "gymer" and loaded != user_id:
                # Once per sign-in, so an edit made in this session is not replaced on each run.
                st.session_state["profile"] = account.load_profile(conn, user_id)
                st.session_state["account_loaded_for"] = user_id
    except account.StoreUnavailable:
        # Nothing is read or written: the session runs as a guest's, with one fixed message.
        st.session_state["store_unavailable"] = True
        return None
    user = found or {"id": user_id, "role": "pending", "display_name": None}
    st.session_state["account"] = user
    return user


def current_user() -> dict | None:
    """Return this run's user as resolve() found it (None for a guest)."""
    return st.session_state.get("account")


def clear_session() -> None:
    """Forget all the session holds about its user (profile, chat, forms) except the kept keys."""
    for key in list(st.session_state):
        if key not in KEPT_KEYS:
            del st.session_state[key]


def sign_out() -> None:
    """Clear the session and sign out of Google (the cookie is removed and a new session starts)."""
    clear_session()
    st.logout()


def leave_demo_user() -> None:
    """Clear the session and go back to the guest in demo mode."""
    clear_session()
    st.session_state[DEMO_KEY] = None


def store_notice() -> None:
    """Show the store's one fixed message when it failed in this run (never the error's text)."""
    if st.session_state.get("store_unavailable"):
        st.error(t("account.store_unavailable"), icon=":material/error:")


def _demo_picker() -> None:
    """Show the demo user picker: a guest or one of the synthetic users (D18)."""
    names = {user.id: user.display_name for user in demo.DEMO_USERS}
    st.selectbox(
        t("account.demo_user"),
        [None, *names],
        format_func=lambda user_id: t("account.guest") if user_id is None else names[user_id],
        key=DEMO_KEY,
        on_change=clear_session,
    )
    st.caption(f":material/science: {t('account.demo_note')}")


def _signed_in(user: dict) -> None:
    """Show who is signed in (the display name, escaped) and the sign-out button."""
    if user["display_name"] is None:
        st.markdown(f":material/account_circle: {t('account.signed_in_google')}")
    else:
        role = t(f"role.{user['role']}")
        name = chat.escape_markdown(user["display_name"])
        st.markdown(f":material/account_circle: **{name}** · {role}")
    if not config.demo_mode():
        st.button(
            t("account.sign_out"), icon=":material/logout:", width="stretch", on_click=sign_out
        )


def sidebar_block(user: dict | None) -> None:
    """Show the account block at the top of the sidebar: sign-in, demo picker or the user."""
    if config.demo_mode():
        _demo_picker()
        if user is not None:
            _signed_in(user)
    elif user is not None:
        _signed_in(user)
    elif identity() is not None:
        # Signed in to Google, but the store failed: no sign-in button, and a way to sign out.
        st.button(
            t("account.sign_out"), icon=":material/logout:", width="stretch", on_click=sign_out
        )
    elif config.sign_in_ready():
        # A secondary button: white text on the sidebar's primary is only 2.0:1 (T9.23).
        st.button(t("account.sign_in"), icon=":material/login:", width="stretch", on_click=st.login)
    elif config.auth_configured():
        st.caption(f":material/info: {t('account.not_set_up')}")
    else:
        st.caption(f":material/info: {t('account.sign_in_off')}")
    st.divider()


def welcome_page() -> None:
    """Show the first sign-in's form: the role (chosen once) and a display name (AC-18)."""
    with header.main_column():
        header.show()
        store_notice()
        st.subheader(t("account.welcome_title"))
        st.markdown(t("account.welcome_text"))
        st.radio(
            t("account.role"),
            users.ROLES,
            index=None,
            format_func=label_of("role_choice"),
            key="account_role",
        )
        st.caption(t("account.role_once"))
        st.text_input(
            t("account.display_name"),
            max_chars=config.DISPLAY_NAME_CHARS[1],
            help=t("account.display_name_help", **NAME_LIMITS),
            key="account_name",
        )
        if st.button(t("account.create"), type="primary", icon=":material/check:"):
            _create_account()


def _create_account() -> None:
    """Store the account from the welcome form, or show why it cannot be stored."""
    user = current_user()
    if user is None or user["role"] != "pending":
        return
    try:
        with account.open_store(store_path()) as conn:
            account.create_account(
                conn,
                user["id"],
                st.session_state.get("account_role"),
                st.session_state.get("account_name"),
            )
    except account.AccountError as error:
        st.error(t(error.code, **NAME_LIMITS), icon=":material/error:")
    except account.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
    else:
        st.rerun()
