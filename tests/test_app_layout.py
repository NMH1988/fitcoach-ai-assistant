"""The UI layout (T8.1): app.py only composes the page; the views hold the rest."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VIEWS = ROOT / "views"

# The modules that build chart specs and table rows: they take the language as a parameter, so
# they are unit-tested without AppTest and must not import streamlit.
PURE_VIEWS = ("charts", "tables")


def _imported_modules(path: Path) -> set[str]:
    """Return the top-level names of every module a Python file imports."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("name", PURE_VIEWS)
def test_the_spec_and_row_builders_do_not_import_streamlit(name):
    """charts.py and tables.py import no streamlit, so their tests need no AppTest."""
    assert "streamlit" not in _imported_modules(VIEWS / f"{name}.py")


def test_the_import_scan_finds_a_streamlit_import(tmp_path):
    """The scan reports `import streamlit`, `from streamlit import` and `import streamlit.x`."""
    source = tmp_path / "mod.py"
    for code in ("import streamlit as st", "from streamlit import cache", "import streamlit.x"):
        source.write_text(code, encoding="utf-8")
        assert "streamlit" in _imported_modules(source)
    source.write_text("from src import config\nimport re", encoding="utf-8")
    assert _imported_modules(source) == {"src", "re"}


# --- app.py only composes the page ---------------------------------------------------------------

APP = ROOT / "app.py"
MAX_APP_LINES = 150
# The only function app.py defines: it lays out the header and the four tabs. Every chart, table
# and card builder lives in views/.
APP_FUNCTIONS = {"_main_area"}


def _functions(path: Path) -> set[str]:
    """Return the names of the functions, methods and classes a Python file defines."""
    nodes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {
        n.name
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(n, nodes)
    }


def test_app_py_has_at_most_150_lines():
    """app.py stays a thin composition (T8.1)."""
    lines = APP.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_APP_LINES


def test_app_py_defines_only_the_allowed_functions():
    """app.py defines no chart, table or card builder: its functions are on a short allowlist."""
    assert _functions(APP) == APP_FUNCTIONS


def test_the_function_scan_finds_functions_methods_and_classes(tmp_path):
    """The scan lists a function, an async function, a method, a class and a nested function."""
    source = tmp_path / "mod.py"
    source.write_text(
        "def a(): pass\nasync def b(): pass\nclass C:\n    def d(self):\n        def e(): pass\n",
        encoding="utf-8",
    )
    assert _functions(source) == {"a", "b", "C", "d", "e"}


def _list_parts(test_file: str, name: str) -> set[str]:
    """Return the parts of a module-level list in a test file, as written (e.g. `APP_FILES`)."""
    tree = ast.parse((ROOT / "tests" / test_file).read_text(encoding="utf-8"))
    [value] = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    assert isinstance(value, ast.List)
    return {ast.unparse(element) for element in value.elts}


def test_the_unsafe_html_and_components_scans_list_the_views():
    """test_prompt_injection's `APP_FILES` (both scans read it) holds app.py, views/ and src/."""
    parts = _list_parts("test_prompt_injection.py", "APP_FILES")
    assert {"APP", "*sorted(VIEWS.rglob('*.py'))", "*sorted(SRC.rglob('*.py'))"} <= parts
    source = (ROOT / "tests" / "test_prompt_injection.py").read_text(encoding="utf-8")
    assert 'VIEWS = config.PROJECT_ROOT / "views"' in source


@pytest.mark.parametrize("test_file", ["test_app_export.py", "test_app_profile.py"])
def test_the_html_and_image_scans_glob_the_views_folder(test_file):
    """The st.html scan and the image scan build their file list from app.py, views/ and src/."""
    tree = ast.parse((ROOT / "tests" / test_file).read_text(encoding="utf-8"))
    globbed = {
        ast.unparse(node.func.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rglob"
        and isinstance(node.func.value, ast.BinOp)
    }
    assert {"root / 'views'", "root / 'src'"} <= globbed
