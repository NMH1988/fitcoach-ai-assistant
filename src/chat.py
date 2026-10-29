"""One chat turn: guard -> the agent and its tools (a knowledge base search among them) -> answer.

`run_turn()` runs the turn as the LangGraph graph in `src/agent/graph.py` (T9.2), whose nodes use
this module's helpers, and turns its errors into fixed messages. The user's question goes only
inside <user_input> in the user message; the chunks a search finds come back only inside <sources>
in that search's tool message (T9.3, `src/agent/search.py`); neither is ever put into the system
prompt (.claude/rules/security-privacy.md). Both are escaped first (`src/prompt_data.py`), so no
text can close or open a block (T3.4). The profile is never in the messages: the tools read it from
the app (owner's choice in T9.3, 2026-10-29). The rewrites from query translation are used only for
the search and shown in the app. Tool results reach the model only as tool messages (T4.4). Every
error a user can cause or meet ends as a TurnResult with a fixed message, so the app shows it in
the answer and keeps the chat history (AC-13). The answer's
language is the app's EN | DE choice, passed in as a fixed value: the code joins that language's
part of the owner's prompt to the end of the system prompt, and nothing the user types picks it
(T7.2).
"""

import logging
import os
import re
import time
import urllib.parse
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from functools import cache, partial
from pathlib import Path
from typing import Any, Literal

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool

from src import config, guard, i18n, llm, profile, usage
from src.prompt_data import escape_prompt_data
from src.rag import hybrid, query_translation
from src.rag.hybrid import KeywordIndex
from src.rag.query_translation import QueryPlan
from src.rag.retriever import RetrievedChunk, embed_queries
from src.rag.sources import ManifestError, Source, license_url_for, load_manifest
from src.rag.store import IndexNotReadyError
from src.tools import registry
from src.tools.registry import ToolRun
from src.usage import CallUsage, ModelPrice, UsageRecorder

logger = logging.getLogger(__name__)


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
# model, key or index problem.
TurnKind = Literal["answer", "no_sources", "rejected", "guardrail", "error"]


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
    # True when nothing passed the filters, so the search ran again without them.
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
    # A fixed message's key in src/i18n.py and its numbers, so the UI shows it in the language
    # chosen now (T7.1); set for every kind but "answer" (tests/conftest.py checks it), None for
    # the model's answer. `text` stays English, for the summary PDF.
    code: str | None = None
    params: Mapping[str, int] = field(default_factory=dict)
    # The turn's ID (a UUID4), set by run_turn() and written on every log line of the turn, so the
    # lines can be matched (T8.2; T9.8 puts it on the trace too). Empty for a hand-made result.
    turn_id: str = ""


# A citation is one bracket holding labels or ranges: [S1], [S1, S3], [S2; S4], [S1 and S2],
# [S1, S2, and S3], [S1 & S2], [S1-S3], [S1–S3], and in a German answer [S1 und S2] (T7.2).
_BRACKET = re.compile(r"\[([^\[\]]{1,80})\]")
_CITED_ITEM = r"S\d+(?:\s*[-–]\s*S?\d+)?"
_CITATION_SEPARATOR = r"\s*(?:[,;]\s*(?:(?:and|und)\s+|&\s*)?|(?:and|und)\s+|&\s*)"
_CITATION_BODY = re.compile(rf"\s*{_CITED_ITEM}(?:{_CITATION_SEPARATOR}{_CITED_ITEM})*\s*")
_LABEL_OR_RANGE = re.compile(r"S(\d+)(?:\s*[-–]\s*S?(\d+))?")
# A Markdown image, inline (![alt](url)) or by reference (![alt][ref]): the browser would load
# its URL with no click, so an injected one could send text to another server. A bare ![alt]
# is left to the escape in remove_images(), so "protein![S1]" keeps its citation.
_MARKDOWN_IMAGE = re.compile(r"!\[([^\[\]]*)\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\])")
# One word of a paced answer with the spaces before it (or the rest of a word already begun).
_PACED_WORD = re.compile(r"\s*\S+")
# Characters Streamlit's Markdown would read as formatting, HTML, LaTeX, strikethrough (~) or an
# emoji or icon shortcode (:) in a title.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>$~:])")


class PromptMissingError(RuntimeError):
    """A prompt file is missing, unreadable or empty; `str()` is the fixed message to show."""

    def __init__(self, message: str, code: str) -> None:
        """Keep the fixed message and its key in src/i18n.py."""
        super().__init__(message)
        self.code = code


class ToolLoopError(llm.LLMError):
    """The model still called tools in the last call, where it was told not to."""

    code = "llm.tool_loop"
    user_message = "The answer could not be finished. Please try again."


@dataclass(frozen=True)
class KnowledgeBaseSummary:
    """What the knowledge base holds, for the app's note on what answers are based on."""

    articles: int
    position_stands: int
    reviews: int
    licenses: tuple[str, ...]


def knowledge_base_summary(manifest: Mapping[str, Source]) -> KnowledgeBaseSummary:
    """Count the approved articles (correction notices left out) by evidence tier and licence."""
    articles = [source for source in manifest.values() if source.corrects is None]
    return KnowledgeBaseSummary(
        articles=len(articles),
        position_stands=sum(source.evidence_tier == 1 for source in articles),
        reviews=sum(source.evidence_tier == 2 for source in articles),
        licenses=tuple(sorted({source.license for source in articles})),
    )


def load_system_prompt(path: Path | None = None) -> str:
    """Return the owner's answer system prompt from its file."""
    text = (path or config.ANSWER_PROMPT_PATH).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("The answer system prompt is empty.")
    return text


def answer_system_prompt(prompt: str, language_part: str) -> str:
    """Return the owner's answer prompt with the chosen language's part as its last section."""
    # Both are the owner's fixed text (O1); the app's language control picks the part (T7.2).
    return f"{prompt}\n\n{language_part}"


def search_queries(query: str, plan: QueryPlan | None) -> tuple[str, ...]:
    """Return the plan's rewrites that differ from the query and from each other."""
    seen = {query.casefold()}
    rewrites = []
    for rewrite in plan.queries if plan is not None else ():
        if rewrite.casefold() not in seen:
            seen.add(rewrite.casefold())
            rewrites.append(rewrite)
    return tuple(rewrites)


# The retry filter of a plan whose topics are all nutrition: any topic but training (T9.20).
_NUTRITION_ONLY = {
    "$or": [{"topics": {"$contains": t}} for t in config.TOPICS if t != config.TRAINING_TOPIC]
}


def find_chunks(
    query: str,
    plan: QueryPlan | None,
    index: Chroma,
    *,
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index,
    recorder: UsageRecorder | None = None,
) -> tuple[list[RetrievedChunk], SearchDetails]:
    """Search the query and its rewrites by meaning and by keyword, merged with RRF (T3.3)."""
    rewrites = search_queries(query, plan)
    queries = (query, *rewrites)
    where = query_translation.build_filter(plan)
    # One embedding call for all the queries; the vectors serve the retry too.
    vectors = embed_queries(index, queries, recorder=recorder)
    chunks = hybrid.hybrid_search(index, queries, vectors, where, keyword_index)
    # Empty only when the query itself has no chunk within the distance limit (T3.8), even if a
    # rewrite has one; a filter that keeps fewer but relevant chunks stays.
    filter_dropped = not chunks and where is not None
    if filter_dropped:
        if plan is not None and plan.topics == (config.TRAINING_TOPIC,):
            # A training-only plan keeps its topic and drops only its year and tier, so the retry
            # passes the same distance gate on training chunks alone: neither a nutrition chunk nor
            # a training chunk that only shares a word stands in for a missing training source
            # (PRD feature 26; T9.20, security review finding 3 and, on the PR, finding 1).
            topic_only = {"topics": {"$contains": config.TRAINING_TOPIC}}
            chunks = (
                []
                if where == topic_only
                else hybrid.hybrid_search(index, queries, vectors, topic_only, keyword_index)
            )
        elif plan is not None and plan.topics:
            # Mirrored: a plan whose topics are all nutrition runs again over the nutrition topics,
            # so a training chunk never joins a nutrition answer (T9.20, T9.19's code review).
            chunks = hybrid.hybrid_search(index, queries, vectors, _NUTRITION_ONLY, keyword_index)
        else:
            # No topic (or no usable plan): the question's domain is unknown, so search everything.
            chunks = hybrid.hybrid_search(index, queries, vectors, None, keyword_index)
    details = SearchDetails(
        query=query,
        rewrites=rewrites,
        topics=plan.topics if plan is not None else (),
        min_year=plan.min_year if plan is not None else None,
        evidence_tier=plan.evidence_tier if plan is not None else None,
        fell_back=plan is None,
        filter_dropped=filter_dropped,
        labels=tuple(range(1, len(chunks) + 1)),
    )
    return chunks, details


def manifest_by_id() -> dict[str, Source]:
    """Return the approved sources by ID, or an empty dict if the manifest cannot be read."""
    try:
        return {source.id: source for source in load_manifest()}
    except ManifestError:
        # The cards then show what the chunks carry, without the journal and corrections.
        return {}


def escape_markdown(text: str) -> str:
    """Escape the characters Markdown would read as formatting, so the text shows as written."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def format_authors(authors: Sequence[str]) -> str:
    """Return the first CARD_AUTHORS_SHOWN authors, then "et al." if there are more."""
    shown = ", ".join(authors[: config.CARD_AUTHORS_SHOWN])
    return f"{shown} et al." if len(authors) > config.CARD_AUTHORS_SHOWN else shown


def markdown_url(url: str) -> str:
    """Percent-encode a URL so none of its characters can end a Markdown link early."""
    return urllib.parse.quote(url, safe=":/%#?=&")


def format_sources(chunks: Sequence[RetrievedChunk], labels: Sequence[int] | None = None) -> str:
    """Return the chunks as labelled blocks: [S#], title, year and tier, then the text, escaped."""
    # labels: each chunk's [S#] number (unique across a turn's searches, T9.3); 1, 2, ... if None.
    if not chunks:
        return config.NO_SOURCES_BLOCK
    numbers = range(1, len(chunks) + 1) if labels is None else labels
    blocks = []
    for number, chunk in zip(numbers, chunks, strict=True):
        meta = chunk.metadata
        tier = config.EVIDENCE_TIER_LABELS.get(meta["evidence_tier"], config.UNKNOWN_TIER_LABEL)
        title, year, tier, text = (
            escape_prompt_data(part) for part in (meta["title"], meta["year"], tier, chunk.text)
        )
        blocks.append(f"[S{number}] {title} ({year}; {tier})\n{text}")
    return "\n\n".join(blocks)


def sources_block(chunks: Sequence[RetrievedChunk], labels: Sequence[int] | None = None) -> str:
    """Return the chunks inside the delimited <sources> block a search's tool message holds."""
    return f"<sources>\n{format_sources(chunks, labels)}\n</sources>"


def build_messages(question: str, system_prompt: str) -> list[BaseMessage]:
    """Return the system prompt and a user message holding only <user_input>."""
    # Plain string content, never a prompt template: braces in the question stay as typed. The
    # chunks come only in a search's tool message (T9.3); the profile is never sent: the tools
    # read it from the app (owner's choice in T9.3, 2026-10-29).
    user = f"<user_input>\n{escape_prompt_data(question)}\n</user_input>"
    return [SystemMessage(system_prompt), HumanMessage(user)]


def cited_labels(answer: str, count: int) -> list[int]:
    """Return the numbers of the [S#] labels cited, in order, only those from 1 to count."""
    numbers: list[int] = []
    for bracket in _BRACKET.finditer(answer):
        if not _CITATION_BODY.fullmatch(bracket.group(1)):
            continue
        for item in _LABEL_OR_RANGE.finditer(bracket.group(1)):
            first = int(item.group(1))
            last = int(item.group(2)) if item.group(2) else first
            # A range is capped at the chunk count, so [S1-S999] cannot run long.
            for number in range(max(first, 1), min(last, count) + 1):
                if number not in numbers:
                    numbers.append(number)
    return numbers


class PacedWriter:
    """Show a growing answer word by word, at most words_per_second, through show(text)."""

    def __init__(
        self,
        show: Callable[[str], None],
        words_per_second: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the display function, the pause between words (0 = none) and the clock."""
        self._show = show
        self._pause = 1 / words_per_second if words_per_second > 0 else 0.0
        self._sleep = sleep
        self._shown = ""

    def __call__(self, text: str) -> None:
        """Reveal the words of text not shown yet, one at a time, pausing after each."""
        # Empty text clears what was shown (the text of a reply that called tools).
        if self._pause == 0 or not text:
            self._shown = text
            self._show(text)
            return
        # Usually the text only grows; if an earlier part changed (an image removed once its
        # syntax was complete), the reveal starts where the shown text and the new text differ.
        start = len(os.path.commonprefix([self._shown, text]))
        for word in _PACED_WORD.finditer(text, start):
            self._shown = text[: word.end()]
            self._show(self._shown)
            self._sleep(self._pause)


def remove_images(answer: str) -> str:
    """Replace each Markdown image with its alt text, then escape any "![" left, so none loads."""
    without_images = _MARKDOWN_IMAGE.sub(lambda image: image.group(1), answer)
    # The pattern misses alt text with nested brackets (![a[b]c](url)), which CommonMark still
    # reads as an image; with its bracket escaped, any "![" left is plain text.
    return without_images.replace("![", "!\\[")


def _corrections(meta: Mapping[str, Any], manifest: Mapping[str, Source]) -> tuple[Correction, ...]:
    """Return the correction notices of a cited article, or the article a cited notice corrects."""
    found = []
    for other_id in meta.get("corrected_by") or []:
        other = manifest.get(other_id)
        if other is not None:
            found.append(Correction("corrected_by", other.title, other.url))
    corrected = manifest.get(meta.get("corrects") or "")
    if corrected is not None:
        found.append(Correction("corrects", corrected.title, corrected.url))
    return tuple(found)


def source_cards(
    chunks: Sequence[RetrievedChunk], numbers: Sequence[int], manifest: Mapping[str, Source]
) -> tuple[SourceCard, ...]:
    """Return one card per cited article, in the order first cited, with all its labels."""
    cited: dict[str, tuple[Mapping[str, Any], list[str]]] = {}
    for number in numbers:
        meta = chunks[number - 1].metadata
        _, labels = cited.setdefault(str(meta["source_id"]), (meta, []))
        labels.append(f"S{number}")
    cards = []
    for source_id, (meta, labels) in cited.items():
        source = manifest.get(source_id)
        cards.append(
            SourceCard(
                source_id=source_id,
                title=meta["title"],
                authors=tuple(meta.get("authors") or ()),
                year=int(meta["year"]),
                evidence_tier=int(meta["evidence_tier"]),
                license=meta["license"],
                license_url=license_url_for(meta["license"]),
                url=meta["source_url"],
                journal=source.journal if source is not None else None,
                labels=tuple(labels),
                corrections=_corrections(meta, manifest),
            )
        )
    return tuple(cards)


def stream_reply(
    chat_model: Runnable[Any, BaseMessage],
    messages: Sequence[BaseMessage],
    on_text: Callable[[str], None] | None = None,
    record: Callable[[UsageMetadata | None], None] | None = None,
) -> AIMessageChunk:
    """Stream one model reply, reporting its text so far as it grows; return the whole reply."""
    # record(usage) gets the reply's token use, which comes with the last chunk (T5.1).
    reply: AIMessageChunk | None = None
    with llm.mapped_errors():
        for chunk in chat_model.stream(messages):
            reply = chunk if reply is None else reply + chunk
            if on_text is not None and chunk.text:
                # Images are removed on every update: one completed mid-stream would load at once.
                on_text(remove_images(reply.text))
    if reply is None:
        raise llm.LLMError(diagnostic="no answer chunks")
    if record is not None:
        # Before the check below: a cut-off reply was paid for too.
        record(reply.usage_metadata)
    if reply.response_metadata.get("finish_reason") == "length":
        # A cut-off answer is not shown half-written, and cut-off tool arguments are not run.
        raise llm.ReplyCutOffError(diagnostic="finish_reason length in the answer step")
    return reply


def answer_with_tools(
    chat_model: BaseChatModel,
    messages: Sequence[BaseMessage],
    tools: Mapping[str, StructuredTool],
    on_step: Callable[[Step], None],
    on_text: Callable[[str], None] | None = None,
    *,
    tools_only: bool = False,
    recorder: UsageRecorder | None = None,
    on_tool_run: Callable[[ToolRun], None] | None = None,
) -> tuple[str | None, tuple[ToolRun, ...]]:
    """Let the model call tools for at most MAX_TOOL_ROUNDS rounds; return its answer and runs."""
    # The chat graph's own answer loop (its agent and ToolNode), run on the given messages; a
    # turn runs it inside the whole graph (src/agent/graph.py). tools_only: replies stay hidden
    # until a tool gives a result (config.BASIS_TOOL_STATUSES), and an answer of None means "not
    # covered", returned with no runs (a whole turn keeps them with "not covered"). The messages
    # must come from a guarded turn: this loop has no guard of its own. on_tool_run gets a valid
    # call's run from the ToolNode's worker thread and a refused bad-JSON call's from the caller's.
    from src.agent import graph  # The graph builds its nodes from this module's helpers.

    context = graph.TurnContext(
        chat_model=lambda: chat_model,
        tools=lambda: tools,
        on_step=on_step,
        on_text=on_text,
        recorder=recorder,
        on_tool_run=on_tool_run,
    )
    state = graph.answer_loop_graph().invoke(
        {"messages": list(messages), "tools_only": tools_only},
        context=context,
        config=graph.run_config(),
    )
    if state["answer"] is None:
        return None, ()
    return state["answer"], tuple(state.get("runs", ()))


def fixed_text(result: TurnResult, lang: i18n.Language) -> str:
    """Return a turn's fixed message in the language, or the model's own answer as written."""
    # Shared by the chat and the summary PDF (T7.2), so the two cannot word a message differently.
    # An unknown key falls back to the English text rather than breaking every later run.
    if result.code is not None and result.code in i18n.TEXT[lang]:
        return i18n.t(result.code, lang, **result.params)
    return result.text


def _cost_text(
    result: TurnResult, prices: Callable[[], Mapping[str, ModelPrice] | None] | None
) -> str | None:
    """Return the turn's cost in dollars as text, or None when a price is unknown."""
    known = prices() if prices is not None and result.usage else None
    cost = usage.price_turn(result.usage, known).cost
    return None if cost is None else format(cost, "f")


@dataclass
class _TurnTrace:
    """What a turn did, collected as it happens, for its log lines (T8.2)."""

    # The chunks the searches gave the model, in [S#] order, the tool runs and the searches run. An
    # error result has no tool runs or searches, so the log cannot read them there.
    chunks: list[RetrievedChunk] = field(default_factory=list)
    tool_runs: list[ToolRun] = field(default_factory=list)
    searches: int = 0


def _log_turn(
    result: TurnResult,
    language: i18n.Language,
    trace: _TurnTrace,
    seconds: float,
    prices: Callable[[], Mapping[str, ModelPrice] | None] | None,
) -> None:
    """Write the turn's one INFO record, and a warning for each tool call that failed (T8.2)."""
    # Only ids, counts, codes and statuses: no question, rewrite, answer, chunk text, profile value
    # or tool argument, and no tool name the model made up (a run's name is None then).
    for run in trace.tool_runs:
        if run.status in ("error", "invalid"):
            logger.warning(
                "tool_failed",
                extra={"turn_id": result.turn_id, "tool": run.name, "status": run.status},
            )
    source_ids = dict.fromkeys(
        str(chunk.metadata["source_id"])
        for chunk in trace.chunks
        if chunk.metadata.get("source_id")
    )
    logger.info(
        "turn",
        extra={
            "turn_id": result.turn_id,
            "kind": result.kind,
            "code": result.code,
            "language": language,
            "chunks": len(trace.chunks),
            "source_ids": list(source_ids),
            "tools": [run.name for run in trace.tool_runs],
            "tool_statuses": [run.status for run in trace.tool_runs],
            "tokens": sum(call.tokens for call in result.usage),
            "cost_usd": _cost_text(result, prices),
            "duration_ms": round(seconds * 1000),
            "searches": trace.searches,
        },
    )


def run_turn(
    text: str,
    limiter: guard.RateLimiter,
    *,
    open_index: Callable[[], Chroma],
    chat_model: Callable[[], BaseChatModel],
    translation_model: Callable[[], BaseChatModel],
    manifest: Mapping[str, Source] | None = None,
    on_step: Callable[[Step], None] | None = None,
    on_text: Callable[[str], None] | None = None,
    user: profile.UserProfile | None = None,
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index,
    on_chunks: Callable[[Sequence[RetrievedChunk]], None] | None = None,
    language: i18n.Language = "en",
    prices: Callable[[], Mapping[str, ModelPrice] | None] | None = None,
) -> TurnResult:
    """Run one chat turn: guard, agent, tools; never raise for an error a user can cause."""
    # on_step(step) is called as each step starts; on_text(text) as the answer streams in. `user`
    # is the session's profile, for the energy and meal plan tools only: it never goes into the
    # model's messages (T9.3).
    # keyword_index(index) gives the BM25 index of the opened index; the app passes a cached one.
    # on_chunks(chunks) gets each search's newly labelled chunks, in [S#] order, so all its calls
    # together give the turn's chunks in label order; only the evaluation run uses it (T6.1, T9.3).
    # language is the app's EN | DE choice (T7.2), never taken from the text; an unknown one is a
    # bug in the caller, refused before any call.
    # prices() gives the model prices already known, never reading them (T8.2): only the turn's log
    # line uses them, and the cost is null when there are none.
    if language not in config.ANSWER_LANGUAGE_PROMPT_PATHS:
        raise ValueError(f"Unknown answer language: {language!r}")
    turn_id = str(uuid.uuid4())
    started = time.monotonic()
    steps: list[Step] = []
    recorder = UsageRecorder()
    trace = _TurnTrace()
    from src.agent import search  # The search tool builds on this module's helpers.

    search_log = search.SearchLog()

    def keep_chunks(chunks: Sequence[RetrievedChunk]) -> None:
        """Keep a search's new chunks for the log line, then pass them to the caller's callback."""
        trace.chunks.extend(chunks)
        if on_chunks is not None:
            on_chunks(chunks)

    def step(name: Step) -> None:
        """Record a step and report it to the caller's progress indicator."""
        steps.append(name)
        if on_step is not None:
            on_step(name)

    def graph_turn() -> TurnResult:
        """Run the turn's graph: the guard first, the index and the models only if it passes."""
        from src.agent import graph  # The graph builds its nodes from this module's helpers.

        # Each factory runs at most once a turn; the prepare node calls them in order (T9.2).
        context = graph.TurnContext(
            chat_model=cache(chat_model),
            tools=cache(partial(registry.build_tools, user)),
            on_step=step,
            on_text=on_text,
            recorder=recorder,
            on_tool_run=trace.tool_runs.append,
            limiter=limiter,
            open_index=cache(open_index),
            translation_model=cache(translation_model),
            manifest=manifest or {},
            keyword_index=keyword_index,
            language=language,
            on_chunks=keep_chunks,
            search_log=search_log,
            turn_id=turn_id,
        )
        state = graph.chat_graph().invoke(
            {"text": text}, context=context, config=graph.run_config()
        )
        return state["result"]

    def failed(message: str, code: str, *, index_not_ready: bool = False) -> TurnResult:
        """Return an error result with the steps run and the tokens spent before the error."""
        return TurnResult(
            "error",
            message,
            steps=tuple(steps),
            index_not_ready=index_not_ready,
            usage=tuple(recorder.calls),
            code=code,
        )

    def outcome() -> TurnResult:
        """Run the turn's graph and return how it ended, writing a warning for a failure."""
        try:
            result = graph_turn()
        except llm.LLMError as exc:
            # A fixed text, safe to show (never the server's reply or the key).
            logger.warning(
                "llm_error",
                extra={
                    "turn_id": turn_id,
                    "code": exc.code,
                    "status_code": exc.status_code,
                    "diagnostic": exc.diagnostic,
                },
            )
            return failed(str(exc), exc.code)
        except IndexNotReadyError as exc:
            return failed(str(exc), exc.code, index_not_ready=True)
        except PromptMissingError as exc:
            return failed(str(exc), exc.code)
        except config.SecretsFileError:
            return failed(config.SECRETS_FILE_MESSAGE, "key.secrets_file")
        except config.MissingAPIKeyError:
            return failed(config.MISSING_KEY_MESSAGE, "key.missing")
        except Exception as exc:
            # Any other error (a bug, an unexpected library error) gets a fixed message too (T1.8).
            # Only its type and place are logged: its message or arguments may hold the question,
            # a chunk or a server's reply. BaseException (Streamlit's rerun and stop) is not
            # caught.
            logger.error(
                "turn_error", extra={"turn_id": turn_id, "diagnostic": llm.error_diagnostic(exc)}
            )
            return failed(config.TURN_ERROR_MESSAGE, "turn.error")
        return replace(result, steps=tuple(steps), usage=tuple(recorder.calls))

    result = replace(outcome(), turn_id=turn_id)
    trace.searches = len(search_log.searches)
    try:
        _log_turn(result, language, trace, time.monotonic() - started, prices)
    except Exception:
        # A turn is not lost because its log line could not be built (e.g. the prices callable
        # raised); only the fixed event is written, never the error's message.
        logger.error("log_failed", extra={"turn_id": turn_id})
    return result
