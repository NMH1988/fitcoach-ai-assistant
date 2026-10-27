"""Checks and formats for the values the store writes (T9.6).

The tables check types, ranges and enums too (`schema.py`); these checks run first so a bad value
fails with a fixed message that names the field, never the value: a message can reach a traceback,
and a stored value must not appear in one (AC-33).
"""

import math
from datetime import UTC, date, datetime

from src import config


class StoreValueError(ValueError):
    """Raised when a value cannot be stored; the message names the field, never the value."""

    def __init__(self, field: str, problem: str) -> None:
        """Keep the field's name and a fixed description of the problem."""
        super().__init__(field, problem)
        self.field = field
        self.problem = problem

    def __str__(self) -> str:
        """Return e.g. "grams must be above zero"."""
        # Joined, not formatted: src/store/ builds no strings with f-strings, % or + (the SQL scan).
        return " ".join((self.field, self.problem))


def utc_text(moment: datetime | None = None) -> str:
    """Return a moment (now by default) as UTC ISO 8601 text ending in +00:00 (D21)."""
    moment = datetime.now(UTC) if moment is None else moment
    if moment.tzinfo is None:
        # A naive time could be any zone; storing it as UTC would shift it silently.
        raise StoreValueError("moment", "needs a time zone")
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def date_text(day: date, field: str) -> str:
    """Return a calendar day as ISO text (YYYY-MM-DD)."""
    if not isinstance(day, date) or isinstance(day, datetime):
        raise StoreValueError(field, "must be a date")
    return day.isoformat()


def user_id(value: object, field: str = "user_id") -> str:
    """Return a user ID if it is non-empty text within the length limit."""
    if not isinstance(value, str) or not 0 < len(value) <= config.STORE_ID_MAX_CHARS:
        raise StoreValueError(field, "is not a valid user ID")
    return value


def text(value: object, field: str, max_chars: int | None = None) -> str:
    """Return text with something besides spaces in it, within the length limit."""
    limit = config.STORE_TEXT_MAX_CHARS if max_chars is None else max_chars
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise StoreValueError(field, "must be non-empty text within the length limit")
    return value


def _finite(value: int | float) -> bool:
    """Return True if the number is finite and fits in a float (SQLite's REAL)."""
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large for a float
        return False


def number(value: object, field: str, *, positive: bool = False) -> float:
    """Return a finite number that is not negative (or above zero when `positive`)."""
    # bool is an int in Python; True would be stored as 1.
    if isinstance(value, bool) or not isinstance(value, int | float) or not _finite(value):
        raise StoreValueError(field, "must be a finite number")
    if positive and value <= 0:
        raise StoreValueError(field, "must be above zero")
    if value < 0:
        raise StoreValueError(field, "must be zero or more")
    return float(value)


def whole_number(value: object, field: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    """Return an integer from `minimum` to `maximum` (no upper limit when it is None)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise StoreValueError(field, "must be a whole number within its range")
    if maximum is not None and value > maximum:
        raise StoreValueError(field, "must be a whole number within its range")
    return value


def in_range(value: object, field: str, bounds: tuple[float, float]) -> float:
    """Return a finite number from bounds[0] to bounds[1], both included."""
    number_ = number(value, field)
    if not bounds[0] <= number_ <= bounds[1]:
        raise StoreValueError(field, "is outside its allowed range")
    return number_


def choice(value: object, field: str, allowed: tuple[str, ...]) -> str:
    """Return the value if it is one of the allowed texts."""
    if value not in allowed:
        raise StoreValueError(field, "is not one of the allowed values")
    return value
