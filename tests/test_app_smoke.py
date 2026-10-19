"""Smoke tests: the app page loads and shows its title and disclaimer."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config

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
    """The 'not medical advice' disclaimer is visible on the page."""
    at = _run_app()
    assert [box.value for box in at.info] == [config.DISCLAIMER]
    assert "not medical advice" in config.DISCLAIMER
