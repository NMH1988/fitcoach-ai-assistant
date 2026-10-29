"""The "About the answers" dialog: what the answers are based on, and the credits (T3.9)."""

import streamlit as st

from src import chat, config
from views import resources
from views.text import t


def content(manifest) -> None:
    """Say what the answers are based on and credit every source (the About dialog's body)."""
    summary = chat.knowledge_base_summary(manifest)
    articles = t(
        "about.articles",
        articles=summary.articles,
        stands=summary.position_stands,
        reviews=summary.reviews,
        licenses=t("about.and").join(summary.licenses),
    )
    models = t(
        "about.models",
        rewrite_model=config.QUERY_TRANSLATION_MODEL,
        answer_model=config.DEFAULT_ANSWER_MODEL,
    )
    # What the answers cover and that a model writes them (PRD guardrails, AC-41; T9.20).
    lines = [articles, t("about.scope"), t("about.method"), models, t("about.ai")]
    st.markdown("\n".join(f"- {line}" for line in lines))
    # Credits every source (copyright policy rule 6): authors, title, journal, licence, link,
    # and the change made with the no-endorsement note, as in ATTRIBUTION.md. The credits
    # themselves stay as the articles give them.
    st.markdown(f"**:material/license: {t('about.credits')}**")
    article = t("about.article")
    for source in manifest.values():
        st.markdown(
            f"**{source.id}.** {chat.escape_markdown(chat.format_authors(source.authors))}. "
            f"{chat.escape_markdown(source.title)} ({source.year}). "
            f"{chat.escape_markdown(source.journal)}. "
            f"[{source.license}]({chat.markdown_url(source.license_url)}) · "
            f"[{article}]({chat.markdown_url(source.url)})"
        )
    st.caption(f"{t('about.changes')} {t('about.full_credits')}")


@st.fragment
def about_button(manifest) -> None:
    """Draw the button that opens the About dialog; a press reruns only this fragment."""
    # A fragment, so a press while an answer streams does not rerun the script and stop that
    # turn: Streamlit runs the fragment once the turn ends, and the dialog opens then (T3.9).
    opened = st.button(
        t("about.title"), icon=":material/menu_book:", width="stretch", key="about_open"
    )
    # Streamlit allows one dialog per run: with the profile form open, a press changes nothing.
    if opened and not st.session_state.get("profile_form_open"):
        # Built in the run of the press, so the dialog's title is in the language chosen now.
        st.dialog(t("about.title"), width="large")(content)(manifest)


def sidebar_button() -> None:
    """Put a button in the sidebar that opens the About dialog."""
    manifest = resources.manifest()
    if not manifest:
        return
    st.divider()
    # A dialog, not an expander: the 20 credits are long and the sidebar is narrow (T3.9). The
    # content is static, so it needs no session state to stay open; a click draws it in that run.
    about_button(manifest)
