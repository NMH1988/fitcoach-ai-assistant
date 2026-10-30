"""The app's name (T9.22): Fitcoach AI Assistant everywhere the current text names the app."""

import ast
from pathlib import Path

import pytest

from src import config, i18n

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
README = ROOT / "README.md"
# The old English and German names, matched case-sensitively, so the old repository's URL
# (`nutrition-ai-assistant`), kept as a record in the `#<n>` notes, does not match, nor does the
# guard's German role word "Ernährungsassistent" (src/guard.py).
OLD_NAMES = ("Nutrition AI Assistant", "KI-Ernährungsassistent")
# Only text files are read; the scanned folders hold nothing else today.
SCANNED_SUFFIXES = {".py", ".md"}
# The one line allowed to name the old name: README's history line, in its Documentation section.
HISTORY_MARK = "until 2026-10-30"


def _scanned_files() -> list[Path]:
    """Return the files whose text must name the app by its new name only."""
    folders = [ROOT / "src", ROOT / "views", ROOT / ".claude" / "agents"]
    found = [
        path
        for folder in folders
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix in SCANNED_SUFFIXES and "__pycache__" not in path.parts
    ]
    return [APP, README, *found]


def _old_name_lines(paths: list[Path]) -> list[tuple[Path, str]]:
    """Return each (file, line) whose text holds an old name, matched case-sensitively."""
    return [
        (path, line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if any(name in line for name in OLD_NAMES)
    ]


def _section(text: str, heading: str) -> list[str]:
    """Return the lines of a Markdown section, from its `## ` heading to the next one."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next((n for n in range(start, len(lines)) if lines[n].startswith("## ")), len(lines))
    return lines[start:end]


def test_the_app_title_is_the_new_name_in_both_languages():
    """The header, the tab and the PDF read `app.title`: the same name in English and German."""
    assert config.APP_TITLE == "Fitcoach AI Assistant"
    for language in i18n.LANGUAGES:
        assert i18n.t("app.title", language) == config.APP_TITLE
        assert i18n.t("pdf.title", language).startswith(f"{config.APP_TITLE}: ")
        assert i18n.t("pdf.footer", language, page=1).startswith(f"{config.APP_TITLE} · ")


def test_the_tab_title_is_the_app_title_in_the_session_language():
    """app.py passes `app.title` in the session's language to st.set_page_config (AppTest can't)."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    [call] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "st.set_page_config"
    ]
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords}
    assert keywords["page_title"] == "i18n.t('app.title', st.session_state[i18n.SESSION_KEY])"


def test_the_old_name_is_only_in_the_readme_history_line():
    """The current text never says "Nutrition AI Assistant", except README's one history line."""
    [(path, line)] = _old_name_lines(_scanned_files())
    assert path == README
    assert HISTORY_MARK in line
    assert line in _section(README.read_text(encoding="utf-8"), "## Documentation")


def test_the_scan_covers_the_app_views_src_agents_and_readme():
    """The scanned files include app.py, README.md, a view, a src module, a prompt, the agents."""
    scanned = set(_scanned_files())
    expected = [
        APP,
        README,
        ROOT / "views" / "header.py",
        ROOT / "src" / "i18n.py",
        ROOT / "src" / "prompts" / "answer_system.md",
        ROOT / ".claude" / "agents" / "code-reviewer.md",
        ROOT / ".claude" / "agents" / "security-reviewer.md",
        ROOT / ".claude" / "agents" / "compliance-reviewer.md",
    ]
    assert all(path in scanned for path in expected)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("# Nutrition AI Assistant", True),
        ("the Nutrition AI Assistant: a chatbot", True),
        ("https://github.com/NMH1988/nutrition-ai-assistant", False),
        ("a nutrition AI assistant", False),
        ("Fitcoach AI Assistant", False),
        ('_DE_APP_TITLE = "KI-Ernährungsassistent"', True),
        ('"du bist jetzt mein Ernährungsassistent"', False),
    ],
)
def test_the_scan_matches_the_old_name_case_sensitively(tmp_path, text, found):
    """The scan finds an old name as written, not the old repository's URL, lower case or a role."""
    path = tmp_path / "file.md"
    path.write_text(f"before\n{text}\nafter\n", encoding="utf-8")
    assert bool(_old_name_lines([path])) is found
