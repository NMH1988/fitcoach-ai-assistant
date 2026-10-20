"""Tests for src/rag/query_translation.py: rewrites, filters and the fallback (T3.2, AC 1)."""

import json

import httpx2
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src import config, llm
from src.rag.query_translation import QueryPlan, build_filter, translate
from tests.fakes import ScriptedTranslator, build_fixture_index, open_fixture_index, plan_json

FAKE_KEY = "sk-test-not-a-real-key"
PROMPT = "Test query translation prompt."
QUESTION = "bulk diet?"
REWRITES = [
    "energy surplus for muscle gain",
    "protein intake during a bulking phase",
    "carbohydrate needs when gaining weight",
]


def _translate(*plans) -> tuple[QueryPlan | None, ScriptedTranslator]:
    """Translate QUESTION with a fake that gives these plans; return the plan and the fake."""
    model = ScriptedTranslator(plans=list(plans))
    return translate(QUESTION, model, PROMPT), model


# --- The plan: 3 rewrites and optional filters ----------------------------------------------------


def test_a_valid_reply_gives_three_rewrites_and_the_filters():
    """One call returns the 3 rewrites and the topic, year and tier filters."""
    reply = plan_json(REWRITES, ["energy_balance", "protein"], 2020, 1)
    plan, model = _translate(reply)
    assert plan == QueryPlan(
        queries=tuple(REWRITES),
        topics=("energy_balance", "protein"),
        min_year=2020,
        evidence_tier=1,
        needs_tool=True,
        needs_profile=True,
    )
    assert len(model.calls) == 1


def test_filters_left_out_mean_no_filter():
    """A plan with empty topics and null year and tier sets no filter."""
    plan, _ = _translate(plan_json(REWRITES))
    assert plan is not None
    assert (plan.topics, plan.min_year, plan.evidence_tier) == ((), None, None)
    assert build_filter(plan) is None


def test_rewrites_are_stripped_and_topics_kept_once():
    """Spaces around a rewrite are dropped and a repeated topic counts once."""
    plan, _ = _translate(plan_json([f"  {q} " for q in REWRITES], ["protein", "fat", "protein"]))
    assert plan.queries == tuple(REWRITES)
    assert plan.topics == ("protein", "fat")


@pytest.mark.parametrize("needs_tool", [True, False])
@pytest.mark.parametrize("needs_profile", [True, False])
def test_the_plan_says_whether_a_tool_or_the_profile_is_needed(needs_tool, needs_profile):
    """needs_tool and needs_profile are read as the model sent them, each on its own (T3.5)."""
    plan, _ = _translate(plan_json(REWRITES, needs_tool=needs_tool, needs_profile=needs_profile))
    assert (plan.needs_tool, plan.needs_profile) == (needs_tool, needs_profile)


def _without(field: str) -> str:
    """Return a valid plan reply with one field left out."""
    reply = json.loads(plan_json(REWRITES))
    del reply[field]
    return json.dumps(reply)


def _with(**fields) -> str:
    """Return a valid plan reply with some fields set to other (raw JSON) values."""
    return json.dumps({**json.loads(plan_json(REWRITES)), **fields})


def test_the_structured_output_uses_the_json_schema_method():
    """The plan is asked for as JSON schema structured output."""
    _, model = _translate(plan_json(REWRITES))
    assert model.structured_kwargs == [{"method": "json_schema"}]


def test_the_question_goes_only_inside_user_input():
    """The system prompt is the owner's text; the question sits only in <user_input>."""
    _, model = _translate(plan_json(REWRITES))
    [[system, user]] = model.calls
    assert isinstance(system, SystemMessage) and system.content == PROMPT
    assert isinstance(user, HumanMessage)
    assert user.content == f"<user_input>\n{QUESTION}\n</user_input>"
    assert QUESTION not in system.content


# --- Invalid output falls back (None: the question alone, no filter) ------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        plan_json(REWRITES[:2]),
        plan_json([*REWRITES, "one more"]),
        plan_json([REWRITES[0], "   ", REWRITES[2]]),
        plan_json([REWRITES[0], "x" * (config.QUERY_REWRITE_MAX_CHARS + 1), REWRITES[2]]),
        plan_json(REWRITES, ["protein", "steroids"]),
        plan_json(REWRITES, min_year=config.QUERY_MIN_YEAR_RANGE[0] - 1),
        plan_json(REWRITES, min_year=config.QUERY_MIN_YEAR_RANGE[1] + 1),
        plan_json(REWRITES, evidence_tier=3),
        json.dumps(
            {"queries": "one string", "topics": [], "min_year": None, "evidence_tier": None}
        ),
        _without("needs_tool"),
        _without("needs_profile"),
        _with(needs_tool="yes"),
        _with(needs_tool=1),
        _with(needs_profile="true"),
        _with(needs_profile=None),
        "not JSON at all",
        "",
    ],
    ids=[
        "two-rewrites",
        "four-rewrites",
        "blank-rewrite",
        "rewrite-too-long",
        "unknown-topic",
        "year-too-early",
        "year-too-late",
        "unknown-tier",
        "queries-not-a-list",
        "needs-tool-missing",
        "needs-profile-missing",
        "needs-tool-a-string",
        "needs-tool-a-number",
        "needs-profile-a-string",
        "needs-profile-null",
        "not-json",
        "empty",
    ],
)
def test_invalid_output_falls_back(reply):
    """A reply that breaks the schema gives None: the question alone is searched, unfiltered."""
    plan, _ = _translate(reply)
    assert plan is None
    assert build_filter(plan) is None


def test_a_rewrite_at_the_length_limit_is_kept():
    """A rewrite of exactly QUERY_REWRITE_MAX_CHARS characters is accepted."""
    longest = "x" * config.QUERY_REWRITE_MAX_CHARS
    plan, _ = _translate(plan_json([longest, *REWRITES[1:]]))
    assert plan.queries[0] == longest


@pytest.mark.parametrize("error", [llm.InvalidReplyError(), llm.ReplyCutOffError()])
def test_a_refused_or_cut_off_reply_falls_back(error):
    """A refusal, an empty reply or one cut off by the token limit gives None."""
    plan, _ = _translate(error)
    assert plan is None


@pytest.mark.parametrize(
    "error",
    [llm.InvalidAPIKeyError(401), llm.OutOfCreditError(402), llm.RateLimitedError(429)],
    ids=["key", "credit", "rate-limit"],
)
def test_other_model_errors_are_raised(error):
    """Key, credit, rate limit or outage errors end the turn: the answer would meet them too."""
    with pytest.raises(type(error)):
        _translate(error)


# --- The real client, with a fake server (no network) ---------------------------------------------


def _reply(content: str | None = None, finish_reason: str = "stop", **message) -> dict:
    """Return an OpenRouter chat completion body with this message content."""
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "created": 0,
        "model": config.QUERY_TRANSLATION_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, **message},
                "finish_reason": finish_reason,
            }
        ],
    }


class _Server:
    """A fake OpenRouter server that records each request and gives one fixed reply."""

    def __init__(self, status: int, body: dict) -> None:
        """Keep the status and the JSON body to answer with."""
        self.status = status
        self.body = body
        self.requests: list[dict] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Record the request body and answer with the fixed reply."""
        self.requests.append(json.loads(request.content))
        return httpx2.Response(self.status, json=self.body)


def _real_translate(status: int, body: dict) -> tuple[QueryPlan | None, _Server]:
    """Translate QUESTION with the real query translation client against a fake server."""
    server = _Server(status, body)
    model = llm.build_chat_model(
        config.QUERY_TRANSLATION_MODEL,
        config.QUERY_TRANSLATION_MAX_TOKENS,
        api_key=FAKE_KEY,
        http_client=httpx2.Client(transport=httpx2.MockTransport(server)),
    )
    return translate(QUESTION, model, PROMPT), server


def test_the_real_client_parses_a_valid_reply():
    """With the real client, a valid JSON reply becomes the plan."""
    plan, server = _real_translate(200, _reply(plan_json(REWRITES, ["protein"])))
    assert plan.queries == tuple(REWRITES)
    assert plan.topics == ("protein",)
    [request] = server.requests
    assert request["model"] == config.QUERY_TRANSLATION_MODEL
    # The client's cap and effort reach the request: structured output overrides neither.
    assert request["max_completion_tokens"] == min(
        config.QUERY_TRANSLATION_MAX_TOKENS, config.MAX_TOKENS_CAP
    )
    assert request["reasoning_effort"] == config.REASONING_EFFORT
    assert request["messages"][0] == {"role": "system", "content": PROMPT}
    assert request["messages"][1]["content"] == f"<user_input>\n{QUESTION}\n</user_input>"


def test_the_schema_sent_is_strict_and_has_no_string_length_limit():
    """OpenAI's strict schema mode rejects maxLength, so the rewrite length is checked locally."""
    _, server = _real_translate(200, _reply(plan_json(REWRITES)))
    response_format = server.requests[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = json.dumps(response_format["json_schema"]["schema"])
    assert "maxLength" not in schema and "minLength" not in schema
    assert '"default"' not in schema
    assert sorted(response_format["json_schema"]["schema"]["required"]) == sorted(
        QueryPlan.model_fields
    )
    for topic in config.TOPICS:
        assert f'"{topic}"' in schema


def test_the_schema_sent_has_the_two_required_booleans():
    """needs_tool and needs_profile are required booleans in the strict schema sent (T3.5)."""
    _, server = _real_translate(200, _reply(plan_json(REWRITES)))
    schema = server.requests[0]["response_format"]["json_schema"]["schema"]
    for field in ("needs_tool", "needs_profile"):
        assert field in schema["required"]
        assert schema["properties"][field]["type"] == "boolean"


def test_the_real_client_reads_the_two_flags():
    """With the real client, false flags in the reply stay false in the plan (T3.5)."""
    reply = plan_json(REWRITES, needs_tool=False, needs_profile=False)
    plan, _ = _real_translate(200, _reply(reply))
    assert (plan.needs_tool, plan.needs_profile) == (False, False)


@pytest.mark.parametrize(
    "body",
    [
        _reply(plan_json(REWRITES[:2])),
        _reply("not JSON at all"),
        _reply(None, refusal="I can't help with that."),
        _reply(""),
        _reply(plan_json(REWRITES), finish_reason="length"),
    ],
    ids=["schema", "not-json", "refusal", "empty", "cut-off"],
)
def test_the_real_client_falls_back_on_an_unusable_reply(body):
    """With the real client, a reply off the schema, refused, empty or cut off gives None."""
    plan, _ = _real_translate(200, body)
    assert plan is None


@pytest.mark.parametrize(
    ("status", "error"), [(401, llm.InvalidAPIKeyError), (402, llm.OutOfCreditError)]
)
def test_the_real_client_raises_key_and_credit_errors(status, error):
    """With the real client, a rejected key or no credit is raised as its mapped error."""
    with pytest.raises(error):
        _real_translate(status, {"error": {"message": "nope", "code": status}})


# --- Filters as Chroma where-filters --------------------------------------------------------------


def _plan(topics=(), min_year=None, evidence_tier=None) -> QueryPlan:
    """Return a plan with the given filters."""
    return QueryPlan(
        queries=tuple(REWRITES),
        topics=topics,
        min_year=min_year,
        evidence_tier=evidence_tier,
        needs_tool=False,
        needs_profile=False,
    )


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        (None, None),
        (_plan(), None),
        (_plan(("protein",)), {"topics": {"$contains": "protein"}}),
        (
            _plan(("protein", "fat")),
            {"$or": [{"topics": {"$contains": "protein"}}, {"topics": {"$contains": "fat"}}]},
        ),
        (_plan(min_year=2022), {"year": {"$gte": 2022}}),
        (_plan(evidence_tier=2), {"evidence_tier": {"$eq": 2}}),
        (
            _plan(("fat",), 2022, 1),
            {
                "$and": [
                    {"topics": {"$contains": "fat"}},
                    {"year": {"$gte": 2022}},
                    {"evidence_tier": {"$eq": 1}},
                ]
            },
        ),
    ],
    ids=["fallback", "none", "one-topic", "two-topics", "year", "tier", "all"],
)
def test_build_filter(plan, expected):
    """Each filter becomes its Chroma condition; several are joined with $and."""
    assert build_filter(plan) == expected


@pytest.fixture(scope="module")
def fixture_index(tmp_path_factory):
    """Open the fixture index (sources 1-4, years 2021-2024, tier 1 only for source 1)."""
    return open_fixture_index(build_fixture_index(tmp_path_factory.mktemp("index") / "chroma"))


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        (_plan(("protein",)), {"1-0", "1-1", "2-0"}),
        (_plan(("carbohydrate", "fat")), {"3-0", "4-0"}),
        (_plan(min_year=2023), {"3-0", "4-0"}),
        (_plan(evidence_tier=1), {"1-0", "1-1"}),
        (_plan(("protein",), 2022, 2), {"2-0"}),
        (_plan(("fat",), evidence_tier=1), set()),
    ],
    ids=["topic", "any-of-two-topics", "year", "tier", "all-three", "none-match"],
)
def test_the_filters_select_the_right_chunks_in_chroma(fixture_index, plan, expected):
    """The where-filter works on the real Chroma index, list topics included."""
    found = fixture_index.get(where=build_filter(plan), include=["metadatas"])
    assert {f"{m['source_id']}-{m['chunk_index']}" for m in found["metadatas"]} == expected


# --- The owner's prompt (O7) ---------------------------------------------------------------------


def test_the_query_translation_prompt_is_the_owners():
    """The committed prompt is the owner's text, not the placeholder (O7; blocks the merge)."""
    text = config.QUERY_TRANSLATION_PROMPT_PATH.read_text(encoding="utf-8").strip()
    assert not text.startswith("TODO (owner)"), "The owner has not written the prompt yet."


def test_the_query_translation_prompt_names_the_fields_and_topics():
    """The prompt names the delimiter, every field and every topic the schema accepts."""
    text = config.QUERY_TRANSLATION_PROMPT_PATH.read_text(encoding="utf-8")
    for name in ("<user_input>", *QueryPlan.model_fields, *config.TOPICS):
        assert name in text, f"The prompt does not mention {name}."
