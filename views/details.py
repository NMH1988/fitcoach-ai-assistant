"""The Details tab and the sidebar card: how the last answer was found, and what it cost (AC-3)."""

import streamlit as st

from src import chat, config, usage
from views import tables, usage_view
from views.text import lang, t


def last_searched() -> dict | None:
    """Return the message of the latest turn that reached the search, or None before any."""
    for message in reversed(st.session_state["messages"]):
        if message["role"] == "assistant" and message["result"].search is not None:
            return message
    return None


def filter_badges(details: chat.SearchDetails) -> None:
    """Show the filters the rewrite step chose as badges, or say there were none."""
    if not details.has_filters:
        st.badge(t("filter.none"), icon=":material/filter_alt_off:", color="gray")
        return
    with st.container(horizontal=True, gap="small"):
        for topic in details.topics:
            st.badge(tables.topic_label(topic, lang()), icon=":material/sell:", color="blue")
        if details.min_year is not None:
            year = t("filter.from_year", year=str(details.min_year))
            st.badge(year, icon=":material/calendar_month:", color="blue")
        if details.evidence_tier is not None:
            tier = details.evidence_tier
            label = (
                t(f"tier_filter.{tier}")
                if tier in config.EVIDENCE_TIERS
                else tables.tier_label(tier, lang())
            )
            st.badge(label, icon=":material/verified:", color="blue")


def routing_badges(result: chat.TurnResult) -> None:
    """Show whether the rewrite step expected a tool, and whether <profile> was sent (T3.5)."""
    if result.search is None or result.search.needs_tool is None:
        # No usable plan: the note from search_notes() says what happened instead.
        return
    st.markdown(f"**{t('routing.title')}**")
    with st.container(horizontal=True, gap="small"):
        if result.search.needs_tool:
            st.badge(t("routing.tool"), icon=":material/build:", color="blue")
        else:
            st.badge(t("routing.no_tool"), icon=":material/build:", color="gray")
        # What the answer model really got: no block when no answer call was made, even if
        # the plan asked for one. Tool results can still name some values (docs/SECURITY.md).
        if result.profile_sent:
            st.badge(t("routing.profile_sent"), icon=":material/person:", color="blue")
        else:
            st.badge(t("routing.profile_not_sent"), icon=":material/person_off:", color="gray")


def search_notes(details: chat.SearchDetails) -> None:
    """Say when the rewrite step gave nothing usable or the filters were dropped."""
    if details.fell_back:
        st.caption(f":material/info: {t('search.fell_back')}")
    if details.filter_dropped:
        st.caption(f":material/filter_alt_off: {t('search.filter_dropped')}")


def tab() -> None:
    """Show how the last answer was found: what was searched and the filters used (AC-3)."""
    message = last_searched()
    st.subheader(f":material/manage_search: {t('details.title')}")
    if message is None:
        st.caption(t("details.empty"))
        return
    details = message["result"].search
    st.markdown(f"**{t('details.searched_for')}**")
    # The question is the user's text and the rewrites the model's: both shown escaped.
    lines = [f"1. {tables.one_line(details.question)} *{t('details.your_question')}*"]
    lines += [
        f"{number}. {tables.one_line(rewrite)}"
        for number, rewrite in enumerate(details.rewrites, 2)
    ]
    st.markdown("\n".join(lines))
    st.markdown(f"**{t('details.filters')}**")
    filter_badges(details)
    routing_badges(message["result"])
    search_notes(details)
    usage_view.section(message.get("usage"))


def last_answer_card() -> None:
    """Show a short summary of how the last answer was found, and its cost, in the sidebar."""
    current = lang()
    message = last_searched()
    if message is None:
        # No turn has searched yet, but one may have spent tokens before failing (AC-10).
        session = usage_view.session_usage()
        if session.tokens:
            line = t("usage.session", usage=tables.dollars(usage.format_session(session, current)))
            st.caption(f"{usage_view.USAGE_ICON} {line}")
        return
    details = message["result"].search
    with st.container(border=True):
        st.markdown(f"**:material/manage_search: {t('card.last_answer')}**")
        # Names the question, as a rejected or failed turn leaves an earlier search here.
        question = tables.one_line(details.question)
        if len(question) > config.CARD_QUESTION_CHARS:
            question = question[: config.CARD_QUESTION_CHARS].rstrip("\\ ") + "…"
        st.caption(t("card.for", question=question))
        if details.rewrites:
            rewrites = len(details.rewrites)
            key = "card.searched_one" if rewrites == 1 else "card.searched_many"
            st.caption(t(key, queries=len(details.queries), rewrites=rewrites))
        else:
            st.caption(t("card.question_only"))
        filter_badges(details)
        if details.filter_dropped:
            st.caption(t("card.filters_dropped"))
        turn_usage = message.get("usage")
        if turn_usage is not None and turn_usage.calls:
            this_answer = tables.dollars(usage.format_turn(turn_usage, current))
            st.caption(f"{usage_view.USAGE_ICON} {t('usage.this_answer', usage=this_answer)}")
        session = tables.dollars(usage.format_session(usage_view.session_usage(), current))
        st.caption(f"{usage_view.USAGE_ICON} {t('usage.session', usage=session)}")
        st.caption(t("card.more"))
