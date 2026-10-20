"""Query translation: one small-model call rewrites the question and picks optional filters (T3.2).

The question goes only inside <user_input> in the user message, escaped like the answer step's
(`src/prompt_data.py`, T3.4), and the messages are built directly, never from a prompt template;
the system prompt is the owner's (O7). The rewrites are used for the search and shown in the app,
never sent to the answer model.
"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src import config, llm
from src.prompt_data import escape_prompt_data

Topic = Literal[config.TOPICS]
EvidenceTier = Literal[config.EVIDENCE_TIERS]


class QueryPlan(BaseModel):
    """Search queries that rephrase one question, and optional topic, year and evidence filters."""

    model_config = ConfigDict(frozen=True)

    # The schema is sent with strict: true, so it keeps to keywords OpenAI's strict mode lists
    # (minItems, maxItems, minimum, maximum, enum): string lengths are checked below instead, and
    # no field has a default (every field is required; "no filter" is an empty list or null).
    queries: tuple[str, ...] = Field(
        min_length=config.QUERY_REWRITES, max_length=config.QUERY_REWRITES
    )
    topics: tuple[Topic, ...] = Field(max_length=len(config.TOPICS))
    min_year: int | None = Field(
        ge=config.QUERY_MIN_YEAR_RANGE[0], le=config.QUERY_MIN_YEAR_RANGE[1]
    )
    evidence_tier: EvidenceTier | None

    @field_validator("queries")
    @classmethod
    def _queries_are_short_and_not_blank(cls, queries: tuple[str, ...]) -> tuple[str, ...]:
        """Strip each rewrite and refuse a blank one or one over QUERY_REWRITE_MAX_CHARS."""
        cleaned = tuple(query.strip() for query in queries)
        if any(not query or len(query) > config.QUERY_REWRITE_MAX_CHARS for query in cleaned):
            raise ValueError("A rewrite is blank or too long.")
        return cleaned

    @field_validator("topics")
    @classmethod
    def _topics_once(cls, topics: tuple[str, ...]) -> tuple[str, ...]:
        """Keep each topic once, in the order given."""
        return tuple(dict.fromkeys(topics))


def build_messages(question: str, system_prompt: str) -> list[SystemMessage | HumanMessage]:
    """Return the owner's system prompt and a user message holding only <user_input>."""
    # Escaped, so a look-alike such as "</user_input>" in the question cannot end the block.
    user = f"<user_input>\n{escape_prompt_data(question)}\n</user_input>"
    return [SystemMessage(system_prompt), HumanMessage(user)]


def translate(question: str, model: BaseChatModel, system_prompt: str) -> QueryPlan | None:
    """Return the model's search plan for the question, or None if its reply was unusable."""
    structured = model.with_structured_output(QueryPlan, method="json_schema")
    try:
        with llm.mapped_errors():
            plan = structured.invoke(build_messages(question, system_prompt))
    except llm.InvalidReplyError, llm.ReplyCutOffError:
        # A reply off the schema, refused, empty or cut off: search the question alone, unfiltered.
        # Other errors (key, credit, rate limit, outage) end the turn; the answer would meet them.
        return None
    return plan if isinstance(plan, QueryPlan) else None


def build_filter(plan: QueryPlan | None) -> dict[str, Any] | None:
    """Return the Chroma where-filter for the plan's filters, or None when it sets none."""
    if plan is None:
        return None
    conditions: list[dict[str, Any]] = []
    # A chunk matches the topic filter when it carries any of the topics named.
    topic_conditions = [{"topics": {"$contains": topic}} for topic in plan.topics]
    if len(topic_conditions) == 1:
        conditions.append(topic_conditions[0])
    elif topic_conditions:
        conditions.append({"$or": topic_conditions})
    if plan.min_year is not None:
        conditions.append({"year": {"$gte": plan.min_year}})
    if plan.evidence_tier is not None:
        conditions.append({"evidence_tier": {"$eq": plan.evidence_tier}})
    if not conditions:
        return None
    # Chroma needs at least two conditions inside $and.
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}
