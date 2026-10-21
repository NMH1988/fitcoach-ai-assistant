"""One chat turn: guard -> query translation -> retrieval -> answer with tools and [S#] citations.

The user's question goes only inside <user_input>, the retrieved chunks only inside <sources> and
the profile only inside <profile>, all in the user message; none is ever put into the system prompt
(.claude/rules/security-privacy.md). All three are escaped first (`src/prompt_data.py`), so no text
can close or open a block (T3.4). The rewrites from query translation are used only for the search
and shown in the app; the answer model gets the user's own question. Tool results reach the model
only as tool messages (T4.4). Every error a user can cause or meet ends as a TurnResult with a fixed
message, so the app shows it in the answer and keeps the chat history (AC-13).
"""

import os
import re
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Any, Literal

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool

from src import config, guard, llm, profile, units, usage
from src.prompt_data import escape_prompt_data
from src.rag import hybrid, query_translation
from src.rag.hybrid import KeywordIndex
from src.rag.query_translation import QueryPlan
from src.rag.retriever import RetrievedChunk, embed_queries
from src.rag.sources import ManifestError, Source, license_url_for, load_manifest
from src.rag.store import IndexNotReadyError
from src.tools import registry
from src.tools.registry import ToolRun
from src.usage import CallUsage, UsageRecorder


class Step(StrEnum):
    """The steps of a turn, as the progress indicator names them."""

    CHECK = "Checking your question"
    REWRITE = "Rewriting the question"
    SEARCH = "Searching the research"
    ANSWER = "Writing the answer"
    TOOLS = "Using the tools"


# answer: the model's answer; no_sources: nothing relevant was found (AC-2); rejected: the guard
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
    """How a turn searched: the question, its rewrites and the filters (AC-3)."""

    question: str
    rewrites: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    min_year: int | None = None
    evidence_tier: int | None = None
    # True when the rewrite step gave no usable plan, so only the question was searched.
    fell_back: bool = False
    # True when nothing passed the filters, so the search ran again without them.
    filter_dropped: bool = False

    @property
    def queries(self) -> tuple[str, ...]:
        """Return what was searched: the question, then its rewrites."""
        return (self.question, *self.rewrites)

    @property
    def has_filters(self) -> bool:
        """Return True when the plan set any filter (used or dropped)."""
        return bool(self.topics) or self.min_year is not None or self.evidence_tier is not None


@dataclass(frozen=True)
class TurnResult:
    """What one chat turn gives the UI: the text to show, its sources and the steps it ran."""

    kind: TurnKind
    text: str
    sources: tuple[SourceCard, ...] = ()
    steps: tuple[Step, ...] = ()
    # How the search ran; None when the turn ended before it (rejected, or an error before it).
    search: SearchDetails | None = None
    # True when the index could not be used, so the app opens it again on the next turn.
    index_not_ready: bool = False
    # The tool calls the model made, in order, with their results (T4.4).
    tool_runs: tuple[ToolRun, ...] = ()
    # The tokens of each model and embedding call the turn made, in order, including the calls
    # made before an error (T5.1); empty when the guard stopped the question.
    usage: tuple[CallUsage, ...] = ()


# A citation is one bracket holding labels or ranges: [S1], [S1, S3], [S2; S4], [S1 and S2],
# [S1, S2, and S3], [S1 & S2], [S1-S3], [S1–S3].
_BRACKET = re.compile(r"\[([^\[\]]{1,80})\]")
_CITED_ITEM = r"S\d+(?:\s*[-–]\s*S?\d+)?"
_CITATION_SEPARATOR = r"\s*(?:[,;]\s*(?:and\s+|&\s*)?|and\s+|&\s*)"
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


class ToolLoopError(llm.LLMError):
    """The model still called tools in the last call, where it was told not to."""

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


def _load_prompt(path: Path, message: str) -> str:
    """Return a prompt file's text; raise PromptMissingError with message if it is unusable."""
    try:
        return load_system_prompt(path)
    except OSError, ValueError:
        raise PromptMissingError(message) from None


def search_queries(question: str, plan: QueryPlan | None) -> tuple[str, ...]:
    """Return the plan's rewrites that differ from the question and from each other."""
    seen = {question.casefold()}
    rewrites = []
    for rewrite in plan.queries if plan is not None else ():
        if rewrite.casefold() not in seen:
            seen.add(rewrite.casefold())
            rewrites.append(rewrite)
    return tuple(rewrites)


def find_chunks(
    question: str,
    plan: QueryPlan | None,
    index: Chroma,
    *,
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index,
    recorder: UsageRecorder | None = None,
) -> tuple[list[RetrievedChunk], SearchDetails]:
    """Search the question and its rewrites by meaning and by keyword, merged with RRF (T3.3)."""
    rewrites = search_queries(question, plan)
    queries = (question, *rewrites)
    where = query_translation.build_filter(plan)
    # One embedding call for all the queries; the vectors serve the retry too.
    vectors = embed_queries(index, queries, recorder=recorder)
    chunks = hybrid.hybrid_search(index, queries, vectors, where, keyword_index)
    # Empty only when no chunk is within the distance limit; a filter that keeps fewer but
    # relevant chunks stays.
    filter_dropped = not chunks and where is not None
    if filter_dropped:
        chunks = hybrid.hybrid_search(index, queries, vectors, None, keyword_index)
    details = SearchDetails(
        question=question,
        rewrites=rewrites,
        topics=plan.topics if plan is not None else (),
        min_year=plan.min_year if plan is not None else None,
        evidence_tier=plan.evidence_tier if plan is not None else None,
        fell_back=plan is None,
        filter_dropped=filter_dropped,
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


def format_sources(chunks: Sequence[RetrievedChunk]) -> str:
    """Return the chunks as labelled blocks: [S#], title, year and tier, then the text, escaped."""
    if not chunks:
        return config.NO_SOURCES_BLOCK
    blocks = []
    for number, chunk in enumerate(chunks, start=1):
        meta = chunk.metadata
        tier = config.EVIDENCE_TIER_LABELS.get(meta["evidence_tier"], config.UNKNOWN_TIER_LABEL)
        title, year, tier, text = (
            escape_prompt_data(part) for part in (meta["title"], meta["year"], tier, chunk.text)
        )
        blocks.append(f"[S{number}] {title} ({year}; {tier})\n{text}")
    return "\n\n".join(blocks)


def format_profile(user: profile.UserProfile | None) -> str:
    """Return the profile as lines of fixed labels and checked values, or say there is none."""
    # Only validated numbers and fixed labels: nothing here is text the user typed.
    if user is None:
        # The exact line the owner's prompt names for a missing profile.
        return "Not given"
    return "\n".join(
        [
            f"Weight: {units.format_weight(user.weight_kg, 'metric')}",
            f"Height: {units.format_height(user.height_cm, 'metric')}",
            f"Age: {user.age} years",
            f"Sex: {profile.SEX_LABELS[user.sex]}",
            f"Activity: {profile.ACTIVITY_LABELS[user.activity]}",
            f"Goal: {profile.GOAL_LABELS[user.goal]}",
        ]
    )


def build_messages(
    question: str,
    chunks: Sequence[RetrievedChunk],
    system_prompt: str,
    user: profile.UserProfile | None = None,
) -> list[BaseMessage]:
    """Return the system prompt and one user message with <sources>, <profile> and <user_input>."""
    # Plain string content, never a prompt template: braces in the question stay as typed. The
    # profile holds only fixed labels and checked numbers; it is escaped like the rest anyway.
    content = (
        f"<sources>\n{format_sources(chunks)}\n</sources>\n\n"
        f"<profile>\n{escape_prompt_data(format_profile(user))}\n</profile>\n\n"
        f"<user_input>\n{escape_prompt_data(question)}\n</user_input>"
    )
    return [SystemMessage(system_prompt), HumanMessage(content)]


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


def _answer_text(reply: AIMessage) -> str:
    """Return the text of the model's reply; raise LLMError if it is empty."""
    text = remove_images(reply.text).strip()
    if not text:
        raise llm.LLMError(diagnostic="empty answer")
    return text


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


def _run_round(
    tools: Mapping[str, StructuredTool], reply: AIMessageChunk
) -> list[tuple[ToolMessage, ToolRun]]:
    """Run the reply's tool calls, within the limits per round; refuse the rest."""
    # OpenAI models always send call ids; a call without one gets "", which the API would refuse
    # on the next request (shown as a service error).
    done = []
    meal_plans = 0
    for number, call in enumerate(reply.tool_calls):
        if number >= config.MAX_TOOL_CALLS_PER_ROUND:
            done.append(registry.refused_call(call["id"] or "", config.TOO_MANY_TOOL_CALLS_MESSAGE))
        elif call["name"] == registry.MEAL_PLAN_TOOL:
            # Its result is long (up to MEAL_PLAN_MAX_ITEMS foods), so fewer of them run (T4.5).
            meal_plans += 1
            if meal_plans > config.MAX_MEAL_PLAN_CALLS_PER_ROUND:
                message = config.TOO_MANY_MEAL_PLANS_MESSAGE
                done.append(registry.refused_call(call["id"] or "", message))
            else:
                done.append(registry.run_tool_call(tools, call))
        else:
            done.append(registry.run_tool_call(tools, call))
    # Every call needs an answer, so arguments that are not valid JSON get one too.
    for call in reply.invalid_tool_calls:
        done.append(registry.refused_call(call["id"] or "", config.INVALID_TOOL_JSON_MESSAGE))
    return done


def answer_with_tools(
    chat_model: BaseChatModel,
    messages: Sequence[BaseMessage],
    tools: Mapping[str, StructuredTool],
    on_step: Callable[[Step], None],
    on_text: Callable[[str], None] | None = None,
    *,
    needs_tool: bool = False,
    recorder: UsageRecorder | None = None,
) -> tuple[str | None, tuple[ToolRun, ...]]:
    """Let the model call tools for at most MAX_TOOL_ROUNDS rounds; return its answer and runs."""
    # needs_tool (no relevant source): replies are not shown until a tool has really run (a refused
    # call, e.g. an unknown tool or bad arguments, does not count), and a reply with no tool call
    # before that gives None, so the caller shows NO_SOURCES_MESSAGE, never an answer with no basis.
    history = list(messages)
    runs: list[ToolRun] = []
    for round_number in range(config.MAX_TOOL_ROUNDS + 1):
        last = round_number == config.MAX_TOOL_ROUNDS
        hidden = needs_tool and all(run.status == "invalid" for run in runs)
        # Only the tools are bound (never the model or max_tokens; security-privacy.md). After the
        # last round the model must answer from the results it has.
        bound = chat_model.bind_tools(list(tools.values()), tool_choice="none" if last else None)
        record = None
        if recorder is not None:
            step = config.USAGE_STEP_ANSWER.format(round=round_number + 1)
            record = partial(recorder.add_chat, step, usage.model_name(chat_model))
        try:
            reply = stream_reply(bound, history, None if hidden else on_text, record)
        except llm.ReplyCutOffError:
            if hidden:
                # Nothing was shown and no tool ran: the turn ends as "not covered".
                return None, ()
            raise
        if not reply.tool_calls and not reply.invalid_tool_calls:
            if hidden:
                return None, ()
            return _answer_text(reply), tuple(runs)
        if last:
            raise ToolLoopError(diagnostic="tool calls after the last round")
        if on_text is not None:
            # Text written before the tool calls is not the answer.
            on_text("")
        on_step(Step.TOOLS)
        history.append(
            AIMessage(
                reply.content,
                tool_calls=reply.tool_calls,
                invalid_tool_calls=reply.invalid_tool_calls,
            )
        )
        for message, run in _run_round(tools, reply):
            history.append(message)
            runs.append(run)
        on_step(Step.ANSWER)
    # Not reached: the last call either answers or raises.
    raise ToolLoopError(diagnostic="tool loop ended without an answer")


@dataclass(frozen=True)
class TurnModels:
    """The clients and prompts an accepted question needs: query translation and the answer."""

    translation_model: BaseChatModel
    translation_prompt: str
    chat_model: BaseChatModel
    system_prompt: str


def answer_question(
    question: str,
    index: Chroma,
    models: TurnModels,
    manifest: Mapping[str, Source],
    on_step: Callable[[Step], None],
    on_text: Callable[[str], None] | None = None,
    user: profile.UserProfile | None = None,
    *,
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index,
    recorder: UsageRecorder | None = None,
) -> TurnResult:
    """Rewrite an accepted question, retrieve its chunks and answer from them, citing [S#]."""
    # recorder collects the tokens of every call; the caller keeps it, so an error keeps them too.
    on_step(Step.REWRITE)
    plan = query_translation.translate(
        question, models.translation_model, models.translation_prompt, recorder
    )
    on_step(Step.SEARCH)
    with llm.mapped_errors():
        chunks, details = find_chunks(
            question, plan, index, keyword_index=keyword_index, recorder=recorder
        )
    on_step(Step.ANSWER)
    # The user's own question, never the rewrites, goes to the answer model.
    messages = build_messages(question, chunks, models.system_prompt, user)
    # The energy tools get the profile here, never from the model.
    tools = registry.build_tools(user)
    # With no relevant chunk the model may still answer from a tool (a food lookup rarely matches
    # a research passage); if it calls none, the fixed "not covered" message is shown (AC-2;
    # owner's choice in T4.4).
    answer, runs = answer_with_tools(
        models.chat_model,
        messages,
        tools,
        on_step,
        on_text,
        needs_tool=not chunks,
        recorder=recorder,
    )
    if answer is None:
        return TurnResult("no_sources", config.NO_SOURCES_MESSAGE, search=details)
    cards = source_cards(chunks, cited_labels(answer, len(chunks)), manifest)
    return TurnResult("answer", answer, cards, search=details, tool_runs=runs)


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
) -> TurnResult:
    """Run one chat turn: the guard first, then retrieval and the answer; never raise for errors."""
    # on_step(step) is called as each step starts; on_text(text) as the answer streams in. `user`
    # is the session's profile, for the energy tools and the model's <profile> block.
    # keyword_index(index) gives the BM25 index of the opened index; the app passes a cached one.
    steps: list[Step] = []
    recorder = UsageRecorder()

    def step(name: Step) -> None:
        """Record a step and report it to the caller's progress indicator."""
        steps.append(name)
        if on_step is not None:
            on_step(name)

    def answer(question: str) -> TurnResult:
        """Open the index and the models only for an accepted question, then answer it."""
        # Read before any API call, so a missing or empty prompt file costs nothing.
        system_prompt = _load_prompt(config.ANSWER_PROMPT_PATH, config.PROMPT_MISSING_MESSAGE)
        translation_prompt = _load_prompt(
            config.QUERY_TRANSLATION_PROMPT_PATH, config.QUERY_PROMPT_MISSING_MESSAGE
        )
        # The index is opened first: a missing index is reported even when the key is missing.
        index = open_index()
        models = TurnModels(translation_model(), translation_prompt, chat_model(), system_prompt)
        return answer_question(
            question,
            index,
            models,
            manifest or {},
            step,
            on_text,
            user,
            keyword_index=keyword_index,
            recorder=recorder,
        )

    def failed(message: str, *, index_not_ready: bool = False) -> TurnResult:
        """Return an error result with the steps run and the tokens spent before the error."""
        return TurnResult(
            "error",
            message,
            steps=tuple(steps),
            index_not_ready=index_not_ready,
            usage=tuple(recorder.calls),
        )

    step(Step.CHECK)
    try:
        decision, result = guard.run_guarded(text, limiter, answer)
    except llm.LLMError as exc:
        # A fixed text, safe to show (never the server's reply or the key).
        return failed(str(exc))
    except IndexNotReadyError as exc:
        return failed(str(exc), index_not_ready=True)
    except PromptMissingError as exc:
        return failed(str(exc))
    except config.SecretsFileError:
        return failed(config.SECRETS_FILE_MESSAGE)
    except config.MissingAPIKeyError:
        return failed(config.MISSING_KEY_MESSAGE)
    if result is None:
        kind = "guardrail" if decision.reason is guard.Rejection.GUARDRAIL else "rejected"
        return TurnResult(kind, decision.message or "", steps=tuple(steps))
    return replace(result, steps=tuple(steps), usage=tuple(recorder.calls))
