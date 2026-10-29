"""The Details tab and the sidebar card: how the last answer was found, and what it cost (AC-3)."""

from collections.abc import Sequence

import streamlit as st

from src import chat, config, usage
from views import tables, usage_view
from views.text import lang, t


def last_searched() -> tuple[str, dict] | None:
    """Return the question and message of the latest turn that reached the model, or None."""
    # searches is () when the model searched nothing and None when the turn ended before it.
    messages = st.session_state["messages"]
    for number in range(len(messages) - 1, -1, -1):
        message = messages[number]
        if message["role"] == "assistant" and message["result"].searches is not None:
            asked = messages[number - 1] if number > 0 else {}
            return asked.get("text", ""), message
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


def merged_filters(searches: Sequence[chat.SearchDetails]) -> chat.SearchDetails:
    """Return one set of filters for the card: each filter the turn's searches set, once."""
    # The card names no search, so a badge per search would repeat filters and show "No filters"
    # beside a search that set some; the Details tab shows each search's own.
    tiers = {details.evidence_tier for details in searches} - {None}
    years = [details.min_year for details in searches if details.min_year is not None]
    return chat.SearchDetails(
        query="",
        topics=tuple(dict.fromkeys(topic for details in searches for topic in details.topics)),
        min_year=min(years) if years else None,
        evidence_tier=tiers.pop() if len(tiers) == 1 else None,
    )


def search_notes(details: chat.SearchDetails) -> None:
    """Say when the rewrite step gave nothing usable or the filters were dropped."""
    if details.fell_back:
        st.caption(f":material/info: {t('search.fell_back')}")
    if details.filter_dropped:
        st.caption(f":material/filter_alt_off: {t('search.filter_dropped')}")


def found_line(details: chat.SearchDetails) -> str:
    """Return how many passages a search found and their [S#] labels, or that it found none."""
    if not details.labels:
        return t("details.found_none")
    labels = ", ".join(f"S{number}" for number in details.labels)
    if len(details.labels) == 1:
        return t("details.found_one", labels=labels)
    return t("details.found", count=len(details.labels), labels=labels)


def search_section(number: int, details: chat.SearchDetails) -> None:
    """Show one search: its query and rewrites, the filters, its notes and what it found."""
    st.markdown(f"**{t('details.search', number=number)}** · {t('details.searched_for')}")
    # The query and the rewrites are the model's text: shown escaped, on one line each.
    lines = [f"1. {tables.one_line(details.query)} *{t('details.model_query')}*"]
    lines += [
        f"{line}. {tables.one_line(rewrite)}" for line, rewrite in enumerate(details.rewrites, 2)
    ]
    st.markdown("\n".join(lines))
    st.markdown(f"**{t('details.filters')}**")
    filter_badges(details)
    search_notes(details)
    st.caption(found_line(details))


def tab() -> None:
    """Show how the last answer was found: each search the model ran, or that it ran none (AC-3)."""
    found = last_searched()
    st.subheader(f":material/manage_search: {t('details.title')}")
    if found is None:
        st.caption(t("details.empty"))
        return
    question, message = found
    st.caption(t("details.question", question=tables.one_line(question)))
    searches = message["result"].searches
    if not searches:
        st.caption(f":material/search_off: {t('details.no_search')}")
    for number, details in enumerate(searches, start=1):
        search_section(number, details)
    usage_view.section(message.get("usage"))


def last_answer_card() -> None:
    """Show a short summary of how the last answer was found, and its cost, in the sidebar."""
    current = lang()
    found = last_searched()
    if found is None:
        # No turn has reached the model yet, but one may have spent tokens before failing (AC-10).
        session = usage_view.session_usage()
        if session.tokens:
            line = t("usage.session", usage=tables.dollars(usage.format_session(session, current)))
            st.caption(f"{usage_view.USAGE_ICON} {line}")
        return
    question, message = found
    searches = message["result"].searches
    with st.container(border=True):
        st.markdown(f"**:material/manage_search: {t('card.last_answer')}**")
        # Names the question, as a rejected or failed turn leaves an earlier answer here.
        question = tables.one_line(question)
        if len(question) > config.CARD_QUESTION_CHARS:
            question = question[: config.CARD_QUESTION_CHARS].rstrip("\\ ") + "…"
        st.caption(t("card.for", question=question))
        queries = sum(len(details.queries) for details in searches)
        if not searches:
            st.caption(t("card.no_search"))
        elif len(searches) == 1:
            st.caption(t("card.searches_one", queries=queries))
        else:
            st.caption(t("card.searches_many", count=len(searches), queries=queries))
        if searches:
            filter_badges(merged_filters(searches))
        if any(details.filter_dropped for details in searches):
            st.caption(t("card.filters_dropped"))
        turn_usage = message.get("usage")
        if turn_usage is not None and turn_usage.calls:
            this_answer = tables.dollars(usage.format_turn(turn_usage, current))
            st.caption(f"{usage_view.USAGE_ICON} {t('usage.this_answer', usage=this_answer)}")
        session = tables.dollars(usage.format_session(usage_view.session_usage(), current))
        st.caption(f"{usage_view.USAGE_ICON} {t('usage.session', usage=session)}")
        st.caption(t("card.more"))
