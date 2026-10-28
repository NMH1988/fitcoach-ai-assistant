"""Every query in src/store/ is a constant string with `?` parameters (T9.6).

The scan reads `src/store/` (sub-packages included) with `ast` and fails on any string built at
run time, SQL or not: an f-string, `%` or `+` with a string or a string constant on either side,
`.format()`, `.join()` on SQL-looking text; on an `execute`, `executemany` or `executescript` whose
query is not a string literal, a module-level name bound once (anywhere: parameters, loops, `with`
and `:=` count) to one, or a migration taken from `schema.MIGRATIONS` (a tuple of such names,
checked below); on one of those methods taken without being called (`run = conn.execute`); and on
`getattr`. Error messages follow the same rule (`values.StoreValueError` joins its two fixed parts
with `" ".join`, which is allowed because it takes no SQL). What it cannot see: a query read from a
file, `setattr` or `globals()` rebinding a constant, a cursor's methods reached through another
object, and `+` on two names that are not constants; review checks those, and none exists.
"""

import ast
from pathlib import Path

import pytest

STORE = Path(__file__).resolve().parents[1] / "src" / "store"
QUERY_METHODS = {"execute", "executemany", "executescript"}
SQL_WORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "PRAGMA", "WHERE", "DROP")


def _is_text(node: ast.AST) -> bool:
    """Return True for a string literal or an f-string."""
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _bound_names(node: ast.AST) -> list[str]:
    """Return the names one node binds: targets, parameters, imports, except, match, def, class."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return [node.id]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.alias):
        return [node.asname or node.name.split(".")[0]]
    if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
        return [node.name]
    if isinstance(node, ast.MatchMapping) and node.rest:
        return [node.rest]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [node.name]
    return []


def _bindings(tree: ast.Module) -> dict[str, int]:
    """Count how often each name is bound anywhere in a module, in every way Python binds one."""
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        for name in _bound_names(node):
            counts[name] = counts.get(name, 0) + 1
    return counts


def _module_constants(tree: ast.Module) -> set[str]:
    """Return the module-level names bound once, anywhere in the module, to a string literal."""
    bound = _bindings(tree)
    literal: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and all(isinstance(t, ast.Name) for t in targets)
            ):
                literal.update(t.id for t in targets)
    return {name for name in literal if bound[name] == 1}


def _migration_names(tree: ast.Module) -> set[str]:
    """Return the loop variables, bound nowhere else, that take their values from MIGRATIONS."""
    bound = _bindings(tree)
    # Only the real migrations count: MIGRATIONS bound once, by importing it from schema.py.
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "src.store.schema"
        and any(alias.name == "MIGRATIONS" and alias.asname is None for alias in node.names)
        for node in ast.walk(tree)
    )
    if not imported or bound.get("MIGRATIONS") != 1:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            source = node.iter.value if isinstance(node.iter, ast.Subscript) else node.iter
            if isinstance(source, ast.Name) and source.id == "MIGRATIONS":
                names.add(node.target.id)
    return {name for name in names if bound[name] == 1}


def problems(source: str) -> list[str]:
    """Return what the scan refuses in one module's source, one line per finding."""
    tree = ast.parse(source)
    constants = _module_constants(tree)
    queries = constants | _migration_names(tree)
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}

    def textual(node: ast.AST) -> bool:
        """Return True for a string literal, an f-string or a string constant's name."""
        return _is_text(node) or (isinstance(node, ast.Name) and node.id in constants)

    found = []
    for node in ast.walk(tree):
        # A query method named as text reaches execute() without the check below:
        # operator.methodcaller("execute", q), conn.__getattribute__("execute")(q).
        if isinstance(node, ast.Call):
            for arg in [*node.args, *(keyword.value for keyword in node.keywords)]:
                if isinstance(arg, ast.Constant) and arg.value in QUERY_METHODS:
                    found.append(f"{node.lineno}: {arg.value} named as text")
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.JoinedStr):
            found.append(f"{line}: f-string")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add):
            if textual(node.left) or textual(node.right):
                found.append(f"{line}: string built with {type(node.op).__name__}")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add | ast.Mod):
            found.append(f"{line}: string built with +=")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in QUERY_METHODS
            and id(node) not in called
        ):
            # `run = conn.execute` and then `run(query)` would escape the check below.
            found.append(f"{line}: {node.attr} taken without calling it")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "getattr":
                found.append(f"{line}: getattr() (a method reached by name)")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method == "format":
                found.append(f"{line}: .format()")
            elif method == "join" and any(
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and any(word in arg.value.upper() for word in SQL_WORDS)
                for arg in ast.walk(node)
            ):
                found.append(f"{line}: SQL joined from pieces")
            elif method in QUERY_METHODS:
                query = node.args[0] if node.args else None
                literal = isinstance(query, ast.Constant) and isinstance(query.value, str)
                named = isinstance(query, ast.Name) and query.id in queries
                if not (literal or named):
                    found.append(f"{line}: {method}() with a query that is not a constant")
    return found


MODULES = sorted(STORE.rglob("*.py"))


@pytest.mark.parametrize("path", MODULES, ids=[p.stem for p in MODULES])
def test_the_store_builds_no_string_and_runs_only_constant_queries(path):
    """No module in src/store/ builds a string; every query is a literal or a constant's name."""
    assert problems(path.read_text(encoding="utf-8")) == [], path


def test_the_store_package_has_its_modules():
    """The scan reads the real package (an empty glob would pass for the wrong reason)."""
    assert {p.stem for p in MODULES} >= {"__init__", "db", "schema", "values"}


def test_every_migration_is_a_module_constant():
    """MIGRATIONS is a tuple of names, each bound once to a string literal in schema.py."""
    tree = ast.parse((STORE / "schema.py").read_text(encoding="utf-8"))
    [assign] = [
        n for n in tree.body if isinstance(n, ast.AnnAssign) and n.target.id == "MIGRATIONS"
    ]
    assert isinstance(assign.value, ast.Tuple) and assign.value.elts
    names = {elt.id for elt in assign.value.elts if isinstance(elt, ast.Name)}
    assert len(names) == len(assign.value.elts)
    assert names <= _module_constants(tree)


CAUGHT = {
    "an import alias rebinding a constant": (
        'Q = "SELECT 1"\nimport os as Q\ndef f(c):\n    c.execute(Q)\n'
    ),
    "except ... as rebinding a constant": (
        'Q = "SELECT 1"\ndef f(c):\n    try:\n        pass\n    except Exception as Q:\n'
        "        c.execute(Q)\n"
    ),
    "a match capture rebinding a constant": (
        'Q = "SELECT 1"\ndef f(c, x):\n    match x:\n        case Q:\n            c.execute(Q)\n'
    ),
    "a def rebinding a constant": (
        'Q = "SELECT 1"\ndef Q():\n    pass\ndef f(c):\n    c.execute(Q)\n'
    ),
    "methodcaller": 'import operator\ndef f(c, q):\n    operator.methodcaller("execute", q)(c)\n',
    "__getattribute__": 'def f(c, q):\n    c.__getattribute__("execute")(q)\n',
    "a local MIGRATIONS list": (
        "MIGRATIONS = ['DROP TABLE users']\ndef f(c):\n    for script in MIGRATIONS:\n"
        "        c.executescript(script)\n"
    ),
    "f-string": 'def f(c, t):\n    c.execute(f"SELECT * FROM {t}")\n',
    "percent": 'def f(c, t):\n    c.execute("SELECT * FROM %s" % t)\n',
    "plus": 'def f(c, t):\n    c.execute("SELECT * FROM " + t)\n',
    "plus on the right": 'def f(c, t):\n    q = t + " WHERE id = 1"\n',
    "plus-equals": 'Q = "SELECT 1"\ndef f(c, t):\n    q = "SELECT"\n    q += t\n',
    "format": 'def f(c, t):\n    c.execute("SELECT * FROM {}".format(t))\n',
    "join": 'def f(c, cols):\n    c.execute(", ".join(cols))\n',
    "join of SQL": 'def f(c, w):\n    q = " ".join(["SELECT * FROM x WHERE", w])\n',
    "a variable": "def f(c, q):\n    c.execute(q, ())\n",
    "a local name": 'def f(c):\n    q = "SELECT 1"\n    c.execute(q)\n',
    "a name bound twice": 'Q = "SELECT 1"\nQ = "DELETE FROM users"\ndef f(c):\n    c.execute(Q)\n',
    "executemany": "def f(c, t, rows):\n    c.executemany(t, rows)\n",
    "executescript": "def f(c, s):\n    c.executescript(s)\n",
    "a call result": "def f(c):\n    c.execute(build())\n",
    "a loop over something else": (
        "def f(c, qs):\n    for script in qs:\n        c.executescript(script)\n"
    ),
    "an f-string message": 'def f(x):\n    raise ValueError(f"bad {x}")\n',
    "a method kept in a variable": "def f(c, q):\n    run = c.execute\n    run(q)\n",
    "getattr": "def f(c, n, q):\n    getattr(c, n)(q)\n",
    "a parameter named like a constant": 'Q = "SELECT 1"\ndef f(c, Q):\n    c.execute(Q)\n',
    "a loop name named like a constant": (
        'Q = "SELECT 1"\ndef f(c, qs):\n    for Q in qs:\n        c.execute(Q)\n'
    ),
    "a constant with %": 'Q = "SELECT * FROM %s"\ndef f(t):\n    return Q % t\n',
    "a migration name bound again": (
        "def f(c, v, s):\n    for script in MIGRATIONS[v:]:\n        pass\n"
        "    script = s\n    c.executescript(script)\n"
    ),
}
PASSES = {
    "a literal": 'def f(c, i):\n    c.execute("SELECT * FROM users WHERE id = ?", (i,))\n',
    "a module constant": 'Q = "SELECT a FROM t WHERE a = ?"\ndef f(c, i):\n    c.execute(Q, (i,))',
    "an annotated constant": 'Q: str = "SELECT 1"\ndef f(c):\n    c.execute(Q)\n',
    "named parameters": 'Q = "SELECT a FROM t WHERE a = :a"\ndef f(c):\n    c.execute(Q, {"a": 1})',
    "a migration": (
        "from src.store.schema import MIGRATIONS\n"
        "def f(c, v):\n    for script in MIGRATIONS[v:]:\n        c.executescript(script)\n"
    ),
    "a message joined from fixed parts": 'def f(a, b):\n    return " ".join((a, b))\n',
    "numbers added": "def f(a, b):\n    return a + b\n",
}


@pytest.mark.parametrize("case", CAUGHT)
def test_the_scan_catches_built_queries(case):
    """Each way of building a query (or any string) is reported."""
    assert problems(CAUGHT[case]), case


@pytest.mark.parametrize("case", PASSES)
def test_the_scan_lets_constant_queries_pass(case):
    """Constant queries with parameters, and code that builds no string, pass."""
    assert problems(PASSES[case]) == [], case
