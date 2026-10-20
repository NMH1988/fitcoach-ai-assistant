"""The session summary PDF (T5.2, AC-9): profile, targets, questions and answers, credits.

The PDF is built in memory with ReportLab and handed to the download button; nothing is written to
disk and nothing is logged (.claude/rules/security-privacy.md). ReportLab's `Paragraph` reads its
text as markup (`<b>`, `<font>`, `<link href=...>`), so every text that is not ours (the question,
the model's answer, source titles, USDA names) goes through `_text()`, which escapes it: no model
text can add formatting or a link, and a "<" cannot break the PDF. Answers are first unescaped
(`html.unescape`), as the model may copy an entity from the escaped prompt (T3.4), and their
Markdown is turned into plain text by `clean_answer()`. The PDF holds no link annotations at all:
URLs are printed as text.
"""

import html
import io
import re
from collections.abc import Mapping, Sequence
from datetime import date
from functools import cache
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src import config, profile, units
from src.chat import SourceCard, TurnResult
from src.profile import UserProfile
from src.rag.sources import (
    ARTICLE_CHANGES_NOTE,
    CHANGES_MADE,
    FORMULA_CHANGES_MADE,
    Source,
)
from src.tools import registry
from src.tools.energy import FORMULA_SOURCES, FormulaSource, Macro, TdeeResult
from src.tools.food import FoodLookupResult, FoodTableError, read_usda_release
from src.units import UnitSystem

FONT = "DejaVuSans"
BOLD_FONT = "DejaVuSans-Bold"
# Page layout, in points.
MARGIN = 18 * mm
CONTENT_WIDTH = A4[0] - 2 * MARGIN
LABEL_WIDTH = 55 * mm
BODY_SIZE = 10
SMALL_SIZE = 8.5
LEADING = 1.35
INDENT = 5 * mm
MUTED = colors.HexColor("#4A5250")
RULE = colors.HexColor("#D8DEDB")
# Shown for a character the font has no glyph for (DejaVu Sans has this one).
MISSING = "�"
BMP_LAST = 0xFFFF

# Every heading and fixed label of the PDF, in one place for the German version (T7.2).
TEXT = {
    "title": f"{config.APP_TITLE}: session summary",
    "created": "Created on {date}",
    "disclaimer": "Not medical advice.",
    "profile": "Your profile",
    "no_profile": "No details were added in this session.",
    "targets": "Your daily targets",
    "targets_note": "Calculated by the app from the profile above, with no AI model.",
    "no_targets": "Add your details in the app to get personal targets.",
    "turns": "Questions and answers",
    "no_turns": "No questions were asked in this session.",
    "question": "Question {number}",
    "answer": "Answer",
    "sources": "Sources",
    "tool_results": "Tool results",
    "credits": "Credits",
    "credits_intro": (
        "The answers and targets draw on the open access articles below; each is used under its "
        "own licence. The full list of the app's sources, with every article's copyright notice, "
        "is in ATTRIBUTION.md in the repository."
    ),
    "formula_sources": "Formula sources (the energy calculations use their equation or factors)",
    "food_data": "Food data",
    "footer": f"{config.APP_TITLE} · Not medical advice · Page {{page}}",
}
# What a turn that has no answer shows under its question, before its fixed message.
KIND_LABELS = {
    "no_sources": "No matching research found",
    "rejected": "Question not accepted",
    "guardrail": "Not something this assistant can advise on",
    "error": "Something went wrong",
}
TOOL_TITLES = {
    registry.TDEE_TOOL: "Daily energy needs",
    registry.MACRO_TOOL: "Daily targets",
    registry.FOOD_TOOL: "Food lookup",
    None: "Tool call not run",
}
PROFILE_LABELS = ("Weight", "Height", "Age", "Sex", "Activity", "Goal")

# Characters no PDF text should hold: C0 controls (but tab and newline) and DEL.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")
# Markdown that clean_answer() turns into plain text.
# A link, with an optional title: [text](url) or [text](<url> "title").
_LINK = re.compile(r"\[([^\[\]]*)\]\(\s*<?([^()\s<>]*)>?(?:\s+\"[^\"]*\")?\s*\)")
_BARE_URL = re.compile(r"https?://[^\s<>*`]+")
_SLOT = re.compile(r"\x00(\d+)\x00")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_QUOTE = re.compile(r"^\s*(?:>\s?)+")
_RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
# Bold with ** may sit inside a word; with __ (and emphasis with _) only at word edges, as in
# CommonMark, so "snake__case__name" stays as written.
_STRONG = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_UNDERSCORE_STRONG = re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)")
_EMPHASIS = re.compile(
    r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])|(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)"
)
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_CODE = re.compile(r"(`+)(.+?)\1")
_BACKSLASH = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~<>])")


class PdfExportError(RuntimeError):
    """The summary could not be built; the message says nothing of the session's content."""


@cache
def _register_fonts() -> None:
    """Register DejaVu Sans and its bold face with ReportLab, once per process."""
    pdfmetrics.registerFont(TTFont(FONT, str(config.PDF_FONT_PATH)))
    pdfmetrics.registerFont(TTFont(BOLD_FONT, str(config.PDF_BOLD_FONT_PATH)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD_FONT)


def _style(name: str, **overrides: object) -> ParagraphStyle:
    """Return a paragraph style in DejaVu Sans, body size unless overridden."""
    size = overrides.pop("fontSize", BODY_SIZE)
    font = overrides.pop("fontName", FONT)
    return ParagraphStyle(
        name, fontName=font, fontSize=size, leading=float(size) * LEADING, **overrides
    )


STYLES = {
    "title": _style("title", fontName=BOLD_FONT, fontSize=16, spaceAfter=2 * mm),
    # Headings stay on the page of what follows them.
    "h1": _style(
        "h1", fontName=BOLD_FONT, fontSize=13, spaceBefore=5 * mm, spaceAfter=2 * mm, keepWithNext=1
    ),
    "h2": _style(
        "h2", fontName=BOLD_FONT, fontSize=11, spaceBefore=4 * mm, spaceAfter=1 * mm, keepWithNext=1
    ),
    "h3": _style("h3", fontName=BOLD_FONT, spaceBefore=2 * mm, spaceAfter=1 * mm, keepWithNext=1),
    "body": _style("body", spaceAfter=1.5 * mm),
    "bullet": _style("bullet", leftIndent=INDENT, firstLineIndent=-3 * mm, spaceAfter=1 * mm),
    "small": _style("small", fontSize=SMALL_SIZE, textColor=MUTED, spaceAfter=1 * mm),
    "correction": _style(
        "correction", fontSize=SMALL_SIZE, textColor=MUTED, leftIndent=INDENT, spaceAfter=1 * mm
    ),
    "cell": _style("cell"),
}


def _plain(text: str) -> str:
    """Return text without control characters and with Windows line ends made plain."""
    return _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


@cache
def _font_characters() -> frozenset[int]:
    """Return the code points DejaVu Sans has a glyph for (and the bold face too)."""
    _register_fonts()
    faces = (pdfmetrics.getFont(name).face for name in (FONT, BOLD_FONT))
    return frozenset.intersection(*(frozenset(face.charToGlyph) for face in faces))


def _text(text: str) -> str:
    """Return text escaped for ReportLab's markup, so it shows exactly as written."""
    # A character outside the BMP (an emoji) or one the font lacks becomes U+FFFD: ReportLab 5.0.1
    # writes a broken text map for the first (5 hex digits, found with pypdf) and would draw an
    # empty box for the others.
    known = _font_characters()
    shown = "".join(
        c if c in "\t\n" or (ord(c) <= BMP_LAST and ord(c) in known) else MISSING
        for c in _plain(text)
    )
    return escape(shown)


def _para(text: str, style: str = "body") -> Paragraph:
    """Return a paragraph of plain (not ours) text, escaped first."""
    return Paragraph(_text(text), STYLES[style])


def _labelled(label: str, text: str, style: str = "body") -> Paragraph:
    """Return a paragraph with our label in bold, then plain text, escaped."""
    # The label is a fixed string of ours, escaped too, so a later translation cannot break it.
    return Paragraph(f"<b>{escape(label)}</b> {_text(text)}", STYLES[style])


def _emphasis_free(text: str) -> str:
    """Return text (no code, links or URLs in it) without emphasis marks or Markdown escapes."""
    text = _STRONG.sub(r"\1", text)
    text = _UNDERSCORE_STRONG.sub(r"\1", text)
    text = _STRIKE.sub(r"\1", text)
    text = _EMPHASIS.sub(lambda m: m.group(1) or m.group(2), text)
    # Entities last, as CommonMark reads them: never as Markdown ("&gt; 5 g" is not a quote).
    return html.unescape(_BACKSLASH.sub(r"\1", text))


def _link(match: re.Match[str]) -> str:
    """Return a Markdown link as its text and its URL in brackets, both plain."""
    label, url = _emphasis_free(match.group(1)).strip(), html.unescape(match.group(2))
    if not url or label == url:
        return label or url
    return f"{label} ({url})" if label else url


def _inline_text(text: str) -> str:
    """Return text outside code spans with its links, URLs and emphasis made plain."""
    # Links and bare URLs are set aside first, so emphasis rules cannot change a URL
    # ("https://x.org/__init__"); the NUL-delimited slots cannot clash, as _plain() drops NUL.
    kept: list[str] = []

    def keep(value: str) -> str:
        """Set a finished piece of text aside and return its slot."""
        kept.append(value)
        return f"\x00{len(kept) - 1}\x00"

    text = _LINK.sub(lambda m: keep(_link(m)), text)
    text = _BARE_URL.sub(lambda m: keep(html.unescape(m.group(0))), text)
    text = _emphasis_free(text)
    return _SLOT.sub(lambda m: kept[int(m.group(1))], text)


def _inline_markdown(line: str) -> str:
    """Return one line with its code spans, links, emphasis and escapes made plain."""
    parts, start = [], 0
    for code in _CODE.finditer(line):
        parts.append(_inline_text(line[start : code.start()]))
        # A code span is shown as written, entities included, as in the app.
        parts.append(code.group(2))
        start = code.end()
    parts.append(_inline_text(line[start:]))
    return "".join(parts)


def _table_row(line: str) -> str | None:
    """Return a Markdown table row as its cells joined by " · ", "" for a separator, else None."""
    if _TABLE_SEPARATOR.match(line):
        return ""
    if not _TABLE_ROW.match(line):
        return None
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return " · ".join(cell.strip() for cell in cells)


def clean_answer(answer: str) -> list[tuple[str, int]]:
    """Return an answer's lines as plain text with their list level (0 = not a list item)."""
    # Block marks are read on the text as the model wrote it, and entities are decoded only in the
    # inline text (T3.4: "p &lt; 0.05" becomes "p < 0.05"; _text() escapes it again later).
    lines: list[tuple[str, int]] = []
    in_code = False
    for raw in _plain(answer).split("\n"):
        if _FENCE.match(raw):
            in_code = not in_code
            continue
        if in_code:
            # A code block is shown as written, as in the app.
            lines.append((raw.strip(), 0))
            continue
        if _RULE.match(raw):
            continue
        line = _HEADING.sub("", _QUOTE.sub("", raw))
        row = _table_row(line)
        if row is not None:
            if row:
                lines.append((_inline_markdown(row).strip(), 0))
            continue
        level = 0
        bullet = _BULLET.match(line)
        if bullet:
            level = 1 + min(len(bullet.group(1).expandtabs(4)) // 2, 2)
            line = "• " + line[bullet.end() :]
        lines.append((_inline_markdown(line).strip(), level))
    return lines


def _answer_flowables(answer: str) -> list[Flowable]:
    """Return the cleaned answer as paragraphs, list items indented by level."""
    flowables: list[Flowable] = []
    for line, level in clean_answer(answer):
        if not line:
            continue
        if level:
            style = ParagraphStyle(
                f"bullet{level}", parent=STYLES["bullet"], leftIndent=INDENT * level
            )
            flowables.append(Paragraph(_text(line), style))
        else:
            flowables.append(_para(line))
    return flowables


def _table(rows: Mapping[str, str] | Sequence[Sequence[str]], header: bool = False) -> Table:
    """Return label and value rows (or rows of cells) as a table of escaped paragraphs."""
    data = list(rows.items()) if isinstance(rows, Mapping) else [list(row) for row in rows]
    cells = [[Paragraph(_text(str(cell)), STYLES["cell"]) for cell in row] for row in data]
    # Paragraph cells need set widths: a label column and the rest, or equal columns.
    columns = len(data[0])
    if header:
        widths = [CONTENT_WIDTH / columns] * columns
    else:
        widths = [LABEL_WIDTH, CONTENT_WIDTH - LABEL_WIDTH]
    table = Table(cells, hAlign="LEFT", colWidths=widths)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if header:
        style.append(("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED))
    table.setStyle(TableStyle(style))
    return table


def profile_rows(user: UserProfile, system: UnitSystem) -> dict[str, str]:
    """Return the profile in the chosen units, as the sidebar shows it."""
    values = (
        units.format_weight(user.weight_kg, system),
        units.format_height(user.height_cm, system),
        f"{user.age} years",
        profile.SEX_LABELS[user.sex],
        profile.ACTIVITY_LABELS[user.activity],
        profile.GOAL_LABELS[user.goal],
    )
    return dict(zip(PROFILE_LABELS, values, strict=True))


def _tdee_flowables(result: TdeeResult) -> list[Flowable]:
    """Return calculate_tdee's result as a table and its method."""
    rows = {
        "Resting energy (BMR)": f"{result.bmr_kcal:,} kcal/day",
        "Activity factor": f"{result.activity_factor:g}",
        "Daily energy needs (TDEE)": f"{result.tdee_kcal:,} kcal/day",
    }
    return [_table(rows), _para(result.method, "small")]


def _macro_cells(macro: Macro, system: UnitSystem) -> list[str]:
    """Return one macro's grams, share of the kcal and grams per body weight."""
    return [
        f"{macro.grams:,} g",
        f"{macro.percent}%",
        units.format_per_body_weight(macro.g_per_kg, system),
    ]


def _macro_flowables(result: registry.MacroToolResult, system: UnitSystem) -> list[Flowable]:
    """Return the daily targets as two tables, the message, the notes and the method."""
    targets = result.targets
    if targets.kcal_target is None or not (
        targets.protein and targets.carbohydrate and targets.fat
    ):
        return [_para(result.message, "small")]
    low, high = targets.kcal_range or (targets.kcal_target, targets.kcal_target)
    protein_low, protein_high = targets.protein_g_range or (0, 0)
    summary = {
        "Daily target": f"{targets.kcal_target:,} kcal",
        "Range for the goal": f"{low:,}-{high:,} kcal",
        "Daily energy needs": f"{result.energy_needs.tdee_kcal:,} kcal",
        "Protein range": f"{protein_low:,}-{protein_high:,} g",
    }
    per_body_weight = f"Per {units.weight_unit(system)} of body weight"
    macros = [
        ["Macro", "Per day", "Share of kcal", per_body_weight],
        ["Protein", *_macro_cells(targets.protein, system)],
        ["Carbohydrate", *_macro_cells(targets.carbohydrate, system)],
        ["Fat", *_macro_cells(targets.fat, system)],
    ]
    flowables: list[Flowable] = [_table(summary), Spacer(1, 2 * mm), _table(macros, header=True)]
    flowables.append(_para(result.message, "small"))
    flowables += [_para(note, "small") for note in targets.notes]
    flowables.append(_para(result.energy_needs.method, "small"))
    return flowables


def _food_flowables(result: FoodLookupResult) -> list[Flowable]:
    """Return a food lookup: the matched USDA food and its nutrients, or the suggestions."""
    if result.status != "found" or result.nutrients is None:
        flowables: list[Flowable] = [_para(result.message, "small")]
        if result.alternatives:
            flowables.append(_labelled("Did you mean:", "; ".join(result.alternatives), "small"))
        return flowables
    nutrients = result.nutrients
    fiber = "not reported" if nutrients.fiber_g is None else f"{nutrients.fiber_g:g} g"
    rows = {
        "USDA food": result.matched_name or "",
        "Amount": f"{result.grams:g} g",
        "Energy": f"{nutrients.kcal:,} kcal",
        "Protein": f"{nutrients.protein_g:g} g",
        "Carbohydrate": f"{nutrients.carbohydrate_g:g} g",
        "Fat": f"{nutrients.fat_g:g} g",
        "Fiber": fiber,
    }
    if result.alternatives:
        rows["Close alternatives"] = "; ".join(result.alternatives)
    return [_table(rows), _para(config.USDA_SOURCE_LINE, "small")]


def _tool_run_flowables(run: registry.ToolRun, system: UnitSystem) -> list[Flowable]:
    """Return one tool result under its heading, as the app's "Tool results" shows it."""
    heading = Paragraph(escape(TOOL_TITLES.get(run.name, TOOL_TITLES[None])), STYLES["h3"])
    result = run.result
    if run.status == "profile_needed":
        body = [_para(config.PROFILE_NEEDED_HINT, "small")]
    elif isinstance(result, TdeeResult) and result.status == "ok":
        body = _tdee_flowables(result)
    elif isinstance(result, registry.MacroToolResult) and result.status == "ok":
        body = _macro_flowables(result, system)
    elif isinstance(result, FoodLookupResult) and result.status != "invalid":
        body = _food_flowables(result)
    else:
        # A refused or failed call: the fixed message, never what the model sent.
        body = [_para(result.message, "small")]
    # The heading keeps with what follows it (keepWithNext in its style).
    return [heading, *body]


def _source_line(card: SourceCard) -> str:
    """Return a cited article as one line: labels, title, year, tier, licence and URL."""
    tier = config.EVIDENCE_TIER_LABELS.get(card.evidence_tier, config.UNKNOWN_TIER_LABEL)
    return (
        f"[{', '.join(card.labels)}] {card.title} ({card.year}). {tier}. {card.license}. {card.url}"
    )


def session_turns(messages: Sequence[Mapping]) -> tuple[tuple[str, TurnResult], ...]:
    """Return each question of the chat history with its result, in order."""
    turns = []
    question: str | None = None
    for message in messages:
        if message.get("role") == "user":
            question = message.get("text", "")
        elif message.get("role") == "assistant" and question is not None:
            turns.append((question, message["result"]))
            question = None
    return tuple(turns)


def _turn_flowables(
    number: int, question: str, result: TurnResult, system: UnitSystem
) -> list[Flowable]:
    """Return one turn: its question, then the answer with sources and tools, or its message."""
    flowables: list[Flowable] = [
        Paragraph(escape(TEXT["question"].format(number=number)), STYLES["h2"]),
        _para(question),
    ]
    if result.kind != "answer":
        flowables.append(_labelled(f"{KIND_LABELS[result.kind]}:", result.text))
        return flowables
    flowables.append(Paragraph(escape(TEXT["answer"]), STYLES["h3"]))
    flowables += _answer_flowables(result.text)
    if result.sources:
        flowables.append(Paragraph(escape(TEXT["sources"]), STYLES["h3"]))
        for card in result.sources:
            flowables.append(_para(_source_line(card), "small"))
            # A correction notice must be read with its article, as the app's card says.
            for correction in card.corrections:
                label = config.CORRECTION_LABELS[correction.relation]
                line = f"{label}: {correction.title}. {correction.url}"
                flowables.append(_para(line, "correction"))
    if result.tool_runs:
        flowables.append(Paragraph(escape(TEXT["tool_results"]), STYLES["h3"]))
        for run in result.tool_runs:
            flowables += _tool_run_flowables(run, system)
    return flowables


def _sentence(text: str) -> str:
    """Return text ending with a full stop."""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _article_credit(source: Source) -> str:
    """Return an approved article's full credit, as in ATTRIBUTION.md."""
    return (
        f"[{source.id}] {_sentence(', '.join(source.authors))} {_sentence(source.title)} "
        f"{source.journal}, {source.year}. DOI: {source.doi} ({source.url}). "
        f"{_sentence(source.copyright_notice)} Licensed under {source.license} "
        f"({source.license_url}). Changes: {CHANGES_MADE}. No endorsement by the authors or "
        "publisher is implied."
    )


def _card_credit(card: SourceCard) -> str:
    """Return a cited article's credit from its card, when the manifest could not be read."""
    return (
        f"[{card.source_id}] {_sentence(', '.join(card.authors))} {_sentence(card.title)} "
        f"{card.year}. {card.url}. Licensed under {card.license} ({card.license_url}). "
        f"Changes: {CHANGES_MADE}. No endorsement by the authors or publisher is implied."
    )


def _formula_credit(source: FormulaSource) -> str:
    """Return a formula source's full credit, as in ATTRIBUTION.md."""
    return (
        f"[{source.id}] {_sentence(', '.join(source.authors))} {_sentence(source.title)} "
        f"{source.journal}, {source.year}. DOI: {source.doi} (https://doi.org/{source.doi}). "
        f"{_sentence(source.copyright_notice)} Licensed under {source.license} "
        f"({source.license_url}). Used for {source.used_for}. Changes: {FORMULA_CHANGES_MADE}. "
        "No endorsement by the authors or publisher is implied."
    )


def _usda_credit() -> str:
    """Return the USDA credit, with the release date of the committed foods table."""
    try:
        release = read_usda_release()
    except FoodTableError:
        release = "unknown"
    citation = config.USDA_CITATION.format(release=release)
    return (
        f"USDA FoodData Central. {citation}. Licence: {config.USDA_LICENSE}, "
        f"{config.USDA_LICENSE_URL}. Changes: {config.USDA_CHANGES} No endorsement by USDA is "
        "implied."
    )


def _credits(
    turns: Sequence[tuple[str, TurnResult]],
    targets: registry.MacroToolResult | None,
    manifest: Mapping[str, Source],
) -> list[Flowable]:
    """Return the credits for every source the PDF uses: articles, formulas and USDA data."""
    runs = [run for _, result in turns for run in result.tool_runs]
    # The articles cited in the answers, then those behind the targets' ranges, each once.
    cited: dict[str, SourceCard | Source] = {}
    for _, result in turns:
        for card in result.sources:
            cited.setdefault(card.source_id, manifest.get(card.source_id) or card)
    energy_results = [
        run.result
        for run in runs
        if isinstance(run.result, registry.MacroToolResult) and run.status == "ok"
    ]
    if targets is not None:
        energy_results.append(targets)
    used_lines = {line for result in energy_results for line in result.targets.sources}
    for source in manifest.values():
        if any(source.url in line for line in used_lines):
            cited.setdefault(source.id, source)
    # A correction notice is credited with its article, and the article with its notice.
    for source in manifest.values():
        if source.corrects in cited:
            cited.setdefault(source.id, source)
        elif source.id in cited and source.corrects in manifest:
            cited.setdefault(source.corrects, manifest[source.corrects])
    uses_formulas = targets is not None or any(
        isinstance(run.result, TdeeResult | registry.MacroToolResult) and run.status == "ok"
        for run in runs
    )
    # A lookup shows USDA names or values, found or not; an invalid call reads no data.
    uses_usda = any(
        isinstance(run.result, FoodLookupResult) and run.status != "invalid" for run in runs
    )

    flowables: list[Flowable] = [
        Paragraph(escape(TEXT["credits"]), STYLES["h1"]),
        _para(TEXT["credits_intro"], "small"),
        _para(ARTICLE_CHANGES_NOTE, "small"),
    ]
    for item in cited.values():
        line = _article_credit(item) if isinstance(item, Source) else _card_credit(item)
        flowables.append(_para(line, "small"))
    if uses_formulas:
        flowables.append(Paragraph(escape(TEXT["formula_sources"]), STYLES["h3"]))
        flowables += [_para(_formula_credit(source), "small") for source in FORMULA_SOURCES]
    if uses_usda:
        flowables.append(Paragraph(escape(TEXT["food_data"]), STYLES["h3"]))
        flowables.append(_para(_usda_credit(), "small"))
    return flowables


def _footer(canvas, doc) -> None:
    """Draw the footer on every page: the app, the disclaimer and the page number."""
    canvas.saveState()
    canvas.setFont(FONT, SMALL_SIZE)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, MARGIN / 2, TEXT["footer"].format(page=doc.page))
    canvas.restoreState()


def _story(
    turns: Sequence[tuple[str, TurnResult]],
    user: UserProfile | None,
    system: UnitSystem,
    manifest: Mapping[str, Source],
    today: date,
) -> list[Flowable]:
    """Return the PDF's content in order: header, profile, targets, turns, credits."""
    story: list[Flowable] = [
        Paragraph(escape(TEXT["title"]), STYLES["title"]),
        _para(TEXT["created"].format(date=today.isoformat()), "small"),
        _labelled(TEXT["disclaimer"], config.DISCLAIMER),
        Paragraph(escape(TEXT["profile"]), STYLES["h1"]),
    ]
    targets = None
    if user is None:
        story += [_para(TEXT["no_profile"]), Paragraph(escape(TEXT["targets"]), STYLES["h1"])]
        story.append(_para(TEXT["no_targets"]))
    else:
        story.append(_table(profile_rows(user, system)))
        story.append(Paragraph(escape(TEXT["targets"]), STYLES["h1"]))
        story.append(_para(TEXT["targets_note"], "small"))
        result = registry.macro_targets(user)
        if isinstance(result, registry.MacroToolResult) and result.status == "ok":
            targets = result
            story += _macro_flowables(result, system)
        else:
            story.append(_para(result.message, "small"))
    story.append(Paragraph(escape(TEXT["turns"]), STYLES["h1"]))
    if not turns:
        story.append(_para(TEXT["no_turns"]))
    for number, (question, result) in enumerate(turns, start=1):
        story += _turn_flowables(number, question, result, system)
    story += _credits(turns, targets, manifest)
    return story


def build_summary_pdf(
    turns: Sequence[tuple[str, TurnResult]],
    user: UserProfile | None,
    system: UnitSystem,
    manifest: Mapping[str, Source] | None = None,
    today: date | None = None,
) -> bytes:
    """Build the session summary PDF in memory and return its bytes; never writes a file."""
    try:
        _register_fonts()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
            title=TEXT["title"],
            # No author or subject: the PDF's metadata says nothing about the user. Not
            # `invariant`: with a fixed date and ID the bytes, and so Streamlit's media URL (a hash
            # of them), would follow from the profile alone.
            author="",
            subject="",
        )
        story = _story(turns, user, system, manifest or {}, today or date.today())
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    except Exception:
        # `from None`: ReportLab's errors can quote the text being laid out (the user's question,
        # the answer), which must not reach a log or a traceback.
        raise PdfExportError("The session summary could not be built.") from None
    return buffer.getvalue()
