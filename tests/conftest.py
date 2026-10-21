"""Shared pytest fixtures."""

import os

import pytest
from streamlit import config as st_config
from streamlit.runtime.secrets import Secrets

from src import config, usage


@pytest.fixture
def no_env_key(monkeypatch):
    """Remove the API key env var so tests only see the key they set up."""
    monkeypatch.delenv(config.API_KEY_NAME, raising=False)


@pytest.fixture
def secrets_from_file(monkeypatch, tmp_path):
    """Return a helper that points a real st.secrets at a secrets.toml with the given text."""
    original = st_config.get_option("secrets.files")
    # Streamlit copies parsed string secrets into os.environ, so restore the key afterwards.
    saved_env = os.environ.get(config.API_KEY_NAME)

    def use(text):
        """Write `text` as secrets.toml and install a fresh Secrets object that reads it."""
        path = tmp_path / "secrets.toml"
        path.write_text(text, encoding="utf-8")
        st_config.set_option("secrets.files", [str(path)])
        monkeypatch.setattr(config.st, "secrets", Secrets())

    yield use
    st_config.set_option("secrets.files", original)
    if saved_env is None:
        os.environ.pop(config.API_KEY_NAME, None)
    else:
        os.environ[config.API_KEY_NAME] = saved_env


def _no_price_network():
    """Fail as an offline price read does, so no test reaches OpenRouter."""
    raise usage.PriceError("no network in tests")


@pytest.fixture(autouse=True)
def no_price_fetch(monkeypatch):
    """Give every test a fresh price cache that never goes online (T5.1); prices are unknown."""
    cache = usage.PriceCache(_no_price_network)
    monkeypatch.setattr(usage, "PRICES", cache)
    return cache
