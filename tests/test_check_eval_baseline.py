"""Tests for scripts/check_eval_baseline.py and the comparison in src/eval_results.py (T8.4)."""

import json
from datetime import datetime

import pytest

from scripts import check_eval_baseline
from src import config, eval_results
from src.eval_results import GitState, ResultsFileError, RunRecord

TOLERANCE = 0.05


@pytest.fixture(autouse=True)
def tolerance(monkeypatch):
    """Use a fixed tolerance, so no test depends on the value set from the owner's baseline run."""
    monkeypatch.setattr(config, "EVAL_TOLERANCE", TOLERANCE)


def _results(
    found=0.9, cited=0.8, language="en", ids=("q1", "q2"), expected=("1",), **changes
) -> dict:
    """Return a results document with these rates, scored questions and their expected sources."""
    document = {
        "schema_version": config.EVAL_RESULTS_SCHEMA_VERSION,
        "commit": "a" * 40,
        "dirty": False,
        "models": {"answer": "answer-model"},
        "language": language,
        "repeat": 3,
        "summary": {"runs": [], "found_rate": found, "cited_rate": cited},
        "runs": [{"id": question, "run": 1, "expected": list(expected)} for question in ids]
        # A question that expects nothing is not scored, so it is not part of the comparison.
        + [{"id": "q11", "run": 1, "expected": []}],
    }
    return {**document, **changes}


def _write(tmp_path, name, document) -> str:
    """Write a results or baseline document and return its path as text."""
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def _check(tmp_path, results, baseline=None, extra=()) -> int:
    """Write both files and run the check on them; return its exit code."""
    baseline_path = _write(tmp_path, "baseline.json", baseline or _results())
    results_path = _write(tmp_path, "results.json", results)
    return check_eval_baseline.main([results_path, "--baseline", baseline_path, *extra])


def test_a_run_equal_to_the_baseline_passes_and_prints_each_rate_with_its_baseline(
    tmp_path, capsys
):
    """Exit 0; the found and cited rate are printed with the baseline and the lowest allowed."""
    assert _check(tmp_path, _results(found=0.9, cited=0.8)) == 0
    out = capsys.readouterr().out
    assert "found rate: 0.9000 (baseline 0.9000, lowest allowed 0.8500): ok" in out
    assert "cited rate: 0.8000 (baseline 0.8000, lowest allowed 0.7500): ok" in out


def test_a_run_above_the_baseline_passes(tmp_path):
    """Better than the baseline is not a failure."""
    assert _check(tmp_path, _results(found=1.0, cited=0.95)) == 0


@pytest.mark.parametrize(
    ("found", "cited", "code"),
    [
        (0.85, 0.75, 0),
        (0.8499, 0.8, 1),
        (0.9, 0.7499, 1),
        (0.5, 0.5, 1),
    ],
    ids=["both exactly at the limit", "found just below", "cited just below", "both far below"],
)
def test_the_check_fails_only_below_the_baseline_minus_the_tolerance(tmp_path, found, cited, code):
    """The limit itself passes; a rate under it fails, whichever of the two it is."""
    assert _check(tmp_path, _results(found=found, cited=cited)) == code


def test_a_failure_names_the_rate_that_fell(tmp_path, capsys):
    """Only the rate below its limit is marked, so the owner sees which one dropped."""
    assert _check(tmp_path, _results(found=0.9, cited=0.6)) == 1
    out = capsys.readouterr().out
    assert "found rate: 0.9000 (baseline 0.9000, lowest allowed 0.8500): ok" in out
    assert "cited rate: 0.6000 (baseline 0.8000, lowest allowed 0.7500): BELOW" in out


def test_the_tolerance_comes_from_the_config(tmp_path, monkeypatch):
    """A larger tolerance lets the same run pass."""
    assert _check(tmp_path, _results(found=0.8, cited=0.8)) == 1
    monkeypatch.setattr(config, "EVAL_TOLERANCE", 0.1)
    assert _check(tmp_path, _results(found=0.8, cited=0.8)) == 0


def test_the_baseline_defaults_to_the_committed_file(tmp_path, monkeypatch):
    """With no --baseline the check reads config.EVAL_BASELINE_PATH."""
    path = tmp_path / "committed.json"
    path.write_text(json.dumps(_results()), encoding="utf-8")
    monkeypatch.setattr(config, "EVAL_BASELINE_PATH", path)
    results = _write(tmp_path, "results.json", _results())
    assert check_eval_baseline.main([results]) == 0


def test_the_run_and_the_baseline_are_named_by_commit(tmp_path, capsys):
    """The output says which code each came from, and flags a run from changed files."""
    results = _results(commit="b" * 40, dirty=True)
    assert _check(tmp_path, results) == 0
    out = capsys.readouterr().out
    assert "baseline: commit aaaaaaa" in out
    assert "results: commit bbbbbbb (files changed since)" in out


def test_other_models_are_a_note_not_a_failure(tmp_path, capsys):
    """A run on other models than the baseline's is compared, with a note saying so."""
    results = _results(models={"answer": "another-model"})
    assert _check(tmp_path, results) == 0
    assert "note: the models differ from the baseline's" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"language": "de"}, "language"),
        ({"schema_version": config.EVAL_RESULTS_SCHEMA_VERSION + 1}, "schema"),
        ({"ids": ("q1", "q2", "q3")}, "questions"),
        ({"ids": ("q1",)}, "questions"),
        ({"expected": ("1", "3")}, "questions"),
    ],
    ids=[
        "language",
        "schema version",
        "a question added",
        "a question removed",
        "a question's expected sources changed",
    ],
)
def test_a_run_that_cannot_be_compared_exits_2_with_the_reason(tmp_path, capsys, changes, message):
    """Another language, schema or set of scored questions needs a new baseline, not a verdict."""
    assert _check(tmp_path, _results(**changes)) == 2
    assert message in capsys.readouterr().err


def test_another_repeat_is_a_note_not_a_failure(tmp_path, capsys):
    """A run with another --repeat than the baseline's is compared, with a note saying so."""
    assert _check(tmp_path, _results(repeat=1)) == 0
    assert "note: --repeat is 1, the baseline's is 3" in capsys.readouterr().out


@pytest.mark.parametrize(
    "rate", [-0.1, 1.5, float("nan")], ids=["below 0", "above 1", "not a number"]
)
def test_a_rate_outside_zero_to_one_is_a_broken_file(tmp_path, rate):
    """A rate is a share: anything outside 0 to 1, or NaN, is refused when the file is read."""
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(_results(found=rate)), encoding="utf-8")
    with pytest.raises(ResultsFileError):
        eval_results.load_results(path)


def test_a_missing_baseline_says_how_to_make_one(tmp_path, capsys):
    """With no baseline file the message names the command that takes one."""
    results = _write(tmp_path, "results.json", _results())
    missing = str(tmp_path / "eval_baseline.json")
    assert check_eval_baseline.main([results, "--baseline", missing]) == 2
    assert "run_evaluation --repeat 3" in capsys.readouterr().err


def test_a_run_with_no_scored_question_cannot_be_compared(tmp_path, capsys):
    """Null rates (nothing scored) are not 0: the run is refused, not failed."""
    results = _results(found=None, cited=None)
    assert _check(tmp_path, results) == 2
    assert "no scored question" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '{"schema_version": 1}', '{"schema_version": 1, "summary": {}}'],
    ids=["not JSON", "not an object", "no summary", "no rates"],
)
def test_a_results_file_in_the_wrong_format_exits_2(tmp_path, capsys, content):
    """A broken or hand-edited results file is refused with a message, never read as passing."""
    results = tmp_path / "results.json"
    results.write_text(content, encoding="utf-8")
    baseline = _write(tmp_path, "baseline.json", _results())
    assert check_eval_baseline.main([str(results), "--baseline", baseline]) == 2
    assert capsys.readouterr().err


def test_a_missing_file_exits_2_and_says_which(tmp_path, capsys):
    """No results file or no baseline gives exit 2 and names the missing path."""
    baseline = _write(tmp_path, "baseline.json", _results())
    missing = str(tmp_path / "nope.json")
    assert check_eval_baseline.main([missing, "--baseline", baseline]) == 2
    assert "nope.json" in capsys.readouterr().err
    results = _write(tmp_path, "results.json", _results())
    assert check_eval_baseline.main([results, "--baseline", missing]) == 2
    assert "nope.json" in capsys.readouterr().err


def test_a_file_written_by_the_run_can_be_read_by_the_check(tmp_path):
    """The writer's output and the checker's input agree: a real document compares with itself."""
    record = RunRecord(
        id="q1",
        run=1,
        with_profile=False,
        kind="answer",
        code=None,
        expected=("1",),
        expected_found=("1",),
        expected_cited=("1",),
        unexpected_citations=(),
        tools=(),
        tokens=10,
        cost_usd=None,
    )
    document = eval_results.results_document(
        [record],
        git=GitState("c" * 40, False),
        models={"answer": "m"},
        language="en",
        repeat=1,
        started=datetime(2026, 10, 27, 9, 0, 0),
        questions_file="eval_questions.json",
    )
    path = eval_results.write_results(document, tmp_path / "run.json")
    assert check_eval_baseline.main([str(path), "--baseline", str(path)]) == 0


def test_the_loader_refuses_a_non_numeric_rate(tmp_path):
    """A rate that is text or a bool is a broken file, not a number to compare."""
    broken = _results(summary={"runs": [], "found_rate": "0.9", "cited_rate": True})
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ResultsFileError):
        eval_results.load_results(path)


def test_the_configured_tolerance_is_a_small_share(monkeypatch):
    """The real tolerance (not the fixed one above) is a rate difference between 0 and 1."""
    monkeypatch.undo()
    assert 0 <= config.EVAL_TOLERANCE < 1


def test_the_committed_baseline_reads_back_and_its_own_runs_stay_within_the_tolerance(
    monkeypatch, capsys
):
    """The tolerance is set from the baseline's spread: each of its runs passes against its mean."""
    monkeypatch.undo()
    baseline = eval_results.load_results(config.EVAL_BASELINE_PATH)
    assert baseline["schema_version"] == config.EVAL_RESULTS_SCHEMA_VERSION
    assert (baseline["language"], baseline["repeat"]) == ("en", 3)
    summary = baseline["summary"]
    assert len(summary["runs"]) == baseline["repeat"]
    for row in summary["runs"]:
        assert row["found_rate"] >= summary["found_rate"] - config.EVAL_TOLERANCE
        assert row["cited_rate"] >= summary["cited_rate"] - config.EVAL_TOLERANCE
    # And the check passes the baseline against itself, through the default path.
    assert check_eval_baseline.main([str(config.EVAL_BASELINE_PATH)]) == 0
    assert "BELOW" not in capsys.readouterr().out
