"""The agent's knowledge base search (T9.3, D10): `search_knowledge_base` as one of its tools.

The model decides whether to search and writes the query; the search runs the same query
translation and hybrid search as the fixed pipeline before T9.3, with the same coverage gate
(`chat.find_chunks()`: only the query's own nearest chunk decides, T3.8). The chunks come back to
the model inside a delimited `<sources>` block in the tool message, escaped like every block, so
retrieved text stays data (T3.4). The query is the model's text: it is checked (type and length),
used only for the rewrite and the search, and escaped wherever it is shown or sent.

A turn's searches share one `SearchLog`, kept in the run's context like the usage recorder, so
each search numbers its chunks after the ones before it, even in the same round, which state
updates (applied only when the round ends) could not do. A chunk found again keeps its first label,
so `[S#]` labels stay unique across the turn. The log takes a lock: the turn runs a round's calls
one at a time (`graph.run_config()`), but the cap and the labels must hold if they ran together.
"""

import dataclasses
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError, field_validator

from src import chat, config, llm
from src.chat import SearchDetails
from src.rag import query_translation
from src.rag.retriever import RetrievedChunk, chunk_key
from src.tools import registry
from src.tools.registry import ToolRun

if TYPE_CHECKING:
    from src.agent.graph import TurnContext

SEARCH_TOOL = "search_knowledge_base"
# What the model reads about the tool: what it does, what it returns, and that the query carries no
# personal values (owner's choice of 2026-10-29, after the compliance review: the query goes to the
# query translation and embedding models). When to call it is the owner's to write (O8).
SEARCH_DESCRIPTION = (
    "Search the app's research knowledge base (openly licensed review articles and position "
    "stands on nutrition for strength training) for passages relevant to a query. Returns the "
    "passages inside <sources>, each labelled [S#] for citing; if none is relevant, <sources> says "
    "so. Write the query in English as a short, self-contained research question. Never put the "
    "user's own values (weight, goal, activity, targets or other personal details) in the query."
)


class SearchArgs(BaseModel):
    """The search tool's one argument: the query, a non-blank text of limited length."""

    model_config = ConfigDict(extra="forbid")

    query: StrictStr

    @field_validator("query")
    @classmethod
    def _query_is_short_and_not_blank(cls, query: str) -> str:
        """Strip the query and refuse a blank one or one over SEARCH_QUERY_MAX_CHARS."""
        cleaned = query.strip()
        if not cleaned or len(cleaned) > config.SEARCH_QUERY_MAX_CHARS:
            raise ValueError("The query is blank or too long.")
        return cleaned


def _not_run_here(query: str) -> str:
    """Never called: the graph runs a search with the turn's index and clients (run_search())."""
    raise RuntimeError("search_knowledge_base runs only through the chat graph.")


def search_tool_definition() -> StructuredTool:
    """Return the tool the model is given: its name, description and argument schema."""
    return StructuredTool.from_function(
        func=_not_run_here,
        name=SEARCH_TOOL,
        description=SEARCH_DESCRIPTION,
        args_schema=SearchArgs,
    )


@dataclass
class SearchLog:
    """A turn's searches and the chunks they gave the model, in [S#] order."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    searches: list[SearchDetails] = field(default_factory=list)
    # Searches let through so far: counted before a search spends anything, so the cap holds even
    # for calls that run together.
    started: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def reserve(self) -> bool:
        """Count a search about to run; return False when the turn's cap is already reached."""
        with self._lock:
            if self.started >= config.MAX_SEARCHES_PER_TURN:
                return False
            self.started += 1
            return True

    def label(self, found: Sequence[RetrievedChunk]) -> tuple[list[int], list[RetrievedChunk]]:
        """Return each found chunk's [S#] number and the chunks new to this turn, labelling them."""
        with self._lock:
            numbers = {chunk_key(c): number for number, c in enumerate(self.chunks, start=1)}
            labels, new = [], []
            for chunk in found:
                key = chunk_key(chunk)
                if key not in numbers:
                    self.chunks.append(chunk)
                    numbers[key] = len(self.chunks)
                    new.append(chunk)
                labels.append(numbers[key])
            return labels, new

    def record(self, details: SearchDetails) -> None:
        """Keep a finished search's details, in the order the searches ended."""
        with self._lock:
            self.searches.append(details)


def run_search(
    context: TurnContext, call: ToolCall, translation_prompt: str
) -> tuple[ToolMessage, ToolRun | None]:
    """Run one search call: check the query, rewrite it, search; return the <sources> message."""
    # A refused call (too many searches, a bad query) is a refused run, like any tool's; a search
    # that ran is no run: it is in the turn's SearchLog, and the Details tab shows it (AC-3).
    log, open_index, translation_model = (
        context.search_log,
        context.open_index,
        context.translation_model,
    )
    if log is None or open_index is None or translation_model is None:
        # The graph offers the tool only to a whole turn, which has all three.
        raise RuntimeError("A search needs the turn's search log, index and translation model.")
    try:
        query = SearchArgs.model_validate(call["args"]).query
    except ValidationError:
        return registry.refused_call(call["id"] or "", config.INVALID_SEARCH_QUERY_MESSAGE)
    # Reserved before anything is spent: a refused query takes no place.
    if not log.reserve():
        return registry.refused_call(call["id"] or "", config.TOO_MANY_SEARCHES_MESSAGE)
    plan = query_translation.translate(
        query, translation_model(), translation_prompt, context.recorder
    )
    with llm.mapped_errors():
        found, details = chat.find_chunks(
            query,
            plan,
            open_index(),
            keyword_index=context.keyword_index,
            recorder=context.recorder,
        )
    labels, new = log.label(found)
    log.record(dataclasses.replace(details, labels=tuple(labels)))
    if context.on_chunks is not None:
        context.on_chunks(tuple(new))
    message = ToolMessage(
        chat.sources_block(found, labels),
        tool_call_id=call["id"] or "",
        name=SEARCH_TOOL,
        status="success",
    )
    return message, None
