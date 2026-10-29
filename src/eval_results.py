"""The results file of an evaluation run (T8.4): what each question gave, with no text in it.

Written by scripts/run_evaluation.py next to its Markdown report and read by
scripts/check_eval_baseline.py. The report holds the answers and the article text, so it is never
committed; this file holds only IDs, labels, counts and the run's details, so the owner can commit
one run as the baseline (data/eval_baseline.json).
"""

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src import config


@dataclass(frozen=True)
class RunRecord:
    """One question asked once, as the results file records it (IDs and counts, no text)."""

    # The question's ID (e.g. q13) and which asking of it this was, from 1 to --repeat.
    id: str
    run: int
    with_profile: bool
    # How the turn ended and its fixed message's code (chat.TurnResult.kind and .code).
    kind: str
    code: str | None
    # The sources the question should find, those of them found among the chunks the answer model
    # got, those of them the answer cites, and the cited sources that are not expected at all.
    expected: tuple[str, ...]
    expected_found: tuple[str, ...]
    expected_cited: tuple[str, ...]
    unexpected_citations: tuple[str, ...]
    # The tools the model called, as (name, status); a name that is not a real tool is "unknown".
    tools: tuple[tuple[str, str], ...]
    tokens: int
    # The cost in dollars as plain text, or None when a price was unknown.
    cost_usd: str | None

    def as_dict(self) -> dict:
        """Return the record as the plain dict that is written to the file."""
        return {
            "id": self.id,
            "run": self.run,
            "with_profile": self.with_profile,
            "kind": self.kind,
            "code": self.code,
            "expected": list(self.expected),
            "expected_found": list(self.expected_found),
            "expected_cited": list(self.expected_cited),
            "unexpected_citations": list(self.unexpected_citations),
            "tools": [{"name": name, "status": status} for name, status in self.tools],
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
        }


@dataclass(frozen=True)
class GitState:
    """The code an evaluation ran on: its commit and whether tracked files differ from it."""

    # All None when git could not say (no git, not a repository).
    commit: str | None
    dirty: bool | None
    # A hash of the tracked files' changes against the commit (`git diff HEAD`), so an edit to a
    # file that was already changed is seen too (T9.21); None when the diff could not be read.
    # Kept in memory only, never written. Read as text, so a second edit to a binary or
    # non-UTF-8 tracked file may give the same hash (no such file changes what a run measures).
    changes: str | None = None


def cost_text(cost: Decimal | None) -> str | None:
    """Return a cost as plain decimal text (no exponent), or None when the price was unknown."""
    return None if cost is None else format(cost, "f")


def git_state(
    folder: Path, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> GitState:
    """Return the HEAD commit of the repository at `folder` and whether tracked files changed."""
    try:
        head = _git(run, folder, "rev-parse", "HEAD")
        status = _git(run, folder, "status", "--porcelain", "--untracked-files=no")
    except OSError, subprocess.SubprocessError:
        return GitState(None, None)
    commit = head.strip()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        return GitState(None, None)
    # A failed diff loses only the change check, not the commit read before it.
    try:
        diff = _git(run, folder, "diff", "HEAD", "--no-ext-diff", "--no-textconv", "--no-color")
    except OSError, subprocess.SubprocessError:
        return GitState(commit, bool(status.strip()))
    changes = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    return GitState(commit, bool(status.strip()), changes)


def changed_during_run(start: GitState, end: GitState) -> bool | None:
    """Return whether HEAD or the tracked files' changes differ between reads; None if unknown."""
    if None in (start.commit, start.changes, end.commit, end.changes):
        return None
    return (start.commit, start.changes) != (end.commit, end.changes)


def change_note(start: GitState, end: GitState) -> str | None:
    """Return the line that says the code changed during the run, or None when it did not."""
    if not changed_during_run(start, end):
        return None
    before, after = (start.commit or "")[:7], (end.commit or "")[:7]
    if before != after:
        what = f"HEAD moved from {before} to {after}"
    else:
        what = f"tracked files changed on {before}"
    return (
        f"Note: the code changed during the run ({what}). The results file records the commit "
        "at the start; rerun to measure one version of the code."
    )


def _git(run: Callable[..., subprocess.CompletedProcess[str]], folder: Path, *args: str) -> str:
    """Return a git command's output for the repository at `folder`; raise if it fails."""
    done = run(
        ["git", "-C", str(folder), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        # A file with other bytes in the diff must not stop the run; the hash only has to change.
        errors="replace",
        timeout=config.EVAL_GIT_TIMEOUT_SECONDS,
        check=False,
    )
    if done.returncode != 0:
        raise subprocess.CalledProcessError(done.returncode, done.args)
    return done.stdout


def _rate(part: int, whole: int) -> float:
    """Return part / whole to four decimals, so the file is short and a rate reads back the same."""
    return round(part / whole, 4)


def summarise(records: Sequence[RunRecord]) -> dict:
    """Return the found and cited rate of each run and their averages, over the scored questions."""
    # A question is scored when it has expected sources. A rate counts expected sources, not
    # questions: of all the sources the scored questions expect in a run, the share found among
    # the chunks the answer model got, and the share the answer cites. A run that ended in an
    # error is never dropped: before the search it found nothing, after it (e.g. the answer model
    # failed) it keeps what it found but cites nothing. `run` is the asking's number.
    runs = []
    found_rates, cited_rates = [], []
    for number in sorted({record.run for record in records if record.expected}):
        scored = [record for record in records if record.run == number and record.expected]
        expected = sum(len(record.expected) for record in scored)
        found = sum(len(record.expected_found) for record in scored)
        cited = sum(len(record.expected_cited) for record in scored)
        found_rates.append(found / expected)
        cited_rates.append(cited / expected)
        runs.append(
            {
                "run": number,
                "expected_sources": expected,
                "found": found,
                "found_rate": _rate(found, expected),
                "cited": cited,
                "cited_rate": _rate(cited, expected),
            }
        )
    if not runs:
        return {"runs": [], "found_rate": None, "cited_rate": None}
    return {
        "runs": runs,
        # Averaged from the exact rates, not the rounded ones in the rows.
        "found_rate": _rate(sum(found_rates), len(runs)),
        "cited_rate": _rate(sum(cited_rates), len(runs)),
    }


def results_document(
    records: Sequence[RunRecord],
    *,
    git: GitState,
    git_at_end: GitState,
    models: Mapping[str, str],
    language: str,
    repeat: int,
    started: datetime,
    questions_file: str,
) -> dict:
    """Return the whole results file: the run's details, then every run's record."""
    # `commit` and `dirty` are read when the run starts, as the modules are loaded then; the
    # `_at_end` fields are read when the file is written (T9.21). Fields were only added, so
    # EVAL_RESULTS_SCHEMA_VERSION stays 1 and an older file (the baseline) still compares.
    return {
        "schema_version": config.EVAL_RESULTS_SCHEMA_VERSION,
        "commit": git.commit,
        "dirty": git.dirty,
        "commit_at_end": git_at_end.commit,
        "dirty_at_end": git_at_end.dirty,
        "changed_during_run": changed_during_run(git, git_at_end),
        "models": dict(models),
        "language": language,
        "repeat": repeat,
        "date": started.astimezone().isoformat(timespec="seconds"),
        "questions_file": questions_file,
        "summary": summarise(records),
        "runs": [record.as_dict() for record in records],
    }


def write_results(document: Mapping, path: Path) -> Path:
    """Write the results document as JSON at `path` (its folder is made) and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


class ResultsFileError(ValueError):
    """A results file is missing, broken or cannot be compared; `str()` says which."""


def _is_rate(value: object) -> bool:
    """Return True for a number from 0 to 1 (a bool and NaN are not)."""
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


def load_results(path: Path) -> dict:
    """Read a results file and check the parts the comparison needs; raise ResultsFileError."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        hint = " Take one with `python -m scripts.run_evaluation --repeat 3`."
        raise ResultsFileError(f"No results file at {path}.{hint}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResultsFileError(f"Could not read {path}: {exc}") from None
    if not isinstance(document, dict):
        raise ResultsFileError(f"{path} must hold a JSON object.")
    summary = document.get("summary")
    if not isinstance(summary, dict):
        raise ResultsFileError(f"{path} has no summary.")
    for name in ("found_rate", "cited_rate"):
        rate = summary.get(name)
        if rate is not None and not _is_rate(rate):
            raise ResultsFileError(f"{path} has a {name} that is not a number from 0 to 1.")
    if not isinstance(document.get("runs"), list):
        raise ResultsFileError(f"{path} has no list of runs.")
    for number, run in enumerate(document["runs"], start=1):
        if not _is_run(run):
            raise ResultsFileError(
                f"{path} has a run (number {number} in the list) without a text `id` and a list "
                "of text `expected` sources, or with a `kind` that is not text."
            )
    return document


def _is_run(run: object) -> bool:
    """Return True for a run entry the comparison can read: a text id and text expected sources."""
    if not isinstance(run, dict) or not isinstance(run.get("id"), str):
        return False
    expected = run.get("expected")
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        return False
    return run.get("kind") is None or isinstance(run["kind"], str)


@dataclass(frozen=True)
class Comparison:
    """What the check found: the lines to print and which rates fell below their limit."""

    lines: tuple[str, ...]
    below: tuple[str, ...]


def _scored(document: Mapping) -> dict[str, tuple]:
    """Return each scored question's ID with its expected sources, from a results file's runs."""
    return {
        str(run.get("id")): tuple(run["expected"])
        for run in document["runs"]
        if isinstance(run, dict) and run.get("expected")
    }


def _scored_errors(document: Mapping) -> int:
    """Return how many runs of scored questions in a results file ended in an error."""
    return sum(
        isinstance(run, dict) and run.get("kind") == "error" and bool(run.get("expected"))
        for run in document["runs"]
    )


def _code(document: Mapping) -> str:
    """Return a results file's commit in short form, and say when its code had changed."""
    commit = document.get("commit")
    text = f"commit {commit[:7]}" if isinstance(commit, str) and commit else "commit unknown"
    text += " (files changed since)" if document.get("dirty") else ""
    return text + (" (code changed during the run)" if document.get("changed_during_run") else "")


def tolerance_for(baseline: Mapping) -> float:
    """Return the baseline's tolerance: its questions file's own, else the default (T9.20)."""
    questions_file = baseline.get("questions_file")
    return config.EVAL_TOLERANCES_BY_QUESTIONS_FILE.get(questions_file, config.EVAL_TOLERANCE)


def compare(results: Mapping, baseline: Mapping, tolerance: float) -> Comparison:
    """Compare a run's average rates with the baseline's; raise ResultsFileError if unlike."""
    # The run and the baseline must have the same schema, the same answer language and the same
    # scored questions with the same expected sources: a new or changed question changes the
    # baseline and needs a new owner run (T8.4). A rate fails when it is below the baseline's
    # minus the tolerance; the limit itself passes.
    if results.get("schema_version") != baseline.get("schema_version"):
        raise ResultsFileError("The results and the baseline have a different schema version.")
    if results.get("language") != baseline.get("language"):
        raise ResultsFileError(
            f"The results are in language {results.get('language')!r}, "
            f"the baseline's in {baseline.get('language')!r}."
        )
    if _scored(results) != _scored(baseline):
        raise ResultsFileError(
            "The results and the baseline score different questions or expect different "
            "sources: a new owner run is needed."
        )
    # An error (no credit left, a provider outage) lowers the rates with no code change, so a
    # scored run that ended in one makes the rates unfit to compare; unscored questions cannot
    # move a rate, so their errors are left alone.
    # Each file gets its own fix: new results are rerun; a broken baseline needs a new owner run.
    fixes = {
        "results": "rerun when the API works again",
        "baseline": "take a new baseline with `python -m scripts.run_evaluation --repeat 3` (O13)",
    }
    problems = []
    for name, document in (("results", results), ("baseline", baseline)):
        errors = _scored_errors(document)
        if errors:
            run_word = "run" if errors == 1 else "runs"
            problems.append(
                f"{errors} scored {run_word} of the {name} ended in an error, so its rates do not "
                f"measure the code: {fixes[name]}."
            )
    if problems:
        raise ResultsFileError(" ".join(problems))
    lines = [f"baseline: {_code(baseline)}", f"results: {_code(results)}"]
    if results.get("models") != baseline.get("models"):
        lines.append("note: the models differ from the baseline's")
    if results.get("repeat") != baseline.get("repeat"):
        lines.append(
            f"note: --repeat is {results.get('repeat')}, the baseline's is {baseline.get('repeat')}"
        )
    below = []
    for name, label in (("found_rate", "found rate"), ("cited_rate", "cited rate")):
        rate, base = results["summary"].get(name), baseline["summary"].get(name)
        if rate is None or base is None:
            raise ResultsFileError("A file has no scored question, so it has no rate to compare.")
        lowest = max(round(base - tolerance, 6), 0)
        ok = round(rate, 6) >= lowest
        lines.append(
            f"{label}: {rate:.4f} (baseline {base:.4f}, lowest allowed {lowest:.4f}): "
            + ("ok" if ok else "BELOW")
        )
        if not ok:
            below.append(label)
    return Comparison(tuple(lines), tuple(below))
