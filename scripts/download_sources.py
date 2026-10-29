"""Download the approved articles' XML from the Europe PMC REST API into data/raw/.

Run from the repo root (no API key needed):

    python scripts/download_sources.py

Only the Europe PMC REST API is used: its terms allow automated retrieval, while the PMC,
Europe PMC and publisher websites must never be scripted (copyright policy rule 10). Requests
carry a descriptive User-Agent and are spaced out. Each file is kept only if its own licence
block says CC BY or CC0 and matches the manifest, and its DOI and its authors (editors left out,
T9.21) match too; a refused file is not written (and an older copy of it is deleted). data/raw/ is
gitignored (rule 8).
"""

import http.client
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src import config, observability
from src.rag.sources import ManifestError, Source, check_article, load_manifest


class FetchError(RuntimeError):
    """Raised when an article could not be downloaded."""


def fulltext_url(source: Source) -> str:
    """Return the Europe PMC REST URL of the source's full-text XML (PMCID checked by Source)."""
    return config.EUROPE_PMC_FULLTEXT_URL.format(pmcid=source.pmcid)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses to follow redirects, so no request ever leaves the Europe PMC REST API."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Return None, which makes urllib raise the 3xx as an HTTPError instead of following it."""
        return None


# A redirect could lead to a publisher's website, which must never be scripted (copyright rule 10).
OPENER = urllib.request.build_opener(NoRedirect())


def fetch(url: str) -> bytes:
    """GET the URL with our User-Agent and return the body, capped at DOWNLOAD_MAX_BYTES."""
    request = urllib.request.Request(
        url, headers={"User-Agent": config.DOWNLOAD_USER_AGENT, "Accept": "application/xml"}
    )
    try:
        with OPENER.open(request, timeout=config.DOWNLOAD_TIMEOUT_SECONDS) as response:
            body = response.read(config.DOWNLOAD_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}") from None
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError(f"could not reach Europe PMC ({type(exc).__name__})") from None
    if len(body) > config.DOWNLOAD_MAX_BYTES:
        raise FetchError(f"the file is larger than {config.DOWNLOAD_MAX_BYTES} bytes")
    return body


@dataclass
class Report:
    """What happened to each source in one run."""

    saved: list[str] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every source was saved."""
        return not self.refused and not self.failed


def raw_path(source: Source, raw_dir: Path) -> Path:
    """Return where the source's XML is kept."""
    return raw_dir / f"{source.pmcid}.xml"


def download_all(
    sources: list[Source],
    raw_dir: Path | None = None,
    fetch: Callable[[str], bytes] = fetch,
    sleep: Callable[[float], None] = time.sleep,
) -> Report:
    """Download, check and save each source's XML, pausing between requests."""
    raw_dir = raw_dir or config.RAW_SOURCES_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    report = Report()
    for index, source in enumerate(sources):
        if index:
            sleep(config.DOWNLOAD_PAUSE_SECONDS)
        try:
            xml = fetch(fulltext_url(source))
        except FetchError as exc:
            report.failed.append((source.id, str(exc)))
            continue
        path = raw_path(source, raw_dir)
        reason = check_article(xml, source)
        if reason:
            report.refused.append((source.id, reason))
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                report.failed.append(
                    (source.id, f"could not delete the older copy ({type(exc).__name__})")
                )
            continue
        try:
            path.write_bytes(xml)
        except OSError as exc:
            report.failed.append((source.id, f"could not write the file ({type(exc).__name__})"))
            continue
        report.saved.append(source.id)
    return report


def format_report(report: Report) -> list[str]:
    """Return the lines to print for a run."""
    lines = [f"Saved {len(report.saved)} article(s): {', '.join(report.saved) or '-'}"]
    lines += [f"REFUSED #{sid}: {reason}" for sid, reason in report.refused]
    lines += [f"FAILED #{sid}: {reason}" for sid, reason in report.failed]
    return lines


def main() -> int:
    """Download every source in the manifest; return 0 if all were saved, 1 otherwise."""
    observability.configure_logging()
    try:
        sources = load_manifest()
    except ManifestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    report = download_all(sources)
    for line in format_report(report):
        print(line, file=sys.stdout if line.startswith("Saved") else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
