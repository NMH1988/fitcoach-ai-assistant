"""Masked LangSmith tracing (T9.8, D19; Sprint 3 Hard 2): metadata only, never personal data.

Tracing is off unless the app's flag (`config.TRACING_FLAG_NAME`) and the LangSmith key are both
set. `configure_tracing()` sets LangSmith's global state once per run of the page or a script
(`observability.configure_logging()` calls it): off, it turns tracing off for every LangChain and
LangGraph run, so LangSmith's own `LANGSMITH_TRACING` flag in the environment, which would trace
with no masking, is ignored; on, it installs one client whose anonymizer is `mask()`, so every
tracer LangChain makes (the chat turn, the conversation, the weekly review, the evaluation run)
sends through it. No caller passes a tracer of its own.

LangSmith's client runs `mask()` on every run's inputs, outputs, metadata and error before it sends
them. It keeps the shape where something is kept (keys that are plain identifiers, lists, dicts; a
nested record with at least one key and nothing kept, or a list with nothing kept (an empty one
too), becomes one placeholder, so neither its keys nor its length show) and replaces every text,
number, boolean and empty value with `config.TRACE_MASK`, except what is listed below: token counts
and the turn's counters and flow flags, the node and model names LangGraph and LangChain add, the
app's tool names, statuses, kinds and codes (not a guardrail's code, which names a health topic,
nor a review's failed checks), `turn_id` (a run's ID, which ties a trace to its log lines), and
each message's constant LangChain class path, so LangSmith shows a model call's roles. An error
keeps only its exception's class name. A tool call's arguments are masked whole, keys included. The
run's name (a node, a model class), its tags and its timing are not data and are sent as LangSmith
makes them. The question, rewrites, answer, chunk text, profile values, memories, logged values,
review text, tool arguments and results, and the stored user IDs are masked (AC-33).

One exception (T9.35, owner's request, 2026-11-13, to show a reviewer what a trace holds): with
`config.tracing_demo_unmasked()`, that is tracing on, the owner's demo flag on and demo mode on
(synthetic users, never with [auth]), `configure_tracing()` installs a second client, built by
`build_demo_client()`, whose anonymizer lets a payload through as it is (an error keeps only its
class name, as in T9.33's experiments), into a project of its own (`config.LANGSMITH_DEMO_PROJECT`).
The gate is checked on every payload, and any doubt, or turning tracing off, masks it again.
"""

import hashlib
import os
import re
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any

import langsmith
import requests
from langsmith import Client

from src import config

# Numbers kept as they are: token counts (LangChain's usage_metadata and the OpenAI token_usage)
# and the counters of a turn and a review. No profile value or metric is named so.
_TOKEN_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "audio_tokens",
        "accepted_prediction_tokens",
        "rejected_prediction_tokens",
        "cache_read",
        "cache_creation",
        "reasoning",
        "audio",
    }
)
_COUNT_KEYS = frozenset({"rounds", "attempts", "langgraph_step", "ls_max_tokens"})
# Text kept when it looks like an identifier: IDs and node paths LangGraph adds, and the model.
_IDENTIFIER_KEYS = frozenset(
    {
        "turn_id",
        "langgraph_node",
        "langgraph_triggers",
        "langgraph_path",
        "langgraph_checkpoint_ns",
        "checkpoint_ns",
        "ls_provider",
        "ls_model_name",
        "ls_model_type",
        "ls_integration",
        "model_name",
        "finish_reason",
    }
)
# The length bounds in these patterns are format checks (an ID, a node path, a model name, a code
# the app writes), not limits of the app: a longer value is not one of these, so it is masked.
_IDENTIFIER = re.compile(r"[A-Za-z0-9_./:|-]{1,200}")
# Codes the app writes itself (a turn's code, a review's outcome). A review's failed checks
# (`errors`, e.g. diagnosis, calorie_floor) hint at a client's health, so they are masked and stay
# in the local log only (owner's choice, 2026-11-06, compliance run on T9.8).
_CODE_KEYS = frozenset({"code", "outcome"})
_CODE = re.compile(r"[a-z][a-z0-9_]{0,40}(?:\.[a-z0-9_]{1,40}){0,4}")
# A guardrail's code names the health topic of the question (guardrail.pregnancy, ...): masked in
# a trace, kept only in the local log; the turn's kind still says a guardrail answered (owner's
# choice, 2026-11-06, code review round 1).
_MASKED_CODE_PREFIX = "guardrail."
# The only booleans kept: the turn's own flow flags. Any other (e.g. a client's metric flags in a
# review) is masked (owner's choice, 2026-11-06, code review round 1).
_FLAG_KEYS = frozenset({"tools_only", "stopped", "awaiting"})
# Values kept only from a closed list: message and serialisation types, statuses, turn kinds.
_TYPES = frozenset(
    {
        "human",
        "ai",
        "system",
        "tool",
        "constructor",
        "secret",
        "not_implemented",
        "tool_call",
        "invalid_tool_call",
        "tool_call_chunk",
        "ChatGeneration",
        "ChatGenerationChunk",
        "AIMessageChunk",
        "LLMResult",
    }
)
# LangChain's serialised class path of a message ({"lc": 1, "id": ["langchain", "schema",
# "messages", "HumanMessage"], ...}): constant names from the library, from which LangSmith shows a
# model call's messages as a chat with their roles. Only these names are kept under an `id` key; a
# message's or a tool call's own ID (any other value) is masked as before (owner's live check, O13,
# 2026-11-07: the roles showed as "Unknown").
_MESSAGE_CLASS_PATH = frozenset(
    {
        "langchain",
        "schema",
        "messages",
        "SystemMessage",
        "HumanMessage",
        "AIMessage",
        "AIMessageChunk",
        "ToolMessage",
        "ChatMessage",
    }
)
# LangChain's serialisation format version, the only value "lc" holds.
_SERIALISATION_VERSION = 1
_STATUSES = frozenset({"ok", "found", "not_found", "invalid", "profile_needed", "error", "success"})
_KINDS = frozenset({"answer", "no_sources", "rejected", "guardrail", "error", "memory"})
# Masked whole, keys included: what the model passes to a tool.
_ARGUMENT_KEYS = frozenset({"args", "arguments"})
# A dict key kept as it is; any other key (e.g. one the model wrote) is masked.
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
# The class name at the start of an error string: LangChain writes `repr(exc)`, "Name(...)", then
# the traceback.
_ERROR_CLASS = re.compile(r"([A-Za-z_][A-Za-z0-9_.]{0,100})\(")
# Every key whose values may be kept: there, an empty value (None) is kept too.
_METADATA_KEYS = (
    _TOKEN_KEYS
    | _COUNT_KEYS
    | _IDENTIFIER_KEYS
    | _CODE_KEYS
    | _FLAG_KEYS
    | {"type", "status", "kind", "name"}
)

# LangSmith's environment variables that add places to send runs to (write replicas); with one
# set, the runs would not stay in the EU project, so tracing stays off.
_REPLICA_VARIABLES = ("LANGSMITH_RUNS_ENDPOINTS", "LANGCHAIN_RUNS_ENDPOINTS")

_LOCK = threading.Lock()
# A digest of the key (and of the mode) the installed client was built with, so a rerun builds no
# second client.
_installed: dict[str, str | None] = {"key_digest": None}
# T9.35: the demo gate. Opened only by `configure_tracing()`, when tracing, the demo flag and demo
# mode are all on; closed whenever tracing is off. It starts closed.
_gate = {"open": False}


@cache
def tool_names() -> frozenset[str]:
    """Return the names of the app's own tools, the only tool names a trace keeps."""
    # Imported here: these modules import much of the app, which imports this one.
    from src import preferences
    from src.agent import search
    from src.tools import coach_clients, registry

    return frozenset(
        {
            registry.TDEE_TOOL,
            registry.MACRO_TOOL,
            registry.FOOD_TOOL,
            registry.MEAL_PLAN_TOOL,
            search.SEARCH_TOOL,
            preferences.PREFERENCE_TOOL,
            # T9.17: the coach's client tools; their arguments and results are masked as any other.
            coach_clients.LIST_TOOL,
            coach_clients.WEEK_TOOL,
        }
    )


def _kept(key: str | None, value: str | int | float) -> bool:
    """Return True if a text or number under this key is metadata, not data."""
    if isinstance(value, int | float):
        if key == "lc":
            return value == _SERIALISATION_VERSION
        return key in _TOKEN_KEYS or key in _COUNT_KEYS
    if key == "id":
        # Kept only as part of a message's class path, never a message's or a call's own ID.
        return value in _MESSAGE_CLASS_PATH
    if key in _IDENTIFIER_KEYS:
        return _IDENTIFIER.fullmatch(value) is not None
    if key in _CODE_KEYS:
        return _CODE.fullmatch(value) is not None and not value.startswith(_MASKED_CODE_PREFIX)
    allowed = {"type": _TYPES, "status": _STATUSES, "kind": _KINDS, "name": tool_names()}
    return key in allowed and value in allowed[key]


def _mask_value(value: Any, key: str | None) -> Any:
    """Return the value with every text and number that is not metadata replaced (see module)."""
    if value is None:
        # An empty value tells something too (a day of a client's week with no log): kept only
        # under a key whose values are metadata (compliance run on T9.8, owner's choice).
        return value if key in _METADATA_KEYS else config.TRACE_MASK
    if isinstance(value, bool):
        return value if key in _FLAG_KEYS else config.TRACE_MASK
    if key in _ARGUMENT_KEYS:
        return config.TRACE_MASK
    if isinstance(value, str | int | float):
        return value if _kept(key, value) else config.TRACE_MASK
    if isinstance(value, Mapping):
        masked = _mask_record(value)
        # A record with nothing kept becomes one placeholder, so a logged day ({kcal, protein_g})
        # looks like a day with no log (None) in a client's week (code review round 4).
        if masked and all(item == config.TRACE_MASK for item in masked.values()):
            return config.TRACE_MASK
        return masked
    if isinstance(value, list | tuple):
        # A list keeps its key's rule: e.g. LangGraph's node path. A list with nothing kept, an
        # empty one included, becomes one placeholder like a record, so its length shows nothing
        # (how many exercises a client logged, whether a review found topics; owner's choice,
        # 2026-11-06, code review round 5).
        masked_items = [_mask_value(item, key) for item in value]
        if all(item == config.TRACE_MASK for item in masked_items):
            return config.TRACE_MASK
        return masked_items
    # LangSmith passes JSON only; anything else is masked rather than turned into text.
    return config.TRACE_MASK


def _error_class(error: object) -> str:
    """Return an error string's exception class name, or the mask when it starts otherwise."""
    if isinstance(error, str):
        found = _ERROR_CLASS.match(error)
        if found is not None and found.group(1).rsplit(".", 1)[-1][:1].isupper():
            return found.group(1)
    return config.TRACE_MASK


def _mask_record(value: Mapping) -> dict:
    """Return a record with each key kept or masked and each value masked by its key's rule."""
    masked = {}
    for number, (name, item) in enumerate(value.items()):
        if isinstance(name, str) and _KEY.fullmatch(name):
            masked[name] = _mask_value(item, name)
        else:
            masked[config.TRACE_MASKED_KEY.format(number=number)] = _mask_value(item, None)
    return masked


def mask_error_only(data: Any) -> Any:
    """Return a run's error as its class name only; leave every other payload as it is (T9.33)."""
    # The evaluation experiments' anonymizer (src/experiments.py): their runs are not masked, but
    # an error is repr(exc) and a traceback, which may quote a provider's reply and the machine's
    # paths, so it keeps its class name as in mask() (code review round 1 of T9.33).
    if isinstance(data, Mapping) and set(data) == {"error"} and isinstance(data["error"], str):
        return {"error": _error_class(data["error"])}
    return data


def mask(data: Any) -> Any:
    """Return a run's inputs, outputs, metadata or error with its data masked (the anonymizer)."""
    # LangSmith hands an error to the anonymizer as {"error": <repr and traceback>}.
    if isinstance(data, Mapping) and set(data) == {"error"} and isinstance(data["error"], str):
        return {"error": _error_class(data["error"])}
    # The payload itself stays a record, as LangSmith expects; only nested records collapse.
    if isinstance(data, Mapping):
        return _mask_record(data)
    return _mask_value(data, None)


def demo_gate_open() -> bool:
    """Return True only while the demo gate is open and demo mode is still on (fails closed)."""
    try:
        return _gate["open"] and config.demo_mode()
    except Exception:
        # Any doubt (e.g. an unreadable secrets file) means the payload is masked.
        return False


def _masked_unless_demo(data: Any) -> Any:
    """Return a payload as it is while the demo gate is open (T9.35), otherwise masked."""
    # An error still keeps only its class name, as in T9.33's experiments: a traceback may quote a
    # provider's reply and the machine's paths.
    return mask_error_only(data) if demo_gate_open() else mask(data)


def build_client(
    api_key: str, *, session: requests.Session | None = None, batch: bool = True
) -> Client:
    """Return a LangSmith client for the EU endpoint that masks everything it sends."""
    return _client(api_key, mask, session, batch)


def build_demo_client(
    api_key: str, *, session: requests.Session | None = None, batch: bool = True
) -> Client:
    """Return the demo-mode client (T9.35): unmasked while the demo gate is open, else masked."""
    return _client(api_key, _masked_unless_demo, session, batch)


def _client(
    api_key: str,
    anonymizer: Any,
    session: requests.Session | None,
    batch: bool,
) -> Client:
    """Return a client for the EU endpoint whose anonymizer is the one given."""
    # `session` and `batch=False` are for tests: a fake session records each run as it is sent.
    # The anonymizer also covers the error and the metadata, which hide_inputs does not.
    return Client(
        api_url=config.LANGSMITH_ENDPOINT,
        api_key=api_key,
        session=session,
        auto_batch_tracing=batch,
        anonymizer=anonymizer,
        # The machine's platform and library versions are not needed to read a trace.
        omit_traced_runtime_info=True,
        # LangSmith's API only: an OpenTelemetry mode set in the environment would send the runs
        # to another exporter too.
        tracing_mode="langsmith",
    )


def _digest(key: str) -> str:
    """Return a digest of the key, so the installed client is recognised without keeping the key."""
    return hashlib.sha256(key.encode()).hexdigest()


def _extra_destinations() -> bool:
    """Return True if LangSmith's environment names more places to send runs to (replicas)."""
    return any(os.environ.get(name, "").strip() for name in _REPLICA_VARIABLES)


def configure_tracing() -> bool:
    """Install the masked client (in demo mode with its flag, the demo one); else turn it off."""
    wanted = config.tracing_requested() and not _extra_destinations()
    key = config.get_langsmith_api_key() if wanted else None
    with _LOCK:
        if key is None:
            # Also turns off a tracer that LangSmith's own environment flag would start. The
            # global client is never cleared: a Streamlit thread that turned tracing on keeps its
            # own `enabled` until its next run, and with no global client LangSmith would build a
            # default one that masks nothing (code review round 1). It keeps the masked one.
            langsmith.configure(enabled=False)
            _installed["key_digest"] = None
            _gate["open"] = False
            return False
        demo = config.tracing_demo_unmasked()
        _gate["open"] = demo
        digest = _digest(key) + (":demo" if demo else "")
        if _installed["key_digest"] != digest:
            client = build_demo_client(key) if demo else build_client(key)
            langsmith.configure(client=client)
            _installed["key_digest"] = digest
        # Both set on every call: LangSmith keeps them per thread too, and Streamlit runs each
        # session's script in a thread of its own (a project set in one thread only would send the
        # others' runs to LangSmith's "default" project).
        project = config.LANGSMITH_DEMO_PROJECT if demo else config.LANGSMITH_PROJECT
        langsmith.configure(enabled=True, project_name=project)
        return True


def run_metadata(turn_id: str) -> dict[str, str]:
    """Return the metadata every run of a turn carries: its turn_id, as on its log lines."""
    return {"turn_id": turn_id} if turn_id else {}


@dataclass(frozen=True)
class RunTrace:
    """Where an evaluation turn's runs go instead: an experiment's tracer and the root run's ID."""

    # Built only by src/experiments.py for `scripts/run_evaluation.py --langsmith` (T9.33): the
    # tracer sends the turn's runs, unmasked, to the experiment's own project, and LangChain then
    # adds no tracer of its own, so they do not also go to the app's masked project. The app
    # never passes one.
    callbacks: tuple[Any, ...]
    run_id: uuid.UUID
