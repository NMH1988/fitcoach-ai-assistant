"""The session summary download: a PDF built in memory only when clicked (T5.2, AC-9)."""

from datetime import date

import streamlit as st

from src import config, export_pdf
from views import resources
from views.text import lang, t


def summary_download() -> None:
    """Offer the session summary as a PDF, built in memory only when clicked (AC-9)."""
    # Drawn after the main area, so the turn that just ran is in it. The PDF is built from this
    # run's snapshot when the user clicks; Streamlit keeps the bytes in memory, never on disk. It
    # is in the language chosen now (T7.2), bound here: the click may build it outside the run.
    turns = export_pdf.session_turns(st.session_state["messages"])
    user = st.session_state.get("profile")
    system = st.session_state["units"]
    manifest = resources.manifest()
    current = lang()
    # One date for the file name and the PDF, even if the click comes after midnight.
    today = date.today()

    def build() -> bytes:
        """Build the PDF from this run's session, in this run's language."""
        return export_pdf.build_summary_pdf(turns, user, system, manifest, today, current)

    empty = user is None and not turns
    st.download_button(
        t("pdf.label"),
        data=build,
        file_name=config.PDF_FILE_NAME.format(date=today.isoformat()),
        mime="application/pdf",
        icon=":material/download:",
        # The download needs no rerun of the app.
        on_click="ignore",
        disabled=empty,
        help=t("pdf.empty_help") if empty else t("pdf.help"),
        key="summary_pdf",
        width="stretch",
    )
