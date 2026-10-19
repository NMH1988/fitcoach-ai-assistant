"""Chat and embedding clients for OpenRouter, and the mapping of API errors to user messages."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src import config


class LLMError(RuntimeError):
    """A model or embedding call failed; `str()` is a fixed message safe to show the user."""

    user_message = "Something went wrong while calling the model service. Please try again."

    def __init__(self, status_code: int | None = None) -> None:
        """Store the HTTP status (if any) and use the class's fixed text as the message."""
        super().__init__(self.user_message)
        self.status_code = status_code


class InvalidAPIKeyError(LLMError):
    """OpenRouter rejected the API key (HTTP 401)."""

    user_message = (
        "The OpenRouter API key was rejected. Check the key in .streamlit/secrets.toml "
        f"or the {config.API_KEY_NAME} environment variable."
    )


class OutOfCreditError(LLMError):
    """The OpenRouter account has no credit left (HTTP 402)."""

    user_message = "The OpenRouter account is out of credit. Add credit, then try again."


class RateLimitedError(LLMError):
    """OpenRouter or the model provider is rate limiting us (HTTP 429), even after retries."""

    user_message = "The model service is getting too many requests. Wait a minute and try again."


class LLMTimeoutError(LLMError):
    """The request timed out on our side or the server's (HTTP 408), even after retries."""

    user_message = "The model service took too long to answer. Please try again."


class ServiceUnavailableError(LLMError):
    """OpenRouter or the provider failed (HTTP 5xx, or an error inside a 200 reply)."""

    user_message = "The model service is temporarily unavailable. Try again in a few minutes."


class LLMConnectionError(LLMError):
    """The model service could not be reached at all."""

    user_message = "Could not reach the model service. Check the internet connection and try again."


class LLMServiceError(LLMError):
    """Any other API error, e.g. a rejected request (HTTP 400, 403, 404)."""


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
# with no "data". OpenRouter sends such replies when the upstream provider fails mid-request.
_CLIENT_PACKAGES = frozenset({"langchain_openai", "openai"})


def translate_error(exc: openai.APIError) -> LLMError:
    """Return the user-facing LLMError for an OpenAI SDK error, keeping only its status code."""
    # APITimeoutError is a subclass of APIConnectionError, so it must be checked first.
    if isinstance(exc, openai.APITimeoutError):
        return LLMTimeoutError()
    if isinstance(exc, openai.APIConnectionError):
        return LLMConnectionError()
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        if status >= 500:
            return ServiceUnavailableError(status)
        return _STATUS_ERRORS.get(status, LLMServiceError)(status)
    return LLMServiceError()


def _raised_by_client(exc: BaseException) -> bool:
    """Return True if the exception was raised inside the OpenAI SDK or langchain-openai."""
    tb = exc.__traceback__
    if tb is None:
        return False
    while tb.tb_next is not None:
        tb = tb.tb_next
    module = tb.tb_frame.f_globals.get("__name__", "")
    return module.split(".")[0] in _CLIENT_PACKAGES


@contextmanager
def mapped_errors() -> Iterator[None]:
    """Turn API errors and malformed replies raised inside the block into LLMError.

    The SDK's messages quote the response body, so `from None` keeps them out of tracebacks.
    The original error is still on `__context__` (Python sets it inside an `except`) and its
    request holds the key: never log or show `__context__`.
    """
    try:
        yield
    except openai.APIError as exc:
        raise translate_error(exc) from None
    except (ValueError, KeyError, TypeError) as exc:
        # Only replies the client could not read; the same errors from the caller's code pass.
        if not _raised_by_client(exc):
            raise
        raise ServiceUnavailableError() from None


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
        http_client=http_client,
    )


def build_embeddings(*, api_key: str | None = None, http_client: Any = None) -> OpenAIEmbeddings:
    """Build the OpenAIEmbeddings client for the configured embedding model on OpenRouter."""
    return OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=api_key or config.get_api_key(),
        # Send raw text: by default the client sends token arrays, which OpenRouter may reject.
        check_embedding_ctx_length=False,
        request_timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
        http_client=http_client,
    )
