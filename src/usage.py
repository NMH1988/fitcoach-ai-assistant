"""Token usage and cost of each chat turn and of the session (T5.1, Medium 5, AC-10).

A turn records the tokens of every model and embedding call it makes (query translation, the query
embedding, each answer round) in a UsageRecorder. The app then prices them with OpenRouter's
per-token prices, read from its public model lists (no key sent) and kept for a day. Output tokens
follow OpenAI's convention: they include the reasoning tokens, which are not added again. Prices
are untrusted data from the network: only finite, non-negative numbers are used, and a model
without a usable price makes its calls "price unknown".
"""

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages.ai import UsageMetadata

from src import config


@dataclass(frozen=True)
class CallUsage:
    """The tokens one model or embedding call used, and which step and model made it."""

    step: str
    model: str
    input_tokens: int
    output_tokens: int = 0
    # Input tokens read from the provider's prompt cache (part of input_tokens, priced lower).
    cached_tokens: int = 0
    # Part of output_tokens (OpenAI's convention); shown, never priced twice.
    reasoning_tokens: int = 0

    @property
    def tokens(self) -> int:
        """Return the call's input and output tokens together."""
        return self.input_tokens + self.output_tokens


def model_name(client: Any) -> str:
    """Return the name of the model a chat client calls, for pricing its tokens."""
    name = getattr(client, "model_name", None)
    return name if isinstance(name, str) else "unknown"


def _count(value: Any) -> int:
    """Return a reported token count as a non-negative int, or 0 if it is missing or unusable."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


@dataclass
class UsageRecorder:
    """Collects the calls of one turn in order, so a turn that fails keeps what it spent."""

    calls: list[CallUsage] = field(default_factory=list)

    def add_chat(self, step: str, model: str, usage: UsageMetadata | None) -> None:
        """Record a chat call's usage as langchain reports it; a call with none is left out."""
        if not usage:
            return
        self.calls.append(
            CallUsage(
                step=step,
                model=model,
                input_tokens=_count(usage.get("input_tokens")),
                output_tokens=_count(usage.get("output_tokens")),
                cached_tokens=_count((usage.get("input_token_details") or {}).get("cache_read")),
                reasoning_tokens=_count((usage.get("output_token_details") or {}).get("reasoning")),
            )
        )

    def add_embedding(self, step: str, model: str, tokens: int | None) -> None:
        """Record an embedding call's input tokens; a call that reported none is left out."""
        if tokens is None:
            return
        self.calls.append(CallUsage(step=step, model=model, input_tokens=_count(tokens)))


@dataclass(frozen=True)
class ModelPrice:
    """A model's price in US dollars per token: input, output and cached input."""

    prompt: Decimal
    completion: Decimal
    cache_read: Decimal | None = None


class PriceError(RuntimeError):
    """The model prices could not be read; the message is fixed text, never the server's."""


def _price(value: Any) -> Decimal | None:
    """Return a price given as a string or number, or None if it is not a finite number >= 0."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        return None
    # OpenRouter gives "-1" for a price that varies (e.g. a router model); it is not usable. A price
    # far above any real one is refused too, so no cost can overflow.
    usable = price.is_finite() and 0 <= price <= Decimal(config.PRICE_MAX_PER_TOKEN)
    return price if usable else None


def parse_prices(payload: Any, models: Iterable[str]) -> dict[str, ModelPrice]:
    """Return the prices of the named models from one OpenRouter model list; skip unusable ones."""
    wanted = set(models)
    data = payload.get("data") if isinstance(payload, dict) else None
    prices: dict[str, ModelPrice] = {}
    for entry in data if isinstance(data, list) else ():
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        if entry["id"] not in wanted:
            continue
        pricing = entry.get("pricing")
        if not isinstance(pricing, dict):
            continue
        prompt, completion = _price(pricing.get("prompt")), _price(pricing.get("completion"))
        if prompt is None or completion is None:
            continue
        cache_read = _price(pricing.get("input_cache_read"))
        prices[entry["id"]] = ModelPrice(prompt, completion, cache_read)
    return prices


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses to follow redirects, so a price request only ever reaches OpenRouter."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Return None, which makes urllib raise the 3xx as an HTTPError instead of following it."""
        return None


_OPENER = urllib.request.build_opener(NoRedirect())


def _get_json(url: str) -> Any:
    """GET a public OpenRouter model list and return its JSON; raise PriceError on any failure."""
    # No key and no user data: these lists are public.
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with _OPENER.open(request, timeout=config.PRICE_TIMEOUT_SECONDS) as response:
            body = response.read(config.PRICE_MAX_BYTES + 1)
    except (OSError, http.client.HTTPException) as exc:
        # HTTPError and timeouts are OSErrors too.
        raise PriceError(f"price list not read ({type(exc).__name__})") from None
    if len(body) > config.PRICE_MAX_BYTES:
        raise PriceError("price list too large")
    try:
        return json.loads(body)
    except ValueError, RecursionError:
        # RecursionError: JSON nested too deeply.
        raise PriceError("price list not JSON") from None


def fetch_prices(get_json: Callable[[str], Any] = _get_json) -> dict[str, ModelPrice]:
    """Read the prices of the app's chat and embedding models from OpenRouter."""
    chat = parse_prices(get_json(config.CHAT_PRICES_URL), config.ALLOWED_MODELS)
    embedding = parse_prices(get_json(config.EMBEDDING_PRICES_URL), [config.EMBEDDING_MODEL])
    if not chat or not embedding:
        # E.g. an error page sent as JSON: a failed read, so it is not kept for a day.
        raise PriceError("no usable price in the list")
    return {**chat, **embedding}


class PriceCache:
    """Keeps the prices for PRICE_CACHE_SECONDS; a failed read is not kept, so the next tries."""

    def __init__(
        self,
        fetch: Callable[[], Mapping[str, ModelPrice]] = fetch_prices,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Keep the function that reads the prices and the clock that ages them."""
        self._fetch = fetch
        self._clock = clock
        self._prices: Mapping[str, ModelPrice] | None = None
        self._read_at = 0.0
        # Sessions run in threads; one read at a time, which the others then reuse.
        self._lock = threading.Lock()

    def get(self) -> Mapping[str, ModelPrice] | None:
        """Return the prices, reading them again when older than a day; None if the read failed."""
        with self._lock:
            now = self._clock()
            if self._prices is None or now - self._read_at >= config.PRICE_CACHE_SECONDS:
                try:
                    prices = self._fetch()
                except PriceError:
                    return None
                self._prices, self._read_at = prices, now
            return self._prices


# The app process's prices, shared by all sessions.
PRICES = PriceCache()


def call_cost(call: CallUsage, prices: Mapping[str, ModelPrice] | None) -> Decimal | None:
    """Return a call's cost in dollars, or None when its model's price is unknown."""
    price = prices.get(call.model) if prices else None
    if price is None:
        return None
    cached = min(call.cached_tokens, call.input_tokens)
    cache_price = price.prompt if price.cache_read is None else price.cache_read
    return (
        (call.input_tokens - cached) * price.prompt
        + cached * cache_price
        + call.output_tokens * price.completion
    )


@dataclass(frozen=True)
class TurnUsage:
    """A turn's calls with the cost of each (None where the price is unknown)."""

    calls: tuple[CallUsage, ...] = ()
    costs: tuple[Decimal | None, ...] = ()

    @property
    def tokens(self) -> int:
        """Return the turn's tokens over all its calls."""
        return sum(call.tokens for call in self.calls)

    @property
    def cost(self) -> Decimal | None:
        """Return the turn's cost, or None if any call's price is unknown."""
        if any(cost is None for cost in self.costs):
            return None
        return sum(self.costs, Decimal(0))


def price_turn(calls: Sequence[CallUsage], prices: Mapping[str, ModelPrice] | None) -> TurnUsage:
    """Return the turn's calls with the cost of each."""
    return TurnUsage(tuple(calls), tuple(call_cost(call, prices) for call in calls))


@dataclass(frozen=True)
class SessionUsage:
    """The session's tokens and the cost of the turns whose price is known."""

    tokens: int
    cost: Decimal
    # True when some turn's price was unknown, so the cost is only part of the total.
    partial: bool


def session_usage(turns: Iterable[TurnUsage]) -> SessionUsage:
    """Add up the tokens and the known costs of the session's turns."""
    tokens, cost, partial = 0, Decimal(0), False
    for turn in turns:
        tokens += turn.tokens
        for call_price in turn.costs:
            if call_price is None:
                partial = True
            else:
                cost += call_price
    return SessionUsage(tokens, cost, partial)


def format_cost(cost: Decimal | None) -> str:
    """Return a cost in dollars to 4 decimals, "<$0.0001" for less, or "price unknown"."""
    if cost is None:
        return config.PRICE_UNKNOWN_LABEL
    if cost == 0:
        return "$0"
    if cost < Decimal(config.COST_SHOWN_MIN):
        return f"<${config.COST_SHOWN_MIN}"
    return f"${cost:.4f}"


def format_tokens(tokens: int) -> str:
    """Return a token count with thousands separators and the right noun."""
    return f"{tokens:,} {'token' if tokens == 1 else 'tokens'}"


def format_turn(turn: TurnUsage) -> str:
    """Return a turn's usage in one line, e.g. "1,234 tokens · $0.0012"."""
    return f"{format_tokens(turn.tokens)} · {format_cost(turn.cost)}"


def format_session(session: SessionUsage) -> str:
    """Return the session's usage in one line, saying when some prices were unknown."""
    if session.partial and session.cost == 0:
        return f"{format_tokens(session.tokens)} · {config.PRICE_UNKNOWN_LABEL}"
    cost = format_cost(session.cost)
    suffix = f" + {config.PRICE_UNKNOWN_LABEL}" if session.partial else ""
    return f"{format_tokens(session.tokens)} · {cost}{suffix}"
