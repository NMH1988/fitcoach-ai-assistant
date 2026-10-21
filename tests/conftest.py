"""Shared pytest fixtures."""

import pytest

from src import usage
from src.config import API_KEY_NAME


@pytest.fixture
def no_env_key(monkeypatch):
    """Remove the API key env var so tests only see the key they set up."""
    monkeypatch.delenv(API_KEY_NAME, raising=False)


def _no_price_network():
    """Fail as an offline price read does, so no test reaches OpenRouter."""
    raise usage.PriceError("no network in tests")


@pytest.fixture(autouse=True)
def no_price_fetch(monkeypatch):
    """Give every test a fresh price cache that never goes online (T5.1); prices are unknown."""
    cache = usage.PriceCache(_no_price_network)
    monkeypatch.setattr(usage, "PRICES", cache)
    return cache
