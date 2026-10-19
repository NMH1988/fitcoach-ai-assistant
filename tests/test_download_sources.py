"""Tests for scripts/download_sources.py with a mocked HTTP client (no network)."""

import email.message
import io
import re
import urllib.error
import urllib.request
import urllib.response

import pytest

from scripts import download_sources
from src import config
from src.rag.sources import Source, load_manifest

FIXTURES = config.PROJECT_ROOT / "tests" / "fixtures" / "jats"
EUROPE_PMC_REST = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
# The real loop, kept before tests replace download_sources.download_all.
REAL_DOWNLOAD_ALL = download_sources.download_all


def made_up_source(sid: str, pmcid: str) -> Source:
    """Return a made-up source that matches the cc_by.xml fixture's licence and DOI."""
    return Source.model_validate(
        {
            "id": sid,
            "title": "A made-up article about oats",
            "authors": ["Ann Example"],
            "year": 2024,
            "journal": "Journal of Made-up Results",
            "doi": "10.1234/made-up.1",
            "pmcid": pmcid,
            "url": "https://doi.org/10.1234/made-up.1",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "copyright_notice": "© The Author(s) 2024",
            "evidence_tier": 1,
            "topics": ["carbohydrate"],
        }
    )


class FakeFetch:
    """Stands in for the HTTP client: records URLs and returns fixture XML per PMCID."""

    def __init__(self, bodies: dict[str, bytes | Exception] | None = None, default=None):
        """Keep the body (or error) to return for each PMCID, and a default body."""
        self.bodies = bodies or {}
        self.default = default if default is not None else (FIXTURES / "cc_by.xml").read_bytes()
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        """Record the URL and return its body, or raise its error."""
        self.urls.append(url)
        pmcid = url.removeprefix(EUROPE_PMC_REST).removesuffix("/fullTextXML")
        body = self.bodies.get(pmcid, self.default)
        if isinstance(body, Exception):
            raise body
        return body


class FakeSleep:
    """Records the pauses instead of sleeping."""

    def __init__(self):
        """Start with no pauses."""
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        """Record one pause."""
        self.calls.append(seconds)


def test_every_manifest_article_is_fetched_only_from_the_europe_pmc_rest_api(tmp_path):
    """The script asks for each manifest PMCID's fullTextXML from the REST API, and nothing else."""
    sources = load_manifest()
    fake = FakeFetch()
    download_sources.download_all(sources, tmp_path, fetch=fake, sleep=FakeSleep())
    assert fake.urls == [f"{EUROPE_PMC_REST}{s.pmcid}/fullTextXML" for s in sources]
    assert f"{EUROPE_PMC_REST}PMC13665703/fullTextXML" in fake.urls  # source #1 (O4)


def test_requests_are_spaced_out(tmp_path):
    """The script pauses between requests: once less than the number of articles."""
    sources = [
        made_up_source("1", "PMC1"),
        made_up_source("2", "PMC2"),
        made_up_source("3", "PMC3"),
    ]
    sleep = FakeSleep()
    download_sources.download_all(sources, tmp_path, fetch=FakeFetch(), sleep=sleep)
    assert sleep.calls == [config.DOWNLOAD_PAUSE_SECONDS] * 2
    assert config.DOWNLOAD_PAUSE_SECONDS >= 1


def test_accepted_articles_are_saved_under_their_pmcid(tmp_path):
    """A CC BY article whose DOI matches is written to data/raw/<PMCID>.xml."""
    report = download_sources.download_all(
        [made_up_source("1", "PMC1")], tmp_path, fetch=FakeFetch(), sleep=FakeSleep()
    )
    assert report.ok and report.saved == ["1"]
    assert (tmp_path / "PMC1.xml").read_bytes() == (FIXTURES / "cc_by.xml").read_bytes()


@pytest.mark.parametrize("name", ["cc_by_nc.xml", "no_license.xml"])
def test_a_file_without_cc_by_or_cc0_is_refused_and_reported(tmp_path, name, capsys):
    """A non-CC BY file is not written, is reported, and makes the run fail."""
    sources = [made_up_source("1", "PMC1"), made_up_source("2", "PMC2")]
    fake = FakeFetch({"PMC2": (FIXTURES / name).read_bytes()})
    report = download_sources.download_all(sources, tmp_path, fetch=fake, sleep=FakeSleep())
    assert report.saved == ["1"]
    assert [sid for sid, _ in report.refused] == ["2"]
    assert not (tmp_path / "PMC2.xml").exists()
    assert not report.ok
    assert any(line.startswith("REFUSED #2: ") for line in download_sources.format_report(report))


def test_a_refused_file_replaces_no_older_copy(tmp_path):
    """An older copy of an article that is now refused is deleted, not kept."""
    (tmp_path / "PMC1.xml").write_bytes(b"old copy")
    fake = FakeFetch(default=(FIXTURES / "cc_by_nc.xml").read_bytes())
    download_sources.download_all(
        [made_up_source("1", "PMC1")], tmp_path, fetch=fake, sleep=FakeSleep()
    )
    assert not (tmp_path / "PMC1.xml").exists()


def test_a_doi_mismatch_is_refused(tmp_path):
    """A file whose DOI is not the manifest's (wrong PMCID) is refused."""
    other = (FIXTURES / "cc_by.xml").read_bytes().replace(b"10.1234/made-up.1", b"10.1234/other")
    report = download_sources.download_all(
        [made_up_source("1", "PMC1")], tmp_path, fetch=FakeFetch(default=other), sleep=FakeSleep()
    )
    assert report.refused and "DOI" in report.refused[0][1]


def test_a_failed_request_is_reported_and_the_run_goes_on(tmp_path):
    """One failed download does not stop the others; it is reported and fails the run."""
    sources = [made_up_source("1", "PMC1"), made_up_source("2", "PMC2")]
    fake = FakeFetch({"PMC1": download_sources.FetchError("HTTP 404")})
    report = download_sources.download_all(sources, tmp_path, fetch=fake, sleep=FakeSleep())
    assert report.failed == [("1", "HTTP 404")]
    assert report.saved == ["2"]
    assert "FAILED #1: HTTP 404" in download_sources.format_report(report)


class FakeResponse(io.BytesIO):
    """A urlopen response: a byte stream usable as a context manager."""


@pytest.fixture
def urlopen_spy(monkeypatch):
    """Replace the script's opener with a spy that records the request and returns a body."""
    calls = {}

    def fake_urlopen(request, timeout):
        """Record the request and timeout, then return the configured body or error."""
        calls["request"] = request
        calls["timeout"] = timeout
        if isinstance(calls.get("body"), Exception):
            raise calls["body"]
        return FakeResponse(calls.get("body", b"<article/>"))

    monkeypatch.setattr(download_sources.OPENER, "open", fake_urlopen)
    return calls


def test_fetch_sends_a_descriptive_user_agent_and_a_timeout(urlopen_spy):
    """The HTTP request names the project in its User-Agent and has a timeout."""
    url = f"{EUROPE_PMC_REST}PMC1/fullTextXML"
    assert download_sources.fetch(url) == b"<article/>"
    request = urlopen_spy["request"]
    assert request.full_url == url
    assert request.get_method() == "GET"
    agent = request.get_header("User-agent")
    assert agent == config.DOWNLOAD_USER_AGENT
    assert "nutrition-ai-assistant" in agent and "github.com" in agent
    assert urlopen_spy["timeout"] == config.DOWNLOAD_TIMEOUT_SECONDS


def test_fetch_refuses_a_body_over_the_size_cap(urlopen_spy, monkeypatch):
    """A response larger than DOWNLOAD_MAX_BYTES is a FetchError, not a saved file."""
    monkeypatch.setattr(config, "DOWNLOAD_MAX_BYTES", 10)
    urlopen_spy["body"] = b"x" * 11
    with pytest.raises(download_sources.FetchError):
        download_sources.fetch(f"{EUROPE_PMC_REST}PMC1/fullTextXML")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (urllib.error.HTTPError("u", 404, "Not Found", {}, None), "HTTP 404"),
        (urllib.error.HTTPError("u", 302, "Found", {}, None), "HTTP 302"),
        (urllib.error.URLError("no route"), "could not reach Europe PMC (URLError)"),
        (TimeoutError(), "could not reach Europe PMC (TimeoutError)"),
    ],
)
def test_fetch_maps_network_errors(urlopen_spy, error, message):
    """HTTP errors, unreachable hosts and timeouts become a short FetchError message."""
    urlopen_spy["body"] = error
    with pytest.raises(download_sources.FetchError, match=re.escape(message)):
        download_sources.fetch(f"{EUROPE_PMC_REST}PMC1/fullTextXML")


def test_main_returns_1_and_reports_when_an_article_is_refused(monkeypatch, tmp_path, capsys):
    """The command line run exits with 1 and prints the refusal."""
    nc = (FIXTURES / "cc_by_nc.xml").read_bytes()

    def fake_download_all(sources):
        """Run the real loop on two made-up sources with a fake client and no sleep."""
        return REAL_DOWNLOAD_ALL(
            [made_up_source("1", "PMC1"), made_up_source("2", "PMC2")],
            tmp_path,
            fetch=FakeFetch({"PMC2": nc}),
            sleep=FakeSleep(),
        )

    monkeypatch.setattr(download_sources, "download_all", fake_download_all)
    assert download_sources.main() == 1
    out = capsys.readouterr()
    assert "Saved 1 article(s): 1" in out.out
    assert "REFUSED #2" in out.err


def test_main_returns_0_when_all_are_saved(monkeypatch, tmp_path, capsys):
    """The command line run exits with 0 when every article was saved."""

    def fake_download_all(sources):
        """Run the real loop on one made-up source with a fake client and no sleep."""
        return REAL_DOWNLOAD_ALL(
            [made_up_source("1", "PMC1")], tmp_path, fetch=FakeFetch(), sleep=FakeSleep()
        )

    monkeypatch.setattr(download_sources, "download_all", fake_download_all)
    assert download_sources.main() == 0


def test_main_returns_1_for_an_invalid_manifest(monkeypatch, capsys):
    """An invalid manifest stops the run before any request, with exit code 1."""

    def broken_manifest():
        """Fail like load_manifest does on a broken file."""
        raise download_sources.ManifestError("The source manifest must be a non-empty JSON list.")

    def no_download(sources):
        """Fail the test if the script tried to download anything."""
        raise AssertionError("no download expected")

    monkeypatch.setattr(download_sources, "load_manifest", broken_manifest)
    monkeypatch.setattr(download_sources, "download_all", no_download)
    assert download_sources.main() == 1
    assert "Error:" in capsys.readouterr().err


class FakeRedirectingHTTPS(urllib.request.BaseHandler):
    """An HTTPS handler that answers every request with a redirect to a publisher's site."""

    handler_order = 100  # before the real HTTPS handler

    def __init__(self):
        """Start with no requests seen."""
        self.urls: list[str] = []

    def https_open(self, req):
        """Record the URL and answer 302 with a Location on another host."""
        self.urls.append(req.full_url)
        headers = email.message.Message()
        headers["Location"] = "https://publisher.example/article.xml"
        response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, code=302)
        response.msg = "Found"
        return response


def test_the_opener_never_follows_redirects():
    """A redirect from Europe PMC is an error, so no request goes to the redirect target."""
    assert any(isinstance(h, download_sources.NoRedirect) for h in download_sources.OPENER.handlers)
    fake = FakeRedirectingHTTPS()
    opener = urllib.request.build_opener(download_sources.NoRedirect(), fake)
    with pytest.raises(urllib.error.HTTPError) as caught:
        opener.open(f"{EUROPE_PMC_REST}PMC1/fullTextXML", timeout=1)
    assert caught.value.code == 302
    assert fake.urls == [f"{EUROPE_PMC_REST}PMC1/fullTextXML"]


def test_a_file_that_cannot_be_written_is_reported(tmp_path):
    """A write error (disk full, locked file) is reported as a failure, not a crash."""
    blocked = tmp_path / "raw"
    blocked.mkdir()
    (blocked / "PMC1.xml").mkdir()  # a folder where the file should go: write_bytes fails
    report = download_sources.download_all(
        [made_up_source("1", "PMC1")], blocked, fetch=FakeFetch(), sleep=FakeSleep()
    )
    assert report.failed and report.failed[0][0] == "1"
    assert "could not write the file" in report.failed[0][1]


def test_an_older_copy_that_cannot_be_deleted_is_reported(tmp_path):
    """A refused article whose older copy cannot be deleted is reported, not a crash."""
    locked = tmp_path / "PMC1.xml"
    locked.mkdir()  # a folder in its place: unlink fails as on a locked Windows file
    (locked / "keep").write_text("x", encoding="utf-8")
    fake = FakeFetch(default=(FIXTURES / "cc_by_nc.xml").read_bytes())
    report = download_sources.download_all(
        [made_up_source("1", "PMC1")], tmp_path, fetch=fake, sleep=FakeSleep()
    )
    assert [sid for sid, _ in report.refused] == ["1"]
    assert report.failed and "could not delete the older copy" in report.failed[0][1]
