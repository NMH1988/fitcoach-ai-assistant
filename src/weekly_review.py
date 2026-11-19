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
- The calorie floor is checked by arithmetic on a recommendation's two kcal fields (`target_kcal`,
  and the client's current target plus `kcal_change`), and on its texts by the patterns in config,
  which stay as the fallback for a figure written only in prose.

Each failed check is a code; the workflow sends the codes' fixed texts back to the model once.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src import config, dashboard, guardrails
from src.chat import sources_block
from src.prompt_data import escape_prompt_data
from src.rag.retriever import RetrievedChunk, chunk_key

Kind = Literal["nutrition", "training"]
NUTRIENTS = ("kcal", "protein_g", "carbohydrate_g", "fat_g")
# A recommendation's kcal figures as numbers (T10.2): a proposed daily intake, and a change to the
# client's current target (negative for a deficit).
KCAL_FIELDS = ("target_kcal", "kcal_change")
_LABEL = re.compile(r"\[?\bS(\d+)\b\]?")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_DASHES = re.compile(r"[‐-―−-]")
_TO_BETWEEN_NUMBERS = re.compile(r"(?<=\d)\s*(?:to|bis)\s*(?=\d)")
_SPACE_AROUND_DASH = re.compile(r"\s*-\s*")
_SPACES = re.compile(r"\s+")
# A figure: digits with thousands or decimal marks, and "k" for a thousand when no letter follows
# it ("1k kcal"; "1000kcal" is 1000, never 1000k).
_FIGURE = r"\d+(?:[.,]\d+)*(?:k(?![a-z]))?"
# One optional approximate word before a figure of a range ("between about 1,000 and 1,300 kcal",
# "zwischen ca. 1.000 und etwa 1.300 kcal"), so the lower end is not lost. It starts a word, so
# "some" in "wholesome" is no approximate word.
_APPROXIMATE = (
    r"(?:\b(?:" + "|".join(re.escape(word) for word in config.REVIEW_KCAL_APPROXIMATE) + r")\s+)?"
)
# A word of letters only, for the whole-word change words.
_LETTER_WORD = re.compile(r"[^\W\d_]+")
# A kcal figure, or a range of two, checked from its lower end: "between X and Y" ("zwischen X und
# Y"), or X and Y joined by a dash, "to", "bis", "up to" or "bis zu" ("pair" or "low" is the lower
# end, "high" the figure or the upper end). A unit may follow a hyphen ("a 1,000-calorie day") and
# be written in any of its usual forms ("kcals", "Kilokalorien").
_PAIR = r"(?:between|zwischen)\s+" + _APPROXIMATE + r"(?P<pair>" + _FIGURE + r")\s*(?:and|und)\s*"
_LOW = r"(?P<low>" + _FIGURE + r")\s*(?:[\u2010-\u2015\u2212-]|to|bis|up\s+to|bis\s+zu)\s*"
_UNIT = r"\s*-?\s*(?:k?cals?|kilo\s?calories?|calories?|kilokalorien|kalorien)\b"
_KCAL = re.compile(
    r"(?:" + _PAIR + r"|" + _LOW + r")?" + _APPROXIMATE + r"(?P<high>" + _FIGURE + r")" + _UNIT,
    re.I,
)
# A mark that ends a sentence: a full stop, "!", "?" or ";" before a capital letter or the end, so
# "2.500", "ca." and "e.g." do not cut a sentence short. German capitalises nouns, so "z. B."
# before a noun still ends one; a change verb before it is then not seen and the figure is read as
# an intake, which fails safe.
_SENTENCE_END = re.compile(r"[.!?;](?=\s+[A-ZÄÖÜ]|\s*$)")

# The fixed text the model gets back for each failed check, on the one retry (English, as the
# prompt is; the coach sees these codes as their own texts in src/i18n/reviews.py).
ERROR_TEXTS: dict[str, str] = {
    "schema": "The reply did not follow the schema.",
    "unknown_evidence": "A citation names a label that is not in <sources>.",
    "observation_evidence": (
        "An observation cites a source; observations come from <metrics> only, so leave their "
        "evidence empty."
    ),
    "calorie_floor": (
        "A recommendation, or a hypothesis that cites a source, names a kcal figure below "
        f"{config.CALORIE_FLOOR_KCAL} kcal a day, or a recommendation's target_kcal, or the "
        f"client's current target plus its kcal_change, is below {config.CALORIE_FLOOR_KCAL} kcal "
        "a day; put the client's current intake in an observation and describe only the "
        'direction of the change, or write a change as "reduce intake by 300 kcal" or "a 300 kcal '
        'deficit".'
    ),
    "kcal_change_no_target": (
        "A recommendation sets kcal_change, but <metrics> has no current target to change; set "
        "kcal_change to null."
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
    """An observation or a hypothesis, with the labels of the sources it cites."""

    # The docstrings and field descriptions of the three review models reach the model as the
    # JSON schema's descriptions: their wording is the owner's (O18), so change it only with the
    # owner.
    model_config = ConfigDict(frozen=True)

    # No default and no string length in the schema (OpenAI's strict mode), so both are checked
    # by the validators below.
    text: str = Field(
        description=(
            "One observation grounded only in <metrics>, or one hypothesis in cautious language; "
            "in the review's language."
        )
    )
    evidence: tuple[str, ...] = Field(
        max_length=config.REVIEW_MAX_CHUNKS,
        description="Labels from <sources> that support this item, such as S1; empty for an "
        "observation.",
    )

    @field_validator("text")
    @classmethod
    def _text_is_short_and_not_blank(cls, text: str) -> str:
        """Strip the text and refuse a blank one or one over REVIEW_TEXT_MAX_CHARS."""
        return _checked_text(text, config.REVIEW_TEXT_MAX_CHARS)


class Recommendation(BaseModel):
    """A recommendation addressed to the coach, nutrition or training, with its evidence."""

    model_config = ConfigDict(frozen=True)

    kind: Kind = Field(description="nutrition or training.")
    text: str = Field(
        description=(
            "The recommendation, addressed to the coach, not written as a direct instruction to "
            "the client."
        )
    )
    evidence: tuple[str, ...] = Field(
        max_length=config.REVIEW_MAX_CHUNKS,
        description=(
            "Labels from <sources> that support this recommendation, such as S1; at least one for "
            "a training recommendation."
        ),
    )
    # True when the recommendation cites nothing: shown as the model's suggestion (PRD guardrail).
    model_suggestion: bool = Field(
        description="true when the recommendation cites no source; false when it cites one or more."
    )
    # Training only (optional for nutrition): which way to change, the source's range quoted as
    # the cited chunk has it, and the population the source studied.
    direction: str | None = Field(
        description=(
            "Training: what should be increased, decreased, or maintained, without a "
            "client-specific amount."
        )
    )
    source_range: str | None = Field(
        description=(
            "Training: the relevant range or recommendation copied verbatim from the cited source "
            "in its original English wording."
        )
    )
    population: str | None = Field(
        description=(
            "Training: the population studied, using only information supported by the cited "
            "source."
        )
    )
    # The kcal figures as numbers, so the floor is checked by arithmetic, not read out of the text.
    # The descriptions reach the model in the schema (wording approved by the owner, O18); the
    # ranges are checked by the validator below, as the rest of the schema keeps its limits there.
    target_kcal: int | None = Field(
        description=(
            "A daily energy intake in kcal that this recommendation proposes for the client, or "
            f"null when it proposes none. Never below {config.CALORIE_FLOOR_KCAL} kcal per day. "
            "Use only a number from <metrics> or from a source this recommendation cites."
        )
    )
    kcal_change: int | None = Field(
        description=(
            "A change in kcal per day to the client's current target (target.kcal in <metrics>): "
            "negative to reduce, positive to raise; null when the recommendation proposes no "
            "change in kcal. Use only a number from <metrics>, such as average_minus_target, or "
            "from a source this recommendation cites."
        )
    )

    @field_validator("text")
    @classmethod
    def _text_is_short_and_not_blank(cls, text: str) -> str:
        """Strip the text and refuse a blank one or one over REVIEW_TEXT_MAX_CHARS."""
        return _checked_text(text, config.REVIEW_TEXT_MAX_CHARS)

    @field_validator("target_kcal", "kcal_change", mode="before")
    @classmethod
    def _kcal_is_whole(cls, value: object) -> object:
        """Refuse anything but a whole number or None: pydantic would read True or "1800" as one."""
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("A kcal field is not a whole number.")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("A kcal field is not a whole number.")
        return value

    @field_validator("target_kcal")
    @classmethod
    def _target_in_range(cls, value: int | None) -> int | None:
        """Refuse a target outside REVIEW_TARGET_KCAL_RANGE."""
        return _in_range(value, config.REVIEW_TARGET_KCAL_RANGE)

    @field_validator("kcal_change")
    @classmethod
    def _change_in_range(cls, value: int | None) -> int | None:
        """Refuse a change outside REVIEW_KCAL_CHANGE_RANGE."""
        return _in_range(value, config.REVIEW_KCAL_CHANGE_RANGE)

    @field_validator("direction", "source_range", "population")
    @classmethod
    def _field_is_short(cls, value: str | None) -> str | None:
        """Strip a training field; a blank one is None, and one over the limit is refused."""
        if value is None or not value.strip():
            return None
        return _checked_text(value, config.REVIEW_FIELD_MAX_CHARS)


class WeeklyReview(BaseModel):
    """A draft weekly review for the coach."""

    model_config = ConfigDict(frozen=True)

    observations: tuple[Statement, ...] = Field(
        min_length=1,
        max_length=config.REVIEW_MAX_ITEMS,
        description="Factual observations grounded only in <metrics>; at least one.",
    )
    hypotheses: tuple[Statement, ...] = Field(
        max_length=config.REVIEW_MAX_ITEMS,
        description=(
            "Possible explanations in cautious language, not conclusions or diagnoses, and never "
            "implying a medical condition."
        ),
    )
    recommendations: tuple[Recommendation, ...] = Field(
        max_length=config.REVIEW_MAX_ITEMS,
        description="Practical recommendations for the coach.",
    )


def _checked_text(text: str, limit: int) -> str:
    """Return the stripped text; ValueError if it is blank or longer than the limit."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > limit:
        raise ValueError("A text is blank or too long.")
    return cleaned


def _in_range(value: int | None, limits: tuple[int, int]) -> int | None:
    """Return the value if it is None or within the limits, ends included; else ValueError."""
    if value is not None and not limits[0] <= value <= limits[1]:
        raise ValueError("A kcal field is out of its range.")
    return value


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


def _words_before(before: str) -> list[str]:
    """Return the words before a kcal figure, without an approximate word right before it."""
    words = before.split()
    # "by around 300 kcal": the approximate word is skipped; "around 300 kcal" alone is no change.
    if words and words[-1] in config.REVIEW_KCAL_APPROXIMATE:
        words = words[:-1]
    return words


def _sentence(text: str, start: int, end: int) -> str:
    """Return the sentence around text[start:end], in lower case."""
    begin = 0
    for found in _SENTENCE_END.finditer(text):
        if found.end() <= start:
            begin = found.end()
    stop = _SENTENCE_END.search(text, end)
    return text[begin : stop.start() if stop else len(text)].lower()


def _is_change(raw_before: str, after: str, sentence: str) -> bool:
    """Return True if the words around a kcal figure make it a change, not an intake."""
    before = raw_before.rstrip()
    # A sign touching the figure ("-300 kcal"); "Target - 1,000 kcal" has a dash, not a sign, and
    # a dash right after a digit is never read as a sign.
    if (
        raw_before.endswith(config.REVIEW_KCAL_SIGNS)
        and not raw_before[:-1].rstrip()[-1:].isdigit()
    ):
        return True
    words = _words_before(before)
    if words and words[-1] in config.REVIEW_KCAL_CHANGE_BEFORE:
        # "by"/"um" with a change verb in the same sentence, before the figure or after it as
        # German often puts it ("Die Zufuhr um 300 kcal senken"); "Die Zufuhr sollte um 1.000
        # kcal liegen" is an intake. A zu-infinitive counts only as a whole word.
        if any(verb in sentence for verb in config.REVIEW_KCAL_CHANGE_VERBS):
            return True
        if set(_LETTER_WORD.findall(sentence)) & set(config.REVIEW_KCAL_CHANGE_WORDS):
            return True
    following = [word.strip(".,;:").rstrip(")") for word in after.split()]
    # Only closing marks are stripped: "1,000 kcal (less than usual)" is an intake with a remark,
    # not a change; "more or less" is no change.
    if not following or following[0] not in config.REVIEW_KCAL_CHANGE_AFTER:
        return False
    return following[1:3] not in (["or", "less"], ["oder", "weniger"])


def _kcal(text: str) -> float:
    """Return a written kcal figure as an intake: "1,200" and "1.200" are 1200, never 1.2."""
    # Either mark may be the decimal one; an intake is the larger reading, so "1.100 kcal" is
    # still 1100 and below the floor. "1k" is 1000, and "1.1k" is 1100 (its smaller reading).
    if text.lower().endswith("k"):
        return 1000 * min(_number_values(text[:-1]), default=0.0)
    return max(_number_values(text), default=0.0)


def _kcal_below_floor(text: str) -> bool:
    """Return True if the text holds a kcal figure below the floor that is not a change."""
    # A recommendation names no kcal figure below the floor at all, not even the client's current
    # intake: "an average of 1,000 kcal" reads as a target as easily as a fact, so the current value
    # belongs in an observation (T9.16; the prompt says so). Only a change ("by 300 kcal", "a 300
    # kcal deficit") is not an intake.
    for match in _KCAL.finditer(text):
        before = text[: match.start()].lower()
        after = text[match.end() :].lstrip().lower()
        lower, upper = match.group("pair") or match.group("low"), match.group("high")
        if _is_change(before, after, _sentence(text, match.start(), match.end())):
            continue
        # A range is an intake from its lower end: "1,000-1,600 kcal" is below the floor.
        lowest = _kcal(upper) if lower is None else min(_kcal(lower), _kcal(upper))
        if lowest < config.CALORIE_FLOOR_KCAL:
            return True
    return False


def _is_a_range(text: str) -> bool:
    """Return True if a source_range is long enough and holds a number and a word (its unit)."""
    found = normalise_range(text)
    return (
        len(found) >= config.REVIEW_SOURCE_RANGE_MIN_CHARS
        and any(char.isdigit() for char in found)
        and any(char.isalpha() for char in found)
    )


def _training_checks(item: Mapping, cited: Sequence[RetrievedChunk]) -> list[str]:
    """Return the failed training checks of one training recommendation (D22, AC-35)."""
    errors = []
    training = [c for c in cited if config.TRAINING_TOPIC in _topics(c)]
    if not training:
        errors.append("training_uncited")
    if not all(item.get(field) for field in ("direction", "source_range", "population")):
        errors.append("training_fields")
    elif training and not (
        _is_a_range(item["source_range"])
        and any(normalise_range(item["source_range"]) in normalise_range(c.text) for c in training)
    ):
        errors.append("source_range")
    # The source's range is checked against its chunk; the other fields must hold no program and
    # no number of sets or volume for this client.
    own = [item[f] for f in ("text", "direction", "population") if isinstance(item.get(f), str)]
    if guardrails.matches_any(config.REVIEW_PROGRAM_PATTERNS, own):
        errors.append("program")
    if guardrails.matches_any(config.REVIEW_CLIENT_VOLUME_PATTERNS, own):
        errors.append("client_volume")
    return errors


def _topics(chunk: RetrievedChunk) -> tuple[str, ...]:
    """Return a chunk's topics from its metadata (a list, or a comma-separated text in Chroma)."""
    topics = chunk.metadata.get("topics", ())
    if isinstance(topics, str):
        return tuple(part.strip() for part in topics.split(",") if part.strip())
    return tuple(topics)


def with_kcal_fields(review: object) -> object:
    """Return the review with None for each kcal field a recommendation lacks; else unchanged."""
    # A draft stored before T10.2 has no kcal fields, and the schema needs both; a missing field
    # says what null says: no figure. Anything that is not a review is left for the schema to fail.
    if not isinstance(review, Mapping):
        return review
    if not isinstance(review.get("recommendations"), list | tuple):
        return review
    blank = dict.fromkeys(KCAL_FIELDS)
    found = [
        {**blank, **item} if isinstance(item, Mapping) else item
        for item in review["recommendations"]
    ]
    return {**review, "recommendations": found}


def current_target_kcal(metrics: Mapping) -> float | None:
    """Return the client's current kcal target from the metrics, or None when there is none."""
    nutrition = metrics.get("nutrition")
    target = nutrition.get("target") if isinstance(nutrition, Mapping) else None
    kcal = target.get("kcal") if isinstance(target, Mapping) else None
    return float(kcal) if isinstance(kcal, int | float) and not isinstance(kcal, bool) else None


def _kcal_field_checks(item: Mapping, target: float | None) -> list[str]:
    """Return the failed floor checks of a recommendation's kcal fields, by plain arithmetic."""
    errors = []
    floor = config.CALORIE_FLOOR_KCAL
    proposed = item.get("target_kcal")
    if proposed is not None and proposed < floor:
        errors.append("calorie_floor")
    change = item.get("kcal_change")
    if change is not None:
        # A change with nothing to change is failed, not skipped, so the coach sees it.
        if target is None:
            errors.append("kcal_change_no_target")
        elif target + change < floor:
            errors.append("calorie_floor")
    return errors


def _safety_checks(
    review: Mapping, chunks: Sequence[RetrievedChunk], metrics: Mapping
) -> list[str]:
    """Return the failed checks a coach's edit must pass too: floor, diagnosis, training."""
    by_label = label_numbers(chunks)
    target = current_target_kcal(metrics)
    errors: list[str] = []
    for item in _items(review):
        if guardrails.matches_any(config.REVIEW_DIAGNOSIS_PATTERNS, _texts(item)):
            errors.append("diagnosis")
    # A hypothesis that cites a source gets the floor check too: its figure comes from the source,
    # not the client's week, and may read as advice; one without a citation may name the client's
    # own current intake, as an observation does.
    cited_hypotheses = [h for h in review.get("hypotheses", ()) if h.get("evidence")]
    for item in cited_hypotheses:
        if any(_kcal_below_floor(text) for text in _texts(item)):
            errors.append("calorie_floor")
    for item in review.get("recommendations", ()):
        # The fields are checked on every kind of recommendation: a training one has no business
        # with a kcal figure, and failing safe costs nothing.
        errors.extend(_kcal_field_checks(item, target))
        if any(_kcal_below_floor(text) for text in _texts(item)):
            errors.append("calorie_floor")
        if item.get("kind") == "training":
            cited = [by_label[label] for label in item.get("evidence", ()) if label in by_label]
            errors.extend(_training_checks(item, cited))
    return errors


def validate(review: Mapping, chunks: Sequence[RetrievedChunk], metrics: Mapping) -> list[str]:
    """Return the codes of every failed check of a draft (empty when it passes), each once."""
    review = with_kcal_fields(review)
    try:
        WeeklyReview.model_validate(review)
    except ValueError:
        return ["schema"]
    by_label = label_numbers(chunks)
    errors: list[str] = []
    allowed = _metric_values(metrics) | {float(config.CALORIE_FLOOR_KCAL)}
    # An observation comes from <metrics> only (the prompt says so): a citation would let it carry a
    # source's figure, worded as advice, past the floor check.
    if any(item.get("evidence") for item in review.get("observations", ())):
        errors.append("observation_evidence")
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
        # The kcal fields follow the texts' number rule, on every kind: otherwise a field would
        # carry a figure the text may not.
        labels = item.get("evidence", ())
        cited = _chunk_values(by_label[label] for label in labels if label in by_label)
        for field in KCAL_FIELDS:
            value = item.get(field)
            if value is not None and abs(float(value)) not in allowed | cited:
                errors.append("number")
    errors.extend(_safety_checks(review, chunks, metrics))
    return list(dict.fromkeys(errors))


def check_edit(
    edited: Mapping, chunks: Sequence[RetrievedChunk], metrics: Mapping | None = None
) -> list[str]:
    """Return the failed checks of the coach's edit: schema, floor, diagnosis, training (AC-35)."""
    # The metrics' target is the client's current one, read when the edit is checked
    # (src/agent/review.py), as that is the target a kcal_change applies to. No metrics means no
    # target, so a kcal_change then fails closed with kcal_change_no_target.
    edited = with_kcal_fields(edited)
    try:
        WeeklyReview.model_validate(edited)
    except ValueError:
        return ["schema"]
    return list(dict.fromkeys(_safety_checks(edited, chunks, metrics or {})))


def sets_kcal_change(review: object) -> bool:
    """Return True if any recommendation of a review dict sets a kcal_change."""
    found = review.get("recommendations") if isinstance(review, Mapping) else None
    return isinstance(found, list | tuple) and any(
        isinstance(item, Mapping) and item.get("kcal_change") is not None for item in found
    )


def check_approval(draft: Mapping, metrics: Mapping) -> list[str]:
    """Return the failed floor checks of a draft's kcal fields against the client's target now."""
    # The draft passed every check against the week's target; on Approve, a kcal_change is added
    # to the target in force when the coach decides, as on an edit (T10.2).
    target = current_target_kcal(metrics)
    errors: list[str] = []
    for item in with_kcal_fields(draft).get("recommendations", ()):
        if isinstance(item, Mapping):
            errors.extend(_kcal_field_checks(item, target))
    return list(dict.fromkeys(errors))


def as_draft(review: WeeklyReview, language: str) -> dict:
    """Return the model's review as the stored draft: its fields as JSON, and the language."""
    return {**review.model_dump(mode="json"), "language": language}


# The keys a stored review text adds to the model's fields.
STORED_KEYS = ("language", "sources", "model")


def without_language(draft: Mapping) -> dict:
    """Return a stored review text's own fields, without the language or the sources it cites."""
    return {key: value for key, value in draft.items() if key not in STORED_KEYS}
