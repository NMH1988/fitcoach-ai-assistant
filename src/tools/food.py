"""lookup_food_nutrition: nutrients of a food and amount, from the USDA Foundation Foods table.

The table (`data/usda_foods.csv`) is made by `scripts/prepare_usda.py` from USDA FoodData Central
(CC0 1.0; docs/SOURCES.md #21). Food names are matched with rapidfuzz, so small typos and plurals
still find the food; the matched USDA name and close alternatives are always returned, so the
model and the user can see what was looked up.
"""

import csv
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rapidfuzz import fuzz, process, utils

from src import config

# The columns of data/usda_foods.csv; values are per 100 g of the food as described.
TABLE_COLUMNS: tuple[str, ...] = (
    "fdc_id",
    "description",
    "kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "fiber_g",
)
SOURCE = "USDA FoodData Central, Foundation Foods (CC0 1.0), https://fdc.nal.usda.gov/"
# The release date in the table's credit line (config.USDA_CITATION).
RELEASE_IN_CREDIT = re.compile(r"Foundation Foods, release (\d{4}-\d{2}-\d{2})\.")
# Words that mark a processed form of a food ("Flour, almond", "Oat milk", "Egg, yolk, dried").
# A name with one the query does not ask for ranks below the plain food.
FORM_WORDS = frozenset({"flour", "oil", "juice", "dried", "powder", "milk", "butter"})


class FoodTableError(RuntimeError):
    """The foods table is missing or does not have the expected columns and values."""


class Food(BaseModel):
    """One row of the foods table: a USDA food and its nutrients per 100 g."""

    model_config = ConfigDict(frozen=True)

    fdc_id: int = Field(gt=0)
    description: str = Field(min_length=1)
    kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    # None when USDA reports no fiber value for the food ("not reported", not zero).
    fiber_g: float | None = Field(default=None, ge=0)


class FoodLookupArgs(BaseModel):
    """The tool's arguments, as the model sends them; checked before any lookup."""

    model_config = ConfigDict(str_strip_whitespace=True)

    food: str = Field(
        min_length=1,
        max_length=config.FOOD_MAX_NAME_CHARS,
        description="One food in plain English, e.g. 'chicken breast raw' or 'rolled oats'.",
    )
    # Strict: a JSON number only (no strings or booleans); an int is accepted.
    grams: float = Field(
        ge=config.FOOD_MIN_GRAMS,
        le=config.FOOD_MAX_GRAMS,
        allow_inf_nan=False,
        strict=True,
        description="Amount of the food in grams.",
    )


class Nutrients(BaseModel):
    """Nutrients in the requested amount of a food."""

    kcal: int
    protein_g: float
    carbohydrate_g: float
    fat_g: float
    # None when USDA reports no fiber value for the food.
    fiber_g: float | None


class FoodLookupResult(BaseModel):
    """What the tool returns: the scaled nutrients of the matched food, or why there are none."""

    status: Literal["found", "not_found", "invalid"]
    message: str
    grams: float | None = None
    matched_name: str | None = None
    fdc_id: int | None = None
    nutrients: Nutrients | None = None
    # Other close USDA names when found; "did you mean" suggestions when not found.
    alternatives: list[str] = Field(default_factory=list)
    source: str = SOURCE


def read_usda_release(path: Path | None = None) -> str:
    """Return the USDA release date (YYYY-MM-DD) named in the foods table's credit line."""
    path = path or config.USDA_FOODS_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FoodTableError(
            f"{path.name} is missing; run python scripts/prepare_usda.py to make it."
        ) from None
    credit = " ".join(line for line in text.splitlines() if line.startswith("#"))
    match = RELEASE_IN_CREDIT.search(credit)
    if match is None:
        raise FoodTableError(f"{path.name} does not name its USDA release.")
    return match.group(1)


def load_food_table(path: Path | None = None) -> tuple[Food, ...]:
    """Return the foods in the table (read once per path, then cached)."""
    return _load_food_table(path or config.USDA_FOODS_PATH)


@lru_cache(maxsize=4)
def _load_food_table(path: Path) -> tuple[Food, ...]:
    """Read and validate the foods table, skipping the '#' credit lines at the top."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FoodTableError(
            f"{path.name} is missing; run python scripts/prepare_usda.py to make it."
        ) from None
    reader = csv.DictReader(line for line in text.splitlines() if not line.startswith("#"))
    if tuple(reader.fieldnames or ()) != TABLE_COLUMNS:
        raise FoodTableError(f"{path.name} does not have the columns {', '.join(TABLE_COLUMNS)}.")
    foods = []
    for number, row in enumerate(reader, start=1):
        try:
            foods.append(Food(**{key: (value or None) for key, value in row.items()}))
        except ValidationError, TypeError:
            raise FoodTableError(f"{path.name}: row {number} is not valid.") from None
    if not foods:
        raise FoodTableError(f"{path.name} has no foods.")
    return tuple(foods)


def _normalise(text: str) -> str:
    """Lower-case the text, drop punctuation and reduce simple plurals, for name matching."""
    words = []
    for word in utils.default_process(text).split():
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("oes"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def _score(query: str, choice: str, **_: object) -> float:
    """Score a name 0-100: the mean of overall similarity and "all query words are in it"."""
    # WRatio alone ranks "tuna" closer to "butter"; token_set_ratio alone gives "banana" a
    # perfect score for "Peppers, banana"; their mean worked best on the real table (T4.3).
    return (fuzz.WRatio(query, choice) + fuzz.token_set_ratio(query, choice)) / 2


def _rank(query: str, foods: Sequence[Food]) -> list[tuple[Food, float]]:
    """Return the foods scoring at least the suggestion threshold with their scores, best first."""
    # The score alone favours short names too much ("milk" scores higher on "Yogurt, plain, whole
    # milk" than on "Milk, whole, 3.25% milkfat"), so the matches are ordered by these, in turn:
    # 1. the plain food before a processed form the query does not name (FORM_WORDS): "Nuts,
    #    almonds" before "Flour, almond" and "Almond butter" for "almonds";
    # 2. a name whose head (before the first comma) is made only of query words, since USDA names
    #    lead with the food itself: for "white rice", "Rice, white" is rice, "Flour, rice" flour;
    # 3. the higher token_set_ratio (how fully the query words appear in the name);
    # 4. the higher score, then the shorter, plainer name.
    names = [_normalise(f.description) for f in foods]
    hits = process.extract(
        query,
        names,
        scorer=_score,
        limit=None,
        score_cutoff=config.FOOD_SUGGESTION_MIN_SCORE,
    )
    query_words = set(query.split())

    def order(hit: tuple[str, float, int]) -> tuple[bool, bool, bool, int, float, int]:
        """Sort key for one hit: matches first, then the preferences listed above."""
        name, score, index = hit
        head = set(_normalise(foods[index].description.split(",")[0]).split())
        return (
            score < config.FOOD_MATCH_MIN_SCORE,
            bool((set(name.split()) & FORM_WORDS) - query_words),
            not head <= query_words,
            -round(fuzz.token_set_ratio(query, name)),
            -score,
            len(name),
        )

    return [(foods[index], score) for _, score, index in sorted(hits, key=order)]


def _scale(food: Food, grams: float) -> Nutrients:
    """Scale the food's per-100 g values to the given amount, rounded for display."""
    factor = grams / 100
    digits = config.FOOD_DECIMALS
    return Nutrients(
        kcal=round(food.kcal * factor),
        protein_g=round(food.protein_g * factor, digits),
        carbohydrate_g=round(food.carbohydrate_g * factor, digits),
        fat_g=round(food.fat_g * factor, digits),
        fiber_g=None if food.fiber_g is None else round(food.fiber_g * factor, digits),
    )


def _invalid_message(error: ValidationError) -> str:
    """Explain which argument is wrong, without repeating what was sent."""
    fields = {str(e["loc"][0]) for e in error.errors() if e["loc"]}
    parts = []
    if "food" in fields:
        parts.append(f"give the name of one food in 1 to {config.FOOD_MAX_NAME_CHARS} characters")
    if "grams" in fields:
        parts.append(
            f"give the amount as a number of grams from {config.FOOD_MIN_GRAMS:g} to "
            f"{config.FOOD_MAX_GRAMS}"
        )
    return "Invalid food lookup: " + ("; ".join(parts) or "check the arguments") + "."


def lookup_food_nutrition(
    food: str, grams: float, table: Sequence[Food] | None = None
) -> FoodLookupResult:
    """Return the nutrients of the named food for the given grams, or a clear message why not."""
    # Invalid arguments and unknown foods give a result, never an exception; a missing or broken
    # table raises FoodTableError, which the tool wrapper (T4.4) turns into a tool error message.
    # `table` replaces the committed foods table (tests).
    try:
        args = FoodLookupArgs(food=food, grams=grams)
    except ValidationError as exc:
        return FoodLookupResult(status="invalid", message=_invalid_message(exc))

    foods = load_food_table() if table is None else table
    query = _normalise(args.food)
    ranked = _rank(query, foods) if query else []
    limit = config.FOOD_MAX_ALTERNATIVES

    if not ranked or ranked[0][1] < config.FOOD_MATCH_MIN_SCORE:
        suggestions = [f.description for f, _ in ranked[:limit]]
        message = "No close match in the USDA Foundation Foods table."
        if suggestions:
            message += " Did you mean one of the alternatives? Look it up by that name."
        else:
            message += " Try a plainer name of a single, unprocessed food (e.g. 'rolled oats')."
        return FoodLookupResult(
            status="not_found", message=message, grams=args.grams, alternatives=suggestions
        )

    best = ranked[0][0]
    message = f"{args.grams:g} g of {best.description}, from per-100 g USDA values."
    if best.fiber_g is None:
        message += " USDA reports no fiber value for this food."
    return FoodLookupResult(
        status="found",
        message=message,
        grams=args.grams,
        matched_name=best.description,
        fdc_id=best.fdc_id,
        nutrients=_scale(best, args.grams),
        alternatives=[f.description for f, _ in ranked[1 : 1 + limit]],
    )
