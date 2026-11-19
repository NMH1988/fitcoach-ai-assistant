"""Comments and docstrings say why the code is as it is, not its history (T10.9).

`CLAUDE.md` (code conventions): who decided something, when, and which review round found it go to
the ticket and its PROGRESS entry; the code keeps the reason, and a ticket ID where it points a
reader to the decision. This scan reads every comment (through `tokenize`, consecutive comment lines
joined, so a phrase wrapped over two lines is still found) and every module, class and function
docstring (through `ast`) in `src/`, `views/`, `scripts/` and `app.py`, and fails on three forms:
"review round" with its number, a reviewer agent's name followed by a date, and "owner's choice",
"decision", "request" or "approval" followed by a date. A factual date (a licence's check date, a
measurement's), an undated "owner's choice" and "the review rounds each figure" pass; review checks
the other forms of history. Tests and `.claude/rules/` are not scanned, as their dates and owner's
decisions are records.
"""

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "src", ROOT / "views", ROOT / "scripts", ROOT / "app.py"]

_DATE = r"\b20\d\d-\d\d-\d\d\b"
# Up to 40 characters inside one clause: no sentence end (". "), semicolon or closing bracket.
_SAME_CLAUSE = r"(?:(?!\.\s|;|\)).){0,40}?"
HISTORY_PATTERNS = {
    # A round's number follows ("round 2", "rounds 6 and 7"), so "the review rounds each figure"
    # (a verb) is no review round.
    "a review round": re.compile(r"\breview,?\s+rounds?\s+\d", re.IGNORECASE),
    "a reviewer agent with a date": re.compile(
        r"\b(?:code|security|compliance)-reviewer\b" + _SAME_CLAUSE + _DATE, re.IGNORECASE
    ),
    "an owner's choice with a date": re.compile(
        r"\bowner['\u2019]s\s+(?:choice|decision|request|approval)s?\b" + _SAME_CLAUSE + _DATE,
        re.IGNORECASE,
    ),
}


def _comment_blocks(source: str) -> list[tuple[int, str]]:
    """Return each run of comments on consecutive lines as (first line, joined text)."""
    blocks: list[tuple[int, str]] = []
    last_line = None
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        text = token.string.lstrip("#").strip()
        if last_line is not None and line == last_line + 1:
            first, joined = blocks[-1]
            blocks[-1] = (first, f"{joined} {text}")
        else:
            blocks.append((line, text))
        last_line = line
    return blocks


def _docstrings(source: str) -> list[tuple[int, str]]:
    """Return every module, class and function docstring as (line, text)."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        docstring = ast.get_docstring(node, clean=False)
        if docstring is not None:
            found.append((node.body[0].lineno, docstring))
    return found


def violations(source: str) -> list[str]:
    """Return "line: form" for each comment or docstring that records history."""
    problems = []
    for line, text in _comment_blocks(source) + _docstrings(source):
        flat = " ".join(text.split())
        for form, pattern in HISTORY_PATTERNS.items():
            if pattern.search(flat):
                problems.append(f"{line}: {form}")
    return sorted(problems, key=lambda problem: int(problem.split(":")[0]))


def _scanned_files() -> list[Path]:
    """Return every Python file of the app the rule applies to."""
    files = []
    for path in SCANNED:
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def test_the_app_source_records_no_history_in_comments():
    """No comment or docstring names a review round, a dated reviewer agent or owner's choice."""
    problems = []
    for path in _scanned_files():
        for problem in violations(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(ROOT).as_posix()}:{problem}")
    assert problems == []


def test_the_scan_reads_the_app_folders():
    """The scan covers app.py and modules of src/, views/ and scripts/."""
    scanned = {path.relative_to(ROOT).as_posix() for path in _scanned_files()}
    assert {"app.py", "src/chat/turn.py", "views/tables.py", "scripts/run_evaluation.py"} <= scanned


@pytest.mark.parametrize(
    "source",
    [
        "x = 1  # Kept as it is (code review round 2).\n",
        "# Fixed after the code\n# review round 3 found it.\nx = 1\n",
        "x = 1  # the PDF's columns (code review, round 2)\n",
        "x = 1  # Not a link (security-reviewer, 2026-11-06).\n",
        "x = 1  # Left out (compliance-reviewer, 2026-11-06).\n",
        "x = 1  # One coach at a time (owner's choice, 2026-11-03).\n",
        "x = 1  # English first (owner's choices of 2026-11-02).\n",
        "x = 1  # From the app (owner's choice in T9.3, 2026-10-29).\n",
        "# No log lines (owner's decision,\n# 2026-11-09).\nx = 1\n",
        "x = 1  # Demo traces (T9.35, owner's request, 2026-11-13).\n",
        "x = 1  # Rule 10 (changed with the owner's approval on 2026-11-06).\n",
        '"""A module (owner\'s choice, 2026-11-06)."""\n',
        'def f():\n    """Return one (code review round 1)."""\n    return 1\n',
        'class C:\n    """A class (review rounds 1 and 2)."""\n',
    ],
)
def test_a_history_comment_is_caught(source):
    """A review round, a dated reviewer agent or owner's choice in a comment or docstring fails."""
    assert violations(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "x = 1  # One coach at a time, so a client's data has one reader (T9.12).\n",
        "x = 1  # Licence read on the publisher's page (checked 2026-11-06).\n",
        "x = 1  # Measured on the real index (O5, 2026-10-20, 28 questions).\n",
        "x = 1  # A product decision (owner's choice, T9.5).\n",
        "x = 1  # The owner's choice of model. Measured again on 2026-11-06.\n",
        'def f():\n    """Return a day as "2026-11-02"."""\n    return 1\n',
        'MESSAGE = "code review round 1 (owner\'s choice, 2026-11-06)"\n',
        "x = 1  # The answer step's round 2 reads the tool results.\n",
        "x = 1  # The review rounds each figure to 0.1 kcal.\n",
    ],
)
def test_an_allowed_comment_passes(source):
    """A reason, a ticket ID, a factual date or an ordinary string is not refused."""
    assert violations(source) == []
