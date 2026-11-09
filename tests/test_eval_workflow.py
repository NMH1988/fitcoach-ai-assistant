"""Tests that the live evaluation workflow is started by hand only and keeps its key (T8.6)."""

import re
from pathlib import Path

import pytest

# PyYAML (MIT) is installed with langchain-core, a runtime dependency, so it needs no pin here.
import yaml

from src import config

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "eval.yml"
SECRET = "OPENROUTER_API_KEY_EVAL"


def _text() -> str:
    """Return the workflow file's text."""
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow() -> dict:
    """Return the parsed workflow."""
    return yaml.safe_load(_text())


def _triggers(workflow: dict) -> dict:
    """Return the `on:` mapping (YAML 1.1 reads the bare key `on` as True)."""
    return workflow.get("on", workflow.get(True))


def _job(workflow: dict) -> dict:
    """Return the workflow's one job."""
    [job] = workflow["jobs"].values()
    return job


def _steps() -> list[dict]:
    """Return the job's steps."""
    return _job(_workflow())["steps"]


def _step(name: str) -> dict:
    """Return the step with this name."""
    [step] = [step for step in _steps() if step.get("name") == name]
    return step


def test_the_workflow_runs_only_when_started_by_hand():
    """`workflow_dispatch` is the one trigger: no push, pull request, target or schedule."""
    assert set(_triggers(_workflow())) == {"workflow_dispatch"}
    assert "pull_request_target" not in _text()


def test_the_token_can_only_read_the_repository():
    """The workflow's token reads contents only, and no job asks for more."""
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in workflow["jobs"].values())


def test_the_inputs_are_closed_lists():
    """The question set and the repeat count are choices, so the cost of a run is bounded."""
    inputs = _triggers(_workflow())["workflow_dispatch"]["inputs"]
    assert inputs["questions"]["type"] == "choice"
    assert inputs["questions"]["options"] == ["nutrition", "training"]
    assert inputs["repeat"]["type"] == "choice"
    assert [int(option) for option in inputs["repeat"]["options"]] == [3, 1, 5]
    assert inputs["repeat"]["default"] == "3"


def test_the_only_secret_is_the_evaluation_key():
    """No other secret is named anywhere in the file, nor the whole secrets context."""
    text = _text()
    assert set(re.findall(r"secrets\.(\w+)", text)) == {SECRET}
    # `secrets['X']` and `toJSON(secrets)` name a secret without the dot: each use is the key's.
    assert len(re.findall(r"\bsecrets\b", text)) == len(re.findall(rf"secrets\.{SECRET}\b", text))


def test_the_key_reaches_only_the_two_steps_that_call_openrouter():
    """Only the index build and the evaluation get the key, under the app's variable name."""
    workflow = _workflow()
    assert SECRET not in str(workflow.get("env", {}))
    assert SECRET not in str(_job(workflow).get("env", {}))
    holders = [step["name"] for step in _steps() if SECRET in str(step)]
    assert holders == ["Build the index", "Run the evaluation"]
    for name in holders:
        assert _step(name)["env"] == {"OPENROUTER_API_KEY": "${{ secrets." + SECRET + " }}"}


def test_no_script_names_the_key_or_an_expression():
    """No `run:` line prints, traces or interpolates: inputs reach the scripts through `env`."""
    for step in _steps():
        script = step.get("run", "")
        assert "${{" not in script
        assert "OPENROUTER_API_KEY" not in script
        assert "set -x" not in script
        assert "echo" not in script
        assert "printenv" not in script and "env |" not in script


def test_tracing_and_other_keys_stay_off():
    """No LangSmith, tracing or USDA setting is passed, so nothing else leaves the runner."""
    for name in ("LANGSMITH", "FITCOACH_TRACING", "USDA_FDC_API_KEY", "DEMO_MODE"):
        assert name not in _text()


def test_the_steps_download_build_run_upload_and_compare_in_order():
    """Europe PMC download, a fresh index, the evaluation, the upload, then the baseline check."""
    scripts = [step.get("run", "") for step in _steps()]
    order = [
        "scripts.download_sources",
        "scripts.build_index",
        'scripts.run_evaluation --repeat "$REPEAT" "$QUESTIONS"',
        "scripts.check_eval_baseline",
    ]
    positions = [next(i for i, run in enumerate(scripts) if part in run) for part in order]
    assert positions == sorted(positions)
    upload = next(i for i, step in enumerate(_steps()) if "upload-artifact" in step.get("uses", ""))
    assert positions[2] < upload < positions[3]
    # Built fresh every run: no index or article text restored from or saved to the Actions cache,
    # and no step hands the index or the raw articles to an action.
    for step in _steps():
        assert "actions/cache" not in step.get("uses", "")
        for value in step.get("with", {}).values():
            assert "chroma" not in str(value) and "data/raw" not in str(value)


def test_only_the_results_file_is_uploaded():
    """The artifact holds the .json (IDs and counts), never the .md report with article text."""
    upload = _step("Upload the results file")
    assert upload["with"]["path"] == "data/eval_runs/*.json"
    assert upload["with"]["if-no-files-found"] == "error"
    assert ".md" not in str(upload)


def test_the_check_runs_after_a_failed_evaluation_too():
    """The upload and the check run once the evaluation ran, failed or not, unless cancelled."""
    for name in ("Upload the results file", "Compare with the baseline"):
        condition = "${{ !cancelled() && steps.evaluation.outcome != 'skipped' }}"
        assert _step(name)["if"] == condition
    assert '--baseline "$BASELINE"' in _step("Compare with the baseline")["run"]


@pytest.mark.parametrize(
    ("choice", "questions", "baseline"),
    [
        ("nutrition", config.EVAL_QUESTIONS_PATH, config.EVAL_BASELINE_PATH),
        ("training", config.EVAL_QUESTIONS_TRAINING_PATH, config.EVAL_TRAINING_BASELINE_PATH),
    ],
)
def test_each_question_set_is_compared_with_its_own_baseline(choice, questions, baseline):
    """The env picks the config's questions file and baseline for each choice; both exist."""
    env = _job(_workflow())["env"]
    relative = [path.relative_to(config.PROJECT_ROOT).as_posix() for path in (questions, baseline)]
    for name, path in zip(("QUESTIONS", "BASELINE"), relative, strict=True):
        assert path in env[name]
        assert (ROOT / path).is_file()
    training = "inputs.questions == 'training' && "
    if choice == "training":
        assert env["QUESTIONS"].startswith("${{ " + training + f"'{relative[0]}'")
        assert env["BASELINE"].startswith("${{ " + training + f"'{relative[1]}'")
    else:
        assert env["QUESTIONS"].endswith(f"|| '{relative[0]}' }}}}")
        assert env["BASELINE"].endswith(f"|| '{relative[1]}' }}}}")


def test_every_action_is_pinned_by_commit():
    """A step that uses an action names a full commit SHA, not a tag that can move."""
    uses = [step["uses"] for step in _steps() if "uses" in step]
    assert uses
    for action in uses:
        assert re.fullmatch(r"actions/[\w-]+@[0-9a-f]{40}", action), action


def test_the_checkout_keeps_no_token():
    """The checkout leaves no GitHub token in .git/config while the key is in the job."""
    [checkout] = [step for step in _steps() if "actions/checkout" in step.get("uses", "")]
    assert checkout["with"]["persist-credentials"] is False


def test_a_run_is_bounded_in_time_and_never_cancelled_by_the_next():
    """One run at a time, a second one waits, and a stuck run stops after 90 minutes."""
    workflow = _workflow()
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert _job(workflow)["timeout-minutes"] == 90
