"""Tests that no committed text file still holds git merge conflict markers (T4.5 review)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# The opening and closing markers git writes; "=======" alone is left out, as Markdown can use it
# to underline a heading.
MARKER = re.compile(r"^(<<<<<<<|>>>>>>>)( |$)", re.MULTILINE)
# Binary files git tracks here (fonts, screenshots).
BINARY_SUFFIXES = {".ttf", ".jpg", ".jpeg", ".png", ".pdf", ".ico"}


def marker_lines(text: str) -> list[int]:
    """Return the line numbers (from 1) of conflict markers in a text."""
    return [text.count("\n", 0, match.start()) + 1 for match in MARKER.finditer(text)]


def _tracked_text_files() -> list[Path]:
    """Return the repository's tracked files that are not binary."""
    try:
        # git writes the names as UTF-8 (unquoted with -z), whatever the locale's encoding.
        listed = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, encoding="utf-8"
        ).stdout
    except OSError, subprocess.CalledProcessError:
        pytest.skip("git is not available here")
    paths = [ROOT / name for name in listed.split("\0") if name]
    return [path for path in paths if path.suffix.lower() not in BINARY_SUFFIXES]


def test_no_tracked_file_has_conflict_markers():
    """A merge left unresolved would put its markers on main and into the course repository."""
    found = {}
    for path in _tracked_text_files():
        if not path.is_file():
            continue
        lines = marker_lines(path.read_text(encoding="utf-8", errors="replace"))
        if lines:
            found[str(path.relative_to(ROOT))] = lines
    assert found == {}


def test_both_markers_are_found_with_their_line_numbers():
    """The opening and closing markers are found, alone on a line or with a ref after them."""
    text = "keep\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> origin/main\n>>>>>>>\n"
    assert marker_lines(text) == [2, 6, 7]


def test_similar_text_is_not_a_marker():
    """A Markdown underline, a quote or arrows inside a line are not markers."""
    text = "Title\n=======\n> quote\nsee a <<<<<<< b\n<<<<<<<<< nine\n"
    assert marker_lines(text) == []
