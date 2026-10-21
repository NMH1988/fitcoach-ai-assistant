"""Tests for src/llm.py: client settings, error mapping and bounded retries (mocked transport)."""

import json
import traceback

import httpx2
import openai
import pydantic
import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from src import config, llm

FAKE_KEY = "sk-test-not-a-real-key"
CHAT_URL = f"{config.OPENROUTER_BASE_URL}/chat/completions"
EMBEDDINGS_URL = f"{config.OPENROUTER_BASE_URL}/embeddings"

CHAT_OK = {
    "id": "gen-test",
    "object": "chat.completion",
    "created": 0,
    "model": config.DEFAULT_ANSWER_MODEL,
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}
EMBEDDINGS_OK = {
    "object": "list",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
    "model": config.EMBEDDING_MODEL,
    "usage": {"prompt_tokens": 1, "total_tokens": 1},
}

# The five failures the ticket names (401, 402, 429, timeout, 5xx), plus 408, OpenRouter's
# upstream timeout; each maps to its own error class.
STATUS_ERRORS = [
    (401, llm.InvalidAPIKeyError),
    (402, llm.OutOfCreditError),
    (408, llm.LLMTimeoutError),
    (429, llm.RateLimitedError),
    (500, llm.ServiceUnavailableError),
    (502, llm.ServiceUnavailableError),
    (503, llm.ServiceUnavailableError),
]
RETRIED_STATUSES = [408, 429, 500, 503]
NOT_RETRIED_STATUSES = [401, 402]


class Recorder:
    """A fake OpenRouter server: records each request and answers with a fixed reply."""

    def __init__(self, status=200, body=None, raise_exc=None, echo_auth=False):
        """Set the status and JSON body to return, or an httpx2 exception class to raise."""
        self.status = status
        self.body = body
        self.raise_exc = raise_exc
        self.echo_auth = echo_auth
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Handle one request the way the configured fake server would."""
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc("fake network failure", request=request)
        body = self.body
        if self.echo_auth:
            # Worst case: the server quotes the Authorization header back in its error.
            body = {"error": {"message": f"bad: {request.headers.get('authorization')}"}}
        return httpx2.Response(self.status, json=body)

    def client(self) -> httpx2.Client:
        """Return an httpx2 client that sends every request to this fake server."""
        return httpx2.Client(transport=httpx2.MockTransport(self))

    def last_json(self) -> dict:
        """Return the JSON body of the last request received."""
        return json.loads(self.requests[-1].content)


def _error_body(status: int) -> dict:
    """Return an OpenRouter-style error body for the given status."""
    return {"error": {"code": status, "message": f"fake error {status}"}}


@pytest.fixture
def no_sleep(monkeypatch):
    """Skip the SDK's back-off sleeps between retries so the tests run instantly."""
    monkeypatch.setattr(openai._base_client.time, "sleep", lambda seconds: None)


def _chat(server: Recorder, **kwargs):
    """Build a chat model with the fake key that talks to the fake server."""
    return llm.build_chat_model(api_key=FAKE_KEY, http_client=server.client(), **kwargs)


def _embeddings(server: Recorder):
    """Build the embeddings client with the fake key that talks to the fake server."""
    return llm.build_embeddings(api_key=FAKE_KEY, http_client=server.client())


# --- Client settings (AC 1) ---


def test_chat_model_settings():
    """The chat model uses OpenRouter, the default model, the config limits and Chat Completions."""
    model = llm.build_chat_model(api_key=FAKE_KEY)
    assert model.model_name == config.DEFAULT_ANSWER_MODEL
    assert model.openai_api_base == config.OPENROUTER_BASE_URL
    assert model.openai_api_key.get_secret_value() == FAKE_KEY
    assert model.max_tokens == config.DEFAULT_MAX_TOKENS
    assert model.reasoning_effort == config.REASONING_EFFORT == "low"
    assert model.request_timeout == config.LLM_TIMEOUT_SECONDS == 60
    assert model.max_retries == config.LLM_MAX_RETRIES == 2
    assert model.use_responses_api is False


@pytest.mark.parametrize("name", config.ALLOWED_MODELS)
def test_chat_model_accepts_every_allowed_model(name):
    """Every model on the allowlist can be built."""
    assert llm.build_chat_model(name, api_key=FAKE_KEY).model_name == name


@pytest.mark.parametrize("name", ["openai/gpt-4o", "anthropic/claude-opus-5.5", "", "gpt-5-mini"])
def test_chat_model_rejects_models_not_on_the_allowlist(name):
    """A model outside the allowlist is refused before any client is built."""
    with pytest.raises(ValueError, match="not on the allowed list"):
        llm.build_chat_model(name, api_key=FAKE_KEY)


def test_max_tokens_is_capped():
    """A request for more tokens than the cap is clamped to the cap."""
    model = llm.build_chat_model(max_tokens=config.MAX_TOKENS_CAP * 10, api_key=FAKE_KEY)
    assert model.max_tokens == config.MAX_TOKENS_CAP


def test_max_tokens_below_the_cap_is_kept():
    """A token budget under the cap is passed through unchanged."""
    assert llm.build_chat_model(max_tokens=500, api_key=FAKE_KEY).max_tokens == 500


@pytest.mark.parametrize("value", [0, -1])
def test_max_tokens_must_be_positive(value):
    """Zero or negative max_tokens is a programming error and raises ValueError."""
    with pytest.raises(ValueError, match="max_tokens"):
        llm.build_chat_model(max_tokens=value, api_key=FAKE_KEY)


def test_chat_request_on_the_wire():
    """A chat call goes to OpenRouter with the key, the model, the token cap and the effort."""
    server = Recorder(body=CHAT_OK)
    reply = _chat(server).invoke("Hi")
    assert reply.content == "Hello."
    request = server.requests[-1]
    assert str(request.url) == CHAT_URL
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = server.last_json()
    assert body["model"] == config.DEFAULT_ANSWER_MODEL
    assert body["max_completion_tokens"] == config.DEFAULT_MAX_TOKENS
    assert body["reasoning_effort"] == "low"
    assert "temperature" not in body


def test_embeddings_settings():
    """The embeddings client uses qwen3-embedding-8b on OpenRouter and sends raw text."""
    embeddings = llm.build_embeddings(api_key=FAKE_KEY)
    assert embeddings.model == config.EMBEDDING_MODEL == "qwen/qwen3-embedding-8b"
    assert embeddings.openai_api_base == config.OPENROUTER_BASE_URL
    assert embeddings.openai_api_key.get_secret_value() == FAKE_KEY
    assert embeddings.check_embedding_ctx_length is False
    assert embeddings.request_timeout == config.LLM_TIMEOUT_SECONDS
    assert embeddings.max_retries == config.LLM_MAX_RETRIES


def test_embeddings_request_on_the_wire():
    """An embedding call sends the text itself, not token IDs, to OpenRouter's endpoint."""
    server = Recorder(body=EMBEDDINGS_OK)
    vector = _embeddings(server).embed_query("protein after training")
    assert vector == [0.1, 0.2, 0.3]
    assert str(server.requests[-1].url) == EMBEDDINGS_URL
    body = server.last_json()
    assert body["model"] == config.EMBEDDING_MODEL
    assert body["input"] == ["protein after training"]


# --- Token use (T5.1) ---


def _sse(*events: dict) -> str:
    """Return a server-sent event stream of these JSON chunks, then [DONE]."""
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"


def _stream_chunk(choices: list, **extra) -> dict:
    """Return one chat completion chunk with these choices."""
    return {
        "id": "gen-test",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": config.DEFAULT_ANSWER_MODEL,
        "choices": choices,
        **extra,
    }


STREAM_USAGE = {
    "prompt_tokens": 2400,
    "completion_tokens": 350,
    "total_tokens": 2750,
    "prompt_tokens_details": {"cached_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 128},
}


class StreamServer(Recorder):
    """A fake OpenRouter server that streams one short answer, then a chunk with the usage."""

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Record the request and stream the answer and its token use."""
        self.requests.append(request)
        text = _sse(
            _stream_chunk([{"index": 0, "delta": {"role": "assistant", "content": "Hi."}}]),
            _stream_chunk([{"index": 0, "delta": {}, "finish_reason": "stop"}]),
            # OpenAI's last chunk with stream_options.include_usage: no choices, only usage.
            _stream_chunk([], usage=STREAM_USAGE),
        )
        return httpx2.Response(200, text=text, headers={"content-type": "text/event-stream"})


def test_chat_model_streams_its_token_use():
    """The client asks OpenRouter for the token use of a streamed reply and reports it."""
    # langchain asks for it only on OpenAI's own URL unless stream_usage is set (T5.1).
    server = StreamServer()
    model = _chat(server)
    assert model.stream_usage is True
    reply = None
    # Bound to a tool as in the answer step: binding keeps the setting.
    for chunk in model.bind_tools([_Answer]).stream("Hi"):
        reply = chunk if reply is None else reply + chunk
    assert server.last_json()["stream_options"] == {"include_usage": True}
    assert reply.text == "Hi."
    assert reply.response_metadata["finish_reason"] == "stop"
    assert reply.usage_metadata["input_tokens"] == 2400
    assert reply.usage_metadata["output_tokens"] == 350
    assert reply.usage_metadata["output_token_details"]["reasoning"] == 128


def _embeddings_body(count: int, usage: dict | None) -> dict:
    """Return an embeddings reply with count vectors and this usage (left out when None)."""
    body = {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": [0.1, 0.2]} for i in range(count)
        ],
        "model": config.EMBEDDING_MODEL,
    }
    if usage is not None:
        body["usage"] = usage
    return body


def test_embeddings_report_the_tokens_the_api_counted():
    """embed_with_usage returns the vectors and the reply's prompt_tokens (T5.1)."""
    server = Recorder(body=_embeddings_body(2, {"prompt_tokens": 17, "total_tokens": 17}))
    vectors, tokens = _embeddings(server).embed_with_usage(["protein", "creatine timing"])
    assert vectors == [[0.1, 0.2], [0.1, 0.2]]
    assert tokens == 17
    assert server.last_json()["input"] == ["protein", "creatine timing"]


def test_embedding_tokens_add_up_over_batches():
    """Texts sent in several requests add up their counts."""
    server = Recorder(body=_embeddings_body(1, {"prompt_tokens": 5, "total_tokens": 5}))
    embeddings = _embeddings(server)
    embeddings.chunk_size = 1
    vectors, tokens = embeddings.embed_with_usage(["a", "b", "c"])
    assert len(vectors) == 3 and len(server.requests) == 3
    assert tokens == 15


@pytest.mark.parametrize(
    "usage", [None, {}, {"prompt_tokens": "17"}, {"prompt_tokens": True}], ids=str
)
def test_embedding_tokens_not_reported_are_unknown(usage):
    """A reply without a usable count gives None, never a made-up 0."""
    server = Recorder(body=_embeddings_body(1, usage))
    vectors, tokens = _embeddings(server).embed_with_usage(["protein"])
    assert vectors == [[0.1, 0.2]]
    assert tokens is None


def test_embedding_usage_errors_are_mapped(no_sleep):
    """A failed counted embedding call maps to the same errors as any other call."""
    server = Recorder(status=402, body=_error_body(402))
    with pytest.raises(llm.OutOfCreditError), llm.mapped_errors():
        _embeddings(server).embed_with_usage(["protein"])


def test_clients_read_the_key_from_config(monkeypatch, no_env_key):
    """Without an explicit key, both clients take it from get_api_key()."""
    monkeypatch.setattr(config.st, "secrets", {config.API_KEY_NAME: FAKE_KEY})
    assert llm.build_chat_model().openai_api_key.get_secret_value() == FAKE_KEY
    assert llm.build_embeddings().openai_api_key.get_secret_value() == FAKE_KEY


def test_clients_without_a_key_raise_missing_key(monkeypatch, no_env_key):
    """With no key configured, building a client raises MissingAPIKeyError."""
    monkeypatch.setattr(config.st, "secrets", {})
    with pytest.raises(config.MissingAPIKeyError):
        llm.build_chat_model()
    with pytest.raises(config.MissingAPIKeyError):
        llm.build_embeddings()


def test_client_repr_hides_the_key():
    """Printing a client never shows the key."""
    assert FAKE_KEY not in repr(llm.build_chat_model(api_key=FAKE_KEY))
    assert FAKE_KEY not in repr(llm.build_embeddings(api_key=FAKE_KEY))


# --- Error mapping and retries (AC 2) ---


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize(("status", "error_class"), STATUS_ERRORS)
def test_chat_status_maps_to_error(status, error_class):
    """Each failing HTTP status from a chat call becomes its own user-readable error."""
    server = Recorder(status=status, body=_error_body(status))
    with pytest.raises(error_class) as excinfo, llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert str(excinfo.value) == error_class.user_message
    assert excinfo.value.status_code == status


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize(("status", "error_class"), STATUS_ERRORS)
def test_embeddings_status_maps_to_error(status, error_class):
    """Each failing HTTP status from an embedding call becomes the same user-readable error."""
    server = Recorder(status=status, body=_error_body(status))
    with pytest.raises(error_class), llm.mapped_errors():
        _embeddings(server).embed_query("protein")


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("status", [400, 403, 404])
def test_other_statuses_map_to_a_generic_error(status):
    """Other client errors (bad request, moderation, unknown model) get the generic message."""
    server = Recorder(status=status, body=_error_body(status))
    with pytest.raises(llm.LLMServiceError) as excinfo, llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert str(excinfo.value) == llm.LLMError.user_message
    assert len(server.requests) == 1


@pytest.mark.usefixtures("no_sleep")
def test_timeout_maps_to_timeout_error():
    """A request that times out becomes LLMTimeoutError, after the bounded retries."""
    server = Recorder(raise_exc=httpx2.ReadTimeout)
    with pytest.raises(llm.LLMTimeoutError) as excinfo, llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert str(excinfo.value) == llm.LLMTimeoutError.user_message
    assert len(server.requests) == config.LLM_MAX_RETRIES + 1


@pytest.mark.usefixtures("no_sleep")
def test_embeddings_timeout_is_retried_then_mapped():
    """An embedding request that times out is retried the bounded number of times, then mapped."""
    server = Recorder(raise_exc=httpx2.ReadTimeout)
    with pytest.raises(llm.LLMTimeoutError), llm.mapped_errors():
        _embeddings(server).embed_query("protein")
    assert len(server.requests) == config.LLM_MAX_RETRIES + 1


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": 502, "message": "provider down"}},
        {"id": "gen-test", "object": "chat.completion", "created": 0, "model": "m"},
        {**CHAT_OK, "choices": None},
    ],
    ids=["error-field", "no-choices", "null-choices"],
)
def test_malformed_chat_reply_maps_to_unavailable(body):
    """A 200 chat reply with an error field or no choices becomes ServiceUnavailableError."""
    server = Recorder(status=200, body=body)
    with pytest.raises(llm.ServiceUnavailableError) as excinfo, llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert "provider down" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize(
    "body",
    [{"error": {"code": 502, "message": "provider down"}}, {**EMBEDDINGS_OK, "data": None}],
    ids=["error-field", "null-data"],
)
def test_malformed_embeddings_reply_maps_to_unavailable(body):
    """A 200 embedding reply with no data becomes ServiceUnavailableError."""
    server = Recorder(status=200, body=body)
    with pytest.raises(llm.ServiceUnavailableError), llm.mapped_errors():
        _embeddings(server).embed_query("protein")


@pytest.mark.parametrize("error_class", [ValueError, KeyError, TypeError])
def test_caller_errors_of_the_same_types_pass_through(error_class):
    """A ValueError, KeyError or TypeError from the caller's own code is not renamed."""
    with pytest.raises(error_class), llm.mapped_errors():
        raise error_class("a bug in our code")


@pytest.mark.usefixtures("no_sleep")
def test_connection_failure_maps_to_connection_error():
    """A service that cannot be reached becomes LLMConnectionError."""
    server = Recorder(raise_exc=httpx2.ConnectError)
    with pytest.raises(llm.LLMConnectionError), llm.mapped_errors():
        _embeddings(server).embed_query("protein")


def test_the_five_named_failures_have_distinct_messages():
    """401, 402, 429, timeout and 5xx each show a different message."""
    classes = [
        llm.InvalidAPIKeyError,
        llm.OutOfCreditError,
        llm.RateLimitedError,
        llm.LLMTimeoutError,
        llm.ServiceUnavailableError,
    ]
    messages = {cls.user_message for cls in classes}
    assert len(messages) == len(classes)
    assert llm.LLMError.user_message not in messages


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("status", RETRIED_STATUSES)
def test_transient_errors_are_retried_a_bounded_number_of_times(status):
    """408, 429 and 5xx are retried exactly LLM_MAX_RETRIES times, then fail."""
    server = Recorder(status=status, body=_error_body(status))
    with pytest.raises(llm.LLMError), llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert len(server.requests) == config.LLM_MAX_RETRIES + 1


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("status", NOT_RETRIED_STATUSES)
def test_key_and_credit_errors_are_not_retried(status):
    """A rejected key or an empty account fails on the first request, with no retry."""
    server = Recorder(status=status, body=_error_body(status))
    with pytest.raises(llm.LLMError), llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert len(server.requests) == 1


@pytest.mark.usefixtures("no_sleep")
def test_a_retry_that_succeeds_returns_the_answer():
    """One 429 followed by a good reply returns the reply, so the user sees no error."""
    replies = iter(
        [httpx2.Response(429, json=_error_body(429)), httpx2.Response(200, json=CHAT_OK)]
    )
    client = httpx2.Client(transport=httpx2.MockTransport(lambda request: next(replies)))
    model = llm.build_chat_model(api_key=FAKE_KEY, http_client=client)
    with llm.mapped_errors():
        assert model.invoke("Hi").content == "Hello."


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("status", [401, 402, 429, 500, 400])
def test_the_key_never_appears_in_a_mapped_error(status):
    """Even when the server quotes the key back, the mapped error and its traceback hide it."""
    server = Recorder(status=status, echo_auth=True)
    with pytest.raises(llm.LLMError) as excinfo, llm.mapped_errors():
        _chat(server).invoke("Hi")
    error = excinfo.value
    assert FAKE_KEY in server.requests[-1].headers["authorization"]
    assert FAKE_KEY not in str(error)
    assert FAKE_KEY not in repr(error)
    assert FAKE_KEY not in "".join(traceback.format_exception(error))
    assert error.__cause__ is None
    assert error.__suppress_context__
    assert FAKE_KEY not in error.diagnostic
    # Python still keeps the SDK error on __context__, and its request holds the key; this is
    # why docs/SECURITY.md says never to log or show it.
    assert FAKE_KEY in error.__context__.request.headers["authorization"]


def test_translate_error_handles_a_bare_api_error():
    """An SDK error with no status (e.g. an unreadable response) maps to the generic error."""
    request = httpx2.Request("POST", CHAT_URL)
    error = llm.translate_error(openai.APIError("odd response", request, body=None))
    assert type(error) is llm.LLMServiceError
    assert error.status_code is None


def test_mapped_errors_lets_other_exceptions_through():
    """Errors that are not from the OpenAI SDK are not swallowed or renamed."""
    with pytest.raises(KeyError), llm.mapped_errors():
        raise KeyError("not an API error")


class _Answer(BaseModel):
    """A tiny structured-output schema for the structured-reply tests."""

    text: str


class _UnknownMessage(BaseMessage):
    """A message type langchain-openai cannot convert, standing in for a bug in our code."""

    type: str = "unknown"


def _call_chat(client: httpx2.Client) -> None:
    """Make one chat call through the given client."""
    llm.build_chat_model(api_key=FAKE_KEY, http_client=client).invoke("Hi")


def _call_embeddings(client: httpx2.Client) -> None:
    """Make one embedding call through the given client."""
    llm.build_embeddings(api_key=FAKE_KEY, http_client=client).embed_query("protein")


@pytest.mark.parametrize("call", [_call_chat, _call_embeddings], ids=["chat", "embeddings"])
@pytest.mark.parametrize("content", [b"", b" ", b'{"choices": ['], ids=["empty", "blank", "cut"])
def test_unreadable_200_body_maps_to_unavailable(call, content):
    """A 200 reply whose JSON body is empty or cut off becomes ServiceUnavailableError."""
    reply = httpx2.Response(200, content=content, headers={"content-type": "application/json"})
    client = httpx2.Client(transport=httpx2.MockTransport(lambda request: reply))
    with pytest.raises(llm.ServiceUnavailableError) as excinfo, llm.mapped_errors():
        call(client)
    assert excinfo.value.diagnostic.startswith("JSONDecodeError in json.")


def test_reply_cut_off_by_the_token_limit_maps_to_its_own_error():
    """Structured output that stops at the token limit becomes ReplyCutOffError, not a crash."""
    body = {**CHAT_OK, "choices": [{**CHAT_OK["choices"][0], "finish_reason": "length"}]}
    server = Recorder(body=body)
    structured = _chat(server).with_structured_output(_Answer)
    with pytest.raises(llm.ReplyCutOffError) as excinfo, llm.mapped_errors():
        structured.invoke("Hi")
    assert str(excinfo.value) == llm.ReplyCutOffError.user_message
    assert excinfo.value.diagnostic.startswith("LengthFinishReasonError")


@pytest.mark.parametrize(
    "error",
    [openai.ContentFilterFinishReasonError(), openai.OpenAIError("some SDK failure")],
    ids=["content-filter", "bare-sdk-error"],
)
def test_sdk_errors_outside_api_error_are_mapped(error):
    """SDK errors that are not APIError (content filter, a bare OpenAIError) get the generic one."""
    with pytest.raises(llm.LLMServiceError) as excinfo, llm.mapped_errors():
        raise error
    assert str(excinfo.value) == llm.LLMError.user_message


def test_our_bug_raised_inside_langchain_keeps_a_diagnostic():
    """A bad message type raised inside langchain-openai is mapped but says where it came from."""
    server = Recorder(body=CHAT_OK)
    with pytest.raises(llm.ServiceUnavailableError) as excinfo, llm.mapped_errors():
        _chat(server).invoke([_UnknownMessage(content="Hi")])
    assert excinfo.value.diagnostic.startswith("TypeError in langchain_openai.")
    assert not server.requests


def test_status_error_diagnostic_names_the_sdk_error():
    """A mapped HTTP error carries the SDK error's type as its diagnostic."""
    server = Recorder(status=401, body=_error_body(401))
    with pytest.raises(llm.InvalidAPIKeyError) as excinfo, llm.mapped_errors():
        _chat(server).invoke("Hi")
    assert excinfo.value.diagnostic.startswith("OpenAIAuthenticationError")


@pytest.mark.parametrize(
    "content",
    ['{"other": "field"}', "not JSON at all", '{"text": 42}'],
    ids=["missing-field", "not-json", "wrong-type"],
)
def test_structured_reply_that_breaks_the_schema_maps_to_invalid_reply(content):
    """A structured reply that fails schema validation is InvalidReplyError, not an outage."""
    message = {"role": "assistant", "content": content}
    body = {**CHAT_OK, "choices": [{**CHAT_OK["choices"][0], "message": message}]}
    server = Recorder(body=body)
    structured = _chat(server).with_structured_output(_Answer)
    with pytest.raises(llm.InvalidReplyError) as excinfo, llm.mapped_errors():
        structured.invoke("Hi")
    assert not isinstance(excinfo.value, llm.ServiceUnavailableError)
    assert str(excinfo.value) == llm.InvalidReplyError.user_message
    assert content not in str(excinfo.value)
    assert excinfo.value.diagnostic.startswith("ValidationError in pydantic.")


def test_validation_error_from_our_own_code_passes_through():
    """A Pydantic ValidationError from our code inside the block is not renamed."""
    with pytest.raises(pydantic.ValidationError), llm.mapped_errors():
        _Answer.model_validate({"other": "field"})


@pytest.mark.parametrize(
    ("message", "raised_by"),
    [
        ({"role": "assistant", "content": None, "refusal": "I can't help."}, "OpenAIRefusalError"),
        ({"role": "assistant", "content": ""}, "ValueError"),
        ({"role": "assistant", "content": None}, "ValueError"),
    ],
    ids=["refusal", "empty-content", "null-content"],
)
def test_refused_or_empty_structured_reply_maps_to_invalid_reply(message, raised_by):
    """A refusal or an empty structured reply is InvalidReplyError, so a caller can fall back."""
    body = {**CHAT_OK, "choices": [{**CHAT_OK["choices"][0], "message": message}]}
    structured = _chat(Recorder(body=body)).with_structured_output(_Answer)
    with pytest.raises(llm.InvalidReplyError) as excinfo, llm.mapped_errors():
        structured.invoke("Hi")
    assert str(excinfo.value) == llm.InvalidReplyError.user_message
    assert "help" not in str(excinfo.value)
    assert excinfo.value.diagnostic.startswith(f"{raised_by} in langchain_openai.")
