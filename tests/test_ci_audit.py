"""Tests that every advisory CI's pip-audit ignores is documented as an accepted risk (T1.6)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
SECURITY = ROOT / "docs" / "SECURITY.md"


def _ignored_ids() -> list[str]:
    """Return the advisory IDs passed to pip-audit with --ignore-vuln in the CI workflow."""
    return re.findall(r"--ignore-vuln\s+(\S+)", CI.read_text(encoding="utf-8"))


def _accepted_risks() -> str:
    """Return the "Accepted risks" section of docs/SECURITY.md."""
    doc = SECURITY.read_text(encoding="utf-8")
    return doc.split("## Accepted risks", 1)[1].split("\n## ", 1)[0]


def test_ci_ignores_some_advisories():
    """The audit step passes its ignores as --ignore-vuln flags, so the check below has input."""
    assert _ignored_ids()


def test_every_ignored_advisory_has_an_accepted_risk_row():
    """No advisory is ignored in CI without its row under "Accepted risks" (security rules)."""
    rows = [line for line in _accepted_risks().splitlines() if line.startswith("| ")]
    for advisory in _ignored_ids():
        assert [row for row in rows if advisory in row], f"{advisory} has no accepted-risk row"


def test_no_advisory_is_ignored_twice():
    """Each advisory is ignored once."""
    ids = _ignored_ids()
    assert len(ids) == len(set(ids))
