"""The page header (title, disclaimer badge and the disclaimer box) and the page's main column."""

import streamlit as st

from src import config
from views.text import t

# The title's container: assets/app.css gives its h1 the size and gradient of the app's name
# (`.st-key-app_title h1`; the start page's since T9.5, every page's by the owner's choice).
TITLE_KEY = "app_title"


def main_column():
    """Return the middle column of the wide layout, where every page's content sits."""
    _, main, _ = st.columns(config.PAGE_COLUMN_WEIGHTS)
    return main


def show() -> None:
    """Show the title, the badge, the intro and the disclaimer."""
    # The title on a row of its own: at its larger size (T9.5) it would wrap mid-word beside the
    # badge in a narrow window. The language control moved to the sidebar in T9.23.
    with st.container(key=TITLE_KEY):
        st.title(t("app.title"), anchor=False)
    with st.container(horizontal=True):
        st.badge(
            t("app.not_medical_advice"),
            icon=":material/info:",
            color="orange",
            help=t("app.disclaimer"),
        )
    st.markdown(t("app.intro"))
    # Shown on every page state (AC-12), large enough to notice (owner's request, 2026-10-20).
    st.warning(f"**{t('app.not_medical_advice')}.** {t('app.disclaimer')}", icon=":material/info:")
