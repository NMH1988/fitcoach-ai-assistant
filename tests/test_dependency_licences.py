"""The runtime dependencies' licences, read offline from installed package metadata (T1.11).

`.claude/rules/copyright.md` rule 9 prefers permissive licences and asks for a check before a
package is added. This test runs that check in CI's pytest run on every push to `main` and every
PR, Dependabot's included: it takes the app's requirements from `[project].dependencies` in
`pyproject.toml`, follows them through the installed packages' metadata (markers evaluated for the
running Python and platform, extras a package asks for followed, the project's own `dev` extra
never), and fails on a licence outside `ALLOWED`: GPL, LGPL, AGPL, SSPL, proprietary, unrecognised
or missing. A runtime requirement that is missing or installed at another version than its pin
fails too, so a stale venv cannot pass.

What it does not check: the dev tools (they do not ship with the app); the licences of the
knowledge base, the USDA data, fonts or screenshots (`docs/SOURCES.md`, `ATTRIBUTION.md`); whether a
package's metadata is right or it bundles code under another licence; packages installed only on
another platform (CI runs on Linux, so a Windows-only package such as colorama is checked only by a
local run on Windows). No network: everything comes from `importlib.metadata`.
"""

import email.message
import importlib.metadata
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# Installed with pytest, which requires it; the project does not pin it.
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

# SPDX identifiers the check accepts (compared without case). "BSD-family" stands for the generic
# "BSD License" classifier, which names no clause count. MPL-2.0 is file-level copyleft: allowed
# because we use those packages unchanged (certifi, orjson and tqdm today).
ALLOWED = frozenset(
    name.lower()
    for name in (
        "MIT",
        "MIT-CMU",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSD-family",
        "0BSD",
        "ISC",
        "Apache-2.0",
        "PSF-2.0",
        "CNRI-Python",
        "Zlib",
        "CC0-1.0",
        "MPL-2.0",
    )
)
# The last part of a `License ::` classifier, as an identifier above. Anything else is unrecognised.
CLASSIFIERS = {
    "MIT License": "MIT",
    "BSD License": "BSD-family",
    "Apache Software License": "Apache-2.0",
    "ISC License (ISCL)": "ISC",
    "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "Python Software Foundation License": "PSF-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}
# Words and brackets that cannot stand where an SPDX identifier or exception is expected.
OPERATORS = {"AND", "OR", "WITH", "(", ")"}
# Free-text spellings of the `License` field that are not SPDX expressions, seen in today's set
# (lower case, spaces collapsed).
ALIASES = {
    "apache2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "3-clause bsd license": "BSD-3-Clause",
    "mit license": "MIT",
}


@dataclass(frozen=True)
class HandChecked:
    """A package the owner checked by hand: the licence text it reads, why it is fine, and when."""

    licence: str
    reason: str
    checked: str


# Packages whose metadata the check cannot accept but whose licence the owner checked by hand, by
# canonical name. An entry applies only while the package reads exactly `licence` and is in the
# runtime set, so it cannot outlive the release it was written for.
LICENCE_EXCEPTIONS: dict[str, HandChecked] = {}


@dataclass
class Report:
    """What a walk found: the packages checked (name to version) and every problem."""

    checked: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[str]:
    """Split an SPDX expression into parentheses and words."""
    return text.replace("(", " ( ").replace(")", " ) ").split()


def spdx_allowed(text: str) -> bool:
    """Whether an SPDX expression is satisfied by ALLOWED; raise ValueError if it does not parse."""
    tokens = _tokens(text)
    position = 0

    def peek() -> str | None:
        """Return the next token, upper-cased, or None at the end."""
        return tokens[position].upper() if position < len(tokens) else None

    def take() -> str:
        """Return the next token and move past it."""
        nonlocal position
        if position >= len(tokens):
            raise ValueError("expression ends early")
        position += 1
        return tokens[position - 1]

    def either() -> bool:
        """Parse `a OR b ...`: allowed if one side is."""
        result = both()
        while peek() == "OR":
            take()
            result = both() or result
        return result

    def both() -> bool:
        """Parse `a AND b ...`: allowed if every side is."""
        result = one()
        while peek() == "AND":
            take()
            result = one() and result
        return result

    def one() -> bool:
        """Parse a bracketed expression or an identifier, with an optional `WITH` exception."""
        token = take()
        if token == "(":
            result = either()
            if take() != ")":
                raise ValueError("unbalanced parentheses")
            return result
        if token.upper() in OPERATORS:
            raise ValueError(f"unexpected {token!r}")
        if peek() == "WITH":
            # An exception only adds permissions, so the licence it qualifies decides.
            take()
            if take().upper() in OPERATORS:
                raise ValueError("WITH needs an exception")
        return token.lower() in ALLOWED

    result = either()
    if position != len(tokens):
        raise ValueError("text after the expression")
    return result


def read_licence(metadata) -> tuple[str, str]:
    """Return the field the licence is read from and its text (expression, classifiers, License)."""
    expression = (metadata.get("License-Expression") or "").strip()
    if expression:
        return "License-Expression", expression
    classifiers = [c for c in metadata.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return "Classifier", "; ".join(c.split(" :: ")[-1] for c in classifiers)
    lines = (metadata.get("License") or "").strip().splitlines()
    return "License", lines[0].strip() if lines else ""


def licence_allowed(source: str, text: str) -> bool:
    """Whether a licence read by `read_licence()` is allowed; unrecognised text is not."""
    if source == "Classifier":
        # Several classifiers may mean a choice or a combination; all must be allowed.
        return all(CLASSIFIERS.get(name, "").lower() in ALLOWED for name in text.split("; "))
    if source == "License":
        text = ALIASES.get(" ".join(text.lower().split()), text)
    try:
        return spdx_allowed(text)
    except ValueError:
        return False


def project_requirements(pyproject: Path = PYPROJECT) -> list[str]:
    """Return the runtime requirement lines of `pyproject.toml` (`[project].dependencies`)."""
    with pyproject.open("rb") as file:
        return tomllib.load(file)["project"]["dependencies"]


def installed(name: str):
    """Return the installed distribution of a package, or None."""
    try:
        return importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _applies(requirement: Requirement, extras: set[str]) -> bool:
    """Whether a requirement applies here when its package was asked for with these extras."""
    marker = requirement.marker
    return marker is None or any(marker.evaluate({"extra": extra}) for extra in extras)


def check(
    roots: list[str],
    find: Callable = installed,
    exceptions: dict[str, HandChecked] | None = None,
) -> Report:
    """Walk the requirements from `roots` through `find` and check each package's licence."""
    exceptions = LICENCE_EXCEPTIONS if exceptions is None else exceptions
    report = Report()
    # The project's own extras (`dev`) are not runtime: "" is the only extra the roots see.
    todo = [(Requirement(line), "pyproject.toml") for line in roots]
    todo = [(req, parent) for req, parent in todo if _applies(req, {""})]
    expanded: dict[str, set[str]] = {}
    dists = {}
    while todo:
        requirement, parent = todo.pop(0)
        name = canonicalize_name(requirement.name)
        dist = dists.get(name) or find(requirement.name)
        if dist is None:
            report.problems.append(
                f"{requirement} (required by {parent}) is not installed: run "
                'pip install -e ".[dev]" with the venv\'s Python'
            )
            continue
        if parent == "pyproject.toml" and not requirement.specifier.contains(
            dist.version, prereleases=True
        ):
            report.problems.append(
                f"{name} {dist.version} is installed but pyproject.toml asks for {requirement}: "
                'run pip install -e ".[dev]" with the venv\'s Python'
            )
        dists[name] = dist
        new = ({""} | set(requirement.extras)) - expanded.setdefault(name, set())
        if not new:
            continue
        expanded[name] |= new
        for line in dist.requires or []:
            child = Requirement(line)
            if _applies(child, new):
                todo.append((child, name))
    for name, dist in sorted(dists.items()):
        report.checked[name] = dist.version
        source, text = read_licence(dist.metadata)
        exception = exceptions.get(name)
        if exception is not None:
            if text != exception.licence:
                report.problems.append(
                    f"{name} {dist.version}: its exception is for {exception.licence!r}, but it "
                    f"now reads {text!r} ({source}); check it again"
                )
        elif not licence_allowed(source, text):
            report.problems.append(
                f"{name} {dist.version}: licence {text or '(none)'!r} ({source}) is not allowed or "
                "not recognised; check it by hand (copyright rule 9)"
            )
    for name in sorted(set(exceptions) - set(dists)):
        report.problems.append(f"{name} has a licence exception but is not a runtime dependency")
    return report


@dataclass
class FakeDist:
    """A fake installed distribution: its version, metadata fields and requirement lines."""

    version: str
    fields: list[tuple[str, str]]
    requires: list[str] | None = None

    @property
    def metadata(self) -> email.message.Message:
        """Return the fields as a metadata message, like `importlib.metadata`'s."""
        message = email.message.Message()
        for key, value in self.fields:
            message[key] = value
        return message


def mit(version: str = "1.0", requires: list[str] | None = None) -> FakeDist:
    """Return a fake MIT-licensed distribution."""
    return FakeDist(version, [("License-Expression", "MIT")], requires)


def finder(dists: dict[str, FakeDist]) -> Callable:
    """Return a `find` function over fake distributions, by canonical name."""
    return lambda name: dists.get(canonicalize_name(name))


# The real environment.


def test_runtime_dependencies_have_allowed_licences():
    """Every installed runtime dependency has an allowed licence and its pinned version (T1.11)."""
    roots = project_requirements()
    report = check(roots)
    assert not report.problems, "\n".join(report.problems)
    # The walk went past the pins: each pin is checked, and so are the packages they pull in.
    assert {canonicalize_name(Requirement(line).name) for line in roots} <= set(report.checked)
    assert len(report.checked) > len(roots)


def test_dev_tools_are_not_runtime_dependencies():
    """The roots are `[project].dependencies` only, so dev-only tools are not walked."""
    names = {canonicalize_name(Requirement(line).name) for line in project_requirements()}
    assert not names & {"pytest", "pytest-cov", "ruff", "pip-audit", "pypdf"}


# Reading the licence.


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ([("License-Expression", "MIT"), ("License", "GPL")], ("License-Expression", "MIT")),
        (
            [("Classifier", "License :: OSI Approved :: BSD License"), ("License", "Dual")],
            ("Classifier", "BSD License"),
        ),
        (
            [
                ("Classifier", "Programming Language :: Python"),
                ("Classifier", "License :: OSI Approved :: MIT License"),
                ("Classifier", "License :: OSI Approved :: Apache Software License"),
            ],
            ("Classifier", "MIT License; Apache Software License"),
        ),
        ([("License", "Apache2.0\n\nLong text")], ("License", "Apache2.0")),
        ([], ("License", "")),
    ],
)
def test_read_licence_order(fields, expected):
    """The expression wins over classifiers, which win over the first line of `License`."""
    assert read_licence(FakeDist("1.0", fields).metadata) == expected


@pytest.mark.parametrize(
    ("source", "text"),
    [
        ("License-Expression", "MIT"),
        ("License-Expression", "mit"),
        ("License-Expression", "Apache-2.0 OR BSD-2-Clause"),
        ("License-Expression", "MPL-2.0 AND (Apache-2.0 OR MIT)"),
        ("License-Expression", "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"),
        ("License-Expression", "Apache-2.0 AND CNRI-Python"),
        ("License-Expression", "MIT OR GPL-3.0-only"),
        ("License-Expression", "Apache-2.0 WITH LLVM-exception"),
        ("Classifier", "BSD License; Apache Software License"),
        ("Classifier", "Mozilla Public License 2.0 (MPL 2.0)"),
        ("License", "Apache License, Version 2.0"),
        ("License", "3-Clause BSD License"),
        ("License", "MPL-2.0 AND MIT"),
        # AND binds tighter than OR: (GPL AND MIT) OR MIT, and MIT OR (GPL AND GPL); both would
        # fail if OR bound tighter.
        ("License-Expression", "GPL-3.0-only AND MIT OR MIT"),
        ("License-Expression", "MIT OR GPL-3.0-only AND GPL-2.0-only"),
        ("License-Expression", "mit or gpl-3.0-only"),
        ("Classifier", "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication"),
    ],
)
def test_allowed_licences_pass(source, text):
    """Permissive licences, MPL-2.0 and a choice that includes one pass."""
    assert licence_allowed(source, text)


@pytest.mark.parametrize(
    ("source", "text"),
    [
        ("License-Expression", "GPL-3.0-only"),
        ("License-Expression", "GPL-2.0-or-later WITH Classpath-exception-2.0"),
        ("License-Expression", "AGPL-3.0"),
        ("License-Expression", "LGPL-3.0-or-later"),
        ("License-Expression", "SSPL-1.0"),
        ("License-Expression", "MIT AND GPL-3.0-only"),
        ("License-Expression", "LicenseRef-Proprietary"),
        ("License-Expression", "MIT OR"),
        ("License-Expression", "(MIT"),
        ("License-Expression", "MIT)"),
        ("License-Expression", "MIT WITH"),
        ("License-Expression", "MIT WITH AND"),
        ("Classifier", "Other/Proprietary License"),
        ("Classifier", "OSI Approved"),
        ("Classifier", "MIT License; GNU General Public License v3 (GPLv3)"),
        ("License", "UNKNOWN"),
        ("License", ""),
        ("License", "Dual License"),
        ("License", "Copyright (c) 2015, Some Developers"),
    ],
)
def test_other_licences_fail(source, text):
    """Copyleft, proprietary, unrecognised, broken and missing licences fail."""
    assert not licence_allowed(source, text)


# Walking the requirements.


def test_walk_follows_requirements_and_extras_a_package_asks_for():
    """Requirements are followed, and so are the extras a parent asks for (chromadb's uvicorn)."""
    dists = {
        "app-lib": mit(requires=["server[standard]>=1", "helper"]),
        "server": mit(
            requires=["h11", "fast-parser; extra == 'standard'", "docs; extra == 'docs'"]
        ),
        "helper": mit(),
        "h11": mit(),
        "fast-parser": mit(),
        "docs": mit(),
    }
    report = check(["app-lib==1.0"], finder(dists), exceptions={})
    assert report.problems == []
    assert set(report.checked) == {"app-lib", "server", "helper", "h11", "fast-parser"}


def test_extras_asked_for_later_are_still_followed():
    """A package reached first without an extra, then with one, gets that extra's requirements."""
    dists = {
        "a": mit(requires=["server"]),
        "b": mit(requires=["server[standard]"]),
        "server": mit(requires=["fast-parser; extra == 'standard'"]),
        "fast-parser": mit(),
    }
    report = check(["a==1.0", "b==1.0"], finder(dists), exceptions={})
    assert "fast-parser" in report.checked


def test_marker_false_requirements_are_skipped():
    """A back-port for another Python is skipped, even when it is not installed."""
    dists = {"app-lib": mit(requires=["backport; python_version < '3.0'"])}
    report = check(["app-lib==1.0"], finder(dists), exceptions={})
    assert report.problems == []
    assert set(report.checked) == {"app-lib"}


def test_a_missing_requirement_fails():
    """A requirement that applies here but is not installed fails, naming who needs it."""
    dists = {"app-lib": mit(requires=["needed>=2"])}
    report = check(["app-lib==1.0"], finder(dists), exceptions={})
    assert len(report.problems) == 1
    assert "needed>=2 (required by app-lib) is not installed" in report.problems[0]


def test_a_missing_pin_fails():
    """A pinned runtime dependency that is not installed fails."""
    report = check(["app-lib==1.0"], finder({}), exceptions={})
    assert "app-lib==1.0 (required by pyproject.toml) is not installed" in report.problems[0]


def test_a_pin_at_another_version_fails():
    """A stale venv, with a pinned package at another version, fails instead of passing."""
    report = check(["app-lib==2.0"], finder({"app-lib": mit("1.0")}), exceptions={})
    assert len(report.problems) == 1
    assert "app-lib 1.0 is installed but pyproject.toml asks for app-lib==2.0" in report.problems[0]


def test_only_pins_are_compared_with_the_installed_version():
    """A transitive requirement's range is pip's job, not this check's."""
    dists = {"app-lib": mit(requires=["helper>=9"]), "helper": mit("1.0")}
    assert check(["app-lib==1.0"], finder(dists), exceptions={}).problems == []


def test_the_project_dev_extra_is_not_walked():
    """A root line for the project's own `dev` extra is not runtime and is skipped."""
    report = check(
        ["app-lib==1.0", "pytest==9.1.1; extra == 'dev'"], finder({"app-lib": mit()}), {}
    )
    assert set(report.checked) == {"app-lib"}


# Failing on a bad licence.


@pytest.mark.parametrize(
    "fields",
    [
        [("License-Expression", "GPL-3.0-or-later")],
        [("Classifier", "License :: OSI Approved :: GNU Affero General Public License v3")],
        [("License", "UNKNOWN")],
        [],
    ],
)
def test_a_badly_licensed_dependency_fails(fields):
    """A GPL, AGPL, UNKNOWN or missing licence deep in the tree fails, naming the package."""
    dists = {"app-lib": mit(requires=["deep"]), "deep": FakeDist("3.1", fields)}
    report = check(["app-lib==1.0"], finder(dists), exceptions={})
    assert len(report.problems) == 1
    raw = read_licence(dists["deep"].metadata)[1]
    assert report.problems[0].startswith(f"deep 3.1: licence {raw or '(none)'!r} ")


def test_an_exception_lets_a_hand_checked_package_pass():
    """A package in the exceptions passes while it reads the text the owner checked."""
    dists = {"app-lib": FakeDist("1.0", [("License", "See LICENSE file")])}
    exceptions = {"app-lib": HandChecked("See LICENSE file", "MIT in LICENSE", "2026-10-27")}
    assert check(["app-lib==1.0"], finder(dists), exceptions).problems == []


def test_an_exception_for_other_text_fails():
    """An exception stops applying when the package's licence text changes."""
    dists = {"app-lib": FakeDist("2.0", [("License", "GPL-3.0-only")])}
    exceptions = {"app-lib": HandChecked("See LICENSE file", "MIT in LICENSE", "2026-10-27")}
    report = check(["app-lib==2.0"], finder(dists), exceptions)
    assert len(report.problems) == 1
    assert "now reads 'GPL-3.0-only'" in report.problems[0]


def test_an_exception_for_a_package_not_in_the_set_fails():
    """An exception for a package no longer among the runtime dependencies must be removed."""
    exceptions = {"gone": HandChecked("UNKNOWN", "checked by hand", "2026-10-27")}
    report = check(["app-lib==1.0"], finder({"app-lib": mit()}), exceptions)
    assert report.problems == ["gone has a licence exception but is not a runtime dependency"]


def test_no_exceptions_today():
    """Today every runtime dependency passes on its metadata alone; an entry needs a reason."""
    assert LICENCE_EXCEPTIONS == {}
