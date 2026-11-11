"""The plan and the progress log agree with their files, and doc links resolve (T1.15)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

PLAN_BACK = re.compile(
    r"^\[Implementation plan\]\(\.\./IMPLEMENTATION_PLAN\.md\) · (Epic \d+: .+)$"
)
PROGRESS_BACK = "[Progress log](../PROGRESS.md)"
TICKET_HEADING = re.compile(r"^### (T\d+\.\d+[a-z]?) (.+?) · status: (.+?) · issue .+$")
ENTRY_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) · (?:(T\d+\.\d+[a-z]?) )?")
EPIC_HEADING = re.compile(r"^## (Epic \d+: .+)$")
LIST_LINE = re.compile(r"^- \[(.*)\]\((tickets|progress)/([^)]+)\)$")
TABLE_ROW = re.compile(r"^\| (?:\[(T[^\]]+)\]\(tickets/([^)]+)\)|(T\d+\.\d+[a-z]?)) \|")
# Inline links and images, reference definitions, and HTML src/href attributes (the README's
# images). Known limits: link text with nested brackets, or a stray backtick earlier on the line,
# hides a link from the check; one flag tracks both ``` and ~~~ fences, so a fence of one kind
# inside the other hides the text after it; on Windows a target differing only in case passes
# (CI runs on Linux, where it fails).
LINK = re.compile(r"!?\[[^\]]*\]\(<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\)")
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*<?([^\s>]+)")
HTML_LINK = re.compile(r"(?:src|href)=\"([^\"]+)\"")
CODE_SPAN = re.compile(r"(`+).*?\1")


def unescape(text: str) -> str:
    """Return Markdown link text with its escaped square brackets restored."""
    return text.replace("\\[", "[").replace("\\]", "]")


def index_lines(index: str, folder: str) -> list[tuple[str, str]]:
    """Return (link text, file name) for each list line of an index linking into the folder."""
    lines = []
    for line in index.splitlines():
        m = LIST_LINE.match(line)
        if m and m[2] == folder:
            lines.append((unescape(m[1]), m[3]))
    return lines


def listed_epics(plan: str) -> dict[str, str]:
    """Return ticket file name -> the epic whose list holds it."""
    epics, epic = {}, ""
    for line in plan.splitlines():
        if m := EPIC_HEADING.match(line):
            epic = m[1]
        elif (m := LIST_LINE.match(line)) and m[2] == "tickets":
            epics[m[3]] = epic
    return epics


def status_word(status: str) -> str:
    """Return a status's keyword: the text before any comma ("done, except ..." is "done")."""
    # Only the keyword is compared, as the order table may shorten the rest (T8.6's row).
    return status.split(",")[0].strip()


def ticket_problems(plan: str, tickets: dict[str, str]) -> list[str]:
    """Return how the plan index and the ticket files (name -> text) disagree."""
    problems = []
    listed = index_lines(plan, "tickets")
    names = [name for _, name in listed]
    for name in sorted(set(names)):
        if names.count(name) > 1:
            problems.append(f"{name}: listed {names.count(name)} times in an epic list")
    rows: dict[str, str] = {}
    for line in plan.splitlines():
        m = TABLE_ROW.match(line)
        if not m:
            continue
        if m[3]:
            problems.append(f"{m[3]}: order-table row without a link to its file")
            continue
        if m[2] != f"{m[1]}.md":
            problems.append(f"{m[1]}: order-table row links {m[2]}")
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if m[2] in rows:
            problems.append(f"{m[2]}: more than one row in the order table")
        rows[m[2]] = cells[-1]
    for _, name in listed:
        if name not in tickets:
            problems.append(f"{name}: in an epic list, but no such file")
    for name in rows:
        if name not in tickets:
            problems.append(f"{name}: in the order table, but no such file")
    epics = listed_epics(plan)
    for name, text in sorted(tickets.items()):
        lines = text.splitlines()
        back = PLAN_BACK.match(lines[0]) if lines else None
        if not back or len(lines) < 3 or lines[1]:
            problems.append(f"{name}: does not start with the link back to the plan")
            continue
        if name in epics and epics[name] != back[1]:
            problems.append(f"{name}: its back link names {back[1]!r}, listed in {epics[name]!r}")
        heading = TICKET_HEADING.match(lines[2])
        if not heading:
            problems.append(f"{name}: no ticket heading on its third line")
            continue
        if name != f"{heading[1]}.md":
            problems.append(f"{name}: the heading names {heading[1]}")
        title = lines[2][4:].split(" · status:")[0]
        if title not in [text for text, listed_name in listed if listed_name == name]:
            problems.append(f"{name}: no epic list line reading {title!r}")
        if name not in rows:
            problems.append(f"{name}: no row in the order table")
        elif status_word(rows[name]) != status_word(heading[3]):
            problems.append(
                f"{name}: status {heading[3]!r} in its heading, {rows[name]!r} in the order table"
            )
    return problems


def progress_problems(index: str, entries: dict[str, str]) -> list[str]:
    """Return how the progress index and the entry files (name -> text) disagree."""
    problems = []
    listed = index_lines(index, "progress")
    names = [name for _, name in listed]
    for name in sorted(set(names)):
        if names.count(name) > 1:
            problems.append(f"{name}: listed {names.count(name)} times")
    for _, name in listed:
        if name not in entries:
            problems.append(f"{name}: in the index, but no such file")
    for name, text in sorted(entries.items()):
        lines = text.splitlines()
        if len(lines) < 3 or lines[0] != PROGRESS_BACK or lines[1]:
            problems.append(f"{name}: does not start with the link back to the log")
            continue
        heading = ENTRY_HEADING.match(lines[2])
        if not heading:
            problems.append(f"{name}: no entry heading on its third line")
            continue
        stem = f"{heading[1]}-{heading[2]}" if heading[2] else heading[1]
        pattern = rf"{re.escape(stem)}(?:-\d+)?\.md" if heading[2] else rf"{stem}-[a-z].*\.md"
        if not re.fullmatch(pattern, name):
            problems.append(f"{name}: its name does not follow its heading ({stem})")
        if (lines[2][3:], name) not in listed:
            problems.append(f"{name}: no index line reading {lines[2][3:]!r}")
    return problems


def broken_links(path: Path, text: str) -> list[str]:
    """Return the relative link targets in a Markdown file that point to no file."""
    broken, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        line = CODE_SPAN.sub("", line)
        for target in [*LINK.findall(line), *REFERENCE.findall(line), *HTML_LINK.findall(line)]:
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#)", target, re.I):
                continue
            file_part = re.split(r"[#?]", target)[0]
            if file_part and not (path.parent / file_part.replace("%20", " ")).exists():
                broken.append(target)
    return broken


def read_folder(folder: Path) -> dict[str, str]:
    """Return every Markdown file in a folder as name -> text."""
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md"))}


def doc_files() -> list[Path]:
    """Return the Markdown files whose links are checked: docs/ (all levels), README, CLAUDE."""
    return [*sorted(DOCS.rglob("*.md")), ROOT / "README.md", ROOT / "CLAUDE.md"]


def test_plan_index_agrees_with_the_ticket_files():
    """Every ticket file has its epic list line and order-table row, with the same status."""
    plan = (DOCS / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    tickets = read_folder(DOCS / "tickets")
    assert tickets, "docs/tickets/ holds no ticket"
    assert ticket_problems(plan, tickets) == []


def test_progress_index_agrees_with_the_entry_files():
    """Every entry file has exactly one index line reading as its heading, and back."""
    index = (DOCS / "PROGRESS.md").read_text(encoding="utf-8")
    entries = read_folder(DOCS / "progress")
    assert entries, "docs/progress/ holds no entry"
    assert progress_problems(index, entries) == []


@pytest.mark.parametrize("path", doc_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_point_to_files(path):
    """Every relative Markdown link in the docs, the README and CLAUDE.md finds its file."""
    assert broken_links(path, path.read_text(encoding="utf-8")) == []


# Synthetic cases: each kind of disagreement is caught.

BACK = "[Implementation plan](../IMPLEMENTATION_PLAN.md) · Epic 1: Foundation\n\n"
HEADING = "### T1.1 Skeleton (S) · status: done · issue #1\n**Serves:** none\n"
PLAN = (
    "| [T1.1](tickets/T1.1.md) | #1 | Skeleton | S | - | 10-20 | done |\n\n"
    "## Epic 1: Foundation\n\n- [T1.1 Skeleton (S)](tickets/T1.1.md)\n"
)
LIST = "- [T1.1 Skeleton (S)](tickets/T1.1.md)\n"
ROW = "| [T1.1](tickets/T1.1.md) | #1 | Skeleton | S | - | 10-20 | done |\n"
FILE = {"T1.1.md": BACK + HEADING}
NAME = "2026-11-11-T1.15.md"
ENTRY = "[Progress log](../PROGRESS.md)\n\n## 2026-11-11 · T1.15 Split · #1 (closes #2)\n- x\n"
LOG = f"# Progress log\n\n- [2026-11-11 · T1.15 Split · #1 (closes #2)](progress/{NAME})\n"


def test_a_consistent_synthetic_plan_and_log_pass():
    """The synthetic plan and log used below agree, so each case breaks one thing only."""
    assert ticket_problems(PLAN, FILE) == []
    assert progress_problems(LOG, {NAME: ENTRY}) == []


@pytest.mark.parametrize(
    ("plan", "tickets", "expected"),
    [
        (PLAN.replace(ROW, ""), {}, "in an epic list, but no such file"),
        (PLAN.replace(LIST, ""), {}, "in the order table, but no such file"),
        (PLAN.replace(LIST, ""), FILE, "no epic list line"),
        (PLAN + LIST, FILE, "listed 2 times in an epic list"),
        (PLAN.replace(ROW, ""), FILE, "no row in the order table"),
        (ROW.replace("done", "todo") + PLAN, FILE, "more than one row in the order table"),
        (PLAN.replace("(tickets/T1.1.md) |", "(tickets/T1.2.md) |"), FILE, "row links T1.2.md"),
        (PLAN.replace("[T1.1](tickets/T1.1.md)", "T1.1"), FILE, "without a link"),
        (PLAN, {"T1.1.md": BACK + HEADING.replace("done", "todo")}, "in its heading"),
        (PLAN.replace("| done |", "| in review |"), FILE, "in its heading"),
        (PLAN, {"T1.1.md": HEADING}, "link back to the plan"),
        (PLAN, {"T1.1.md": BACK.replace("1: Foundation", "9: Agent") + HEADING}, "listed in"),
        (PLAN, {"T1.1.md": BACK + HEADING.replace("Skeleton", "Frame")}, "no epic list line"),
        (PLAN, {"T1.2.md": BACK + HEADING}, "the heading names T1.1"),
    ],
    ids=[
        "listed-without-file",
        "table-row-without-file",
        "file-without-list-line",
        "listed-twice",
        "file-without-table-row",
        "two-table-rows",
        "table-row-links-another-file",
        "table-row-without-link",
        "status-changed-in-file-only",
        "status-changed-in-table-only",
        "no-back-link",
        "back-link-names-another-epic",
        "title-differs",
        "file-name-differs",
    ],
)
def test_ticket_disagreements_are_caught(plan, tickets, expected):
    """Each kind of disagreement between the plan index and the ticket files is reported."""
    problems = ticket_problems(plan, tickets)
    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("index", "entries", "expected"),
    [
        (LOG, {}, "no such file"),
        ("# Progress log\n", {NAME: ENTRY}, "no index line"),
        (LOG, {NAME: ENTRY.replace("Split", "Join")}, "no index line"),
        (LOG + LOG.splitlines()[-1] + "\n", {NAME: ENTRY}, "listed 2 times"),
        (LOG, {NAME: ENTRY.split("\n\n", 1)[1]}, "link back to the log"),
        (LOG.replace(NAME, "a.md"), {"a.md": ENTRY}, "does not follow its heading"),
        (
            LOG.replace("T1.15 Split", "Plan the split").replace(NAME, "2026-11-10-plan-x.md"),
            {"2026-11-10-plan-x.md": ENTRY.replace("T1.15 Split", "Plan the split")},
            "does not follow its heading",
        ),
    ],
    ids=[
        "line-without-file",
        "file-without-line",
        "heading-differs",
        "listed-twice",
        "no-back",
        "name-differs",
        "name-differs-without-ticket",
    ],
)
def test_progress_disagreements_are_caught(index, entries, expected):
    """Each kind of disagreement between the progress index and the entry files is reported."""
    problems = progress_problems(index, entries)
    assert any(expected in problem for problem in problems), problems


def test_a_broken_relative_link_is_caught(tmp_path):
    """A relative link to a missing file is reported; web links, anchors and code are not."""
    (tmp_path / "there.md").write_text("x", encoding="utf-8")
    page = tmp_path / "page.md"
    text = (
        "[ok](there.md) [ok](there.md#part) [web](https://example.com/x.md) [anchor](#top)\n"
        "[ok](<there.md> 'title') <img src=\"there.md\"> [ref]: there.md\n"
        "[gone](missing.md) `[code](also-missing.md)`\n"
        '<img src="missing.png" alt="x"> <a href="missing.html">x</a>\n'
        "[ref]: missing-ref.md\n"
        "```\n[fenced](fenced-missing.md)\n```\n"
        "~~~\n[fenced](tilde-missing.md)\n~~~\n"
    )
    assert broken_links(page, text) == [
        "missing.md",
        "missing.png",
        "missing.html",
        "missing-ref.md",
    ]
