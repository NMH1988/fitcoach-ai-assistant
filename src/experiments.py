"""LangSmith experiments of the evaluation run (T9.33): datasets, traced turns, feedback scores.

Used only by `scripts/run_evaluation.py --langsmith` (a scan in `tests/test_tracing.py` keeps it
so). Each questions file becomes a LangSmith dataset (`sync_dataset()`): one example per question
and profile variant (q13 with its fixed profile and without), with a fixed ID worked out from the
dataset and the question, so uploading again only adds, changes or removes what the file changed.
Each run of the script becomes an experiment on that dataset (`start_experiment()`): every turn is
traced, through `tracing.RunTrace`, into the experiment's own project and linked to its example,
and the script then sends each turn's results as feedback scores (`expectation_feedback()`,
`score_feedback()`).

Unlike the app's runs, an experiment is not masked (owner's choice, 2026-11-12): it holds only
the evaluation's own text, the owner's questions and good answers, the made-up profile of a
question (`EvalItem.profile`), the CC BY and public domain chunks (the `<sources>` block shows
each chunk's title, year and tier; the turn's output carries the cited sources' cards with their
authors, licence and link, but a chunk found and not cited has no attribution in the trace), the
prompts and the answers. So a failed question can be read in the trace.
Only a run's error is reduced to its class name (`tracing.mask_error_only()`), as a traceback can
quote a provider's reply and the machine's paths. The unmasked client is built here, only after
`tracing.configure_tracing()` says tracing is on (the flag and the key, T9.8), and is never
installed as LangSmith's global client: the app's own
runs, and every run the script does not pass a `RunTrace` for (the judge's calls among them), go
through the masked one. LangSmith sends datasets and feedback as they are, with no anonymizer.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client
from langsmith import utils as ls_utils

from src import config, tracing
from src.eval_questions import EvalItem

NOT_SET_UP = (
    "--langsmith needs LangSmith tracing set up: the flag "
    f"{config.TRACING_FLAG_NAME} and the key {config.LANGSMITH_API_KEY_NAME} "
    "(.streamlit/secrets.toml or the environment)."
)
# The errors a LangSmith call may raise: its own, and the network's below it.
_LANGSMITH_ERRORS = (ls_utils.LangSmithError, requests.RequestException)
# The metadata keys this module writes on an example; LangSmith may add others of its own.
_EXAMPLE_METADATA_KEYS = ("question_id", "with_profile", "questions_file")


class ExperimentError(Exception):
    """LangSmith is not set up or could not be reached; `str()` is fixed text, no server reply."""


def _failed(what: str, exc: BaseException) -> ExperimentError:
    """Return an error naming what failed and the exception's class, never its message."""
    # A server reply could quote what was sent; the class name says enough to look further.
    return ExperimentError(f"LangSmith: {what} failed ({type(exc).__name__}).")


def build_client(
    api_key: str, *, session: requests.Session | None = None, batch: bool = True
) -> Client:
    """Return a LangSmith client for the EU endpoint that sends the evaluation's runs unmasked."""
    # `session` and `batch=False` are for tests, as in tracing.build_client(). Inputs, outputs and
    # metadata are not masked: an experiment holds the evaluation's own text only (module
    # docstring). An error keeps only its class name, as a traceback can quote a provider's reply
    # and the machine's paths (code review round 1). Never installed globally.
    return Client(
        api_url=config.LANGSMITH_ENDPOINT,
        api_key=api_key,
        session=session,
        auto_batch_tracing=batch,
        anonymizer=tracing.mask_error_only,
        omit_traced_runtime_info=True,
        tracing_mode="langsmith",
    )


def open_client() -> Client:
    """Return the experiments' client, or raise ExperimentError when tracing is not set up."""
    # The same switch as the app's tracing: the flag, the key and no write replicas (T9.8).
    if not tracing.configure_tracing():
        raise ExperimentError(NOT_SET_UP)
    api_key = config.get_langsmith_api_key()
    if api_key is None:
        raise ExperimentError(NOT_SET_UP)
    return build_client(api_key)


def example_key(item: EvalItem, with_profile: bool) -> str:
    """Return a question variant's name, as its run label starts (e.g. 'q13 (no profile)')."""
    return item.id if with_profile or item.profile is None else f"{item.id} (no profile)"


def variants(items: Sequence[EvalItem]) -> list[tuple[EvalItem, bool]]:
    """Return each question once, and a question with a profile twice: with it, then without."""
    found = []
    for item in items:
        if item.profile is not None:
            found.append((item, True))
        found.append((item, False))
    return found


def dataset_name(path: Path) -> str:
    """Return the dataset's name for a questions file, e.g. 'fitcoach-eval-eval_questions'."""
    return f"{config.EVAL_DATASET_PREFIX}{path.stem}"


def example_id(dataset_id: uuid.UUID, key: str) -> uuid.UUID:
    """Return the fixed ID of a question's variant in a dataset, so an upload never duplicates."""
    # Derived from the dataset's own ID: a dataset deleted and made again gets new example IDs.
    return uuid.uuid5(dataset_id, key)


def example_content(item: EvalItem, with_profile: bool, questions_file: str) -> dict[str, Any]:
    """Return an example's inputs, reference outputs and metadata for a question's variant."""
    profile = item.profile.model_dump(mode="json") if with_profile and item.profile else None
    return {
        "inputs": {"question": item.question, "profile": profile},
        "outputs": {
            "expected_sources": list(item.expected_sources),
            "good_answer": item.good_answer,
        },
        "metadata": {
            "question_id": item.id,
            "with_profile": with_profile,
            "questions_file": questions_file,
        },
    }


def _unchanged(example: Any, content: Mapping[str, Any]) -> bool:
    """Return True if a stored example already holds this content (its own metadata aside)."""
    metadata = example.metadata or {}
    return (
        (example.inputs or {}) == content["inputs"]
        and (example.outputs or {}) == content["outputs"]
        and all(metadata.get(key) == content["metadata"][key] for key in _EXAMPLE_METADATA_KEYS)
    )


@dataclass(frozen=True)
class SyncedDataset:
    """A questions file's dataset after the upload: its ID and each variant's example ID."""

    id: uuid.UUID
    name: str
    examples: Mapping[str, uuid.UUID]
    created: int = 0
    updated: int = 0
    deleted: int = 0


def sync_dataset(client: Client, path: Path, items: Sequence[EvalItem]) -> SyncedDataset:
    """Make the file's dataset hold exactly its questions, sending only what differs."""
    name = dataset_name(path)
    try:
        if client.has_dataset(dataset_name=name):
            dataset = client.read_dataset(dataset_name=name)
        else:
            dataset = client.create_dataset(
                name,
                description=(
                    f"The owner's evaluation questions from {path.name} (Fitcoach AI Assistant, "
                    "T9.33): synthetic test data, no user's data."
                ),
            )
        dataset_id = uuid.UUID(str(dataset.id))
        wanted = {
            example_id(dataset_id, example_key(item, with_profile)): (
                example_key(item, with_profile),
                example_content(item, with_profile, path.name),
            )
            for item, with_profile in variants(items)
        }
        stored = {
            uuid.UUID(str(example.id)): example
            for example in client.list_examples(dataset_id=dataset_id)
        }
        new = [
            {"id": key_id, **content}
            for key_id, (_, content) in wanted.items()
            if key_id not in stored
        ]
        changed = [
            {"id": key_id, **content}
            for key_id, (_, content) in wanted.items()
            if key_id in stored and not _unchanged(stored[key_id], content)
        ]
        removed = [key_id for key_id in stored if key_id not in wanted]
        if new:
            client.create_examples(dataset_id=dataset_id, examples=new)
        if changed:
            client.update_examples(dataset_id=dataset_id, updates=changed)
        if removed:
            client.delete_examples(removed)
    except _LANGSMITH_ERRORS as exc:
        raise _failed("uploading the dataset", exc) from None
    return SyncedDataset(
        id=dataset_id,
        name=name,
        examples={key: key_id for key_id, (key, _) in wanted.items()},
        created=len(new),
        updated=len(changed),
        deleted=len(removed),
    )


def experiment_name(
    commit: str | None, dirty: bool | None, answer_model: str, language: str, started: datetime
) -> str:
    """Return an experiment's name: the prefix, the commit, the answer model, language and time."""
    code = (commit or "")[:7] or "no-git"
    if dirty:
        code += "-dirty"
    model = answer_model.replace("/", "_")
    return f"{config.EVAL_EXPERIMENT_PREFIX}-{code}-{model}-{language}-{started:%Y%m%d-%H%M%S}"


@dataclass(frozen=True)
class Feedback:
    """One score sent for a turn: a key, a number or none, and an optional value and comment."""

    key: str
    score: float | None
    value: str | None = None
    comment: str | None = None


def expectation_feedback(
    expected: Sequence[str],
    found: Sequence[str],
    cited: Sequence[str],
    unexpected: Sequence[str],
    kind: str,
) -> list[Feedback]:
    """Return a turn's source checks as feedback, the same counts as the results file (T8.4)."""
    feedback = [Feedback("turn_kind", None, value=kind)]
    if expected:
        # The share of the expected sources found among the chunks the answer model got, and cited.
        feedback += [
            Feedback("expected_found", round(len(found) / len(expected), 4)),
            Feedback("expected_cited", round(len(cited) / len(expected), 4)),
        ]
    else:
        # A question that expects no source passes when the answer cites nothing.
        feedback.append(Feedback("cites_nothing", 0.0 if unexpected else 1.0))
    feedback.append(Feedback("unexpected_citations", float(len(unexpected))))
    return feedback


def score_feedback(scores: Mapping[str, Any]) -> list[Feedback]:
    """Return a turn's DeepEval scores (T9.10) as feedback, with the judge's reason as comment."""
    # A missing score is sent with its note as the value and no number, so a mean leaves it out.
    return [
        Feedback(name, score.score, value=score.note, comment=score.reason or None)
        for name, score in scores.items()
    ]


@dataclass
class Experiment:
    """One run of the evaluation as a LangSmith experiment: traces each turn, sends its scores."""

    client: Client
    name: str
    project_id: uuid.UUID
    examples: Mapping[str, uuid.UUID]
    failed: int = 0

    def trace(self, key: str) -> tracing.RunTrace:
        """Return the tracer and root run ID for one turn of this question's variant."""
        tracer = LangChainTracer(
            project_name=self.name, example_id=self.examples[key], client=self.client
        )
        return tracing.RunTrace((tracer,), uuid.uuid4())

    def record(self, run_id: uuid.UUID, feedback: Sequence[Feedback]) -> None:
        """Send a turn's feedback; a failure is counted, never raised, as the run is paid for."""
        for item in feedback:
            try:
                # With trace_id, LangSmith queues the feedback with the runs (sent by finish()).
                self.client.create_feedback(
                    run_id,
                    item.key,
                    score=item.score,
                    value=item.value,
                    comment=item.comment,
                    trace_id=run_id,
                )
            except _LANGSMITH_ERRORS:
                self.failed += 1

    def finish(self) -> None:
        """Wait a set time for the runs and feedback to be sent, then mark the experiment ended."""
        # One flush with a timeout: every tracer shares this client, and a tracer's own
        # wait_for_futures() flushes it with none, so a slow LangSmith would block the script
        # (code review round 1). LangSmith sends from a background thread that logs a refused
        # batch and never raises, so only what is still queued after the timeout is seen here.
        try:
            self.client.flush(timeout=config.EVAL_EXPERIMENT_FLUSH_SECONDS)
            queue = getattr(self.client, "tracing_queue", None)
            if queue is not None and queue.unfinished_tasks:
                raise ExperimentError(
                    "LangSmith: sending the experiment did not finish in "
                    f"{config.EVAL_EXPERIMENT_FLUSH_SECONDS} s."
                )
            self.client.update_project(self.project_id, end_time=datetime.now(UTC))
        except _LANGSMITH_ERRORS as exc:
            raise _failed("sending the experiment", exc) from None


def start_experiment(
    client: Client,
    dataset: SyncedDataset,
    *,
    name: str,
    metadata: Mapping[str, Any],
    repeat: int,
) -> Experiment:
    """Create the experiment's project on the dataset and return it, ready to trace turns."""
    try:
        project = client.create_project(
            name,
            description="An evaluation run of scripts/run_evaluation.py --langsmith (T9.33).",
            metadata=dict(metadata),
            reference_dataset_id=dataset.id,
            num_examples=len(dataset.examples),
            num_repetitions=repeat,
        )
    except _LANGSMITH_ERRORS as exc:
        raise _failed("creating the experiment", exc) from None
    return Experiment(client, name, uuid.UUID(str(project.id)), dataset.examples)
