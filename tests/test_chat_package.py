"""Tests for the src/chat package: every old name kept, patches that land, imports in any order."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_config_package import defined_names

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "chat"
# The public names of the chat module before T10.10 split it into a package (at 55f2c40): the
# modules define every one of them and no other, and the package gives each as chat.<name>.
OLD_NAMES = frozenset(
    """
    logger Step TurnKind Correction SourceCard SearchDetails TurnResult PromptMissingError
    ToolLoopError KnowledgeBaseSummary knowledge_base_summary prompt_version Prompt
    load_system_prompt answer_system_prompt search_queries find_chunks manifest_by_id
    escape_markdown format_authors markdown_url format_sources sources_block user_message
    build_messages strip_citations exchange_messages trim_history cited_labels PacedWriter
    remove_images source_cards stream_reply answer_with_tools fixed_text memory_text TurnDeps
    TurnCallbacks run_turn
    """.split()
)
# The names tests patch on the package itself; their callers read them as chat.<name>.
PATCHED_ON_THE_PACKAGE = {"run_turn", "manifest_by_id", "load_system_prompt"}
# The names the old module's tests patched that a module of the package now reads directly.
READ_INSIDE = {"embed_queries", "load_manifest", "_NUTRITION_ONLY"}
# The callers the rule on imported names covers; src/chat/ itself re-exports every name.
CALLER_FOLDERS = ("src", "views", "scripts")


def _chat_modules() -> list[Path]:
    """Return the package's modules, its __init__ left out."""
    return sorted(p for p in PACKAGE.glob("*.py") if p.name != "__init__.py")


def _tree(path: Path) -> ast.Module:
    """Return a Python file's syntax tree."""
    return ast.parse(path.read_text(encoding="utf-8"))


def test_the_package_defines_the_old_module_s_names_each_once():
    """The modules define exactly the old names between them, none of them in two modules."""
    defined = [name for path in _chat_modules() for name in defined_names(path)]
    assert len(defined) == len(set(defined)), sorted({n for n in defined if defined.count(n) > 1})
    assert set(defined) == OLD_NAMES


def test_every_old_name_is_read_through_the_package_from_its_own_module():
    """chat.<name> is the object its module defines, so every caller sees the one object."""
    # In a fresh interpreter: this one's conftest has patched run_turn on the package.
    check = (
        "import sys\n"
        "from src import chat\n"
        "for module_name, names in __import__('json').loads(sys.argv[1]).items():\n"
        "    module = getattr(chat, module_name)\n"
        "    wrong = [n for n in names if getattr(chat, n) is not getattr(module, n)]\n"
        "    assert not wrong, wrong\n"
    )
    defined = {path.stem: defined_names(path) for path in _chat_modules()}
    done = subprocess.run(
        [sys.executable, "-c", check, json.dumps(defined)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr


def test_the_init_only_gathers_the_modules():
    """The package's __init__ defines nothing of its own: it imports every module, no more."""
    init = PACKAGE / "__init__.py"
    assert defined_names(init) == []
    imported = {node.module for node in _tree(init).body if isinstance(node, ast.ImportFrom)}
    assert imported == {f"src.chat.{path.stem}" for path in _chat_modules()}


def _bound_at_top(tree: ast.Module) -> set[str]:
    """Return the names a module binds at its top level: defs, classes, assignments, imports."""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def read_by_bare_name(source: str) -> set[str]:
    """Return the module-level names a module's code reads by bare name (its own or imported)."""
    tree = ast.parse(source)
    bound = _bound_at_top(tree)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in bound
    }


def _read_inside_the_package() -> set[str]:
    """Return every name a module of src/chat/ reads by bare name."""
    found: set[str] = set()
    for path in _chat_modules():
        found |= read_by_bare_name(path.read_text(encoding="utf-8"))
    return found


def _target(node: ast.AST, package_names: set[str]) -> tuple[str, str] | None:
    """Return a patch call's target as (the dotted path under src.chat, the name), else None."""
    if not (isinstance(node, ast.Call) and node.args):
        return None
    method = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
    if method not in ("setattr", "object", "patch"):
        return None
    first = node.args[0]
    second = node.args[1] if len(node.args) > 1 else None
    name = second.value if isinstance(second, ast.Constant) else None
    if isinstance(first, ast.Name) and first.id in package_names:
        return ("", name) if isinstance(name, str) else None
    if (
        isinstance(first, ast.Attribute)
        and isinstance(first.value, ast.Name)
        and first.value.id in package_names
    ):
        return (first.attr, name) if isinstance(name, str) else None
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        path, _, dotted_name = first.value.rpartition(".")
        if path == "src.chat" or path.startswith("src.chat."):
            return path.removeprefix("src.chat").removeprefix("."), dotted_name
    return None


def patched_on_the_package(node: ast.AST, package_names: set[str]) -> str | None:
    """Return the name a setattr, patch or patch.object call patches on the package, else None."""
    target = _target(node, package_names)
    return target[1] if target is not None and target[0] == "" else None


def patched_on_a_module(node: ast.AST, package_names: set[str]) -> tuple[str, str] | None:
    """Return (module, name) for a patch on one module of the package, else None."""
    target = _target(node, package_names)
    return target if target is not None and target[0] != "" else None


def package_names_in(tree: ast.Module) -> set[str]:
    """Return the names a test binds to the src.chat package (`from src import chat [as x]`)."""
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "src"
        for alias in node.names
        if alias.name == "chat"
    }


def _test_trees() -> list[tuple[str, ast.Module]]:
    """Return each test file's name and syntax tree."""
    return [(path.name, _tree(path)) for path in sorted((ROOT / "tests").glob("*.py"))]


def _patches_in_the_tests() -> list[tuple[str, int, str]]:
    """Return each patch on the package in tests/: the file, the line and the name."""
    found = []
    for file, tree in _test_trees():
        names = package_names_in(tree)
        for node in ast.walk(tree):
            if (name := patched_on_the_package(node, names)) is not None:
                found.append((file, node.lineno, name))
    return found


def _module_patches_in_the_tests() -> list[tuple[str, int, tuple[str, str]]]:
    """Return each patch on a module of the package in tests/: the file, the line, the target."""
    found = []
    for file, tree in _test_trees():
        names = package_names_in(tree)
        for node in ast.walk(tree):
            if (target := patched_on_a_module(node, names)) is not None:
                found.append((file, node.lineno, target))
    return found


def _imported_across_the_package() -> set[tuple[str, str]]:
    """Return (module, name) for each name a module of the package imports from another one."""
    return {
        (node.module.removeprefix("src.chat."), alias.name)
        for path in _chat_modules()
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src.chat.")
        for alias in node.names
    }


def test_no_test_patches_a_name_the_package_reads_inside_on_the_package_alone():
    """A name a module reads directly is patched on that module, or the patch would miss it."""
    read = _read_inside_the_package()
    assert READ_INSIDE <= read
    assert PATCHED_ON_THE_PACKAGE.isdisjoint(read)
    patches = _patches_in_the_tests()
    found = [f"{file}:{line} {name}" for file, line, name in patches if name in read]
    assert found == []


def test_no_test_patches_on_its_module_a_name_another_module_imports():
    """A name one module imports from another is read there too, so one patch would miss it."""
    shared = _imported_across_the_package()
    assert ("citations", "strip_citations") in shared
    patches = _module_patches_in_the_tests()
    assert ("retrieval", "embed_queries") in {target for _, _, target in patches}
    found = [f"{file}:{line} {target}" for file, line, target in patches if target in shared]
    assert found == []


def test_the_tests_patch_on_the_package_only_the_names_callers_read_through_it():
    """The names patched on the package are the ones listed, so the import rule below sees them."""
    assert {name for _, _, name in _patches_in_the_tests()} == PATCHED_ON_THE_PACKAGE


def imports_by_name(source: str, names: set[str]) -> list[str]:
    """Return the listed names a module imports by name from src.chat or one of its modules."""
    return [
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and (node.module == "src.chat" or node.module.startswith("src.chat."))
        for alias in node.names
        if alias.name in names
    ]


def _caller_files() -> list[Path]:
    """Return app.py and every module of src/, views/ and scripts/ outside src/chat/."""
    files = [ROOT / "app.py"]
    for folder in CALLER_FOLDERS:
        files += sorted((ROOT / folder).rglob("*.py"))
    return [path for path in files if PACKAGE not in path.parents]


def test_no_caller_imports_by_name_a_name_the_tests_patch_on_the_package():
    """Callers read the names tests patch on the package as chat.<name>, so the patches land."""
    found = [
        f"{path.relative_to(ROOT).as_posix()}: {name}"
        for path in _caller_files()
        for name in imports_by_name(path.read_text(encoding="utf-8"), PATCHED_ON_THE_PACKAGE)
    ]
    assert found == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('monkeypatch.setattr(chat, "embed_queries", fake)', "embed_queries"),
        ('setattr(chat, "_NUTRITION_ONLY", None)', "_NUTRITION_ONLY"),
        ('mock.patch.object(chat, "load_manifest", fake)', "load_manifest"),
        ('monkeypatch.setattr("src.chat.embed_queries", fake)', "embed_queries"),
        ('mock.patch("src.chat.embed_queries", fake)', "embed_queries"),
        ('monkeypatch.setattr(\n    chat,\n    "run_turn",\n    fake,\n)', "run_turn"),
        ('monkeypatch.setattr(chat.retrieval, "embed_queries", fake)', None),
        ('monkeypatch.setattr("src.chat.retrieval.embed_queries", fake)', None),
        ('monkeypatch.setattr(config, "embed_queries", fake)', None),
        ("monkeypatch.setattr(chat, name, fake)", None),
        ('monkeypatch.delenv("X")', None),
    ],
)
def test_the_patch_scan_finds_a_patch_on_the_package_only(source, expected):
    """The scan reads the call's target: the package, by object or by dotted name, not a module."""
    tree = ast.parse(source)
    found = [n for node in ast.walk(tree) if (n := patched_on_the_package(node, {"chat"}))]
    assert found == ([expected] if expected else [])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            'monkeypatch.setattr(chat.citations, "strip_citations", f)',
            ("citations", "strip_citations"),
        ),
        ('mock.patch("src.chat.markdown.remove_images", f)', ("markdown", "remove_images")),
        ('monkeypatch.setattr(chat, "run_turn", f)', None),
        ('monkeypatch.setattr(views_chat.citations, "strip_citations", f)', None),
    ],
)
def test_the_module_patch_scan_finds_a_patch_on_one_module(source, expected):
    """The scan reads a patch on a module of the package, by attribute or by dotted name."""
    tree = ast.parse(source)
    found = [t for node in ast.walk(tree) if (t := patched_on_a_module(node, {"chat"}))]
    assert found == ([expected] if expected else [])


def test_only_a_name_bound_to_the_package_counts_as_the_package():
    """A test's own `chat` (e.g. the views module) is not the package; an alias of it is."""
    tree = ast.parse("from src import chat as turns\nfrom views import chat")
    assert package_names_in(tree) == {"turns"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from src.chat import run_turn", ["run_turn"]),
        ("from src.chat.turn import run_turn", ["run_turn"]),
        ("from src.chat import (\n    TurnResult,\n    manifest_by_id,\n)", ["manifest_by_id"]),
        ("def f():\n    from src.chat.prompts import load_system_prompt", ["load_system_prompt"]),
        ("from src import chat", []),
        ("from src.chat import TurnResult, fixed_text", []),
        ("from src.chatter import run_turn", []),
    ],
)
def test_the_import_scan_finds_a_patched_name_imported_by_name(source, expected):
    """The scan sees an import of a patched name from the package or one of its modules."""
    assert imports_by_name(source, PATCHED_ON_THE_PACKAGE) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from x import a\ndef f():\n    return a()", {"a"}),
        ("B = 1\ndef f():\n    return B", {"B"}),
        ("def f():\n    a = 1\n    return a", set()),
        ("import os\ndef f():\n    return os.sep", {"os"}),
    ],
)
def test_the_bare_name_scan_finds_module_level_names_only(source, expected):
    """A name read inside a function counts when the module binds it at its top level."""
    assert read_by_bare_name(source) == expected


def _imports_the_package(node: ast.stmt) -> bool:
    """Return True for a statement that imports src.chat or one of its modules."""
    if isinstance(node, ast.Import):
        return any(a.name == "src.chat" or a.name.startswith("src.chat.") for a in node.names)
    if not isinstance(node, ast.ImportFrom):
        return False
    module = node.module or ""
    if module == "src":
        return any(alias.name == "chat" for alias in node.names)
    return module == "src.chat" or module.startswith("src.chat.")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from src import chat, config", True),
        ("import src.chat", True),
        ("from src.chat.results import TurnResult", True),
        ("from src import config", False),
        ("from src.chatter import x", False),
        ("import src.chatter", False),
    ],
)
def test_the_importer_scan_sees_every_form_of_import(source, expected):
    """A top-level import of the package counts in either form; a look-alike name does not."""
    assert _imports_the_package(ast.parse(source).body[0]) is expected


def _modules_importing_chat_at_the_top() -> list[str]:
    """Return the modules of src/ outside the package that import it at their top level."""
    found = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if PACKAGE in path.parents:
            continue
        for node in _tree(path).body:
            if _imports_the_package(node):
                parts = path.relative_to(ROOT).with_suffix("").parts
                found.append(".".join(parts))
                break
    return found


IMPORTED_FIRST = ["src.chat", *_modules_importing_chat_at_the_top()]


def test_the_import_list_holds_every_known_importer():
    """The list found by scanning holds the modules known to import chat at the top."""
    assert {
        "src.agent.graph",
        "src.agent.memory",
        "src.agent.review",
        "src.agent.search",
        "src.export_pdf",
        "src.weekly_review",
    } <= set(IMPORTED_FIRST)


@pytest.mark.parametrize("module", IMPORTED_FIRST)
def test_the_package_imports_whichever_module_comes_first(module):
    """A fresh interpreter imports the module first, then reads a name from every chat module."""
    check = (
        "import importlib, sys\n"
        "importlib.import_module(sys.argv[1])\n"
        "from src import chat\n"
        "assert chat.run_turn and chat.find_chunks and chat.answer_with_tools\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", check, module],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
