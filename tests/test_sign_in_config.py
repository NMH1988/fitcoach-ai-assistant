"""Tests for the sign-in and demo settings read from secrets.toml (T9.5, D14, D18)."""

import os
import tomllib
from pathlib import Path

import pytest

from src import config

EXAMPLE = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml.example"
REAL_SECRET = "a" * config.USER_KEY_SECRET_MIN_CHARS
REAL_COOKIE = "b" * 40
AUTH = (
    "[auth]\n"
    'redirect_uri = "http://localhost:8501/oauth2callback"\n'
    f'cookie_secret = "{REAL_COOKIE}"\n'
    'client_id = "test-client.apps.googleusercontent.com"\n'
    'client_secret = "test-not-a-real-secret"\n'
    'server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"\n'
)


def _account(secret: str) -> str:
    """Return the [account] section of secrets.toml with this user key secret."""
    return f'[account]\nuser_key_secret = "{secret}"\n'


def _uncommented_example() -> str:
    """Return the example secrets file with its commented-out sections switched on."""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    on = [
        line[2:] if line.startswith("# [") or line.startswith("# ") and " = " in line else line
        for line in lines
    ]
    return "\n".join(line for line in on if not line.startswith("DEMO_MODE")) + "\n"


@pytest.fixture(autouse=True)
def no_demo_env(monkeypatch):
    """Remove DEMO_MODE from the environment before and after, so each test sees only its own."""
    monkeypatch.delenv(config.DEMO_MODE_NAME, raising=False)
    yield
    # Streamlit copies root-level string secrets (DEMO_MODE = "1") into os.environ.
    os.environ.pop(config.DEMO_MODE_NAME, None)


def test_the_example_as_copied_has_no_auth_section(secrets_from_file):
    """A copy of the example runs for guests: its [auth] and [account] are commented out."""
    secrets_from_file(EXAMPLE.read_text(encoding="utf-8"))
    assert not config.auth_configured()
    assert not config.sign_in_ready()


def test_the_example_holds_every_auth_placeholder():
    """Uncommented, the example has the [auth] keys st.login needs, with placeholders only."""
    parsed = tomllib.loads(_uncommented_example())
    assert set(parsed["auth"]) == {
        "redirect_uri",
        "cookie_secret",
        "client_id",
        "client_secret",
        "server_metadata_url",
    }
    assert parsed["auth"]["redirect_uri"] == "http://localhost:8501/oauth2callback"
    assert parsed["auth"]["cookie_secret"] == config.COOKIE_SECRET_PLACEHOLDER
    assert parsed["account"]["user_key_secret"] == config.USER_KEY_SECRET_PLACEHOLDER


def test_the_uncommented_example_is_not_ready(secrets_from_file):
    """The example's placeholders never let anyone sign in: the section is there, sign-in is not."""
    secrets_from_file(_uncommented_example())
    assert config.auth_configured()
    assert not config.sign_in_ready()


def test_sign_in_is_ready_with_real_secrets(secrets_from_file):
    """An [auth] section with a real cookie secret and a long user key secret offers sign-in."""
    secrets_from_file(AUTH + _account(REAL_SECRET))
    assert config.sign_in_ready()
    assert config.user_key_secret() == REAL_SECRET


@pytest.mark.parametrize(
    "account",
    [
        "",
        _account(""),
        _account("x" * (config.USER_KEY_SECRET_MIN_CHARS - 1)),
        _account(config.USER_KEY_SECRET_PLACEHOLDER),
        'user_key_secret = "' + REAL_SECRET + '"\n',  # at the root, not in [account]
    ],
)
def test_a_missing_short_or_placeholder_user_key_secret_is_refused(secrets_from_file, account):
    """Without a usable user key secret there is no sign-in, even with an [auth] section."""
    secrets_from_file(account + AUTH)
    assert config.user_key_secret() is None
    assert not config.sign_in_ready()


def test_the_cookie_placeholder_is_refused(secrets_from_file):
    """The example's cookie secret is public, so sign-in stays off while it is used."""
    secrets_from_file(
        AUTH.replace(REAL_COOKIE, config.COOKIE_SECRET_PLACEHOLDER) + _account(REAL_SECRET)
    )
    assert not config.sign_in_ready()


def test_no_secrets_file_means_no_sign_in(monkeypatch):
    """With no secrets.toml at all, the settings read as off instead of failing."""

    class NoFile:
        """Mimics st.secrets when no secrets.toml exists."""

        def get(self, key, default=None):
            """Fail like Streamlit does when there is no secrets file."""
            raise FileNotFoundError("No secrets found.")

    monkeypatch.setattr(config.st, "secrets", NoFile())
    assert not config.auth_configured()
    assert config.user_key_secret() is None
    assert not config.sign_in_ready()
    assert not config.demo_mode()


def test_demo_mode_is_off_by_default(secrets_from_file):
    """Demo mode needs DEMO_MODE set; nothing set means off."""
    secrets_from_file('OPENROUTER_API_KEY = "sk-test-not-a-real-key"\n')
    assert not config.demo_mode()


@pytest.mark.parametrize("value", ["true", '"1"', '"yes"', '"ON"'])
def test_demo_mode_from_secrets(secrets_from_file, value):
    """DEMO_MODE in secrets.toml turns demo mode on (a TOML true or a yes-like text)."""
    secrets_from_file(f"DEMO_MODE = {value}\n")
    assert config.demo_mode()


@pytest.mark.parametrize("value", ["false", '"0"', '"no"', '""'])
def test_demo_mode_stays_off_for_other_values(secrets_from_file, value):
    """Only a yes-like value turns demo mode on."""
    secrets_from_file(f"DEMO_MODE = {value}\n")
    assert not config.demo_mode()


def test_demo_mode_from_the_environment(secrets_from_file, monkeypatch):
    """DEMO_MODE in the environment turns demo mode on when secrets.toml does not set it."""
    secrets_from_file('OPENROUTER_API_KEY = "sk-test-not-a-real-key"\n')
    monkeypatch.setenv(config.DEMO_MODE_NAME, "1")
    assert config.demo_mode()


def test_demo_mode_is_ignored_when_auth_exists(secrets_from_file, monkeypatch):
    """With an [auth] section demo mode is off, whatever DEMO_MODE says (D18)."""
    secrets_from_file("DEMO_MODE = true\n" + AUTH + _account(REAL_SECRET))
    monkeypatch.setenv(config.DEMO_MODE_NAME, "1")
    assert not config.demo_mode()
