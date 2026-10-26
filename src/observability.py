"""The app's JSON log lines: one record per chat turn and a warning per failure (T8.2).

Records go to stderr only, one JSON object per line, and hold only fields from `ALLOWED_FIELDS`:
ids, counts, codes, statuses and durations. Never the question, a rewrite, the answer, chunk text,
profile values, tool arguments or the key (.claude/rules/security-privacy.md). Two rules keep that
true even if a caller slips: the formatter drops every `extra` field that is not on the list, and it
ignores the message's arguments and any exception, so an error's text or a traceback cannot reach a
line. The event is a fixed name too: a message that is not one of `EVENTS` (an f-string, an
exception object, a word) is written as `unnamed_event`. A field's value must be plain (text, a
number, a boolean, None or a flat list of them): an object such as an exception is never turned
into text, and the record becomes a `log_failed` line instead.
"""

import json
import logging
import threading
from datetime import UTC, datetime
from typing import IO

from src import config

# The app's logger: every module's `logging.getLogger(__name__)` under `src.` reports through it.
LOGGER_NAME = "src"

# The app's events; a message that is not one of them is written as UNNAMED_EVENT. Add a name here
# when a new kind of record is added (docs/ARCHITECTURE.md section 10).
LOG_FAILED_EVENT = "log_failed"
EVENTS = frozenset(
    {"turn", "turn_error", "llm_error", "guard_rejected", "tool_failed", LOG_FAILED_EVENT}
)
UNNAMED_EVENT = "unnamed_event"
_PLAIN = (str, int, float, bool, type(None))
# The libraries whose own loggers could write a prompt, the profile or the key at DEBUG level (the
# OpenAI SDK logs its request options, httpcore its headers). They bypass the allowlist, so
# configure_logging() keeps them at WARNING.
_CHATTY_LIBRARIES = ("openai", "httpx", "httpcore")

# The only fields a record may carry besides ts, level, logger and event. None of them holds text
# the user typed or the model wrote (docs/SECURITY.md, "What is logged").
ALLOWED_FIELDS = frozenset(
    {
        # The turn record.
        "turn_id",
        "kind",
        "code",
        "language",
        "chunks",
        "source_ids",
        "tools",
        "tool_statuses",
        "tokens",
        "cost_usd",
        "duration_ms",
        "profile_sent",
        # The warnings and the error line.
        "diagnostic",
        "status_code",
        "reason",
        "tool",
        "status",
    }
)


def _is_plain(value: object) -> bool:
    """Return True for text, a number, a boolean, None, or a flat list or tuple of them."""
    if isinstance(value, list | tuple):
        return all(isinstance(item, _PLAIN) for item in value)
    return isinstance(value, _PLAIN)


def _base_fields(record: logging.LogRecord) -> dict[str, object]:
    """Return the time, level and logger name every line starts with."""
    return {
        "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
        "level": record.levelname,
        "logger": record.name,
    }


class JsonFormatter(logging.Formatter):
    """Format a record as one line of JSON with ts, level, logger, event and allowed fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a JSON line, without unknown fields, arguments or exceptions."""
        entry = _base_fields(record)
        # The event is a fixed name; `args` are never applied, so a value put there stays out.
        entry["event"] = record.msg if record.msg in EVENTS else UNNAMED_EVENT
        for name in sorted(ALLOWED_FIELDS):
            if name in record.__dict__:
                value = record.__dict__[name]
                if not _is_plain(value):
                    # E.g. an exception passed instead of its diagnostic: its text could quote the
                    # question or a server's reply. The handler writes a log_failed line instead.
                    raise TypeError(f"log field {name} is not a plain value")
                entry[name] = value
        return json.dumps(entry)


class _JsonHandler(logging.StreamHandler):
    """The handler configure_logging() installs, so a second call finds it again."""

    # Found by this marker, not by class: Streamlit's reloader can define the class again.
    is_app_handler = True

    def handleError(self, record: logging.LogRecord) -> None:
        """Write a fixed line when a record cannot be written, never the record or its arguments."""
        # The default prints the message, its arguments and a traceback to stderr, outside the
        # allowlist; a value json.dumps cannot write (e.g. an integer of 5,000 digits) lands here.
        try:
            line = json.dumps({**_base_fields(record), "event": LOG_FAILED_EVENT})
            self.stream.write(line + "\n")
        except Exception:  # noqa: BLE001 - nothing more can be done for a broken stream
            pass


# Streamlit runs the script of every session in its own thread, on every rerun.
_LOCK = threading.Lock()


def configure_logging(level: str | int | None = None, stream: IO[str] | None = None) -> None:
    """Send the app's log lines to stderr as JSON; calling it again keeps the one handler."""
    # No file handler: the lines go to the process's stderr and the host decides where they land.
    # `stream` is for tests. propagate is off, so a handler on the root logger cannot print the
    # same record in its own format.
    logger = logging.getLogger(LOGGER_NAME)
    with _LOCK:
        handler = next((h for h in logger.handlers if getattr(h, "is_app_handler", False)), None)
        if handler is None:
            handler = _JsonHandler(stream)
            handler.setFormatter(JsonFormatter())
            logger.addHandler(handler)
        elif stream is not None and isinstance(handler, logging.StreamHandler):
            handler.setStream(stream)
        logger.setLevel(config.LOG_LEVEL if level is None else level)
        logger.propagate = False
        for name in _CHATTY_LIBRARIES:
            logging.getLogger(name).setLevel(logging.WARNING)
