"""Tests for src/config.py: models, limits and API key loading."""

import pytest

from src import config


def test_allowed_models():
    """Allowed chat models are the three gpt-5 models chosen in docs/ARCHITECTURE.md."""
    assert config.ALLOWED_MODELS == ("openai/gpt-5-mini", "openai/gpt-5-nano", "openai/gpt-5")


def test_default_models_are_allowed():
    """Answers use gpt-5-mini and query translation gpt-5-nano, both on the allowed list."""
    assert config.DEFAULT_ANSWER_MODEL == "openai/gpt-5-mini"
    assert config.QUERY_TRANSLATION_MODEL == "openai/gpt-5-nano"
    assert config.DEFAULT_ANSWER_MODEL in config.ALLOWED_MODELS
    assert config.QUERY_TRANSLATION_MODEL in config.ALLOWED_MODELS


def test_embedding_model_and_endpoint():
    """Embeddings use qwen3-embedding-8b, and every call goes to OpenRouter's API."""
    assert config.EMBEDDING_MODEL == "qwen/qwen3-embedding-8b"
    assert config.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"


def test_default_max_tokens_fits_the_cap():
    """The default token budget is positive and not above the per-request cap."""
    assert 0 < config.DEFAULT_MAX_TOKENS <= config.MAX_TOKENS_CAP


def test_input_and_rate_limits():
    """Input and rate limits keep their Sprint 1 values; per-minute stays below per-session."""
    assert config.MAX_INPUT_CHARS == 2000
    assert config.RATE_LIMIT_PER_MINUTE == 10
    assert config.RATE_LIMIT_WINDOW_SECONDS == 60
    assert config.RATE_LIMIT_PER_SESSION == 50
    assert config.RATE_LIMIT_PER_MINUTE < config.RATE_LIMIT_PER_SESSION


def test_disclaimer_says_not_medical_advice():
    """The disclaimer text says the app is not medical advice."""
    assert "not medical advice" in config.DISCLAIMER


class _NoSecretsFile:
    """Mimics st.secrets when no secrets.toml exists."""

    def get(self, key, default=None):
        """Fail like Streamlit does when there is no secrets file."""
        raise FileNotFoundError("No secrets found.")


def test_api_key_from_secrets(monkeypatch, no_env_key):
    """The key is read from st.secrets."""
    monkeypatch.setattr(config.st, "secrets", {config.API_KEY_NAME: "sk-test-from-secrets"})
    assert config.get_api_key() == "sk-test-from-secrets"


def test_secrets_take_precedence_over_env(monkeypatch):
    """If both are set, st.secrets wins over the env var."""
    monkeypatch.setattr(config.st, "secrets", {config.API_KEY_NAME: "sk-test-from-secrets"})
    monkeypatch.setenv(config.API_KEY_NAME, "sk-test-from-env")
    assert config.get_api_key() == "sk-test-from-secrets"


def test_api_key_falls_back_to_env(monkeypatch):
    """If st.secrets has no key, the env var is used."""
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setenv(config.API_KEY_NAME, "sk-test-from-env")
    assert config.get_api_key() == "sk-test-from-env"


def test_api_key_from_env_when_no_secrets_file(monkeypatch):
    """With no secrets file at all, the env var is still used."""
    monkeypatch.setattr(config.st, "secrets", _NoSecretsFile())
    monkeypatch.setenv(config.API_KEY_NAME, "sk-test-from-env")
    assert config.get_api_key() == "sk-test-from-env"


def test_api_key_is_stripped(monkeypatch, no_env_key):
    """Spaces and newlines around the key are removed."""
    monkeypatch.setattr(config.st, "secrets", {config.API_KEY_NAME: "  sk-test-padded \n"})
    assert config.get_api_key() == "sk-test-padded"


@pytest.mark.parametrize("secrets", [{}, {config.API_KEY_NAME: ""}, {config.API_KEY_NAME: "  "}])
def test_missing_api_key_raises(monkeypatch, no_env_key, secrets):
    """An absent, empty or blank key raises MissingAPIKeyError."""
    monkeypatch.setattr(config.st, "secrets", secrets)
    with pytest.raises(config.MissingAPIKeyError):
        config.get_api_key()


def test_missing_api_key_raises_when_no_secrets_file(monkeypatch, no_env_key):
    """No secrets file and no env var raises MissingAPIKeyError, not SecretsFileError."""
    monkeypatch.setattr(config.st, "secrets", _NoSecretsFile())
    with pytest.raises(config.MissingAPIKeyError) as excinfo:
        config.get_api_key()
    assert not isinstance(excinfo.value, config.SecretsFileError)


@pytest.mark.parametrize("value", [123, {"nested": "table"}, ["a"], True])
def test_non_string_secret_is_treated_as_missing(monkeypatch, no_env_key, value):
    """A number, table or list under the key is not turned into a fake key string."""
    monkeypatch.setattr(config.st, "secrets", {config.API_KEY_NAME: value})
    with pytest.raises(config.MissingAPIKeyError):
        config.get_api_key()


def test_unparseable_secrets_file_raises_secrets_file_error(secrets_from_file, no_env_key):
    """An unquoted key makes a real secrets.toml unparseable, which gets its own error."""
    secrets_from_file(f"{config.API_KEY_NAME} = sk-test-unquoted\n")
    with pytest.raises(config.SecretsFileError) as excinfo:
        config.get_api_key()
    # The raw parser message could echo file content, so it must not leak out.
    assert "sk-test-unquoted" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def test_unparseable_secrets_file_falls_back_to_env(secrets_from_file, monkeypatch):
    """A broken secrets.toml does not block a key set in the environment."""
    secrets_from_file(f"{config.API_KEY_NAME} = sk-test-unquoted\n")
    monkeypatch.setenv(config.API_KEY_NAME, "sk-test-from-env")
    # A bool, so a failure never prints the key a real secrets.toml might give (T5.1a).
    env_key_used = config.get_api_key() == "sk-test-from-env"
    assert env_key_used


def test_valid_secrets_file_is_read(secrets_from_file, no_env_key):
    """A correctly quoted key in a real secrets.toml is returned."""
    secrets_from_file(f'{config.API_KEY_NAME} = "sk-test-from-file"\n')
    file_key_used = config.get_api_key() == "sk-test-from-file"
    assert file_key_used


def test_missing_key_error_does_not_contain_a_key(monkeypatch):
    """The missing-key message names the setting, never a key value."""
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.delenv(config.API_KEY_NAME, raising=False)
    with pytest.raises(config.MissingAPIKeyError) as excinfo:
        config.get_api_key()
    assert config.API_KEY_NAME in str(excinfo.value)
    assert "sk-" not in str(excinfo.value)
