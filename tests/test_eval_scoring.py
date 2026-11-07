"""Tests for src/eval_scoring.py (T9.10): DeepEval's metrics with a mocked judge; no network.

The real scored run is the owner's live check (O13), recorded in docs/TESTING.md.
"""

import asyncio
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from src import config, eval_scoring, llm, usage
from tests.fakes import FakeJudgeChat

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "How much protein per meal?"
ANSWER = "About 0.4 g/kg per meal [S1]."
CHUNKS = ["Made-up chunk: about 0.4 g/kg per meal."]
# A .env file in the folder a command runs in; DeepEval alone would load it into the environment.
ENV_FILE = "T910_CANARY=from-the-env-file\n"


class Reply(BaseModel):
    """A schema made up for these tests."""

    reason: str


def _judge(chat=None):
    """Return a Judge over a fake client, with the recorder its calls go to."""
    recorder = usage.UsageRecorder()
    return eval_scoring.Judge(chat or FakeJudgeChat(), recorder), recorder


def test_the_judge_asks_the_built_client_for_the_schema_and_nothing_else():
    """Only the schema, json_schema and include_raw reach the client: no model, cap or URL."""
    chat = FakeJudgeChat()
    judge, _ = _judge(chat)
    assert judge.generate("Judge this.", schema=Reply) == Reply(reason="JUDGE-REASON")
    assert chat.structured == [
        ("Reply", "Judge this.", {"method": "json_schema", "include_raw": True})
    ]
    # DeepEval keeps the same client object: it builds none of its own.
    assert judge.load_model() is chat
    assert judge.get_model_name() == config.EVAL_JUDGE_MODEL


def test_the_judge_records_the_tokens_of_each_call():
    """Every call's usage is recorded under the judge's step and model, for the run's cost."""
    judge, recorder = _judge()
    judge.generate("One.", schema=Reply)
    judge.generate("Two.")
    assert [(call.step, call.model, call.tokens) for call in recorder.calls] == [
        ("judge", config.EVAL_JUDGE_MODEL, 110),
        ("judge", config.EVAL_JUDGE_MODEL, 110),
    ]


def test_the_judge_without_a_schema_returns_the_text():
    """A call with no schema returns the reply's text."""
    judge, _ = _judge()
    assert judge.generate("Say something.") == "JUDGE-TEXT"


def test_the_async_call_gives_the_same_reply():
    """a_generate() asks the judge as generate() does."""
    judge, _ = _judge()
    assert asyncio.run(judge.a_generate("Judge this.", schema=Reply)) == Reply(
        reason="JUDGE-REASON"
    )


class UnparsedJudgeChat(FakeJudgeChat):
    """A judge client whose structured reply could not be parsed (`parsed` is None)."""

    def with_structured_output(self, schema, **kwargs):
        """Return a runnable that gives no parsed reply, as include_raw does on a bad one."""
        return RunnableLambda(lambda prompt: {"raw": None, "parsed": None, "parsing_error": "x"})


def test_a_reply_off_the_schema_is_an_invalid_reply():
    """A reply DeepEval could not use raises the app's InvalidReplyError, not a raw error."""
    judge, _ = _judge(UnparsedJudgeChat())
    with pytest.raises(llm.InvalidReplyError):
        judge.generate("Judge this.", schema=Reply)


def test_both_metrics_are_scored_from_the_mocked_judge():
    """Faithfulness and answer relevancy are the share of verdicts that pass, with a reason."""
    chat = FakeJudgeChat(verdicts=["yes", "no"])
    judge, _ = _judge(chat)
    scores = eval_scoring.score_answer(QUESTION, ANSWER, CHUNKS, judge)
    assert list(scores) == list(config.EVAL_SCORE_METRICS)
    for name in config.EVAL_SCORE_METRICS:
        assert scores[name].score == 0.5
        assert scores[name].note is None
        assert scores[name].reason == "JUDGE-REASON"
    asked = [schema for schema, _, _ in chat.structured]
    # Faithfulness reads the chunks (truths) and the answer (claims); relevancy the statements.
    assert {"Truths", "Claims", "Statements"} <= set(asked)
    prompts = " ".join(prompt for _, prompt, _ in chat.structured)
    for text in (QUESTION, ANSWER, CHUNKS[0]):
        assert text in prompts


def test_every_verdict_passing_scores_one():
    """All verdicts "yes" give 1.0 on both metrics."""
    judge, _ = _judge(FakeJudgeChat(verdicts=["yes", "yes"]))
    scores = eval_scoring.score_answer(QUESTION, ANSWER, CHUNKS, judge)
    assert [score.score for score in scores.values()] == [1.0, 1.0]


def test_an_answer_with_no_chunks_is_scored_for_relevancy_only():
    """With nothing retrieved (a tool answer) faithfulness has no score, and no call is made."""
    chat = FakeJudgeChat()
    judge, _ = _judge(chat)
    scores = eval_scoring.score_answer(QUESTION, ANSWER, [], judge)
    assert scores["faithfulness"] == eval_scoring.MetricScore(None, "no_chunks")
    assert scores["answer_relevancy"].score == 1.0
    assert "Truths" not in [schema for schema, _, _ in chat.structured]


def test_a_judge_error_gives_its_code_and_the_next_metric_still_runs():
    """An LLMError becomes its code with the safe diagnostic; nothing is raised."""
    error = llm.LLMTimeoutError(diagnostic="APITimeoutError in openai.x")
    judge, _ = _judge(FakeJudgeChat(error=error))
    scores = eval_scoring.score_answer(QUESTION, ANSWER, CHUNKS, judge)
    for name in config.EVAL_SCORE_METRICS:
        assert scores[name].score is None
        assert scores[name].note == "llm.timeout"
        assert scores[name].diagnostic == "APITimeoutError in openai.x"


@pytest.mark.parametrize("error", [llm.OutOfCreditError(402), llm.InvalidAPIKeyError(401)])
def test_an_error_every_call_would_hit_stops_the_calls(error):
    """No credit or a rejected key: the next metric gets the same code without a call."""
    chat = FakeJudgeChat(error=error)
    judge, _ = _judge(chat)
    scores = eval_scoring.score_answer(QUESTION, ANSWER, CHUNKS, judge)
    assert {score.note for score in scores.values()} == {error.code}
    assert len(chat.structured) == 1
    assert eval_scoring.stop_note(scores) == error.code


def test_another_failure_of_the_metric_is_judge_failed():
    """An error DeepEval raises itself is recorded as judge.failed with its type only."""
    judge, _ = _judge(FakeJudgeChat(error=ValueError("CANARY model text")))
    scores = eval_scoring.score_answer(QUESTION, ANSWER, CHUNKS, judge)
    for score in scores.values():
        assert score.note == "judge.failed"
        assert score.diagnostic.startswith("ValueError")
        assert "CANARY" not in score.diagnostic


def test_not_scored_gives_every_metric_the_same_note():
    """A turn with no answer has every metric unscored, with the note."""
    assert eval_scoring.not_scored("no_answer") == {
        name: eval_scoring.MetricScore(None, "no_answer") for name in config.EVAL_SCORE_METRICS
    }


@pytest.mark.parametrize("name", config.EVAL_SCORE_METRICS)
def test_each_metric_is_decided_by_the_judge_alone(name, monkeypatch):
    """eval_mode is "llm" even when DeepEval's setting asks for its System One service."""
    monkeypatch.setenv("DEEPEVAL_EVAL_MODE", "system_one")
    judge, _ = _judge()
    metric = eval_scoring._metric(name, judge)
    assert metric.eval_mode == "llm"
    assert metric.system_one_model is None
    assert metric.model is judge
    assert metric.async_mode is False


def test_the_judge_model_is_on_the_allowlist():
    """build_chat_model() accepts the judge model, so no other model can be judged with."""
    assert config.EVAL_JUDGE_MODEL in config.ALLOWED_MODELS
    # Within the app's cap, so build_chat_model() does not lower it without a word.
    assert config.EVAL_JUDGE_MAX_TOKENS <= config.MAX_TOKENS_CAP


def test_the_library_names_its_pinned_version():
    """The results file records the library and the version the eval extra pins."""
    [pin] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]["eval"]
    assert eval_scoring.library() == "deepeval " + pin.removeprefix("deepeval==")


# DeepEval's own switches, checked in a new Python, as they work at its first import. Each new
# Python imports DeepEval (about 30 s on Windows), so the checks share two processes.


def _python(code: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """Run code in a new Python in tmp_path, with DeepEval's switches unset unless given."""
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DEEPEVAL_", "CONFIDENT_", "OPENROUTER_"))
    }
    clean |= {"PYTHONPATH": str(ROOT), "DEEPEVAL_HOME": str(tmp_path / "home"), **env}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=clean,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_importing_turns_off_telemetry_reads_no_env_file_and_refuses_confident_ai(tmp_path):
    """No PostHog backend, no .env read, no file in DeepEval's home; a Confident AI key refused."""
    (tmp_path / ".env").write_text(ENV_FILE, encoding="utf-8")
    code = """
import os
import src.eval_scoring as s
from deepeval.telemetry import NoopBackend, get_backend
print(isinstance(get_backend(), NoopBackend), 'T910_CANARY' in os.environ)
try:
    s.check_ready()
except s.ScoringNotReady:
    print('refused')
"""
    done = _python(code, tmp_path, CONFIDENT_API_KEY="confident-test-not-a-real-key")
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["True", "False", "refused"]
    assert not (tmp_path / "home").exists()


def test_deepeval_alone_reads_the_env_file_and_then_the_module_refuses_to_load(tmp_path):
    """The checks above can fail: DeepEval alone loads .env; imported first, it is refused."""
    (tmp_path / ".env").write_text(ENV_FILE, encoding="utf-8")
    code = """
import os
import deepeval
print('T910_CANARY' in os.environ)
import src.eval_scoring
"""
    done = _python(code, tmp_path, DEEPEVAL_TELEMETRY_OPT_OUT="1")
    assert done.stdout.split() == ["True"]
    assert done.returncode != 0
    assert "imported before src.eval_scoring" in done.stderr


def test_with_no_confident_ai_key_scoring_is_ready():
    """With no Confident AI key (as in this test run), check_ready() lets the scoring go on."""
    assert not os.environ.get("CONFIDENT_API_KEY")
    eval_scoring.check_ready()
