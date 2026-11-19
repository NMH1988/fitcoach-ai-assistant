"""What a chat turn gives back: its steps, results, source cards and errors."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from src import llm
from src.tools.registry import ToolRun
from src.usage import CallUsage


class Step(StrEnum):
    """The steps of a turn, as the progress indicator names them."""

    CHECK = "Checking your question"
    PLAN = "Planning the answer"
    SEARCH = "Searching the research"
    ANSWER = "Writing the answer"
    TOOLS = "Using the tools"


# answer: the model's answer; no_sources: no search found a relevant chunk and no tool gave a
# result (BASIS_TOOL_STATUSES), so an answer would rest on nothing (AC-2); rejected: the guard
# refused the input; guardrail: a domain guardrail refused or redirected it (AC-12); error: a
# model, key or index problem; memory: a coach's turn that proposed a preference (or had one
# refused) and gave no answer with a basis, so a fixed line stands in for no_sources (T9.7).
TurnKind = Literal["answer", "no_sources", "rejected", "guardrail", "error", "memory"]


@dataclass(frozen=True)
class Correction:
    """A correction notice linked to a cited article, or the article a cited notice corrects."""

    relation: Literal["corrected_by", "corrects"]
    title: str
    url: str


@dataclass(frozen=True)
class SourceCard:
    """One cited article, with the labels that cite it and what the Sources list shows."""

    source_id: str
    title: str
    authors: tuple[str, ...]
    year: int
    evidence_tier: int
    license: str
    license_url: str
    url: str
    journal: str | None
    labels: tuple[str, ...]
    corrections: tuple[Correction, ...] = ()


@dataclass(frozen=True)
class SearchDetails:
    """How one search ran: its query, the rewrites, the filters and what it found (AC-3)."""

    # The query the model wrote for the search tool (T9.3).
    query: str
    rewrites: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    min_year: int | None = None
    evidence_tier: int | None = None
    # True when the rewrite step gave no usable plan, so only the query was searched.
    fell_back: bool = False
    # True when nothing passed the filters, so they were relaxed (T9.20: a training-only plan
    # keeps its topic, a nutrition-only plan the nutrition topics, any other none).
    filter_dropped: bool = False
    # The [S#] number of each relevant chunk found, in rank order (a chunk an earlier search of the
    # turn found keeps its label, T9.3); empty when the sources do not cover the query.
    labels: tuple[int, ...] = ()

    @property
    def queries(self) -> tuple[str, ...]:
        """Return what was searched: the query, then its rewrites."""
        return (self.query, *self.rewrites)


@dataclass(frozen=True)
class TurnResult:
    """What one chat turn gives the UI: the text to show, its sources and the steps it ran."""

    kind: TurnKind
    text: str
    sources: tuple[SourceCard, ...] = ()
    steps: tuple[Step, ...] = ()
    # Each search the agent ran, in order (T9.3); () when it ran none, None when the turn was
    # rejected or ended in an error (an error result keeps no searches, as it keeps no tool runs).
    searches: tuple[SearchDetails, ...] | None = None
    # True when the index could not be used, so the app opens it again on the next turn.
    index_not_ready: bool = False
    # The tool calls the model made, in order, with their results (T4.4).
    tool_runs: tuple[ToolRun, ...] = ()
    # The tokens of each model and embedding call the turn made, in order, including the calls
    # made before an error (T5.1); empty when the guard stopped the question.
    usage: tuple[CallUsage, ...] = ()
    # A fixed message's key in src/i18n/ and its numbers, so the UI shows it in the language
    # chosen now (T7.1); set for every kind but "answer" (tests/conftest.py checks it), None for
    # the model's answer. `text` stays English, for the summary PDF.
    code: str | None = None
    params: Mapping[str, int] = field(default_factory=dict)
    # The turn's ID (a UUID4), set by run_turn() and written on every log line of the turn, so the
    # lines can be matched (T8.2; T9.8 puts it on the trace too). Empty for a hand-made result.
    turn_id: str = ""
    # True when the chat's memory did not keep this answer because it reads like an instruction to
    # the assistant (T10.1): the answer is still shown, with a line saying the question and answer
    # are not remembered.
    not_remembered: bool = False
    # The versions of the prompts the turn was set up with, by their trace and log keys
    # (tracing.PROMPT_ANSWER_KEY, PROMPT_QUERY_KEY), set by run_turn() (T10.4); empty when the
    # prompts could not be read (a missing file, or a bug), and for a hand-made result.
    prompts: Mapping[str, str] = field(default_factory=dict)


class PromptMissingError(RuntimeError):
    """A prompt file is missing, unreadable or empty; `str()` is the fixed message to show."""

    def __init__(self, message: str, code: str) -> None:
        """Keep the fixed message and its key in src/i18n/."""
        super().__init__(message)
        self.code = code


class ToolLoopError(llm.LLMError):
    """The model still called tools in the last call, where it was told not to."""

    code = "llm.tool_loop"
    user_message = "The answer could not be finished. Please try again."
