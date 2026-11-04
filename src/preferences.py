"""The coach's long-term memory (T9.7, D12): checks on a proposed preference, and <memories>.

A preference is one of the coach's own working preferences ("keep answers short"), never a
client's personal or health data. The code checks what it can before a proposal is shown and again
before it is saved (AC-36): the input guard (length, injection patterns) and the domain guardrails
(medical conditions, pregnancy, medication, ...), with no rate limit; and the display name of every
client the coach has had, active or ended, read through `users.list_relationships()` (which reads
each name with `users.display_name_of()`, not audited: owner's choice, 2026-11-03). A name matches
as a whole word, all its words in a row, without case, so a client named "Max" blocks "MAX eats
late" but not "maximum protein". Descriptive data with no name (an age and a weight) is not caught:
the card's note and the coach's approval cover it.

Saved preferences reach the model of the coach's chat only, inside a delimited <memories> block
before the question, never in the system prompt (`memories_block()`).
"""

import logging
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src import config, guard
from src.prompt_data import escape_prompt_data
from src.store import records, users

logger = logging.getLogger(__name__)

PREFERENCE_TOOL = "remember_preference"
# What the model reads about the tool; the owner's prompt part says when to call it (O8).
PREFERENCE_DESCRIPTION = (
    "Propose saving one of the coach's own working preferences: how the coach works or wants "
    "answers (e.g. 'keep answers short', 'most of my clients are vegetarian'), so later chats "
    "follow it. The coach saves, edits or discards it on a card; nothing is saved without their "
    "approval. A preference never holds personal or health data about a client or a group of "
    "clients: no names, ages, weights, medical conditions, pregnancy or medication. Not about "
    "units or the response language, which the app sets. One short text of at most "
    f"{config.PREFERENCE_MAX_CHARS} characters."
)

# The guard's reasons, as a proposal's refusal codes (config.PREFERENCE_REFUSED_MESSAGES).
_REFUSALS = {
    guard.Rejection.EMPTY: "invalid",
    guard.Rejection.TOO_LONG: "invalid",
    guard.Rejection.INJECTION: "injection",
    guard.Rejection.GUARDRAIL: "guardrail",
}


@dataclass(frozen=True)
class PreferenceCheck:
    """A proposed text's check: the cleaned text if it may be proposed, else a refusal code."""

    allowed: bool
    text: str = ""
    # A key of config.PREFERENCE_REFUSED_MESSAGES; None when allowed.
    code: str | None = None


@dataclass(frozen=True)
class CoachMemory:
    """What a coach's chat turn needs from the store, read before the turn: names, preferences."""

    coach_id: str
    # The display names of every client the coach has had, active or ended.
    client_names: tuple[str, ...] = ()
    # The newest saved preferences (at most config.MEMORY_PREFERENCES_IN_PROMPT), oldest first.
    preferences: tuple[str, ...] = ()


@dataclass
class Proposals:
    """A turn's proposals: the texts that passed the checks, and the refusals' codes."""

    texts: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)


class PreferenceArgs(BaseModel):
    """remember_preference's one argument: the text of the preference, nothing else."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=config.PREFERENCE_MAX_CHARS)


def _not_run(**_: object) -> str:
    """Stand for the tool's function: a call is only ever handled by propose()."""
    raise RuntimeError("remember_preference is run by preferences.propose().")


def tool_definition() -> StructuredTool:
    """Return remember_preference for binding: its name, description and schema only."""
    return StructuredTool.from_function(
        func=_not_run,
        name=PREFERENCE_TOOL,
        description=PREFERENCE_DESCRIPTION,
        args_schema=PreferenceArgs,
    )


def _name_pattern(name: str) -> re.Pattern[str] | None:
    """Return the pattern of a name as whole words in a row, without case, or None if empty."""
    words = name.casefold().split()
    if not words:
        return None
    # \w on both sides, so "max" is not found in "maximum" and "o'neil" not in "o'neill".
    return re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, words)) + r"(?!\w)")


def names_in(text: str, names: Iterable[str]) -> bool:
    """Return True if the text holds any of the names as whole words, without case."""
    folded = text.casefold()
    return any(
        pattern.search(folded) for name in names if (pattern := _name_pattern(name)) is not None
    )


def check_preference(text: object, client_names: Sequence[str]) -> PreferenceCheck:
    """Check a proposed or edited preference: guard, guardrails, then the clients' names."""
    if not isinstance(text, str):
        return PreferenceCheck(False, code="invalid")
    decision = guard.check_text(text, config.PREFERENCE_MAX_CHARS)
    if not decision.allowed:
        return PreferenceCheck(False, code=_REFUSALS.get(decision.reason, "invalid"))
    # The cleaned text, and the guard's detection views of the raw one, so a name split by an
    # invisible character or written in full-width letters is found too.
    views = {decision.text, *guard.detection_views(text)}
    if any(names_in(view, client_names) for view in views):
        return PreferenceCheck(False, code="client_name")
    return PreferenceCheck(True, text=decision.text)


def propose(
    memory: CoachMemory, proposals: Proposals, call: ToolCall, turn_id: str = ""
) -> ToolMessage:
    """Check one remember_preference call; keep a passing text for the coach's card."""
    # Nothing is written here: the conversation graph pauses for the coach's answer once the turn
    # is over (src/agent/memory.py). The model gets a fixed message that never repeats the text.
    try:
        args = PreferenceArgs.model_validate(call["args"])
    except ValidationError:
        code: str | None = "invalid"
    else:
        if len(proposals.texts) >= config.MAX_PREFERENCE_PROPOSALS_PER_TURN:
            code = "one_per_turn"
        else:
            checked = check_preference(args.text, memory.client_names)
            code = checked.code
            if checked.allowed:
                proposals.texts.append(checked.text)
    if code is None:
        logger.info("preference_proposed", extra={"turn_id": turn_id})
        content, status = config.PREFERENCE_PROPOSED_MESSAGE, "success"
    else:
        proposals.refused.append(code)
        logger.warning("preference_refused", extra={"turn_id": turn_id, "reason": code})
        content, status = config.PREFERENCE_REFUSED_MESSAGES[code], "error"
    return ToolMessage(content, tool_call_id=call["id"] or "", name=PREFERENCE_TOOL, status=status)


def client_names(conn: sqlite3.Connection, coach_id: str) -> tuple[str, ...]:
    """Return the display names of every client the coach has had, active or ended."""
    return tuple(
        dict.fromkeys(row["other_name"] for row in users.list_relationships(conn, coach_id))
    )


def load(conn: sqlite3.Connection, coach_id: str) -> CoachMemory:
    """Read a coach's client names and newest preferences for one chat turn."""
    saved = records.list_preferences(conn, coach_id, coach_id)
    newest = saved[-config.MEMORY_PREFERENCES_IN_PROMPT :] if saved else []
    return CoachMemory(
        coach_id=coach_id,
        client_names=client_names(conn, coach_id),
        preferences=tuple(row["text"] for row in newest),
    )


def save(conn: sqlite3.Connection, coach_id: str, text: object) -> PreferenceCheck:
    """Check the text again against the coach's clients now, and save it if it passes."""
    checked = check_preference(text, client_names(conn, coach_id))
    if checked.allowed:
        records.add_preference(conn, coach_id, checked.text)
    return checked


def memories_block(preferences: Sequence[str]) -> str:
    """Return the preferences inside the delimited <memories> block, escaped like the others."""
    # One line each: a line break in a saved text cannot make it look like two preferences.
    lines = "\n".join(f"- {escape_prompt_data(' '.join(text.split()))}" for text in preferences)
    return f"<memories>\n{lines}\n</memories>"
