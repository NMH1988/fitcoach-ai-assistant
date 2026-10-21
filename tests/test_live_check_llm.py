"""Tests for scripts/live_check_llm.py with fake clients (the real run is the owner's check)."""

import http.client
import io
import json
import urllib.error
from decimal import Decimal
from types import SimpleNamespace

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage

from scripts import live_check_llm
from src import config, llm
from src.usage import CallUsage, ModelPrice
from tests.fakes import ScriptedChatModel
from tests.test_llm import STREAM_USAGE, Recorder, StreamServer

FAKE_KEY = "sk-test-not-a-real-key"
# Stands in for the key in a developer's own .streamlit/secrets.toml.
OTHER_KEY = "sk-test-other-local-key"
# The real function, kept before the autouse fixture below replaces it.
REAL_FETCH_GENERATION = live_check_llm.fetch_generation
REAL_BUILD_STREAMING_MODEL = live_check_llm.build_streaming_model


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


STREAM_REPLY_USAGE = {
    "input_tokens": 14,
    "output_tokens": 40,
    "total_tokens": 54,
    "output_token_details": {"reasoning": 24},
}


def _streaming_fake(usage=STREAM_REPLY_USAGE, ids=()):
    """Return a fake streaming model whose reply reports this usage, and a transport stand-in."""
    reply = AIMessage("Protein is made of amino acids.", usage_metadata=usage)
    return ScriptedChatModel(replies=[reply]), SimpleNamespace(ids=list(ids))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Keep main() offline: a fake streamed call, no prices, no generation record by default."""
    # No key unless a test sets one with _use_fake_key(): a local secrets.toml is never read.
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setattr(live_check_llm, "read_prices", lambda: None)
    monkeypatch.setattr(live_check_llm, "fetch_generation", lambda generation_id, key: None)
    monkeypatch.setattr(live_check_llm, "build_streaming_model", _streaming_fake)


def _use_clients(monkeypatch, chat, embeddings):
    """Make the script build the given fake clients instead of real ones."""
    monkeypatch.setattr(llm, "build_chat_model", lambda: chat)
    monkeypatch.setattr(llm, "build_embeddings", lambda: embeddings)


def _use_fake_key(monkeypatch):
    """Make get_api_key() return FAKE_KEY, whatever a local secrets.toml holds."""
    # st.secrets is read before the env var, so setting only the env var is not enough.
    monkeypatch.setattr(config.st, "secrets", {config.API_KEY_NAME: FAKE_KEY})


def _record_generation_keys(monkeypatch) -> list[tuple[str, bool]]:
    """Answer every generation request and note its ID and whether the key was FAKE_KEY."""
    # A bool, not the key itself, so a failing assertion never prints a key.
    asked = []
    monkeypatch.setattr(
        live_check_llm,
        "fetch_generation",
        lambda generation_id, key: asked.append((generation_id, key == FAKE_KEY)) or GENERATION,
    )
    return asked


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
    _use_fake_key(monkeypatch)
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


def test_main_prints_both_costs_for_the_plain_and_the_streamed_call(
    monkeypatch, capsys, no_env_key
):
    """main() prints the app's cost and OpenRouter's record for both chat calls."""
    _use_fake_key(monkeypatch)
    asked = _record_generation_keys(monkeypatch)
    monkeypatch.setattr(live_check_llm, "read_prices", lambda: PRICES)
    monkeypatch.setattr(
        live_check_llm, "build_streaming_model", lambda: _streaming_fake(ids=["gen-stream"])
    )
    _use_clients(monkeypatch, FakeChat(), FakeEmbeddings())
    assert live_check_llm.main() == 0
    out = capsys.readouterr().out
    # 12 x 0.00000025 + 30 x 0.000002 = 0.000063 (the 20 reasoning tokens are not priced).
    assert "cost (app): $0.00006300" in out
    assert (
        "cost (OpenRouter): $0.00010000, native tokens: prompt 12, completion 30, reasoning 20"
        in out
    )
    assert "recorded tokens in 14 / out 40 (reasoning 24)" in out
    # 14 x 0.00000025 + 40 x 0.000002 = 0.0000835
    assert "cost (app, streamed): $0.00008350" in out
    assert "cost (OpenRouter, streamed): $0.00010000" in out
    assert asked == [("gen-test", True), ("gen-stream", True)]
    assert FAKE_KEY not in out


def test_a_local_secrets_file_does_not_reach_the_live_check_tests(
    monkeypatch, capsys, no_env_key, secrets_from_file
):
    """With a secrets.toml holding another key, as in a developer's checkout, FAKE_KEY is used."""
    secrets_from_file(f'{config.API_KEY_NAME} = "{OTHER_KEY}"\n')
    # The file wins over the env var, which is how the real key once reached these tests.
    monkeypatch.setenv(config.API_KEY_NAME, FAKE_KEY)
    file_wins = config.get_api_key() == OTHER_KEY
    assert file_wins
    _use_fake_key(monkeypatch)
    asked = _record_generation_keys(monkeypatch)
    monkeypatch.setattr(
        live_check_llm, "build_streaming_model", lambda: _streaming_fake(ids=["gen-stream"])
    )
    _use_clients(monkeypatch, FakeChat(), FakeEmbeddings())
    assert live_check_llm.main() == 0
    assert asked == [("gen-test", True), ("gen-stream", True)]
    assert OTHER_KEY not in capsys.readouterr().out


def test_costs_say_when_nothing_could_be_read():
    """Without usage, prices or a generation record both cost lines say so."""
    lines = live_check_llm.cost_lines(None, None, None, ", streamed")
    assert lines == [
        "cost (app, streamed): n/a from OpenRouter's prices and the tokens",
        "cost (OpenRouter, streamed): not available (GET /api/v1/generation gave no record)",
    ]


# --- The streamed call, as the app's answer rounds make it (PR #64 review) ------------------------


def _stream_model(transport) -> object:
    """Build the real answer client with the fake key, sending to this transport."""
    return llm.build_chat_model(api_key=FAKE_KEY, http_client=httpx2.Client(transport=transport))


def test_the_stream_check_records_the_real_clients_usage_once():
    """With the real client and an OpenAI-style stream, the usage is recorded once, not twice."""
    lines, call = live_check_llm.stream_check(_stream_model(httpx2.MockTransport(StreamServer())))
    assert call == CallUsage(
        live_check_llm.STREAM_STEP,
        config.DEFAULT_ANSWER_MODEL,
        STREAM_USAGE["prompt_tokens"],
        STREAM_USAGE["completion_tokens"],
        0,
        STREAM_USAGE["completion_tokens_details"]["reasoning_tokens"],
    )
    assert lines == [
        "chat (streamed, as the app's answer rounds): 3 characters, recorded tokens in 2400 / "
        "out 350 (reasoning 128)"
    ]


def test_a_stream_without_usage_is_reported():
    """A stream that reports no token use says the app would count no answer round."""
    model, _ = _streaming_fake(usage=None)
    lines, call = live_check_llm.stream_check(model)
    assert call is None
    assert "the stream reported no token use" in lines[0]


def test_the_transport_notes_the_generation_id_and_keeps_the_stream():
    """The generation ID is read from the streamed body, which reaches langchain unchanged."""
    transport = live_check_llm.GenerationIdTransport(httpx2.MockTransport(StreamServer()))
    _, call = live_check_llm.stream_check(_stream_model(transport))
    assert transport.ids == ["gen-test"]
    assert call is not None and call.input_tokens == STREAM_USAGE["prompt_tokens"]


def test_the_streaming_model_is_built_through_the_apps_builder(monkeypatch):
    """The streamed call's client comes from build_chat_model, so allowlist and cap apply."""
    built = []
    monkeypatch.setattr(llm, "build_chat_model", lambda **kwargs: built.append(kwargs) or "model")
    model, transport = REAL_BUILD_STREAMING_MODEL()
    assert model == "model"
    assert isinstance(transport, live_check_llm.GenerationIdTransport)
    [kwargs] = built
    assert list(kwargs) == ["http_client"]


def test_the_streamed_reply_is_asked_for_uncompressed(monkeypatch, no_env_key):
    """The streamed request says Accept-Encoding: identity, so the ID is readable in the body."""
    server = StreamServer()
    monkeypatch.setattr(httpx2, "HTTPTransport", lambda: httpx2.MockTransport(server))
    _use_fake_key(monkeypatch)
    model, transport = REAL_BUILD_STREAMING_MODEL()
    live_check_llm.stream_check(model)
    assert server.requests[-1].headers["accept-encoding"] == "identity"
    assert transport.ids == ["gen-test"]


class _ChunkedStream(httpx2.SyncByteStream):
    """A response body sent in small pieces, as a network stream may arrive."""

    def __init__(self, body: bytes, size: int) -> None:
        """Keep the body and the piece size."""
        self._body = body
        self._size = size

    def __iter__(self):
        """Yield the body in pieces of `size` bytes."""
        for start in range(0, len(self._body), self._size):
            yield self._body[start : start + self._size]


class _ChunkedServer(StreamServer):
    """The streaming fake server, but its body arrives in 5-byte pieces."""

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Answer as StreamServer does, with the body split into small pieces."""
        whole = super().__call__(request)
        body = whole.read()
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, stream=_ChunkedStream(body, 5)
        )


def test_an_id_split_across_chunks_is_still_found():
    """The ID is found even when the stream cuts it into pieces, and the reply is unchanged."""
    transport = live_check_llm.GenerationIdTransport(httpx2.MockTransport(_ChunkedServer()))
    lines, call = live_check_llm.stream_check(_stream_model(transport))
    assert transport.ids == ["gen-test"]
    assert call is not None and call.output_tokens == STREAM_USAGE["completion_tokens"]
    assert "3 characters" in lines[0]


@pytest.fixture
def no_sleep(monkeypatch):
    """Skip the SDK's back-off sleeps between retries so the test runs instantly."""
    monkeypatch.setattr(openai._base_client.time, "sleep", lambda seconds: None)


def test_an_error_status_through_the_transport_is_still_mapped(no_sleep):
    """A 429 passes through the wrapper and becomes the app's fixed rate-limit error."""
    server = Recorder(status=429, body={"error": {"code": 429, "message": "slow down"}})
    transport = live_check_llm.GenerationIdTransport(httpx2.MockTransport(server))
    with pytest.raises(llm.RateLimitedError):
        live_check_llm.stream_check(_stream_model(transport))
    assert transport.ids == []


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
        return _Body(result if isinstance(result, bytes) else json.dumps(result).encode())

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
        [http.client.IncompleteRead(b"{")],
        [{"data": "x" * live_check_llm.GENERATION_MAX_BYTES}],
        [b"[" * 100_000],
    ],
    ids=["401", "offline", "malformed", "never-recorded", "cut-off", "too-large", "too-deep"],
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
