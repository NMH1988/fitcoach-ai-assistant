"""Shared pytest fixtures."""

import logging
import os
import uuid

import pytest
import streamlit as st
from streamlit import config as st_config
from streamlit.runtime.secrets import Secrets

from src import chat, config, i18n, observability, tracing, usage
from src.store import db
from tests.fakes import TEST_COACH_PART, TEST_LANGUAGE_PARTS


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


# LangSmith's own flags: tracing must stay off in tests even if the machine sets them (T9.8).
LANGSMITH_ENV_FLAGS = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
)


@pytest.fixture(autouse=True)
def tracing_is_off(monkeypatch):
    """Keep LangSmith tracing off in every test, whatever the owner's secrets or env say (T9.8)."""
    # The tracing tests set the flag again and use a fake LangSmith session (tests/test_tracing.py).
    monkeypatch.setattr(config, "tracing_requested", lambda: False)
    for name in (*LANGSMITH_ENV_FLAGS, config.LANGSMITH_API_KEY_NAME, config.TRACING_FLAG_NAME):
        monkeypatch.delenv(name, raising=False)
    tracing.configure_tracing()
    yield
    # A test may have set the flag again on this same monkeypatch, which is undone only after
    # this teardown: turn it off first, so tracing never stays on into the next test.
    monkeypatch.setattr(config, "tracing_requested", lambda: False)
    tracing.configure_tracing()


@pytest.fixture(autouse=True)
def app_logger_is_reset():
    """Undo configure_logging() after every test, so its handler never reaches caplog tests."""
    yield
    logger = logging.getLogger(observability.LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    # configure_logging() also keeps these libraries' loggers at WARNING.
    for name in ("openai", "httpx", "httpcore", "langsmith"):
        logging.getLogger(name).setLevel(logging.NOTSET)


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
    """Point the answer's language and coach parts at test files, not the owner's text."""
    # A folder of their own: some tests check that their tmp_path stays empty.
    folder = tmp_path_factory.mktemp("language_parts")
    paths = {}
    for lang, text in TEST_LANGUAGE_PARTS.items():
        paths[lang] = folder / f"answer_language_{lang}.md"
        paths[lang].write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_LANGUAGE_PROMPT_PATHS", paths)
    coach_part = folder / "answer_coach.md"
    coach_part.write_text(TEST_COACH_PART, encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_COACH_PROMPT_PATH", coach_part)
    return paths


@pytest.fixture
def login_calls(monkeypatch):
    """Replace st.login and st.logout with recorders and return the list of calls (T9.5)."""
    made = []
    monkeypatch.setattr(st, "login", lambda *args: made.append("login"))
    monkeypatch.setattr(st, "logout", lambda: made.append("logout"))
    return made


@pytest.fixture(scope="session")
def store_root(tmp_path_factory):
    """Return one temporary folder for all the tests' store files."""
    return tmp_path_factory.mktemp("store")


@pytest.fixture(autouse=True)
def store_file_is_temporary(store_root, monkeypatch):
    """Point the store at a fresh temporary file, so no test writes data/store/ (T9.6)."""
    # Only the path is set; the folder is made when a test opens the store.
    folder = store_root / uuid.uuid4().hex
    monkeypatch.setattr(config, "STORE_DIR", folder)
    monkeypatch.setattr(config, "STORE_PATH", folder / "test.sqlite3")
    return config.STORE_PATH


@pytest.fixture
def store_conn():
    """Yield an open, migrated connection to the test's own store file."""
    with db.connect() as conn:
        yield conn
