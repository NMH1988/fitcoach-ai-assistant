"""The page header (title, disclaimer badge and the disclaimer box) and the page's main column."""

import streamlit as st

from src import config
from views.text import t


def main_column():
    """Return the middle column of the wide layout, where every page's content sits."""
    _, main, _ = st.columns(config.PAGE_COLUMN_WEIGHTS)
    return main


def show() -> None:
    """Show the title, the badge, the intro and the disclaimer."""
    # The language control moved to the sidebar in T9.23; the row keeps only the badge.
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"
    ):
        st.title(t("app.title"))
        st.badge(
            t("app.not_medical_advice"),
            icon=":material/info:",
            color="orange",
            help=t("app.disclaimer"),
        )
    st.markdown(t("app.intro"))
    # Shown on every page state (AC-12), large enough to notice (owner's request, 2026-10-20).
    st.warning(f"**{t('app.not_medical_advice')}.** {t('app.disclaimer')}", icon=":material/info:")
