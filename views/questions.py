"""Questions to the coach under an approved weekly review (T9.25, PRD feature 27, AC-42).

Under each approved review on the gymer's My week: the thread and a box to ask; under the approved
review of the picked week on the coach's Client week: the thread and a box to answer. The store
checks every write by the review's own rule (`src/store/questions.py`); this page only offers the
box the store would accept and shows one fixed message, naming no scope, when it refuses. Every
question and answer is shown with `st.text`, so no Markdown, HTML or link is read in it, and none is
ever sent to a model. Nothing is real time: a new row shows on the page's next run.
"""

import streamlit as st

from src import account as accounts
from src import config, guard
from src.store import questions
from src.store.access import NotFound
from src.store.values import StoreValueError
from views import account, tables
from views.text import lang, t

# The outcome of the last question or answer, shown once on the next run: (review ID, kind, key).
FLASH_KEY = "questions_flash"


def _written(review_id: int, key: str) -> None:
    """Keep the success to show next run and drop a prepared export, which lacks the new row."""
    # As Today and Workouts do after a save: My data prepares the export again, with the new
    # question or answer in it (code review round 7).
    st.session_state.pop(account.MY_DATA_EXPORT_KEY, None)
    _flash(review_id, "success", key)


def _flash(review_id: int, kind: str, key: str) -> None:
    """Keep the outcome of a send to show under its review on the next run."""
    st.session_state[FLASH_KEY] = (review_id, kind, key)


def _show_flash(review_id: int | None) -> None:
    """Show the kept outcome once: under its review, or (None) wherever the caller shows it."""
    kept = st.session_state.get(FLASH_KEY)
    if kept is None or (review_id is not None and kept[0] != review_id):
        return
    st.session_state.pop(FLASH_KEY)
    _, kind, key = kept
    if kind == "success":
        st.success(t(key), icon=":material/check_circle:")
    elif key.startswith("guardrail."):
        # The guard's fixed message, in this language; it never quotes the question.
        st.warning(f"{t('questions.refused')} {t(key)}", icon=":material/health_and_safety:")
    elif key == "questions.too_long":
        st.warning(t(key, max=config.REVIEW_THREAD_MAX_CHARS), icon=":material/warning:")
    else:
        st.warning(t(key), icon=":material/info:")


def show_flash() -> None:
    """Show a kept outcome whatever its review: the coach's review may be hidden by now."""
    _show_flash(None)


def _show_rows(rows: list[dict], viewer: str) -> None:
    """Show each question and answer, oldest first, with who wrote it and when, as plain text."""
    for row in rows:
        icon = ":material/help:" if row["kind"] == "question" else ":material/person:"
        st.caption(f"{icon} {tables.thread_label(row, viewer, lang())}")
        st.text(row["text"])


def _ask_key(review_id: int) -> str:
    """Return the widget key of the question box under a review."""
    return f"questions_ask_text_{review_id}"


def _answer_key(review_id: int) -> str:
    """Return the widget key of the answer box under a review."""
    return f"questions_answer_text_{review_id}"


def _ask(user_id: str, review_id: int) -> None:
    """Check the typed question and write it; keep the outcome for the run that follows."""
    # A callback, so it runs before the page is drawn again: a send the page no longer offers
    # (the relationship ended in between) still reaches the store, which refuses it.
    text = st.session_state.get(_ask_key(review_id)) or ""
    decision = guard.check_for_a_person(text, config.REVIEW_THREAD_MAX_CHARS)
    if not decision.allowed:
        if decision.reason is guard.Rejection.GUARDRAIL:
            _flash(review_id, "warning", decision.code)
        elif decision.reason is guard.Rejection.EMPTY:
            _flash(review_id, "warning", "questions.empty")
        else:
            _flash(review_id, "warning", "questions.too_long")
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            questions.ask_question(conn, user_id, review_id, decision.text)
    except NotFound, questions.NotYourTurn:
        # Ended or a scope turned off since the page was drawn, or (another tab) a question now
        # waits or the thread is used up: the next run's line in place of the box says which, so
        # nothing is flashed too (code review round 1).
        return
    except StoreValueError:
        _flash(review_id, "warning", "questions.too_long")
        return
    except accounts.StoreUnavailable:
        _flash(review_id, "warning", "account.store_unavailable")
        return
    _written(review_id, "questions.sent")


def gymer_thread(user: dict, review: dict, rows: list[dict], askable: frozenset[int]) -> None:
    """Show the thread under one approved review on My week, with the box when the gymer may ask."""
    st.markdown(f"**{t('questions.heading')}**")
    _show_rows(rows, "gymer")
    _show_flash(review["id"])
    kinds = [row["kind"] for row in rows]
    if review["id"] not in askable:
        st.caption(f":material/lock: {t('questions.closed')}")
        return
    if kinds and kinds[-1] == "question":
        st.caption(t("questions.waiting"))
        return
    if kinds.count("question") >= config.REVIEW_THREAD_MAX_QUESTIONS:
        st.caption(t("questions.used_up", max=config.REVIEW_THREAD_MAX_QUESTIONS))
        return
    with st.form(f"questions_ask_{review['id']}", clear_on_submit=True):
        st.text_area(
            t("questions.ask_label"),
            max_chars=config.REVIEW_THREAD_MAX_CHARS,
            key=_ask_key(review["id"]),
        )
        st.caption(f":material/info: {t('questions.note')}")
        st.form_submit_button(
            t("questions.ask"),
            icon=":material/send:",
            on_click=_ask,
            args=(user["id"], review["id"]),
        )


def _answer(user_id: str, review_id: int, question_id: int) -> None:
    """Write the coach's typed answer; keep the outcome (the fixed message when refused)."""
    # A callback, as _ask(): it runs even when the next run no longer shows the client.
    cleaned = guard.clean_input(st.session_state.get(_answer_key(review_id)) or "")
    if not cleaned:
        _flash(review_id, "warning", "questions.empty")
        return
    try:
        with accounts.open_store(account.store_path()) as conn:
            questions.answer_question(conn, user_id, review_id, cleaned, question_id)
    except NotFound:
        # The relationship ended or a scope the review used was turned off while the page was
        # open: the review (or the client) is hidden now, so the message shows at the page's top.
        _flash(review_id, "warning", "questions.closed")
        return
    except questions.NotYourTurn:
        _flash(review_id, "warning", "questions.answered_already")
        return
    except StoreValueError:
        _flash(review_id, "warning", "questions.too_long")
        return
    except accounts.StoreUnavailable:
        _flash(review_id, "warning", "account.store_unavailable")
        return
    _written(review_id, "questions.answered")


def coach_thread(user: dict, review: dict, rows: list[dict]) -> None:
    """Show the thread under the approved review on Client week, with a box for an open question."""
    with st.container(border=True):
        st.markdown(f"**{t('questions.heading')}**")
        if not rows:
            st.caption(t("questions.none"))
            return
        _show_rows(rows, "coach")
        if rows[-1]["kind"] != "question":
            return
        with st.form(f"questions_answer_{review['id']}", clear_on_submit=True):
            st.text_area(
                t("questions.answer_label"),
                max_chars=config.REVIEW_THREAD_MAX_CHARS,
                key=_answer_key(review["id"]),
            )
            st.caption(f":material/info: {t('questions.answer_note')}")
            st.form_submit_button(
                t("questions.answer"),
                icon=":material/send:",
                on_click=_answer,
                args=(user["id"], review["id"], rows[-1]["id"]),
            )
