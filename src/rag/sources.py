"""The source manifest, the licence check on article XML and the attribution file.

The manifest (`data/sources.json`) lists the approved articles of `docs/SOURCES.md`. Downloaded
article XML is used only if its own licence block says CC BY or CC0 and matches the manifest
(copyright policy, `.claude/rules/copyright.md`).
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from src import config

# The change made to every article, stated in the attribution as CC BY requires.
CHANGES_MADE = "text extracted and split into chunks"

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
# A Creative Commons URL anywhere in the licence block, as a link or as plain text.
_CC_URL_IN_TEXT = re.compile(r"(?:https?://)?(?:www\.)?creativecommons\.org/[^\s<>\"')]+", re.I)
_CC_BY = re.compile(r"creativecommons\.org/licenses/by/(\d+\.\d+)")
_CC0 = re.compile(r"creativecommons\.org/publicdomain/zero/1\.0")
# Licence wording that contradicts CC BY or CC0, e.g. a CC BY link next to "NonCommercial" text.
_RESTRICTIVE_WORDING = re.compile(
    r"non-?commercial|no-?deriv\w*|share-?alike|all rights reserved", re.IGNORECASE
)


class ManifestError(ValueError):
    """Raised when the source manifest is missing, malformed or inconsistent."""


class Source(BaseModel):
    """One approved article, as listed in the manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, StringConstraints(pattern=r"^\d+[a-z]?$")]
    title: Text
    authors: list[Text] = Field(min_length=1)
    year: int = Field(ge=1900, le=2100)
    journal: Text
    doi: Annotated[str, StringConstraints(pattern=r"^10\.\d{4,9}/\S+$")]
    pmcid: Annotated[str, StringConstraints(pattern=r"^PMC\d+$")]
    url: Text
    license: Annotated[str, StringConstraints(pattern=r"^(CC BY \d+\.\d+|CC0 1\.0)$")]
    license_url: Text
    copyright_notice: Text
    evidence_tier: int
    topics: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Source:
        """Check the URL against the DOI, the licence URL against its name, tier and topics."""
        if self.url != f"https://doi.org/{self.doi}":
            raise ValueError("url must be https://doi.org/<doi>")
        if self.license_url != license_url_for(self.license):
            raise ValueError("license_url does not match license")
        if self.evidence_tier not in config.EVIDENCE_TIERS:
            raise ValueError(f"evidence_tier must be one of {config.EVIDENCE_TIERS}")
        unknown = set(self.topics) - set(config.TOPICS)
        if unknown:
            raise ValueError(f"unknown topics {sorted(unknown)}; allowed: {config.TOPICS}")
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("topics must not repeat")
        return self


def license_url_for(name: str) -> str:
    """Return the canonical Creative Commons URL for "CC BY <version>" or "CC0 1.0"."""
    if name == "CC0 1.0":
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    version = name.removeprefix("CC BY ")
    return f"https://creativecommons.org/licenses/by/{version}/"


def load_manifest(path: Path | None = None) -> list[Source]:
    """Read and validate the manifest (default: config's path); raise ManifestError if wrong."""
    path = path or config.SOURCES_MANIFEST_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read the source manifest {path.name}: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise ManifestError("The source manifest must be a non-empty JSON list.")
    sources = []
    for index, entry in enumerate(raw):
        try:
            sources.append(Source.model_validate(entry))
        except ValidationError as exc:
            raise ManifestError(f"Manifest entry {index} is invalid: {exc}") from exc
    for field in ("id", "pmcid", "doi"):
        # DOIs are case-insensitive, so "10.1/A" and "10.1/a" are the same article.
        values = [str(getattr(source, field)).casefold() for source in sources]
        if len(set(values)) != len(values):
            raise ManifestError(f"Manifest entries must have distinct values for {field!r}.")
    return sources


@dataclass(frozen=True)
class License:
    """A licence found in an article: its name and canonical URL."""

    name: str
    url: str


class LicenseRefused(ValueError):
    """Raised when an article's licence block does not allow us to use it."""


def _normalise_cc_url(url: str) -> str:
    """Reduce a Creative Commons URL to host and path, without scheme, `www.` or deed suffix."""
    value = url.strip().casefold().rstrip(".,;")
    value = re.sub(r"^https?://", "", value).removeprefix("www.")
    value = value.rstrip("/")
    value = re.sub(r"/(legalcode|deed)(\.[a-z-]+)?$", "", value)
    return value.rstrip("/")


def _license_identifiers(license_el: ET.Element) -> list[str]:
    """Return the machine-readable licence IDs of a <license>: its href and any ali:license_ref."""
    found = [license_el.get(_XLINK_HREF, "")]
    found += [
        el.text or ""
        for el in license_el.iter()
        if isinstance(el.tag, str) and el.tag.endswith("license_ref")
    ]
    return [value.strip() for value in found if value.strip()]


def _license_urls(license_el: ET.Element) -> set[str]:
    """Collect the Creative Commons URLs a JATS <license> element names, in any markup."""
    found = _license_identifiers(license_el)
    found += [el.get(_XLINK_HREF) for el in license_el.iter() if el.get(_XLINK_HREF)]
    found += _CC_URL_IN_TEXT.findall(" ".join(license_el.itertext()))
    return {_normalise_cc_url(url) for url in found if "creativecommons.org" in url.casefold()}


# CC BY wins over CC0 when both appear: BioMed Central articles waive copyright on their data with
# CC0 while the text is CC BY. Any other Creative Commons licence (NC, ND, SA), a machine-readable
# licence ID that is not Creative Commons, restrictive wording, or no CC BY or CC0 licence at all
# refuses the whole article ("unknown licence = excluded", copyright policy rule 2).
def read_license(article: ET.Element) -> License:
    """Return the article's licence from its JATS front matter, or raise LicenseRefused."""
    elements = article.findall("front/article-meta/permissions/license")
    if not elements:
        raise LicenseRefused("no <license> element in the article's front matter")
    for el in elements:
        for value in _license_identifiers(el):
            if "creativecommons.org" not in value.casefold():
                raise LicenseRefused(f"the licence is not a Creative Commons licence ({value})")
        if words := _RESTRICTIVE_WORDING.search(" ".join(el.itertext())):
            raise LicenseRefused(f"the licence text says {words.group(0)!r}")
    urls = set().union(*(_license_urls(el) for el in elements))
    by_versions = {m.group(1) for url in urls if (m := _CC_BY.fullmatch(url))}
    cc0 = {url for url in urls if _CC0.fullmatch(url)}
    others = urls - cc0 - {url for url in urls if _CC_BY.fullmatch(url)}
    if others:
        raise LicenseRefused(f"the licence is not CC BY or CC0 ({', '.join(sorted(others))})")
    if len(by_versions) > 1:
        raise LicenseRefused(f"the licence names several CC BY versions ({sorted(by_versions)})")
    if by_versions:
        name = f"CC BY {by_versions.pop()}"
    elif cc0:
        name = "CC0 1.0"
    else:
        raise LicenseRefused("the licence block names no CC BY or CC0 licence")
    return License(name=name, url=license_url_for(name))


def read_doi(article: ET.Element) -> str | None:
    """Return the article's DOI from its JATS front matter, or None if it has none."""
    doi = article.findtext("front/article-meta/article-id[@pub-id-type='doi']")
    return doi.strip() if doi and doi.strip() else None


def check_article(xml: bytes, source: Source) -> str | None:
    """Return why this article XML may not be used for the source, or None if it may."""
    try:
        article = ET.fromstring(xml)
    except ET.ParseError:
        return "the file is not valid XML"
    try:
        found = read_license(article)
    except LicenseRefused as exc:
        return str(exc)
    if found.url != source.license_url:
        return f"the article says {found.name} but the manifest says {source.license}"
    doi = read_doi(article)
    if doi is None or doi.casefold() != source.doi.casefold():
        return f"the article's DOI ({doi}) is not the manifest's ({source.doi})"
    return None


def _md(text: str) -> str:
    """Escape the characters Markdown would read as formatting or HTML."""
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", text)


def _sentence(text: str) -> str:
    """End the text with a full stop unless it already ends with one."""
    return text if text.endswith(".") else f"{text}."


def render_attribution(sources: list[Source]) -> str:
    """Return the text of ATTRIBUTION.md: one CC BY credit per source, in manifest order."""
    lines = [
        "# Attribution",
        "",
        "The knowledge base of this app is built from the open access articles below. Each is "
        "used under its own licence, as stated in the article itself; the licence of this "
        "repository's code does not apply to them.",
        "",
        f"Changes made to every article: {CHANGES_MADE}. No endorsement by the authors, the "
        "journals or the publishers is implied.",
        "",
        "Generated from `data/sources.json` by `python scripts/generate_attribution.py`; do not "
        "edit by hand.",
        "",
        "## Sources",
        "",
    ]
    for s in sources:
        lines.append(
            f"- **[{s.id}]** {_md(_sentence(', '.join(s.authors)))} *{_md(s.title)}*. "
            f"{_md(s.journal)}, {s.year}. DOI: {s.doi} ({s.url}). "
            f"{_md(_sentence(s.copyright_notice))} "
            f"Licensed under {s.license} ({s.license_url}). "
            f"Changes: {CHANGES_MADE}. "
            "No endorsement by the authors or publisher is implied."
        )
    return "\n".join(lines) + "\n"
