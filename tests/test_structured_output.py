"""Tests for the structured output models and the prompts beside them (T10.3)."""

import json
import re
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from src import config, llm
from src.rag.query_translation import QueryPlan
from src.weekly_review import Recommendation, Statement, WeeklyReview

MODELS = (QueryPlan, WeeklyReview, Statement, Recommendation)
PROMPTS = sorted((config.PROJECT_ROOT / "src" / "prompts").glob("*.md"))
FAKE_KEY = "sk-test-not-a-real-key"
# Decision, ticket, owner-task and criterion IDs: a developer reads them in a docstring, but the
# docstring is also the schema's description, and they mean nothing to the model.
PROJECT_ID = re.compile(r"\b(?:D\d+|T\d+\.\d+|O\d+|AC-\d+)\b")
EMPTY_VALUES = ([], {}, None, False, "", 0)


def _json_objects(text: str) -> Iterator[dict[str, Any]]:
    """Yield every JSON object written in the text, nested ones included."""
    decoder = json.JSONDecoder()
    for brace in re.finditer(r"\{", text):
        try:
            found, _ = decoder.raw_decode(text, brace.start())
        except json.JSONDecodeError:
            continue
        if isinstance(found, dict):
            yield found


def _is_skeleton(found: dict[str, Any], model: type[BaseModel]) -> bool:
    """Say whether the object lists two or more of the model's fields, every value empty."""
    # Empty values tell a skeleton from the prompt's few-shot examples, which fill the fields; a
    # skeleton written with placeholder values ("string", "integer or null") is not caught.
    shared = set(found) & set(model.model_fields)
    return len(shared) >= 2 and all(value in EMPTY_VALUES for value in found.values())


def _described(schema: dict[str, Any], where: str) -> Iterator[tuple[str, str | None]]:
    """Yield each object and property of a JSON schema with its description, nested ones too."""
    yield where, schema.get("description")
    for name, field in schema.get("properties", {}).items():
        yield f"{where}.{name}", field.get("description")
    for name, nested in schema.get("$defs", {}).items():
        yield from _described(nested, name)


def _schema_sent(model: type[BaseModel]) -> dict[str, Any]:
    """Return the json_schema the real client sends for the model, against a fake server."""
    requests: list[dict[str, Any]] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        """Record the request and reply with a cut-off completion, so the call stops there."""
        requests.append(json.loads(request.content))
        choice = {"index": 0, "message": {"role": "assistant", "content": ""}}
        body = {"id": "gen-test", "object": "chat.completion", "created": 0, "model": "x"}
        return httpx2.Response(
            200, json={**body, "choices": [{**choice, "finish_reason": "length"}]}
        )

    chat = llm.build_chat_model(
        config.QUERY_TRANSLATION_MODEL,
        config.QUERY_TRANSLATION_MAX_TOKENS,
        api_key=FAKE_KEY,
        http_client=httpx2.Client(transport=httpx2.MockTransport(answer)),
    )
    with pytest.raises(llm.ReplyCutOffError), llm.mapped_errors():
        chat.with_structured_output(model, method="json_schema").invoke("question")
    return requests[0]["response_format"]["json_schema"]


# --- The schema is given once (criterion 1) -------------------------------------------------------


def test_the_skeleton_check_finds_the_old_query_translation_skeleton():
    """The check below catches the JSON skeleton the prompt held before T10.3."""
    old = '{"queries": [], "topics": [], "min_year": null, "evidence_tier": null}'
    assert any(_is_skeleton(found, QueryPlan) for found in _json_objects(f"Return:\n{old}\n"))


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda path: path.name)
def test_no_prompt_holds_a_schema_skeleton(prompt):
    """No prompt repeats a structured output model's fields as a JSON object of empty values."""
    for found in _json_objects(prompt.read_text(encoding="utf-8")):
        for model in MODELS:
            assert not _is_skeleton(found, model), f"{prompt.name} repeats {model.__name__}."


def test_every_example_in_the_query_translation_prompt_is_a_valid_plan():
    """Each example output in the owner's prompt has exactly the plan's fields and parses."""
    text = config.QUERY_TRANSLATION_PROMPT_PATH.read_text(encoding="utf-8")
    examples = [found for found in _json_objects(text) if "queries" in found]
    assert examples, "The prompt has no example output."
    for example in examples:
        assert set(example) == set(QueryPlan.model_fields), example["queries"]
        QueryPlan.model_validate(example)


# --- No prompt describes behaviour the app no longer has (criteria 2 and 3) -----------------------


@pytest.mark.parametrize("name", ["<profile>", "needs_tool", "needs_profile"])
def test_the_query_translation_prompt_names_nothing_the_app_dropped(name):
    """The prompt names no <profile> block and neither routing flag (dropped in T9.3 and T10.3)."""
    assert name not in config.QUERY_TRANSLATION_PROMPT_PATH.read_text(encoding="utf-8")


def test_the_plan_has_no_routing_flags():
    """QueryPlan keeps only the search fields: the agent decides on tools since T9.3."""
    assert tuple(QueryPlan.model_fields) == ("queries", "topics", "min_year", "evidence_tier")


# --- Field meanings live in the models (criterion 4) ----------------------------------------------


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_every_model_and_field_has_a_description(model):
    """Each model and each of its fields has a description, with no project ID in it."""
    for where, text in _described(model.model_json_schema(), model.__name__):
        assert text and text.strip(), f"{where} has no description."
        assert not PROJECT_ID.search(text), f"{where} names a project ID: {text}"


@pytest.mark.parametrize("model", [QueryPlan, WeeklyReview], ids=lambda model: model.__name__)
def test_the_strict_schema_sent_keeps_every_description(model):
    """The strict schema the real client sends carries every description, all fields required."""
    sent = _schema_sent(model)
    assert sent["strict"] is True
    schema = sent["schema"]
    assert all(text for _, text in _described(schema, model.__name__))
    assert dict(_described(schema, model.__name__)) == dict(
        _described(model.model_json_schema(), model.__name__)
    )
    for nested in (schema, *schema.get("$defs", {}).values()):
        assert nested["additionalProperties"] is False
        assert sorted(nested["required"]) == sorted(nested["properties"])
        assert '"default"' not in json.dumps(nested)
