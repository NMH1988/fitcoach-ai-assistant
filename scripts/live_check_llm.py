"""Live check O5 for T1.2 and T5.1: one real chat call and one real embedding call via OpenRouter.

Run by the owner from the repo root, with the key set up as in the README:

    python scripts/live_check_llm.py

It costs a fraction of a cent and never prints the key. Since T5.1 it also prints the chat call's
cost as the app computes it (OpenRouter's prices x the reported tokens) next to the cost OpenRouter
itself records for that call (GET /api/v1/generation), to check how reasoning tokens are billed.
Record the output in docs/TESTING.md.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src import config, llm, usage

CHAT_PROMPT = "In one short sentence, what is dietary protein?"
EMBEDDING_TEXT = "protein intake for muscle gain"
# OpenRouter records a call's cost a moment after the reply: ask a few times before giving up.
GENERATION_URL = f"{config.OPENROUTER_BASE_URL}/generation"
GENERATION_ATTEMPTS = 5
GENERATION_WAIT_SECONDS = 2
# The key goes in this request, so it never follows a redirect to another host.
_OPENER = urllib.request.build_opener(usage.NoRedirect())


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
                data = json.load(response).get("data")
        except urllib.error.HTTPError as exc:
            # 404 until OpenRouter has recorded the call; any other status will not change.
            if exc.code == 404:
                continue
            return None
        except OSError, ValueError, AttributeError:
            # Never the error's text: it could quote the request, which holds the key.
            return None
        return data if isinstance(data, dict) else None
    return None


def _dollars(value: Any) -> str:
    """Return a dollar amount with 8 decimals, or "n/a" for one that is not a number."""
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return "n/a"
    return f"${Decimal(str(value)):.8f}"


def cost_lines(
    reply: AIMessage, model: str, prices: dict | None, generation: dict | None
) -> list[str]:
    """Return the app's cost of the reply and the cost and native tokens OpenRouter recorded."""
    recorder = usage.UsageRecorder()
    recorder.add_chat("live check", model, reply.usage_metadata)
    ours = usage.call_cost(recorder.calls[0], prices) if recorder.calls else None
    lines = [f"cost (app): {_dollars(ours)} from OpenRouter's prices and the reported tokens"]
    if generation is None:
        lines.append("cost (OpenRouter): not available (GET /api/v1/generation gave no record)")
        return lines
    tokens = ", ".join(
        f"{name} {generation.get(f'native_tokens_{name}', 'n/a')}"
        for name in ("prompt", "completion", "reasoning")
    )
    lines.append(
        f"cost (OpenRouter): {_dollars(generation.get('total_cost'))}, native tokens: {tokens}"
    )
    return lines


def read_prices() -> dict | None:
    """Return the app's model prices from OpenRouter, or None if they could not be read."""
    try:
        return usage.fetch_prices()
    except usage.PriceError:
        return None


def main() -> int:
    """Run the live check, print the results or the mapped error, and return the exit code."""
    try:
        chat_model = llm.build_chat_model()
        lines, reply = run_checks(chat_model, llm.build_embeddings())
        generation_id = reply.response_metadata.get("id")
        generation = (
            fetch_generation(generation_id, config.get_api_key())
            if isinstance(generation_id, str)
            else None
        )
    except (config.MissingAPIKeyError, llm.LLMError, LiveCheckError) as exc:
        print(f"Live check failed: {exc}", file=sys.stderr)
        return 1
    lines += cost_lines(reply, chat_model.model_name, read_prices(), generation)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
