"""Live check O5 for T6.1: the owner's evaluation questions through the app's whole chat turn.

Run by the owner from the repo root, after the index is built, with the key set up:

    python scripts/run_evaluation.py [--repeat N] [--language en|de] [data/eval_questions.json]

For the German questions (T7.2):

    python scripts/run_evaluation.py --language de data/eval_questions_de.json

Each question goes through `chat.run_turn()`, the function the app calls: the input guard and the
domain guardrails, then the agent with its tools, the knowledge base search among them (query
translation and hybrid search; T9.3: the agent decides whether to search). The models
are the app's own (`llm.build_chat_model()`). A question with a "profile" (q13) runs twice: with
that fixed session profile, then with none. Other questions run with no profile, as a new visitor
asks them. `--repeat N` runs every question N times (default 1). `--language` is the answer
language the app's EN | DE control would set (default en, T7.2); the questions keep their own
language either way.

For each run the script prints how the turn ended, the searches the agent ran with their filters,
the sources found (in [S#] order over all its searches; "*" marks a chunk found by keyword only),
the sources the answer cites, whether
the expected sources were found and cited (or, with none expected, whether the answer cites
nothing), the tools called and the tokens and cost. Then the run's totals. It writes a full
report, with each answer, its tool results and the text of every chunk found, to a gitignored
file in data/eval_runs/ for judging the citations against the good answers. It costs a few US
cents and never prints or writes the key. Record the results in docs/TESTING.md.

Next to the report it writes a results file with the same name and a .json ending (T8.4): the run's
commit, models, language and date, and for each run only IDs and counts (how it ended, the expected
sources found and cited, the sources cited that were not expected, the tools, tokens and cost). It
holds no answer, question or chunk text, so one run can be committed as data/eval_baseline.json;
scripts/check_eval_baseline.py compares a later run with it.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel

from src import chat, config, eval_results, guard, i18n, llm, observability, usage
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
    # Which asking of this question and profile variant this is, from 1 to --repeat (T8.4).
    number: int = 1


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
    asked: Counter[tuple[str, bool]] = Counter()
    for label, item, with_profile in runs:
        asked[item.id, with_profile] += 1
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
            prices=lambda: prices,
        )
        # Each search reports its newly labelled chunks, so together they are in [S#] order.
        chunks = tuple(chunk for found in seen for chunk in found)
        done.append(
            EvalRun(
                label,
                item,
                with_profile,
                result,
                chunks,
                usage.price_turn(result.usage, prices),
                asked[item.id, with_profile],
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


@dataclass(frozen=True)
class Expectation:
    """How a run met its question's expected sources (the data behind the summary line, T8.4)."""

    expected: tuple[str, ...]
    # The expected sources among the chunks the answer model got, and those the answer cites.
    found: tuple[str, ...]
    cited: tuple[str, ...]
    # The sources cited that are not expected: all of them when the question expects none.
    unexpected: tuple[str, ...]


def expectation(run: EvalRun) -> Expectation:
    """Return which expected sources the run found and cited, and which others it cited."""
    cited = [card.source_id for card in run.result.sources]
    expected = run.item.expected_sources
    found_ids = {str(chunk.metadata.get("source_id")) for chunk in run.chunks}
    return Expectation(
        expected=tuple(expected),
        found=tuple(source_id for source_id in expected if source_id in found_ids),
        cited=tuple(source_id for source_id in expected if source_id in cited),
        unexpected=tuple(source_id for source_id in cited if source_id not in expected),
    )


def expectation_line(run: EvalRun) -> str:
    """Return whether the expected sources were found and cited, or whether nothing was cited."""
    met = expectation(run)
    if not met.expected:
        verdict = (
            "cites nothing" if not met.unexpected else f"cites {_ids(met.unexpected)}: check them"
        )
        return f"expected none: {verdict}"
    return f"expected {_ids(met.expected)}: found {_ids(met.found)}, cited {_ids(met.cited)}"


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
    text += " (dropped: nothing passed them)" if search.filter_dropped else ""
    return text + (" (no usable rewrite: the query alone)" if search.fell_back else "")


def _searches(searches: Sequence[chat.SearchDetails]) -> str:
    """Return each search's passages found and filters in a few words, or 'none'."""
    return (
        "; ".join(f"{len(search.labels)} found, filters: {_filters(search)}" for search in searches)
        or "none"
    )


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
        if result.searches is not None:
            lines.append(f"  searches: {_searches(result.searches)}")
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


def run_records(runs: Sequence[EvalRun]) -> list[eval_results.RunRecord]:
    """Return each run as a results-file record: IDs and counts only, never any text (T8.4)."""
    records = []
    for run in runs:
        met = expectation(run)
        records.append(
            eval_results.RunRecord(
                id=run.item.id,
                run=run.number,
                with_profile=run.with_profile,
                kind=run.result.kind,
                code=run.result.code,
                expected=met.expected,
                expected_found=met.found,
                expected_cited=met.cited,
                unexpected_citations=met.unexpected,
                # A tool name the model made up is None here; it is never written (T8.2's rule).
                tools=tuple((tool.name or "unknown", tool.status) for tool in run.result.tool_runs),
                tokens=run.cost.tokens,
                cost_usd=eval_results.cost_text(run.cost.cost),
            )
        )
    return records


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
            f"**Turn:** {result.kind} · {usage.format_turn(run.cost)}",
        ]
        if result.searches is not None:
            if not result.searches:
                parts.append("**Searches:** none")
            for number, search in enumerate(result.searches, start=1):
                # Model output on one line each and escaped, so a newline, a heading, a link or an
                # image in it stays text when the report is previewed.
                query = chat.escape_markdown(" ".join(search.query.split()))
                rewrites = (
                    "; ".join(chat.escape_markdown(" ".join(r.split())) for r in search.rewrites)
                    or "none"
                )
                labels = ", ".join(f"S{label}" for label in search.labels) or "nothing"
                parts += [
                    f"**Search {number}:** {query} · rewrites: {rewrites} · filters: "
                    f"{_filters(search)} · found: {labels}"
                ]
            parts.append(f"**Cited:** {_cited(result)} · {expectation_line(run)}")
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
    observability.configure_logging()
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
    results = eval_results.write_results(
        eval_results.results_document(
            run_records(runs),
            # The commit of the code that ran: `src` is read from the project folder, which is not
            # always the folder the command was started in (T8.3's two wrong runs).
            git=eval_results.git_state(config.PROJECT_ROOT),
            models={
                "answer": usage.model_name(chat_model),
                "query_translation": usage.model_name(translation_model),
                "embedding": config.EMBEDDING_MODEL,
            },
            language=options.language,
            repeat=options.repeat,
            started=started,
            questions_file=options.path.name,
        ),
        report.with_suffix(".json"),
    )
    print(f"Results file: {results}")
    return 1 if any(run.result.kind == "error" for run in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
