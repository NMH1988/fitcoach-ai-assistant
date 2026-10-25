"""The page header: title, disclaimer badge, the EN | DE switch, and the disclaimer box."""

import streamlit as st

from src import i18n
from views.text import t


def language_control() -> None:
    """Show the EN | DE switch: an icon and a segmented control whose label is collapsed."""
    with st.container(horizontal=True, gap="small", vertical_alignment="center", width="content"):
        st.markdown(":material/translate:")
        # required=True: a click on the chosen language cannot deselect it to None. The value is
        # the session's language, written before the control is drawn (no default here).
        st.segmented_control(
            t("language.label"),
            i18n.LANGUAGES,
            format_func=i18n.LANGUAGE_LABELS.get,
            required=True,
            key=i18n.SESSION_KEY,
            label_visibility="collapsed",
        )


def show() -> None:
    """Show the title, the badge, the language switch, the intro and the disclaimer."""
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"
    ):
        st.title(t("app.title"))
        with st.container(
            horizontal=True, gap="medium", vertical_alignment="center", width="content"
        ):
            st.badge(
                t("app.not_medical_advice"),
                icon=":material/info:",
                color="orange",
                help=t("app.disclaimer"),
            )
            language_control()
    st.markdown(t("app.intro"))
    # Shown on every page state (AC-12), large enough to notice (owner's request, 2026-10-20).
    st.warning(f"**{t('app.not_medical_advice')}.** {t('app.disclaimer')}", icon=":material/info:")
