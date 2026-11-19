"""The sources: the <sources> block, the [S#] citations, the source cards, the manifest."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src import config
from src.chat.results import Correction, SourceCard
from src.prompt_data import escape_prompt_data
from src.rag.retriever import RetrievedChunk
from src.rag.sources import ManifestError, Source, license_url_for, load_manifest

# A citation is one bracket holding labels or ranges: [S1], [S1, S3], [S2; S4], [S1 and S2],
# [S1, S2, and S3], [S1 & S2], [S1-S3], [S1–S3], and in a German answer [S1 und S2] (T7.2).
_BRACKET = re.compile(r"\[([^\[\]]{1,80})\]")
# A bracket with the spaces before it, so a removed citation leaves no space before a full stop.
_BRACKET_WITH_SPACE = re.compile(r"[ \t]*\[([^\[\]]{1,80})\]")
_CITED_ITEM = r"S\d+(?:\s*[-–]\s*S?\d+)?"
_CITATION_SEPARATOR = r"\s*(?:[,;]\s*(?:(?:and|und)\s+|&\s*)?|(?:and|und)\s+|&\s*)"
_CITATION_BODY = re.compile(rf"\s*{_CITED_ITEM}(?:{_CITATION_SEPARATOR}{_CITED_ITEM})*\s*")
_LABEL_OR_RANGE = re.compile(r"S(\d+)(?:\s*[-–]\s*S?(\d+))?")


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


def manifest_by_id() -> dict[str, Source]:
    """Return the approved sources by ID, or an empty dict if the manifest cannot be read."""
    try:
        return {source.id: source for source in load_manifest()}
    except ManifestError:
        # The cards then show what the chunks carry, without the journal and corrections.
        return {}


def format_authors(authors: Sequence[str]) -> str:
    """Return the first CARD_AUTHORS_SHOWN authors, then "et al." if there are more."""
    shown = ", ".join(authors[: config.CARD_AUTHORS_SHOWN])
    return f"{shown} et al." if len(authors) > config.CARD_AUTHORS_SHOWN else shown


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


def strip_citations(answer: str) -> str:
    """Return the answer without its [S#] citations, as the conversation keeps it (T9.4)."""

    # A later turn labels its own chunks from S1 again, so an old label could stand for another
    # source (copyright policy rule 7; T9.4). A bracket that is not a citation stays.
    def remove(bracket: re.Match[str]) -> str:
        """Return "" for a citation bracket, else the bracket as written."""
        return "" if _CITATION_BODY.fullmatch(bracket.group(1)) else bracket.group(0)

    return _BRACKET_WITH_SPACE.sub(remove, answer)


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
