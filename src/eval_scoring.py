"""DeepEval scores of the evaluation answers (T9.10): faithfulness and answer relevancy.

Imported only by `scripts/run_evaluation.py --score` and its tests, never by the app; DeepEval is
in the `eval` extra. The judge is the app's own client from `llm.build_chat_model()`, wrapped in
`Judge`: DeepEval gets no model name, key, URL or token limit, only this object, and the object
passes nothing to the client but the schema of the answer DeepEval wants and, as run metadata for
a masked trace (T9.8), the `turn_id` of the answer being scored.

What DeepEval would otherwise do on its own, and what stops it:
- send usage telemetry to PostHog: `DEEPEVAL_TELEMETRY_OPT_OUT`, set before the import and
  checked after it;
- read `.env` files from the folder the command runs in into the environment:
  `DEEPEVAL_DISABLE_DOTENV`, set before the import;
- ask PyPI for a newer version: only when `DEEPEVAL_UPDATE_WARNING_OPT_IN` is set, so it is removed;
- keep its test runs in a local file: only with `DEEPEVAL_LOCAL_STORE` and `evaluate()`; the
  metrics are measured one by one here and the setting is removed (it makes an empty `.deepeval/`
  folder in the working folder on import, which is gitignored);
- send test runs and traces to Confident AI when its key is set: `check_ready()` refuses to score;
- hand a decision to its own "System One" service (`DEEPEVAL_EVAL_MODE`): each metric is built
  with `eval_mode="llm"`, which wins over the setting.
"""

import os
import sys

if "deepeval" in sys.modules:
    # Its settings are read on the first import, so the switches below would come too late.
    raise ImportError("deepeval was imported before src.eval_scoring could configure it.")
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
os.environ.pop("DEEPEVAL_UPDATE_WARNING_OPT_IN", None)
# Its local store of test runs (the questions, answers and chunks in a SQLite or JSON file) is
# opt-in and fills only through evaluate(), which is not used here; the switches go all the same.
os.environ.pop("DEEPEVAL_LOCAL_STORE", None)
os.environ.pop("DEEPEVAL_RESULTS_FOLDER", None)

import importlib.metadata  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from typing import Any  # noqa: E402

from deepeval.confident.api import is_confident  # noqa: E402
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.telemetry import telemetry_opt_out  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from src import config, llm, tracing, usage  # noqa: E402

if not telemetry_opt_out():
    raise ImportError("DeepEval's telemetry is still on; nothing is scored.")

# The step name of the judge's calls in the usage records.
JUDGE_STEP = "judge"
# Why a metric has no score; with an LLMError's own code (e.g. llm.timeout), the notes the
# results file can hold. no_answer: the turn ended in anything but an answer (a guard or
# guardrail stop, no sources, a coach's memory line, an error); no_chunks: faithfulness of an
# answer that retrieved nothing; judge.interrupted: the owner stopped the scoring (Ctrl-C).
NO_ANSWER = "no_answer"
NO_CHUNKS = "no_chunks"
JUDGE_FAILED = "judge.failed"
INTERRUPTED = "judge.interrupted"
# The notes that are not the judge failing on an answer: the answer was not to be scored.
SKIPPED = frozenset({NO_ANSWER, NO_CHUNKS})
# Errors that every later call would hit too (a rejected key, no credit left): after one, the
# remaining metrics and answers get the same code without a call.
FATAL = frozenset({llm.InvalidAPIKeyError.code, llm.OutOfCreditError.code})


def library() -> str:
    """Return the scoring library and its installed version, e.g. 'deepeval 4.3.3'."""
    return f"deepeval {importlib.metadata.version('deepeval')}"


class ScoringNotReady(RuntimeError):
    """Scoring would send the run somewhere else than the judge's model; `str()` says why."""


def check_ready() -> None:
    """Raise ScoringNotReady when a Confident AI key is set, as DeepEval would upload to it."""
    if is_confident():
        raise ScoringNotReady(
            "A Confident AI key is set (CONFIDENT_API_KEY or DeepEval's login), and DeepEval "
            "would send the questions, answers and chunks there. Remove it, then run again."
        )


def _text(reply: Any) -> str:
    """Return a chat reply's text, joining the text parts of a list reply."""
    content = getattr(reply, "content", "")
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


class Judge(DeepEvalBaseLLM):
    """DeepEval's judge: a client built by llm.build_chat_model(), recording the tokens it uses."""

    def __init__(
        self, chat_model: BaseChatModel, recorder: usage.UsageRecorder, turn_id: str = ""
    ) -> None:
        """Keep the built client, the recorder its calls' usage goes to and the scored turn's ID."""
        self._chat = chat_model
        self._recorder = recorder
        self._name = usage.model_name(chat_model)
        # A traced call carries the turn_id of the answer it scores (T9.8, code review round 8).
        self._config = {"metadata": tracing.run_metadata(turn_id)}
        super().__init__(self._name)

    def for_turn(self, turn_id: str) -> Judge:
        """Return a judge over the same client and recorder whose calls carry this turn's ID."""
        return Judge(self._chat, self._recorder, turn_id)

    def load_model(self) -> BaseChatModel:
        """Return the built client (DeepEval keeps it; nothing here builds another)."""
        return self._chat

    def get_model_name(self) -> str:
        """Return the client's model name, for DeepEval's records."""
        return self._name

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> BaseModel | str:
        """Ask the judge; return the reply in DeepEval's schema when it gives one, else text."""
        if schema is None:
            with llm.mapped_errors():
                reply = self._chat.invoke(prompt, config=self._config)
            self._recorder.add_chat(JUDGE_STEP, self._name, reply.usage_metadata)
            return _text(reply)
        structured = self._chat.with_structured_output(
            schema, method="json_schema", include_raw=True
        )
        with llm.mapped_errors():
            out = structured.invoke(prompt, config=self._config)
        raw = out.get("raw")
        self._recorder.add_chat(JUDGE_STEP, self._name, getattr(raw, "usage_metadata", None))
        parsed = out.get("parsed")
        if not isinstance(parsed, schema):
            raise llm.InvalidReplyError(diagnostic=f"judge reply not a {schema.__name__}")
        return parsed

    async def a_generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> BaseModel | str:
        """Ask the judge as generate() does (the metrics run with async_mode off)."""
        return self.generate(prompt, schema)


@dataclass(frozen=True)
class MetricScore:
    """One metric's score of one answer, or the code that says why it has none."""

    score: float | None
    note: str | None = None
    # The judge's reason: model text, for the gitignored report only, never the results file.
    reason: str | None = None
    # The error's type and where it was raised (llm.error_diagnostic), when the judge failed.
    diagnostic: str | None = None


def not_scored(note: str) -> dict[str, MetricScore]:
    """Return every metric with no score, for one reason (e.g. the turn gave no answer)."""
    return {name: MetricScore(None, note) for name in config.EVAL_SCORE_METRICS}


def _metric(name: str, judge: DeepEvalBaseLLM) -> Any:
    """Return a new DeepEval metric by name, judged by `judge` with the LLM alone."""
    classes = {"faithfulness": FaithfulnessMetric, "answer_relevancy": AnswerRelevancyMetric}
    return classes[name](model=judge, eval_mode="llm", async_mode=False, include_reason=True)


def _measure(
    name: str, question: str, answer: str, chunks: list[str], judge: DeepEvalBaseLLM
) -> MetricScore:
    """Run one metric on one answer; a failed judge gives a code instead of a score."""
    try:
        # Built inside the try: DeepEval checks the case and the metric's settings itself.
        case = LLMTestCase(input=question, actual_output=answer, retrieval_context=chunks)
        metric = _metric(name, judge)
        metric.measure(case)
    except llm.LLMError as exc:
        return MetricScore(None, exc.code, diagnostic=exc.diagnostic)
    except Exception as exc:
        # DeepEval's own errors (e.g. a reply it cannot read): one answer must not end a paid run.
        return MetricScore(None, JUDGE_FAILED, diagnostic=llm.error_diagnostic(exc))
    if not isinstance(metric.score, int | float) or isinstance(metric.score, bool):
        return MetricScore(None, JUDGE_FAILED, diagnostic="no score")
    reason = metric.reason if isinstance(metric.reason, str) else None
    return MetricScore(round(float(metric.score), 4), reason=reason)


def score_answer(
    question: str, answer: str, chunks: list[str], judge: DeepEvalBaseLLM
) -> dict[str, MetricScore]:
    """Score one answer on each metric: faithfulness to the chunks, relevancy to the question."""
    scores: dict[str, MetricScore] = {}
    for name in config.EVAL_SCORE_METRICS:
        if fatal := stop_note(scores):
            # The same error would come back: no call, the same code.
            scores[name] = MetricScore(None, fatal)
        elif name == "faithfulness" and not chunks:
            # Nothing was retrieved (a tool answer), so there is nothing to be faithful to.
            scores[name] = MetricScore(None, NO_CHUNKS)
        else:
            scores[name] = _measure(name, question, answer, chunks, judge)
    return scores


def stop_note(scores: dict[str, MetricScore]) -> str | None:
    """Return the fatal code among an answer's scores, after which no answer is scored; or None."""
    return next((score.note for score in scores.values() if score.note in FATAL), None)
