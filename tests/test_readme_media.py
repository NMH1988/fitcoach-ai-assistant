"""The README's screenshots and GIF: present, described, and within their size limits (T9.27)."""

import re
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MEDIA = ROOT / "docs" / "media"
STILL_MAX_BYTES = 300 * 1024
GIF_MAX_BYTES = 5 * 1024 * 1024
GIF_MAX_SECONDS = 10.0
# Markdown images, ![alt](path), and HTML ones, <img src="..." alt="...">.
MARKDOWN_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)")
HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')


def readme_images() -> list[tuple[str, str]]:
    """Return every image the README names, as (path from the project folder, alt text) pairs."""
    text = README.read_text(encoding="utf-8")
    found = [(match["src"], match["alt"]) for match in MARKDOWN_IMAGE.finditer(text)]
    for tag in HTML_IMAGE.findall(text):
        attributes = dict(ATTRIBUTE.findall(tag))
        found.append((attributes.get("src", ""), attributes.get("alt", "")))
    return found


def gif_seconds(path: Path) -> float:
    """Return a GIF's length: its frames' durations summed, in seconds."""
    total_ms = 0
    with Image.open(path) as image:
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            total_ms += image.info.get("duration", 0)
    return total_ms / 1000


def test_the_readme_shows_a_gif_and_four_to_six_screenshots():
    """One GIF and 4 to 6 still images, all from docs/media/."""
    paths = [ROOT / src for src, _alt in readme_images()]
    assert all(path.parent == MEDIA for path in paths), paths
    gifs = [path for path in paths if path.suffix == ".gif"]
    stills = [path for path in paths if path.suffix != ".gif"]
    assert len(gifs) == 1
    assert 4 <= len(stills) <= 6


@pytest.mark.parametrize(("src", "alt"), readme_images())
def test_each_image_exists_and_has_alt_text(src, alt):
    """Every image the README names is in the repo and is described for screen readers."""
    assert (ROOT / src).is_file(), src
    assert alt.strip(), src


def test_every_file_in_docs_media_is_shown():
    """No image is committed under docs/media/ that the README does not show."""
    shown = {ROOT / src for src, _alt in readme_images()}
    assert set(MEDIA.iterdir()) == shown


@pytest.mark.parametrize("src", [src for src, _alt in readme_images() if not src.endswith(".gif")])
def test_each_screenshot_is_small(src):
    """Each still image is at most 300 KB."""
    assert (ROOT / src).stat().st_size <= STILL_MAX_BYTES


@pytest.mark.parametrize("src", [src for src, _alt in readme_images() if src.endswith(".gif")])
def test_the_gif_is_short_and_small(src):
    """The GIF is at most 5 MB and plays for at most 10 seconds."""
    path = ROOT / src
    assert path.stat().st_size <= GIF_MAX_BYTES
    assert 0 < gif_seconds(path) <= GIF_MAX_SECONDS
