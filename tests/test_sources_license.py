"""Tests for the licence and DOI check on article XML (fixtures are tiny made-up documents)."""

import pyexpat
import xml.etree.ElementTree as ET

import pytest

from src import config
from src.rag.sources import LicenseRefused, Source, check_article, read_doi, read_license

FIXTURES = config.PROJECT_ROOT / "tests" / "fixtures" / "jats"

ARTICLE = """<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ali="http://www.niso.org/schemas/ali/1.0/">
  <front><article-meta>
    <article-id pub-id-type="doi">10.1234/made-up.1</article-id>
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
    ],
    ids=["license-href", "ali-ref", "ext-link-legalcode", "plain-text-deed", "uri"],
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
