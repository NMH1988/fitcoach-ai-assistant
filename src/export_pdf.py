"""The session summary PDF (T5.2, AC-9): profile, targets, questions and answers, credits.

The PDF is built in memory with ReportLab and handed to the download button; nothing is written to
disk and nothing is logged (.claude/rules/security-privacy.md). ReportLab's `Paragraph` reads its
text as markup (`<b>`, `<font>`, `<link href=...>`), so every text that is not ours (the question,
the model's answer, source titles, USDA names, the food names the model sent to the meal plan
check) goes through `_text()`, which escapes it: no model text can add formatting or a link, and a
"<" cannot break the PDF. Answers are first unescaped (`html.unescape`), as the model may copy an
entity from the escaped prompt (T3.4), and their Markdown is turned into plain text by
`clean_answer()`. The PDF holds no link annotations at all: URLs are printed as text.

The PDF is written in the UI's language (T7.2): its headings, labels, table cells, numbers and
fixed messages come from src/i18n.py, as the app shows them. What the app keeps English stays
English here too: the tools' messages, notes and method lines, source titles, licence names, USDA
names, the credit lines (as in ATTRIBUTION.md) and the font's licence. Each answer stays in the
language it was written in.
"""

import html
import io
import re
from collections.abc import Mapping, Sequence
from datetime import date
from functools import cache, partial
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

from src import config, i18n, units
from src.chat import SourceCard, TurnResult
from src.i18n import Language
from src.profile import UserProfile
from src.rag.sources import (
    ARTICLE_CHANGES_NOTE,
    CHANGES_MADE,
    FORMULA_CHANGES_MADE,
    Source,
)
from src.tools import meal_plan, registry
from src.tools.energy import FORMULA_SOURCES, MACRO_SOURCES, FormulaSource, Macro, TdeeResult
from src.tools.food import FoodLookupResult, FoodTableError, read_usda_release
from src.tools.meal_plan import MealPlanResult
from src.units import UnitSystem

FONT = "DejaVuSans"
BOLD_FONT = "DejaVuSans-Bold"
# Page layout, in points.
MARGIN = 18 * mm
CONTENT_WIDTH = A4[0] - 2 * MARGIN
LABEL_WIDTH = 55 * mm
# ReportLab's default left and right padding of a table cell (6 points each).
CELL_PADDING = 12
# The narrowest a name column of a fitted table may get before its columns are made equal.
MIN_WIDE_COLUMN = 25 * mm
BODY_SIZE = 10
SMALL_SIZE = 8.5
LEADING = 1.35
INDENT = 5 * mm
MUTED = colors.HexColor("#4A5250")
RULE = colors.HexColor("#D8DEDB")
# Shown for a character the font has no glyph for (DejaVu Sans has this one).
MISSING = "�"
BMP_LAST = 0xFFFF

# The PDF's own headings and fixed labels live in src/i18n.py under "pdf.*", in English and German
# (T7.2); TEXT is their English version, unfilled, as the tests read it.
TEXT_KEYS = (
    "title",
    "created",
    "disclaimer",
    "profile",
    "no_profile",
    "age",
    "targets",
    "targets_note",
    "no_targets",
    "turns",
    "no_turns",
    "question",
    "answer",
    "sources",
    "tool_results",
    "credits",
    "credits_intro",
    "formula_sources",
    "food_data",
    "font",
    "font_credit",
    "footer",
)
TEXT = {key: i18n.TEXT["en"][f"pdf.{key}"] for key in TEXT_KEYS}
# The profile's rows: the sidebar's labels (src/i18n.py) and the profile field each shows.
PROFILE_ROWS = ("weight", "height", "age", "sex", "activity", "goal")

# Characters no PDF text should hold: C0 controls (but tab and newline) and DEL.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")
# Markdown that clean_answer() turns into plain text.
# A link, with an optional title: [text](url) or [text](<url> "title").
_LINK = re.compile(r"\[([^\[\]]*)\]\(\s*<?([^()\s<>]*)>?(?:\s+\"[^\"]*\")?\s*\)")
# A bare URL ends at a slot (NUL), so it cannot swallow a link set aside before it.
_BARE_URL = re.compile(r"https?://[^\s<>*`\x00]+")
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
# A code span, unless its first backtick is escaped (a backslash before it: plain text).
_CODE = re.compile(r"(?<!\\)(`+)(.+?)\1")
# A backslash before any ASCII punctuation escapes it (CommonMark).
_BACKSLASH = re.compile(r"\\([!-/:-@\[-`{-~])")


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
    "small_cell": _style("small_cell", fontSize=SMALL_SIZE),
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
    """Return text (escapes, links and URLs set aside) without emphasis marks, entities decoded."""
    text = _STRONG.sub(r"\1", text)
    text = _UNDERSCORE_STRONG.sub(r"\1", text)
    text = _STRIKE.sub(r"\1", text)
    text = _EMPHASIS.sub(lambda m: m.group(1) or m.group(2), text)
    # Entities last, as CommonMark reads them: never as Markdown ("&gt; 5 g" is not a quote).
    return html.unescape(text)


def _inline_markdown(text: str) -> str:
    """Return one line with its code spans, escapes, links, URLs and emphasis made plain."""
    # Code spans, then backslash escapes, then links, then bare URLs are set aside in NUL-delimited
    # slots before the emphasis rules, so code stays as written (also in a link's text),
    # "\*note\*" keeps its stars and a URL keeps its "__" (code review); the slots cannot clash
    # with the text, as _plain() drops NUL.
    kept: list[str] = []

    def keep(value: str) -> str:
        """Set a finished piece of text aside and return its slot."""
        kept.append(value)
        return f"\x00{len(kept) - 1}\x00"

    def plain_label(label: str) -> str:
        """Return a link's text with its URLs kept and its emphasis made plain."""
        return _emphasis_free(_BARE_URL.sub(lambda m: keep(html.unescape(m.group(0))), label))

    def link(match: re.Match[str]) -> str:
        """Return a Markdown link as its text and its URL in brackets, both plain."""
        label, url = plain_label(match.group(1)).strip(), html.unescape(match.group(2))
        if not url or restore(label) == restore(url):
            return label or url
        return f"{label} ({url})" if label else url

    def restore(value: str) -> str:
        """Put the kept pieces back, also those inside a kept piece (a link's escaped text)."""
        return _SLOT.sub(lambda m: restore(kept[int(m.group(1))]), value)

    # A code span is shown as written, entities included, as in the app.
    text = _CODE.sub(lambda m: keep(m.group(2)), text)
    text = _BACKSLASH.sub(lambda m: keep(m.group(1)), text)
    text = _LINK.sub(lambda m: keep(link(m)), text)
    text = _BARE_URL.sub(lambda m: keep(html.unescape(m.group(0))), text)
    return restore(_emphasis_free(text))


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


def _fitted_widths(rows: Sequence[Sequence[str]], wide: Sequence[int], size: float) -> list[float]:
    """Return column widths: each column fits its longest text, the wide ones share the rest."""
    # Measuring needs the font; registering it is cached, so this costs nothing in a build.
    _register_fonts()
    columns = len(rows[0])
    widths = [
        max(pdfmetrics.stringWidth(str(row[i]), FONT, size) for row in rows) + CELL_PADDING
        for i in range(columns)
    ]
    rest = CONTENT_WIDTH - sum(w for i, w in enumerate(widths) if i not in wide)
    if rest < MIN_WIDE_COLUMN * len(wide):
        # Values too long to fit side by side: equal columns, which wrap.
        return [CONTENT_WIDTH / columns] * columns
    return [rest / len(wide) if i in wide else w for i, w in enumerate(widths)]


def _table(
    rows: Mapping[str, str] | Sequence[Sequence[str]],
    header: bool = False,
    widths: Sequence[float] | None = None,
    cell_style: str = "cell",
) -> Table:
    """Return label and value rows (or rows of cells) as a table of escaped paragraphs."""
    data = list(rows.items()) if isinstance(rows, Mapping) else [list(row) for row in rows]
    cells = [[Paragraph(_text(str(cell)), STYLES[cell_style]) for cell in row] for row in data]
    # Paragraph cells need set widths: given, a label column and the rest, or equal columns.
    columns = len(data[0])
    if widths is not None:
        widths = list(widths)
    elif header:
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


def profile_rows(user: UserProfile, system: UnitSystem, lang: Language = "en") -> dict[str, str]:
    """Return the profile in the chosen units and language, as the sidebar shows it."""
    values = (
        units.format_weight(user.weight_kg, system, lang),
        units.format_height(user.height_cm, system),
        i18n.t("pdf.age", lang, age=user.age),
        i18n.t(f"sex.{user.sex}", lang),
        i18n.t(f"activity.{user.activity}", lang),
        i18n.t(f"goal.{user.goal}", lang),
    )
    labels = (i18n.t(f"profile.{row}", lang) for row in PROFILE_ROWS)
    return dict(zip(labels, values, strict=True))


def _kcal(value: int, lang: Language, unit: str = "kcal") -> str:
    """Return a kcal number with the language's thousands mark and a unit, e.g. "2.759 kcal"."""
    return f"{i18n.number(value, lang)} {unit}"


def _tdee_flowables(result: TdeeResult, lang: Language = "en") -> list[Flowable]:
    """Return calculate_tdee's result as a table and its method (the method stays English)."""
    per_day = i18n.t("unit.kcal_per_day", lang)
    rows = {
        i18n.t("tdee.bmr", lang): _kcal(result.bmr_kcal, lang, per_day),
        i18n.t("tdee.factor", lang): i18n.plain(result.activity_factor, lang),
        i18n.t("tdee.tdee", lang): _kcal(result.tdee_kcal, lang, per_day),
    }
    return [_table(rows), _para(result.method, "small")]


def _macro_cells(
    macro: Macro, weight_kg: float, system: UnitSystem, lang: Language = "en"
) -> list[str]:
    """Return one macro's grams, share of the kcal and grams per body weight."""
    # From the grams and the weight, rounded once, as the app shows them (T4.7): Macro.g_per_kg
    # is already rounded to 0.1, and converting it again can be off by 0.01-0.03 g/lb.
    return [
        f"{i18n.number(macro.grams, lang)} g",
        i18n.percent(macro.percent, lang),
        units.format_grams_per_body_weight(macro.grams, weight_kg, system, lang),
    ]


def _macro_flowables(
    result: registry.MacroToolResult, system: UnitSystem, lang: Language = "en"
) -> list[Flowable]:
    """Return the daily targets as two tables, the message, the notes and the method."""
    targets = result.targets
    # Grams per body weight need the weight the targets are for (T4.7); without it, as without
    # the targets, only the message is shown.
    weight = targets.weight_kg
    if (
        targets.kcal_target is None
        or not (targets.protein and targets.carbohydrate and targets.fat)
        or not weight
    ):
        return [_para(result.message, "small")]
    low, high = targets.kcal_range or (targets.kcal_target, targets.kcal_target)
    protein_low, protein_high = targets.protein_g_range or (0, 0)
    summary = {
        i18n.t("targets.daily_target", lang): _kcal(targets.kcal_target, lang),
        i18n.t("macros.range", lang): f"{i18n.number(low, lang)}-{_kcal(high, lang)}",
        i18n.t("macros.needs", lang): _kcal(result.energy_needs.tdee_kcal, lang),
        i18n.t("macros.protein_range", lang): (
            f"{i18n.number(protein_low, lang)}-{i18n.number(protein_high, lang)} g"
        ),
    }
    per_body_weight = i18n.t("macros.per_weight", lang, unit=units.weight_unit(system))
    header = [i18n.t(f"macros.{key}", lang) for key in ("macro", "per_day", "share")]
    macros = [[*header, per_body_weight]]
    for name in ("protein", "carbohydrate", "fat"):
        macro = getattr(targets, name)
        macros.append([i18n.t(f"macro.{name}", lang), *_macro_cells(macro, weight, system, lang)])
    flowables: list[Flowable] = [_table(summary), Spacer(1, 2 * mm), _table(macros, header=True)]
    # The tool's message, notes and method stay English, as in the app (owner's choice in T7.1).
    flowables.append(_para(result.message, "small"))
    flowables += [_para(note, "small") for note in targets.notes]
    flowables.append(_para(result.energy_needs.method, "small"))
    return flowables


def _grams(value: float, lang: Language) -> str:
    """Return grams with the language's decimal mark, e.g. "20.2 g" or "20,2 g"."""
    return f"{i18n.plain(value, lang)} g"


def _food_flowables(result: FoodLookupResult, lang: Language = "en") -> list[Flowable]:
    """Return a food lookup: the matched USDA food and its nutrients, or the suggestions."""
    did_you_mean = f"{i18n.t('food.did_you_mean', lang)}:"
    if result.status != "found" or result.nutrients is None:
        flowables: list[Flowable] = [_para(result.message, "small")]
        if result.alternatives:
            flowables.append(_labelled(did_you_mean, "; ".join(result.alternatives), "small"))
        return flowables
    nutrients = result.nutrients
    fiber = (
        i18n.t("food.not_reported", lang)
        if nutrients.fiber_g is None
        else _grams(nutrients.fiber_g, lang)
    )
    rows = {
        i18n.t("food.usda_food", lang): result.matched_name or "",
        i18n.t("food.amount", lang): _grams(result.grams or 0, lang),
        i18n.t("nutrient.energy", lang): _kcal(nutrients.kcal, lang),
        i18n.t("nutrient.protein", lang): _grams(nutrients.protein_g, lang),
        i18n.t("nutrient.carbohydrate", lang): _grams(nutrients.carbohydrate_g, lang),
        i18n.t("nutrient.fat", lang): _grams(nutrients.fat_g, lang),
        i18n.t("nutrient.fiber", lang): fiber,
    }
    if result.alternatives:
        rows[i18n.t("food.close_alternatives", lang)] = "; ".join(result.alternatives)
    return [_table(rows), _para(i18n.t("usda.source_line", lang), "small")]


def _meal_plan_flowables(result: MealPlanResult, lang: Language = "en") -> list[Flowable]:
    """Return a meal plan check: the foods, the plan against the targets, message and notes."""
    # The same cells as the app's tables (src/tools/meal_plan.py); _table() escapes each one, so
    # a USDA name or the name the model asked for cannot add markup (T4.5).
    foods = [
        list(meal_plan.food_columns(lang)),
        *(meal_plan.food_row(item, lang) for item in result.items),
    ]
    # Eight columns: small cells, the values as wide as their longest text and the two name
    # columns sharing the rest, so no header or value breaks mid-word (code review, round 2).
    widths = _fitted_widths(foods, wide=(0, 1), size=SMALL_SIZE)
    flowables: list[Flowable] = [_table(foods, header=True, widths=widths, cell_style="small_cell")]
    # The app's "Other close USDA names" column, as lines under the table.
    for item in result.items:
        if item.alternatives:
            key = "food.did_you_mean" if item.status == "not_found" else "food.close_alternatives"
            names = f"{item.requested}: {'; '.join(item.alternatives)}"
            flowables.append(_labelled(f"{i18n.t(key, lang)}:", names, "small"))
    comparison = meal_plan.comparison_rows(result, lang)
    if comparison:
        rows = [list(meal_plan.comparison_columns(lang)), *comparison]
        flowables += [Spacer(1, 2 * mm), _table(rows, header=True)]
    flowables.append(_para(result.message, "small"))
    flowables += [_para(note, "small") for note in result.notes]
    flowables.append(_para(i18n.t("meal.source_line", lang), "small"))
    return flowables


def _tool_title(name: str | None, lang: Language) -> str:
    """Return a tool's heading as the app's "Tool results" names it; an unknown tool its own."""
    key = f"tool.title.{name}"
    return i18n.t(key if key in i18n.TEXT[lang] else "tool.title.none", lang)


def _tool_run_flowables(
    run: registry.ToolRun, system: UnitSystem, lang: Language = "en"
) -> list[Flowable]:
    """Return one tool result under its heading, as the app's "Tool results" shows it."""
    heading = Paragraph(escape(_tool_title(run.name, lang)), STYLES["h3"])
    result = run.result
    if run.status == "profile_needed":
        body = [_para(i18n.t("tool.profile_needed", lang), "small")]
    elif isinstance(result, TdeeResult) and result.status == "ok":
        body = _tdee_flowables(result, lang)
    elif isinstance(result, registry.MacroToolResult) and result.status == "ok":
        body = _macro_flowables(result, system, lang)
    elif isinstance(result, FoodLookupResult) and result.status != "invalid":
        body = _food_flowables(result, lang)
    elif isinstance(result, MealPlanResult) and result.status != "invalid":
        body = _meal_plan_flowables(result, lang)
    else:
        # A refused or failed call: the fixed message, never what the model sent.
        body = [_para(result.message, "small")]
    # The heading keeps with what follows it (keepWithNext in its style).
    return [heading, *body]


def _source_line(card: SourceCard, lang: Language = "en") -> str:
    """Return a cited article as one line: labels, title, year, tier, licence and URL."""
    tier_key = f"tier.{card.evidence_tier}"
    tier = i18n.t(tier_key if tier_key in i18n.TEXT[lang] else "tier.unknown", lang)
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


def fixed_text(result: TurnResult, lang: Language = "en") -> str:
    """Return a turn's fixed message in the language, as the app shows it; else its own text."""
    # An unknown key falls back to the English text, as in the app.
    if result.code is not None and result.code in i18n.TEXT[lang]:
        return i18n.t(result.code, lang, **result.params)
    return result.text


def _turn_flowables(
    number: int, question: str, result: TurnResult, system: UnitSystem, lang: Language = "en"
) -> list[Flowable]:
    """Return one turn: its question, then the answer with sources and tools, or its message."""
    flowables: list[Flowable] = [
        Paragraph(escape(i18n.t("pdf.question", lang, number=number)), STYLES["h2"]),
        _para(question),
    ]
    if result.kind != "answer":
        # The label the app's status box ends with for this kind of turn.
        label = f"{i18n.t(f'status.{result.kind}', lang)}:"
        flowables.append(_labelled(label, fixed_text(result, lang)))
        return flowables
    flowables.append(Paragraph(escape(i18n.t("pdf.answer", lang)), STYLES["h3"]))
    # The model's answer, in the language it was written in.
    flowables += _answer_flowables(result.text)
    if result.sources:
        flowables.append(Paragraph(escape(i18n.t("pdf.sources", lang)), STYLES["h3"]))
        for card in result.sources:
            flowables.append(_para(_source_line(card, lang), "small"))
            # A correction notice must be read with its article, as the app's card says.
            for correction in card.corrections:
                label = i18n.t(f"correction.{correction.relation}", lang)
                line = f"{label}: {correction.title}. {correction.url}"
                flowables.append(_para(line, "correction"))
    if result.tool_runs:
        flowables.append(Paragraph(escape(i18n.t("pdf.tool_results", lang)), STYLES["h3"]))
        for run in result.tool_runs:
            flowables += _tool_run_flowables(run, system, lang)
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
    lang: Language = "en",
) -> list[Flowable]:
    """Return the credits for every source the PDF uses: articles, formulas and USDA data."""
    # The headings and the intro follow the language; each credit line stays English, word for
    # word as in ATTRIBUTION.md, and so does the font's licence.
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
    # A meal plan check compares with the macro targets, so it uses their sources too (T4.5). Its
    # result does not carry the targets, so this reads MACRO_SOURCES, the default of
    # MacroTargetsResult.sources; if a target ever lists other sources, credit those here too.
    meal_plans = [
        run.result for run in runs if isinstance(run.result, MealPlanResult) and run.status == "ok"
    ]
    if meal_plans:
        used_lines |= set(MACRO_SOURCES)
    for source in manifest.values():
        if any(source.url in line for line in used_lines):
            cited.setdefault(source.id, source)
    # A correction notice is credited with its article, and the article with its notice.
    for source in manifest.values():
        if source.corrects in cited:
            cited.setdefault(source.id, source)
        elif source.id in cited and source.corrects in manifest:
            cited.setdefault(source.corrects, manifest[source.corrects])
    uses_formulas = (
        targets is not None
        or bool(meal_plans)
        or any(
            isinstance(run.result, TdeeResult | registry.MacroToolResult) and run.status == "ok"
            for run in runs
        )
    )
    # A lookup or a meal plan shows USDA names or values, found or not; an invalid call reads none.
    uses_usda = any(
        isinstance(run.result, FoodLookupResult | MealPlanResult) and run.status != "invalid"
        for run in runs
    )

    flowables: list[Flowable] = [
        Paragraph(escape(i18n.t("pdf.credits", lang)), STYLES["h1"]),
        _para(i18n.t("pdf.credits_intro", lang), "small"),
        _para(ARTICLE_CHANGES_NOTE, "small"),
    ]
    for item in cited.values():
        line = _article_credit(item) if isinstance(item, Source) else _card_credit(item)
        flowables.append(_para(line, "small"))
    if uses_formulas:
        flowables.append(Paragraph(escape(i18n.t("pdf.formula_sources", lang)), STYLES["h3"]))
        flowables += [_para(_formula_credit(source), "small") for source in FORMULA_SOURCES]
    if uses_usda:
        flowables.append(Paragraph(escape(i18n.t("pdf.food_data", lang)), STYLES["h3"]))
        flowables.append(_para(_usda_credit(), "small"))
    # Every PDF embeds the font, so its credit is always there.
    flowables.append(Paragraph(escape(i18n.t("pdf.font", lang)), STYLES["h3"]))
    flowables.append(_para(i18n.t("pdf.font_credit", lang), "small"))
    flowables += [_para(paragraph, "small") for paragraph in font_licence_paragraphs()]
    return flowables


@cache
def font_licence_paragraphs() -> tuple[str, ...]:
    """Return the fonts' licence (the part for DejaVu Sans), word for word, one paragraph each."""
    # Read from the LICENSE committed with the fonts, so the PDF can never drift from it. A
    # paragraph's wrapped lines are joined with spaces; the "-----" lines under titles are dropped.
    text = config.PDF_FONT_LICENSE_PATH.read_text(encoding="utf-8")
    part = text.split(config.PDF_FONT_LICENSE_END, 1)[0]
    paragraphs = []
    for block in re.split(r"\n\s*\n", part.replace("\r\n", "\n")):
        lines = [line.strip() for line in block.split("\n") if not re.fullmatch(r"\s*-+\s*", line)]
        if any(lines):
            paragraphs.append(" ".join(line for line in lines if line))
    return tuple(paragraphs)


def _footer(canvas, doc, lang: Language = "en") -> None:
    """Draw the footer on every page: the app, the disclaimer and the page number."""
    canvas.saveState()
    canvas.setFont(FONT, SMALL_SIZE)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, MARGIN / 2, i18n.t("pdf.footer", lang, page=doc.page))
    canvas.restoreState()


def format_date(day: date, lang: Language = "en") -> str:
    """Return a date as the language writes it: 2026-10-21 or 21.10.2026."""
    return day.strftime("%d.%m.%Y") if lang == "de" else day.isoformat()


def _heading(key: str, lang: Language, style: str = "h1") -> Paragraph:
    """Return one of the PDF's own headings in the language."""
    return Paragraph(escape(i18n.t(f"pdf.{key}", lang)), STYLES[style])


def _story(
    turns: Sequence[tuple[str, TurnResult]],
    user: UserProfile | None,
    system: UnitSystem,
    manifest: Mapping[str, Source],
    today: date,
    lang: Language = "en",
) -> list[Flowable]:
    """Return the PDF's content in order: header, profile, targets, turns, credits."""
    story: list[Flowable] = [
        _heading("title", lang, "title"),
        _para(i18n.t("pdf.created", lang, date=format_date(today, lang)), "small"),
        _labelled(i18n.t("pdf.disclaimer", lang), i18n.t("app.disclaimer", lang)),
        _heading("profile", lang),
    ]
    targets = None
    if user is None:
        story += [_para(i18n.t("pdf.no_profile", lang)), _heading("targets", lang)]
        story.append(_para(i18n.t("pdf.no_targets", lang)))
    else:
        story.append(_table(profile_rows(user, system, lang)))
        story.append(_heading("targets", lang))
        story.append(_para(i18n.t("pdf.targets_note", lang), "small"))
        result = registry.macro_targets(user)
        if isinstance(result, registry.MacroToolResult) and result.status == "ok":
            targets = result
            story += _macro_flowables(result, system, lang)
        else:
            story.append(_para(result.message, "small"))
    story.append(_heading("turns", lang))
    if not turns:
        story.append(_para(i18n.t("pdf.no_turns", lang)))
    for number, (question, result) in enumerate(turns, start=1):
        story += _turn_flowables(number, question, result, system, lang)
    story += _credits(turns, targets, manifest, lang)
    return story


def build_summary_pdf(
    turns: Sequence[tuple[str, TurnResult]],
    user: UserProfile | None,
    system: UnitSystem,
    manifest: Mapping[str, Source] | None = None,
    today: date | None = None,
    lang: Language = "en",
) -> bytes:
    """Build the session summary PDF in memory, in the UI's language; never writes a file."""
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
            title=i18n.t("pdf.title", lang),
            # No author or subject: the PDF's metadata says nothing about the user. Not
            # `invariant`: with a fixed date and ID the bytes, and so Streamlit's media URL (a hash
            # of them), would follow from the profile alone. reportlab also fixes them when the
            # SOURCE_DATE_EPOCH environment variable is set: never set it where the app runs.
            author="",
            subject="",
        )
        story = _story(turns, user, system, manifest or {}, today or date.today(), lang)
        footer = partial(_footer, lang=lang)
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    except Exception:
        # `from None`: ReportLab's errors can quote the text being laid out (the user's question,
        # the answer), which must not reach a log or a traceback.
        raise PdfExportError("The session summary could not be built.") from None
    return buffer.getvalue()
