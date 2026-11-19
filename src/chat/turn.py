"""One chat turn: its dependencies, run_turn() and the turn's log lines."""

import logging
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cache, partial
from typing import TYPE_CHECKING, Any

from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from src import config, guard, i18n, llm, preferences, profile, tracing, usage
from src.chat.results import PromptMissingError, Step, TurnResult
from src.rag import hybrid
from src.rag.hybrid import KeywordIndex
from src.rag.query_translation import Domain
from src.rag.retriever import RetrievedChunk
from src.rag.sources import Source
from src.rag.store import IndexNotReadyError
from src.tools import registry
from src.tools.coach_clients import CoachClients
from src.tools.food import FoodLookupResult
from src.tools.food_api import FOOD_API_FAILURES, FoodSearch
from src.tools.registry import ToolRun
from src.usage import ModelPrice, UsageRecorder

if TYPE_CHECKING:
    # The memory builds on this package, so it is imported here for the annotation only.
    from src.agent.memory import Conversation

logger = logging.getLogger(__name__)


def _cost_text(
    result: TurnResult, prices: Callable[[], Mapping[str, ModelPrice] | None] | None
) -> str | None:
    """Return the turn's cost in dollars as text, or None when a price is unknown."""
    known = prices() if prices is not None and result.usage else None
    cost = usage.price_turn(result.usage, known).cost
    return None if cost is None else format(cost, "f")


@dataclass
class _TurnTrace:
    """What a turn did, collected as it happens, for its log lines (T8.2)."""

    # The chunks the searches gave the model, in [S#] order, the tool runs and the searches run. An
    # error result has no tool runs or searches, so the log cannot read them there.
    chunks: list[RetrievedChunk] = field(default_factory=list)
    tool_runs: list[ToolRun] = field(default_factory=list)
    searches: int = 0


def _log_turn(
    result: TurnResult,
    language: i18n.Language,
    trace: _TurnTrace,
    seconds: float,
    prices: Callable[[], Mapping[str, ModelPrice] | None] | None,
) -> None:
    """Write the turn's INFO record, a warning per failed tool call and a food_api line (T9.9)."""
    # Only ids, counts, codes and statuses: no question, rewrite, answer, chunk text, profile value
    # or tool argument, and no tool name the model made up (a run's name is None then).
    for run in trace.tool_runs:
        if run.status in ("error", "invalid"):
            logger.warning(
                "tool_failed",
                extra={"turn_id": result.turn_id, "tool": run.name, "status": run.status},
            )
        api_code = run.result.api_code if isinstance(run.result, FoodLookupResult) else None
        if api_code is not None:
            # The FoodData Central API's outcome (T9.9): its code only, never the food's name.
            logger.log(
                logging.WARNING if api_code in FOOD_API_FAILURES else logging.INFO,
                "food_api",
                extra={"turn_id": result.turn_id, "code": api_code, "status": run.status},
            )
    source_ids = dict.fromkeys(
        str(chunk.metadata["source_id"])
        for chunk in trace.chunks
        if chunk.metadata.get("source_id")
    )
    logger.info(
        "turn",
        extra={
            "turn_id": result.turn_id,
            "kind": result.kind,
            "code": result.code,
            "language": language,
            "chunks": len(trace.chunks),
            "source_ids": list(source_ids),
            "tools": [run.name for run in trace.tool_runs],
            "tool_statuses": [run.status for run in trace.tool_runs],
            "tokens": sum(call.tokens for call in result.usage),
            "cost_usd": _cost_text(result, prices),
            "duration_ms": round(seconds * 1000),
            "searches": trace.searches,
            # Which prompts the turn ran with (T10.4): versions, never their text.
            tracing.PROMPT_ANSWER_KEY: result.prompts.get(tracing.PROMPT_ANSWER_KEY),
            tracing.PROMPT_QUERY_KEY: result.prompts.get(tracing.PROMPT_QUERY_KEY),
        },
    )


@dataclass(frozen=True)
class TurnDeps:
    """What a chat turn is built with: its models, the index, the sources, prices and services."""

    # Factories: each is called at most once a turn, and only after the guard passes (T9.2).
    chat_model: Callable[[], BaseChatModel]
    translation_model: Callable[[], BaseChatModel]
    open_index: Callable[[], Chroma]
    # keyword_index(index) gives the BM25 index of the opened index; the app passes a cached one.
    keyword_index: Callable[[Chroma], KeywordIndex] = hybrid.build_keyword_index
    # The knowledge base's sources by ID, for the answer's source cards; None counts as empty.
    manifest: Mapping[str, Source] | None = None
    # prices() gives the model prices already known, never reading them (T8.2): only the turn's log
    # line uses them, and the cost is null when there are none.
    prices: Callable[[], Mapping[str, ModelPrice] | None] | None = None
    # The USDA FoodData Central search (T9.9), asked by the food tool for a food the table does not
    # have; None (no key, the evaluation run) keeps the table alone.
    food_api: FoodSearch | None = None
    # A coach's chat (T9.7): their client names and saved preferences, read from the store before
    # the turn; it offers remember_preference and <memories>. None for a guest.
    coach: preferences.CoachMemory | None = None
    # A coach's client tools (T9.17): the coach, the store and the chat's references, which give
    # list_my_clients and get_client_week. None for a guest.
    clients: CoachClients | None = None
    # An evaluation experiment's tracer and root run ID (T9.33, src/experiments.py): only
    # `scripts/run_evaluation.py --langsmith` passes one, never the app.
    run_trace: tracing.RunTrace | None = None


@dataclass(frozen=True)
class TurnCallbacks:
    """What the caller is told while a turn runs: each step, the answer so far, the chunks found."""

    # on_step(step) is called as each step starts; on_text(text) as the answer streams in.
    on_step: Callable[[Step], None] | None = None
    on_text: Callable[[str], None] | None = None
    # on_chunks(chunks) gets each search's newly labelled chunks, in [S#] order, so all its calls
    # together give the turn's chunks in label order; only the evaluation run uses it (T6.1, T9.3).
    on_chunks: Callable[[Sequence[RetrievedChunk]], None] | None = None


def run_turn(
    text: str,
    limiter: guard.RateLimiter,
    *,
    deps: TurnDeps,
    language: i18n.Language = "en",
    user: profile.UserProfile | None = None,
    conversation: Conversation | None = None,
    callbacks: TurnCallbacks | None = None,
) -> TurnResult:
    """Run one chat turn: guard, agent, tools; never raise for an error a user can cause."""
    # `user` is the session's profile, for the energy and meal plan tools only: it never goes into
    # the model's messages (T9.3).
    # language is the app's language control (en or de) (T7.2), never taken from the text; an
    # unknown one is a bug in the caller, refused before any call.
    # conversation is the session's memory (T9.4): the turn sees its earlier questions and answers
    # and, when answered, is kept in it. None: the turn stands alone (the evaluation run).
    # callbacks: None, or a callback left as None, tells the caller nothing.
    callbacks = callbacks or TurnCallbacks()
    if language not in config.ANSWER_LANGUAGE_PROMPT_PATHS:
        raise ValueError(f"Unknown answer language: {language!r}")
    turn_id = str(uuid.uuid4())
    started = time.monotonic()
    steps: list[Step] = []
    recorder = UsageRecorder()
    trace = _TurnTrace()
    from src.agent import search  # The search tool builds on this package's helpers.

    search_log = search.SearchLog()
    from src.agent import graph  # The graph builds its nodes from this package's helpers.

    # The prompts are read once, here, so the run's metadata carries the versions of the very text
    # the turn sends (T10.4). A missing one is kept and raised by the prepare node, after the guard,
    # so a rejected input still gets the guard's message as before. Any other error (a bug) is kept
    # and raised there too, so outcome() maps it to its fixed message and run_turn() never raises.
    prompts: graph.TurnPrompts | Exception
    try:
        prompts = graph.load_turn_prompts(language, coach=deps.coach is not None)
    except Exception as exc:
        prompts = exc
    versions = prompts.versions() if isinstance(prompts, graph.TurnPrompts) else {}

    def keep_chunks(chunks: Sequence[RetrievedChunk]) -> None:
        """Keep a search's new chunks for the log line, then pass them to the caller's callback."""
        trace.chunks.extend(chunks)
        if callbacks.on_chunks is not None:
            callbacks.on_chunks(chunks)

    def step(name: Step) -> None:
        """Record a step and report it to the caller's progress indicator."""
        steps.append(name)
        if callbacks.on_step is not None:
            callbacks.on_step(name)

    def graph_turn() -> TurnResult:
        """Run the turn's graph: the guard first, the index and the models only if it passes."""
        # The one place a TurnContext is built from the turn's deps (T10.7). Each factory runs at
        # most once a turn; the prepare node calls them in order (T9.2).
        context = graph.TurnContext(
            chat_model=cache(deps.chat_model),
            tools=cache(
                partial(
                    registry.build_tools,
                    user,
                    food_api=deps.food_api,
                    # A coach's clients' names never reach the FoodData Central API (T9.9).
                    client_names=deps.coach.client_names if deps.coach is not None else (),
                    # A coach's client tools and this chat's references (T9.17).
                    clients=deps.clients,
                )
            ),
            on_step=step,
            on_text=callbacks.on_text,
            recorder=recorder,
            on_tool_run=trace.tool_runs.append,
            limiter=limiter,
            open_index=cache(deps.open_index),
            translation_model=cache(deps.translation_model),
            manifest=deps.manifest or {},
            keyword_index=deps.keyword_index,
            language=language,
            on_chunks=keep_chunks,
            search_log=search_log,
            turn_id=turn_id,
            coach=deps.coach,
            prompts=prompts,
        )

        def turn_graph(
            history: list[BaseMessage], domains: Mapping[str, Domain] | None = None
        ) -> Mapping[str, Any]:
            """Run the turn's graph after these earlier messages and return its output."""
            # domains: each earlier question's domain, by its message id (T10.5).
            return graph.chat_graph().invoke(
                {"text": text, "history": history, "history_domains": domains or {}},
                context=context,
                config=graph.run_config(turn_id, deps.run_trace, versions),
            )

        if conversation is None:
            return turn_graph([], {})["result"]
        return conversation.run(turn_graph, turn_id, versions)

    def failed(message: str, code: str, *, index_not_ready: bool = False) -> TurnResult:
        """Return an error result with the steps run and the tokens spent before the error."""
        return TurnResult(
            "error",
            message,
            steps=tuple(steps),
            index_not_ready=index_not_ready,
            usage=tuple(recorder.calls),
            code=code,
        )

    def outcome() -> TurnResult:
        """Run the turn's graph and return how it ended, writing a warning for a failure."""
        try:
            result = graph_turn()
        except llm.LLMError as exc:
            # A fixed text, safe to show (never the server's reply or the key).
            logger.warning(
                "llm_error",
                extra={
                    "turn_id": turn_id,
                    "code": exc.code,
                    "status_code": exc.status_code,
                    "diagnostic": exc.diagnostic,
                },
            )
            return failed(str(exc), exc.code)
        except IndexNotReadyError as exc:
            return failed(str(exc), exc.code, index_not_ready=True)
        except PromptMissingError as exc:
            return failed(str(exc), exc.code)
        except config.SecretsFileError:
            return failed(config.SECRETS_FILE_MESSAGE, "key.secrets_file")
        except config.MissingAPIKeyError:
            return failed(config.MISSING_KEY_MESSAGE, "key.missing")
        except Exception as exc:
            # Any other error (a bug, an unexpected library error) gets a fixed message too (T1.8).
            # Only its type and place are logged: its message or arguments may hold the question,
            # a chunk or a server's reply. BaseException (Streamlit's rerun and stop) is not
            # caught.
            logger.error(
                "turn_error", extra={"turn_id": turn_id, "diagnostic": llm.error_diagnostic(exc)}
            )
            return failed(config.TURN_ERROR_MESSAGE, "turn.error")
        return replace(result, steps=tuple(steps), usage=tuple(recorder.calls))

    result = replace(outcome(), turn_id=turn_id, prompts=versions)
    trace.searches = len(search_log.searches)
    try:
        _log_turn(result, language, trace, time.monotonic() - started, deps.prices)
    except Exception:
        # A turn is not lost because its log line could not be built (e.g. the prices callable
        # raised); only the fixed event is written, never the error's message.
        logger.error("log_failed", extra={"turn_id": turn_id})
    return result
