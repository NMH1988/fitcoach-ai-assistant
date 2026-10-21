"""Tests for scripts/live_check_llm.py with fake clients (the real run is the owner's check)."""

import io
import json
import urllib.error
from decimal import Decimal

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage

from scripts import live_check_llm
from src import config, llm
from src.usage import ModelPrice

FAKE_KEY = "sk-test-not-a-real-key"
# The real function, kept before the autouse fixture below replaces it.
REAL_FETCH_GENERATION = live_check_llm.fetch_generation


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
        return AIMessage(
            content=self.reply, usage_metadata=usage, response_metadata={"id": "gen-test"}
        )


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


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Keep main() offline: no prices and no generation record, unless a test sets them."""
    monkeypatch.setattr(live_check_llm, "read_prices", lambda: None)
    monkeypatch.setattr(live_check_llm, "fetch_generation", lambda generation_id, key: None)


def _use_clients(monkeypatch, chat, embeddings):
    """Make the script build the given fake clients instead of real ones."""
    monkeypatch.setattr(llm, "build_chat_model", lambda: chat)
    monkeypatch.setattr(llm, "build_embeddings", lambda: embeddings)


def test_run_checks_reports_both_calls():
    """A good chat reply and vector give one result line each, with models and sizes."""
    lines, reply = live_check_llm.run_checks(FakeChat(), FakeEmbeddings())
    assert reply.response_metadata["id"] == "gen-test"
    assert lines[0].startswith(f"chat: {config.DEFAULT_ANSWER_MODEL} ok")
    assert "tokens in 12 / out 30 (reasoning 20)" in lines[0]
    assert lines[1] == f"embedding: {config.EMBEDDING_MODEL} ok, 3 dimensions"


def test_main_prints_results_and_succeeds(monkeypatch, capsys, no_env_key):
    """With working clients the script prints both lines and exits 0."""
    # The key is read again for OpenRouter's cost record (T5.1).
    monkeypatch.setenv(config.API_KEY_NAME, FAKE_KEY)
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


# --- Cost: the app's computation next to OpenRouter's record (T5.1, O5) ---------------------------

PRICES = {config.DEFAULT_ANSWER_MODEL: ModelPrice(Decimal("0.00000025"), Decimal("0.000002"))}
GENERATION = {
    "id": "gen-test",
    "total_cost": 0.0001,
    "native_tokens_prompt": 12,
    "native_tokens_completion": 30,
    "native_tokens_reasoning": 20,
}


def test_main_prints_both_costs(monkeypatch, capsys, no_env_key):
    """main() prints the app's cost and OpenRouter's recorded cost and native tokens."""
    monkeypatch.setenv(config.API_KEY_NAME, FAKE_KEY)
    asked = []
    monkeypatch.setattr(live_check_llm, "read_prices", lambda: PRICES)
    monkeypatch.setattr(
        live_check_llm,
        "fetch_generation",
        lambda generation_id, key: asked.append((generation_id, key)) or GENERATION,
    )
    _use_clients(monkeypatch, FakeChat(), FakeEmbeddings())
    assert live_check_llm.main() == 0
    out = capsys.readouterr().out
    # 12 x 0.00000025 + 30 x 0.000002 = 0.000063 (the 20 reasoning tokens are part of the 30).
    assert "cost (app): $0.00006300" in out
    assert (
        "cost (OpenRouter): $0.00010000, native tokens: prompt 12, completion 30, reasoning 20"
        in out
    )
    assert asked == [("gen-test", FAKE_KEY)]
    assert FAKE_KEY not in out


def test_costs_say_when_nothing_could_be_read():
    """Without prices or a generation record both cost lines say so."""
    reply = FakeChat().invoke("x")
    lines = live_check_llm.cost_lines(reply, config.DEFAULT_ANSWER_MODEL, None, None)
    assert lines == [
        "cost (app): n/a from OpenRouter's prices and the reported tokens",
        "cost (OpenRouter): not available (GET /api/v1/generation gave no record)",
    ]


class _Body(io.BytesIO):
    """A stand-in HTTP response body that works as a context manager."""


def _opener(*results):
    """Return a fake opener that gives each result (a body or an exception) in turn."""
    requests = []

    def open_(request, timeout):
        """Record the request, then answer or fail with the next result."""
        requests.append(request)
        result = results[len(requests) - 1]
        if isinstance(result, Exception):
            raise result
        return _Body(json.dumps(result).encode())

    return open_, requests


def _http_error(code: int) -> urllib.error.HTTPError:
    """Return the error urllib raises for an HTTP status."""
    return urllib.error.HTTPError("u", code, "status", {}, None)


def test_fetch_generation_asks_with_the_key_and_waits_for_the_record():
    """The record is asked for by ID with the key; a 404 (not recorded yet) is retried."""
    opener, requests = _opener(_http_error(404), {"data": GENERATION})
    waits = []
    data = REAL_FETCH_GENERATION("gen-test", FAKE_KEY, opener, waits.append)
    assert data == GENERATION
    assert len(requests) == 2 and waits == [live_check_llm.GENERATION_WAIT_SECONDS]
    request = requests[0]
    assert request.full_url == f"{config.OPENROUTER_BASE_URL}/generation?id=gen-test"
    assert request.get_header("Authorization") == f"Bearer {FAKE_KEY}"


@pytest.mark.parametrize(
    "results",
    [
        [_http_error(401)],
        [urllib.error.URLError("offline")],
        [{"data": "x"}],
        [_http_error(404)] * live_check_llm.GENERATION_ATTEMPTS,
    ],
    ids=["401", "offline", "malformed", "never-recorded"],
)
def test_fetch_generation_gives_none_when_there_is_no_record(results):
    """Any other status, a network failure, a malformed body or no record in time give None."""
    opener, requests = _opener(*results)
    assert REAL_FETCH_GENERATION("gen-test", FAKE_KEY, opener, lambda s: None) is None
    assert len(requests) == len(results)


def test_the_generation_request_never_follows_a_redirect():
    """The request holding the key goes through an opener that refuses redirects."""
    handlers = [type(h).__name__ for h in live_check_llm._OPENER.handlers]
    assert "NoRedirect" in handlers and "HTTPRedirectHandler" not in handlers
