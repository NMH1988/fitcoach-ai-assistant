"""Article XML -> text sections -> chunks with metadata, for the vector index.

Keeps the article title, the abstract and the body sections. Drops figures, tables, display
formulas, supplementary material, the reference list, numeric citation markers, back matter and
anything that carries its own <permissions> or <attrib> (third-party content), as the copyright
policy requires (text only, rules 5 and 7). Inline formulas keep their plain text, with exponents,
subscripts, brackets and accents written out ("I^2", "β_x", "P(>0)", "R̂") so the numbers keep
their meaning (owner's choice in T2.2). Only the front matter's abstract and the <body> are read;
<back>, <floats-group> and sub-articles never are.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src import config
from src.rag.sources import Source, check_article, load_manifest

# Elements that never become text: floats, formulas, supplementary files, references, notes, the
# glossary, labels (section numbers, list bullets) and the TeX copy of a formula.
_DROPPED_TAGS = frozenset(
    {
        "disp-formula",
        "disp-formula-group",
        "fig",
        "fig-group",
        "fn",
        "fn-group",
        "glossary",
        "graphic",
        "inline-graphic",
        "label",
        "media",
        "ref-list",
        "supplementary-material",
        "table",
        "table-wrap",
        "table-wrap-group",
        "tex-math",
    }
)
# Elements that start a new line in the text.
_BLOCK_TAGS = frozenset({"boxed-text", "def-list", "disp-quote", "list", "p", "sec", "statement"})
# Children of a section that are not part of its text.
_SECTION_META_TAGS = frozenset({"label", "sec-meta", "title"})
# Cross-references to notes we drop; their markers ("a", "b") would be stray letters.
_DROPPED_XREF_TYPES = frozenset({"fn", "table-fn"})
# Superscripts that are symbols, ordinals or note marks, not exponents, so they get no "^".
_PLAIN_SUPERSCRIPTS = frozenset({"®", "™", "†", "‡", "§", "*", "st", "nd", "rd", "th"})
_MATHML = "{http://www.w3.org/1998/Math/MathML}"
# Combining marks for MathML accents, so an R with a hat over it reads "R̂".
_ACCENTS = {
    "^": "̂",
    "ˆ": "̂",
    "~": "̃",
    "˜": "̃",
    "¯": "̄",
    "‾": "̄",
    "˙": "̇",  # a dot, as in V̇O2
}
# Stands in for a removed reference marker until the line is cleaned, so only brackets that held
# markers are removed, never brackets that were in the text ("(-)-epicatechin").
_CITATION = "\x00"
_SEPARATORS = r"\s,;–—-"
# Reference markers that are numbers ("12", "3-5", "1, 2"); author-year text is kept.
_NUMERIC_CITATION = re.compile(rf"[\d{_SEPARATORS}]*")
# A link on the year alone, as in "Smith et al. (2020)": part of the sentence, so it is kept.
_CITATION_YEAR = re.compile(r"\s*(?:19|20)\d{2}[a-z]?\s*")
# Brackets that hold only removed markers and separators: "[1]", "[1, 2]", "(3-5)".
_CITATION_BRACKETS = re.compile(
    rf"[\[(][{_SEPARATORS}]*{_CITATION}[{_CITATION}{_SEPARATORS}]*[\])]"
)
# A superscript that held nothing but citations: "1,2", "[1]".
_CITATION_ONLY = re.compile(rf"[{_CITATION}\[\](){_SEPARATORS}]*")
# A run of removed markers with the space before it, left once their brackets are gone.
_CITATION_RUN = re.compile(rf"\s*{_CITATION}(?:[{_SEPARATORS}]*{_CITATION})*")


@dataclass(frozen=True)
class Section:
    """One section of an article: its title (a path such as "Methods > Search") and its text."""

    title: str
    text: str


@dataclass(frozen=True)
class ParsedArticle:
    """The text of an article: its title and its sections in reading order."""

    title: str
    sections: list[Section]


class IngestError(RuntimeError):
    """Raised when article XML cannot be read, parsed or turned into chunks."""


def _local(tag: Any) -> str:
    """Return an element's tag without its namespace ("" for comments and processing steps)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _skipped(el: ET.Element) -> bool:
    """Tell whether an element is left out of the text, with everything inside it."""
    local = _local(el.tag)
    if not local or local in _DROPPED_TAGS:
        return True
    if local == "xref" and el.get("ref-type") in _DROPPED_XREF_TYPES:
        return True
    # Content with its own copyright line, or credited to someone else, belongs to a third party
    # (copyright policy rule 7).
    return el.find("permissions") is not None or el.find("attrib") is not None


def _space(text: str | None) -> str:
    """Collapse the XML's own line breaks and indentation into single spaces."""
    return re.sub(r"\s+", " ", text) if text else ""


def _render(el: ET.Element) -> str:
    """Return the text inside an element, without skipped elements; blocks start a new line."""
    # Whitespace between MathML elements is only layout, so "P (>0) =" stays "P(>0)=".
    math = _local(el.tag) != "" and el.tag.startswith(_MATHML)
    parts = [_space(el.text) if not math or (el.text or "").strip() else ""]
    before = el.text or ""  # the raw text before the next child, line breaks included
    for child in el:
        if not _skipped(child):
            text = _render_child(child)
            if text.startswith("^") and "\n" in before[len(before.rstrip()) :]:
                # The XML broke the line just before an exponent ("τ\n<sup>2</sup>"); a real
                # space stays, e.g. before an isotope ("doses of ^15N-glycine").
                parts[-1] = parts[-1].rstrip()
            parts.append(text)
        tail = child.tail or ""
        parts.append(_space(tail) if not math or tail.strip() else "")
        before = tail
    return "".join(parts)


def _render_math(el: ET.Element, local: str) -> str | None:
    """Render a MathML script, fence or accent as plain text, or None for other elements."""
    if local not in ("msup", "msub", "msubsup", "mfenced", "mover"):
        return None
    # _render_child, so a script or fence directly inside another keeps its own structure.
    parts = [_render_child(c).strip() for c in el if _local(c.tag)]
    if local == "mfenced":
        # MathML's default separator is a comma; separators="" means none.
        separator = (el.get("separators", ",").strip()[:1] + " ").lstrip()
        return el.get("open", "(") + separator.join(parts) + el.get("close", ")")
    if len(parts) < 2:
        return "".join(parts)
    if local == "msup":
        return f"{parts[0]}^{parts[1]}"
    if local == "msub":
        return f"{parts[0]}_{parts[1]}"
    if local == "msubsup":
        return f"{parts[0]}_{parts[1]}^{parts[2]}" if len(parts) > 2 else f"{parts[0]}_{parts[1]}"
    base, over = parts[0], parts[1]
    if over in _ACCENTS:
        # Some publishers repeat the accent inside the base ("R^" under "^"); keep one hat.
        return base.removesuffix(over) + _ACCENTS[over]
    return base + over


def _render_child(child: ET.Element) -> str:
    """Render one kept child element, keeping exponents, fences and citations readable."""
    local = _local(child.tag)
    if local == "xref" and child.get("ref-type") == "bibr":
        text = "".join(child.itertext())
        numeric = _NUMERIC_CITATION.fullmatch(text) and not _CITATION_YEAR.fullmatch(text)
        return _CITATION if numeric else _space(text)
    if child.tag.startswith(_MATHML) and (math := _render_math(child, local)) is not None:
        return math
    text = _render(child)
    if local == "list-item":
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n- " + "\n".join(lines) + "\n" if lines else ""
    if local in _BLOCK_TAGS:
        return f"\n{text}\n"
    if local == "sup":
        if _CITATION in text and _CITATION_ONLY.fullmatch(text):
            return _CITATION  # a superscript that held only reference numbers ("1,2")
        if not text.strip() or text.strip() in _PLAIN_SUPERSCRIPTS:
            return text
        return f"^{text}"  # an exponent: "10^-3", "kg^-1", "I^2"
    if local == "break":
        return " "
    return text


def _clean_line(text: str) -> str:
    """Collapse whitespace and take out removed citations together with their brackets."""
    text = " ".join(text.split())
    while (cleaned := _CITATION_BRACKETS.sub(_CITATION, text)) != text:
        text = cleaned  # repeat for nested brackets, e.g. "([1], [2])"
    return _CITATION_RUN.sub("", text).strip()


def _clean(text: str) -> str:
    """Clean each line of a rendered block and drop the empty ones."""
    lines = (_clean_line(line) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _title_key(title: str) -> str:
    """Reduce a section title to lower-case words, for matching against the drop list."""
    text = title.casefold().replace("’", "").replace("'", "")
    text = re.sub(r"^[\d.\s]+", "", text)
    return " ".join(re.sub(r"[^a-z]+", " ", text).split())


def _dropped_section(sec: ET.Element, title: str) -> bool:
    """Tell whether a section is back matter (acknowledgements, funding, references, ...)."""
    sec_types = {part.casefold() for part in (sec.get("sec-type") or "").split("|")}
    if sec_types & config.INGEST_DROPPED_SEC_TYPES:
        return True
    key = _title_key(title)
    return key in config.INGEST_DROPPED_SEC_TITLES or key.startswith("appendix")


def _collect(container: ET.Element, path: list[str], out: list[Section]) -> None:
    """Append the sections of a container (abstract, body or sec) to `out` in reading order."""
    blocks: list[str] = []

    def flush() -> None:
        """Close the text gathered so far as one section under the current title path."""
        if blocks:
            out.append(Section(" > ".join(path) or config.MAIN_TEXT_TITLE, "\n\n".join(blocks)))
            blocks.clear()

    for child in container:
        local = _local(child.tag)
        if _skipped(child) or local in _SECTION_META_TAGS:
            continue
        if local == "sec":
            # Text after a subsection becomes its own section, so no section mixes two.
            flush()
            title_el = child.find("title")
            title = _clean_line(_render(title_el)) if title_el is not None else ""
            if not _dropped_section(child, title):
                _collect(child, [*path, title] if title else path, out)
        elif text := _clean(_render(child)):
            blocks.append(text)
    flush()


def parse_article(xml: bytes) -> ParsedArticle:
    """Return the title, abstract and body sections of a JATS article; raise IngestError."""
    try:
        article = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise IngestError("The article is not valid XML.") from exc
    title_el = article.find("front/article-meta/title-group/article-title")
    title = _clean_line(_render(title_el)) if title_el is not None else ""
    sections: list[Section] = []
    for abstract in article.findall("front/article-meta/abstract"):
        _collect(abstract, ["Abstract"], sections)
    body = article.find("body")
    if body is not None:
        _collect(body, [], sections)
    return ParsedArticle(title=title, sections=sections)


def merge_short_spans(spans: list[tuple[int, int]], header_chars: int) -> list[tuple[int, int]]:
    """Join each short (start, end) span to the one before it, else after it, within the cap."""
    # The splitter leaves short pieces where a paragraph or a section ends, often little more than
    # the overlap they repeat; such chunks were near short, generic queries (T3.7).
    cap = config.CHUNK_SIZE + config.CHUNK_MIN_CHARS
    merged = list(spans)
    i = 0
    while i < len(merged):
        start, end = merged[i]
        if len(merged) > 1 and header_chars + end - start < config.CHUNK_MIN_CHARS:
            if i > 0 and header_chars + end - merged[i - 1][0] <= cap:
                merged[i - 1 : i + 1] = [(merged[i - 1][0], end)]
                i -= 1  # check the joined span again
                continue
            if i + 1 < len(merged) and header_chars + merged[i + 1][1] - start <= cap:
                merged[i : i + 2] = [(start, merged[i + 1][1])]
                continue
        i += 1
    return merged


def _piece_spans(text: str, pieces: list[str]) -> list[tuple[int, int]] | None:
    """Return each piece's (start, end) in the text, or None if they do not cover it in order."""
    spans: list[tuple[int, int]] = []
    previous_start, previous_end = -1, 0
    for piece in pieces:
        # Each piece adds text after the one before it, so an earlier copy of its words (e.g. a
        # repeated sentence inside the overlap) is skipped. LangChain's own start_index is not
        # used: it takes the first copy after the overlap starts, which can be that earlier one.
        start = text.find(piece, previous_start + 1)
        while start >= 0 and start + len(piece) <= previous_end:
            start = text.find(piece, start + 1)
        if start < 0 or text[previous_end:start].strip():
            return None  # not found, or text between two pieces would be lost
        previous_start, previous_end = start, start + len(piece)
        spans.append((start, previous_end))
    return None if text[previous_end:].strip() else spans


def _split_section(text: str, header: str) -> list[str]:
    """Split a section's text into chunk bodies; a short piece joins a neighbouring one."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max(config.CHUNK_SIZE - len(header), config.CHUNK_MIN_BODY_CHARS),
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    pieces = splitter.split_text(text)
    spans = _piece_spans(text, pieces)
    # If the pieces cannot be placed in the text, they stay as the splitter made them.
    if spans is None:
        return pieces
    # A joined span is one passage of the section's own text: nothing lost, no overlap repeated.
    return [text[start:end] for start, end in merge_short_spans(spans, len(header))]


def chunk_article(
    article: ParsedArticle, source: Source, extra_metadata: dict[str, Any] | None = None
) -> list[Document]:
    """Split each section into chunks that start with the section title, with source metadata."""
    chunks: list[Document] = []
    for section in article.sections:
        header = f"{section.title}\n\n"
        for piece in _split_section(section.text, header):
            # The ten required keys come last, so extra metadata can never overwrite them.
            metadata = {
                # Lists are copied, so changing one chunk's metadata never changes another's.
                **{
                    key: list(value) if isinstance(value, list) else value
                    for key, value in (extra_metadata or {}).items()
                },
                "source_id": source.id,
                "title": source.title,
                "authors": list(source.authors),
                "year": source.year,
                "section": section.title,
                "topics": list(source.topics),
                "evidence_tier": source.evidence_tier,
                "license": source.license,
                "source_url": source.url,
                "chunk_index": len(chunks),
            }
            chunks.append(Document(page_content=header + piece, metadata=metadata))
    return chunks


def load_chunks(sources: list[Source] | None = None, raw_dir: Path | None = None) -> list[Document]:
    """Return the chunks of every source's downloaded article; raise IngestError if any fails."""
    sources = load_manifest() if sources is None else sources
    raw_dir = raw_dir or config.RAW_SOURCES_DIR
    corrected_by: dict[str, list[str]] = {}
    for source in sources:
        if source.corrects:
            corrected_by.setdefault(source.corrects, []).append(source.id)
    chunks: list[Document] = []
    problems: list[str] = []
    for source in sources:
        name = f"#{source.id} ({source.pmcid})"
        try:
            xml = (raw_dir / f"{source.pmcid}.xml").read_bytes()
        except OSError:
            problems.append(
                f"{name}: missing or unreadable; run python scripts/download_sources.py"
            )
            continue
        if (reason := check_article(xml, source)) is not None:
            problems.append(f"{name}: refused: {reason}")
            continue
        # A correction must be read with the article it corrects (copyright policy rule 7).
        extra: dict[str, Any] = {}
        if source.corrects:
            extra["corrects"] = source.corrects
        if source.id in corrected_by:
            extra["corrected_by"] = corrected_by[source.id]
        article_chunks = chunk_article(parse_article(xml), source, extra)
        if not article_chunks:
            problems.append(f"{name}: no text found")
            continue
        chunks.extend(article_chunks)
    if problems:
        raise IngestError("Cannot build the chunks:\n" + "\n".join(f"- {p}" for p in problems))
    return chunks
