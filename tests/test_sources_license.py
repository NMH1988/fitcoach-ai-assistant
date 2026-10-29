"""Tests for the licence and DOI check on article XML (fixtures are tiny made-up documents)."""

import pyexpat
import xml.etree.ElementTree as ET

import pytest

from src import config
from src.rag.sources import (
    LicenseRefused,
    Source,
    authors_mismatch,
    check_article,
    read_authors,
    read_doi,
    read_license,
)

FIXTURES = config.PROJECT_ROOT / "tests" / "fixtures" / "jats"

ARTICLE = """<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ali="http://www.niso.org/schemas/ali/1.0/">
  <front><article-meta>
    <article-id pub-id-type="doi">10.1234/made-up.1</article-id>
    <contrib-group><contrib><name><surname>Example</surname><given-names>Ann</given-names></name></contrib></contrib-group>
    <permissions>{permissions}</permissions>
  </article-meta></front>
  <body><sec><title>Test</title><p>Made-up text for a test.</p></sec></body>
</article>"""


def article(license_block: str) -> ET.Element:
    """Parse a made-up article whose <permissions> hold the given licence markup."""
    return ET.fromstring(ARTICLE.format(permissions=license_block))


def source(**changes) -> Source:
    """Return a made-up manifest entry matching the cc_by.xml fixture, with fields changed."""
    data = {
        "id": "1",
        "title": "A made-up article about oats",
        "authors": ["Ann Example"],
        "year": 2024,
        "journal": "Journal of Made-up Results",
        "doi": "10.1234/made-up.1",
        "pmcid": "PMC1234567",
        "url": "https://doi.org/10.1234/made-up.1",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "copyright_notice": "© The Author(s) 2024",
        "evidence_tier": 1,
        "topics": ["carbohydrate"],
    }
    data.update(changes)
    return Source.model_validate(data)


def fixture(name: str) -> bytes:
    """Read a fixture XML file as bytes."""
    return (FIXTURES / name).read_bytes()


def test_cc_by_fixture_is_accepted():
    """A CC BY article whose licence and DOI match the manifest passes the check."""
    assert check_article(fixture("cc_by.xml"), source()) is None


def test_cc_by_with_a_cc0_data_waiver_counts_as_cc_by():
    """CC BY wins over the CC0 waiver for data that BioMed Central articles add."""
    found = read_license(ET.fromstring(fixture("cc_by.xml")))
    assert found.name == "CC BY 4.0"
    assert found.url == "https://creativecommons.org/licenses/by/4.0/"


@pytest.mark.parametrize("name", ["cc_by_nc.xml", "no_license.xml"])
def test_fixture_without_cc_by_or_cc0_is_refused(name):
    """An NC licence or no licence at all refuses the article, with a reason."""
    reason = check_article(fixture(name), source())
    assert reason
    assert "licen" in reason


@pytest.mark.parametrize(
    "block",
    [
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>x</license-p>'
        "</license>",
        "<license><ali:license_ref>http://creativecommons.org/licenses/by/4.0</ali:license_ref>"
        "</license>",
        '<license><license-p>See <ext-link xlink:href="https://www.creativecommons.org/licenses/'
        'by/4.0/legalcode">the licence</ext-link>.</license-p></license>',
        "<license><license-p>Licensed under https://creativecommons.org/licenses/by/4.0/deed.en."
        "</license-p></license>",
        '<license><license-p><uri xlink:href="http://creativecommons.org/licenses/by/4.0/">CC BY'
        "</uri></license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/deed.en_US"></license>',
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/?ref=chooser-v1">'
        "</license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/#ref-appropriate-credit">'
        "</license>",
        # Ordinary words that only look like the restrictive ones.
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>Reuse is '
        "permitted by anyone, including commercially, provided the work is cited (see Nondas "
        "et al.).</license-p></license>",
    ],
    ids=[
        "license-href",
        "ali-ref",
        "ext-link-legalcode",
        "plain-text-deed",
        "uri",
        "deed-with-region",
        "chooser-query",
        "fragment",
        "harmless-wording",
    ],
)
def test_cc_by_is_found_in_every_markup(block):
    """CC BY 4.0 is read from an href, an ali:license_ref, a link or plain text."""
    assert read_license(article(block)).name == "CC BY 4.0"


def test_cc_by_2_0_is_read_with_its_version():
    """An older CC BY version keeps its own version and canonical URL."""
    found = read_license(
        article('<license xlink:href="http://creativecommons.org/licenses/by/2.0"></license>')
    )
    assert found.name == "CC BY 2.0"
    assert found.url == "https://creativecommons.org/licenses/by/2.0/"


def test_cc0_alone_is_accepted():
    """A CC0 article is allowed, as the policy says."""
    block = "<license><ali:license_ref>https://creativecommons.org/publicdomain/zero/1.0/</ali:license_ref></license>"
    assert read_license(article(block)).name == "CC0 1.0"


@pytest.mark.parametrize(
    "block",
    [
        '<license xlink:href="https://creativecommons.org/licenses/by-nc/4.0/"></license>',
        '<license xlink:href="https://creativecommons.org/licenses/by-nd/4.0/"></license>',
        '<license xlink:href="https://creativecommons.org/licenses/by-sa/4.0/"></license>',
        '<license xlink:href="https://creativecommons.org/licenses/by-nc-nd/4.0/"></license>',
        # A CC BY link next to an NC one is ambiguous: refused.
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "Text and data mining: https://creativecommons.org/licenses/by-nc/4.0/</license-p>"
        "</license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "Also http://creativecommons.org/licenses/by/3.0/</license-p></license>",
        "<license><license-p>Free to read on our website.</license-p></license>",
        # A publisher's own licence ID is unknown, even with a CC BY URL in the text.
        '<license xlink:href="https://publisher.example/custom-terms"><license-p>Text mining '
        "permitted under https://creativecommons.org/licenses/by/4.0/</license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"></license>'
        "<license><ali:license_ref>https://publisher.example/tdm</ali:license_ref></license>",
        # Wording that contradicts the CC BY link.
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "Creative Commons Attribution-NonCommercial licence.</license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "All rights reserved.</license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "This article is licensed under CC BY-NC 4.0.</license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "Creative Commons Attribution Non Commercial licence.</license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "Attribution-Non‐Commercial-No‑Derivatives licence.</license-p></license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>'
        "Licensed under CC BY SA 4.0.</license-p></license>",
        '<license license-type="cc-by-nd" xlink:href="https://creativecommons.org/licenses/by/4.0/">'
        "</license>",
        '<license xlink:href="https://creativecommons.org/licenses/by/3.0/us/"></license>',
        '<license xlink:href="https://example.org/our-own-licence"></license>',
        "",
    ],
    ids=[
        "nc",
        "nd",
        "sa",
        "nc-nd",
        "by-and-nc",
        "two-versions",
        "no-url",
        "publisher-id-with-cc-text",
        "second-license-publisher-ref",
        "noncommercial-wording",
        "all-rights-reserved-wording",
        "by-nc-abbreviation",
        "non-commercial-with-space",
        "unicode-hyphens",
        "by-sa-with-space",
        "license-type-nd",
        "ported-licence",
        "other-url",
        "none",
    ],
)
def test_other_licences_are_refused(block):
    """NC, ND, SA, mixed, unknown or missing licences raise LicenseRefused."""
    with pytest.raises(LicenseRefused):
        read_license(article(block))


def test_licence_must_match_the_manifest():
    """A CC BY 2.0 article listed as CC BY 4.0 in the manifest is refused."""
    xml = ARTICLE.format(
        permissions='<license xlink:href="http://creativecommons.org/licenses/by/2.0/"></license>'
    ).encode()
    reason = check_article(xml, source())
    assert reason == "the article says CC BY 2.0 but the manifest says CC BY 4.0"


def test_doi_must_match_the_manifest():
    """An article whose DOI is not the manifest's (e.g. a wrong PMCID) is refused."""
    reason = check_article(
        fixture("cc_by.xml"), source(doi="10.1234/other", url="https://doi.org/10.1234/other")
    )
    assert reason and "DOI" in reason


def test_doi_is_compared_without_case():
    """DOIs are case-insensitive, so a case difference is not a mismatch."""
    upper = source(doi="10.1234/MADE-UP.1", url="https://doi.org/10.1234/MADE-UP.1")
    assert check_article(fixture("cc_by.xml"), upper) is None


def test_missing_doi_is_refused():
    """An article with no DOI cannot be matched to the manifest and is refused."""
    xml = fixture("cc_by.xml").replace(b'pub-id-type="doi"', b'pub-id-type="other"')
    assert read_doi(ET.fromstring(xml)) is None
    assert "DOI" in check_article(xml, source())


@pytest.mark.parametrize("xml", [b"", b"<article>", b"<html><body>Not found</body></html>"])
def test_broken_or_foreign_files_are_refused(xml):
    """Invalid XML, or XML that is not a JATS article, is refused."""
    assert check_article(xml, source())


def test_licence_in_a_sub_article_does_not_count():
    """Only the article's own front matter counts, not a licence deeper in the file."""
    xml = (
        b'<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>'
        b'<article-id pub-id-type="doi">10.1234/made-up.1</article-id></article-meta></front>'
        b'<sub-article><front-stub><permissions><license xlink:href="https://creativecommons.org/'
        b'licenses/by/4.0/"/></permissions></front-stub></sub-article></article>'
    )
    assert "no <license>" in check_article(xml, source())


def test_expat_limits_entity_expansion():
    """The XML parser's expat is 2.4.1 or newer, which limits billion-laughs expansion."""
    version = tuple(int(part) for part in pyexpat.version_info)
    assert version >= (2, 4, 1)


def test_explanatory_links_in_the_licence_text_are_not_refused():
    """A non-CC link inside the licence prose (e.g. to the journal's policy) does not refuse."""
    block = (
        '<license xlink:href="https://creativecommons.org/licenses/by/4.0/"><license-p>See our '
        '<ext-link xlink:href="https://journal.example/open-access">open access policy</ext-link>.'
        "</license-p></license>"
    )
    assert read_license(article(block)).name == "CC BY 4.0"


CC0_BLOCK = (
    "<license><ali:license_ref>https://creativecommons.org/publicdomain/zero/1.0/"
    "</ali:license_ref></license>"
)


def test_cc0_article_listed_as_cc0_is_accepted():
    """A CC0 article whose manifest entry says CC0 1.0 passes the check."""
    xml = ARTICLE.format(permissions=CC0_BLOCK).encode()
    cc0 = source(
        license="CC0 1.0", license_url="https://creativecommons.org/publicdomain/zero/1.0/"
    )
    assert check_article(xml, cc0) is None


def test_cc0_only_article_listed_as_cc_by_is_refused():
    """A file with only a CC0 waiver does not pass for a source the manifest lists as CC BY."""
    xml = ARTICLE.format(permissions=CC0_BLOCK).encode()
    assert (
        check_article(xml, source()) == "the article says CC0 1.0 but the manifest says CC BY 4.0"
    )


# The author check (T9.21). Every name below is made up for the tests.
AUTHORS_ARTICLE = """<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front><article-meta>
    <article-id pub-id-type="doi">10.1234/made-up.1</article-id>
    {groups}
    <permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"/></permissions>
  </article-meta></front>
</article>"""


def person(given: str, surname: str, attributes: str = "", roles: str = "") -> str:
    """Return the JATS markup of one made-up contributor with a name and optional roles."""
    name = f"<name><surname>{surname}</surname><given-names>{given}</given-names></name>"
    return f"<contrib{attributes}>{name}{roles}</contrib>"


def authors_xml(*groups: str) -> bytes:
    """Return a made-up CC BY article whose front matter holds the given contributor groups."""
    return AUTHORS_ARTICLE.format(groups="".join(groups)).encode()


ANN_AND_BEN = (
    '<contrib-group content-type="author">'
    + person("Ann B.", "Example", ' contrib-type="author"')
    + person("Ben", "Sample", ' contrib-type="author"')
    + "</contrib-group>"
)


def test_the_article_authors_in_order_with_dotted_initials_match():
    """Names match without case, dots or extra spaces, so "Ann B." equals the manifest's "Ann B"."""
    assert read_authors(ET.fromstring(authors_xml(ANN_AND_BEN))) == ["Ann B. Example", "Ben Sample"]
    assert (
        check_article(authors_xml(ANN_AND_BEN), source(authors=["ann b  example", "Ben Sample"]))
        is None
    )


def test_names_are_compared_in_one_unicode_form():
    """A composed and a decomposed accent are the same letter."""
    xml = authors_xml(f"<contrib-group>{person('Jos\u00e9', 'Example')}</contrib-group>")
    assert check_article(xml, source(authors=["Jose\u0301 Example"])) is None


def test_an_author_the_manifest_lacks_is_refused_and_named():
    """An extra author in the article is named in the reason."""
    reason = check_article(authors_xml(ANN_AND_BEN), source(authors=["Ann B Example"]))
    assert (
        reason == "the article's authors are not the manifest's (not in the manifest: Ben Sample)"
    )


def test_an_author_the_article_lacks_is_refused_and_named():
    """A manifest author the article does not list is named, next to the article's extra one."""
    reason = check_article(authors_xml(ANN_AND_BEN), source(authors=["Ann B Example", "Cy Third"]))
    assert reason == (
        "the article's authors are not the manifest's "
        "(not in the article: Cy Third; not in the manifest: Ben Sample)"
    )


def test_the_same_authors_in_another_order_are_refused():
    """The attribution lists authors in the article's order, so another order is a mismatch."""
    reason = check_article(
        authors_xml(ANN_AND_BEN), source(authors=["Ben Sample", "Ann B Example"])
    )
    assert reason == "the article lists the manifest's authors in another order"


def test_an_academic_editor_group_is_left_out():
    """An MDPI-style editor group with an "Academic Editor" role is not part of the authors."""
    editors = (
        '<contrib-group content-type="editor">'
        + person("Eve", "Editorial", ' contrib-type="editor"', "<role>Academic Editor</role>")
        + "</contrib-group>"
    )
    xml = authors_xml(ANN_AND_BEN, editors)
    assert read_authors(ET.fromstring(xml)) == ["Ann B. Example", "Ben Sample"]
    assert check_article(xml, source(authors=["Ann B Example", "Ben Sample"])) is None
    # The T9.19 mistake: the editor listed as an author in the manifest is refused.
    with_editor = source(authors=["Ann B Example", "Ben Sample", "Eve Editorial"])
    assert "not in the article: Eve Editorial" in check_article(xml, with_editor)


@pytest.mark.parametrize(
    "contributor",
    [
        person("Eve", "Editorial", ' contrib-type="editor"'),
        person("Eve", "Editorial", "", "<role>Academic Editor</role>"),
        person("Eve", "Editorial", "", "<role>Guest editors</role>"),
    ],
)
def test_an_editor_inside_the_author_group_is_left_out(contributor):
    """A contrib-type of editor, or a role naming an editor, leaves the contributor out."""
    xml = authors_xml(f"<contrib-group>{person('Ann', 'Example')}{contributor}</contrib-group>")
    assert read_authors(ET.fromstring(xml)) == ["Ann Example"]


def test_a_credit_review_and_editing_role_keeps_the_author():
    """A CRediT role such as "Writing – review & editing" names no editor."""
    roles = "<role>Conceptualization</role><role>Writing \u2013 review &amp; editing</role>"
    xml = authors_xml(f"<contrib-group>{person('Ann', 'Example', '', roles)}</contrib-group>")
    assert check_article(xml, source(authors=["Ann Example"])) is None


def test_an_article_with_no_author_is_refused():
    """An article whose front matter names no author cannot be matched and is refused."""
    assert check_article(authors_xml(), source()) == "the article names no author"


def test_contributors_outside_the_article_meta_do_not_count():
    """Only the article's own front matter counts, not a contributor in a sub-article."""
    xml = authors_xml().replace(
        b"</article>",
        f"<sub-article><front-stub><contrib-group>{person('Ann', 'Example')}"
        "</contrib-group></front-stub></sub-article></article>".encode(),
    )
    assert check_article(xml, source()) == "the article names no author"


def test_a_group_author_is_its_collab_text():
    """A group author (<collab>) is compared by its name."""
    xml = authors_xml(
        "<contrib-group><contrib><collab>The Made-up Oats Group</collab></contrib></contrib-group>"
    )
    assert check_article(xml, source(authors=["The Made-up Oats Group"])) is None


def test_a_group_author_with_a_nested_member_list_is_its_own_name():
    """The members JATS may list inside a <collab> are not part of the group's name."""
    members = f"<contrib-group>{person('Ann', 'Example')}</contrib-group>"
    xml = authors_xml(
        "<contrib-group><contrib><collab>The Made-up Oats Group"
        f"{members}</collab></contrib></contrib-group>"
    )
    assert check_article(xml, source(authors=["The Made-up Oats Group"])) is None


@pytest.mark.parametrize(
    "contributor",
    [
        "<contrib><name-alternatives><name><surname>Example</surname>"
        "<given-names>Ann</given-names></name><name><surname>Beispiel</surname>"
        "<given-names>Anna</given-names></name></name-alternatives></contrib>",
        "<contrib><string-name>Ann Example</string-name></contrib>",
    ],
    ids=["name-alternatives", "string-name"],
)
def test_a_name_in_name_alternatives_or_a_string_name_is_read(contributor):
    """The first <name> of <name-alternatives>, or a <string-name>, is the contributor's name."""
    xml = authors_xml(f"<contrib-group>{contributor}</contrib-group>")
    assert read_authors(ET.fromstring(xml)) == ["Ann Example"]
    assert check_article(xml, source(authors=["Ann Example"])) is None


def test_a_contributor_with_no_name_is_refused_with_a_placeholder():
    """An author with no name never matches, and the reason says so without an empty name."""
    xml = authors_xml(f"<contrib-group>{person('Ann', 'Example')}<contrib/></contrib-group>")
    reason = check_article(xml, source(authors=["Ann Example"]))
    assert reason == (
        "the article's authors are not the manifest's "
        "(not in the manifest: (a contributor with no name))"
    )


def test_a_refusal_shows_no_control_characters():
    """A name from the file is shown with printable characters only."""
    assert authors_mismatch(["Ann\x1b[31m Example"], ["Ann Example"]) == (
        "the article's authors are not the manifest's "
        "(not in the article: Ann Example; not in the manifest: Ann[31m Example)"
    )
