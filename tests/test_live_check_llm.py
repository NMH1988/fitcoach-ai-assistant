"""Tests for scripts/live_check_llm.py with fake clients (the real run is the owner's check)."""

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage

from scripts import live_check_llm
from src import config, llm

FAKE_KEY = "sk-test-not-a-real-key"


class FakeChat:
    """Stands in for the chat model: returns a fixed reply or raises a fixed error."""

    model_name = config.DEFAULT_ANSWER_MODEL
    max_tokens = config.DEFAULT_MAX_TOKENS

    def __init__(self, reply="Protein is a nutrient made of amino acids.", error=None, output=30):
        """Keep the reply text and output token count to return, or the error to raise."""
        self.reply = reply
        self.error = error
        self.output = output

    def invoke(self, prompt):
        """Return the fixed reply with token usage, or raise the fixed error."""
        if self.error is not None:
            raise self.error
        usage = {
            "input_tokens": 12,
            "output_tokens": self.output,
            "total_tokens": 12 + self.output,
            "output_token_details": {"reasoning": 20},
        }
        return AIMessage(content=self.reply, usage_metadata=usage)


class FakeEmbeddings:
    """Stands in for the embeddings client: returns a fixed vector."""

    model = config.EMBEDDING_MODEL

    def __init__(self, vector=(0.1, 0.2, 0.3)):
        """Keep the vector to return."""
        self.vector = list(vector)

    def embed_query(self, text):
        """Return the fixed vector."""
        return self.vector


def _rate_limit_error() -> openai.RateLimitError:
    """Build the SDK error a 429 from OpenRouter would raise."""
    request = httpx2.Request("POST", f"{config.OPENROUTER_BASE_URL}/chat/completions")
    response = httpx2.Response(429, request=request)
    return openai.RateLimitError(f"echo {FAKE_KEY}", response=response, body=None)


def _use_clients(monkeypatch, chat, embeddings):
    """Make the script build the given fake clients instead of real ones."""
    monkeypatch.setattr(llm, "build_chat_model", lambda: chat)
    monkeypatch.setattr(llm, "build_embeddings", lambda: embeddings)


def test_run_checks_reports_both_calls():
    """A good chat reply and vector give one result line each, with models and sizes."""
    lines = live_check_llm.run_checks(FakeChat(), FakeEmbeddings())
    assert lines[0].startswith(f"chat: {config.DEFAULT_ANSWER_MODEL} ok")
    assert "tokens in 12 / out 30 (reasoning 20)" in lines[0]
    assert lines[1] == f"embedding: {config.EMBEDDING_MODEL} ok, 3 dimensions"


def test_main_prints_results_and_succeeds(monkeypatch, capsys):
    """With working clients the script prints both lines and exits 0."""
    _use_clients(monkeypatch, FakeChat(), FakeEmbeddings())
    assert live_check_llm.main() == 0
    assert "embedding:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("chat", "embeddings"),
    [
        (FakeChat(reply="  "), FakeEmbeddings()),
        (FakeChat(), FakeEmbeddings(vector=())),
        (FakeChat(output=config.DEFAULT_MAX_TOKENS + 1), FakeEmbeddings()),
    ],
    ids=["empty-reply", "empty-vector", "over-token-cap"],
)
def test_unusable_results_fail(monkeypatch, capsys, chat, embeddings):
    """An empty reply, an empty vector or a reply over the token cap is reported as a failure."""
    _use_clients(monkeypatch, chat, embeddings)
    assert live_check_llm.main() == 1
    assert "Live check failed" in capsys.readouterr().err


def test_api_error_shows_the_mapped_message_without_the_key(monkeypatch, capsys):
    """An API error prints the user-readable message and never the key."""
    _use_clients(monkeypatch, FakeChat(error=_rate_limit_error()), FakeEmbeddings())
    assert live_check_llm.main() == 1
    output = capsys.readouterr()
    assert llm.RateLimitedError.user_message in output.err
    assert FAKE_KEY not in output.err + output.out


def test_missing_key_fails_cleanly(monkeypatch, capsys, no_env_key):
    """With no key configured the script says so and exits 1 instead of crashing."""
    monkeypatch.setattr(config.st, "secrets", {})
    assert live_check_llm.main() == 1
    assert config.API_KEY_NAME in capsys.readouterr().err
