"""The My data page (T9.5, AC-34): what the store holds about the user, its export and deletes.

Every read and delete goes through the store with the session's own user ID (`views/account.py`),
so a user only ever sees and deletes their own rows. The export is built only when the user asks
for it (a coach's export writes audit rows, T9.6), kept in the session until the user signs out,
deletes an entry, logs or changes food or weight (T9.13), saves or deletes a workout (T9.14),
the account is gone, or the session ends, and downloaded as JSON; the server keeps no copy.
"""

import streamlit as st

from src import account as accounts
from src import chat, config
from src.agent import review_threads
from src.store import my_data, records
from views import account, header, tables
from views.text import lang, t

EXPORT_KEY = account.MY_DATA_EXPORT_KEY
FAILED_KEY = "my_data_failed"
EXPORT_FILE_NAME = "fitcoach-my-data.json"
URL_PATH = "my-data"
_LISTS = {
    "profile_entries": records.list_profile_entries,
    "body_measurements": records.list_body_measurements,
    "nutrition_targets": records.list_targets,
    "meal_items": records.list_meal_items,
    "workout_sessions": records.list_workout_sessions,
    "preferences": records.list_preferences,
}


def _stored(user: dict) -> dict[str, list[dict]]:
    """Return the user's own records by kind: a gymer's records, a coach's preferences (T9.7)."""
    kinds = tables.STORED_KINDS_BY_ROLE.get(user["role"], ())
    if not kinds:
        return {}
    with accounts.open_store(account.store_path()) as conn:
        return {kind: _LISTS[kind](conn, user["id"], user["id"]) for kind in kinds}


def _records(stored: dict[str, list[dict]]) -> None:
    """Show one table per kind of record, or a line saying nothing of that kind is stored."""
    system = st.session_state["units"]
    for kind, rows in stored.items():
        st.markdown(f"**{t(f'my_data.kind.{kind}')}** · {t('my_data.count', count=len(rows))}")
        if rows:
            st.dataframe(tables.stored_table(kind, rows, system, lang()), hide_index=True)


def _delete_one(user: dict, stored: dict[str, list[dict]]) -> None:
    """Let the user pick one of their records and delete it."""
    system = st.session_state["units"]
    # A target the coach set is not offered: the store would refuse it (T9.17).
    entries = {
        (kind, row["id"]): tables.entry_label(kind, row, system, lang())
        for kind, rows in stored.items()
        for row in rows
        if not tables.set_by_coach(kind, row)
    }
    coach_set = any(tables.set_by_coach(kind, row) for kind, rows in stored.items() for row in rows)
    if not entries and not coach_set:
        return
    st.subheader(t("my_data.delete_one"))
    if coach_set:
        st.caption(f":material/info: {t('my_data.coach_target_note')}")
    if not entries:
        return
    picked = st.selectbox(
        t("my_data.entry"),
        list(entries),
        index=None,
        format_func=entries.get,
        placeholder=t("my_data.entry_placeholder"),
        key="my_data_entry",
    )
    if st.button(t("my_data.delete_entry"), icon=":material/delete:", disabled=picked is None):
        kind, record_id = picked
        try:
            with accounts.open_store(account.store_path()) as conn:
                records.delete_record(conn, user["id"], kind, record_id)
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except records.NotFound:
            pass  # deleted already (e.g. in another tab): the list below is read again
        st.session_state.pop("my_data_entry", None)
        # The next run loads the profile from the store again, so a deleted entry does not live
        # on in the sidebar (and cannot be saved back by the goal control); the profile leaves the
        # session now, so a store that fails on that run leaves no stored profile behind.
        st.session_state.pop("account_loaded_for", None)
        st.session_state.pop("profile", None)
        # A prepared export still holds the deleted entry: it is dropped, to be prepared again.
        st.session_state.pop(EXPORT_KEY, None)
        st.rerun()


def _export(user: dict) -> None:
    """Build the JSON export when asked, then offer it as a download."""
    st.subheader(t("my_data.export"))
    st.caption(t("my_data.export_note"))
    if st.button(t("my_data.prepare_export"), icon=":material/data_object:"):
        try:
            with accounts.open_store(account.store_path()) as conn:
                st.session_state[EXPORT_KEY] = my_data.export_user_data(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
    document = st.session_state.get(EXPORT_KEY)
    if document is not None:
        st.download_button(
            t("my_data.download"),
            data=document,
            file_name=EXPORT_FILE_NAME,
            mime="application/json",
            icon=":material/download:",
            on_click="ignore",
        )


def delete_everything() -> None:
    """Delete every row about the session's user, then sign out (or leave the demo user)."""
    user_id = account.acting_user_id()
    user = account.current_user()
    if user_id is None or user is None or user["id"] != user_id:
        return
    path = account.store_path()
    try:
        with accounts.open_store(path) as conn:
            # The review workflow's threads about or by the user go too (T9.16, AC-34).
            my_data.delete_user_data(
                conn,
                user_id,
                lambda threads: review_threads.delete_for_user(path, user_id, threads),
            )
    except accounts.StoreUnavailable:
        st.session_state[FAILED_KEY] = True
        return
    except my_data.NotFound:
        pass  # deleted already: sign out all the same
    if config.demo_mode():
        account.leave_demo_user()
    else:
        account.sign_out()


def _delete_all() -> None:
    """Offer to delete everything, after a confirmation."""
    st.subheader(t("my_data.delete_all"))
    st.caption(t("my_data.delete_all_note"))
    confirmed = st.checkbox(t("my_data.confirm_delete_all"), key="my_data_confirm")
    st.button(
        t("my_data.delete_all_button"),
        icon=":material/delete_forever:",
        disabled=not confirmed,
        on_click=delete_everything,
    )
    if st.session_state.pop(FAILED_KEY, False):
        st.error(t("account.store_unavailable"), icon=":material/error:")


def page_ref() -> st.Page:
    """Return this page as st.navigation registers it, for the menu and for links to it."""
    # A link finds the page by its url_path (Streamlit hashes it), so a new st.Page works.
    return st.Page(
        page, title=t("page.my_data"), icon=":material/folder_shared:", url_path=URL_PATH
    )


def page() -> None:
    """Show the My data page: the account, the records, delete one, export and delete all."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] == "pending":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.my_data"))
        st.markdown(t(f"my_data.intro_{user['role']}"))
        try:
            stored = _stored(user)
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        name = chat.escape_markdown(user["display_name"])
        role = t(f"role.{user['role']}")
        st.markdown(t("my_data.account", name=name, role=role, created=user["created_at"][:10]))
        if stored:
            _records(stored)
            _delete_one(user, stored)
        _export(user)
        _delete_all()
