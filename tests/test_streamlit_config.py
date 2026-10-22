"""Tests for the server, telemetry and error settings in .streamlit/config.toml (T1.7)."""

import tomllib
from pathlib import Path

import pytest
from streamlit import config as streamlit_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".streamlit" / "config.toml"


def _config() -> dict:
    """Parse the app's Streamlit config file."""
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def _option_names(table: dict, prefix: str = "") -> list[str]:
    """Return every setting in a parsed TOML table as a dotted name, e.g. "server.address"."""
    names = []
    for key, value in table.items():
        name = f"{prefix}{key}"
        names.extend(_option_names(value, f"{name}.") if isinstance(value, dict) else [name])
    return names


def test_the_server_listens_on_localhost_only():
    """Streamlit binds localhost, not every interface, so nobody else on the network can connect."""
    assert _config()["server"]["address"] == "localhost"


def test_usage_statistics_are_off():
    """No page view sends usage events or the visitor's IP to Streamlit's metrics host."""
    assert _config()["browser"]["gatherUsageStats"] is False


def test_error_details_are_hidden():
    """An uncaught error shows no message, type or traceback in the browser."""
    assert _config()["client"]["showErrorDetails"] == "none"


def test_every_setting_is_an_option_streamlit_knows():
    """Each key of the file is a real Streamlit option, so a misspelt name cannot be ignored."""
    options = streamlit_config.get_config_options()
    unknown = [name for name in _option_names(_config()) if name not in options]
    assert not unknown


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("server.address", "localhost"),
        ("browser.gatherUsageStats", False),
        ("client.showErrorDetails", "none"),
    ],
)
def test_streamlit_reads_the_settings_from_the_file(monkeypatch, option, expected):
    """Streamlit itself loads the file from the repo root and gets each value, as the app does."""
    monkeypatch.chdir(ROOT)
    streamlit_config.get_config_options(force_reparse=True)
    try:
        assert streamlit_config.get_option(option) == expected
    finally:
        # Leave Streamlit's options as the other tests found them.
        streamlit_config.get_config_options(force_reparse=True)
