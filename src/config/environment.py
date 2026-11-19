"""The keys, sign-in, demo mode, logging and tracing settings, and the functions that read them.

These functions are the only code that reads `.streamlit/secrets.toml` or the environment.
"""

import os
from collections.abc import Mapping

import streamlit as st

# The level of the app's JSON log lines (src/observability.py, T8.2): INFO writes one line per chat
# turn, WARNING only the guard rejections, model errors and failed tool calls.
LOG_LEVEL = "INFO"

# Masked LangSmith tracing (T9.8, D19; src/tracing.py). Off unless both the app's own flag and the
# LangSmith key are set (secrets.toml or the environment); LangSmith's own LANGSMITH_TRACING flag
# is always ignored, as it would trace with no masking. The key follows the OpenRouter key's rules
# (.claude/rules/security-privacy.md): read only by get_langsmith_api_key(), never logged or shown.
LANGSMITH_API_KEY_NAME = "LANGSMITH_API_KEY"
TRACING_FLAG_NAME = "FITCOACH_TRACING"
TRACING_ON_VALUES = frozenset({"1", "true", "yes", "on"})
# The EU region (owner's choice, 2026-11-06): the LangSmith account is created there (O10).
LANGSMITH_ENDPOINT = "https://eu.api.smith.langchain.com"
LANGSMITH_PROJECT = "fitcoach-ai-assistant"
# Unmasked traces in demo mode only (T9.35, owner's request, 2026-11-13, to show a reviewer what a
# trace holds): on only with tracing on, demo mode on (synthetic users, no [auth]) and this flag;
# the runs go to a project of their own, which the owner deletes after the demo.
TRACING_DEMO_UNMASKED_FLAG_NAME = "FITCOACH_TRACING_DEMO_UNMASKED"
LANGSMITH_DEMO_PROJECT = "fitcoach-ai-assistant-demo"
# What a masked value or key becomes in a trace.
TRACE_MASK = "[masked]"
TRACE_MASKED_KEY = "[masked key {number}]"

# Sign-in (T9.5, D14): st.login with Google, configured by the [auth] section of secrets.toml. The
# user's ID is a keyed hash of the issuer and `sub`, with the secret in its own [account] section
# (a section, so Streamlit does not copy it into os.environ as it does root-level strings).
AUTH_SECTION = "auth"
ACCOUNT_SECTION = "account"
USER_KEY_SECRET_NAME = "user_key_secret"
USER_KEY_SECRET_MIN_CHARS = 32
# Streamlit signs the identity cookie with [auth] cookie_secret; a guessable one would let anyone
# forge a sign-in, so sign-in is not offered with a shorter one.
COOKIE_SECRET_MIN_CHARS = 32
# The placeholders in .streamlit/secrets.toml.example: a copied example is "not set up", so no
# one signs in with a secret that is public in the repo (tests/test_config.py reads the example).
USER_KEY_SECRET_PLACEHOLDER = "replace-with-a-long-random-secret-for-user-ids"
COOKIE_SECRET_PLACEHOLDER = "replace-with-a-long-random-secret-for-the-cookie"
# Demo mode (T9.5, D18): synthetic users on a temporary database, only when DEMO_MODE is set in
# secrets.toml or the environment and there is no [auth] section. Off by default.
DEMO_MODE_NAME = "DEMO_MODE"
DEMO_MODE_ON_VALUES = frozenset({"1", "true", "yes", "on"})
# The OpenRouter key (.claude/rules/security-privacy.md): read only by get_api_key().
API_KEY_NAME = "OPENROUTER_API_KEY"
# The USDA FoodData Central API key (T9.9): optional, read only by get_food_api_key().
FOOD_API_KEY_NAME = "USDA_FDC_API_KEY"
# The example secrets file's placeholder (.streamlit/secrets.toml.example) counts as no key.
FOOD_API_KEY_PLACEHOLDER = "your-fdc-api-key-here"


class MissingAPIKeyError(RuntimeError):
    """Raised when no OpenRouter API key is configured."""


class SecretsFileError(MissingAPIKeyError):
    """Raised when secrets.toml exists but cannot be parsed, and no env var is set."""


def get_api_key() -> str:
    """Return the OpenRouter key from `st.secrets`, falling back to the environment."""
    file_broken = False
    try:
        value = st.secrets.get(API_KEY_NAME)
    except FileNotFoundError as exc:
        value = None
        file_broken = _parse_failed(exc)
    secret = value.strip() if isinstance(value, str) else ""
    key = secret or os.environ.get(API_KEY_NAME, "").strip()
    if not key:
        if file_broken:
            # `from None` keeps the parser's message (it may quote file content) out of tracebacks.
            raise SecretsFileError(".streamlit/secrets.toml could not be parsed.") from None
        raise MissingAPIKeyError(f"{API_KEY_NAME} is not set.")
    return key


def get_food_api_key() -> str | None:
    """Return the USDA FoodData Central API key from st.secrets or the environment, or None."""
    # Optional (T9.9): without it the food tool uses the local table only. Same rules as the
    # OpenRouter key: never logged, shown, stored in the session or put in an error.
    value = _secret(FOOD_API_KEY_NAME)
    secret = value.strip() if isinstance(value, str) else ""
    key = secret or os.environ.get(FOOD_API_KEY_NAME, "").strip()
    # A key with a line break, another non-printable character or a non-ASCII one inside would
    # make http.client raise an error (one that quotes the header), so it is not used (compliance
    # run 1's question; code review round 2). api.data.gov keys are ASCII letters and digits.
    if not key or key == FOOD_API_KEY_PLACEHOLDER or not (key.isascii() and key.isprintable()):
        return None
    return key


def _secret(name: str) -> object:
    """Return a value of st.secrets, or None when it or the secrets file is missing or broken."""
    try:
        return st.secrets.get(name)
    except FileNotFoundError:  # no secrets.toml, or one that cannot be parsed
        return None


def _parse_failed(exc: FileNotFoundError) -> bool:
    """Return True if st.secrets' error means the file exists but cannot be parsed."""
    # Streamlit raises FileNotFoundError for a missing secrets.toml, and chains the TOML error as
    # the cause when the file exists but cannot be parsed.
    return exc.__cause__ is not None


def secrets_file_broken() -> bool:
    """Return True if secrets.toml exists but cannot be parsed (every secret then reads missing)."""
    try:
        st.secrets.get(API_KEY_NAME)
    except FileNotFoundError as exc:
        return _parse_failed(exc)
    return False


def auth_configured() -> bool:
    """Return True if secrets.toml has an [auth] section (sign-in with Google, T9.5)."""
    section = _secret(AUTH_SECTION)
    return isinstance(section, Mapping) and len(section) > 0


def user_key_secret() -> str | None:
    """Return the user ID's hash secret; None if missing, too short or the example's placeholder."""
    section = _secret(ACCOUNT_SECTION)
    value = section.get(USER_KEY_SECRET_NAME) if isinstance(section, Mapping) else None
    secret = value.strip() if isinstance(value, str) else ""
    if len(secret) < USER_KEY_SECRET_MIN_CHARS or secret == USER_KEY_SECRET_PLACEHOLDER:
        return None
    return secret


def sign_in_ready() -> bool:
    """Return True if sign-in can be offered: [auth] with a long, real cookie secret and the key."""
    if not auth_configured():
        return False
    value = _secret(AUTH_SECTION).get("cookie_secret")
    cookie = value.strip() if isinstance(value, str) else ""
    if len(cookie) < COOKIE_SECRET_MIN_CHARS or cookie == COOKIE_SECRET_PLACEHOLDER:
        return False
    return user_key_secret() is not None


def demo_mode() -> bool:
    """Return True if demo mode is on: DEMO_MODE set (secrets or environment) and no [auth]."""
    if auth_configured():
        return False
    value = _secret(DEMO_MODE_NAME)
    if value is None:
        value = os.environ.get(DEMO_MODE_NAME, "")
    return str(value).strip().lower() in DEMO_MODE_ON_VALUES


def get_langsmith_api_key() -> str | None:
    """Return the LangSmith key from `st.secrets` or the environment; None when it is not set."""
    # Missing is not an error: tracing is simply off (T9.8). A broken secrets.toml reads as missing.
    value = _secret(LANGSMITH_API_KEY_NAME)
    secret = value.strip() if isinstance(value, str) else ""
    return secret or os.environ.get(LANGSMITH_API_KEY_NAME, "").strip() or None


def tracing_requested() -> bool:
    """Return True if the app's tracing flag is on (secrets or environment), key or not (T9.8)."""
    value = _secret(TRACING_FLAG_NAME)
    if value is None:
        value = os.environ.get(TRACING_FLAG_NAME, "")
    return str(value).strip().lower() in TRACING_ON_VALUES


def tracing_demo_unmasked() -> bool:
    """Return True if traces go unmasked: tracing and the demo flag on, in demo mode (T9.35)."""
    # Demo mode has synthetic users only and is never on with [auth]; a signed-in user's runs are
    # therefore always masked, whatever the flag says.
    if not tracing_requested() or not demo_mode():
        return False
    value = _secret(TRACING_DEMO_UNMASKED_FLAG_NAME)
    if value is None:
        value = os.environ.get(TRACING_DEMO_UNMASKED_FLAG_NAME, "")
    return str(value).strip().lower() in TRACING_ON_VALUES
