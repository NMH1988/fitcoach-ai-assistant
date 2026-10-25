"""The cited articles shown under an answer: one card per source."""

import streamlit as st

from src import chat
from views import tables
from views.text import lang, t

TIER_COLORS = {1: "green", 2: "violet"}


def card(source: chat.SourceCard) -> None:
    """Show one cited article: title, authors, tier, journal, year, licence and link (AC-1)."""
    with st.container(border=True):
        # Titles, journals, authors and licence names stay as the articles give them (English).
        st.markdown(f"**{chat.escape_markdown(source.title)}**")
        if source.authors:
            # Credits the authors on the card itself (CC BY; copyright policy rule 6).
            st.caption(chat.escape_markdown(chat.format_authors(source.authors)))
        st.badge(
            tables.tier_label(source.evidence_tier, lang()),
            color=TIER_COLORS.get(source.evidence_tier, "gray"),
        )
        meta = [chat.escape_markdown(source.journal)] if source.journal else []
        meta += [
            str(source.year),
            f"[{source.license}]({chat.markdown_url(source.license_url)})",
            t("card.cited_as", labels=", ".join(source.labels)),
        ]
        st.caption(" · ".join(meta))
        open_article = t("card.open_article")
        st.markdown(f"[:material/open_in_new: {open_article}]({chat.markdown_url(source.url)})")
        for correction in source.corrections:
            relation = t(f"correction.{correction.relation}")
            st.caption(
                f":material/edit_note: {relation}: "
                f"[{chat.escape_markdown(correction.title)}]({chat.markdown_url(correction.url)})"
            )
