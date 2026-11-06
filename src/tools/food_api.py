"""The USDA FoodData Central API, asked by the chat's food tool when the local table has no match.

T9.9 (docs/SOURCES.md #21; copyright policy rule 10 as changed on 2026-11-06). `lookup()` runs the
table lookup first (`lookup_food_nutrition`); only a "not_found" there, with the owner's key set,
sends one search to the API. The request is a POST to the fixed URL in `config.FOOD_API_URL` whose
JSON body holds the checked food name and fixed fields only (`request_body()`); the key goes in the
`X-Api-Key` header, so it is in no URL; redirects are refused, so it reaches no other host. A
timeout, a connection error or a 5xx answer is tried again up to `FOOD_API_MAX_ATTEMPTS`; every
failure becomes a code (`ApiCode`), never an exception or a text with the key or the name. The
foods that come back are checked (their data type, name and per-100 g values) and ranked with the
table's own fuzzy match, so the same rules decide what counts as a match. Nothing is stored.
"""

import http.client
import json
import math
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from src import config
from src.preferences import names_in
from src.tools.food import (
    ApiCode,
    Food,
    FoodLookupResult,
    _found,
    _normalise,
    _rank,
    lookup_food_nutrition,
)
from src.usage import NoRedirect

# USDA nutrient IDs, and the nutrient numbers some answers give instead (USDA's API documents both
# forms). Energy: Atwater specific factors first, then general factors, then the reported energy,
# as in the table (docs/ARCHITECTURE.md section 6).
ENERGY_IDS = (2048, 2047, 1008)
PROTEIN_ID = 1003
FAT_ID = 1004
CARBOHYDRATE_ID = 1005
FIBER_IDS = (1079, 2033)
_ID_BY_NUMBER = {
    "958": 2048,
    "957": 2047,
    "208": 1008,
    "203": PROTEIN_ID,
    "204": FAT_ID,
    "205": CARBOHYDRATE_ID,
    "291": 1079,
    "293": 2033,
}
# The codes of a search that failed (logged at WARNING; the rest are outcomes, logged at INFO).
FOOD_API_FAILURES = frozenset(
    {"timeout", "unavailable", "rate_limited", "key_rejected", "bad_response"}
)
# The unit each nutrient must be reported in; any other unit (kJ for energy) is not used.
_UNITS = {
    **dict.fromkeys(ENERGY_IDS, "KCAL"),
    **dict.fromkeys((PROTEIN_ID, FAT_ID, CARBOHYDRATE_ID, *FIBER_IDS), "G"),
}

# The characters a food name sent to the API may hold (config.FOOD_API_MAX_WORDS says the rest).
_NAME = re.compile(r"[A-Za-z0-9 ,'%()/.\-]+")
# A "." that is not between two digits ("1.5% milk" is fine; "www.example" is not).
_LOOSE_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")
# At least one word of FOOD_MIN_NAME_CHARS letters, as the tool's own name check asks.
_LETTERS = re.compile(rf"[A-Za-z]{{{config.FOOD_MIN_NAME_CHARS}}}")

# Messages the model and the user read; none repeats the name that was asked for.
_NOT_SENT = {
    "name_refused": (
        " The name was not sent to the USDA FoodData Central API: only plain English words, "
        "digits and , ' % ( ) / - are sent."
    ),
    "turn_limit": (
        " The USDA FoodData Central API was not searched: at most "
        f"{config.FOOD_API_MAX_CALLS_PER_TURN} searches are made in one turn."
    ),
}
# A name holding one of a coach's clients' names (same code, its own reason; names no one).
_CLIENT_NAME = (
    " The name was not sent to the USDA FoodData Central API: it holds the name of one of the "
    "coach's clients."
)
_FAILED = (
    " The USDA FoodData Central API could not be searched just now, so only the table was searched."
)
_NO_MATCH = "No close match in the USDA Foundation Foods table or the USDA FoodData Central API."


class Opener(Protocol):
    """What sends a request: urllib's opener, or a fake one in the tests."""

    def open(self, request: urllib.request.Request, timeout: float) -> Any:
        """Send the request and return a response to read, or raise an OSError."""
        ...


_OPENER: Opener = urllib.request.build_opener(NoRedirect())


@dataclass(frozen=True)
class ApiFood:
    """A food from the API: its per-100 g values and the USDA data type it belongs to."""

    food: Food
    data_type: str


@dataclass(frozen=True)
class ApiSearch:
    """The outcome of one search: code None with the foods that passed the checks, or a failure."""

    code: ApiCode | None
    foods: tuple[ApiFood, ...] = ()
    attempts: int = 0


class FoodSearch(Protocol):
    """Anything that searches foods by name: FoodApi, or a fake one in the tests."""

    def search(self, name: str) -> ApiSearch:
        """Return the foods found for the name, or a failure code."""
        ...


class _Failed(Exception):
    """One attempt failed; `retry` says whether another attempt may help."""

    def __init__(self, code: ApiCode, retry: bool) -> None:
        """Keep the failure's code and whether to try again; no text, so nothing can leak."""
        super().__init__(code)
        self.code: ApiCode = code
        self.retry = retry


def api_query(name: str) -> str | None:
    """Return the food name as it is sent to the API, or None when it may not be sent."""
    # Only plain words leave the app (AC 3): no "@", ":" or other punctuation, and few digits (a
    # phone or card number, spaced or not, has more). A heuristic: plain-word text such as a name
    # or a street still passes (docs/SECURITY.md, known limits).
    text = " ".join(name.split())
    if not config.FOOD_MIN_NAME_CHARS <= len(text) <= config.FOOD_MAX_NAME_CHARS:
        return None
    if not _NAME.fullmatch(text) or _LOOSE_DOT.search(text) or not _LETTERS.search(text):
        return None
    if len(text.split()) > config.FOOD_API_MAX_WORDS:
        return None
    if sum(char.isdigit() for char in text) > config.FOOD_API_MAX_DIGITS:
        return None
    return text


def request_body(query: str) -> dict[str, object]:
    """Return the search's JSON body: the food name and the fixed fields, nothing else."""
    return {
        "query": query,
        "dataType": list(config.FOOD_API_DATA_TYPES),
        "pageSize": config.FOOD_API_PAGE_SIZE,
    }


def _number(value: object) -> float | None:
    """Return a finite JSON number as a float, or None (booleans and text are not numbers)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:  # an integer too large for a float
        return None
    return number if math.isfinite(number) else None


def _nutrient_id(entry: Mapping[str, Any]) -> int | None:
    """Return the USDA nutrient ID of one nutrient entry, from its ID or its number."""
    nutrient_id = entry.get("nutrientId")
    if isinstance(nutrient_id, int) and not isinstance(nutrient_id, bool):
        return nutrient_id
    number = entry.get("nutrientNumber", entry.get("number"))
    return _ID_BY_NUMBER.get(number) if isinstance(number, str) else None


def _values(nutrients: object) -> dict[int, float]:
    """Return the used nutrients' values by ID, first one of each, in the unit each must have."""
    values: dict[int, float] = {}
    if not isinstance(nutrients, list):
        return values
    for entry in nutrients:
        if not isinstance(entry, Mapping):
            continue
        nutrient_id = _nutrient_id(entry)
        unit = entry.get("unitName")
        value = _number(entry.get("value", entry.get("amount")))
        if (
            nutrient_id in _UNITS
            and nutrient_id not in values
            and isinstance(unit, str)
            and unit.upper() == _UNITS[nutrient_id]
            and value is not None
        ):
            values[nutrient_id] = max(value, 0.0)  # e.g. carbohydrate by difference below 0
    return values


def _description(value: object) -> str | None:
    """Return a food's name with its spacing tidied, or None if it is empty, too long or odd."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > config.FOOD_API_MAX_DESCRIPTION_CHARS:
        return None
    # A control, format, surrogate, private-use or unassigned character (e.g. a zero-width or bidi
    # mark, or a lone surrogate that cannot be written as UTF-8) is not in a USDA name.
    if any(unicodedata.category(char).startswith("C") for char in text):
        return None
    return text


def _food(item: object) -> ApiFood | None:
    """Return one search result as a checked food, or None if any part of it fails a check."""
    if not isinstance(item, Mapping):
        return None
    data_type = item.get("dataType")
    fdc_id = item.get("fdcId")
    description = _description(item.get("description"))
    if (
        data_type not in config.FOOD_API_DATA_TYPES
        or not isinstance(fdc_id, int)
        or isinstance(fdc_id, bool)
        or description is None
    ):
        return None
    values = _values(item.get("foodNutrients"))
    kcal = next((values[i] for i in ENERGY_IDS if i in values), None)
    macros = [values.get(i) for i in (PROTEIN_ID, CARBOHYDRATE_ID, FAT_ID)]
    fiber = next((values[i] for i in FIBER_IDS if i in values), None)
    if kcal is None or None in macros or kcal > config.FOOD_API_MAX_KCAL:
        return None
    grams = [value for value in (*macros, fiber) if value is not None]
    if any(value > config.FOOD_API_MAX_GRAMS_PER_100G for value in grams):
        return None
    protein, carbohydrate, fat = macros
    try:
        food = Food(
            fdc_id=fdc_id,
            description=description,
            kcal=kcal,
            protein_g=protein,
            carbohydrate_g=carbohydrate,
            fat_g=fat,
            fiber_g=fiber,
        )
    except ValidationError:
        return None
    return ApiFood(food, str(data_type))


def parse_search(payload: object) -> tuple[ApiFood, ...]:
    """Return the foods of a search answer that pass every check, each name once."""
    foods = payload.get("foods") if isinstance(payload, Mapping) else None
    if not isinstance(foods, list):
        raise _Failed("bad_response", retry=False)
    checked: dict[str, ApiFood] = {}
    for item in foods:
        found = _food(item)
        if found is not None:
            checked.setdefault(found.food.description, found)
    return tuple(checked.values())


@dataclass(frozen=True)
class FoodApi:
    """The FoodData Central search with the owner's key; the key is never shown or logged."""

    key: str = field(repr=False)
    # None: the module's urllib opener, which refuses redirects (read when a search runs, so the
    # tests can replace it).
    opener: Opener | None = field(default=None, repr=False)
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)

    def search(self, name: str) -> ApiSearch:
        """Search the API for a checked food name; retry what may pass on a second try."""
        body = json.dumps(request_body(name)).encode("utf-8")
        code: ApiCode = "unavailable"
        for attempt in range(1, config.FOOD_API_MAX_ATTEMPTS + 1):
            if attempt > 1:
                self.sleep(config.FOOD_API_RETRY_PAUSE_SECONDS)
            try:
                return ApiSearch(None, parse_search(self._post(body)), attempt)
            except _Failed as failure:
                code = failure.code
                if not failure.retry:
                    return ApiSearch(code, attempts=attempt)
        return ApiSearch(code, attempts=config.FOOD_API_MAX_ATTEMPTS)

    def _post(self, body: bytes) -> object:
        """Send one search and return its JSON; raise _Failed with a code on any failure."""
        request = urllib.request.Request(
            config.FOOD_API_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Api-Key": self.key,
            },
        )
        try:
            opener = _OPENER if self.opener is None else self.opener
            with opener.open(request, timeout=config.FOOD_API_TIMEOUT_SECONDS) as response:
                raw = response.read(config.FOOD_API_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            # An HTTPError is a response too (and a URLError and an OSError, so it comes first).
            raise _http_failure(exc.code) from None
        except TimeoutError:
            raise _Failed("timeout", retry=True) from None
        except urllib.error.URLError as exc:
            timed_out = isinstance(exc.reason, TimeoutError)
            raise _Failed("timeout" if timed_out else "unavailable", retry=True) from None
        except OSError, http.client.HTTPException:
            raise _Failed("unavailable", retry=True) from None
        if len(raw) > config.FOOD_API_MAX_BYTES:
            raise _Failed("bad_response", retry=False)
        try:
            return json.loads(raw)
        except ValueError, RecursionError:
            # ValueError covers bad UTF-8 and bad JSON; RecursionError JSON nested too deeply.
            raise _Failed("bad_response", retry=False) from None


def _http_failure(status: int) -> _Failed:
    """Map an HTTP error status to a failure code; only a server error is tried again."""
    if status == 429:
        return _Failed("rate_limited", retry=False)
    if status in (401, 403):
        return _Failed("key_rejected", retry=False)
    if status >= 500:
        return _Failed("unavailable", retry=True)
    # A refused redirect (3xx) or another client error: not a search result.
    return _Failed("bad_response", retry=False)


def build_food_api() -> FoodApi | None:
    """Return the API client with the owner's key, or None when no key is set."""
    key = config.get_food_api_key()
    return None if key is None else FoodApi(key)


@dataclass
class TurnBudget:
    """The API searches one chat turn may still make, and the failure that stopped them, if any."""

    left: int = field(default_factory=lambda: config.FOOD_API_MAX_CALLS_PER_TURN)
    # Set by the turn's first failed search: the rest of the turn sends no request (a service
    # that is down, a used-up quota or a refused key would only fail again, each time after a wait).
    failed: ApiCode | None = None

    def take(self) -> bool:
        """Use one search; return False when none is left."""
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def lookup(
    food: str,
    grams: float,
    api: FoodSearch | None,
    budget: TurnBudget,
    table: Sequence[Food] | None = None,
    client_names: Sequence[str] = (),
) -> FoodLookupResult:
    """Look the food up in the table, then, only if it is not found there, through the API."""
    # client_names: in a coach's chat, the names of the coach's current and former clients (T9.7's
    # list); a name holding one of them is never sent (compliance run 1, owner's choice).
    local = lookup_food_nutrition(food, grams, table)
    if local.status != "not_found" or api is None or local.grams is None:
        return local
    query = api_query(food)
    if query is None:
        return _not_found(local, "name_refused")
    if names_in(query, client_names):
        return _not_found(local, "name_refused", _CLIENT_NAME)
    if budget.failed is not None:
        return _not_found(local, budget.failed)
    if not budget.take():
        return _not_found(local, "turn_limit")
    search = api.search(query)
    if search.code is not None:
        budget.failed = search.code
        return _not_found(local, search.code)
    # Keyed by name, as parse_search() keeps each name once.
    data_types = {found.food.description: found.data_type for found in search.foods}
    ranked = _rank(_normalise(query), [found.food for found in search.foods])
    limit = config.FOOD_MAX_ALTERNATIVES
    if not ranked or ranked[0][1] < config.FOOD_MATCH_MIN_SCORE:
        suggestions = [match.description for match, _ in ranked[:limit]] or local.alternatives
        message = _NO_MATCH
        if suggestions:
            message += " Did you mean one of the alternatives? They are the closest names found."
        return FoodLookupResult(
            status="not_found",
            message=message,
            grams=local.grams,
            alternatives=suggestions,
            source=config.FOOD_API_NO_MATCH_SOURCE,
            api_code="no_match",
        )
    best = ranked[0][0]
    others = [match.description for match, _ in ranked[1 : 1 + limit]]
    return _found(best, local.grams, others, data_types[best.description])


def _not_found(
    local: FoodLookupResult, code: ApiCode, reason: str | None = None
) -> FoodLookupResult:
    """Return the table's "not found" with the reason the API gave no result."""
    return FoodLookupResult(
        status="not_found",
        message=local.message + (reason or _NOT_SENT.get(code, _FAILED)),
        grams=local.grams,
        alternatives=local.alternatives,
        api_code=code,
    )
