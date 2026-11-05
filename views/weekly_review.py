"""The weekly review on the coach's Client week page, and a review's text on My week (T9.16).

Under the week the coach picked: a "Draft weekly review" button once the week is over, then the
draft with Approve, Edit and Reject (D17's human in the loop). The run and the decision go through
`src/agent/review.py`, which checks access in the store at every step; this page only shows what
`dashboard.client_week()` already read (the coach's reviews of this client whose every scope is
still shared) and the outcome of the last action. The texts are escaped onto plain lines
(`tables.review_sections()`), so neither the model nor a coach adds a link, image or HTML. The
gymer's My week shows an approved review's text the same way, read-only.
"""

from datetime import date, timedelta

import streamlit as st

from src import account as accounts
from src import config, dashboard, guard, i18n
from src.agent import graph, review
from src.chat import PromptMissingError
from views import account, resources, tables
from views.text import lang, t

# The outcome of the last start or decision, shown once on the next run.
FLASH_KEY = "weekly_review_flash"
# The ID of the review whose edit form is open.
EDIT_KEY = "weekly_review_editing"
START_KEY = "weekly_review_start"
_SUCCESS = frozenset({"pending", "approved", "edited", "rejected"})
_FIELDS = ("observations", "hypotheses", "recommendations")


def show_text(text: dict) -> None:
    """Show a review's text: its sections, then the sources its labels cite."""
    if not tables.has_review_fields(text):
        # A review saved before T9.16 fixed the fields: every text as an escaped list.
        st.markdown(tables.review_markdown(text))
        return
    for heading, body in tables.review_sections(text, lang()):
        st.markdown(f"**{heading}**")
        st.markdown(body)
    lines = tables.review_source_lines(text, resources.manifest(), lang())
    if lines:
        st.markdown(f"**{t('review.sources')}**")
        st.markdown("\n".join(f"- [{line}]({url})" for line, url in lines))


def _context() -> review.ReviewContext:
    """Return the run's context: the store file, the cached index and model, the owner's prompt."""
    return review.ReviewContext(
        store_path=account.store_path(),
        chat_model=resources.review_model,
        open_index=resources.index,
        keyword_index=resources.keyword_index,
        prompt=graph.load_prompt(
            config.REVIEW_PROMPT_PATH, config.REVIEW_PROMPT_MISSING_MESSAGE, "prompt.review_missing"
        ),
    )


def _flash(result: review.RunResult) -> None:
    """Keep the outcome to show on the next run."""
    st.session_state[FLASH_KEY] = result


def _show_flash() -> None:
    """Show the last action's outcome once, in the chosen language."""
    result = st.session_state.pop(FLASH_KEY, None)
    if result is None:
        return
    if isinstance(result, guard.GuardResult):
        # The session's rate limit refused the run; its numbers fill the text in this language.
        st.warning(t(f"review.{result.reason.value}", **result.params), icon=":material/timer:")
        return
    if result.outcome == "error":
        # A fixed message in the chosen language (AC-30); never the service's own text.
        code = result.error_code if result.error_code in i18n.TEXT["en"] else "llm.error"
        st.error(t(code), icon=":material/error:")
    elif result.outcome == "edit_invalid":
        checks = " ".join(t(f"review.check.{code}") for code in result.errors)
        st.warning(t("review.outcome.edit_invalid", checks=checks), icon=":material/warning:")
    elif result.outcome in _SUCCESS:
        st.success(t(f"review.outcome.{result.outcome}"), icon=":material/check_circle:")
    else:
        st.warning(t(f"review.outcome.{result.outcome}"), icon=":material/info:")


def _start(user: dict, client_id: str, monday: date) -> None:
    """Run a new review of the week with a spinner and keep its outcome."""
    try:
        context = _context()
    except PromptMissingError as exc:
        _flash(review.RunResult(outcome="error", error_code=exc.code))
        return
    # A run spends model and embedding calls, so it counts against the session's limit, as a chat
    # question does (code review round 1); a refusal makes no call.
    refused = guard.session_limiter(st.session_state).try_acquire()
    if refused is not None:
        st.session_state[FLASH_KEY] = refused
        return
    try:
        with st.spinner(t("review.running")):
            result = review.start_review(context, user["id"], client_id, monday, lang())
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    if result.error_code and result.error_code.startswith("index."):
        # Open the index again next time, e.g. once the owner has rebuilt it.
        resources.index.clear()
        resources.keyword_index.clear()
    _flash(result)


def _decide(user: dict, row: dict, decision: str, final: dict | None = None) -> None:
    """Resume the waiting run with the coach's decision and keep its outcome."""
    context = review.ReviewContext(store_path=account.store_path())
    try:
        result = review.decide_review(
            context, user["id"], row["id"], row.get("thread_id") or "", decision, final
        )
    except accounts.StoreUnavailable:
        st.error(t("account.store_unavailable"), icon=":material/error:")
        return
    if result.outcome != "edit_invalid":
        st.session_state.pop(EDIT_KEY, None)
    _flash(result)


def _edit_key(row: dict, section: str, index: int, field: str) -> str:
    """Return the widget key of one text in the edit form."""
    return f"weekly_review_edit_{row['id']}_{section}_{index}_{field}"


def edited_text(draft: dict, values: dict) -> dict:
    """Return the draft with the coach's texts; an emptied text leaves its item out."""
    # Kind, evidence, the suggestion label and the source's range stay as drafted (the form shows
    # no field for them); the store keeps the result as the coach's final text.
    found = {name: [] for name in _FIELDS}
    for name in _FIELDS:
        for index, item in enumerate(draft.get(name, [])):
            text = values.get((name, index, "text"), item["text"]).strip()
            if not text:
                continue
            changed = {**item, "text": text}
            for field in ("direction", "population"):
                if (name, index, field) in values:
                    changed[field] = values[(name, index, field)].strip() or None
            found[name].append(changed)
    return found


def _edit_form(user: dict, row: dict) -> None:
    """Show the draft's texts in a form; Approve my edit sends it, Cancel closes the form."""
    draft = row["draft"]
    st.caption(t("review.edit_help"))
    with st.form(f"weekly_review_form_{row['id']}"):
        for name in _FIELDS:
            items = draft.get(name, [])
            if not items:
                continue
            st.markdown(f"**{t(f'review.{name}')}**")
            for index, item in enumerate(items):
                st.text_area(
                    t(f"review.kind.{item['kind']}") if name == "recommendations" else " ",
                    value=item["text"],
                    max_chars=config.REVIEW_TEXT_MAX_CHARS,
                    key=_edit_key(row, name, index, "text"),
                    label_visibility="visible" if name == "recommendations" else "collapsed",
                )
                if name == "recommendations" and item.get("kind") == "training":
                    for field in ("direction", "population"):
                        st.text_input(
                            t(f"review.{field}"),
                            value=item.get(field) or "",
                            max_chars=config.REVIEW_FIELD_MAX_CHARS,
                            key=_edit_key(row, name, index, field),
                        )
        save, cancel = st.columns(2)
        submitted = save.form_submit_button(t("review.save_edit"), type="primary")
        cancelled = cancel.form_submit_button(t("review.cancel_edit"))
    if cancelled:
        st.session_state.pop(EDIT_KEY, None)
        st.rerun()
    if submitted:
        values = {}
        for name in _FIELDS:
            for index in range(len(draft.get(name, []))):
                for field in ("text", "direction", "population"):
                    key = _edit_key(row, name, index, field)
                    if key in st.session_state:
                        values[(name, index, field)] = st.session_state[key]
        _decide(user, row, "edit", edited_text(draft, values))
        st.rerun()


def _pending(user: dict, row: dict) -> None:
    """Show a draft waiting for the coach, with Approve, Edit and Reject."""
    st.markdown(f"**{t('review.pending', week=row['period_start'])}**")
    if st.session_state.get(EDIT_KEY) == row["id"]:
        _edit_form(user, row)
        return
    show_text(row["draft"])
    approve, edit, reject = st.columns(3)
    if approve.button(
        t("review.approve"), type="primary", key=f"weekly_review_approve_{row['id']}"
    ):
        _decide(user, row, "approve")
        st.rerun()
    if edit.button(t("review.edit"), key=f"weekly_review_edit_{row['id']}"):
        st.session_state[EDIT_KEY] = row["id"]
        st.rerun()
    if reject.button(t("review.reject"), key=f"weekly_review_reject_{row['id']}"):
        _decide(user, row, "reject")
        st.rerun()


def coach_section(user: dict, client_id: str, monday: date, week: dashboard.DashboardWeek) -> None:
    """Show the weekly review of the picked client's week: start it, decide it, or read it."""
    st.subheader(t("review.section"))
    st.caption(f":material/smart_toy: {t('review.intro')}")
    _show_flash()
    if week.reviews is None:
        st.caption(t("review.needs_nutrition"))
        return
    this_week = [row for row in week.reviews if row["period_start"] == monday.isoformat()]
    by_status = {row["status"]: row for row in this_week}
    if "APPROVED" in by_status:
        row = by_status["APPROVED"]
        st.markdown(f"**{tables.review_heading(row, lang())}**")
        st.caption(f":material/smart_toy: {tables.review_label(row, lang())}")
        show_text(row["final"] or {})
        return
    if "PENDING_REVIEW" in by_status:
        _pending(user, by_status["PENDING_REVIEW"])
        return
    if "REJECTED" in by_status:
        st.caption(t("review.rejected_note"))
    if monday + timedelta(days=6) >= accounts.today():
        st.caption(t("review.not_finished"))
        return
    if st.button(t("review.start"), type="primary", key=START_KEY):
        _start(user, client_id, monday)
        st.rerun()
