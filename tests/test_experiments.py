"""LangSmith experiments of the evaluation run (T9.33): datasets, turns, feedback; no network.

The dataset and feedback calls go to `FakeLangSmith`, a stand-in for LangSmith's client that keeps
what it was sent. The traced turn goes through LangSmith's real client on the fake `requests`
session of tests/test_tracing.py, so the payloads are the ones it would send.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import langsmith
import pytest
import requests
from langsmith import utils as ls_utils

from src import chat, config, experiments, guard, tracing
from src.eval_questions import EvalItem
from tests import test_observability as obs
from tests import test_tracing as tracing_tests
from tests.fakes import PROFILE, ScriptedTranslator

# The canary fixtures of the log tests, as in tests/test_tracing.py.
canary_setup = obs.canary_setup
index_path = obs.index_path
index = obs.index
traced = tracing_tests.traced

QUESTIONS_FILE = Path("data/eval_questions.json")
# A reply LangSmith could send, which an error must never repeat.
SERVER_REPLY = "server reply quoting CANARY-SENT text"


class FakeLangSmith:
    """A stand-in for LangSmith's client: keeps datasets, examples, projects and feedback."""

    def __init__(self) -> None:
        """Start with nothing stored and no call made."""
        self.datasets: dict[str, SimpleNamespace] = {}
        self.examples: dict[uuid.UUID, dict[uuid.UUID, SimpleNamespace]] = {}
        self.calls: list[tuple] = []
        self.feedback: list[dict] = []
        self.projects: list[dict] = []
        self.ended: list[uuid.UUID] = []
        self.flushed = 0
        self.fail_on: str | None = None

    def _call(self, name: str, *details) -> None:
        """Record a call, and fail it when the test asked for that."""
        self.calls.append((name, *details))
        if self.fail_on == name:
            raise ls_utils.LangSmithError(SERVER_REPLY)

    def has_dataset(self, *, dataset_name: str) -> bool:
        """Return whether a dataset of this name exists."""
        self._call("has_dataset", dataset_name)
        return dataset_name in self.datasets

    def read_dataset(self, *, dataset_name: str) -> SimpleNamespace:
        """Return the dataset of this name."""
        self._call("read_dataset", dataset_name)
        return self.datasets[dataset_name]

    def create_dataset(self, name: str, *, description: str) -> SimpleNamespace:
        """Create an empty dataset with a new ID."""
        self._call("create_dataset", name)
        dataset = SimpleNamespace(id=uuid.uuid4(), name=name, description=description)
        self.datasets[name] = dataset
        self.examples[dataset.id] = {}
        return dataset

    def list_examples(self, *, dataset_id: uuid.UUID) -> list[SimpleNamespace]:
        """Return the dataset's examples."""
        self._call("list_examples", dataset_id)
        return list(self.examples[dataset_id].values())

    def _store(self, dataset_id: uuid.UUID, example: dict) -> None:
        """Store an example as LangSmith does, adding a metadata key of its own."""
        metadata = {**example["metadata"], "dataset_split": ["base"]}
        self.examples[dataset_id][example["id"]] = SimpleNamespace(
            id=example["id"],
            inputs=json.loads(json.dumps(example["inputs"])),
            outputs=json.loads(json.dumps(example["outputs"])),
            metadata=metadata,
        )

    def create_examples(self, *, dataset_id: uuid.UUID, examples: list[dict]) -> None:
        """Add the examples."""
        self._call("create_examples", len(examples))
        for example in examples:
            assert example["id"] not in self.examples[dataset_id]
            self._store(dataset_id, example)

    def update_examples(self, *, dataset_id: uuid.UUID, updates: list[dict]) -> None:
        """Replace the examples."""
        self._call("update_examples", len(updates))
        for example in updates:
            assert example["id"] in self.examples[dataset_id]
            self._store(dataset_id, example)

    def delete_examples(self, example_ids: list[uuid.UUID]) -> None:
        """Remove the examples."""
        self._call("delete_examples", len(example_ids))
        for examples in self.examples.values():
            for example_id in example_ids:
                examples.pop(example_id, None)

    def create_project(self, name: str, **kwargs) -> SimpleNamespace:
        """Create an experiment's project and return it with a new ID."""
        self._call("create_project", name)
        project = SimpleNamespace(id=uuid.uuid4(), name=name)
        self.projects.append({"name": name, "id": project.id, **kwargs})
        return project

    def create_feedback(self, run_id, key, **kwargs) -> None:
        """Keep a feedback score."""
        self._call("create_feedback", key)
        self.feedback.append({"run_id": run_id, "key": key, **kwargs})

    def flush(self, timeout=None) -> None:
        """Count a flush."""
        self._call("flush")
        self.flushed += 1

    def update_project(self, project_id, *, end_time) -> None:
        """Keep the ended project's ID."""
        self._call("update_project")
        self.ended.append(project_id)

    def sent(self, name: str) -> list[tuple]:
        """Return the calls of this name."""
        return [call for call in self.calls if call[0] == name]


def _item(id: str, question: str = "How much protein per meal?", profile=None) -> EvalItem:
    """Return an evaluation question with a made-up good answer."""
    return EvalItem(
        id=id,
        question=question,
        expected_sources=["4"],
        good_answer=f"A made-up good answer for {id}.",
        profile=profile,
    )


ITEMS = [_item("q1"), _item("q13", "What are my daily targets?", profile=PROFILE)]


# --- The dataset (criterion 1) --------------------------------------------------------------------


def test_each_question_and_profile_variant_is_one_example():
    """q13 with its profile and without are two examples, named as the run labels start."""
    assert [
        (experiments.example_key(item, with_profile), with_profile)
        for item, with_profile in experiments.variants(ITEMS)
    ] == [("q1", False), ("q13", True), ("q13 (no profile)", False)]


def test_the_first_upload_creates_the_dataset_and_its_examples():
    """The file's dataset is made with every variant, the profile only in the profile one."""
    client = FakeLangSmith()
    synced = experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    assert synced.name == "fitcoach-eval-eval_questions"
    assert (synced.created, synced.updated, synced.deleted) == (3, 0, 0)
    stored = {
        example.metadata["question_id"] + str(example.metadata["with_profile"]): example
        for example in client.examples[synced.id].values()
    }
    assert stored["q13True"].inputs["profile"] == PROFILE.model_dump(mode="json")
    assert stored["q13False"].inputs["profile"] is None
    assert stored["q1False"].inputs == {"question": ITEMS[0].question, "profile": None}
    assert stored["q1False"].outputs == {
        "expected_sources": ["4"],
        "good_answer": "A made-up good answer for q1.",
    }
    assert stored["q1False"].metadata["questions_file"] == "eval_questions.json"
    assert set(synced.examples) == {"q1", "q13", "q13 (no profile)"}


def test_uploading_the_same_file_again_sends_no_example():
    """A second upload of an unchanged file adds, changes and removes nothing."""
    client = FakeLangSmith()
    first = experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    client.calls.clear()
    second = experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    assert second.examples == first.examples
    assert (second.created, second.updated, second.deleted) == (0, 0, 0)
    assert [call[0] for call in client.calls] == ["has_dataset", "read_dataset", "list_examples"]
    assert len(client.examples[first.id]) == 3


def test_an_upload_adds_changes_and_removes_only_what_the_file_changed():
    """A new question is added, an edited one changed and a dropped one removed, nothing else."""
    client = FakeLangSmith()
    first = experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    edited = [_item("q1", "How much protein per meal, edited?"), _item("q2")]
    second = experiments.sync_dataset(client, QUESTIONS_FILE, edited)
    assert (second.created, second.updated, second.deleted) == (1, 1, 2)
    assert second.examples["q1"] == first.examples["q1"]
    questions = sorted(example.inputs["question"] for example in client.examples[first.id].values())
    assert questions == ["How much protein per meal, edited?", "How much protein per meal?"]


def test_example_ids_are_fixed_per_dataset_and_differ_between_datasets():
    """The same question gets the same ID in its dataset and another one in another dataset."""
    one, other = uuid.uuid4(), uuid.uuid4()
    assert experiments.example_id(one, "q1") == experiments.example_id(one, "q1")
    assert experiments.example_id(one, "q1") != experiments.example_id(other, "q1")
    assert experiments.example_id(one, "q13") != experiments.example_id(one, "q13 (no profile)")


def test_each_questions_file_has_a_dataset_of_its_own():
    """The four questions files give four dataset names (owner's choice, 2026-11-12)."""
    paths = [
        config.EVAL_QUESTIONS_PATH,
        config.EVAL_QUESTIONS_DE_PATH,
        config.EVAL_QUESTIONS_TRAINING_PATH,
        config.EVAL_QUESTIONS_TRAINING_DE_PATH,
    ]
    names = {experiments.dataset_name(path) for path in paths}
    assert len(names) == 4
    assert all(name.startswith(config.EVAL_DATASET_PREFIX) for name in names)


@pytest.mark.parametrize("failing", ["has_dataset", "list_examples", "create_examples"])
def test_a_failed_upload_names_the_error_class_never_the_reply(failing):
    """An upload that fails raises ExperimentError with fixed text and the class name."""
    client = FakeLangSmith()
    client.fail_on = failing
    with pytest.raises(experiments.ExperimentError) as raised:
        experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    assert str(raised.value) == "LangSmith: uploading the dataset failed (LangSmithError)."
    assert SERVER_REPLY not in str(raised.value)


def test_a_network_error_is_an_experiment_error_too():
    """A connection error below LangSmith is caught like its own errors."""
    client = FakeLangSmith()

    def offline(**_kwargs):
        """Fail as a request with no network does."""
        raise requests.ConnectionError(SERVER_REPLY)

    client.has_dataset = offline
    with pytest.raises(experiments.ExperimentError, match=r"\(ConnectionError\)"):
        experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)


# --- The experiment and its feedback (criterion 2) ------------------------------------------------


def test_the_experiment_is_named_by_commit_model_language_and_time():
    """The name holds the short commit, a dirty mark, the model without '/', language and time."""
    started = datetime(2026, 11, 12, 21, 5, 9)
    assert (
        experiments.experiment_name("a" * 40, False, "openai/gpt-5-mini", "de", started)
        == "fitcoach-eval-aaaaaaa-openai_gpt-5-mini-de-20261112-210509"
    )
    assert experiments.experiment_name(None, None, "m", "en", started).startswith(
        "fitcoach-eval-no-git-m-en-"
    )
    assert "-aaaaaaa-dirty-" in experiments.experiment_name("a" * 40, True, "m", "en", started)


def test_the_experiment_s_project_is_linked_to_the_dataset():
    """start_experiment() creates a project on the dataset with the run's metadata."""
    client = FakeLangSmith()
    synced = experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    experiment = experiments.start_experiment(
        client, synced, name="fitcoach-eval-x", metadata={"commit": "abc"}, repeat=3
    )
    [project] = client.projects
    assert project["reference_dataset_id"] == synced.id
    assert project["metadata"] == {"commit": "abc"}
    assert (project["num_examples"], project["num_repetitions"]) == (3, 3)
    assert experiment.project_id == project["id"]
    assert experiment.examples == synced.examples


def test_a_failed_project_stops_with_an_experiment_error():
    """A project LangSmith refuses raises ExperimentError, never its reply."""
    client = FakeLangSmith()
    synced = experiments.sync_dataset(client, QUESTIONS_FILE, ITEMS)
    client.fail_on = "create_project"
    with pytest.raises(experiments.ExperimentError) as raised:
        experiments.start_experiment(client, synced, name="x", metadata={}, repeat=1)
    assert SERVER_REPLY not in str(raised.value)


def test_the_source_checks_are_the_results_file_s_shares():
    """Found and cited are shares of the expected sources; none expected checks for no citation."""
    feedback = experiments.expectation_feedback(["1", "3"], ["1"], [], ["7"], "answer")
    assert {item.key: (item.score, item.value) for item in feedback} == {
        "turn_kind": (None, "answer"),
        "expected_found": (0.5, None),
        "expected_cited": (0.0, None),
        "unexpected_citations": (1.0, None),
    }
    none_expected = experiments.expectation_feedback([], [], [], [], "no_sources")
    assert {item.key: item.score for item in none_expected} == {
        "turn_kind": None,
        "cites_nothing": 1.0,
        "unexpected_citations": 0.0,
    }
    assert experiments.expectation_feedback([], [], [], ["2"], "answer")[1].score == 0.0


def test_scores_are_sent_with_the_judge_s_reason_and_a_missing_one_with_its_note():
    """A DeepEval score keeps the judge's reason as comment; a missing one has no number."""
    scores = {
        "faithfulness": SimpleNamespace(score=0.8, note=None, reason="Claim two is unsupported."),
        "answer_relevancy": SimpleNamespace(score=None, note="no_chunks", reason=""),
    }
    assert experiments.score_feedback(scores) == [
        experiments.Feedback("faithfulness", 0.8, None, "Claim two is unsupported."),
        experiments.Feedback("answer_relevancy", None, "no_chunks", None),
    ]


def test_feedback_goes_to_the_turn_s_root_run_and_a_failure_is_counted():
    """Each score names the root run as run and trace; a refused one is counted, not raised."""
    client = FakeLangSmith()
    experiment = experiments.Experiment(client, "x", uuid.uuid4(), {"q1": uuid.uuid4()})
    run_id = uuid.uuid4()
    experiment.record(run_id, [experiments.Feedback("expected_found", 1.0)])
    [sent] = client.feedback
    assert (sent["run_id"], sent["trace_id"], sent["score"]) == (run_id, run_id, 1.0)
    client.fail_on = "create_feedback"
    experiment.record(run_id, [experiments.Feedback("a", 1.0), experiments.Feedback("b", 0.0)])
    assert experiment.failed == 2


def test_finish_flushes_and_ends_the_experiment():
    """finish() waits for the runs and feedback, then marks the experiment's project ended."""
    client = FakeLangSmith()
    project = uuid.uuid4()
    experiments.Experiment(client, "x", project, {}).finish()
    assert client.flushed == 1
    assert client.ended == [project]
    client.fail_on = "flush"
    with pytest.raises(experiments.ExperimentError, match="sending the experiment"):
        experiments.Experiment(client, "x", project, {}).finish()


# --- Only with LangSmith set up (criterion 3) -----------------------------------------------------


@pytest.mark.parametrize(("flag", "key"), [(False, tracing_tests.FAKE_LANGSMITH_KEY), (True, None)])
def test_no_client_is_built_without_the_flag_and_the_key(monkeypatch, flag, key):
    """open_client() refuses, building no client, unless T9.8's flag and key are both set."""
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setattr(config, "tracing_requested", lambda: flag)
    monkeypatch.delenv(config.LANGSMITH_API_KEY_NAME, raising=False)
    if key is not None:
        monkeypatch.setenv(config.LANGSMITH_API_KEY_NAME, key)

    def never(*_args, **_kwargs):
        """Fail the test if a client is built."""
        raise AssertionError("no client may be built")

    monkeypatch.setattr(experiments, "build_client", never)
    with pytest.raises(experiments.ExperimentError) as raised:
        experiments.open_client()
    assert str(raised.value) == experiments.NOT_SET_UP


def test_the_experiments_client_is_unmasked_but_never_the_global_one(traced):
    """open_client() builds an EU client that masks errors only; the global client stays masked."""
    client = experiments.open_client()
    assert client.api_url == config.LANGSMITH_ENDPOINT
    assert client._anonymizer is tracing.mask_error_only
    assert client._omit_traced_runtime_info is True
    assert client.tracing_mode == "langsmith"
    assert langsmith.run_trees.get_cached_client()._anonymizer is tracing.mask


# --- What goes where (criterion 4) ----------------------------------------------------------------


def _turn(index, run_trace=None):
    """Run one canary turn with the canary profile, traced into the experiment when given."""
    return chat.run_turn(
        obs.CANARY_QUESTION,
        guard.RateLimiter(),
        open_index=lambda: index,
        chat_model=lambda: obs._answer_model(),
        translation_model=lambda: ScriptedTranslator(),
        user=obs.CANARY_PROFILE,
        prices=lambda: {},
        run_trace=run_trace,
    )


def test_an_experiment_turn_goes_unmasked_to_its_project_only(index, traced):
    """The turn's runs reach the experiment, linked to its example; none reach the app's project."""
    session = tracing_tests.RecordingSession()
    client = experiments.build_client(
        tracing_tests.FAKE_LANGSMITH_KEY, session=session, batch=False
    )
    example = uuid.uuid4()
    experiment = experiments.Experiment(client, "fitcoach-eval-test", uuid.uuid4(), {"q1": example})
    run_trace = experiment.trace("q1")
    result = _turn(index, run_trace)
    assert result.kind == "answer"
    runs = session.runs()
    [root] = [run for run in runs if run.get("id") == str(run_trace.run_id)][:1]
    assert root["session_name"] == "fitcoach-eval-test"
    assert root["reference_example_id"] == str(example)
    assert all(
        run.get("session_name", "fitcoach-eval-test") == "fitcoach-eval-test" for run in runs
    )
    # Not masked: the evaluation's own question and answer can be read.
    assert "CANARY-Q" in json.dumps(runs) and "CANARY-A" in json.dumps(runs)
    # LangChain added no tracer of its own: nothing went to the app's masked project.
    assert traced.runs() == []


def test_the_app_s_turns_stay_masked_after_an_experiment_in_the_same_process(index, traced):
    """A turn with no RunTrace goes to the masked client only, even after an experiment's turn."""
    session = tracing_tests.RecordingSession()
    client = experiments.build_client(
        tracing_tests.FAKE_LANGSMITH_KEY, session=session, batch=False
    )
    experiment = experiments.Experiment(client, "x", uuid.uuid4(), {"q1": uuid.uuid4()})
    _turn(index, experiment.trace("q1"))
    experiment_runs = len(session.runs())
    _turn(index)
    app_runs = traced.runs()
    assert app_runs
    searched = tracing_tests._searched(app_runs)
    for canary in obs.CANARY_TEXTS:
        assert canary not in searched, canary
    # The experiment's client got nothing from the app's turn.
    assert len(session.runs()) == experiment_runs
    assert langsmith.run_trees.get_cached_client()._anonymizer is tracing.mask


# --- Errors keep only their class name (code review round 1) -------------------------------------


def test_the_experiments_anonymizer_reduces_only_an_error():
    """mask_error_only() keeps an error's class name and leaves every other payload as it is."""
    traceback = 'RuntimeError("CANARY reply")\nTraceback (most recent call last):\n  File "fake.py"'
    assert tracing.mask_error_only({"error": traceback}) == {"error": "RuntimeError"}
    payload = {"question": "CANARY-Q", "error": "kept beside other keys"}
    assert tracing.mask_error_only(payload) is payload


@pytest.mark.turn_error
def test_a_failed_experiment_turn_sends_no_reply_or_traceback(index, traced):
    """A model error in an experiment turn reaches LangSmith as its class name, no text or path."""
    session = tracing_tests.RecordingSession()
    client = experiments.build_client(
        tracing_tests.FAKE_LANGSMITH_KEY, session=session, batch=False
    )
    experiment = experiments.Experiment(client, "x", uuid.uuid4(), {"q1": uuid.uuid4()})
    result = chat.run_turn(
        obs.CANARY_QUESTION,
        guard.RateLimiter(),
        open_index=lambda: index,
        chat_model=lambda: obs._failing_model(RuntimeError("CANARY-PROVIDER-REPLY")),
        translation_model=lambda: ScriptedTranslator(),
        prices=lambda: {},
        run_trace=experiment.trace("q1"),
    )
    assert result.code == "turn.error"
    errors = [run["error"] for run in session.runs() if run.get("error")]
    assert errors and set(errors) == {"RuntimeError"}
    # `serialized` left out, as in tests/test_tracing.py: the fake model prints its own error
    # there, which the app's ChatOpenAI never does.
    sent = json.dumps(
        [
            {key: value for key, value in run.items() if key != "serialized"}
            for run in session.runs()
        ]
    )
    for leak in ("CANARY-PROVIDER-REPLY", "Traceback", "test_experiments.py"):
        assert leak not in sent, leak
    # Not masked otherwise: the evaluation's question is still readable.
    assert "CANARY-Q" in sent


def test_finish_says_when_the_sends_did_not_end_in_time():
    """Runs or feedback still queued after the flush's timeout are reported, not ignored."""
    client = FakeLangSmith()
    client.tracing_queue = SimpleNamespace(unfinished_tasks=2)
    with pytest.raises(experiments.ExperimentError, match="did not finish"):
        experiments.Experiment(client, "x", uuid.uuid4(), {}).finish()
    assert client.ended == []
