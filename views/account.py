"""The start page, the account block in the sidebar, the welcome page and the session's user.

When sign-in is set up (or in demo mode), a new session opens on the start page: sign in with
Google or continue as a guest (owner's choice, 2026-11-02); nothing else is reachable until one is
chosen. With no [auth] section the app opens as a guest, with a note in the sidebar.

The session's user is worked out again on every run (`resolve()`): from the signed-in Google
account (`st.user`, hashed with the secret into the user ID; its name, email and picture are
never read) or, in demo mode, from the demo user picked on the start page or in the sidebar (a
closed list). It is never taken from a form, a URL or a model argument (docs/SECURITY.md). A
guest never opens the store.
"""

from pathlib import Path

import streamlit as st

from src import account, chat, config, demo, guard, i18n
from src.store import users
from views import header, resources
from views.text import label_of, t

DEMO_KEY = "demo_user"
# The start page's own demo picker. A widget's identity includes the page that draws it, so the
# start page cannot share the sidebar's widget (drawn by app.py): its choice is copied to DEMO_KEY.
START_DEMO_KEY = "demo_user_start"
# Set when a visitor chose "Continue as guest" on the start page; a sign-out clears it.
GUEST_KEY = "guest_chosen"
# Kept when the user changes: the language and the session's rate limit (a sign-out is no way
# around it), and the demo picker's own value.
KEPT_KEYS = frozenset({i18n.SESSION_KEY, guard.SESSION_LIMITER_KEY, DEMO_KEY})
# Where the sidebar's goal control leaves a message for the next run (views/sidebar.py).
PROFILE_NOTICE_KEY = "profile_save_failed"
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
                # visitor can make a new account under a demo ID; the pickers show the guest too.
                st.session_state[DEMO_KEY] = None
                return None
            if found is None:
                # No account (a first sign-in, or deleted in another tab): nothing of an earlier
                # account's profile stays in the session, and its profile is loaded afresh later.
                st.session_state.pop("account_loaded_for", None)
                st.session_state.pop("profile", None)
            loaded = st.session_state.get("account_loaded_for")
            if found is not None and found["role"] == "gymer" and loaded != user_id:
                # Once per sign-in, so an edit made in this session is not replaced on each run.
                st.session_state["profile"] = account.load_profile(conn, user_id)
                st.session_state["account_loaded_for"] = user_id
    except account.StoreUnavailable:
        # Nothing is read or written: the session runs as a guest's, with one fixed message. A
        # profile loaded from the store earlier leaves the session, so a stored gymer's details
        # never reach the guest's chat (compliance run 4 on T9.5; owner's choice, 2026-11-02); one
        # typed in this state is a guest's own and stays.
        st.session_state["store_unavailable"] = True
        if st.session_state.pop("account_loaded_for", None) is not None:
            st.session_state.pop("profile", None)
            # An open "Your details" dialog would still hold the stored values.
            st.session_state["profile_form_open"] = False
        return None
    user = found or {"id": user_id, "role": "pending", "display_name": None}
    st.session_state["account"] = user
    return user


def start_offered() -> bool:
    """Return True if a new session opens on the start page: sign-in is configured, or demo mode."""
    return config.auth_configured() or config.demo_mode()


def needs_start(user: dict | None) -> bool:
    """Return True if this run shows only the start page: no user, and no guest chosen yet."""
    # Signed in to Google but with the store down is not a new visitor: no start page then.
    if user is not None or identity() is not None or st.session_state.get(GUEST_KEY):
        return False
    return start_offered()


def continue_as_guest() -> None:
    """Remember that the visitor chose to use the app as a guest (nothing is stored)."""
    st.session_state[GUEST_KEY] = True


def back_to_start() -> None:
    """Go back to the start page from a guest's session, to sign in."""
    st.session_state[GUEST_KEY] = False


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


def pick_demo_user_from_start() -> None:
    """Take the start page's demo pick as the session's demo user, with a fresh session."""
    picked = st.session_state.get(START_DEMO_KEY)
    clear_session()
    st.session_state[DEMO_KEY] = picked


def _demo_picker(key: str = DEMO_KEY, on_change=clear_session) -> None:
    """Show the demo user picker: a guest or one of the synthetic users (D18)."""
    names = {user.id: user.display_name for user in demo.DEMO_USERS}
    st.selectbox(
        t("account.demo_user"),
        [None, *names],
        format_func=lambda user_id: t("account.guest") if user_id is None else names[user_id],
        key=key,
        on_change=on_change,
    )
    st.caption(f":material/science: {t('account.demo_note')}")


def _signed_in(user: dict) -> None:
    """Show who is signed in (the display name, escaped) and the sign-out button."""
    # A subheader, so the account reads at the size of the sidebar's other headings (owner's
    # choice, 2026-11-02).
    if user["display_name"] is None:
        st.subheader(f":material/account_circle: {t('account.signed_in_google')}", anchor=False)
    else:
        role = t(f"role.{user['role']}")
        name = chat.escape_markdown(user["display_name"])
        st.subheader(f":material/account_circle: {name} · {role}", anchor=False)
    if not config.demo_mode():
        st.button(
            t("account.sign_out"), icon=":material/logout:", width="stretch", on_click=sign_out
        )


def sidebar_block(user: dict | None) -> None:
    """Show the account block at the top of the sidebar: the demo picker, the user or a note."""
    # Not drawn on the start page: app.py draws no sidebar there (owner's choice, 2026-11-02).
    if config.demo_mode():
        _demo_picker()
        if user is not None:
            _signed_in(user)
    elif user is not None:
        _signed_in(user)
    elif identity() is not None:
        # Signed in to Google, but the store failed: the session is a guest's (say so, as the guest
        # note does), no sign-in button, and a way to sign out.
        st.caption(f":material/person: {t('account.guest_note')}")
        st.button(
            t("account.sign_out"), icon=":material/logout:", width="stretch", on_click=sign_out
        )
    elif config.sign_in_ready():
        # A guest who chose to be one: no sign-in here, only the way back to the start page.
        st.caption(f":material/person: {t('account.guest_note')}")
        st.button(
            t("account.start_page"),
            icon=":material/login:",
            width="stretch",
            on_click=back_to_start,
        )
    elif config.auth_configured():
        # [auth] that is not ready: the start page could not sign anyone in either.
        st.caption(f":material/info: {t('account.not_set_up')}")
    elif config.secrets_file_broken():
        st.caption(f":material/error: {t('account.secrets_broken')}")
    else:
        st.caption(f":material/info: {t('account.sign_in_off')}")


def start_page() -> None:
    """Show the start page: sign in with Google, or continue as a guest (owner's choice)."""
    # No sidebar here (app.py draws none for this page): the language is a link at the top right,
    # the title stands alone, and the disclaimer is one line under the choices (owner's choices,
    # 2026-11-02; AC-12 keeps it on every page).
    with header.main_column():
        _language_link()
        with st.container(key=header.TITLE_KEY):
            # assets/app.css gives this title its size and green gradient.
            st.title(t("app.title"), anchor=False)
        store_notice()
        st.subheader(t("start.title"))
        if config.demo_mode():
            st.markdown(t("start.demo"))
            _demo_picker(START_DEMO_KEY, on_change=pick_demo_user_from_start)
        elif config.sign_in_ready():
            st.markdown(t("start.text"))
        else:
            st.caption(f":material/info: {t('account.not_set_up')}")
            st.markdown(t("start.guest_only"))
        with st.container(horizontal=True):
            if config.sign_in_ready():
                # The main theme's primary, not the sidebar's (T9.23's 2.0:1 note is the sidebar).
                st.button(
                    t("account.sign_in"), type="primary", icon=":material/login:", on_click=st.login
                )
            st.button(t("start.guest"), icon=":material/person:", on_click=continue_as_guest)
        st.caption(f":material/info: **{t('app.not_medical_advice')}.** {t('app.disclaimer')}")


def switch_language(language: i18n.Language) -> None:
    """Change the session's language (the start page's link)."""
    st.session_state[i18n.SESSION_KEY] = language


def _language_link() -> None:
    """Show the other language as a link-style button at the top right of the start page."""
    other = next(code for code in i18n.LANGUAGES if code != st.session_state[i18n.SESSION_KEY])
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button(
            i18n.LANGUAGE_LABELS[other],
            icon=":material/language:",
            type="tertiary",
            key="start_language",
            on_click=switch_language,
            args=(other,),
        )


def welcome_page() -> None:
    """Show the first sign-in's form: the role (chosen once) and a display name (AC-18)."""
    with header.main_column():
        header.show()
        store_notice()
        # A save that found the account deleted elsewhere says why this page appeared, here.
        failed = st.session_state.pop(PROFILE_NOTICE_KEY, None)
        if failed is not None:
            st.warning(t(failed), icon=":material/info:")
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
