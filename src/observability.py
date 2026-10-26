"""The app's JSON log lines: one record per chat turn and a warning per failure (T8.2).

Records go to stderr only, one JSON object per line, and hold only fields from `ALLOWED_FIELDS`:
ids, counts, codes, statuses and durations. Never the question, a rewrite, the answer, chunk text,
profile values, tool arguments or the key (.claude/rules/security-privacy.md). Two rules keep that
true even if a caller slips: the formatter drops every `extra` field that is not on the list, and it
ignores the message's arguments and any exception, so an error's text or a traceback cannot reach a
line. The event is a fixed name too: a message that is not a short lowercase name (an f-string, an
exception object) is written as `unnamed_event`.
"""

import json
import logging
import re
import threading
from datetime import UTC, datetime
from typing import IO

from src import config

# The app's logger: every module's `logging.getLogger(__name__)` under `src.` reports through it.
LOGGER_NAME = "src"

# What an event name looks like: `turn`, `guard_rejected`. Anything else is not a name.
_EVENT_NAME = re.compile(r"[a-z][a-z_]{0,39}")
# The event written for a message that is not a name.
UNNAMED_EVENT = "unnamed_event"
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


class JsonFormatter(logging.Formatter):
    """Format a record as one line of JSON with ts, level, logger, event and allowed fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a JSON line, without unknown fields, arguments or exceptions."""
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            # The event is a fixed name; `args` are never applied, so a value put there stays out.
            "event": record.msg
            if isinstance(record.msg, str) and _EVENT_NAME.fullmatch(record.msg)
            else UNNAMED_EVENT,
        }
        for name in sorted(ALLOWED_FIELDS):
            if name in record.__dict__:
                entry[name] = record.__dict__[name]
        return json.dumps(entry, default=str)


class _JsonHandler(logging.StreamHandler):
    """The handler configure_logging() installs, so a second call finds it again."""

    # Found by this marker, not by class: Streamlit's reloader can define the class again.
    is_app_handler = True

    def handleError(self, record: logging.LogRecord) -> None:
        """Write a fixed line when a record cannot be written, never the record or its arguments."""
        # The default prints the message, its arguments and a traceback to stderr, outside the
        # allowlist; a value json.dumps cannot write (e.g. an integer of 5,000 digits) lands here.
        try:
            self.stream.write('{"event": "log_failed"}\n')
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
