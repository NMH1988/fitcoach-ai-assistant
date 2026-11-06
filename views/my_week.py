"""A gymer's My week page (T9.15): their own week and the weekly reviews a coach approved.

Read-only (T9.24): the page has no chat and no control that edits, decides or deletes a review or
changes a target, whoever set it; only the week picker is a control. The week comes from
`dashboard.own_week()`, the same views as the coach's Client week, every scope. A review shows only
when the coach approved it (the store never gives a gymer a pending or rejected review, or the
model's draft), labelled as an AI draft the coach approved (AC-41); a former coach's approved
reviews show too, so no text says "your coach" (compliance run 1). Under each review, T9.25's
questions to the coach (views/questions.py): the thread, still readable once the relationship has
ended, and a box to ask while the coach may read the review.
"""

import streamlit as st

from src import account as accounts
from src import dashboard
from src.store import questions as store_questions
from src.store.access import NotFound
from views import account, header, questions, tables, week_view, weekly_review
from views.text import lang, t

URL_PATH = "my-week"
WEEK_KEY = "my_week_week"


def _reviews(
    user: dict, week: dashboard.DashboardWeek, rows: list[dict], askable: frozenset[int]
) -> None:
    """Show the approved reviews, newest first, each with its week, the AI label and its thread."""
    st.subheader(t("my_week.reviews"))
    if not week.reviews:
        st.caption(t("my_week.no_reviews"))
        return
    for review in sorted(week.reviews, key=lambda item: (item["period_start"], item["id"]))[::-1]:
        with st.container(border=True):
            st.markdown(f"**{tables.review_heading(review, lang())}**")
            st.caption(f":material/smart_toy: {tables.review_label(review, lang())}")
            weekly_review.show_text(review["final"] or {})
            st.divider()
            thread = [row for row in rows if row["review_id"] == review["id"]]
            questions.gymer_thread(user, review, thread, askable)


def page() -> None:
    """Show the My week page: the week picker, the week's views and the approved reviews."""
    with header.main_column():
        header.show()
        account.store_notice()
        user = account.current_user()
        if user is None or user["role"] != "gymer":
            return  # not registered for them (views/navigation.py); never reached
        st.subheader(t("page.my_week"))
        st.markdown(t("my_week.intro"))
        monday = week_view.week_picker(WEEK_KEY)
        try:
            with accounts.open_store(account.store_path()) as conn:
                week = dashboard.own_week(conn, user["id"], monday)
                rows = store_questions.list_questions(conn, user["id"], user["id"])
                askable = store_questions.askable_reviews(conn, user["id"])
        except accounts.StoreUnavailable:
            st.error(t("account.store_unavailable"), icon=":material/error:")
            return
        except NotFound:
            return  # the account was deleted in another tab: the next run shows the welcome page
        week_view.show(week, st.session_state["units"])
        st.divider()
        _reviews(user, week, rows, askable)
