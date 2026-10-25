"""Tokens and cost of the turns, shown under an answer, in the Details tab and the sidebar."""

import streamlit as st

from src import chat, usage
from views import tables
from views.text import lang, t

USAGE_ICON = ":material/data_usage:"


def price(result: chat.TurnResult) -> usage.TurnUsage:
    """Price a turn's calls with OpenRouter's prices; a turn with no call needs no prices."""
    return usage.price_turn(result.usage, usage.PRICES.get() if result.usage else None)


def caption(turn_usage: usage.TurnUsage | None) -> None:
    """Show a turn's tokens and cost under its answer, if it made any model call (AC-10)."""
    if turn_usage is not None and turn_usage.calls:
        st.caption(f"{USAGE_ICON} {tables.dollars(usage.format_turn(turn_usage, lang()))}")


def session_usage() -> usage.SessionUsage:
    """Add up the tokens and the known cost of every turn of the session (AC-10)."""
    turns = [m["usage"] for m in st.session_state["messages"] if m.get("usage") is not None]
    return usage.session_usage(turns)


def section(turn_usage: usage.TurnUsage | None) -> None:
    """Show the tokens and cost of each call of the last answer, and the session totals."""
    current = lang()
    st.subheader(f"{USAGE_ICON} {t('usage.title')}")
    if turn_usage is not None and turn_usage.calls:
        st.dataframe(tables.usage_rows(turn_usage, current), hide_index=True)
        this_answer = tables.dollars(usage.format_turn(turn_usage, current))
        st.markdown(tables.bold_label(t("usage.this_answer", usage=this_answer)))
    else:
        st.caption(t("usage.no_calls"))
    session = tables.dollars(usage.format_session(session_usage(), current))
    st.markdown(tables.bold_label(t("usage.this_session", usage=session)))
    st.caption(t("usage.explain"))
