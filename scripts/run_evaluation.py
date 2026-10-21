"""Live check O5 for T6.1: the owner's evaluation questions through the app's whole chat turn.

Run by the owner from the repo root, after the index is built, with the key set up:

    python scripts/run_evaluation.py [--repeat N] [--language en|de] [data/eval_questions.json]

For the German questions (T7.2):

    python scripts/run_evaluation.py --language de data/eval_questions_de.json

Each question goes through `chat.run_turn()`, the function the app calls: the input guard and the
domain guardrails, query translation, hybrid search, the answer model with its tools. The models
are the app's own (`llm.build_chat_model()`). A question with a "profile" (q13) runs twice: with
that fixed session profile, then with none. Other questions run with no profile, as a new visitor
asks them. `--repeat N` runs every question N times (default 1). `--language` is the answer
language the app's EN | DE control would set (default en, T7.2); the questions keep their own
language either way.

For each run the script prints how the turn ended, the plan's flags and filters, the sources found
(in [S#] order; "*" marks a chunk found by keyword only), the sources the answer cites, whether
the expected sources were found and cited (or, with none expected, whether the answer cites
nothing), the tools called and the tokens and cost. Then the run's totals. It writes a full
report, with each answer, its tool results and the text of every chunk found, to a gitignored
file in data/eval_runs/ for judging the citations against the good answers. It costs a few US
cents and never prints or writes the key. Record the results in docs/TESTING.md.
"""

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel

from src import chat, config, guard, i18n, llm, usage
from src.eval_questions import EvalItem, QuestionsFileError, load_eval_items
from src.rag import hybrid, store
from src.rag.retriever import RetrievedChunk
from src.rag.sources import Source
from src.usage import ModelPrice, TurnUsage


@dataclass(frozen=True)
class EvalRun:
    """One question asked once: its label, whether a profile was set and what the turn gave."""

    label: str
    item: EvalItem
    with_profile: bool
    result: chat.TurnResult
    # The chunks the answer model got, in [S#] order; empty when the turn ended before the search.
    chunks: tuple[RetrievedChunk, ...]
    cost: TurnUsage


def planned_runs(items: Sequence[EvalItem], repeat: int) -> list[tuple[str, EvalItem, bool]]:
    """Return each run's label, question and whether it uses the question's profile."""
    runs = []
    for item in items:
        variants = [(item.id, False)]
        if item.profile is not None:
            variants = [(item.id, True), (f"{item.id} (no profile)", False)]
        for label, with_profile in variants:
            for number in range(1, repeat + 1):
                suffix = f" run {number}" if repeat > 1 else ""
                runs.append((label + suffix, item, with_profile))
    return runs


def evaluate(
    items: Sequence[EvalItem],
    *,
    index: Chroma,
    chat_model: BaseChatModel,
    translation_model: BaseChatModel,
    manifest: Mapping[str, Source],
    prices: Mapping[str, ModelPrice] | None,
    repeat: int = 1,
    language: i18n.Language = "en",
) -> list[EvalRun]:
    """Ask every question through the app's chat turn, in this answer language; return the runs."""
    runs = planned_runs(items, repeat)
    # One run may ask more questions than the app's per-minute limit allows.
    limiter = guard.RateLimiter(per_window=len(runs), per_session=len(runs))
    keywords = hybrid.build_keyword_index(index)
    done = []
    for label, item, with_profile in runs:
        seen: list[Sequence[RetrievedChunk]] = []
        result = chat.run_turn(
            item.question,
            limiter,
            open_index=lambda: index,
            chat_model=lambda: chat_model,
            translation_model=lambda: translation_model,
            manifest=manifest,
            user=item.profile if with_profile else None,
            keyword_index=lambda _: keywords,
            on_chunks=seen.append,
            language=language,
        )
        chunks = tuple(seen[0]) if seen else ()
        done.append(
            EvalRun(
                label, item, with_profile, result, chunks, usage.price_turn(result.usage, prices)
            )
        )
    return done


def _found(chunks: Sequence[RetrievedChunk]) -> str:
    """Return the source IDs of the chunks found, in [S#] order, e.g. '#4 #4* #10'."""
    return (
        " ".join(
            f"#{chunk.metadata.get('source_id')}" + ("*" if chunk.distance is None else "")
            for chunk in chunks
        )
        or "nothing"
    )


def _cited(result: chat.TurnResult) -> str:
    """Return the cited sources with their labels, e.g. '#7 (S1, S4), #11 (S2)'."""
    return (
        ", ".join(f"#{card.source_id} ({', '.join(card.labels)})" for card in result.sources)
        or "nothing"
    )


def _ids(source_ids: Sequence[str]) -> str:
    """Return source IDs as '#7 #11', or 'none'."""
    return " ".join(f"#{source_id}" for source_id in source_ids) or "none"


def expectation_line(run: EvalRun) -> str:
    """Return whether the expected sources were found and cited, or whether nothing was cited."""
    cited = [card.source_id for card in run.result.sources]
    expected = run.item.expected_sources
    if not expected:
        verdict = "cites nothing" if not cited else f"cites {_ids(cited)}: check them"
        return f"expected none: {verdict}"
    found_ids = {str(chunk.metadata.get("source_id")) for chunk in run.chunks}
    found = [source_id for source_id in expected if source_id in found_ids]
    cited_expected = [source_id for source_id in expected if source_id in cited]
    return f"expected {_ids(expected)}: found {_ids(found)}, cited {_ids(cited_expected)}"


def _flag(value: bool | None) -> str:
    """Return a plan flag as 'yes', 'no' or 'no plan'."""
    return "no plan" if value is None else ("yes" if value else "no")


def _filters(search: chat.SearchDetails) -> str:
    """Return the plan's filters in a few words, saying when they were dropped."""
    parts = []
    if search.topics:
        parts.append("topics " + ", ".join(search.topics))
    if search.min_year is not None:
        parts.append(f"from {search.min_year}")
    if search.evidence_tier is not None:
        parts.append(f"tier {search.evidence_tier}")
    text = "; ".join(parts) or "none"
    return text + (" (dropped: nothing passed them)" if search.filter_dropped else "")


def _tools(result: chat.TurnResult) -> str:
    """Return the tools the model called with their status, e.g. 'lookup_food_nutrition (found)'."""
    return (
        ", ".join(f"{run.name or 'unknown tool'} ({run.status})" for run in result.tool_runs)
        or "none"
    )


def summary_lines(runs: Sequence[EvalRun]) -> list[str]:
    """Return the printed report: one block per run, then the totals."""
    lines = []
    for run in runs:
        result = run.result
        head = f"{run.label}: {result.kind}"
        if result.kind != "answer":
            head += f" - {result.text}"
        lines.append(f"{head} · {usage.format_turn(run.cost)}")
        if result.search is not None:
            search = result.search
            lines.append(
                f"  plan: needs_tool {_flag(search.needs_tool)}, "
                f"needs_profile {_flag(search.needs_profile)}; filters: {_filters(search)}; "
                f"profile sent: {'yes' if result.profile_sent else 'no'}"
            )
            lines.append(f"  found: {_found(run.chunks)}")
            lines.append(f"  cited: {_cited(result)}")
            lines.append(f"  tools: {_tools(result)}")
            lines.append(f"  {expectation_line(run)}")
    session = usage.session_usage(run.cost for run in runs)
    errors = sum(run.result.kind == "error" for run in runs)
    lines.append(
        f"{len(runs)} runs, {errors} ended with an error · {usage.format_session(session)}"
    )
    return lines


def _fence(text: str) -> str:
    """Return the text in a fence no line of it can close."""
    fence = "~~~~"
    while fence in text:
        fence += "~"
    return f"{fence}\n{text}\n{fence}"


def _chunk_block(label: int, chunk: RetrievedChunk) -> str:
    """Return one chunk found, with its label, source, section, distance and whole text."""
    meta = chunk.metadata
    distance = "keyword only" if chunk.distance is None else f"distance {chunk.distance:.3f}"
    head = (
        f"- **S{label}** #{meta.get('source_id')} {meta.get('title')} ({meta.get('year')}) · "
        f"{meta.get('section')} · {distance}"
    )
    return f"{head}\n\n{_fence(chunk.text)}"


def report_text(runs: Sequence[EvalRun], started: datetime, language: i18n.Language = "en") -> str:
    """Return the full Markdown report: each run's answer, tool results and chunks found."""
    parts = [
        f"# Evaluation run {started:%Y-%m-%d %H:%M}",
        "Local report of scripts/run_evaluation.py (T6.1). Not committed: it holds article text.",
        f"**Answer language:** {language}",
        _fence("\n".join(summary_lines(runs))),
    ]
    for run in runs:
        result = run.result
        parts += [
            f"## {run.label}",
            f"**Question:** {run.item.question}",
            f"**Good answer:** {run.item.good_answer}",
            f"**Session profile:** {'the fixed profile' if run.with_profile else 'none'}",
            f"**Turn:** {result.kind} · {usage.format_turn(run.cost)} · "
            f"profile block sent: {'yes' if result.profile_sent else 'no'}",
        ]
        if result.search is not None:
            search = result.search
            # Model output on one line each, so a newline or a heading in a rewrite stays text.
            rewrites = "; ".join(" ".join(rewrite.split()) for rewrite in search.rewrites) or "none"
            parts += [
                f"**Rewrites:** {rewrites}",
                f"**Plan:** needs_tool {_flag(search.needs_tool)}, needs_profile "
                f"{_flag(search.needs_profile)}; filters: {_filters(search)}",
                f"**Cited:** {_cited(result)} · {expectation_line(run)}",
            ]
        parts += ["### Answer", _fence(result.text)]
        if result.tool_runs:
            parts.append("### Tool results")
            for tool_run in result.tool_runs:
                parts.append(f"- {tool_run.name or 'unknown tool'} ({tool_run.status})")
                parts.append(_fence(tool_run.result.model_dump_json(indent=2)))
        if run.chunks:
            parts.append("### Chunks found, in [S#] order")
            parts += [_chunk_block(n, chunk) for n, chunk in enumerate(run.chunks, start=1)]
    return "\n\n".join(parts) + "\n"


def write_report(
    runs: Sequence[EvalRun], started: datetime, folder: Path, language: i18n.Language = "en"
) -> Path:
    """Write the full report into the folder and return its path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run-{started:%Y%m%d-%H%M%S}.md"
    path.write_text(report_text(runs, started, language), encoding="utf-8")
    return path


def _prices() -> Mapping[str, ModelPrice] | None:
    """Return OpenRouter's public prices, or None when they cannot be read (costs then unknown)."""
    try:
        return usage.fetch_prices()
    except usage.PriceError:
        return None


def main(args: Sequence[str] | None = None) -> int:
    """Run the evaluation questions through the app's chat turn and return the exit code."""
    parser = argparse.ArgumentParser(description="Run the owner's evaluation questions (T6.1).")
    parser.add_argument("path", nargs="?", type=Path, default=config.EVAL_QUESTIONS_PATH)
    parser.add_argument("--repeat", type=int, default=1, help="times to ask each question")
    parser.add_argument(
        "--language",
        choices=i18n.LANGUAGES,
        default="en",
        help="the answer language, as the app's EN | DE control sets it (T7.2)",
    )
    options = parser.parse_args(sys.argv[1:] if args is None else args)
    if options.repeat < 1:
        print("--repeat must be at least 1.", file=sys.stderr)
        return 2
    try:
        items = load_eval_items(options.path)
    except QuestionsFileError as exc:
        print(exc, file=sys.stderr)
        return 2
    started = datetime.now()
    try:
        # Built and opened before the first question, so a missing key or index stops the run.
        index = store.open_index()
        chat_model = llm.build_chat_model()
        translation_model = llm.build_chat_model(
            config.QUERY_TRANSLATION_MODEL, config.QUERY_TRANSLATION_MAX_TOKENS
        )
    except store.IndexNotReadyError as exc:
        print(f"Evaluation not run: {exc}", file=sys.stderr)
        return 1
    except config.SecretsFileError:
        print(f"Evaluation not run: {config.SECRETS_FILE_MESSAGE}", file=sys.stderr)
        return 1
    except config.MissingAPIKeyError:
        print(f"Evaluation not run: {config.MISSING_KEY_MESSAGE}", file=sys.stderr)
        return 1
    runs = evaluate(
        items,
        index=index,
        chat_model=chat_model,
        translation_model=translation_model,
        manifest=chat.manifest_by_id(),
        prices=_prices(),
        repeat=options.repeat,
        language=options.language,
    )
    print(f"Answer language: {options.language}")
    print("\n".join(summary_lines(runs)))
    report = write_report(runs, started, config.EVAL_RUNS_DIR, options.language)
    print(f"Full report: {report}")
    return 1 if any(run.result.kind == "error" for run in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
