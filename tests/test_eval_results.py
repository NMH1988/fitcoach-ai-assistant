"""Tests for src/eval_results.py (T8.4): the results file of an evaluation run; no network."""

import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from decimal import Decimal

import pytest

from src import config, eval_results
from src.eval_results import GitState, RunRecord

STARTED = datetime(2026, 10, 27, 9, 30, 15)
MODELS = {
    "answer": "answer-model",
    "query_translation": "rewrite-model",
    "embedding": "embed-model",
}


def _record(**changes) -> RunRecord:
    """Return a made-up run record: q1 asked once, #1 found and cited, #3 missed."""
    values = {
        "id": "q1",
        "run": 1,
        "with_profile": False,
        "kind": "answer",
        "code": None,
        "expected": ("1", "3"),
        "expected_found": ("1",),
        "expected_cited": ("1",),
        "unexpected_citations": ("2",),
        "tools": (("lookup_food_nutrition", "found"),),
        "tokens": 1210,
        "cost_usd": "0.0013",
    }
    return RunRecord(**{**values, **changes})


def _document(records, **changes) -> dict:
    """Return the results document for these records with made-up run details."""
    details = {
        "git": GitState(commit="a" * 40, dirty=False, changes="same"),
        "git_at_end": GitState(commit="a" * 40, dirty=False, changes="same"),
        "models": MODELS,
        "language": "en",
        "repeat": 3,
        "started": STARTED,
        "questions_file": "eval_questions.json",
    }
    return eval_results.results_document(records, **{**details, **changes})


def test_a_run_record_is_written_with_the_fields_the_ticket_names():
    """Each run has its id, kind, code, the expected sources found and cited, tools and cost."""
    assert _record().as_dict() == {
        "id": "q1",
        "run": 1,
        "with_profile": False,
        "kind": "answer",
        "code": None,
        "expected": ["1", "3"],
        "expected_found": ["1"],
        "expected_cited": ["1"],
        "unexpected_citations": ["2"],
        "tools": [{"name": "lookup_food_nutrition", "status": "found"}],
        "tokens": 1210,
        "cost_usd": "0.0013",
    }


def test_the_document_names_the_code_the_models_the_language_the_repeat_and_the_date():
    """The header says what was run: schema, commit, dirty flag, models, language, repeat, date."""
    document = _document([_record()])
    assert document["schema_version"] == config.EVAL_RESULTS_SCHEMA_VERSION
    assert document["commit"] == "a" * 40
    assert document["dirty"] is False
    assert document["commit_at_end"] == "a" * 40
    assert document["dirty_at_end"] is False
    assert document["changed_during_run"] is False
    assert document["models"] == MODELS
    assert document["language"] == "en"
    assert document["repeat"] == 3
    assert document["date"].startswith("2026-10-27T09:30:15")
    assert document["questions_file"] == "eval_questions.json"
    assert document["runs"] == [_record().as_dict()]


def test_the_document_is_plain_json_that_reads_back_the_same(tmp_path):
    """Writing then reading gives the same document, in a file that ends with a newline."""
    document = _document([_record(), _record(id="q13", with_profile=True, cost_usd=None)])
    path = tmp_path / "out" / "run.json"
    eval_results.write_results(document, path)
    assert path.read_text(encoding="utf-8").endswith("}\n")
    assert json.loads(path.read_text(encoding="utf-8")) == document


def test_a_run_with_no_known_price_has_no_cost():
    """An unknown price is null, never 0, so a missing price is not read as a free run."""
    assert _record(cost_usd=None).as_dict()["cost_usd"] is None


def test_a_cost_is_written_as_plain_decimal_text():
    """A cost has no exponent and no float rounding, as in the turn log."""
    assert eval_results.cost_text(Decimal("0.0017")) == "0.0017"
    assert eval_results.cost_text(Decimal("1E-7")) == "0.0000001"
    assert eval_results.cost_text(Decimal(0)) == "0"
    assert eval_results.cost_text(None) is None


def _fake_git(outputs):
    """Return a stand-in for subprocess.run that answers each git call from the outputs."""

    def run(command, **_kwargs):
        """Return the scripted output for this git subcommand (else empty), or fail like git."""
        output = outputs.get(command[3], (0, ""))
        if isinstance(output, Exception):
            raise output
        return subprocess.CompletedProcess(command, output[0], stdout=output[1])

    return run


def _sha(text: str) -> str:
    """Return the SHA-256 hex digest of a text, as the git state hashes the diff."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_git_state_is_the_head_commit_and_whether_tracked_files_changed(tmp_path):
    """A clean tree is dirty False; a change to a tracked file is dirty True, its diff hashed."""
    head = (0, "b" * 40 + "\n")
    clean = _fake_git({"rev-parse": head, "status": (0, ""), "diff": (0, "")})
    assert eval_results.git_state(tmp_path, run=clean) == GitState("b" * 40, False, _sha(""))
    diff = "diff --git a/src/chat.py b/src/chat.py\n+x\n"
    changed = _fake_git({"rev-parse": head, "status": (0, " M src/chat.py\n"), "diff": (0, diff)})
    assert eval_results.git_state(tmp_path, run=changed) == GitState("b" * 40, True, _sha(diff))


@pytest.mark.parametrize(
    "outputs",
    [
        {"rev-parse": FileNotFoundError("no git"), "status": (0, "")},
        {"rev-parse": (128, ""), "status": (128, "")},
        {"rev-parse": (0, "not a commit\n"), "status": (0, "")},
        {"rev-parse": (0, "c" * 40), "status": subprocess.TimeoutExpired("git", 10)},
    ],
    ids=["no git", "not a repository", "odd output", "status times out"],
)
def test_the_git_state_is_unknown_when_git_cannot_say(tmp_path, outputs):
    """With no git, no repository or odd output, commit and dirty are null, never a guess."""
    assert eval_results.git_state(tmp_path, run=_fake_git(outputs)) == GitState(None, None)


@pytest.mark.parametrize(
    "diff", [(128, ""), subprocess.TimeoutExpired("git", 10)], ids=["fails", "times out"]
)
def test_a_failed_diff_keeps_the_commit_and_loses_only_the_change_check(tmp_path, diff):
    """The commit and dirty flag read before the diff stay; the change check becomes unknown."""
    outputs = {"rev-parse": (0, "c" * 40), "status": (0, " M a.txt\n"), "diff": diff}
    state = eval_results.git_state(tmp_path, run=_fake_git(outputs))
    assert state == GitState("c" * 40, True, None)
    assert eval_results.changed_during_run(state, state) is None


def test_git_is_asked_about_the_folder_given_with_fixed_arguments(tmp_path):
    """Each call names the folder with -C and uses no shell, so the folder is the code that ran."""
    seen = []

    def run(command, **kwargs):
        """Record the call and answer like a clean repository."""
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout="d" * 40 if "rev-parse" in command else ""
        )

    eval_results.git_state(tmp_path, run=run)
    assert [command[:3] for command, _ in seen] == [["git", "-C", str(tmp_path)]] * 3
    assert [command[3] for command, _ in seen] == ["rev-parse", "status", "diff"]
    # No external diff tool or text conversion from the user's git config runs.
    assert {"--no-ext-diff", "--no-textconv"} <= set(seen[2][0])
    for _, kwargs in seen:
        assert kwargs.get("shell") is not True
        assert kwargs["timeout"] > 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available here")
def test_the_git_state_of_a_real_repository(tmp_path):
    """On a real repository: the commit is 40 hex digits and an edit to a tracked file is dirty."""

    def git(*args):
        """Run git in the temporary repository with no signing and a made-up author."""
        subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com",
             "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True,
        )  # fmt: skip

    git("init", "-q")
    tracked = tmp_path / "a.txt"
    tracked.write_text("one", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-q", "-m", "first")
    clean = eval_results.git_state(tmp_path)
    assert clean.dirty is False
    assert clean.commit is not None and len(clean.commit) == 40
    tracked.write_text("two", encoding="utf-8")
    edited = eval_results.git_state(tmp_path)
    assert edited.dirty is True
    assert eval_results.changed_during_run(clean, edited) is True
    # A second edit to a file that was already changed is seen too (T9.21).
    tracked.write_text("three", encoding="utf-8")
    assert eval_results.changed_during_run(edited, eval_results.git_state(tmp_path)) is True
    (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")
    git("checkout", "--", "a.txt")
    restored = eval_results.git_state(tmp_path)
    assert restored.dirty is False
    assert eval_results.changed_during_run(clean, restored) is False
    tracked.write_text("four", encoding="utf-8")
    git("commit", "-q", "-am", "second")
    committed = eval_results.git_state(tmp_path)
    assert committed.dirty is False
    assert eval_results.changed_during_run(clean, committed) is True


START = GitState("a" * 40, True, _sha("one change"))


@pytest.mark.parametrize(
    ("end", "changed"),
    [
        (GitState("a" * 40, True, _sha("one change")), False),
        (GitState("b" * 40, False, _sha("")), True),
        (GitState("a" * 40, True, _sha("one change, then another")), True),
        (GitState(None, None), None),
        (GitState("a" * 40, True, None), None),
    ],
    ids=["no change", "a new commit", "an edited tracked file", "git cannot say", "no diff"],
)
def test_the_code_changed_during_the_run_when_head_or_the_diff_moved(end, changed):
    """HEAD or the tracked files' changes moving is a change; an unknown state is null."""
    assert eval_results.changed_during_run(START, end) is changed
    assert eval_results.changed_during_run(GitState(None, None), START) is None


def test_the_document_records_the_end_and_whether_the_code_changed():
    """The start's commit stays the file's commit; the end's is recorded beside it (T9.21)."""
    document = _document([_record()], git=START, git_at_end=GitState("b" * 40, False, _sha("")))
    assert (document["commit"], document["dirty"]) == ("a" * 40, True)
    assert (document["commit_at_end"], document["dirty_at_end"]) == ("b" * 40, False)
    assert document["changed_during_run"] is True
    assert _sha("one change") not in json.dumps(document)
    unknown = _document([_record()], git=START, git_at_end=GitState(None, None))
    assert unknown["changed_during_run"] is None


def test_the_change_note_names_both_commits_or_the_edited_files():
    """The note says HEAD moved with both short commits, or that tracked files changed."""
    moved = eval_results.change_note(START, GitState("b" * 40, False, _sha("")))
    assert moved is not None and "HEAD moved from aaaaaaa to bbbbbbb" in moved
    edited = eval_results.change_note(START, GitState("a" * 40, True, _sha("more")))
    assert edited is not None and "tracked files changed on aaaaaaa" in edited
    assert eval_results.change_note(START, START) is None
    assert eval_results.change_note(START, GitState(None, None)) is None


# --- The summary: found and cited rate per run and averaged -------------------------------------


def _two_runs() -> list[RunRecord]:
    """Return two runs of two questions: run 1 misses and run 2 finds everything."""
    return [
        _record(id="q1", run=1, expected=("1", "3"), expected_found=("1",), expected_cited=("1",)),
        _record(id="q2", run=1, expected=("2",), expected_found=("2",), expected_cited=()),
        _record(
            id="q1",
            run=2,
            expected=("1", "3"),
            expected_found=("1", "3"),
            expected_cited=("1", "3"),
        ),
        _record(id="q2", run=2, expected=("2",), expected_found=("2",), expected_cited=("2",)),
    ]


def test_the_summary_counts_expected_sources_found_and_cited_per_run_and_averaged():
    """Rates count expected sources: run 1 found 2 of 3 and cited 1; run 2 found and cited all 3."""
    summary = eval_results.summarise(_two_runs())
    assert summary["runs"] == [
        {
            "run": 1,
            "expected_sources": 3,
            "found": 2,
            "found_rate": 0.6667,
            "cited": 1,
            "cited_rate": 0.3333,
        },
        {
            "run": 2,
            "expected_sources": 3,
            "found": 3,
            "found_rate": 1.0,
            "cited": 3,
            "cited_rate": 1.0,
        },
    ]
    assert summary["found_rate"] == 0.8333
    assert summary["cited_rate"] == 0.6667


def test_a_question_with_no_expected_source_is_not_in_the_rates():
    """A question that expects nothing, even one that cites sources, does not change a rate."""
    records = [
        *_two_runs(),
        _record(id="q11", run=1, expected=(), expected_found=(), expected_cited=()),
        _record(id="q12", run=2, expected=(), unexpected_citations=("5", "6")),
    ]
    assert eval_results.summarise(records) == eval_results.summarise(_two_runs())


def test_a_run_that_ended_in_an_error_after_the_search_keeps_what_it_found():
    """An error after the search keeps its found sources but cites none; it is never dropped."""
    failed = _record(
        id="q1", kind="error", code="llm.error", expected_found=("1",), expected_cited=()
    )
    summary = eval_results.summarise([failed, _record(id="q2", expected=("2",))])
    assert summary["runs"][0]["expected_sources"] == 3
    assert summary["runs"][0]["found"] == 2
    assert summary["runs"][0]["cited"] == 1


def test_a_run_that_ended_in_an_error_counts_its_expected_sources_as_missed():
    """An error before the search finds and cites nothing, so it lowers both rates."""
    failed = _record(id="q1", kind="error", code="llm.error", expected_found=(), expected_cited=())
    summary = eval_results.summarise([failed, _record(id="q2", expected=("2",))])
    assert summary["runs"][0]["expected_sources"] == 3
    assert summary["runs"][0]["found"] == 1


def test_the_rates_are_null_when_no_question_has_an_expected_source():
    """With nothing to score the rates are null and there are no per-run rows, not 0 or 1."""
    summary = eval_results.summarise([_record(expected=(), expected_found=(), expected_cited=())])
    assert summary == {"runs": [], "found_rate": None, "cited_rate": None}
    assert eval_results.summarise([]) == summary


def test_the_summary_is_in_the_document_before_the_runs():
    """The results file carries the summary of its own records."""
    records = _two_runs()
    document = _document(records)
    assert document["summary"] == eval_results.summarise(records)
    assert list(document)[-2:] == ["summary", "runs"]
