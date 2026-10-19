"""Tests for the ATTRIBUTION.md generator."""

import json

from scripts import generate_attribution
from src import config
from src.rag.sources import CHANGES_MADE, Source, load_manifest, render_attribution


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
    assert generate_attribution.write_attribution(manifest, target) == 1
    assert target.read_bytes() == render_attribution([made_up_source()]).encode("utf-8")


def test_committed_attribution_credits_every_source():
    """ATTRIBUTION.md is up to date with the manifest and credits every approved source."""
    sources = load_manifest()
    committed = config.ATTRIBUTION_PATH.read_text(encoding="utf-8")
    assert committed == render_attribution(sources), "run python scripts/generate_attribution.py"
    for source in sources:
        line = entry_line(committed, source.id)
        assert source.doi in line and source.license_url in line


def test_main_writes_the_file_and_returns_0(monkeypatch, tmp_path, capsys):
    """The command line run writes ATTRIBUTION.md to the configured path."""
    target = tmp_path / "ATTRIBUTION.md"
    monkeypatch.setattr(config, "ATTRIBUTION_PATH", target)
    assert generate_attribution.main() == 0
    assert target.read_text(encoding="utf-8") == render_attribution(load_manifest())
    assert "with 21 sources" in capsys.readouterr().out


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
