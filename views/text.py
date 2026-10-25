"""The session's language and the helpers that show texts and numbers in it."""

from collections.abc import Callable

import streamlit as st

from src import i18n


def lang() -> i18n.Language:
    """Return the session's UI language."""
    return st.session_state[i18n.SESSION_KEY]


def t(key: str, **params: object) -> str:
    """Return a UI text in the session's language."""
    return i18n.t(key, lang(), **params)


def n(value: float) -> str:
    """Show a number with thousands marks in the session's language ("2,500" or "2.500")."""
    return i18n.number(value, lang())


def plain(value: float) -> str:
    """Show a number with no thousands marks in the session's language ("1.5" or "1,5")."""
    return i18n.plain(value, lang())


def percent(value: int) -> str:
    """Show a percentage as the language writes it: "20%" or "20 %"."""
    return i18n.percent(value, lang())


def label_of(prefix: str) -> Callable[[str], str]:
    """Return a widget's format_func: a value's label under a key prefix, in today's language."""
    # The language is bound now: Streamlit (and AppTest) may call format_func outside the run.
    current = lang()
    return lambda value: i18n.t(f"{prefix}.{value}", current)
