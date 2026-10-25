"""Shared pytest fixtures."""

import os

import pytest
from streamlit import config as st_config
from streamlit.runtime.secrets import Secrets

from src import chat, config, i18n, usage
from tests.fakes import TEST_LANGUAGE_PARTS


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


@pytest.fixture(autouse=True)
def turn_codes_are_keys(monkeypatch, request):
    """Check every turn's fixed message (T7.1), and fail a hidden unexpected error (T1.8)."""
    run_turn = chat.run_turn
    expects_turn_error = request.node.get_closest_marker("turn_error") is not None

    def checked(*args, **kwargs):
        """Run the turn; unless the model answered, its message must fill in both languages."""
        result = run_turn(*args, **kwargs)
        # The catch-all would turn a fake's AssertionError or a regression into a plain error
        # result; only the tests marked turn_error expect it.
        if result.code == "turn.error" and not expects_turn_error:
            pytest.fail("The turn ended in turn.error: an unexpected error was caught (T1.8).")
        if result.kind != "answer":
            # A missing key or a {placeholder} the params do not fill would break every later
            # run of the session, as the chat history is drawn again each time.
            for lang in i18n.LANGUAGES:
                assert i18n.t(result.code, lang, **result.params), (result.kind, result.code)
        return result

    monkeypatch.setattr(chat, "run_turn", checked)


@pytest.fixture(autouse=True)
def language_part_files(tmp_path_factory, monkeypatch):
    """Point the answer's language parts at test files, so no test depends on the owner's text."""
    # A folder of their own: some tests check that their tmp_path stays empty.
    folder = tmp_path_factory.mktemp("language_parts")
    paths = {}
    for lang, text in TEST_LANGUAGE_PARTS.items():
        paths[lang] = folder / f"answer_language_{lang}.md"
        paths[lang].write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_LANGUAGE_PROMPT_PATHS", paths)
    return paths
