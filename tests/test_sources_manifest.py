"""Tests for the source manifest (data/sources.json) against the approved list (docs/SOURCES.md)."""

import json
import re

import pytest

from src import config
from src.rag.sources import ManifestError, Source, load_manifest

SOURCES_MD = config.PROJECT_ROOT / "docs" / "SOURCES.md"


def approved_rows() -> dict[str, dict]:
    """Return the Approved articles of docs/SOURCES.md: tier, year, licence and PMCID per ID."""
    rows = {}
    tier = None
    in_approved = False
    for line in SOURCES_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_approved = line.strip() == "## Approved"
        elif line.startswith("### "):
            match = re.match(r"### Tier (\d)", line)
            tier = int(match.group(1)) if match else None
        elif in_approved and tier and (match := re.match(r"\| (\d+a?) \|", line)):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[match.group(1)] = {
                "tier": tier,
                "year": int(re.match(r"\d{4}", cells[2]).group(0)),
                "license": re.search(r"CC BY \d\.\d|CC0 1\.0", line).group(0),
                "pmcid": re.search(r"PMC\d+", cells[-1]).group(0),
            }
    return rows


@pytest.fixture(scope="module")
def manifest() -> list[Source]:
    """Load the committed manifest once for the module."""
    return load_manifest()


def entry(**changes) -> dict:
    """Return a valid made-up manifest entry, with the given fields changed."""
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
        "topics": ["protein"],
    }
    data.update(changes)
    return data


def write_manifest(tmp_path, entries) -> object:
    """Write a manifest file with the given entries and return its path."""
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_the_approved_list_is_parsed():
    """The parser finds all 21 approved articles (#1-#20 and the correction #18a)."""
    rows = approved_rows()
    assert sorted(rows) == sorted([str(n) for n in range(1, 21)] + ["18a"])


def test_manifest_ids_match_the_approved_list(manifest):
    """The manifest lists exactly the Approved articles of docs/SOURCES.md, by ID."""
    assert sorted(s.id for s in manifest) == sorted(approved_rows())


def test_manifest_matches_the_approved_list_per_article(manifest):
    """Each article's PMCID, year, licence and tier match its row in docs/SOURCES.md."""
    rows = approved_rows()
    for source in manifest:
        row = rows[source.id]
        assert source.pmcid == row["pmcid"], source.id
        assert source.year == row["year"], source.id
        assert source.license == row["license"], source.id
        assert source.evidence_tier == row["tier"], source.id


def test_no_manifest_field_is_empty():
    """Every field of every raw manifest entry is present and not empty."""
    raw = json.loads(config.SOURCES_MANIFEST_PATH.read_text(encoding="utf-8"))
    required = {name for name, field in Source.model_fields.items() if field.is_required()}
    for item in raw:
        assert required <= set(item) <= set(Source.model_fields), item.get("id")
        for field, value in item.items():
            assert value not in ("", [], None), (item["id"], field)
            if isinstance(value, list):
                assert all(str(v).strip() for v in value), (item["id"], field)


def test_manifest_topics_and_tiers_come_from_config(manifest):
    """Topics and tiers use only the values in config."""
    for source in manifest:
        assert set(source.topics) <= set(config.TOPICS)
        assert source.evidence_tier in config.EVIDENCE_TIERS


def test_source_one_comes_from_europe_pmc(manifest):
    """Source #1 has a PMCID, so the script downloads it like the others (O4 not needed)."""
    one = next(s for s in manifest if s.id == "1")
    assert one.pmcid == "PMC13665703"
    assert one.doi == "10.1080/15502783.2026.2740266"


def test_corrections_match_the_approved_list(manifest):
    """Exactly the rows marked "Correction to #N" in docs/SOURCES.md correct source N (#18a)."""
    listed = dict(
        re.findall(r"^\| (\d+a?) \| Correction to #(\d+)", SOURCES_MD.read_text("utf-8"), re.M)
    )
    assert listed == {"18a": "18"}
    assert {s.id: s.corrects for s in manifest if s.corrects} == listed


def test_a_correction_of_a_listed_source_loads(tmp_path):
    """A correction that names another listed source loads with its `corrects` field."""
    corrected = entry()
    correction = entry(
        id="1a",
        pmcid="PMC7654321",
        doi="10.1234/made-up.2",
        url="https://doi.org/10.1234/made-up.2",
    )
    correction["corrects"] = "1"
    loaded = load_manifest(write_manifest(tmp_path, [corrected, correction]))
    assert [s.corrects for s in loaded] == [None, "1"]


@pytest.mark.parametrize("corrects", ["1", "2", "#2", ""])
def test_a_bad_correction_link_is_rejected(tmp_path, corrects):
    """A source that corrects itself, an unlisted source or a malformed ID fails to load."""
    with pytest.raises(ManifestError):
        load_manifest(write_manifest(tmp_path, [entry(corrects=corrects)]))


def test_a_valid_entry_loads(tmp_path):
    """A complete, consistent entry loads into a Source."""
    [source] = load_manifest(write_manifest(tmp_path, [entry()]))
    assert source.pmcid == "PMC1234567"


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "  "},
        {"authors": []},
        {"authors": [""]},
        {"journal": ""},
        {"copyright_notice": ""},
        {"topics": []},
        {"topics": ["steroids"]},
        {"topics": ["protein", "protein"]},
        {"evidence_tier": 3},
        {"pmcid": "12345"},
        {"pmcid": "PMC123/../x"},
        {"doi": "not-a-doi"},
        {"url": "https://example.com/article"},
        {"license": "CC BY-NC 4.0"},
        {"license_url": "https://creativecommons.org/licenses/by/2.0/"},
        {"extra": "field"},
    ],
)
def test_an_invalid_entry_is_rejected(tmp_path, changes):
    """Empty, unknown or inconsistent fields make the manifest fail to load."""
    with pytest.raises(ManifestError):
        load_manifest(write_manifest(tmp_path, [entry(**changes)]))


def test_a_missing_field_is_rejected(tmp_path):
    """An entry without one of the fields fails to load."""
    data = entry()
    del data["copyright_notice"]
    with pytest.raises(ManifestError):
        load_manifest(write_manifest(tmp_path, [data]))


@pytest.mark.parametrize("field", ["id", "pmcid", "doi"])
def test_duplicate_entries_are_rejected(tmp_path, field):
    """Two entries with the same ID, PMCID or DOI fail to load."""
    first = entry()
    second = entry(id="2", pmcid="PMC7654321", doi="10.1234/made-up.2")
    second["url"] = f"https://doi.org/{second['doi']}"
    second[field] = first[field]
    if field == "doi":
        second["url"] = first["url"]
    with pytest.raises(ManifestError):
        load_manifest(write_manifest(tmp_path, [first, second]))


@pytest.mark.parametrize("content", ["", "{}", "[]", "not json"])
def test_a_malformed_manifest_is_rejected(tmp_path, content):
    """A manifest that is not a non-empty JSON list fails to load."""
    path = tmp_path / "sources.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_a_missing_manifest_is_rejected(tmp_path):
    """A manifest file that does not exist gives a ManifestError."""
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "missing.json")


def test_dois_that_differ_only_in_case_are_duplicates(tmp_path):
    """DOIs are case-insensitive, so two entries with the same DOI in other case are rejected."""
    first = entry()
    second = entry(
        id="2", pmcid="PMC7654321", doi="10.1234/MADE-UP.1", url="https://doi.org/10.1234/MADE-UP.1"
    )
    with pytest.raises(ManifestError):
        load_manifest(write_manifest(tmp_path, [first, second]))
