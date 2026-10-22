"""Smoke tests: the app page loads and shows its title and disclaimer."""

import ast
from pathlib import Path

import pytest
import streamlit as st
from streamlit.proto.Block_pb2 import Block
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


def _open_about() -> AppTest:
    """Run the app and press the sidebar's "About the answers" button."""
    at = _run_app()
    [button] = [b for b in at.sidebar.button if b.label == "About the answers"]
    return button.click().run(timeout=30)


def test_the_sidebar_has_a_button_and_no_credits_until_it_is_pressed():
    """The sidebar holds one "About the answers" button; no credits are drawn before a click."""
    at = _run_app()
    assert [b.label for b in at.sidebar.button if b.label == "About the answers"] == [
        "About the answers"
    ]
    assert not at.sidebar.expander
    assert not at.get("dialog")
    assert not [m for m in at.sidebar.markdown if "creativecommons.org" in m.value]
    [button] = [b for b in at.sidebar.button if b.label == "About the answers"]
    assert button.proto.icon == ":material/menu_book:"


def test_without_a_manifest_the_sidebar_has_no_about_button(monkeypatch):
    """With no approved sources there is nothing to credit, so no button is drawn."""
    monkeypatch.setattr(chat, "manifest_by_id", dict)
    st.cache_resource.clear()  # the app caches the manifest per process
    try:
        at = _run_app()
    finally:
        st.cache_resource.clear()  # so later tests read the real manifest again
    assert not at.exception
    assert not [b for b in at.sidebar.button if b.label == "About the answers"]


def test_the_about_button_does_nothing_while_the_profile_form_is_open():
    """With the profile form open, pressing About opens no second dialog (one per run)."""
    at = _run_app()
    [add] = [b for b in at.sidebar.button if b.label == "Add your details"]
    at = add.click().run(timeout=30)
    [about] = [b for b in at.sidebar.button if b.label == "About the answers"]
    at = about.click().run(timeout=30)
    assert not at.exception
    assert [d.proto.dialog.title for d in at.get("dialog")] == ["Your details"]


def _decorators(source: str, function: str) -> list[str]:
    """Return the decorators of a top-level function in this source, as written."""
    [node] = [
        n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == function
    ]
    return [ast.unparse(d) for d in node.decorator_list]


def test_the_about_button_is_a_fragment_so_a_press_does_not_stop_a_turn():
    """The button is drawn in an st.fragment: its press waits for a running turn, not stop it."""
    # AppTest neither shows fragments nor interrupts a run, so this reads the decorator. A press
    # outside a fragment reruns the script and stops an answer that is streaming (T3.9 review).
    assert _decorators(APP.read_text(encoding="utf-8"), "_about_button") == ["st.fragment"]


def test_the_about_dialog_says_what_the_answers_are_based_on():
    """The dialog counts the articles by tier and credits each source with its licence."""
    at = _open_about()
    assert not at.exception
    summary = chat.knowledge_base_summary(chat.manifest_by_id())
    assert summary.articles == 20
    [about] = at.get("dialog")
    assert about.proto.dialog.title == "About the answers"
    assert Block.Dialog.DialogWidth.Name(about.proto.dialog.width) == "LARGE"
    notes = [m.value for m in about.markdown if "open-access research articles" in m.value]
    assert len(notes) == 1
    assert f"{summary.position_stands} ISSN position stands" in notes[0]
    assert config.DEFAULT_ANSWER_MODEL in notes[0]
    assert config.QUERY_TRANSLATION_MODEL in notes[0]
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
