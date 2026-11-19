"""The evaluation run, its baseline check, its scores and its LangSmith experiments."""

from src.config.models import DEFAULT_MAX_TOKENS
from src.config.paths import EVAL_QUESTIONS_TRAINING_PATH

# Training questions that the pain and injury guard (T9.19a) must catch: their evaluation check is
# the fixed message and no model or embedding call. Read only by tests/test_guardrails.py.
EVAL_GUARDED_QUESTION_IDS: frozenset[str] = frozenset({"t8"})
# The layout of the results file that scripts/run_evaluation.py writes next to each report (T8.4;
# src/eval_results.py). Raise it when a field is renamed or removed, so an old baseline is refused
# instead of read wrongly.
EVAL_RESULTS_SCHEMA_VERSION = 1
# How far the found or cited rate of a run may fall below the baseline's before the check fails.
# Set from the spread of the baseline run's three askings (T8.4, 2026-10-26): the same code gives
# different rates from run to run (the query translation step picks other rewrites and topic
# filters, and the embedding API's vectors move a little). The largest distance of one asking from
# the baseline's average was one expected source of 17, 0.0588 (found rate 15, 14 and 13 of 17;
# cited 14, 14 and 13), rounded up to 0.06: every baseline asking passes against its own average.
# One source is worth 0.0588 of a single asking and 0.0196 of an average of three. Limits: the
# check compares averages of three askings, so losing one expected source in all three (found
# 39 of 51, 0.7647, against a lowest allowed 0.7635) still passes, and only a loss of two fails;
# and a run of unchanged code falls below the found rate's limit about one time in ten (less often
# for the cited rate), so rerun before believing a failure (docs/TESTING.md, "Baseline (T8.4)").
EVAL_TOLERANCE = 0.06
# Its own tolerance (owner's choice, 2026-10-29), set by T8.4's rule (the largest distance of one
# asking from the average, rounded up) on the owner's first training run (b22a375): found 13, 16
# and 13 of 19 expected sources (0.6842, 0.8421, 0.6842; average 0.7368, so 0.1053), cited 12, 15
# and 13 (0.0877). The committed baseline's own askings (8394573: 15, 15 and 14 of 19) are only
# 0.0351 from their average, but the owner kept 0.11 as the training runs vary more from run to
# run: cde5dcf's run, one prompt line earlier, (0.7018 / 0.6842) would fail 0.06 (lowest allowed
# 0.7119). Limits: one source is 0.0526 of a single asking and 0.0175 of an average of three, so
# losing six expected sources over the three askings (38 of 57, 0.6667, against a lowest allowed
# 0.6619) still passes and only seven fail. A baseline whose questions file is not listed uses
# EVAL_TOLERANCE.
EVAL_TRAINING_TOLERANCE = 0.11
EVAL_TOLERANCES_BY_QUESTIONS_FILE: dict[str, float] = {
    EVAL_QUESTIONS_TRAINING_PATH.name: EVAL_TRAINING_TOLERANCE,
}
# How long each of the three git calls that read the evaluated code's state may take (T8.4, T9.21).
EVAL_GIT_TIMEOUT_SECONDS = 10
# The judge of the evaluation scores (`scripts/run_evaluation.py --score`, T9.10): the model that
# writes the answers, so it grades its own (a limit in docs/TESTING.md). The owner chose
# openai/gpt-5 first, a stronger model, but the course's OpenRouter key does not allow it (404 on
# every judge call of the first run, no tokens billed); gpt-5-mini then (owner's choice,
# 2026-11-06). Built by llm.build_chat_model(), so it must be on ALLOWED_MODELS.
EVAL_JUDGE_MODEL = "openai/gpt-5-mini"
# Twice the app's default: faithfulness lists the facts of every chunk an answer got in one reply,
# and gpt-5's reasoning tokens count against the same cap; a cut-off reply is a lost score. Only
# the tokens used are paid.
EVAL_JUDGE_MAX_TOKENS = 2 * DEFAULT_MAX_TOKENS
# The DeepEval metrics the script scores each answer on, in the order they are written. Context
# precision and recall wait for the owner's reference answers (O14; owner's choice, 2026-11-06).
EVAL_SCORE_METRICS: tuple[str, ...] = ("faithfulness", "answer_relevancy")
# LangSmith experiments of the evaluation run (`scripts/run_evaluation.py --langsmith`, T9.33;
# src/experiments.py): one dataset per questions file, named with this prefix and the file's stem
# (e.g. fitcoach-eval-eval_questions), and each run an experiment of its own on that dataset,
# named with this prefix, the commit, the answer model, the language and the start time. The
# evaluation's own text is not masked there (owner's choice, 2026-11-12); the app's runs always
# are (LANGSMITH_PROJECT, src/tracing.py).
EVAL_DATASET_PREFIX = "fitcoach-eval-"
EVAL_EXPERIMENT_PREFIX = "fitcoach-eval"
# Seconds to wait at the end of a run for the experiment's runs and feedback to reach LangSmith.
EVAL_EXPERIMENT_FLUSH_SECONDS = 60
