"""Compare an evaluation run's results with the committed baseline (T8.4).

    python -m scripts.check_eval_baseline data/eval_runs/run-<date>-<time>.json [--baseline FILE]
    python -m scripts.check_eval_baseline <run>.json --baseline data/eval_baseline_training.json

Run it with -m from the checkout you mean to test: a plain `python scripts/...` can
import `src`, and so the baseline path and the tolerance, from another checkout.

The results file is the one scripts/run_evaluation.py writes next to its report. The check reads
two JSON files and calls nothing: no key, no index, no network. It prints the found rate and the
cited rate (the share of the expected sources found among the chunks the answer model got, and
cited by its answer) with the baseline's and the lowest rate allowed, the baseline's tolerance
below the baseline's (`config.EVAL_TOLERANCE`, or its questions file's own in
`config.EVAL_TOLERANCES_BY_QUESTIONS_FILE`: the training baseline, T9.20). Exit code 0: neither
rate is below its limit. 1: a rate is below. 2: a file is missing or broken (including a
hand-edited run entry), or the run cannot be compared: a scored run ended in an error (no credit, an
outage: rerun the results, or take a new baseline when the error is the baseline's), or another
language, schema, scored questions or expected sources (a new owner run is needed to make a new
baseline).
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from src import config, eval_results, observability


def main(args: Sequence[str] | None = None) -> int:
    """Compare a results file with the baseline and return the exit code."""
    observability.configure_logging()
    parser = argparse.ArgumentParser(description="Compare an evaluation run with the baseline.")
    parser.add_argument("results", type=Path, help="the results .json a run wrote")
    parser.add_argument(
        "--baseline", type=Path, default=config.EVAL_BASELINE_PATH, help="the baseline results"
    )
    options = parser.parse_args(sys.argv[1:] if args is None else args)
    try:
        results = eval_results.load_results(options.results)
        baseline = eval_results.load_results(options.baseline)
        comparison = eval_results.compare(results, baseline, eval_results.tolerance_for(baseline))
    except eval_results.ResultsFileError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("\n".join(comparison.lines))
    if comparison.below:
        print(f"Below the baseline: {', '.join(comparison.below)}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
