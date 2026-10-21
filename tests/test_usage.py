"""Tests for src/usage.py: recording tokens, reading prices, the day cache, cost and its display."""

import io
import json
import urllib.error
from decimal import Decimal

import pytest

from src import config, usage
from src.usage import (
    CallUsage,
    ModelPrice,
    PriceCache,
    PriceError,
    TurnUsage,
    UsageRecorder,
)

ANSWER = config.DEFAULT_ANSWER_MODEL
REWRITE = config.QUERY_TRANSLATION_MODEL
EMBEDDING = config.EMBEDDING_MODEL
# Made-up round prices, in dollars per token, so the expected costs are easy to check by hand.
PRICES = {
    ANSWER: ModelPrice(Decimal("0.000001"), Decimal("0.00001"), Decimal("0.0000001")),
    REWRITE: ModelPrice(Decimal("0.0000001"), Decimal("0.000001")),
    EMBEDDING: ModelPrice(Decimal("0.00000001"), Decimal("0")),
}


# --- Recording the calls of a turn ----------------------------------------------------------------


def test_a_chat_call_records_its_tokens_cached_input_and_reasoning():
    """The recorder keeps langchain's counts: input, output, cached input and reasoning."""
    recorder = UsageRecorder()
    recorder.add_chat(
        "Answer, round 1",
        ANSWER,
        {
            "input_tokens": 2000,
            "output_tokens": 500,
            "total_tokens": 2500,
            "input_token_details": {"cache_read": 1024},
            "output_token_details": {"reasoning": 300},
        },
    )
    assert recorder.calls == [CallUsage("Answer, round 1", ANSWER, 2000, 500, 1024, 300)]
    assert recorder.calls[0].tokens == 2500


def test_calls_are_kept_in_order_and_unreported_ones_left_out():
    """Each call is kept in the order made; a call that reported nothing adds no row."""
    recorder = UsageRecorder()
    recorder.add_chat(
        "Rewrite", REWRITE, {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    )
    recorder.add_chat("Answer", ANSWER, None)
    recorder.add_embedding("Search", EMBEDDING, None)
    recorder.add_embedding("Search", EMBEDDING, 12)
    assert [(call.step, call.tokens) for call in recorder.calls] == [
        ("Rewrite", 15),
        ("Search", 12),
    ]


@pytest.mark.parametrize("value", [-5, "12", 1.5, True, None])
def test_unusable_counts_become_zero(value):
    """A negative or non-integer count from the provider adds nothing."""
    recorder = UsageRecorder()
    recorder.add_chat("Answer", ANSWER, {"input_tokens": value, "output_tokens": 3})
    assert recorder.calls[0].input_tokens == 0
    assert recorder.calls[0].output_tokens == 3


def test_model_name_reads_the_client_or_says_unknown():
    """The model name comes from the client; a client without one is "unknown" (no price)."""

    class Client:
        """A stand-in client with a model name."""

        model_name = ANSWER

    assert usage.model_name(Client()) == ANSWER
    assert usage.model_name(object()) == "unknown"


# --- Prices from OpenRouter's model lists ---------------------------------------------------------


def _models(*entries: dict) -> dict:
    """Return a model list body as OpenRouter sends it."""
    return {"data": list(entries)}


def _entry(model: str, **pricing) -> dict:
    """Return one model of the list with this pricing."""
    return {"id": model, "name": "Made-up", "pricing": pricing}


def test_prices_are_read_as_exact_decimals():
    """Prices are strings of dollars per token; they are read exactly, cached input too."""
    payload = _models(
        _entry(ANSWER, prompt="0.00000025", completion="0.000002", input_cache_read="0.000000025"),
        _entry(REWRITE, prompt="0.00000005", completion="0.0000004"),
        _entry("someone/other-model", prompt="1", completion="1"),
    )
    prices = usage.parse_prices(payload, config.ALLOWED_MODELS)
    assert prices == {
        ANSWER: ModelPrice(Decimal("0.00000025"), Decimal("0.000002"), Decimal("0.000000025")),
        REWRITE: ModelPrice(Decimal("0.00000005"), Decimal("0.0000004"), None),
    }


@pytest.mark.parametrize(
    "pricing",
    [
        {"prompt": "-1", "completion": "-1"},
        {"prompt": "NaN", "completion": "0.000001"},
        {"prompt": "Infinity", "completion": "0.000001"},
        {"prompt": "1e999999", "completion": "0.000001"},
        {"prompt": "0.0100001", "completion": "0.000001"},
        {"prompt": "cheap", "completion": "0.000001"},
        {"prompt": True, "completion": "0.000001"},
        {"prompt": None, "completion": "0.000001"},
        {"prompt": ["0.000001"], "completion": "0.000001"},
        {"completion": "0.000001"},
        "free",
    ],
    ids=str,
)
def test_an_unusable_price_leaves_the_model_out(pricing):
    """A price that is not a finite number of 0 or more is not used: the cost is unknown."""
    entry = {"id": ANSWER, "pricing": pricing}
    assert usage.parse_prices(_models(entry), [ANSWER]) == {}


def test_the_highest_accepted_price_is_kept():
    """A price of exactly PRICE_MAX_PER_TOKEN is still used."""
    entry = _entry(ANSWER, prompt=config.PRICE_MAX_PER_TOKEN, completion="0")
    assert usage.parse_prices(_models(entry), [ANSWER])[ANSWER].prompt == Decimal("0.01")


def test_an_unusable_cache_price_falls_back_to_the_input_price():
    """A bad cached-input price is dropped; cached tokens are then priced as input."""
    payload = _models(_entry(ANSWER, prompt="0.000001", completion="0.00001", input_cache_read="x"))
    assert usage.parse_prices(payload, [ANSWER])[ANSWER].cache_read is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "data",
        {},
        {"data": "x"},
        {"data": [1, None, {"id": 3}]},
        {"data": [{"id": [ANSWER], "pricing": {"prompt": "0.000001", "completion": "0.000001"}}]},
        {"data": [{"id": {"x": 1}, "pricing": {"prompt": "0.000001", "completion": "0.000001"}}]},
    ],
    ids=str,
)
def test_a_malformed_list_gives_no_prices(payload):
    """A body that is not a model list gives no prices, without raising."""
    assert usage.parse_prices(payload, [ANSWER]) == {}


def test_fetch_prices_reads_both_lists():
    """Chat prices come from the models list and the embedding price from the embeddings list."""
    bodies = {
        config.CHAT_PRICES_URL: _models(_entry(ANSWER, prompt="0.000001", completion="0.000002")),
        config.EMBEDDING_PRICES_URL: _models(_entry(EMBEDDING, prompt="1e-8", completion="0")),
    }
    asked = []

    def get_json(url):
        """Return the made-up body of the URL asked for."""
        asked.append(url)
        return bodies[url]

    prices = usage.fetch_prices(get_json)
    assert asked == [config.CHAT_PRICES_URL, config.EMBEDDING_PRICES_URL]
    assert set(prices) == {ANSWER, EMBEDDING}
    assert config.CHAT_PRICES_URL == "https://openrouter.ai/api/v1/models"
    assert config.EMBEDDING_PRICES_URL == "https://openrouter.ai/api/v1/embeddings/models"


@pytest.mark.parametrize("empty", [config.CHAT_PRICES_URL, config.EMBEDDING_PRICES_URL])
def test_a_list_with_no_usable_price_is_a_failed_read(empty):
    """A list holding none of the app's models (e.g. an error sent as JSON) is not kept."""
    bodies = {
        config.CHAT_PRICES_URL: _models(_entry(ANSWER, prompt="0.000001", completion="0.000002")),
        config.EMBEDDING_PRICES_URL: _models(_entry(EMBEDDING, prompt="1e-8", completion="0")),
    }
    bodies[empty] = {"error": {"message": "temporarily unavailable"}}
    with pytest.raises(PriceError, match="no usable price"):
        usage.fetch_prices(bodies.__getitem__)


class _Response(io.BytesIO):
    """A stand-in HTTP response body that works as a context manager."""


def test_get_json_sends_no_key_and_reads_the_body(monkeypatch):
    """The price request is a plain GET with no Authorization header and a short timeout."""
    seen = {}

    def fake_open(request, timeout):
        """Record the request and answer with a small JSON body."""
        seen["request"], seen["timeout"] = request, timeout
        return _Response(json.dumps(_models()).encode())

    monkeypatch.setattr(usage._OPENER, "open", fake_open)
    assert usage._get_json(config.CHAT_PRICES_URL) == {"data": []}
    request = seen["request"]
    assert request.get_method() == "GET" and request.full_url == config.CHAT_PRICES_URL
    assert not request.has_header("Authorization")
    assert seen["timeout"] == config.PRICE_TIMEOUT_SECONDS == 5


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("offline"),
        TimeoutError("slow"),
        urllib.error.HTTPError("u", 302, "redirect refused", {}, None),
        urllib.error.HTTPError("u", 500, "server error", {}, None),
    ],
    ids=["offline", "timeout", "redirect", "500"],
)
def test_get_json_turns_network_failures_into_price_error(monkeypatch, failure):
    """Any network failure becomes PriceError with fixed text."""

    def fake_open(request, timeout):
        """Fail as the network would."""
        raise failure

    monkeypatch.setattr(usage._OPENER, "open", fake_open)
    with pytest.raises(PriceError, match="price list not read"):
        usage._get_json(config.CHAT_PRICES_URL)


@pytest.mark.parametrize(
    ("body", "message"),
    [(b"<html>", "not JSON"), (b"x" * 11, "too large")],
    ids=["not-json", "too-large"],
)
def test_get_json_refuses_a_body_that_is_not_a_small_json(monkeypatch, body, message):
    """A body that is not JSON, or larger than PRICE_MAX_BYTES, gives PriceError."""
    monkeypatch.setattr(config, "PRICE_MAX_BYTES", 10)
    monkeypatch.setattr(usage._OPENER, "open", lambda request, timeout: _Response(body))
    with pytest.raises(PriceError, match=message):
        usage._get_json(config.CHAT_PRICES_URL)


def test_get_json_refuses_json_nested_too_deeply(monkeypatch):
    """Really nested JSON (json.loads raises RecursionError) gives PriceError, not a crash."""
    body = b"[" * 100_000
    monkeypatch.setattr(usage._OPENER, "open", lambda request, timeout: _Response(body))
    with pytest.raises(PriceError, match="not JSON"):
        usage._get_json(config.CHAT_PRICES_URL)


def test_redirects_are_not_followed():
    """The opener's redirect handler refuses every redirect, so only OpenRouter is reached."""
    handler = usage.NoRedirect()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://example.com") is None


# --- The day cache --------------------------------------------------------------------------------


class _Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        """Start at time 0."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current time."""
        return self.now


def _counting_fetch(results: list):
    """Return a fetch that gives (or raises) each result in turn, and the list of its calls."""
    calls = []

    def fetch():
        """Record the call, then give the next result."""
        calls.append(1)
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return fetch, calls


def test_prices_are_read_once_a_day():
    """The prices are kept for PRICE_CACHE_SECONDS, then read again."""
    clock = _Clock()
    fetch, calls = _counting_fetch([PRICES, {ANSWER: PRICES[ANSWER]}])
    cache = PriceCache(fetch, clock)
    assert cache.get() == PRICES
    clock.now = config.PRICE_CACHE_SECONDS - 1
    assert cache.get() == PRICES
    assert len(calls) == 1
    clock.now = config.PRICE_CACHE_SECONDS
    assert cache.get() == {ANSWER: PRICES[ANSWER]}
    assert len(calls) == 2
    assert config.PRICE_CACHE_SECONDS == 86_400


def test_a_failed_read_is_not_kept():
    """A failed read gives None (price unknown) and the next call tries again."""
    fetch, calls = _counting_fetch([PriceError("x"), PRICES])
    cache = PriceCache(fetch, _Clock())
    assert cache.get() is None
    assert cache.get() == PRICES
    assert len(calls) == 2


def test_a_failed_daily_refresh_gives_unknown_then_retries():
    """When the day is over and the new read fails, the old prices are not used past their day."""
    clock = _Clock()
    fetch, calls = _counting_fetch([PRICES, PriceError("x"), PRICES])
    cache = PriceCache(fetch, clock)
    cache.get()
    clock.now = config.PRICE_CACHE_SECONDS
    assert cache.get() is None
    assert cache.get() == PRICES
    assert len(calls) == 3


# --- Cost ----------------------------------------------------------------------------------------


def test_cost_of_a_call_prices_input_cached_input_and_output():
    """Uncached input at the input price, cached input at its price, output (reasoning in it)."""
    call = CallUsage("Answer", ANSWER, input_tokens=2000, output_tokens=500, cached_tokens=1000,
                     reasoning_tokens=300)  # fmt: skip
    # 1000 x 0.000001 + 1000 x 0.0000001 + 500 x 0.00001 = 0.001 + 0.0001 + 0.005
    assert usage.call_cost(call, PRICES) == Decimal("0.0061")


def test_reasoning_tokens_are_not_priced_twice():
    """Reasoning is shown but adds no cost: OpenRouter bills input and output only (O5)."""
    plain = CallUsage("Answer", ANSWER, 100, 50)
    thinking = CallUsage("Answer", ANSWER, 100, 50, reasoning_tokens=40)
    assert usage.call_cost(plain, PRICES) == usage.call_cost(thinking, PRICES)


def test_cached_tokens_without_a_cache_price_cost_the_input_price():
    """A model with no cached-input price prices those tokens as input."""
    call = CallUsage("Rewrite", REWRITE, input_tokens=1000, output_tokens=0, cached_tokens=600)
    assert usage.call_cost(call, PRICES) == Decimal("0.0001")


def test_cached_tokens_above_the_input_are_capped():
    """A cached count larger than the input (a provider bug) cannot make the cost negative."""
    call = CallUsage("Answer", ANSWER, input_tokens=100, cached_tokens=500)
    assert usage.call_cost(call, PRICES) == Decimal("0.00001")


def test_an_embedding_call_costs_its_input():
    """An embedding call has input tokens only."""
    assert usage.call_cost(CallUsage("Search", EMBEDDING, 40), PRICES) == Decimal("0.0000004")


@pytest.mark.parametrize("prices", [None, {}, {REWRITE: PRICES[REWRITE]}], ids=str)
def test_cost_is_unknown_without_the_models_price(prices):
    """No prices, or none for the call's model, gives None (shown as "price unknown")."""
    assert usage.call_cost(CallUsage("Answer", ANSWER, 10, 10), prices) is None


def test_a_turn_adds_up_its_calls():
    """A turn's tokens and cost are the sums over its calls."""
    calls = [
        CallUsage("Rewrite", REWRITE, 1000, 200),
        CallUsage("Search", EMBEDDING, 40),
        CallUsage("Answer, round 1", ANSWER, 3000, 400),
    ]
    turn = usage.price_turn(calls, PRICES)
    assert turn.tokens == 4640
    # 0.0001 + 0.0002 + 0.0000004 + 0.003 + 0.004
    assert turn.cost == Decimal("0.0073004")
    assert turn.costs[1] == Decimal("0.0000004")


def test_a_turn_with_one_unknown_price_has_an_unknown_cost():
    """If any call cannot be priced the turn's cost is unknown, not too low."""
    calls = [CallUsage("Answer", ANSWER, 10, 10), CallUsage("Answer", "unknown", 10, 10)]
    turn = usage.price_turn(calls, PRICES)
    assert turn.cost is None
    assert turn.tokens == 40


def test_a_turn_with_no_calls_costs_nothing():
    """A turn the guard stopped made no call: 0 tokens, $0."""
    turn = usage.price_turn([], None)
    assert (turn.tokens, turn.cost) == (0, Decimal(0))


def test_the_session_adds_known_costs_and_says_when_some_are_missing():
    """The session total adds every turn's tokens and the known costs, and flags unknown ones."""
    known = usage.price_turn([CallUsage("Answer", ANSWER, 1000, 100)], PRICES)
    unknown = usage.price_turn([CallUsage("Answer", ANSWER, 500, 50)], None)
    assert usage.session_usage([known, known]) == usage.SessionUsage(2200, Decimal("0.004"), False)
    assert usage.session_usage([known, unknown]) == usage.SessionUsage(1650, Decimal("0.002"), True)
    assert usage.session_usage([]) == usage.SessionUsage(0, Decimal(0), False)


# --- Display -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cost", "shown"),
    [
        (None, "price unknown"),
        (Decimal(0), "$0"),
        (Decimal("0.00009"), "<$0.0001"),
        (Decimal("0.0001"), "$0.0001"),
        (Decimal("0.00123"), "$0.0012"),
        (Decimal("0.07315"), "$0.0732"),
        (Decimal("1.5"), "$1.5000"),
    ],
    ids=str,
)
def test_format_cost(cost, shown):
    """Costs show in dollars to 4 decimals; tiny ones as "<$0.0001"; None as "price unknown"."""
    assert usage.format_cost(cost) == shown


def test_format_turn_and_tokens():
    """A turn shows as "1,234 tokens · $0.0012"; one token is singular."""
    turn = TurnUsage((CallUsage("Answer", ANSWER, 1000, 234),), (Decimal("0.0012"),))
    assert usage.format_turn(turn) == "1,234 tokens · $0.0012"
    assert usage.format_tokens(1) == "1 token"


@pytest.mark.parametrize(
    ("session", "shown"),
    [
        (usage.SessionUsage(12_345, Decimal("0.0123"), False), "12,345 tokens · $0.0123"),
        (
            usage.SessionUsage(12_345, Decimal("0.0123"), True),
            "12,345 tokens · $0.0123 + price unknown",
        ),
        (usage.SessionUsage(500, Decimal(0), True), "500 tokens · price unknown"),
    ],
    ids=["known", "partial", "all-unknown"],
)
def test_format_session(session, shown):
    """The session line says when part of its cost is unknown."""
    assert usage.format_session(session) == shown
