"""The README capture script's address check and its limits, with no browser started (T9.27)."""

import ast
import sys
from datetime import date
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scripts import capture_media

SCRIPT = Path(capture_media.__file__)


@pytest.mark.parametrize("url", ["http://localhost:8501", "http://localhost:8501/"])
def test_the_local_app_is_allowed(url):
    """Only the local app's address passes, given with or without the final slash."""
    assert capture_media.check_app_url(url) == "http://localhost:8501/"


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost:8501",
        "http://localhost:8502",
        "http://localhost",
        "http://127.0.0.1:8501",
        "http://[::1]:8501",
        "http://localhost.example.com:8501",
        "http://localhost:8501@example.com",
        "http://user:pass@localhost:8501",
        "http://localhost:8501/clients",
        "http://localhost:8501/?page=x",
        "http://localhost:8501/#x",
        "http://localhost:99999",
        "http://example.com",
        "localhost:8501",
        "",
    ],
)
def test_any_other_address_is_refused(url):
    """Another scheme, host, port, path, user or a trick in the address is refused."""
    with pytest.raises(ValueError):
        capture_media.check_app_url(url)


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("http://localhost:8501/static/js/main.js", True),
        ("https://localhost:8501/", False),
        ("https://fonts.googleapis.com/css", False),
        ("http://localhost:8502/", False),
        ("http://localhost:8501@example.com/", False),
        ("http://example.com/x.png", False),
    ],
)
def test_the_browser_reaches_only_the_local_app(url, allowed):
    """Every HTTP request the page makes off the local app is aborted."""
    assert capture_media.is_app_request(url) is allowed


def test_a_refused_address_starts_nothing(monkeypatch, tmp_path, capsys):
    """A wrong address stops the run before Playwright is imported or a folder is written."""
    monkeypatch.setitem(sys.modules, "playwright", None)  # importing it would fail
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    monkeypatch.setattr(capture_media, "OUTPUT_ROOT", tmp_path / "capture")
    tool = tmp_path / "tool.exe"
    tool.write_text("")
    code = capture_media.main(
        ["--url", "http://example.com", "--browser", str(tool), "--ffmpeg", str(tool)]
    )
    assert code == 2
    assert "localhost:8501" in capsys.readouterr().err
    assert not (tmp_path / "capture").exists()


def test_a_missing_tool_starts_nothing(monkeypatch, tmp_path):
    """A browser or FFmpeg path that is not a file stops the run before anything is written."""
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setattr(capture_media, "OUTPUT_ROOT", tmp_path / "capture")
    missing = str(tmp_path / "missing.exe")
    assert capture_media.main(["--browser", missing, "--ffmpeg", missing]) == 2
    assert not (tmp_path / "capture").exists()


def test_playwright_is_imported_only_where_the_browser_starts():
    """No top-level import of Playwright, so the script's tests run in CI without it."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    top = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    names = [alias.name for node in top for alias in node.names]
    names += [node.module or "" for node in top if isinstance(node, ast.ImportFrom)]
    assert not any(name.startswith("playwright") for name in names)


def test_the_script_never_reads_the_key_secrets_or_store():
    """The script imports nothing of the app and no code of it names the key, secrets or store."""
    # Nothing of `src`, not even its logging set-up, which reads the secrets file (owner's
    # decision, 2026-11-09, code review round 2).
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    # The module docstring explains these words; the code may not use them.
    tree.body = tree.body[1:]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules = [alias.name for alias in node.names] + [getattr(node, "module", "") or ""]
            assert not any(
                m.split(".")[0] in {"src", "scripts", "streamlit", "tomllib", "os", "importlib"}
                for m in modules
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.lower()
            words = ("secret", "openrouter", "api_key", "data/store", ".sqlite")
            assert not any(word in text for word in words)
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert name not in {"environ", "getenv", "secrets", "get_api_key", "__import__"}


def test_the_output_folder_is_gitignored():
    """The screenshots, frames and GIF go to data/capture/, which .gitignore names."""
    root = Path(__file__).resolve().parents[1]
    assert capture_media.OUTPUT_ROOT == root / "data" / "capture"
    ignored = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/capture/" in ignored


@pytest.mark.parametrize(
    ("today", "monday"),
    [
        (date(2026, 11, 9), date(2026, 11, 2)),  # a Monday
        (date(2026, 11, 15), date(2026, 11, 2)),  # a Sunday
        (date(2026, 11, 11), date(2026, 11, 2)),
    ],
)
def test_the_review_week_is_last_week(today, monday):
    """The week picked for the review is the Monday of the week before today's."""
    assert capture_media.last_monday(today) == monday


def _image(path: Path, box: tuple[int, int, int, int] | None = None) -> Path:
    """Write a white 200x200 PNG, with a black rectangle at `box` if given."""
    image = Image.new("RGB", (200, 200), "white")
    if box is not None:
        ImageDraw.Draw(image).rectangle(box, fill="black")
    image.save(path)
    return path


def test_only_a_frame_that_changed_is_kept(tmp_path):
    """A frame like the last one, or with only a spinner-sized change, is dropped from the GIF."""
    blank = _image(tmp_path / "a.png")
    assert not capture_media.changed(blank, _image(tmp_path / "b.png"))
    assert not capture_media.changed(blank, _image(tmp_path / "c.png", (10, 10, 25, 25)))
    assert capture_media.changed(blank, _image(tmp_path / "d.png", (10, 10, 120, 80)))


def test_the_gif_command_fits_the_readme_limit(tmp_path):
    """FFmpeg is called with a list (no shell), and the GIF is cut at most at 10 seconds."""
    command = capture_media.gif_command(Path("ffmpeg.exe"), tmp_path, 120, tmp_path / "a.gif")
    assert all(isinstance(part, str) for part in command)
    assert float(command[command.index("-t") + 1]) <= 10
    assert command[-1].endswith("a.gif")
