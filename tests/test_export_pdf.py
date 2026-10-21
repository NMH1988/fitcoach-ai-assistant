"""Tests for src/export_pdf.py: the session summary PDF's content, escaping and no files (T5.2)."""

import builtins
import dataclasses
import io
import os
import re
from datetime import date

import pytest
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics

from src import chat, config, export_pdf
from src.rag.sources import ARTICLE_CHANGES_NOTE, Source
from src.tools import registry
from src.tools.energy import FORMULA_SOURCES, MACRO_SOURCES, TDEE_METHOD
from src.tools.food import lookup_food_nutrition
from src.tools.registry import (
    FOOD_TOOL,
    MACRO_TOOL,
    MEAL_PLAN_TOOL,
    TDEE_TOOL,
    ToolNotice,
    ToolRun,
)
from tests.fakes import FOODS, HOSTILE_FOOD_NAME, PROFILE, pdf_text

TODAY = date(2026, 10, 20)
MANIFEST = chat.manifest_by_id()
# Approved sources whose titles hold characters outside Latin-1: "β" (#4) and U+2010 "‐" (#16).
HMB, PROTEIN_SUPPLEMENTS = MANIFEST["4"], MANIFEST["16"]


def _card(source: Source, *labels: str) -> chat.SourceCard:
    """Return the source card the chat would show for a cited approved article."""
    return chat.SourceCard(
        source_id=source.id,
        title=source.title,
        authors=tuple(source.authors),
        year=source.year,
        evidence_tier=source.evidence_tier,
        license=source.license,
        license_url=source.license_url,
        url=source.url,
        journal=source.journal,
        labels=labels or ("S1",),
    )


def _answer(text: str, *cards: chat.SourceCard, runs: tuple[ToolRun, ...] = ()) -> chat.TurnResult:
    """Return an answered turn with its text, cited sources and tool runs."""
    return chat.TurnResult("answer", text, cards, tool_runs=runs)


def _pdf(turns=(), user=PROFILE, system="metric", manifest=MANIFEST) -> bytes:
    """Build the summary PDF for these turns and profile, dated TODAY."""
    return export_pdf.build_summary_pdf(list(turns), user, system, manifest, TODAY)


def _annotations(data: bytes) -> list:
    """Return every annotation (links included) on the PDF's pages."""
    reader = PdfReader(io.BytesIO(data))
    return [annot for page in reader.pages for annot in (page.get("/Annots") or [])]


def _run(name: str, args: dict | None = None, profile=PROFILE) -> ToolRun:
    """Run one tool as the model would call it, with the fixture foods."""
    tools = registry.build_tools(profile, FOODS)
    call = {"name": name, "args": args or {}, "id": "call-1", "type": "tool_call"}
    return registry.run_tool_call(tools, call)[1]


# --- The PDF's content: profile, targets, turns, disclaimer, credits (AC 1) -----------------------


def test_the_pdf_has_the_title_date_and_disclaimer():
    """The first page names the app, the day it was made and the full disclaimer."""
    text = pdf_text(_pdf())
    assert export_pdf.TEXT["title"] in text
    assert "Created on 2026-10-20" in text
    assert f"Not medical advice. {config.DISCLAIMER}" in text


def test_every_page_has_the_disclaimer_in_its_footer():
    """Each page's footer says "Not medical advice" and its page number."""
    turns = [(f"Question {n}?", _answer("A long answer. " * 120)) for n in range(4)]
    reader = PdfReader(io.BytesIO(_pdf(turns)))
    assert len(reader.pages) > 1
    for number, page in enumerate(reader.pages, start=1):
        assert f"Not medical advice · Page {number}" in page.extract_text()


@pytest.mark.parametrize(
    ("system", "weight", "height"),
    [("metric", "80 kg", "180 cm"), ("imperial", "176.4 lb", "5 ft 11 in")],
)
def test_the_profile_is_shown_in_the_chosen_units(system, weight, height):
    """Weight and height follow the unit system; age, sex, activity and goal are labelled."""
    text = pdf_text(_pdf(system=system))
    for expected in (
        f"Weight {weight}",
        f"Height {height}",
        "Age 30 years",
        "Sex Male",
        "Activity Moderate · exercise 4-5 times a week",
        "Goal Build muscle",
    ):
        assert expected in text


def test_without_a_profile_the_pdf_says_so_and_has_no_targets():
    """No profile: the PDF says no details were added and invites the user to add them."""
    text = pdf_text(_pdf(user=None))
    assert export_pdf.TEXT["no_profile"] in text
    assert export_pdf.TEXT["no_targets"] in text
    assert "Daily target" not in text


@pytest.mark.parametrize(
    ("system", "per_body_weight"),
    # 418 g at 80 kg is 2.37 g/lb, rounded once (T4.7); from the rounded 5.2 g/kg it was 2.36.
    [("metric", ["1.9 g/kg", "5.2 g/kg", "1.1 g/kg"]), ("imperial", ["0.86 g/lb", "2.37 g/lb"])],
)
def test_the_targets_come_from_the_profile_in_the_chosen_units(system, per_body_weight):
    """The targets are the macro tool's result for the profile, per kg or per lb of body weight."""
    targets = registry.macro_targets(PROFILE).targets
    text = pdf_text(_pdf(system=system))
    assert export_pdf.TEXT["targets_note"] in text
    assert f"Daily target {targets.kcal_target:,} kcal" in text
    assert "Daily energy needs 2,759 kcal" in text
    assert f"Protein {targets.protein.grams:,} g {targets.protein.percent}%" in text
    assert f"Per {'kg' if system == 'metric' else 'lb'} of body weight" in text
    for value in per_body_weight:
        assert value in text
    assert targets.message in text
    assert TDEE_METHOD in text


def test_the_targets_notes_are_shown():
    """A target raised to the calorie floor carries its notes, as in the app."""
    small = PROFILE.model_copy(
        update={"weight_kg": 40.0, "height_cm": 150.0, "age": 80, "sex": "female"}
    )
    small = small.model_copy(update={"activity": "sedentary", "goal": "lose_fat"})
    targets = registry.macro_targets(small).targets
    assert targets.floor_applied
    text = pdf_text(_pdf(user=small))
    for note in targets.notes:
        assert " ".join(note.split()) in text


def test_each_question_and_answer_is_in_the_pdf_with_its_sources():
    """Every turn shows its number, question and answer; a cited source shows its card line."""
    turns = [
        ("How much protein per meal?", _answer("Spread it over four meals [S1].", _card(HMB))),
        ("And after training?", _answer("Within a few hours [S1, S2].", _card(MANIFEST["8"]))),
    ]
    text = pdf_text(_pdf(turns))
    assert "Question 1 How much protein per meal? Answer Spread it over four meals [S1]." in text
    assert "Question 2 And after training? Answer Within a few hours [S1, S2]." in text
    assert f"[S1] {HMB.title} ({HMB.year}). ISSN position stand. CC BY 4.0. {HMB.url}" in text


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("no_sources", config.NO_SOURCES_MESSAGE),
        ("rejected", "Your question could not be accepted."),
        ("guardrail", "This assistant does not advise on that."),
        ("error", "The answer could not be finished. Please try again."),
    ],
)
def test_a_turn_without_an_answer_shows_its_question_and_message(kind, message):
    """Every kind of turn is in the PDF, as in the chat, with its label and fixed message."""
    turns = [("Some question?", chat.TurnResult(kind, message))]
    text = pdf_text(_pdf(turns))
    expected = f"Question 1 Some question? {config.STATUS_LABELS[kind]}: {message}"
    assert " ".join(expected.split()) in text


def test_without_turns_the_pdf_says_no_question_was_asked():
    """A session with no question says so under "Questions and answers"."""
    assert export_pdf.TEXT["no_turns"] in pdf_text(_pdf())


def test_the_tool_results_follow_their_answer():
    """Each tool result of a turn is shown under the answer, as in "Tool results"."""
    runs = (
        _run(TDEE_TOOL),
        _run(MACRO_TOOL),
        _run(FOOD_TOOL, {"food": "rolled oats", "grams": 80}),
    )
    text = pdf_text(_pdf([("Plan my day?", _answer("Here are your numbers.", runs=runs))]))
    answer_part = text.split("Plan my day?", 1)[1]
    assert "Tool results Daily energy needs Resting energy (BMR) 1,780 kcal/day" in answer_part
    assert "Daily energy needs (TDEE) 2,759 kcal/day" in answer_part
    assert "Daily targets Daily target" in answer_part
    oats = "Food lookup USDA food Oats, whole grain, rolled, old fashioned Amount 80 g"
    assert oats in answer_part
    assert "Fiber 8 g" in answer_part
    assert config.USDA_SOURCE_LINE in answer_part


def test_a_food_without_fiber_says_not_reported():
    """A missing fiber value reads "not reported", never 0."""
    run = _run(FOOD_TOOL, {"food": "chicken breast", "grams": 100})
    assert run.result.nutrients.fiber_g is None
    assert "Fiber not reported" in pdf_text(_pdf([("Chicken?", _answer("Lean.", runs=(run,)))]))


def test_tool_results_without_values_show_their_message():
    """Profile needed, a refused call and a food not found show their fixed text."""
    not_found = registry.ToolRun(
        FOOD_TOOL, "not_found", lookup_food_nutrition("zzzz qqqq", 100, FOODS)
    )
    runs = (
        _run(TDEE_TOOL, profile=None),
        registry.refused_call("call-2", config.UNKNOWN_TOOL_MESSAGE)[1],
        not_found,
    )
    text = pdf_text(_pdf([("Numbers?", _answer("See below.", runs=runs))], user=None))
    assert f"Daily energy needs {config.PROFILE_NEEDED_HINT}" in text
    assert f"Tool call not run {config.UNKNOWN_TOOL_MESSAGE}" in text
    assert " ".join(not_found.result.message.split()) in text


def test_macro_targets_without_their_weight_show_only_the_message():
    """Targets with no weight_kg cannot give grams per body weight, so only the message shows."""
    result = registry.macro_targets(PROFILE)
    weightless = result.model_copy(
        update={"targets": result.targets.model_copy(update={"weight_kg": None})}
    )
    run = registry.ToolRun(MACRO_TOOL, "ok", weightless)
    text = pdf_text(_pdf([("Targets?", _answer("See below.", runs=(run,)))], user=None))
    assert " ".join(result.message.split()) in text
    assert "of body weight" not in text and "Share of kcal" not in text


def test_the_credits_name_every_cited_article_in_full():
    """A cited article is credited with all authors, its copyright notice, licence and DOI."""
    text = pdf_text(_pdf([("HMB?", _answer("It may help [S1].", _card(HMB)))], user=None))
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert ARTICLE_CHANGES_NOTE in credits
    for part in (
        ", ".join(HMB.authors),
        HMB.title,
        f"DOI: {HMB.doi} ({HMB.url})",
        HMB.copyright_notice,
        f"Licensed under {HMB.license} ({HMB.license_url})",
        "No endorsement by the authors or publisher is implied.",
        "ATTRIBUTION.md",
    ):
        assert " ".join(part.split()) in credits


def test_the_credits_name_the_sources_behind_the_targets_and_the_formulas():
    """With targets, the articles behind their ranges and the formula sources are credited."""
    credits = pdf_text(_pdf()).split(export_pdf.TEXT["credits"], 1)[1]
    for source_id in ("1", "9", "11", "12"):
        assert f"[{source_id}] " in credits
        assert MANIFEST[source_id].doi in credits
    for formula in FORMULA_SOURCES:
        assert f"[{formula.id}] " in credits
        assert " ".join(formula.used_for.split()) in credits


def test_the_credits_name_usda_only_when_a_food_was_looked_up():
    """The USDA credit, with its CC0 licence, is there only after a food lookup."""
    assert config.USDA_LICENSE not in pdf_text(_pdf(user=None))
    run = _run(FOOD_TOOL, {"food": "rolled oats", "grams": 80})
    text = pdf_text(_pdf([("Oats?", _answer("See below.", runs=(run,)))], user=None))
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert "FoodData Central: Foundation Foods, release" in credits
    assert f"Licence: {config.USDA_LICENSE}" in credits
    assert "No endorsement by USDA is implied." in credits


def test_without_a_profile_or_tools_no_formula_source_is_credited():
    """No targets and no energy tool: the formula sources are not listed."""
    credits = pdf_text(_pdf(user=None)).split(export_pdf.TEXT["credits"], 1)[1]
    assert export_pdf.TEXT["formula_sources"] not in credits


def test_a_cited_article_missing_from_the_manifest_is_credited_from_its_card():
    """If the manifest could not be read, the card's authors, title, licence and URL credit it."""
    text = pdf_text(_pdf([("HMB?", _answer("Yes [S1].", _card(HMB)))], user=None, manifest={}))
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert f"[{HMB.id}] " in credits
    assert HMB.url in credits
    assert f"Licensed under {HMB.license}" in credits


def test_session_turns_pairs_each_question_with_its_result():
    """The chat history becomes (question, result) pairs; a question still running is left out."""
    first, second = _answer("One."), chat.TurnResult("rejected", "No.")
    messages = [
        {"role": "user", "text": "Q1"},
        {"role": "assistant", "result": first},
        {"role": "user", "text": "Q2"},
        {"role": "assistant", "result": second},
        {"role": "user", "text": "Q3"},
    ]
    assert export_pdf.session_turns(messages) == (("Q1", first), ("Q2", second))


# --- Non-Latin characters (AC 3) ------------------------------------------------------------------


def test_non_latin_characters_in_source_titles_read_back_exactly():
    """Titles with "β" and U+2010 read back as written, in the answer and the credits."""
    assert "β" in HMB.title and "‐" in PROTEIN_SUPPLEMENTS.title
    turns = [("HMB?", _answer("Yes [S1, S2].", _card(HMB), _card(PROTEIN_SUPPLEMENTS, "S2")))]
    text = pdf_text(_pdf(turns))
    assert text.count(HMB.title) == 2
    assert text.count(PROTEIN_SUPPLEMENTS.title) == 2


def test_characters_the_font_lacks_do_not_break_the_pdf():
    """Emoji, other scripts and control characters give a PDF; emoji become U+FFFD."""
    answer = "Great 💪 choice \x00\x07 for 漢字 [S1].\r\nNext line \U0001f600"
    text = pdf_text(_pdf([("Ok?\x1b", _answer(answer, _card(HMB)))]))
    assert "Great � choice for" in text
    assert "Next line �" in text
    assert "\x00" not in text and "\x1b" not in text


# --- Unescaped, then escaped for ReportLab: no markup, no links (AC 4) ----------------------------


def test_an_entity_the_model_copied_reads_back_as_the_character():
    """An answer holding "p &lt; 0.05" reads back "p < 0.05" (and &gt;, &amp; likewise)."""
    text = pdf_text(
        _pdf([("Stats?", _answer("Significant at p &lt; 0.05, n &gt; 10 &amp; more."))])
    )
    assert "Significant at p < 0.05, n > 10 & more." in text
    assert "&lt;" not in text


@pytest.mark.parametrize(
    "markup",
    [
        "<b>x</b>",
        '<link href="https://example.com">x</link>',
        '<a href="https://example.com">x</a>',
        '<font color="red" size="40">x</font>',
        "&lt;b&gt;x&lt;/b&gt;",
        "<para>broken <i>",
    ],
)
def test_markup_in_an_answer_reads_back_as_literal_text_with_no_link(markup):
    """ReportLab markup in model text is shown as written: no formatting, no link annotation."""
    data = _pdf([("Markup?", _answer(f"Before {markup} after."))])
    literal = markup.replace("&lt;", "<").replace("&gt;", ">")
    assert f"Before {literal} after." in pdf_text(data)
    assert _annotations(data) == []


def test_markup_in_a_question_a_title_and_a_usda_name_stays_text():
    """The user's question, a source title and a USDA name are escaped like the answer."""
    title_card = chat.SourceCard(
        "1", '<link href="https://example.com">T</link>', ("A",), 2020, 1, "CC BY 4.0",
        "https://creativecommons.org/licenses/by/4.0/", "https://doi.org/10.1/x", None, ("S1",),
    )  # fmt: skip
    run = _run(FOOD_TOOL, {"food": HOSTILE_FOOD_NAME, "grams": 100})
    turns = [("<b>bold</b> & </para>?", _answer("Ok [S1].", title_card, runs=(run,)))]
    data = _pdf(turns, manifest={})
    text = pdf_text(data)
    assert "<b>bold</b> & </para>?" in text
    assert '[S1] <link href="https://example.com">T</link> (2020)' in text
    assert "</user_input>" in text
    assert _annotations(data) == []


def test_the_pdf_has_no_link_annotations_at_all():
    """Source and licence URLs are printed as text: the PDF holds no annotation."""
    run = _run(FOOD_TOOL, {"food": "rolled oats", "grams": 80})
    data = _pdf([("HMB?", _answer("[See](https://example.com) [S1].", _card(HMB), runs=(run,)))])
    assert _annotations(data) == []
    assert "See (https://example.com) [S1]." in pdf_text(data)


# --- Markdown made plain text (owner's choice, 2026-10-20) ----------------------------------------


@pytest.mark.parametrize(
    ("markdown", "plain"),
    [
        ("## Protein timing", [("Protein timing", 0)]),
        ("**Protein** and __fat__ matter", [("Protein and fat matter", 0)]),
        ("*often* and _sometimes_", [("often and sometimes", 0)]),
        ("Use `1.6 g/kg` daily", [("Use 1.6 g/kg daily", 0)]),
        ("- one\n* two\n  - nested", [("• one", 1), ("• two", 1), ("• nested", 2)]),
        ("1. first\n2. second", [("1. first", 0), ("2. second", 0)]),
        ("> quoted line", [("quoted line", 0)]),
        ("[ISSN](https://doi.org/10.1/x)", [("ISSN (https://doi.org/10.1/x)", 0)]),
        ("[https://e.com](https://e.com)", [("https://e.com", 0)]),
        ("~~old~~ new", [("old new", 0)]),
        (r"2 \* 3 and \[S1\]", [("2 * 3 and [S1]", 0)]),
        ("a\n---\nb", [("a", 0), ("b", 0)]),
        ("```\ncode\n```", [("code", 0)]),
        ("Cited [S1, S2] and 3 * 4 = 12", [("Cited [S1, S2] and 3 * 4 = 12", 0)]),
        ("snake_case_name stays", [("snake_case_name stays", 0)]),
        ("p &lt; 0.05", [("p < 0.05", 0)]),
        # Entities never make Markdown (CommonMark): the characters are kept (code review).
        ("&gt; 10 g a day adds nothing", [("> 10 g a day adds nothing", 0)]),
        ("&#35; x", [("# x", 0)]),
        ("&ast;x&ast;", [("*x*", 0)]),
        ("- &gt; 5 g", [("• > 5 g", 1)]),
        # Code is shown as written, entities included, as in the app.
        ("Use `a &lt; b` here", [("Use a &lt; b here", 0)]),
        ("```\n# not a heading &lt;\n```", [("# not a heading &lt;", 0)]),
        # URLs and words with underscores keep them.
        ("See https://x.org/__init__ now", [("See https://x.org/__init__ now", 0)]),
        ("snake__case__name", [("snake__case__name", 0)]),
        ("[**ISSN**](https://doi.org/1?a=1&amp;b=2)", [("ISSN (https://doi.org/1?a=1&b=2)", 0)]),
        ('[x](https://e.com "title")', [("x (https://e.com)", 0)]),
        ("> # Quoted heading", [("Quoted heading", 0)]),
        # A table becomes one line per row, its separator row dropped.
        (
            "| Macro | g |\n|:---|---:|\n| **Protein** | 160 |",
            [("Macro · g", 0), ("Protein · 160", 0)],
        ),
        # Escaped marks stay as the characters (PR #54 review): no emphasis, no link.
        (r"\*note\*", [("*note*", 0)]),
        (r"\_note\_", [("_note_", 0)]),
        (r"\[x](y)", [("[x](y)", 0)]),
        (r"[a\_b](https://y.org)", [("a_b (https://y.org)", 0)]),
        # An escaped backtick starts no code span; any ASCII punctuation can be escaped; code in a
        # link's text stays code (PR #54 review, round 3).
        (r"\`not code\`", [("`not code`", 0)]),
        (r"\&amp; costs \$5\?", [("&amp; costs $5?", 0)]),
        ("[`code`](https://u.org)", [("code (https://u.org)", 0)]),
        ("``a ` b``", [("a ` b", 0)]),
        (r"[a\]b](https://u.org)", [("a]b (https://u.org)", 0)]),
        # A bare URL right before a link keeps the link (PR #54 review).
        ("https://a.org[guide](https://b.org)", [("https://a.orgguide (https://b.org)", 0)]),
        # A URL in a link's text keeps its underscores too.
        ("[https://x.org/__init__](https://x.org/__init__)", [("https://x.org/__init__", 0)]),
        (
            "[see https://x.org/__a__](https://y.org)",
            [("see https://x.org/__a__ (https://y.org)", 0)],
        ),
    ],
)
def test_clean_answer_turns_markdown_into_plain_lines(markdown, plain):
    """Headings, emphasis, code, lists, quotes, links and escapes become plain text lines."""
    assert export_pdf.clean_answer(markdown) == plain


def test_an_entity_that_looks_like_markdown_reads_back_as_the_character():
    """ "&gt; 5 g" reads back "> 5 g", as the app shows it, not as a quote mark dropped."""
    text = pdf_text(_pdf([("Dose?", _answer("&gt; 5 g/day adds no benefit [S1]."))]))
    assert "> 5 g/day adds no benefit [S1]." in text


def test_list_items_read_back_with_bullets():
    """A Markdown list in an answer reads back as bullet lines."""
    text = pdf_text(_pdf([("List?", _answer("Eat:\n- **eggs**\n- oats [S1]"))]))
    assert "Eat: • eggs • oats [S1]" in text


# --- Built in memory: no file written (AC 2) ------------------------------------------------------


def test_building_the_pdf_writes_no_file(tmp_path, monkeypatch):
    """No file is opened for writing (open, io.open, os.open) and the working folder stays empty."""
    real_open, real_os_open = builtins.open, os.open
    written: list[str] = []

    def open_read_only(file, mode="r", *args, **kwargs):
        """Open a file, recording any mode that writes."""
        if any(flag in mode for flag in "wax+"):
            written.append(str(file))
        return real_open(file, mode, *args, **kwargs)

    def os_open_read_only(path, flags, *args, **kwargs):
        """Open a file descriptor, recording flags that write or create."""
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            written.append(str(path))
        return real_os_open(path, flags, *args, **kwargs)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "open", open_read_only)
    # pathlib's write_text and write_bytes go through io.open, another name for the same function.
    monkeypatch.setattr(io, "open", open_read_only)
    monkeypatch.setattr(os, "open", os_open_read_only)
    run = _run(FOOD_TOOL, {"food": "rolled oats", "grams": 80})
    data = _pdf([("HMB?", _answer("Yes [S1].", _card(HMB), runs=(run,)))])
    assert data.startswith(b"%PDF-")
    assert written == []
    assert list(tmp_path.iterdir()) == []


def test_the_pdf_metadata_says_nothing_about_the_user():
    """The PDF's title is the app's; no author or subject is set."""
    metadata = PdfReader(io.BytesIO(_pdf())).metadata
    assert metadata.title == export_pdf.TEXT["title"]
    assert not metadata.author
    assert not metadata.subject


def test_a_build_failure_raises_a_fixed_error_without_the_content(monkeypatch):
    """A ReportLab error becomes PdfExportError with a fixed message and no chained cause."""

    def fail(*args, **kwargs):
        """Fail as a layout error quoting the question would."""
        raise ValueError("paragraph text: my secret question")

    monkeypatch.setattr(export_pdf, "_story", fail)
    with pytest.raises(export_pdf.PdfExportError) as caught:
        _pdf([("my secret question", _answer("x"))])
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_every_turn_kind_has_a_label():
    """Each kind of turn has the label the app and the PDF show for it."""
    assert set(chat.TurnKind.__args__) <= set(config.STATUS_LABELS)


def test_tool_titles_match_the_tools():
    """Every tool, and a refused call (None), has a heading in the app and the PDF."""
    assert set(registry.TOOL_TITLES) == {TDEE_TOOL, MACRO_TOOL, FOOD_TOOL, MEAL_PLAN_TOOL, None}


def test_the_fonts_cover_every_character_of_the_approved_sources():
    """DejaVu Sans has a glyph for every character in the manifest's titles, authors and notices."""
    export_pdf._register_fonts()
    known = export_pdf._font_characters()
    text = "".join(
        source.title + source.journal + source.copyright_notice + "".join(source.authors)
        for source in MANIFEST.values()
    )
    assert {c for c in text if ord(c) not in known} == set()


def test_a_tool_notice_has_no_values_to_show():
    """A ToolNotice result (error) is shown by its message alone."""
    notice = ToolNotice(status="error", message=config.TOOL_FAILED_MESSAGE)
    run = ToolRun(FOOD_TOOL, "error", notice)
    text = pdf_text(_pdf([("Oats?", _answer("Not available.", runs=(run,)))], user=None))
    assert f"Food lookup {config.TOOL_FAILED_MESSAGE}" in text
    assert re.search(r"Food data", text) is None


def test_a_cited_article_shows_its_correction_and_both_are_credited():
    """A card's correction notice is under its source line, and the notice is credited too."""
    original, notice = MANIFEST["18"], MANIFEST["18a"]
    correction = chat.Correction("corrected_by", notice.title, notice.url)
    card = dataclasses.replace(_card(original), corrections=(correction,))
    text = pdf_text(_pdf([("Creatine?", _answer("It helps [S1].", card))], user=None))
    label = config.CORRECTION_LABELS["corrected_by"]
    assert " ".join(f"{label}: {notice.title}. {notice.url}".split()) in text
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert f"[{original.id}] " in credits and f"[{notice.id}] " in credits


def test_a_cited_correction_notice_brings_its_article_into_the_credits():
    """Citing the notice alone credits the article it corrects as well."""
    notice = MANIFEST["18a"]
    text = pdf_text(_pdf([("Creatine?", _answer("See [S1].", _card(notice)))], user=None))
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert f"[{notice.corrects}] " in credits


def test_two_pdfs_of_the_same_session_differ():
    """The PDF carries its own creation time and ID, so its bytes do not follow from the profile."""
    assert _pdf() != _pdf()


def test_the_credits_end_with_the_fonts_licence_word_for_word():
    """Every PDF names DejaVu Sans and prints its licence's notices exactly as in LICENSE."""
    credits = pdf_text(_pdf(user=None)).split(export_pdf.TEXT["credits"], 1)[1]
    # A page break puts the next page's footer inside the text read back.
    footer = re.escape(export_pdf.TEXT["footer"]).replace(re.escape("{page}"), r"\d+")
    credits = re.sub(rf"{footer} ", "", credits)
    assert " ".join(export_pdf.TEXT["font_credit"].split()) in credits
    # The whole part for DejaVu Sans, compared word for word with the committed file.
    licence = config.PDF_FONT_LICENSE_PATH.read_text(encoding="utf-8")
    part = licence.split(config.PDF_FONT_LICENSE_END, 1)[0]
    words = " ".join(word for word in part.split() if set(word) != {"-"})
    assert words in credits
    for notice in (
        "Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved.",
        "Bitstream Vera is a trademark of Bitstream, Inc.",
        "Copyright (c) 2006 by Tavmjong Bah. All Rights Reserved.",
        "this permission notice shall be included in all copies",
    ):
        assert notice in credits
    assert config.PDF_FONT_LICENSE_END not in credits


def test_the_font_licence_is_read_in_paragraphs_without_title_underlines():
    """The licence's paragraphs are kept, joined into lines, with no "-----" line of their own."""
    paragraphs = export_pdf.font_licence_paragraphs()
    assert paragraphs[1] == "Bitstream Vera Fonts Copyright"
    assert "Arev Fonts Copyright" in paragraphs
    assert all(set(paragraph) != {"-"} and "\n" not in paragraph for paragraph in paragraphs)


# --- The meal plan check (T4.5) -------------------------------------------------------------------

DAY = {
    "items": [
        {"food": "rolled oats", "grams": 80},
        {"food": "chicken breast", "grams": 200},
        {"food": "zzzz qqqq", "grams": 50},
    ]
}


def test_a_meal_plan_check_shows_its_foods_targets_and_notes():
    """The meal plan shows both of the app's tables, its message, its notes and the source line."""
    run = _run(MEAL_PLAN_TOOL, DAY)
    text = pdf_text(_pdf([("My day?", _answer("See below.", runs=(run,)))]))
    part = text.split("My day?", 1)[1]
    assert "Meal plan check Food asked USDA food Amount" in part
    assert "rolled oats Oats, whole grain, rolled, old fashioned 80 g 304 kcal" in part
    assert "zzzz qqqq Not found 50 g" in part
    energy = "Energy 544 kcal 3,035 kcal 2,491 kcal below the target Below 3,035-3,311 kcal"
    assert energy in part
    assert "Fiber 8 g No target" in part
    for line in (run.result.message, *run.result.notes, config.MEAL_PLAN_SOURCE_LINE):
        assert " ".join(line.split()) in part


def test_a_meal_plan_with_no_food_found_has_no_totals_table():
    """With no food found, the foods table and the message are shown, and no comparison."""
    run = _run(MEAL_PLAN_TOOL, {"items": [{"food": "zzzz qqqq", "grams": 50}]})
    text = pdf_text(_pdf([("My day?", _answer("See below.", runs=(run,)))]))
    assert "zzzz qqqq Not found 50 g" in text
    assert "Plan total" not in text
    assert " ".join(run.result.message.split()) in text


def test_meal_plan_names_stay_text_in_the_pdf():
    """The name asked for and a hostile USDA name are escaped: no markup, no link."""
    asked = "<b>oats</b> & </para>"
    run = _run(MEAL_PLAN_TOOL, {"items": [{"food": HOSTILE_FOOD_NAME, "grams": 100}]})
    asked_run = _run(MEAL_PLAN_TOOL, {"items": [{"food": asked, "grams": 100}]})
    data = _pdf([("Day?", _answer("Ok.", runs=(run, asked_run)))], manifest={})
    # The table's narrow cells wrap long names, so compare without whitespace.
    compact = "".join(pdf_text(data).split())
    assert "".join(HOSTILE_FOOD_NAME.split()) in compact
    assert "".join(asked.split()) in compact
    assert _annotations(data) == []


@pytest.mark.parametrize("items", [DAY["items"], [{"food": "zzzz qqqq", "grams": 50}]])
def test_a_meal_plan_credits_usda(items):
    """A meal plan shows USDA names or values, found or not, so USDA is credited (T4.5)."""
    run = _run(MEAL_PLAN_TOOL, {"items": items})
    assert run.status in ("ok", "not_found")
    text = pdf_text(_pdf([("Day?", _answer("See below.", runs=(run,)))], user=None))
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert f"Licence: {config.USDA_LICENSE}" in credits


def test_a_meal_plan_credits_the_targets_and_formula_sources():
    """A meal plan compares with the targets, so their articles and the formulas are credited."""
    run = _run(MEAL_PLAN_TOOL, DAY)
    text = pdf_text(_pdf([("Day?", _answer("See below.", runs=(run,)))], user=None))
    credits = text.split(export_pdf.TEXT["credits"], 1)[1]
    assert export_pdf.TEXT["formula_sources"] in credits
    for source in MANIFEST.values():
        if any(source.url in line for line in MACRO_SOURCES):
            assert source.url in credits, source.id


def test_a_meal_plan_shows_the_alternatives_and_suggestions():
    """The app's "Other close USDA names" reach the PDF: suggestions and close alternatives."""
    plan = {
        "items": [{"food": "chicken thigh", "grams": 100}, {"food": "rolled oats", "grams": 80}]
    }
    run = _run(MEAL_PLAN_TOOL, plan)
    compact = "".join(pdf_text(_pdf([("Day?", _answer("Ok.", runs=(run,)))])).split())
    did_you_mean = "Did you mean: chicken thigh: Chicken, breast, boneless, skinless, raw"
    assert "".join(did_you_mean.split()) in compact
    close = f"Close alternatives: rolled oats: {HOSTILE_FOOD_NAME}"
    assert "".join(close.split()) in compact


def test_the_meal_plan_foods_table_splits_no_header_word():
    """Each header of the foods table reads back whole, so none is split mid-word."""
    run = _run(MEAL_PLAN_TOOL, DAY)
    text = pdf_text(_pdf([("Day?", _answer("Ok.", runs=(run,)))]))
    assert "Amount Energy Protein Carbohydrate Fat Fiber" in text
    # The values in their columns' order. pdf_text() joins lines with a space, so this cannot see
    # a value that wraps between its number and its unit; the widths test below covers the fit.
    assert "80 g 304 kcal 10.6 g 54.4 g 5.1 g 8 g" in text


def test_fitted_widths_fit_each_value_and_fill_the_page():
    """Value columns get their longest text plus padding; the name columns share the rest."""
    rows = [["Name", "Other", "Carbohydrate"], ["a", "b", "54.4 g"]]
    widths = export_pdf._fitted_widths(rows, wide=(0, 1), size=export_pdf.SMALL_SIZE)
    text = pdfmetrics_width("Carbohydrate", export_pdf.SMALL_SIZE)
    assert widths[2] == pytest.approx(text + export_pdf.CELL_PADDING)
    assert widths[0] == widths[1]
    assert sum(widths) == pytest.approx(export_pdf.CONTENT_WIDTH)


def test_fitted_widths_fall_back_to_equal_columns():
    """When the values leave the name columns too little room, every column is equal."""
    rows = [["Name", "x" * 400]]
    widths = export_pdf._fitted_widths(rows, wide=(0,), size=export_pdf.SMALL_SIZE)
    assert widths == [export_pdf.CONTENT_WIDTH / 2] * 2


def pdfmetrics_width(text: str, size: float) -> float:
    """Return the width of the text in the PDF's font at this size."""
    return pdfmetrics.stringWidth(text, export_pdf.FONT, size)
