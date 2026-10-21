"""Tests for src/rag/ingest.py: JATS parsing, chunking and chunk metadata (T2.2)."""

import shutil
from pathlib import Path

import pytest

from src import config
from src.rag import ingest
from src.rag.ingest import (
    IngestError,
    ParsedArticle,
    Section,
    chunk_article,
    load_chunks,
    merge_short_spans,
    parse_article,
)
from src.rag.sources import Source

FIXTURES = Path(__file__).parent / "fixtures" / "jats"
ARTICLE_XML = (FIXTURES / "ingest_article.xml").read_bytes()
# The metadata every chunk carries (acceptance criteria of T2.2; copyright policy rule 6).
METADATA_KEYS = {
    "source_id",
    "title",
    "authors",
    "year",
    "section",
    "topics",
    "evidence_tier",
    "license",
    "source_url",
    "chunk_index",
}
# Marker words in the fixture that sit only inside elements that must be dropped.
DROPPED_MARKERS = [
    "FIGURECAPTION",
    "TABLECAPTION",
    "TABLECELL",
    "TABLEFOOTNOTE",
    "DISPLAYFORMULA",
    "SUPPLEMENTCAPTION",
    "QUOTEDBOX",
    "THIRDPARTY",
    "QUOTEDPASSAGE",
    "made-up poet",
    "FOOTNOTEMARK",
    "NOTETEXT",
    "ACKTEXT",
    "COITEXT",
    "FUNDINGTEXT",
    "PUBLISHERNOTE",
    "APPENDIXTEXT",
    "REFERENCETEXT",
    "BACKACK",
    "BACKREFERENCE",
    "FLOATCAPTION",
    "KEYWORDTEXT",
]


def make_source(**changes) -> Source:
    """Return a made-up Source that matches the fixture article, with the given fields changed."""
    data = {
        "id": "1",
        "title": "A made-up article title",
        "authors": ["Ann Example", "Ben Sample"],
        "year": 2024,
        "journal": "Journal of Made-up Results",
        "doi": "10.1234/made-up.1",
        "pmcid": "PMC1234567",
        "url": "https://doi.org/10.1234/made-up.1",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "copyright_notice": "© The Author(s) 2024",
        "evidence_tier": 1,
        "topics": ["protein", "supplements"],
    }
    data.update(changes)
    return Source.model_validate(data)


def long_text(sentences: int, word: str = "oats") -> str:
    """Return made-up text of numbered sentences, long enough to need several chunks."""
    return " ".join(f"Sentence {n} says {word} are a grain." for n in range(sentences))


def body_of(chunk_text: str, title: str) -> str:
    """Return a chunk's text without the section title it starts with."""
    header = f"{title}\n\n"
    assert chunk_text.startswith(header)
    return chunk_text[len(header) :]


@pytest.fixture(scope="module")
def parsed() -> ParsedArticle:
    """Parse the fixture article once for the module."""
    return parse_article(ARTICLE_XML)


def test_the_article_title_is_kept(parsed):
    """The article title is read from the front matter, inline markup flattened."""
    assert parsed.title == "Oats and made-up lifters"


def test_abstract_and_body_sections_are_kept_in_reading_order(parsed):
    """The abstract and body sections come out in order, with their title paths."""
    assert [s.title for s in parsed.sections] == [
        "Abstract > Background",
        "Abstract > Conclusions",
        "Introduction",
        "Methods",
        "Methods > Search",
        "Methods",
    ]


def test_paragraph_and_list_text_is_kept(parsed):
    """Paragraphs are kept and list items become "- " lines, without their bullet labels."""
    sections = {s.title: s.text for s in parsed.sections}
    assert sections["Abstract > Background"] == "Oats were eaten by made-up lifters."
    assert sections["Abstract > Conclusions"] == "Two points:\n\n- Oats are fine.\n- Water is fine."
    assert sections["Methods > Search"] == "We searched a made-up library."


def test_text_after_a_subsection_is_its_own_section(parsed):
    """Parent text before and after a subsection never joins the subsection's text."""
    methods = [s.text for s in parsed.sections if s.title == "Methods"]
    assert methods == ["We read made-up papers.", "Then we wrote it down."]


def intro_paragraphs(parsed: ParsedArticle) -> list[str]:
    """Return the paragraphs of the fixture's Introduction section."""
    return next(s.text for s in parsed.sections if s.title == "Introduction").split("\n\n")


def test_the_introduction_keeps_exactly_its_text_paragraphs(parsed):
    """Only the paragraphs and the list are kept; the quoted passage and every float are not."""
    assert len(intro_paragraphs(parsed)) == 6


def test_citation_markers_are_removed_cleanly(parsed):
    """Numeric reference markers go with their brackets; other cross-references stay."""
    first = intro_paragraphs(parsed)[0]
    assert first == (
        "Oats help. Rice helps too. See the oat counts (Table 1). Doses fell by 10^-3 units."
    )


def test_brackets_that_are_part_of_the_text_stay(parsed):
    """Brackets in the text stay, author-year citations keep their words, nested ones go."""
    assert intro_paragraphs(parsed)[2] == (
        "Green tea (-)-epicatechin was tested (Example and Sample, 2020). Oats help."
    )


def test_text_after_a_dropped_element_is_kept(parsed):
    """The words after a display formula and a footnote marker inside a paragraph stay."""
    assert intro_paragraphs(parsed)[3] == "The model is: where oats are fixed."


def test_inline_formulas_keep_their_plain_text(parsed):
    """An inline formula keeps its symbols, so the sentence stays whole (owner's choice)."""
    assert intro_paragraphs(parsed)[1] == "The effect was τ = 0.5 overall."


def test_exponents_brackets_and_accents_keep_their_meaning(parsed):
    """Superscripts, MathML scripts, fences and accents are written out, not flattened."""
    assert intro_paragraphs(parsed)[4] == (
        "Heterogeneity was I^2 = 0%, P(>0)= 0.8, R̂ = 1.01 and β_oats = 0.2 on a N(0, 100^2) prior."
    )


def test_line_breaks_in_the_xml_do_not_split_sentences(parsed):
    """The XML's own indentation and line breaks inside a paragraph become single spaces."""
    for paragraph in intro_paragraphs(parsed)[:5]:
        assert "\n" not in paragraph


def test_nested_list_items_get_their_own_lines(parsed):
    """An item inside another item's list gets its own "- " line."""
    assert intro_paragraphs(parsed)[5] == "- Grains\n- Oats"


@pytest.mark.parametrize("marker", DROPPED_MARKERS)
def test_dropped_content_never_appears(parsed, marker):
    """Figures, tables, formulas, supplements, notes, third-party and back matter are dropped."""
    text = parsed.title + "\n".join(f"{s.title}\n{s.text}" for s in parsed.sections)
    assert marker not in text


@pytest.mark.parametrize(
    "title",
    [
        "Acknowledgements",
        "Authors’ contributions",
        "Conflicts of Interest",
        "Disclaimer/Publisher's Note",
        "5. Data Availability Statement",
        "Supplementary Material",
        "Appendix B: More plots",
    ],
)
def test_back_matter_titles_are_dropped(title):
    """Back-matter sections are recognised by title, in any case, numbering and punctuation."""
    xml = (
        "<article><body><sec><title>Protein</title><p>Kept text.</p></sec>"
        f"<sec><title>{title}</title><p>DROPPED</p></sec></body></article>"
    ).encode()
    article = parse_article(xml)
    assert [s.title for s in article.sections] == ["Protein"]


@pytest.mark.parametrize(
    "title",
    ["Clinical Trial Registration", "Systematic review registration", "Trial registration"],
)
def test_registration_notes_in_the_abstract_are_dropped(title):
    """An abstract's registration note (a bare registry ID) is dropped, the rest is kept (T3.7)."""
    xml = (
        "<article><front><article-meta><abstract>"
        "<sec><title>Objective</title><p>Kept text.</p></sec>"
        f"<sec><title>{title}</title><p>PROSPERO CRD00000000000.</p></sec>"
        "</abstract></article-meta></front></article>"
    ).encode()
    article = parse_article(xml)
    assert [s.title for s in article.sections] == ["Abstract > Objective"]


def test_a_methods_protocol_and_registration_section_is_kept():
    """A Methods section on the protocol and its registration is content, so it stays (T3.7)."""
    xml = (
        b"<article><body><sec><title>Methods</title><sec><title>Protocol and registration</title>"
        b"<p>The review followed a made-up protocol.</p></sec></sec></body></article>"
    )
    article = parse_article(xml)
    assert article.sections == [
        Section("Methods > Protocol and registration", "The review followed a made-up protocol.")
    ]


def test_body_paragraphs_outside_sections_get_the_main_text_title():
    """Paragraphs directly in the body (like correction #18a) get a section title of their own."""
    xml = b"<article><body><p>The table had a typo.</p><fig><p>FIG</p></fig></body></article>"
    article = parse_article(xml)
    assert article.sections == [Section(config.MAIN_TEXT_TITLE, "The table had a typo.")]


def test_invalid_xml_raises_an_ingest_error():
    """Text that is not XML gives an IngestError, not a parser crash."""
    with pytest.raises(IngestError):
        parse_article(b"<article><body>")


def test_every_chunk_starts_with_its_section_title(parsed):
    """Each chunk's text starts with the title of the one section it comes from."""
    chunks = chunk_article(parsed, make_source())
    assert len(chunks) == len(parsed.sections)
    for chunk, section in zip(chunks, parsed.sections, strict=True):
        assert chunk.page_content == f"{section.title}\n\n{section.text}"
        assert chunk.metadata["section"] == section.title


def test_long_sections_split_into_chunks_of_about_1000_characters():
    """Chunks are at most 1,000 characters, title included; only the last may be shorter or more."""
    article = ParsedArticle("T", [Section("Protein timing", long_text(120))])
    chunks = chunk_article(article, make_source())
    sizes = [len(c.page_content) for c in chunks]
    assert len(chunks) > 3
    assert max(sizes[:-1]) <= config.CHUNK_SIZE
    assert min(sizes[:-1]) >= config.CHUNK_SIZE - 100
    assert config.CHUNK_MIN_CHARS <= sizes[-1] <= config.CHUNK_SIZE + config.CHUNK_MIN_CHARS


# A short paragraph that does not fit in one chunk with a long_text(28) paragraph ("Protein").
SHORT_PARAGRAPH = "Oats and rice are both grains, eaten by made-up lifters."


def test_a_short_last_paragraph_joins_the_chunk_before_it():
    """A short paragraph left over at the end of a section is not a chunk of its own (T3.7)."""
    title = "Protein"
    first = long_text(28)
    text = f"{first}\n\n{SHORT_PARAGRAPH}"
    assert len(f"{title}\n\n{first}") < config.CHUNK_SIZE < len(f"{title}\n\n{text}")
    chunks = chunk_article(ParsedArticle("T", [Section(title, text)]), make_source())
    assert [c.page_content for c in chunks] == [f"{title}\n\n{text}"]


def test_a_short_last_paragraph_that_repeats_a_sentence_is_not_lost():
    """A last paragraph whose words also end the paragraph before it is joined, not dropped."""
    title = "Protein"
    text = f"{long_text(28)} Not reported.\n\nNot reported."
    assert len(f"{title}\n\n{text}") > config.CHUNK_SIZE
    chunks = chunk_article(ParsedArticle("T", [Section(title, text)]), make_source())
    assert [c.page_content for c in chunks] == [f"{title}\n\n{text}"]


def test_pieces_that_cannot_be_placed_in_the_text_stay_as_split(monkeypatch):
    """If the splitter's pieces are not found in the section in order, none is joined (T3.7)."""
    pieces = ["A piece the section does not hold.", "short"]
    monkeypatch.setattr(
        ingest.RecursiveCharacterTextSplitter, "split_text", lambda self, text: pieces
    )
    chunks = chunk_article(ParsedArticle("T", [Section("Fat", "Text.")]), make_source())
    assert [c.page_content for c in chunks] == [f"Fat\n\n{piece}" for piece in pieces]


def test_a_short_middle_paragraph_joins_the_chunk_before_it():
    """A short paragraph between two long ones joins the chunk before it (T3.7)."""
    title = "Protein"
    first, last = long_text(28), long_text(28, "rice")
    text = f"{first}\n\n{SHORT_PARAGRAPH}\n\n{last}"
    chunks = chunk_article(ParsedArticle("T", [Section(title, text)]), make_source())
    assert [c.page_content for c in chunks] == [
        f"{title}\n\n{first}\n\n{SHORT_PARAGRAPH}",
        f"{title}\n\n{last}",
    ]


def test_a_short_first_paragraph_joins_the_chunk_after_it():
    """A short paragraph at the start of a section joins the chunk after it (T3.7)."""
    title = "Protein"
    text = f"{SHORT_PARAGRAPH}\n\n{long_text(28)}"
    assert len(f"{title}\n\n{text}") > config.CHUNK_SIZE
    chunks = chunk_article(ParsedArticle("T", [Section(title, text)]), make_source())
    assert [c.page_content for c in chunks] == [f"{title}\n\n{text}"]


@pytest.mark.parametrize(
    ("spans", "expected"),
    [
        # A short last span joins the one before it.
        ([(0, 990), (992, 1100)], [(0, 1100)]),
        # Overlapping spans, as the splitter makes them, join with the overlap counted once.
        ([(0, 990), (850, 1000)], [(0, 1000)]),
        # A short first span joins the one after it.
        ([(0, 100), (102, 1000)], [(0, 1000)]),
        # The second span joins the first; the third would then pass the cap backwards, so it
        # joins the fourth.
        ([(0, 990), (992, 1250), (1252, 1450), (1452, 2400)], [(0, 1250), (1252, 2400)]),
        # Neither join fits under the cap, so the short span stays.
        ([(0, 1200), (1202, 1400), (1402, 2500)], [(0, 1200), (1202, 1400), (1402, 2500)]),
        # Short spans keep joining until the result is long enough or nothing is left to join.
        ([(0, 100), (102, 200), (202, 300)], [(0, 300)]),
        # A section with one span keeps it, however short.
        ([(0, 50)], [(0, 50)]),
    ],
)
def test_merge_short_spans_joins_within_the_cap(spans, expected):
    """Short spans join the span before, else after, never past CHUNK_SIZE + CHUNK_MIN_CHARS."""
    assert (config.CHUNK_SIZE, config.CHUNK_MIN_CHARS) == (1000, 300)
    assert merge_short_spans(spans, header_chars=9) == expected


def test_short_pieces_are_merged_as_one_passage_of_the_section():
    """Across section lengths, each chunk is one passage of the section and none is short (T3.7)."""
    title = "Protein timing"
    merged = 0
    for sentences in range(20, 120):
        text = long_text(sentences)
        chunks = chunk_article(ParsedArticle("T", [Section(title, text)]), make_source())
        bodies = [body_of(c.page_content, title) for c in chunks]
        # Each body is one passage of the section, so no overlap is repeated inside it.
        assert all(body in text for body in bodies)
        assert text.endswith(bodies[-1])
        # No sentence is lost.
        for n in range(sentences):
            assert any(f"Sentence {n} says" in body for body in bodies)
        sizes = [len(c.page_content) for c in chunks]
        assert len(chunks) == 1 or min(sizes) >= config.CHUNK_MIN_CHARS
        assert max(sizes) <= config.CHUNK_SIZE + config.CHUNK_MIN_CHARS
        merged += sizes[-1] > config.CHUNK_SIZE
    # Some of these lengths left a short last piece, so the merge really ran.
    assert merged > 0


def test_a_section_with_one_short_chunk_stays_as_it_is():
    """A whole section shorter than CHUNK_MIN_CHARS is kept, not dropped or joined (T3.7)."""
    sections = [Section("Abstract > Objective", "We asked whether oats help."), Section("B", "x")]
    chunks = chunk_article(ParsedArticle("T", sections), make_source())
    assert [c.page_content for c in chunks] == [
        "Abstract > Objective\n\nWe asked whether oats help.",
        "B\n\nx",
    ]


def test_neighbouring_chunks_overlap_by_at_most_150_characters():
    """Each chunk repeats the end of the previous one (up to 150 characters), so no text is lost."""
    title = "Protein timing"
    chunks = chunk_article(ParsedArticle("T", [Section(title, long_text(120))]), make_source())
    bodies = [body_of(c.page_content, title) for c in chunks]
    for previous, current in zip(bodies, bodies[1:], strict=False):
        shared = max(k for k in range(config.CHUNK_OVERLAP + 1) if previous.endswith(current[:k]))
        assert 50 <= shared <= config.CHUNK_OVERLAP


def test_chunks_never_span_two_sections():
    """Every chunk's text comes from exactly one section, even when sections are long."""
    sections = [Section("Protein", long_text(60, "eggs")), Section("Fat", long_text(60, "nuts"))]
    chunks = chunk_article(ParsedArticle("T", sections), make_source())
    for chunk in chunks:
        title = chunk.metadata["section"]
        body = body_of(chunk.page_content, title)
        owners = [s.title for s in sections if body in s.text]
        assert owners == [title]
    assert {c.metadata["section"] for c in chunks} == {"Protein", "Fat"}


def test_a_very_long_section_title_still_leaves_room_for_text():
    """A title longer than the chunk size still gives chunks with text after it."""
    title = "Methods > " + "very long title " * 70
    chunks = chunk_article(ParsedArticle("T", [Section(title, long_text(80))]), make_source())
    for chunk in chunks:
        assert len(body_of(chunk.page_content, title)) > 0


def test_every_chunk_has_the_source_metadata(parsed):
    """Each chunk carries exactly the ten metadata fields, with the source's values."""
    source = make_source()
    chunks = chunk_article(parsed, source)
    for index, chunk in enumerate(chunks):
        assert set(chunk.metadata) == METADATA_KEYS
        assert chunk.metadata == {
            "source_id": "1",
            "title": source.title,
            "authors": ["Ann Example", "Ben Sample"],
            "year": 2024,
            "section": chunk.metadata["section"],
            "topics": ["protein", "supplements"],
            "evidence_tier": 1,
            "license": "CC BY 4.0",
            "source_url": "https://doi.org/10.1234/made-up.1",
            "chunk_index": index,
        }


def test_chunk_index_runs_across_sections():
    """chunk_index counts the chunks of an article from 0, across all its sections."""
    sections = [Section("A", long_text(40)), Section("B", "Short."), Section("C", long_text(40))]
    chunks = chunk_article(ParsedArticle("T", sections), make_source())
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


def write_raw(raw_dir: Path, pmcid: str, xml: bytes = ARTICLE_XML) -> None:
    """Save article XML in a raw folder under the name the download script uses."""
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / f"{pmcid}.xml").write_bytes(xml)


def test_load_chunks_reads_each_downloaded_article(tmp_path):
    """Chunks are built from data/raw/<PMCID>.xml for every source, in manifest order."""
    write_raw(tmp_path, "PMC1234567")
    write_raw(tmp_path, "PMC7654321")
    sources = [make_source(), make_source(id="2", pmcid="PMC7654321")]
    chunks = load_chunks(sources, tmp_path)
    assert [c.metadata["source_id"] for c in chunks] == ["1"] * 6 + ["2"] * 6
    assert all(set(c.metadata) == METADATA_KEYS for c in chunks)


def test_a_correction_and_the_corrected_article_point_to_each_other(tmp_path):
    """A correction's chunks name the article it corrects, and that article's chunks name it."""
    write_raw(tmp_path, "PMC1234567")
    write_raw(tmp_path, "PMC7654321")
    sources = [make_source(id="18"), make_source(id="18a", pmcid="PMC7654321", corrects="18")]
    chunks = load_chunks(sources, tmp_path)
    by_source = {c.metadata["source_id"]: c.metadata for c in chunks}
    assert by_source["18"]["corrected_by"] == ["18a"]
    assert "corrects" not in by_source["18"]
    assert by_source["18a"]["corrects"] == "18"
    assert "corrected_by" not in by_source["18a"]


def test_a_missing_file_stops_the_build_and_names_the_source(tmp_path):
    """A source without its XML file raises IngestError naming it and the download script."""
    write_raw(tmp_path, "PMC1234567")
    sources = [make_source(), make_source(id="2", pmcid="PMC7654321")]
    with pytest.raises(IngestError) as caught:
        load_chunks(sources, tmp_path)
    assert "#2 (PMC7654321)" in str(caught.value)
    assert "scripts/download_sources.py" in str(caught.value)
    assert "#1 " not in str(caught.value)


def test_a_file_the_licence_check_refuses_stops_the_build(tmp_path):
    """XML whose licence is not CC BY is refused before parsing, and the error says why."""
    shutil.copy(FIXTURES / "cc_by_nc.xml", tmp_path / "PMC1234567.xml")
    with pytest.raises(IngestError, match=r"#1 \(PMC1234567\): refused"):
        load_chunks([make_source()], tmp_path)


def test_an_article_without_text_stops_the_build(tmp_path):
    """An accepted article that yields no text is reported, so no source is silently missing."""
    empty = (
        ARTICLE_XML.split(b"<body>")[0]
        .replace(b"<abstract>", b"<!--")
        .replace(b"</abstract>", b"-->")
    )
    write_raw(tmp_path, "PMC1234567", empty + b"<body/></article>")
    with pytest.raises(IngestError, match="no text found"):
        load_chunks([make_source()], tmp_path)


@pytest.mark.parametrize("text", ["(-)-epicatechin", "(+)/(-) forms", "f() and g[]", "[2.1%]"])
def test_brackets_without_removed_citations_are_untouched(text):
    """Text brackets, even empty ones, are never removed when no citation was taken out."""
    article = parse_article(f"<article><body><p>{text}</p></body></article>".encode())
    assert article.sections[0].text == text


def test_extra_metadata_cannot_overwrite_the_required_keys(parsed):
    """Extra metadata (the correction link) never replaces one of the ten required keys."""
    chunks = chunk_article(parsed, make_source(), {"section": "OVERRIDDEN", "corrects": "2"})
    assert all(c.metadata["section"] != "OVERRIDDEN" for c in chunks)
    assert all(c.metadata["corrects"] == "2" for c in chunks)


def test_chunks_cut_at_a_paragraph_break_share_no_text():
    """Where a cut falls between paragraphs, the next chunk starts with the next paragraph."""
    paragraphs = [long_text(18, word) for word in ("eggs", "nuts", "rice")]
    title = "Protein"
    text = "\n\n".join(paragraphs)
    chunks = chunk_article(ParsedArticle("T", [Section(title, text)]), make_source())
    bodies = [body_of(c.page_content, title) for c in chunks]
    assert len(paragraphs[0]) + len(title) + 2 < config.CHUNK_SIZE
    assert bodies[1].startswith(paragraphs[1][:40])


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        ("with τ\n      <sup>2</sup> = 0", "with τ^2 = 0"),
        ("doses of <sup>15</sup>N-glycine", "doses of ^15N-glycine"),
        (
            '<inline-formula><mml:math><mml:mover accent="true"><mml:mrow><mml:mi>R</mml:mi>'
            "<mml:mo>^</mml:mo></mml:mrow><mml:mo>^</mml:mo></mml:mover></mml:math></inline-formula>"
            " = 1",
            "R̂ = 1",
        ),
    ],
)
def test_publisher_layout_quirks_do_not_change_the_text(inner, expected):
    """A line break before an exponent goes, a real space stays, and one hat is kept."""
    xml = (
        '<article xmlns:mml="http://www.w3.org/1998/Math/MathML"><body>'
        f"<p>{inner}</p></body></article>"
    )
    assert parse_article(xml.encode()).sections[0].text == expected


def render_math(inner: str) -> str:
    """Return the text of a made-up paragraph holding one inline MathML formula."""
    xml = (
        '<article xmlns:mml="http://www.w3.org/1998/Math/MathML"><body><p>'
        f"<inline-formula><mml:math>{inner}</mml:math></inline-formula></p></body></article>"
    )
    return parse_article(xml.encode()).sections[0].text


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        (
            "<mml:msubsup><mml:mi>x</mml:mi><mml:mi>i</mml:mi><mml:mn>2</mml:mn></mml:msubsup>",
            "x_i^2",
        ),
        (
            '<mml:mfenced open="[" close="]"><mml:mn>0.1</mml:mn>'
            "<mml:mn>0.9</mml:mn></mml:mfenced>",
            "[0.1, 0.9]",
        ),
        (
            '<mml:mfenced separators=""><mml:mi>a</mml:mi><mml:mi>b</mml:mi></mml:mfenced>',
            "(ab)",
        ),
        (
            "<mml:msup><mml:mfenced><mml:mi>a</mml:mi></mml:mfenced><mml:mn>2</mml:mn></mml:msup>",
            "(a)^2",
        ),
        (
            "<mml:msup><mml:msub><mml:mi>x</mml:mi><mml:mi>i</mml:mi></mml:msub>"
            "<mml:mn>2</mml:mn></mml:msup>",
            "x_i^2",
        ),
        ('<mml:mover accent="true"><mml:mi>x</mml:mi><mml:mo>¯</mml:mo></mml:mover>', "x̄"),
        ('<mml:mover accent="true"><mml:mi>V</mml:mi><mml:mo>˙</mml:mo></mml:mover>', "V̇"),
    ],
)
def test_mathml_scripts_fences_and_accents_are_written_out(inner, expected):
    """Sub- and superscripts, fences with their attributes, nested scripts and accents."""
    assert render_math(inner) == expected


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        ("Whey<sup>®</sup> powder", "Whey® powder"),
        ('Oats help<sup>[<xref ref-type="bibr" rid="r1">1</xref>]</sup>.', "Oats help."),
    ],
)
def test_symbol_and_bracketed_citation_superscripts(inner, expected):
    """A registered-mark superscript gets no "^", and one holding only a citation is removed."""
    article = parse_article(f"<article><body><p>{inner}</p></body></article>".encode())
    assert article.sections[0].text == expected


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        (
            'Smith et al. (<xref ref-type="bibr" rid="r1">2020</xref>) found oats help.',
            "Smith et al. (2020) found oats help.",
        ),
        (
            'Oats help (Smith et al., <xref ref-type="bibr" rid="r1">2020a</xref>).',
            "Oats help (Smith et al., 2020a).",
        ),
        ('Oats help [<xref ref-type="bibr" rid="r1">20</xref>].', "Oats help."),
    ],
)
def test_a_citation_linked_on_its_year_keeps_the_year(inner, expected):
    """A link on the year of an author-year citation keeps the year; numbered markers still go."""
    article = parse_article(f"<article><body><p>{inner}</p></body></article>".encode())
    assert article.sections[0].text == expected


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        ("the 20<sup>th</sup> century", "the 20th century"),
        ("whey<sup>†</sup> and casein", "whey† and casein"),
    ],
)
def test_ordinal_and_note_superscripts_get_no_caret(inner, expected):
    """Ordinals and note marks in superscript are not exponents, so no "^" is added."""
    article = parse_article(f"<article><body><p>{inner}</p></body></article>".encode())
    assert article.sections[0].text == expected


def test_chunks_never_share_a_list_of_extra_metadata(parsed):
    """Each chunk gets its own copy of a list in the extra metadata (e.g. corrected_by)."""
    chunks = chunk_article(parsed, make_source(), {"corrected_by": ["18a"]})
    chunks[0].metadata["corrected_by"].append("changed")
    assert all(c.metadata["corrected_by"] == ["18a"] for c in chunks[1:])
