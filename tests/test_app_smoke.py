"""Smoke tests: the app page loads and shows its title and disclaimer."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import chat, config
from src.rag.sources import ARTICLE_CHANGES_NOTE

APP = Path(__file__).resolve().parent.parent / "app.py"

# The page must load without any key, so CI never needs one.
pytestmark = pytest.mark.usefixtures("no_env_key")


def _run_app() -> AppTest:
    """Run app.py once with no API key and return the test handle."""
    at = AppTest.from_file(str(APP))
    # A non-empty secrets dict replaces any local secrets.toml, so no real key is read.
    at.secrets["UNRELATED"] = "x"
    at.run(timeout=30)
    return at


def test_app_renders_without_exception():
    """The page loads with no exception and no error message."""
    at = _run_app()
    assert not at.exception
    assert not at.error


def test_app_shows_title():
    """The page title is the app's name."""
    at = _run_app()
    assert at.title[0].value == config.APP_TITLE


def test_app_shows_disclaimer():
    """The 'Not medical advice' badge and the full disclaimer box are on the page (AC-12)."""
    at = _run_app()
    assert ":orange-badge[:material/info: Not medical advice]" in [m.value for m in at.markdown]
    assert [box.value for box in at.warning] == [f"**Not medical advice.** {config.DISCLAIMER}"]
    assert "not medical advice" in config.DISCLAIMER


def test_app_shows_the_four_tabs():
    """The page has the Ask, My targets, Food lookup and Details tabs (docs/UI_DESIGN.md)."""
    at = _run_app()
    assert [tab.label for tab in at.tabs] == [
        ":material/chat: **Ask**",
        ":material/target: **My targets**",
        ":material/search: **Food lookup**",
        ":material/list: **Details**",
    ]


def test_the_sidebar_says_what_the_answers_are_based_on():
    """The sidebar counts the articles by tier and credits each source with its licence."""
    at = _run_app()
    summary = chat.knowledge_base_summary(chat.manifest_by_id())
    assert summary.articles == 20
    notes = [m.value for m in at.sidebar.markdown if "open-access research articles" in m.value]
    assert len(notes) == 1
    assert f"{summary.position_stands} ISSN position stands" in notes[0]
    assert config.DEFAULT_ANSWER_MODEL in notes[0]
    assert config.QUERY_TRANSLATION_MODEL in notes[0]
    [about] = [e for e in at.sidebar.expander if e.label == "About the answers"]
    assert "**:material/license: Sources and credits**" in [m.value for m in about.markdown]
    lines = [m.value for m in about.markdown if "creativecommons.org" in m.value]
    assert len(lines) == len(chat.manifest_by_id())
    assert all("creativecommons.org" in line and "https://doi.org/" in line for line in lines)
    first = next(iter(chat.manifest_by_id().values()))
    assert chat.escape_markdown(chat.format_authors(first.authors)) in lines[0]
    # The change made and the no-endorsement note, worded as in ATTRIBUTION.md (CC BY).
    [note] = [c.value for c in about.caption]
    assert note.startswith(ARTICLE_CHANGES_NOTE)
    assert ARTICLE_CHANGES_NOTE in Path(config.ATTRIBUTION_PATH).read_text(encoding="utf-8")
