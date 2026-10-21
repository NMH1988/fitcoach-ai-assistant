"""Live check O5 for T1.2 and T5.1: real chat calls and one real embedding call via OpenRouter.

Run by the owner from the repo root, with the key set up as in the README:

    python scripts/live_check_llm.py

It costs a fraction of a cent and never prints the key. Since T5.1 it makes two chat calls: one
plain call, and one streamed through `chat.stream_reply()` with a usage recorder, exactly as the
app's answer rounds are, so the check shows whether OpenRouter's stream reports the token use once
(not twice, not missing). For each it prints the cost as the app computes it (OpenRouter's prices
x the tokens) next to the cost and native tokens OpenRouter itself records for that call
(GET /api/v1/generation), to check how reasoning tokens are billed. Record the output in
docs/TESTING.md.
"""

import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from decimal import Decimal
from functools import partial
from typing import Any

import httpx2
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src import chat, config, llm, usage

CHAT_PROMPT = "In one short sentence, what is dietary protein?"
EMBEDDING_TEXT = "protein intake for muscle gain"
# OpenRouter records a call's cost a moment after the reply: ask a few times before giving up.
GENERATION_URL = f"{config.OPENROUTER_BASE_URL}/generation"
GENERATION_ATTEMPTS = 5
GENERATION_WAIT_SECONDS = 2
# One generation record is a few KB; anything far bigger is not one.
GENERATION_MAX_BYTES = 1_000_000
# The key goes in this request, so it never follows a redirect to another host.
_OPENER = urllib.request.build_opener(usage.NoRedirect())
# OpenRouter's ID of a call, as each chunk of a streamed reply carries it.
_GENERATION_ID = re.compile(rb'"id"\s*:\s*"(gen-[A-Za-z0-9_-]{1,100})"')
# How much of a streamed reply is searched for the ID: it is in the first chunk.
_ID_SEARCH_BYTES = 8192
STREAM_STEP = "live check (streamed)"


class LiveCheckError(RuntimeError):
    """A call succeeded but returned nothing usable."""


def run_checks(chat_model: ChatOpenAI, embeddings: OpenAIEmbeddings) -> tuple[list[str], AIMessage]:
    """Make one chat call and one embedding call; return one result line each and the reply."""
    with llm.mapped_errors():
        reply = chat_model.invoke(CHAT_PROMPT)
        vector = embeddings.embed_query(EMBEDDING_TEXT)
    if not reply.text.strip():
        raise LiveCheckError("The chat model returned an empty reply (token budget used up?).")
    if not vector:
        raise LiveCheckError("The embedding call returned an empty vector.")
    usage_data = reply.usage_metadata or {}
    # Evidence that OpenRouter honours the token cap (sent as max_completion_tokens).
    if usage_data.get("output_tokens", 0) > chat_model.max_tokens:
        raise LiveCheckError("The reply used more tokens than max_tokens allows.")
    reasoning = usage_data.get("output_token_details", {}).get("reasoning", "n/a")
    lines = [
        f"chat: {chat_model.model_name} ok, {len(reply.text)} characters, "
        f"tokens in {usage_data.get('input_tokens', 'n/a')} / "
        f"out {usage_data.get('output_tokens', 'n/a')} (reasoning {reasoning})",
        f"embedding: {embeddings.model} ok, {len(vector)} dimensions",
    ]
    return lines, reply


class _IdStream(httpx2.SyncByteStream):
    """A response body passed on unchanged, noting the first generation ID found in it."""

    def __init__(self, inner: Any, found: list[str]) -> None:
        """Keep the real body and the list the ID is added to."""
        self._inner = inner
        self._found = found
        self._head = b""

    def __iter__(self) -> Iterator[bytes]:
        """Yield the body's chunks, searching its start for the ID."""
        for part in self._inner:
            if len(self._head) < _ID_SEARCH_BYTES and not self._found:
                self._head += part
                match = _GENERATION_ID.search(self._head)
                if match:
                    self._found.append(match.group(1).decode("ascii"))
            yield part

    def close(self) -> None:
        """Close the real body."""
        self._inner.close()


class GenerationIdTransport(httpx2.BaseTransport):
    """Sends requests through the real transport and notes the generation ID of each reply."""

    # langchain-openai drops the ID of a streamed reply, which /api/v1/generation needs.

    def __init__(self, inner: httpx2.BaseTransport | None = None) -> None:
        """Keep the real transport; the IDs found go into `ids`, in order."""
        self._inner = inner or httpx2.HTTPTransport()
        self.ids: list[str] = []

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        """Send the request and return the reply with its body watched for the ID."""
        response = self._inner.handle_request(request)
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            stream=_IdStream(response.stream, self.ids),
            extensions=response.extensions,
            request=request,
        )

    def close(self) -> None:
        """Close the real transport."""
        self._inner.close()


def stream_check(chat_model: ChatOpenAI) -> tuple[list[str], usage.CallUsage | None]:
    """Stream one reply as the app's answer step does; return its line and the recorded usage."""
    recorder = usage.UsageRecorder()
    record = partial(recorder.add_chat, STREAM_STEP, chat_model.model_name)
    reply = chat.stream_reply(chat_model, [HumanMessage(CHAT_PROMPT)], None, record)
    if not reply.text.strip():
        raise LiveCheckError("The streamed reply was empty (token budget used up?).")
    if not recorder.calls:
        return [
            "chat (streamed): ok, but the stream reported no token use: the app would count no "
            "answer round"
        ], None
    [call] = recorder.calls
    line = (
        f"chat (streamed, as the app's answer rounds): {len(reply.text)} characters, recorded "
        f"tokens in {call.input_tokens} / out {call.output_tokens} "
        f"(reasoning {call.reasoning_tokens})"
    )
    return [line], call


def fetch_generation(
    generation_id: str,
    api_key: str,
    opener: Callable[..., Any] = _OPENER.open,
    sleep: Callable[[float], None] = time.sleep,
) -> dict | None:
    """Return OpenRouter's record of one call (cost, native tokens), or None if not available."""
    url = f"{GENERATION_URL}?{urllib.parse.urlencode({'id': generation_id})}"
    for attempt in range(GENERATION_ATTEMPTS):
        if attempt:
            sleep(GENERATION_WAIT_SECONDS)
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with opener(request, timeout=config.PRICE_TIMEOUT_SECONDS) as response:
                body = response.read(GENERATION_MAX_BYTES + 1)
            if len(body) > GENERATION_MAX_BYTES:
                return None
            data = json.loads(body).get("data")
        except urllib.error.HTTPError as exc:
            # 404 until OpenRouter has recorded the call; any other status will not change.
            if exc.code == 404:
                continue
            return None
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            RecursionError,
            AttributeError,
        ):
            # Never the error's text: it could quote the request, which holds the key.
            return None
        return data if isinstance(data, dict) else None
    return None


def _dollars(value: Any) -> str:
    """Return a dollar amount with 8 decimals, or "n/a" for one that is not a number."""
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return "n/a"
    return f"${Decimal(str(value)):.8f}"


def reply_usage(reply: AIMessage, model: str) -> usage.CallUsage | None:
    """Return a plain reply's usage as the app records it, or None if it reported none."""
    recorder = usage.UsageRecorder()
    recorder.add_chat("live check", model, reply.usage_metadata)
    return recorder.calls[0] if recorder.calls else None


def cost_lines(
    call: usage.CallUsage | None,
    prices: dict | None,
    generation: dict | None,
    label: str = "",
) -> list[str]:
    """Return the app's cost of a call and the cost and native tokens OpenRouter recorded."""
    ours = usage.call_cost(call, prices) if call is not None else None
    lines = [f"cost (app{label}): {_dollars(ours)} from OpenRouter's prices and the tokens"]
    if generation is None:
        lines.append(
            f"cost (OpenRouter{label}): not available (GET /api/v1/generation gave no record)"
        )
        return lines
    tokens = ", ".join(
        f"{name} {generation.get(f'native_tokens_{name}', 'n/a')}"
        for name in ("prompt", "completion", "reasoning")
    )
    lines.append(
        f"cost (OpenRouter{label}): {_dollars(generation.get('total_cost'))}, "
        f"native tokens: {tokens}"
    )
    return lines


def read_prices() -> dict | None:
    """Return the app's model prices from OpenRouter, or None if they could not be read."""
    try:
        return usage.fetch_prices()
    except usage.PriceError:
        return None


def build_streaming_model() -> tuple[ChatOpenAI, GenerationIdTransport]:
    """Build the answer model's client with a transport that notes each reply's generation ID."""
    # Through build_chat_model, so the allowlist and the token cap apply as in the app.
    transport = GenerationIdTransport()
    return llm.build_chat_model(http_client=httpx2.Client(transport=transport)), transport


def main() -> int:
    """Run the live check, print the results or the mapped error, and return the exit code."""
    try:
        chat_model = llm.build_chat_model()
        lines, reply = run_checks(chat_model, llm.build_embeddings())
        streaming_model, transport = build_streaming_model()
        stream_lines, stream_call = stream_check(streaming_model)
        api_key = config.get_api_key()
        generation_id = reply.response_metadata.get("id")
        generation = (
            fetch_generation(generation_id, api_key) if isinstance(generation_id, str) else None
        )
        stream_generation = fetch_generation(transport.ids[0], api_key) if transport.ids else None
    except (config.MissingAPIKeyError, llm.LLMError, LiveCheckError) as exc:
        print(f"Live check failed: {exc}", file=sys.stderr)
        return 1
    prices = read_prices()
    lines += cost_lines(reply_usage(reply, chat_model.model_name), prices, generation)
    lines += stream_lines
    lines += cost_lines(stream_call, prices, stream_generation, ", streamed")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
