"""One chat turn: guard -> vector retrieval -> answer with [S#] citations -> TurnResult.

The user's question goes only inside <user_input> and the retrieved chunks only inside <sources>,
both in the user message; neither is ever put into the system prompt
(.claude/rules/security-privacy.md). Every error a user can cause or meet ends as a TurnResult with
a fixed message, so the app shows it in the answer and keeps the chat history (AC-13).
"""

import re
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
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
)

from src import config, guard, llm
from src.rag.retriever import RetrievedChunk, retrieve
from src.rag.sources import ManifestError, Source, license_url_for, load_manifest
from src.rag.store import IndexNotReadyError


class Step(StrEnum):
    """The steps of a turn, as the progress indicator names them."""

    CHECK = "Checking your question"
    SEARCH = "Searching the research"
    ANSWER = "Writing the answer"


# answer: the model's answer; no_sources: nothing relevant was found (AC-2); rejected: the guard
# refused the input; error: a model, key or index problem.
TurnKind = Literal["answer", "no_sources", "rejected", "error"]


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
class TurnResult:
    """What one chat turn gives the UI: the text to show, its sources and the steps it ran."""

    kind: TurnKind
    text: str
    sources: tuple[SourceCard, ...] = ()
    steps: tuple[Step, ...] = ()
    # True when the index could not be used, so the app opens it again on the next turn.
    index_not_ready: bool = False


# A citation is one bracket holding labels or ranges: [S1], [S1, S3], [S2; S4], [S1 and S2],
# [S1, S2, and S3], [S1 & S2], [S1-S3], [S1–S3].
_BRACKET = re.compile(r"\[([^\[\]]{1,80})\]")
_CITED_ITEM = r"S\d+(?:\s*[-–]\s*S?\d+)?"
_CITATION_SEPARATOR = r"\s*(?:[,;]\s*(?:and\s+|&\s*)?|and\s+|&\s*)"
_CITATION_BODY = re.compile(rf"\s*{_CITED_ITEM}(?:{_CITATION_SEPARATOR}{_CITED_ITEM})*\s*")
_LABEL_OR_RANGE = re.compile(r"S(\d+)(?:\s*[-–]\s*S?(\d+))?")
# A Markdown image, inline (![alt](url)) or by reference (![alt][ref]): the browser would load
# its URL with no click, so an injected one could send text to another server.
_MARKDOWN_IMAGE = re.compile(r"!\[([^\[\]]*)\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\])?")
# Characters Streamlit's Markdown would read as formatting, HTML or LaTeX in a title.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>$])")


class PromptMissingError(RuntimeError):
    """The answer prompt file is missing, unreadable or empty."""


def load_system_prompt(path: Path | None = None) -> str:
    """Return the owner's answer system prompt from its file."""
    text = (path or config.ANSWER_PROMPT_PATH).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("The answer system prompt is empty.")
    return text


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
    """Return the chunks as labelled blocks: [S#], title, year and tier, then the text."""
    blocks = []
    for number, chunk in enumerate(chunks, start=1):
        meta = chunk.metadata
        tier = config.EVIDENCE_TIER_LABELS.get(meta["evidence_tier"], config.UNKNOWN_TIER_LABEL)
        blocks.append(f"[S{number}] {meta['title']} ({meta['year']}; {tier})\n{chunk.text}")
    return "\n\n".join(blocks)


def build_messages(
    question: str, chunks: Sequence[RetrievedChunk], system_prompt: str
) -> list[BaseMessage]:
    """Return the system prompt and one user message holding <sources> and <user_input>."""
    user = (
        f"<sources>\n{format_sources(chunks)}\n</sources>\n\n"
        f"<user_input>\n{question}\n</user_input>"
    )
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
    """Return the text of the model's reply; raise LLMError if it is cut off or empty."""
    if reply.response_metadata.get("finish_reason") == "length":
        raise llm.ReplyCutOffError(diagnostic="finish_reason length in the answer step")
    text = remove_images(reply.text).strip()
    if not text:
        raise llm.LLMError(diagnostic="empty answer")
    return text


def stream_answer(
    chat_model: BaseChatModel,
    messages: Sequence[BaseMessage],
    on_text: Callable[[str], None] | None = None,
) -> str:
    """Stream the model's answer, reporting the text so far as it grows; return the full text."""
    reply: AIMessageChunk | None = None
    with llm.mapped_errors():
        for chunk in chat_model.stream(messages):
            reply = chunk if reply is None else reply + chunk
            if on_text is not None and chunk.text:
                # Images are removed on every update: one completed mid-stream would load at once.
                on_text(remove_images(reply.text))
    if reply is None:
        raise llm.LLMError(diagnostic="no answer chunks")
    return _answer_text(reply)


def answer_question(
    question: str,
    index: Chroma,
    chat_model: BaseChatModel,
    manifest: Mapping[str, Source],
    on_step: Callable[[Step], None],
    system_prompt: str,
    on_text: Callable[[str], None] | None = None,
) -> TurnResult:
    """Retrieve the chunks for an accepted question and answer it from them, citing [S#]."""
    on_step(Step.SEARCH)
    with llm.mapped_errors():
        chunks = retrieve(index, question)
    if not chunks:
        # Nothing close enough: no model call and no citation (AC-2).
        return TurnResult("no_sources", config.NO_SOURCES_MESSAGE)
    on_step(Step.ANSWER)
    messages = build_messages(question, chunks, system_prompt)
    answer = stream_answer(chat_model, messages, on_text)
    cards = source_cards(chunks, cited_labels(answer, len(chunks)), manifest)
    return TurnResult("answer", answer, cards)


def run_turn(
    text: str,
    limiter: guard.RateLimiter,
    *,
    open_index: Callable[[], Chroma],
    chat_model: Callable[[], BaseChatModel],
    manifest: Mapping[str, Source] | None = None,
    on_step: Callable[[Step], None] | None = None,
    on_text: Callable[[str], None] | None = None,
) -> TurnResult:
    """Run one chat turn: the guard first, then retrieval and the answer; never raise for errors."""
    # on_step(step) is called as each step starts; on_text(text) as the answer streams in.
    steps: list[Step] = []

    def step(name: Step) -> None:
        """Record a step and report it to the caller's progress indicator."""
        steps.append(name)
        if on_step is not None:
            on_step(name)

    def answer(question: str) -> TurnResult:
        """Open the index and the model only for an accepted question, then answer it."""
        # Read before any API call, so a missing or empty prompt file costs nothing.
        try:
            system_prompt = load_system_prompt()
        except OSError, ValueError:
            raise PromptMissingError from None
        # The index is opened first: a missing index is reported even when the key is missing.
        index = open_index()
        return answer_question(
            question, index, chat_model(), manifest or {}, step, system_prompt, on_text
        )

    step(Step.CHECK)
    try:
        decision, result = guard.run_guarded(text, limiter, answer)
    except llm.LLMError as exc:
        # A fixed text, safe to show (never the server's reply or the key).
        return TurnResult("error", str(exc), steps=tuple(steps))
    except IndexNotReadyError as exc:
        return TurnResult("error", str(exc), steps=tuple(steps), index_not_ready=True)
    except PromptMissingError:
        return TurnResult("error", config.PROMPT_MISSING_MESSAGE, steps=tuple(steps))
    except config.SecretsFileError:
        return TurnResult("error", config.SECRETS_FILE_MESSAGE, steps=tuple(steps))
    except config.MissingAPIKeyError:
        return TurnResult("error", config.MISSING_KEY_MESSAGE, steps=tuple(steps))
    if result is None:
        return TurnResult("rejected", decision.message or "", steps=tuple(steps))
    return replace(result, steps=tuple(steps))
