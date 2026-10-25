"""Chat and embedding clients for OpenRouter, and the mapping of API errors to user messages."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import openai
import pydantic
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_openai.chat_models.base import OpenAIRefusalError

from src import config


class LLMError(RuntimeError):
    """A model or embedding call failed; `str()` is a fixed message safe to show the user."""

    user_message = "Something went wrong while calling the model service. Please try again."
    # The key of the message in src/i18n.py, so the UI shows it in the chosen language (T7.1).
    code = "llm.error"

    def __init__(self, status_code: int | None = None, diagnostic: str | None = None) -> None:
        """Store the HTTP status and a safe-to-log diagnostic; the message is the fixed text."""
        super().__init__(self.user_message)
        self.status_code = status_code
        # Error type and where it was raised, never its message: safe to log, unlike __context__.
        self.diagnostic = diagnostic


class InvalidAPIKeyError(LLMError):
    """OpenRouter rejected the API key (HTTP 401)."""

    code = "llm.invalid_key"
    user_message = (
        "The OpenRouter API key was rejected. Check the key in .streamlit/secrets.toml "
        f"or the {config.API_KEY_NAME} environment variable."
    )


class OutOfCreditError(LLMError):
    """The OpenRouter account has no credit left (HTTP 402)."""

    code = "llm.out_of_credit"
    user_message = "The OpenRouter account is out of credit. Add credit, then try again."


class RateLimitedError(LLMError):
    """OpenRouter or the model provider is rate limiting us (HTTP 429), even after retries."""

    code = "llm.rate_limited"
    user_message = "The model service is getting too many requests. Wait a minute and try again."


class LLMTimeoutError(LLMError):
    """The request timed out on our side or the server's (HTTP 408), even after retries."""

    code = "llm.timeout"
    user_message = "The model service took too long to answer. Please try again."


class ServiceUnavailableError(LLMError):
    """OpenRouter or the provider failed (HTTP 5xx, or an error inside a 200 reply)."""

    code = "llm.unavailable"
    user_message = "The model service is temporarily unavailable. Try again in a few minutes."


class LLMConnectionError(LLMError):
    """The model service could not be reached at all."""

    code = "llm.connection"
    user_message = "Could not reach the model service. Check the internet connection and try again."


class ReplyCutOffError(LLMError):
    """The reply hit the token limit before it was finished (an answer or structured output)."""

    code = "llm.cut_off"
    user_message = "The answer was cut off before it was finished. Please try again."


class InvalidReplyError(LLMError):
    """A structured reply was unusable (schema mismatch, refusal, empty); callers may fall back."""

    code = "llm.invalid_reply"
    user_message = "The model's answer was not in the expected format. Please try again."


class LLMServiceError(LLMError):
    """Any other SDK error, e.g. a rejected request (HTTP 400, 403, 404) or a content filter."""


# HTTP status -> error class; 5xx is handled by range in translate_error().
_STATUS_ERRORS: dict[int, type[LLMError]] = {
    401: InvalidAPIKeyError,
    402: OutOfCreditError,
    # OpenRouter answers 408 when the upstream request timed out.
    408: LLMTimeoutError,
    429: RateLimitedError,
}

# Packages whose code raises ValueError, KeyError or TypeError for a malformed reply: langchain
# for a 200 reply that carries an "error" field or no "choices", the embeddings client for one
# with no "data", the SDK (through json) for an empty or cut-off body. OpenRouter sends such
# replies when the upstream provider fails mid-request. The SDK also validates a structured
# reply with Pydantic, whose ValidationError is a ValueError: that one is a bad answer from the
# model, not an outage, so it gets InvalidReplyError.
_CLIENT_PACKAGES = frozenset({"langchain_openai", "openai"})
# langchain-openai's parser for structured output; it raises ValueError for an empty reply.
_STRUCTURED_PARSER = "_oai_structured_outputs_parser"


def error_diagnostic(exc: BaseException) -> str:
    """Return the error's type and the function that raised it, without its message."""
    tb = exc.__traceback__
    if tb is None:
        return type(exc).__name__
    while tb.tb_next is not None:
        tb = tb.tb_next
    module = tb.tb_frame.f_globals.get("__name__", "?")
    return f"{type(exc).__name__} in {module}.{tb.tb_frame.f_code.co_name}"


def translate_error(exc: openai.OpenAIError) -> LLMError:
    """Return the user-facing LLMError for an OpenAI SDK error, keeping only its status code."""
    diagnostic = error_diagnostic(exc)
    # APITimeoutError is a subclass of APIConnectionError, so it must be checked first.
    if isinstance(exc, openai.APITimeoutError):
        return LLMTimeoutError(diagnostic=diagnostic)
    if isinstance(exc, openai.APIConnectionError):
        return LLMConnectionError(diagnostic=diagnostic)
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        error_class = ServiceUnavailableError if status >= 500 else _STATUS_ERRORS.get(status)
        return (error_class or LLMServiceError)(status, diagnostic)
    if isinstance(exc, openai.LengthFinishReasonError):
        return ReplyCutOffError(diagnostic=diagnostic)
    return LLMServiceError(diagnostic=diagnostic)


def _is_invalid_reply(exc: BaseException) -> bool:
    """Return True for a structured reply that failed its schema or came back empty."""
    if isinstance(exc, pydantic.ValidationError):
        return True
    tb = exc.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    return tb is not None and tb.tb_frame.f_code.co_name == _STRUCTURED_PARSER


def _passed_through_client(exc: BaseException) -> bool:
    """Return True if any frame between the `with` block and the raise is in a client package."""
    tb = exc.__traceback__
    while tb is not None:
        module = tb.tb_frame.f_globals.get("__name__", "")
        if module.split(".")[0] in _CLIENT_PACKAGES:
            return True
        tb = tb.tb_next
    return False


@contextmanager
def mapped_errors() -> Iterator[None]:
    """Turn SDK errors and malformed replies raised inside the block into LLMError."""
    # The SDK's messages quote the response body, so `from None` keeps them out of tracebacks.
    # The original stays on `__context__` (Python sets it inside an `except`) and its request
    # holds the key: never log or show `__context__`; log `LLMError.diagnostic` instead.
    try:
        yield
    except openai.OpenAIError as exc:
        raise translate_error(exc) from None
    except OpenAIRefusalError as exc:
        # The model declined to answer; its message is the refusal text.
        raise InvalidReplyError(diagnostic=error_diagnostic(exc)) from None
    except (ValueError, KeyError, TypeError) as exc:
        # Only errors raised while the client handled the call; the caller's own pass through.
        # A bug of ours that langchain raises (e.g. a bad message type) also lands here, which
        # is why the diagnostic is kept.
        if not _passed_through_client(exc):
            raise
        # Its message quotes the model's reply, so it is mapped (and hidden) too.
        if _is_invalid_reply(exc):
            raise InvalidReplyError(diagnostic=error_diagnostic(exc)) from None
        raise ServiceUnavailableError(diagnostic=error_diagnostic(exc)) from None


def build_chat_model(
    model: str = config.DEFAULT_ANSWER_MODEL,
    max_tokens: int = config.DEFAULT_MAX_TOKENS,
    *,
    api_key: str | None = None,
    http_client: Any = None,
) -> ChatOpenAI:
    """Build a ChatOpenAI client for an allowed model on OpenRouter, with capped max_tokens."""
    if model not in config.ALLOWED_MODELS:
        raise ValueError(f"Model {model!r} is not on the allowed list.")
    if max_tokens < 1:
        raise ValueError("max_tokens must be at least 1.")
    return ChatOpenAI(
        model=model,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=api_key or config.get_api_key(),
        max_tokens=min(max_tokens, config.MAX_TOKENS_CAP),
        reasoning_effort=config.REASONING_EFFORT,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
        # OpenRouter's chat completions endpoint; never let the model name switch the API.
        use_responses_api=False,
        # Token use of streamed replies (T5.1): langchain turns it on only for OpenAI's own URL.
        stream_usage=True,
        http_client=http_client,
    )


class CountingEmbeddings(OpenAIEmbeddings):
    """OpenAIEmbeddings that can also return the input tokens the API reports (T5.1)."""

    # The client is shared by all sessions (views/resources.py caches it), so the count is
    # returned with the vectors, never kept on the client.

    def embed_with_usage(self, texts: list[str]) -> tuple[list[list[float]], int | None]:
        """Embed the texts as embed_documents does; also return the tokens, None if unreported."""
        # The parent's raw-text path (check_embedding_ctx_length=False, set by build_embeddings),
        # which drops the response's "usage".
        if self.check_embedding_ctx_length:
            return self.embed_documents(texts), None
        self._ensure_sync_client_available()
        vectors: list[list[float]] = []
        tokens: int | None = 0
        for start in range(0, len(texts), self.chunk_size):
            response = self.client.create(
                input=texts[start : start + self.chunk_size], **self._invocation_params
            )
            if not isinstance(response, dict):
                response = response.model_dump()
            vectors.extend(item["embedding"] for item in response["data"])
            reported = (response.get("usage") or {}).get("prompt_tokens")
            # One batch without a count makes the whole count unknown, never too low.
            if tokens is None or isinstance(reported, bool) or not isinstance(reported, int):
                tokens = None
            else:
                tokens += reported
        return vectors, tokens


def build_embeddings(*, api_key: str | None = None, http_client: Any = None) -> CountingEmbeddings:
    """Build the embeddings client for the configured embedding model on OpenRouter."""
    return CountingEmbeddings(
        model=config.EMBEDDING_MODEL,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=api_key or config.get_api_key(),
        # Send raw text: by default the client sends token arrays, which OpenRouter may reject.
        check_embedding_ctx_length=False,
        request_timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
        http_client=http_client,
    )
