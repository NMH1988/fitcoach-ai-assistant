"""Masked LangSmith tracing (T9.8): off by default, every payload masked, turn_id on each trace.

The payloads are the ones LangSmith's own client sends, read from a fake `requests` session: the
real client, built by `tracing.build_client()` with the app's anonymizer, sends each run as it
happens (`batch=False`), and no test opens a connection. AC-33 for traces.
"""

import io
import json
import re
import threading
from pathlib import Path

import langsmith
import pytest
import requests
from langchain_core.load import dumpd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import utils as ls_utils

from src import config, llm, observability, tracing
from src.agent import search
from src.agent.memory import Conversation
from src.config import tracing_requested as real_tracing_requested
from src.preferences import PreferenceCheck
from src.tools import coach_clients, registry
from tests import store_world as world
from tests import test_agent_clients as clients_tests
from tests import test_agent_review as review_tests
from tests import test_observability as obs
from tests.fakes import tool_reply

# The canary fixtures of the log tests, so a trace is checked on the same turns as a log line.
canary_setup = obs.canary_setup
index_path = obs.index_path
index = obs.index

FAKE_LANGSMITH_KEY = "lsv2-test-not-a-real-key-CANARYLS"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# A run's own fields that LangSmith fills with random IDs and clock times, whose digits can hold a
# canary's by chance (only at the run's top level; IDs inside the data stay and are searched, with
# UUIDs replaced). The turn_id is pinned to the turn's own ID instead. The project's name is the
# app's (config.LANGSMITH_PROJECT, checked on its own), and holds "coach-a", a world user's ID.
GENERATED_FIELDS = frozenset(
    {
        "id",
        "trace_id",
        "parent_run_id",
        "dotted_order",
        "start_time",
        "end_time",
        "session_name",
    }
)


class RecordingSession(requests.Session):
    """A requests session that records what LangSmith would send and never opens a connection."""

    def __init__(self) -> None:
        """Start with nothing sent."""
        super().__init__()
        self.sent: list[dict] = []

    def request(self, method, url, **kwargs):
        """Record the request and answer it with 200 and an empty JSON body."""
        self.sent.append({"method": method, "url": url, "data": kwargs.get("data")})
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.url = url
        response.request = requests.Request(method, url).prepare()
        return response

    def runs(self) -> list[dict]:
        """Return every run payload sent (a new run or its update), parsed from JSON."""
        wait_for_all_tracers()
        found = []
        for request in self.sent:
            data = request["data"]
            if data:
                found.append(json.loads(data))
        return found


@pytest.fixture
def traced(monkeypatch):
    """Turn masked tracing on with the fake session and the fake key; return the session."""
    session = RecordingSession()
    # Not the machine's secrets.toml, which may hold the owner's real key (code review round 2).
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setattr(config, "tracing_requested", lambda: True)
    monkeypatch.setenv(config.LANGSMITH_API_KEY_NAME, FAKE_LANGSMITH_KEY)
    build = tracing.build_client
    monkeypatch.setattr(
        tracing, "build_client", lambda key: build(key, session=session, batch=False)
    )
    assert tracing.configure_tracing()
    yield session
    monkeypatch.setattr(config, "tracing_requested", lambda: False)
    tracing.configure_tracing()


def _without_generated(run: dict) -> dict:
    """Return a run without its own random IDs and clock times (its events' times included)."""
    kept = {name: value for name, value in run.items() if name not in GENERATED_FIELDS}
    if isinstance(kept.get("events"), list):
        kept["events"] = [
            {name: value for name, value in event.items() if name != "time"}
            if isinstance(event, dict)
            else event
            for event in kept["events"]
        ]
    return kept


def _searched(runs: list[dict]) -> str:
    """Return the payloads as one text to search for canaries, IDs and times left out."""
    # `serialized` describes the model client: the app's ChatOpenAI holds settings only
    # (test_the_model_client_is_described_by_its_settings_only); the tests' fake models print
    # their scripted replies there, which a real client never sends.
    kept = [
        _without_generated({name: value for name, value in run.items() if name != "serialized"})
        for run in runs
    ]
    return UUID.sub("<uuid>", json.dumps(kept))


def _metadata(runs: list[dict]) -> list[dict]:
    """Return each run's metadata as sent."""
    return [run.get("extra", {}).get("metadata", {}) for run in runs]


# --- Off unless the flag and the key are set (AC 1) -----------------------------------------------


@pytest.mark.parametrize(
    ("flag", "key", "on"),
    [(True, FAKE_LANGSMITH_KEY, True), (True, None, False), (False, FAKE_LANGSMITH_KEY, False)],
)
def test_tracing_is_on_only_with_the_flag_and_the_key(monkeypatch, flag, key, on):
    """configure_tracing() turns LangSmith on only when both are set, and off otherwise."""
    # Not the machine's secrets.toml, which may hold the owner's real key (code review round 2).
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setattr(config, "tracing_requested", lambda: flag)
    if key is not None:
        monkeypatch.setenv(config.LANGSMITH_API_KEY_NAME, key)
    build = tracing.build_client
    monkeypatch.setattr(
        tracing, "build_client", lambda key: build(key, session=RecordingSession(), batch=False)
    )
    assert tracing.configure_tracing() is on
    assert ls_utils.tracing_is_enabled() is on


def test_the_installed_client_masks_and_sends_to_the_eu_endpoint(traced):
    """The one global client is the app's: the EU endpoint, the mask as anonymizer, no runtime."""
    client = langsmith.run_trees.get_cached_client()
    assert client.api_url == config.LANGSMITH_ENDPOINT == "https://eu.api.smith.langchain.com"
    assert client._anonymizer is tracing.mask
    assert client.api_key == FAKE_LANGSMITH_KEY
    assert client._omit_traced_runtime_info is True
    # An OpenTelemetry mode set in the environment would add another exporter.
    assert client.tracing_mode == "langsmith"


@pytest.mark.parametrize("name", ["LANGSMITH_RUNS_ENDPOINTS", "LANGCHAIN_RUNS_ENDPOINTS"])
def test_tracing_stays_off_when_the_environment_adds_destinations(monkeypatch, name):
    """Write replicas would send the runs beyond the EU project, so tracing stays off."""
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setattr(config, "tracing_requested", lambda: True)
    monkeypatch.setenv(config.LANGSMITH_API_KEY_NAME, FAKE_LANGSMITH_KEY)
    monkeypatch.setenv(name, '{"https://replica.test": "lsv2-test-not-a-real-key"}')
    assert tracing.configure_tracing() is False
    assert not ls_utils.tracing_is_enabled()


def _start_thread(work) -> tuple[threading.Thread, list[BaseException]]:
    """Start the work in a thread of its own, as Streamlit runs each script run."""
    errors: list[BaseException] = []

    def run():
        """Run the work and keep any error (a failed assert included) for the test's thread."""
        try:
            work()
        except BaseException as exc:  # noqa: BLE001 - raised again in the test's thread
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, errors


def _finish(thread: threading.Thread, errors: list[BaseException]) -> None:
    """Wait for the thread to end and raise its error, if any, in the test's thread."""
    thread.join(120)
    assert not thread.is_alive()
    if errors:
        raise errors[0]


def _in_a_new_thread(work) -> None:
    """Run the work in a thread of its own and wait for it."""
    _finish(*_start_thread(work))


def test_a_run_in_another_thread_goes_to_the_app_s_project(index, traced):
    """A later script run, in a new thread, traces into config.LANGSMITH_PROJECT (round 1)."""

    def turn():
        """Set tracing up as a rerun does, then run a turn."""
        observability.configure_logging(stream=io.StringIO())
        obs.CANARY_ENDINGS["answer"](index)

    _in_a_new_thread(turn)
    runs = traced.runs()
    assert runs
    assert {run.get("session_name") for run in runs} == {config.LANGSMITH_PROJECT}


def test_turning_tracing_off_never_leaves_an_unmasked_client(
    index, traced, monkeypatch, no_network
):
    """A thread still on when another turns tracing off sends through the masked client only."""
    # no_network: had the bug come back, LangSmith's default client would try the real API.
    ready, turned_off = threading.Event(), threading.Event()

    def turn():
        """Turn tracing on in this thread, wait until it is turned off elsewhere, run a turn."""
        tracing.configure_tracing()
        ready.set()
        assert turned_off.wait(60)
        obs.CANARY_ENDINGS["answer"](index)

    worker, errors = _start_thread(turn)
    assert ready.wait(60)
    monkeypatch.setattr(config, "tracing_requested", lambda: False)
    assert tracing.configure_tracing() is False
    turned_off.set()
    _finish(worker, errors)
    # The worker's own `enabled` is still on, so it traced; only through the masked client.
    assert langsmith.run_trees.get_cached_client()._anonymizer is tracing.mask
    runs = traced.runs()
    # After runs(), which flushes the client: a default client would have sent by now.
    assert no_network == []
    assert runs
    searched = _searched(runs)
    for canary in obs.CANARY_TEXTS:
        assert canary not in searched, canary


def test_a_rerun_keeps_the_client_already_installed(traced):
    """Streamlit calls configure_logging() on every run; the client is built once per key."""
    first = langsmith.run_trees.get_cached_client()
    assert tracing.configure_tracing()
    assert langsmith.run_trees.get_cached_client() is first


@pytest.mark.parametrize("value", ["true", "TRUE", " 1 ", "yes", "on"])
def test_the_flag_reads_on_values_from_the_environment(monkeypatch, value):
    """The app's own flag is on for the usual spellings of yes."""
    # Not the machine's secrets.toml, which may set the flag (code review round 3).
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setenv(config.TRACING_FLAG_NAME, value)
    assert real_tracing_requested()


@pytest.mark.parametrize("value", ["", "false", "0", "no", "maybe"])
def test_the_flag_is_off_for_anything_else(monkeypatch, value):
    """Anything that is not a clear yes leaves tracing off."""
    monkeypatch.setattr(config.st, "secrets", {})
    monkeypatch.setenv(config.TRACING_FLAG_NAME, value)
    assert not real_tracing_requested()


def test_the_flag_and_the_key_come_from_secrets_first(secrets_from_file, monkeypatch):
    """secrets.toml wins over the environment, as for the OpenRouter key."""
    monkeypatch.setenv(config.LANGSMITH_API_KEY_NAME, "lsv2-test-env-key")
    secrets_from_file(
        f'{config.TRACING_FLAG_NAME} = true\n{config.LANGSMITH_API_KEY_NAME} = " lsv2-test-file "\n'
    )
    assert real_tracing_requested()
    assert config.get_langsmith_api_key() == "lsv2-test-file"


def test_a_missing_key_is_none_not_an_error(secrets_from_file, monkeypatch):
    """With no key anywhere tracing is simply off; nothing is raised."""
    monkeypatch.delenv(config.LANGSMITH_API_KEY_NAME, raising=False)
    secrets_from_file("OTHER = 1\n")
    assert config.get_langsmith_api_key() is None


@pytest.fixture
def langsmith_env_flag(monkeypatch):
    """Set LangSmith's own tracing flag and key in the environment, as a user might."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv(config.LANGSMITH_API_KEY_NAME, FAKE_LANGSMITH_KEY)
    # LangSmith caches what it reads from the environment.
    ls_utils.get_env_var.cache_clear()
    yield
    monkeypatch.delenv("LANGSMITH_TRACING")
    ls_utils.get_env_var.cache_clear()


@pytest.fixture
def no_network(monkeypatch):
    """Record every request any requests session makes, and refuse it."""
    sent = []

    def refuse(self, method, url, **kwargs):
        """Record the URL and fail as an offline machine does."""
        sent.append(url)
        raise requests.ConnectionError("no network in tests")

    monkeypatch.setattr(requests.Session, "request", refuse)
    return sent


def test_langsmiths_own_environment_flag_traces_nothing(index, langsmith_env_flag, no_network):
    """LANGSMITH_TRACING=true and a key, but not the app's flag: no run leaves the machine."""
    observability.configure_logging(stream=io.StringIO())
    obs.CANARY_ENDINGS["answer"](index)
    wait_for_all_tracers()
    assert not ls_utils.tracing_is_enabled()
    assert no_network == []


def test_without_the_app_s_setup_the_environment_flag_would_trace(langsmith_env_flag):
    """The check above has something to catch: left to the environment, LangSmith would trace."""
    langsmith.configure(enabled=None)
    assert ls_utils.tracing_is_enabled() is True


# --- The mask (AC 2) ---------------------------------------------------------------------------


def _message(kind: str, text: str, **extra) -> dict:
    """Return a message as LangChain serialises it into a run's inputs or outputs."""
    return {
        "lc": 1,
        "type": "constructor",
        "id": ["langchain", "schema", "messages", "Message"],
        "kwargs": {"content": text, "type": kind, **extra},
    }


def test_the_mask_replaces_text_and_numbers_and_keeps_the_shape():
    """Questions, answers, profile values and metrics become placeholders."""
    masked = tracing.mask(
        {
            "text": "CANARY-Q 87.3 kg",
            "history": [_message("human", "CANARY-H"), _message("ai", "CANARY-A")],
            "metrics": {"weight_kg": 87.3, "kcal": 2345, "days": 3},
            "tools_only": True,
            "answer": None,
        }
    )
    assert masked["text"] == config.TRACE_MASK
    assert masked["history"][0]["kwargs"] == {"content": config.TRACE_MASK, "type": "human"}
    # A record with nothing kept is one placeholder (code review round 4).
    assert masked["metrics"] == config.TRACE_MASK
    assert (masked["tools_only"], masked["answer"]) == (True, config.TRACE_MASK)
    assert "CANARY" not in json.dumps(masked) and "87.3" not in json.dumps(masked)


def test_the_mask_keeps_token_counts_tool_names_statuses_and_codes():
    """What reading a trace needs stays: tokens, counters, the app's tool names, fixed codes."""
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    masked = tracing.mask(
        {
            "messages": [
                _message(
                    "ai",
                    "CANARY",
                    tool_calls=[
                        {
                            "name": registry.TDEE_TOOL,
                            "args": {"weight_kg": 87.3},
                            "type": "tool_call",
                        },
                        {"name": "CANARY-TOOL", "args": {}, "type": "tool_call"},
                    ],
                    usage_metadata={**usage, "output_token_details": {"reasoning": 3}},
                )
            ],
            "rounds": 2,
            "attempts": 1,
            "status": "ok",
            "kind": "answer",
            "code": "answer.no_sources",
            "errors": ["calorie_floor", "CANARY text"],
        }
    )
    kwargs = masked["messages"][0]["kwargs"]
    assert [call["name"] for call in kwargs["tool_calls"]] == [
        registry.TDEE_TOOL,
        config.TRACE_MASK,
    ]
    assert [call["args"] for call in kwargs["tool_calls"]] == [config.TRACE_MASK] * 2
    assert kwargs["usage_metadata"] == {**usage, "output_token_details": {"reasoning": 3}}
    assert (masked["rounds"], masked["attempts"]) == (2, 1)
    assert (masked["status"], masked["kind"], masked["code"]) == (
        "ok",
        "answer",
        "answer.no_sources",
    )
    # A review's failed checks hint at a client's health: masked (owner's choice).
    assert masked["errors"] == config.TRACE_MASK


def test_a_guardrail_code_is_masked_and_its_kind_kept():
    """The health topic a guardrail names stays local; the trace says only that one answered."""
    masked = tracing.mask({"kind": "guardrail", "code": "guardrail.pregnancy"})
    assert masked == {"kind": "guardrail", "code": config.TRACE_MASK}


def test_a_day_with_no_log_looks_like_a_logged_one():
    """A logged day (a record) and a day with no log (None) both become one placeholder."""
    # The shape weekly_review.aggregates() gives (compliance run 1, code review round 4).
    logged = {"kcal": 1534.0, "protein_g": 120.0}
    masked = tracing.mask(
        {"nutrition": {"days": [logged, None, None, logged], "target": None}, "finish_reason": None}
    )
    # The whole week becomes one placeholder: a list with nothing kept collapses too (round 5).
    assert masked == {"nutrition": config.TRACE_MASK, "finish_reason": None}


def test_a_record_that_keeps_something_keeps_its_keys():
    """Only a record with nothing kept collapses; a message keeps its type and its shape."""
    masked = tracing.mask({"kwargs": {"content": "CANARY", "type": "human"}, "empty": {}})
    assert masked == {"kwargs": {"content": config.TRACE_MASK, "type": "human"}, "empty": {}}


@pytest.mark.parametrize(
    ("message", "role"),
    [
        (SystemMessage("CANARY system"), "SystemMessage"),
        (HumanMessage("CANARY-Q 87.3 kg", id="CANARY-msg-1"), "HumanMessage"),
        (AIMessage("CANARY-A", id="lc_run--CANARY"), "AIMessage"),
        (ToolMessage("CANARY result", tool_call_id="call_CANARY"), "ToolMessage"),
    ],
)
def test_a_message_keeps_its_class_path_so_its_role_shows(message, role):
    """lc and the class path stay, so LangSmith shows the role; the text and the IDs go (O13)."""
    masked = tracing.mask({"messages": [[dumpd(message)]]})
    [[sent]] = masked["messages"]
    assert sent["lc"] == 1
    assert sent["id"] == ["langchain", "schema", "messages", role]
    assert sent["kwargs"]["content"] == config.TRACE_MASK
    assert "CANARY" not in json.dumps(masked) and "87.3" not in json.dumps(masked)


@pytest.mark.parametrize("value", ["lc_run--1234", "call_abc", "CANARY", "HumanMessage x"])
def test_an_id_outside_the_class_path_is_masked(value):
    """A message's or a tool call's own ID is masked; only the class path's names are kept."""
    assert tracing.mask({"id": value, "lc": 2}) == {
        "id": config.TRACE_MASK,
        "lc": config.TRACE_MASK,
    }


def test_a_traced_model_call_carries_its_messages_class_paths(index, traced):
    """A real turn's model call keeps its messages' class paths, in and out (owner's O13)."""
    obs.CANARY_ENDINGS["answer"](index)
    text = json.dumps(traced.runs())
    assert '"id": ["langchain", "schema", "messages", "SystemMessage"]' in text
    assert '"id": ["langchain", "schema", "messages", "HumanMessage"]' in text
    # The output: the reply's class path and the result's type (code review round 7).
    assert re.search(r'"id": \["langchain", "schema", "messages", "AIMessage(Chunk)?"\]', text)
    assert '"type": "LLMResult"' in text


@pytest.mark.parametrize("items", [[], ["squat"], ["squat", "bench", "row", "deadlift"], [None]])
def test_a_list_with_nothing_kept_hides_its_length(items):
    """No exercise, one or four: the trace shows one placeholder (code review round 5)."""
    assert tracing.mask({"exercises": items}) == {"exercises": config.TRACE_MASK}


def test_a_list_that_keeps_something_keeps_its_items():
    """LangGraph's node path and a reply's tool calls keep their items."""
    masked = tracing.mask(
        {
            "langgraph_path": ["__pregel_pull", "agent"],
            "tool_calls": [{"name": registry.FOOD_TOOL, "args": {}, "type": "tool_call"}],
        }
    )
    assert masked["langgraph_path"] == ["__pregel_pull", "agent"]
    assert masked["tool_calls"][0]["name"] == registry.FOOD_TOOL


def test_only_the_turn_s_flow_flags_keep_their_booleans():
    """tools_only, stopped and awaiting stay; any other boolean (a client's flag) is masked."""
    masked = tracing.mask(
        {"tools_only": True, "stopped": False, "awaiting": True, "fiber_complete": False}
    )
    assert masked == {
        "tools_only": True,
        "stopped": False,
        "awaiting": True,
        "fiber_complete": config.TRACE_MASK,
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("name", "Oats, rolled"),
        ("name", "oats"),
        ("status", "CANARY"),
        ("kind", "87.3"),
        ("type", "CANARY"),
        ("code", "CANARY Q"),
        ("weight_kg", 87.3),
        ("age", 37),
        ("tokens_note", 15),
        ("turn_id", "CANARY Q with spaces"),
    ],
)
def test_a_value_outside_its_key_s_rule_is_masked(key, value):
    """A food name, a free text under a kept key, or a number not a token count is masked."""
    assert tracing.mask({key: value}) == {key: config.TRACE_MASK}


def test_a_key_that_is_not_an_identifier_is_masked():
    """A key the model or a user could write (spaces, digits first) does not reach the trace."""
    masked = tracing.mask({"CANARY key 87.3": "x", "1st": "y", "ok_key": "z"})
    assert set(masked) == {"[masked key 0]", "[masked key 1]", "ok_key"}
    assert "CANARY" not in json.dumps(masked)


def test_metadata_keeps_the_turn_and_node_and_masks_the_users_ids():
    """turn_id and LangGraph's node fields stay; a review's coach, client and thread go."""
    masked = tracing.mask(
        {
            "turn_id": "0b5c1a2e-0d86-468f-8d14-20c58e2b20fa",
            "langgraph_node": "agent",
            "langgraph_step": 3,
            "langgraph_path": ["__pregel_pull", "agent"],
            "ls_model_name": "openai/gpt-5-mini",
            "coach_id": "coach-a",
            "client_id": "gym-shared",
            "thread_id": "f3b1",
        }
    )
    assert masked["turn_id"] == "0b5c1a2e-0d86-468f-8d14-20c58e2b20fa"
    assert (masked["langgraph_node"], masked["langgraph_step"]) == ("agent", 3)
    assert masked["langgraph_path"] == ["__pregel_pull", "agent"]
    assert masked["ls_model_name"] == "openai/gpt-5-mini"
    assert [masked[k] for k in ("coach_id", "client_id", "thread_id")] == [config.TRACE_MASK] * 3


@pytest.mark.parametrize(
    ("error", "kept"),
    [
        (
            "RuntimeError('CANARY 87.3')\n\nTraceback (most recent call last): CANARY",
            "RuntimeError",
        ),
        ("openai.InternalServerError('CANARY')", "openai.InternalServerError"),
        ("CANARY: something", config.TRACE_MASK),
        ("canary(87.3)", config.TRACE_MASK),
        (12, config.TRACE_MASK),
    ],
)
def test_an_error_keeps_only_its_class_name(error, kept):
    """LangSmith passes an error as {"error": repr and traceback}; only the class is sent."""
    assert tracing.mask({"error": error}) == {"error": kept}


def test_the_model_client_is_described_by_its_settings_only():
    """The `serialized` form of the app's chat client holds its settings, never the key."""
    model = llm.build_chat_model(api_key=obs.CANARY_KEY)
    text = json.dumps(dumpd(model))
    assert obs.CANARY_KEY not in text
    assert set(dumpd(model)["kwargs"]) <= {
        "model_name",
        "openai_api_key",
        "openai_api_base",
        "request_timeout",
        "stream_usage",
        "max_retries",
        "max_tokens",
        "reasoning_effort",
        "use_responses_api",
    }


# --- Every payload a turn sends is masked (AC 2, AC-33) ------------------------------------------


@pytest.mark.turn_error
@pytest.mark.parametrize("ending", obs.CANARY_ENDINGS)
def test_no_payload_holds_the_question_the_answer_the_profile_or_the_key(index, traced, ending):
    """Every ending of a turn is traced with canary values; none reaches LangSmith."""
    result = obs.CANARY_ENDINGS[ending](index)
    runs = traced.runs()
    assert runs, ending
    # Every run has a turn_id; a setup turn before (a waiting proposal) has an ID of its own.
    turn_ids = {meta.get("turn_id") for meta in _metadata(runs)}
    assert result.turn_id in turn_ids and None not in turn_ids
    searched = _searched(runs)
    # '"guardrail.': a guardrail's code (its health topic) is masked too (owner's choice).
    for canary in (*obs.CANARY_TEXTS, FAKE_LANGSMITH_KEY, '"guardrail.'):
        assert canary not in searched, (ending, canary)


def test_a_turn_with_history_masks_the_earlier_answer(index, traced):
    """The conversation's kept question and answer (T9.4) are masked in the next turn's trace."""
    conversation = Conversation()
    obs._canary_turn(
        obs.CANARY_QUESTION,
        index,
        obs._answer_model(),
        obs._rewrites_translator(),
        conversation=conversation,
    )
    assert len(conversation.messages()) == 2
    traced.sent.clear()
    obs._canary_turn(
        "And per day?",
        index,
        obs._answer_model(),
        obs._rewrites_translator(),
        conversation=conversation,
    )
    searched = _searched(traced.runs())
    for canary in obs.CANARY_TEXTS:
        assert canary not in searched, canary


def test_a_trace_keeps_the_nodes_tools_statuses_tokens_and_timing(index, traced):
    """The masked trace still shows the graph: node names, tool names, statuses, tokens, times."""
    obs.CANARY_ENDINGS["answer with tools"](index)
    runs = traced.runs()
    names = {run.get("name") for run in runs}
    assert {"guard", "prepare", "agent", "tools", "end_round", "finish"} <= names
    text = json.dumps(runs)
    assert f'"name": "{registry.TDEE_TOOL}"' in text
    assert f'"name": "{registry.FOOD_TOOL}"' in text
    assert '"status": "ok"' in text
    # The query translation's usage (tests/fakes.py: the answer fakes report none).
    assert '"input_tokens": 5' in text and '"total_tokens": 10' in text
    finished = [run for run in runs if run.get("end_time")]
    assert finished and all(run["start_time"] <= run["end_time"] for run in finished)


def test_the_leak_check_catches_an_unmasked_payload(index, traced, monkeypatch):
    """With the mask switched off, the same check finds the question in the payload."""
    monkeypatch.setattr(tracing, "_mask_value", lambda value, key: value)
    obs.CANARY_ENDINGS["answer"](index)
    assert "CANARY-Q" in _searched(traced.runs())


# --- The coach's memories, a preference and the weekly review (AC 2) ------------------------------


def test_a_coach_s_memories_and_proposal_are_masked(index, traced):
    """The <memories> block, the proposed text and the coach's answer on the card are masked."""
    conversation = Conversation()
    obs._canary_turn(
        "CANARY-Q keep answers short",
        index,
        obs._proposing_model("CANARY-PREF keep answers short"),
        coach=obs.CANARY_COACH,
        conversation=conversation,
    )
    conversation.decide("save", "CANARY-PREF edited", lambda text: PreferenceCheck(True, text))
    searched = _searched(traced.runs())
    # "keep answers short" is also the tool description's own example, so the canaries are these.
    for canary in ("CANARY", "answer in bullet points"):
        assert canary not in searched, canary


REVIEW_CANARIES = (
    "CANARY",
    world.COACH_A,
    world.SHARED,
    str(world.WEIGHT),
    str(world.HEIGHT),
    "2345",
    "571.5",
    "Oats",
    review_tests.PROMPT,
)


def test_a_weekly_review_and_its_decision_are_masked_and_carry_their_turn_id(store_conn, traced):
    """A client's metrics, the draft and the users' IDs stay out; each run has its log's turn_id."""
    world.build(store_conn)
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    draft = review_tests._draft(
        observations=[{"text": "CANARY-REVIEW The client logged 1 of 7 days.", "evidence": []}]
    )
    context = review_tests._context(review_tests._model(draft))
    started = review_tests._start(context)
    assert started.outcome == "pending"
    start_runs = traced.runs()
    traced.sent.clear()
    [row] = review_tests.reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)
    decided = review_tests.review.decide_review(
        context, world.COACH_A, row["id"], row["thread_id"], "approve"
    )
    assert decided.outcome == "approved"
    decide_runs = traced.runs()
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    ids = [line["turn_id"] for line in lines if line["event"] == "weekly_review"]
    assert len(ids) == 2 and ids[0] != ids[1]
    assert {meta.get("turn_id") for meta in _metadata(start_runs)} == {ids[0]}
    assert {meta.get("turn_id") for meta in _metadata(decide_runs)} == {ids[1]}
    searched = _searched(start_runs + decide_runs)
    for canary in REVIEW_CANARIES:
        assert canary not in searched, canary
    # The world's week (one logged day and six without, one exercise) is traced as one
    # placeholder: neither its days nor how many exercises show (code review rounds 4 and 5).
    weeks = list(_values_under("metrics", start_runs))
    assert weeks and all(week == config.TRACE_MASK for week in weeks)


def _values_under(key: str, value):
    """Yield every value found under the key anywhere in the value."""
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key:
                yield item
            yield from _values_under(key, item)
    elif isinstance(value, list):
        for item in value:
            yield from _values_under(key, item)


# --- The key and the turn_id (AC 1, AC 3) -------------------------------------------------------


def test_the_key_is_never_logged_or_sent_in_a_payload(index, traced):
    """The LangSmith key goes only in the request header, never in a log line or a run."""
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    obs.CANARY_ENDINGS["answer"](index)
    assert FAKE_LANGSMITH_KEY not in stream.getvalue()
    assert FAKE_LANGSMITH_KEY not in json.dumps(traced.runs())


def test_each_run_of_a_turn_carries_the_turn_id_of_its_log_line(index, traced):
    """The turn's log line and every run of its trace share one turn_id (T8.2)."""
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    result = obs.CANARY_ENDINGS["answer with tools"](index)
    [line] = [json.loads(x) for x in stream.getvalue().splitlines() if '"event": "turn"' in x]
    runs = traced.runs()
    assert line["turn_id"] == result.turn_id
    assert len(runs) > 6
    assert all(meta.get("turn_id") == result.turn_id for meta in _metadata(runs))


def test_the_evaluation_judge_s_calls_are_masked_and_carry_the_scored_turn_s_id(traced):
    """A scored evaluation's judge calls carry the answer's turn_id and hide its texts (round 8)."""
    from src import eval_scoring, usage  # Needs the eval extra, as tests/test_eval_scoring.py.
    from tests.fakes import FakeJudgeChat

    turn_id = "0f1e2d3c-4b5a-4968-8776-655443322110"
    judge = eval_scoring.Judge(FakeJudgeChat(reason="CANARY-REASON"), usage.UsageRecorder())
    scores = eval_scoring.score_answer(
        "CANARY-QUESTION protein?",
        "CANARY-ANSWER 0.4 g/kg.",
        ["CANARY-CHUNK text."],
        judge.for_turn(turn_id),
    )
    assert all(score.score is not None for score in scores.values())
    runs = traced.runs()
    assert runs
    assert all(meta.get("turn_id") == turn_id for meta in _metadata(runs))
    searched = _searched(runs)
    for canary in ("CANARY", "claim one", "statement one", "truth one"):
        assert canary not in searched


def test_a_search_tool_name_is_kept():
    """The knowledge base search keeps its name in a trace, like the other tools."""
    assert tracing.mask({"name": search.SEARCH_TOOL}) == {"name": search.SEARCH_TOOL}


# --- The coach's client tools (T9.17) -------------------------------------------------------------

# Never in either tool's result by design (a client is a reference), so they must not reach a
# trace either: the clients' display names and the users' IDs.
CLIENT_CANARIES = ("CANARYNAME", world.COACH_A, *world.GYMERS)
# What the two results do hold for client-1 (the made-up world's week), as a trace would carry
# it: in the tool message's JSON text (quotes escaped) or as the result's own fields. The week
# gives the logged food's energy, the latest weight and the target; the list gives the logged
# days, the workouts and a follow-up reason; both give the reference and the week's Monday.
_FIELD = r'{}\\*"\s*:\s*{}\b'
CLIENT_VALUES = tuple(
    re.compile(pattern)
    for pattern in (
        r"571\.5",
        re.escape(str(world.WEIGHT)),
        r"2345",
        _FIELD.format("logged_days", 1),
        _FIELD.format("workouts", 1),
        r"few_logged_days",
        # As a JSON value: the tool's fixed description, kept in the trace, has 'client-1' as an
        # example in single quotes.
        r'\\*"client-1\\*"',
        re.escape(str(world.DAY)),
    )
)
relationships = clients_tests.relationships


@pytest.mark.parametrize("name", [coach_clients.LIST_TOOL, coach_clients.WEEK_TOOL])
def test_a_client_tool_name_is_kept(name):
    """Both client tools keep their names in a trace, like the other tools."""
    assert tracing.mask({"name": name}) == {"name": name}


@pytest.mark.parametrize("masked", [True, False])
def test_a_coach_s_client_tools_are_masked_in_a_trace(
    relationships, index_path, traced, monkeypatch, masked
):
    """Both tools' results, a week now and a past one, leave no stored value or name in a trace."""
    if not masked:
        # The check itself: with the mask switched off, the same search finds the values.
        monkeypatch.setattr(tracing, "_mask_value", lambda value, key: value)
    clients = clients_tests._clients()
    result, _ = clients_tests._turn(
        index_path,
        clients,
        tool_reply((coach_clients.LIST_TOOL, {})),
        tool_reply((coach_clients.WEEK_TOOL, {"client": "client-1"})),
        tool_reply((coach_clients.WEEK_TOOL, {"client": "client-1", "week_of": "2026-10-19"})),
        AIMessage("client-1 logged one day."),
        question="How did my clients do?",
    )
    assert result.kind == "answer"
    assert [(run.name, run.status) for run in result.tool_runs] == [
        (coach_clients.LIST_TOOL, "ok"),
        (coach_clients.WEEK_TOOL, "ok"),
        (coach_clients.WEEK_TOOL, "ok"),
    ]
    # The tools did read the stored values: the unmasked result holds the logged food's energy.
    assert "571.5" in result.tool_runs[1].result.model_dump_json()
    runs = traced.runs()
    text = json.dumps(runs)
    assert f'"name": "{coach_clients.LIST_TOOL}"' in text
    assert f'"name": "{coach_clients.WEEK_TOOL}"' in text
    searched = _searched(runs)
    found = [pattern.pattern for pattern in CLIENT_VALUES if pattern.search(searched)]
    if not masked:
        # The check itself: with the mask off, the search finds every value both results hold.
        assert found == [pattern.pattern for pattern in CLIENT_VALUES]
        return
    assert found == []
    for canary in CLIENT_CANARIES:
        assert canary not in searched, canary


# --- No other way to trace, and nothing that writes past the mask (code review round 1) ---------

ROOT = Path(__file__).resolve().parents[1]
TRACING_MODULE = ROOT / "src" / "tracing.py"
SCANNED = [*(ROOT / "src").rglob("*.py"), *(ROOT / "views").rglob("*.py")]
SCANNED += [*(ROOT / "scripts").glob("*.py"), ROOT / "app.py"]
# Only src/tracing.py imports langsmith (configure, traceable, trace, tracing_context all come from
# it). LangChain's own ways to trace are named too, and a retry, whose events carry an error's
# message and a reply past the anonymizer (LangGraph's RetryPolicy also logs the error outside the
# app's formatter).
TRACE_BYPASS = re.compile(
    r"^\s*(?:import|from)\s+langsmith\b"
    r"|\b(?:with_retry|RetryPolicy|retry_policy|tracing_v2_enabled|LangChainTracer)\b",
    re.MULTILINE,
)


def bypasses(source: str) -> list[str]:
    """Return what in the source would trace another way or send a retry's text."""
    return [found.strip() for found in TRACE_BYPASS.findall(source)]


def test_only_the_tracing_module_uses_langsmith_and_nothing_retries():
    """No module but src/tracing.py imports langsmith or traces otherwise; nothing retries."""
    found = {
        str(path.relative_to(ROOT)): bypasses(path.read_text(encoding="utf-8"))
        for path in SCANNED
        if path != TRACING_MODULE and bypasses(path.read_text(encoding="utf-8"))
    }
    assert found == {}


@pytest.mark.parametrize(
    "source",
    [
        "model.with_retry(stop_after_attempt=2)",
        "builder.add_node('x', f, retry_policy=RetryPolicy())",
        "from langsmith import traceable",
        "import langsmith as ls",
        "    from langsmith.run_helpers import tracing_context",
        "from langchain_core.tracers.context import tracing_v2_enabled",
        "callbacks=[LangChainTracer()]",
    ],
)
def test_the_bypass_scan_catches(source):
    """The scan finds each pattern it is meant to refuse."""
    assert bypasses(source)


@pytest.mark.parametrize(
    "source",
    ["# the word traceable in a comment", "text = 'langsmith is a service'", "x.retry_count = 2"],
)
def test_the_bypass_scan_passes_plain_text(source):
    """Plain words pass; a comment or string naming a scanned name (e.g. with_retry) fails."""
    assert bypasses(source) == []
