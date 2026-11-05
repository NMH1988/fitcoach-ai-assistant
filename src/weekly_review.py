"""The weekly review's content: its schema, the client's week as aggregates, and its checks (T9.16).

No model, network or store call here, so all of it is unit-tested; the workflow that calls it is
`src/agent/review.py` (D17).

- `WeeklyReview` is what the model writes (`with_structured_output`): observations, hypotheses and
  recommendations, each citing the evidence by its `[S#]` label. The stored draft adds the language.
- `aggregates()` turns a `dashboard.DashboardWeek` into the numbers the model gets: averages, the
  target, logged days, the weight change, sessions and volume, for "the client"; never a name, a
  food or a date of birth, and only the scopes the review uses.
- `validate()` checks a draft (AC-27, AC-35): every label is a chunk retrieved in this run; no
  recommended intake is below the calorie floor; no diagnosis; a training recommendation cites a
  training chunk, holds no program and no client set count, and carries a direction, the source's
  range (found in a cited chunk) and the population; the numbers quoted match the metrics or a
  cited chunk; a nutrition recommendation without a citation is labelled as the model's
  suggestion. `check_edit()` runs the safety checks on the coach's edit.

Each failed check is a code; the workflow sends the codes' fixed texts back to the model once.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src import config, dashboard
from src.chat import sources_block
from src.prompt_data import escape_prompt_data
from src.rag.retriever import RetrievedChunk, chunk_key

Kind = Literal["nutrition", "training"]
NUTRIENTS = ("kcal", "protein_g", "carbohydrate_g", "fat_g")
# The target's stored names for the same nutrients (nutrition_targets.carbs_g is carbohydrate_g).
_LABEL = re.compile(r"\[?\bS(\d+)\b\]?")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_DASHES = re.compile(r"[‐-―−-]")
_TO_BETWEEN_NUMBERS = re.compile(r"(?<=\d)\s*(?:to|bis)\s*(?=\d)")
_SPACE_AROUND_DASH = re.compile(r"\s*-\s*")
_SPACES = re.compile(r"\s+")
_KCAL = re.compile(r"(\d+(?:[.,]\d+)*)\s*(?:kcal|kilocalories|calories|kalorien)\b", re.I)

# The fixed text the model gets back for each failed check, on the one retry (English, as the
# prompt is; the coach sees these codes as their own texts in src/i18n.py).
ERROR_TEXTS: dict[str, str] = {
    "schema": "The reply did not follow the schema.",
    "unknown_evidence": "A citation names a label that is not in <sources>.",
    "calorie_floor": (
        f"A recommendation gives an intake below {config.CALORIE_FLOOR_KCAL} kcal per day."
    ),
    "diagnosis": "A text names a medical condition or diagnosis.",
    "training_uncited": "A training recommendation does not cite a resistance training source.",
    "training_fields": (
        "A training recommendation lacks its direction, source_range or population."
    ),
    "source_range": (
        "A training recommendation's source_range is not quoted exactly from a cited source."
    ),
    "program": "A training recommendation is a program (sets and reps, days, a plan).",
    "client_volume": (
        "A training recommendation gives the client's own set count or volume; leave that "
        "number to the coach."
    ),
    "number": "A number is neither in <metrics> nor in a source the item cites.",
    "suggestion_label": (
        "A nutrition recommendation without a citation must have model_suggestion true, and one "
        "with a citation false."
    ),
}


class Statement(BaseModel):
    """An observation or a hypothesis: one text and the labels of the sources it cites."""

    model_config = ConfigDict(frozen=True)

    # No default and no string length in the schema (OpenAI's strict mode), so both are checked
    # by the validators below.
    text: str
    evidence: tuple[str, ...] = Field(max_length=config.REVIEW_MAX_CHUNKS)

    @field_validator("text")
    @classmethod
    def _text_is_short_and_not_blank(cls, text: str) -> str:
        """Strip the text and refuse a blank one or one over REVIEW_TEXT_MAX_CHARS."""
        return _checked_text(text, config.REVIEW_TEXT_MAX_CHARS)


class Recommendation(BaseModel):
    """A recommendation to the coach, nutrition or training, with its evidence (D22)."""

    model_config = ConfigDict(frozen=True)

    kind: Kind
    text: str
    evidence: tuple[str, ...] = Field(max_length=config.REVIEW_MAX_CHUNKS)
    # True when the recommendation cites nothing: shown as the model's suggestion (PRD guardrail).
    model_suggestion: bool
    # Training only (optional for nutrition): which way to change, the source's range quoted as
    # the cited chunk has it, and the population the source studied.
    direction: str | None
    source_range: str | None
    population: str | None

    @field_validator("text")
    @classmethod
    def _text_is_short_and_not_blank(cls, text: str) -> str:
        """Strip the text and refuse a blank one or one over REVIEW_TEXT_MAX_CHARS."""
        return _checked_text(text, config.REVIEW_TEXT_MAX_CHARS)

    @field_validator("direction", "source_range", "population")
    @classmethod
    def _field_is_short(cls, value: str | None) -> str | None:
        """Strip a training field; a blank one is None, and one over the limit is refused."""
        if value is None or not value.strip():
            return None
        return _checked_text(value, config.REVIEW_FIELD_MAX_CHARS)


class WeeklyReview(BaseModel):
    """The model's draft of a weekly review (D17): what it saw, what may explain it, what to do."""

    model_config = ConfigDict(frozen=True)

    observations: tuple[Statement, ...] = Field(min_length=1, max_length=config.REVIEW_MAX_ITEMS)
    hypotheses: tuple[Statement, ...] = Field(max_length=config.REVIEW_MAX_ITEMS)
    recommendations: tuple[Recommendation, ...] = Field(max_length=config.REVIEW_MAX_ITEMS)


def _checked_text(text: str, limit: int) -> str:
    """Return the stripped text; ValueError if it is blank or longer than the limit."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > limit:
        raise ValueError("A text is blank or too long.")
    return cleaned


def _rounded(value: float | None) -> float | None:
    """Round a metric to one decimal for the model, keeping None."""
    return None if value is None else round(float(value), 1)


def _percent(part: float | None, whole: float | None) -> float | None:
    """Return part as a percentage of whole, rounded to a whole number; None if not known."""
    if part is None or not whole:
        return None
    return float(round(100 * part / whole))


def aggregates(week: dashboard.DashboardWeek, scopes: Sequence[str]) -> dict:
    """Return the week's numbers the model gets, for the scopes the review uses, as JSON values."""
    found = week.nutrition
    average = found.average
    target = found.target
    nutrition: dict = {
        "logged_days": found.logged_days,
        "days_in_week": found.days_in_week,
        "average_per_logged_day": None,
        "fiber_complete": None,
        "target": None,
        "average_minus_target": None,
        "percent_of_target": None,
        # Each day Monday first: its kcal and protein, or null when nothing was logged ("not
        # logged", never "ate nothing", AC-26).
        "days": [
            None
            if totals is None
            else {"kcal": _rounded(totals.kcal), "protein_g": _rounded(totals.protein_g)}
            for _, totals in found.days
        ],
    }
    if average is not None:
        nutrition["average_per_logged_day"] = {
            name: _rounded(getattr(average, name)) for name in (*NUTRIENTS, "fiber_g")
        }
        nutrition["fiber_complete"] = average.fiber_complete
    if target is not None:
        nutrition["target"] = {name: _rounded(getattr(target, name)) for name in NUTRIENTS}
    if found.difference is not None:
        nutrition["average_minus_target"] = {
            name: _rounded(value) for name, value in found.difference.items()
        }
    if average is not None and target is not None:
        nutrition["percent_of_target"] = {
            name: _percent(getattr(average, name), getattr(target, name)) for name in NUTRIENTS
        }
    result: dict = {
        "the_client": "the client",
        "week": {"start": found.week_start.isoformat(), "end": found.week_end.isoformat()},
        "nutrition": nutrition,
    }
    if "body" in scopes:
        result["body"] = {
            "latest_weight_kg": _rounded(found.latest_weight_kg),
            "previous_weight_kg": _rounded(found.previous_weight_kg),
            "weight_change_kg": _rounded(found.weight_change_kg),
            "weights_in_week": sum(
                1
                for day, _ in (week.weight_trend or ())
                if found.week_start <= day <= found.week_end
            ),
        }
    if "training" in scopes and week.training is not None:
        training = week.training
        result["training"] = {
            "sessions": training.sessions,
            "sets": training.sets,
            "volume_kg": _rounded(training.volume_kg),
            "exercises": [
                {
                    "exercise": exercise.exercise_id,
                    "sets": exercise.sets,
                    "reps": exercise.reps,
                    "volume_kg": _rounded(exercise.volume_kg),
                    "top_weight_kg": _rounded(exercise.top_weight_kg),
                }
                for exercise in training.exercises
            ],
        }
    return result


def data_quality(metrics: Mapping, scopes: Sequence[str]) -> dict:
    """Return what the review's numbers rest on: logged days, a target, fibre, the scopes."""
    nutrition = metrics["nutrition"]
    return {
        "logged_days": nutrition["logged_days"],
        "days_in_week": nutrition["days_in_week"],
        "target_set": nutrition["target"] is not None,
        "fiber_complete": nutrition["fiber_complete"],
        "weights_in_week": metrics.get("body", {}).get("weights_in_week"),
        "scopes": list(scopes),
    }


def evidence_topics(metrics: Mapping) -> tuple[str, ...]:
    """Return the topics the metrics raise, in a fixed order (D17)."""
    nutrition = metrics["nutrition"]
    gap = nutrition["average_minus_target"]
    target = nutrition["target"]
    topics: list[str] = []
    if gap is not None and target is not None:
        if gap["protein_g"] < -config.REVIEW_PROTEIN_GAP_SHARE * target["protein_g"]:
            topics.append("protein")
        if abs(gap["kcal"]) > config.REVIEW_KCAL_GAP_SHARE * target["kcal"]:
            topics.append("energy_balance")
    training = metrics.get("training")
    if training is not None and training["sessions"] > 0:
        topics.append(config.TRAINING_TOPIC)
    return tuple(topics)


def build_messages(
    system_prompt: str,
    metrics: Mapping,
    chunks: Sequence[RetrievedChunk],
    language: str,
    errors: Sequence[str] = (),
) -> list[SystemMessage | HumanMessage]:
    """Return the owner's prompt and one user message with the delimited blocks (data only)."""
    # The metrics are numbers and fixed keys, escaped all the same; the chunks are escaped by
    # sources_block(). On the retry, the failed checks' fixed texts follow; never the draft's text.
    parts = [
        f"<language>\n{escape_prompt_data(language)}\n</language>",
        "<metrics>\n"
        + escape_prompt_data(json.dumps(metrics, ensure_ascii=False))
        + "\n</metrics>",
        sources_block(chunks),
    ]
    if errors:
        lines = "\n".join(f"- {ERROR_TEXTS[code]}" for code in errors)
        parts.append(f"<validation_errors>\n{lines}\n</validation_errors>")
    return [SystemMessage(system_prompt), HumanMessage("\n\n".join(parts))]


def label_numbers(chunks: Sequence[RetrievedChunk]) -> dict[str, RetrievedChunk]:
    """Return each chunk by its label as <sources> shows it ("S1", "S2", ...)."""
    return {f"S{number}": chunk for number, chunk in enumerate(chunks, start=1)}


def evidence_refs(review: Mapping, chunks: Sequence[RetrievedChunk]) -> list[tuple[str, str]]:
    """Return (source_id, chunk_id) for every chunk the review cites, once each, in label order."""
    by_label = label_numbers(chunks)
    cited = {label for item in _items(review) for label in item.get("evidence", ())}
    return [
        (str(chunk.metadata["source_id"]), chunk_key(chunk))
        for label, chunk in by_label.items()
        if label in cited
    ]


def cited_sources(review: Mapping, chunks: Sequence[RetrievedChunk]) -> dict[str, dict]:
    """Return {label: {source_id, chunk_id}} for the labels the review cites, kept with its text."""
    # The [S#] labels are the run's own; the stored text keeps what each one cited, so the coach's
    # and the gymer's pages list the right source beside each label after the run has gone.
    by_label = label_numbers(chunks)
    cited = {label for item in _items(review) for label in item.get("evidence", ())}
    return {
        label: {"source_id": str(chunk.metadata["source_id"]), "chunk_id": chunk_key(chunk)}
        for label, chunk in by_label.items()
        if label in cited
    }


def _items(review: Mapping) -> Iterable[Mapping]:
    """Yield every observation, hypothesis and recommendation of a review dict."""
    for field in ("observations", "hypotheses", "recommendations"):
        yield from review.get(field, ())


def _texts(item: Mapping) -> list[str]:
    """Return an item's texts: its text and, for a recommendation, its filled fields."""
    return [
        item[field]
        for field in ("text", "direction", "source_range", "population")
        if isinstance(item.get(field), str)
    ]


def _matches_any(patterns: Sequence[str], texts: Iterable[str]) -> bool:
    """Return True if any pattern is found in any text, without case."""
    return any(re.search(pattern, text, re.I) for pattern in patterns for text in texts)


def _number_values(token: str) -> set[float]:
    """Return the values a written number may have: "2,210.5", "2.210,5", "1,6" and "1.6"."""
    found: set[float] = set()
    for thousands, decimal in ((",", "."), (".", ",")):
        if token.count(decimal) > 1:
            continue
        plain = token.replace(thousands, "").replace(decimal, ".")
        try:
            found.add(abs(float(plain)))
        except ValueError:
            continue
    return found


def numbers_in(text: str) -> list[set[float]]:
    """Return each number in a text as its possible values, leaving out dates and [S#] labels."""
    cleaned = _LABEL.sub(" ", _DATE.sub(" ", text))
    return [_number_values(token) for token in _NUMBER.findall(cleaned)]


def _metric_values(value: object) -> set[float]:
    """Return every number in the metrics, each also rounded to 0 and 1 decimals, as absolutes."""
    found: set[float] = set()
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, int | float):
        number = abs(float(value))
        return {number, float(round(number)), round(number, 1)}
    if isinstance(value, Mapping):
        value = list(value.values())
    if isinstance(value, list | tuple):
        for part in value:
            found |= _metric_values(part)
    return found


def _chunk_values(chunks: Iterable[RetrievedChunk]) -> set[float]:
    """Return every number written in the chunks' texts."""
    found: set[float] = set()
    for chunk in chunks:
        for values in numbers_in(chunk.text):
            found |= values
    return found


def normalise_range(text: str) -> str:
    """Return text for the source_range check: lower case, one dash, "to" between numbers a dash."""
    text = _DASHES.sub("-", text.lower())
    text = _TO_BETWEEN_NUMBERS.sub("-", text)
    text = _SPACES.sub(" ", text)
    return _SPACE_AROUND_DASH.sub("-", text).strip()


def _is_change(before: str, after: str) -> bool:
    """Return True if the words around a kcal figure make it a change, not an intake."""
    if before.endswith(config.REVIEW_KCAL_SIGNS):
        return True
    words = before.split()
    # "by around 300 kcal": the approximate word is skipped; "around 300 kcal" alone is no change.
    if words and words[-1] in config.REVIEW_KCAL_APPROXIMATE:
        words = words[:-1]
    if words and words[-1] in config.REVIEW_KCAL_CHANGE_BEFORE:
        return True
    following = after.split()
    return bool(following) and following[0].strip(".,;:") in config.REVIEW_KCAL_CHANGE_AFTER


def _kcal_below_floor(text: str) -> bool:
    """Return True if the text gives an intake (not a change) below the calorie floor."""
    for match in _KCAL.finditer(text):
        before = text[: match.start()].rstrip().lower()
        after = text[match.end() :].lstrip().lower()
        if _is_change(before, after):
            continue
        # "1,200" or "2.500" may be read with either mark as the decimal one; an intake is the
        # larger reading (1200 kcal, never 1.2), so "1.100 kcal" is still 1100 and below the floor.
        if max(_number_values(match.group(1)), default=0) < config.CALORIE_FLOOR_KCAL:
            return True
    return False


def _training_checks(item: Mapping, cited: Sequence[RetrievedChunk]) -> list[str]:
    """Return the failed training checks of one training recommendation (D22, AC-35)."""
    errors = []
    training = [c for c in cited if config.TRAINING_TOPIC in _topics(c)]
    if not training:
        errors.append("training_uncited")
    if not all(item.get(field) for field in ("direction", "source_range", "population")):
        errors.append("training_fields")
    elif training and not any(
        normalise_range(item["source_range"]) in normalise_range(c.text) for c in training
    ):
        errors.append("source_range")
    # The source's range is checked against its chunk; the other fields must hold no program and
    # no number of sets or volume for this client.
    own = [item[f] for f in ("text", "direction", "population") if isinstance(item.get(f), str)]
    if _matches_any(config.REVIEW_PROGRAM_PATTERNS, own):
        errors.append("program")
    if _matches_any(config.REVIEW_CLIENT_VOLUME_PATTERNS, own):
        errors.append("client_volume")
    return errors


def _topics(chunk: RetrievedChunk) -> tuple[str, ...]:
    """Return a chunk's topics from its metadata (a list, or a comma-separated text in Chroma)."""
    topics = chunk.metadata.get("topics", ())
    if isinstance(topics, str):
        return tuple(part.strip() for part in topics.split(",") if part.strip())
    return tuple(topics)


def _safety_checks(review: Mapping, chunks: Sequence[RetrievedChunk]) -> list[str]:
    """Return the failed checks a coach's edit must pass too: floor, diagnosis, training."""
    by_label = label_numbers(chunks)
    errors: list[str] = []
    for item in _items(review):
        if _matches_any(config.REVIEW_DIAGNOSIS_PATTERNS, _texts(item)):
            errors.append("diagnosis")
    for item in review.get("recommendations", ()):
        if any(_kcal_below_floor(text) for text in _texts(item)):
            errors.append("calorie_floor")
        if item.get("kind") == "training":
            cited = [by_label[label] for label in item.get("evidence", ()) if label in by_label]
            errors.extend(_training_checks(item, cited))
    return errors


def validate(review: Mapping, chunks: Sequence[RetrievedChunk], metrics: Mapping) -> list[str]:
    """Return the codes of every failed check of a draft (empty when it passes), each once."""
    try:
        WeeklyReview.model_validate(review)
    except ValueError:
        return ["schema"]
    by_label = label_numbers(chunks)
    errors: list[str] = []
    allowed = _metric_values(metrics) | {float(config.CALORIE_FLOOR_KCAL)}
    for item in _items(review):
        labels = item.get("evidence", ())
        if any(label not in by_label for label in labels):
            errors.append("unknown_evidence")
        if item.get("kind") == "training":
            continue  # its numbers are the source's range, checked against the chunk
        cited = _chunk_values(by_label[label] for label in labels if label in by_label)
        for text in _texts(item):
            if any(not (values & (allowed | cited)) for values in numbers_in(text)):
                errors.append("number")
    for item in review.get("recommendations", ()):
        if item.get("kind") == "nutrition" and item["model_suggestion"] != (not item["evidence"]):
            errors.append("suggestion_label")
        if item.get("kind") == "training" and item["model_suggestion"]:
            errors.append("training_uncited")
    errors.extend(_safety_checks(review, chunks))
    return list(dict.fromkeys(errors))


def check_edit(edited: Mapping, chunks: Sequence[RetrievedChunk]) -> list[str]:
    """Return the failed checks of the coach's edit: schema, floor, diagnosis, training (AC-35)."""
    try:
        WeeklyReview.model_validate(edited)
    except ValueError:
        return ["schema"]
    return list(dict.fromkeys(_safety_checks(edited, chunks)))


def as_draft(review: WeeklyReview, language: str) -> dict:
    """Return the model's review as the stored draft: its fields as JSON, and the language."""
    return {**review.model_dump(mode="json"), "language": language}


# The keys a stored review text adds to the model's fields.
STORED_KEYS = ("language", "sources", "model")


def without_language(draft: Mapping) -> dict:
    """Return a stored review text's own fields, without the language or the sources it cites."""
    return {key: value for key, value in draft.items() if key not in STORED_KEYS}
