"""Tests for the ATTRIBUTION.md generator."""

import json

from scripts import generate_attribution
from src import config
from src.rag.sources import (
    CHANGES_MADE,
    FORMULA_CHANGES_MADE,
    Source,
    load_manifest,
    render_attribution,
)
from src.tools.energy import FORMULA_SOURCES
from src.tools.food import read_usda_release

USDA_LINE = "- **USDA FoodData Central.** "


def made_up_foods_table(tmp_path, release="2025-12-18"):
    """Write a foods table whose credit line names the given USDA release; return its path."""
    path = tmp_path / "usda_foods.csv"
    credit = config.USDA_CITATION.format(release=release)
    path.write_text(f"# Source: {credit}\nfdc_id,description\n", encoding="utf-8")
    return path


def made_up_source(**changes) -> Source:
    """Return a made-up source, with the given fields changed."""
    data = {
        "id": "7",
        "title": "A made-up article about oats",
        "authors": ["Ann Example", "Ben Sample"],
        "year": 2024,
        "journal": "Journal of Made-up Results",
        "doi": "10.1234/made-up.1",
        "pmcid": "PMC1234567",
        "url": "https://doi.org/10.1234/made-up.1",
        "license": "CC BY 2.0",
        "license_url": "https://creativecommons.org/licenses/by/2.0/",
        "copyright_notice": "© 2024 Example and Sample; licensee Made-up Press",
        "evidence_tier": 2,
        "topics": ["carbohydrate"],
    }
    data.update(changes)
    return Source.model_validate(data)


def entry_line(text: str, sid: str) -> str:
    """Return the attribution line of the source with this ID."""
    [line] = [line for line in text.splitlines() if line.startswith(f"- **[{sid}]** ")]
    return line


def test_entry_has_every_attribution_element():
    """One entry carries authors, title, journal, year, DOI, notice, licence link and changes."""
    line = entry_line(render_attribution([made_up_source()]), "7")
    assert line == (
        "- **[7]** Ann Example, Ben Sample. *A made-up article about oats*. "
        "Journal of Made-up Results, 2024. DOI: 10.1234/made-up.1 "
        "(https://doi.org/10.1234/made-up.1). "
        "© 2024 Example and Sample; licensee Made-up Press. "
        "Licensed under CC BY 2.0 (https://creativecommons.org/licenses/by/2.0/). "
        f"Changes: {CHANGES_MADE}. No endorsement by the authors or publisher is implied."
    )


def test_notice_keeps_its_own_full_stop():
    """A copyright notice that ends with a full stop does not get a second one."""
    line = entry_line(
        render_attribution([made_up_source(copyright_notice="© 2024 by the authors.")]), "7"
    )
    assert "© 2024 by the authors. Licensed under" in line


def test_markdown_characters_in_titles_are_escaped():
    """A title with "<" or "*" is shown as text, not read as HTML or emphasis."""
    line = entry_line(render_attribution([made_up_source(title="Adults <50 *years*")]), "7")
    assert r"*Adults \<50 \*years\**" in line


def test_header_states_the_change_and_no_endorsement():
    """The file says what was changed and that no endorsement is implied."""
    text = render_attribution([made_up_source()])
    assert text.startswith("# Attribution\n")
    assert f"Changes made to every article: {CHANGES_MADE}." in text
    assert "No endorsement" in text


def test_entries_follow_manifest_order():
    """Sources appear in the order of the manifest."""
    text = render_attribution([made_up_source(id="2"), made_up_source(id="1", pmcid="PMC1")])
    assert text.index("**[2]**") < text.index("**[1]**")


def test_write_attribution_writes_the_rendered_file(tmp_path):
    """The script writes exactly what render_attribution returns, with LF line endings."""
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps([made_up_source().model_dump()], ensure_ascii=False), encoding="utf-8"
    )
    target = tmp_path / "ATTRIBUTION.md"
    foods = made_up_foods_table(tmp_path)
    assert generate_attribution.write_attribution(manifest, target, foods) == 1
    expected = render_attribution(
        [made_up_source()], usda_release="2025-12-18", formula_sources=FORMULA_SOURCES
    )
    assert target.read_bytes() == expected.encode("utf-8")


def test_committed_attribution_credits_every_source():
    """ATTRIBUTION.md is up to date with the manifest and credits every approved source."""
    sources = load_manifest()
    committed = config.ATTRIBUTION_PATH.read_text(encoding="utf-8")
    expected = render_attribution(
        sources, usda_release=read_usda_release(), formula_sources=FORMULA_SOURCES
    )
    assert committed == expected, "run python scripts/generate_attribution.py"
    for source in sources:
        line = entry_line(committed, source.id)
        assert source.doi in line and source.license_url in line


def test_committed_attribution_credits_usda_fooddata_central():
    """ATTRIBUTION.md credits the USDA release that data/usda_foods.csv was made from."""
    committed = config.ATTRIBUTION_PATH.read_text(encoding="utf-8")
    [line] = [line for line in committed.splitlines() if line.startswith(USDA_LINE)]
    assert f"FoodData Central: Foundation Foods, release {read_usda_release()}." in line


def test_usda_entry_has_every_credit_element():
    """The USDA entry carries the citation, release, CC0 link, changes and no endorsement."""
    text = render_attribution([made_up_source()], usda_release="2026-04-30")
    [line] = [line for line in text.splitlines() if line.startswith(USDA_LINE)]
    assert "## Food data" in text
    assert config.USDA_CITATION.format(release="2026-04-30") in line
    assert f"Licence: {config.USDA_LICENSE}, {config.USDA_LICENSE_URL}." in line
    assert f"Changes: {config.USDA_CHANGES}" in line
    assert line.endswith("No endorsement by USDA is implied.")
    assert text.index("## Sources") < text.index("## Food data")


def test_no_usda_entry_without_a_release():
    """Without a USDA release the file credits only the articles."""
    text = render_attribution([made_up_source()])
    assert "## Food data" not in text and USDA_LINE not in text


def test_main_writes_the_file_and_returns_0(monkeypatch, tmp_path, capsys):
    """The command line run writes ATTRIBUTION.md to the configured path."""
    target = tmp_path / "ATTRIBUTION.md"
    monkeypatch.setattr(config, "ATTRIBUTION_PATH", target)
    assert generate_attribution.main() == 0
    expected = render_attribution(
        load_manifest(), usda_release=read_usda_release(), formula_sources=FORMULA_SOURCES
    )
    assert target.read_text(encoding="utf-8") == expected
    assert "with 21 sources" in capsys.readouterr().out


def test_main_returns_1_without_the_foods_table(monkeypatch, tmp_path, capsys):
    """A missing foods table gives an error message and exit code 1, and writes nothing."""
    target = tmp_path / "ATTRIBUTION.md"
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "absent.csv")
    monkeypatch.setattr(config, "ATTRIBUTION_PATH", target)
    assert generate_attribution.main() == 1
    assert "prepare_usda.py" in capsys.readouterr().err
    assert not target.exists()


def test_main_returns_1_for_an_invalid_manifest(monkeypatch, tmp_path, capsys):
    """An invalid manifest gives an error message and exit code 1, and writes nothing."""
    bad = tmp_path / "sources.json"
    bad.write_text("[]", encoding="utf-8")
    target = tmp_path / "ATTRIBUTION.md"
    monkeypatch.setattr(config, "SOURCES_MANIFEST_PATH", bad)
    monkeypatch.setattr(config, "ATTRIBUTION_PATH", target)
    assert generate_attribution.main() == 1
    assert "Error:" in capsys.readouterr().err
    assert not target.exists()


def test_dois_and_urls_cannot_inject_markdown():
    """A DOI with "<" or "*" is escaped as text and percent-encoded in the link."""
    doi = "10.1002/(SICI)1097-4636<45:AID-JBM1>*x"
    line = entry_line(
        render_attribution([made_up_source(doi=doi, url=f"https://doi.org/{doi}")]), "7"
    )
    assert r"DOI: 10.1002/(SICI)1097-4636\<45:AID-JBM1\>\*x " in line
    assert "(https://doi.org/10.1002/%28SICI%291097-4636%3C45:AID-JBM1%3E%2Ax)" in line
    assert "<45" not in line.replace(r"\<45", "")


def test_committed_attribution_credits_the_formula_sources():
    """ATTRIBUTION.md credits sources #22 and #23 with DOI, notice, licence and changes."""
    committed = config.ATTRIBUTION_PATH.read_text(encoding="utf-8")
    assert committed.index("## Food data") < committed.index("## Formula sources")
    for source in FORMULA_SOURCES:
        line = entry_line(committed, source.id)
        assert f"https://doi.org/{source.doi}" in line
        assert source.license_url in line and source.license in line
        assert source.copyright_notice.split(".")[0] in line
        assert f"Changes: {FORMULA_CHANGES_MADE}." in line
        assert line.endswith("No endorsement by the authors or publisher is implied.")


def test_formula_sources_are_ids_22_and_23():
    """The formula sources keep the IDs they have in docs/SOURCES.md."""
    assert [source.id for source in FORMULA_SOURCES] == ["22", "23"]
    sources_md = (config.PROJECT_ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8")
    for source in FORMULA_SOURCES:
        assert f"| {source.id} |" in sources_md and source.doi in sources_md


def test_no_formula_section_without_formula_sources():
    """Without formula sources the file has no formula section."""
    assert "## Formula sources" not in render_attribution([made_up_source()])
