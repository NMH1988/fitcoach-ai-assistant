"""Integration tests for the answer step's tool loop with a scripted model (T4.4, AC 1, 2, 5)."""

import json

import httpx2
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src import chat, config, guard, llm
from src.chat import Step
from src.tools import registry
from src.tools.registry import FOOD_TOOL, MACRO_TOOL, TDEE_TOOL
from tests.fakes import (
    HOSTILE_FOOD_NAME,
    PROFILE,
    ScriptedChatModel,
    build_fixture_index,
    open_fixture_index,
    tool_reply,
    write_food_table,
)

QUESTION = "How much protein per meal?"
ANSWER = "About 0.4 g/kg per meal [S1]."
OATS = {"food": "rolled oats", "grams": 80}
# Matches no fixture chunk (no keyword of tests.fakes.KEYWORDS), like a food question in the app.
FOOD_QUESTION = "How many kcal are in 80 g of rolled oats?"


@pytest.fixture(autouse=True)
def test_prompt(tmp_path, monkeypatch):
    """Use a test prompt and the fixture foods table, so no test depends on the real files."""
    path = tmp_path / "prompt.md"
    path.write_text("Test system prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_PROMPT_PATH", path)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", write_food_table(tmp_path / "foods.csv"))


@pytest.fixture(scope="module")
def index_path(tmp_path_factory):
    """Build the fixture index once for the module and return its directory."""
    return build_fixture_index(tmp_path_factory.mktemp("index") / "chroma")


@pytest.fixture
def index(index_path):
    """Open the fixture index with the keyword embeddings."""
    return open_fixture_index(index_path)


def _turn(index, *replies: AIMessage, user=PROFILE, on_step=None, on_text=None, question=QUESTION):
    """Run one turn on the fixture index with a model scripted with these replies."""
    model = ScriptedChatModel(replies=list(replies))
    result = chat.run_turn(
        question,
        guard.RateLimiter(),
        open_index=lambda: index,
        chat_model=lambda: model,
        on_step=on_step,
        on_text=on_text,
        user=user,
    )
    return result, model


def _tool_messages(model: ScriptedChatModel, call: int = -1) -> list[ToolMessage]:
    """Return the tool messages the model received in a call (the last by default)."""
    return [m for m in model.calls[call] if isinstance(m, ToolMessage)]


def _content(message: ToolMessage) -> dict:
    """Return a tool message's JSON content."""
    return json.loads(message.content)


# --- The loop: one tool, two tools, errors, the round limit (AC 1) --------------------------------


def test_one_tool_call_runs_and_the_model_answers_from_its_result(index):
    """The model calls one tool, gets its result as a tool message, then answers."""
    result, model = _turn(index, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER))
    assert (result.kind, result.text) == ("answer", ANSWER)
    assert [(run.name, run.status) for run in result.tool_runs] == [(TDEE_TOOL, "ok")]
    assert len(model.calls) == 2
    system, user, request, reply = model.calls[1]
    assert isinstance(system, SystemMessage) and isinstance(user, HumanMessage)
    assert isinstance(request, AIMessage) and isinstance(reply, ToolMessage)
    assert request.tool_calls[0]["name"] == TDEE_TOOL
    assert reply.tool_call_id == request.tool_calls[0]["id"]
    assert _content(reply)["tdee_kcal"] == 2759


def test_every_call_binds_the_three_tools(index):
    """Each model call gets the three tools' schemas and no forced tool choice before the limit."""
    _, model = _turn(index, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER))
    for kwargs in model.call_kwargs:
        names = [tool["function"]["name"] for tool in kwargs["tools"]]
        assert sorted(names) == sorted([TDEE_TOOL, MACRO_TOOL, FOOD_TOOL])
        assert kwargs["tool_choice"] is None


def test_two_tools_in_one_round_both_run_in_order(index):
    """Two calls in one reply give two tool messages, in the order called."""
    result, model = _turn(index, tool_reply((MACRO_TOOL, {}), (FOOD_TOOL, OATS)), AIMessage(ANSWER))
    assert [run.name for run in result.tool_runs] == [MACRO_TOOL, FOOD_TOOL]
    first, second = _tool_messages(model)
    assert (first.tool_call_id, second.tool_call_id) == ("call-0", "call-1")
    assert _content(first)["targets"]["kcal_target"] == 3035
    assert _content(second)["nutrients"]["kcal"] == 304


def test_rounds_follow_each_other_and_the_steps_show_them(index):
    """Two rounds run one after the other; the steps show each tool round between answers."""
    steps = []
    result, model = _turn(
        index,
        tool_reply((TDEE_TOOL, {})),
        tool_reply((FOOD_TOOL, OATS)),
        AIMessage(ANSWER),
        on_step=steps.append,
    )
    assert len(model.calls) == 3
    assert len(_tool_messages(model)) == 2
    assert steps == [
        Step.CHECK,
        Step.SEARCH,
        Step.ANSWER,
        Step.TOOLS,
        Step.ANSWER,
        Step.TOOLS,
        Step.ANSWER,
    ]
    assert result.steps == tuple(steps)


def test_a_tool_error_returns_to_the_model_as_a_message(index, monkeypatch, tmp_path):
    """A missing foods table gives the fixed message as the tool result; the turn goes on."""
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "missing.csv")
    result, model = _turn(index, tool_reply((FOOD_TOOL, OATS)), AIMessage(ANSWER))
    [reply] = _tool_messages(model)
    assert reply.status == "error"
    assert _content(reply) == {"status": "error", "message": config.TOOL_FAILED_MESSAGE}
    assert (result.kind, result.tool_runs[0].status) == ("answer", "error")


def test_invalid_arguments_return_to_the_model_as_a_message(index):
    """Arguments that fail the schema come back as the fixed message, and the model answers."""
    result, model = _turn(
        index,
        tool_reply((TDEE_TOOL, {"weight_kg": 50}), (FOOD_TOOL, {"food": "oats"})),
        AIMessage(ANSWER),
    )
    tdee, food = _tool_messages(model)
    assert _content(tdee)["message"] == config.NO_ARGUMENTS_MESSAGE
    assert _content(food)["message"].startswith("Invalid food lookup: ")
    assert result.kind == "answer"


def test_the_loop_stops_after_four_rounds_and_asks_for_the_answer(index):
    """After 4 tool rounds the fifth call has tool_choice "none", and its answer is used."""
    rounds = [tool_reply((TDEE_TOOL, {})) for _ in range(config.MAX_TOOL_ROUNDS)]
    result, model = _turn(index, *rounds, AIMessage(ANSWER))
    assert config.MAX_TOOL_ROUNDS == 4
    assert len(model.calls) == 5
    assert [kwargs["tool_choice"] for kwargs in model.call_kwargs] == [None] * 4 + ["none"]
    assert len(result.tool_runs) == 4
    assert result.text == ANSWER


def test_tool_calls_after_the_last_round_end_the_turn_with_an_error(index):
    """A model that calls tools in the last call gets no fifth round; the turn shows an error."""
    rounds = [tool_reply((TDEE_TOOL, {})) for _ in range(config.MAX_TOOL_ROUNDS + 1)]
    result, model = _turn(index, *rounds)
    assert len(model.calls) == 5
    assert (result.kind, result.text) == ("error", chat.ToolLoopError.user_message)


def test_at_most_six_calls_of_one_reply_run(index):
    """Calls beyond MAX_TOOL_CALLS_PER_ROUND get the fixed message; every call is answered."""
    calls = [(FOOD_TOOL, OATS)] * (config.MAX_TOOL_CALLS_PER_ROUND + 2)
    result, model = _turn(index, tool_reply(*calls), AIMessage(ANSWER))
    replies = _tool_messages(model)
    assert len(replies) == len(calls)
    statuses = [_content(reply)["status"] for reply in replies]
    assert statuses == ["found"] * config.MAX_TOOL_CALLS_PER_ROUND + ["invalid"] * 2
    assert _content(replies[-1])["message"] == config.TOO_MANY_TOOL_CALLS_MESSAGE
    assert len(result.tool_runs) == len(calls)


def test_arguments_that_are_not_json_get_the_fixed_message(index):
    """A call whose arguments do not parse is answered with the fixed message, not run."""
    # Langchain completes a JSON string that is only cut short, so this one is not JSON at all;
    # a reply cut off by the token limit is refused before (test_a_cut_off_tool_call_is_not_run).
    broken = AIMessage(
        "",
        invalid_tool_calls=[
            {"name": FOOD_TOOL, "args": "food = oats", "id": "bad-1", "error": None}
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    result, model = _turn(index, broken, AIMessage(ANSWER))
    [reply] = _tool_messages(model)
    assert reply.tool_call_id == "bad-1"
    assert _content(reply)["message"] == config.INVALID_TOOL_JSON_MESSAGE
    assert result.kind == "answer"


def test_a_cut_off_tool_call_is_not_run(index):
    """A reply cut off by the token limit is an error, and its tool calls never run."""
    cut = tool_reply((FOOD_TOOL, OATS))
    cut.response_metadata = {"finish_reason": "length"}
    result, model = _turn(index, cut)
    assert (result.kind, result.text) == ("error", llm.ReplyCutOffError.user_message)
    assert len(model.calls) == 1
    assert result.tool_runs == ()


def test_text_before_tool_calls_is_cleared_from_the_screen(index):
    """Text the model writes in a tool round is cleared before the answer streams in."""
    shown = []
    _turn(
        index,
        tool_reply((TDEE_TOOL, {}), text="Let me check."),
        AIMessage(ANSWER),
        on_text=shown.append,
    )
    cleared = shown.index("")
    assert shown[cleared - 1] == "Let me check."
    assert shown[-1] == ANSWER


# --- No relevant source: a tool may still answer (owner's choice, B2) -----------------------------


def test_with_no_source_a_tool_can_still_answer(index):
    """A food question that matches no chunk is answered from the lookup, citing nothing."""
    tool_text = "Let me look that up."
    answer = "The app's food lookup gives 304 kcal for 80 g of rolled oats."
    shown = []
    result, model = _turn(
        index,
        tool_reply((FOOD_TOOL, OATS), text=tool_text),
        AIMessage(answer),
        question=FOOD_QUESTION,
        on_text=shown.append,
    )
    assert (result.kind, result.text, result.sources) == ("answer", answer, ())
    assert [run.status for run in result.tool_runs] == ["found"]
    _, user = model.calls[0][:2]
    assert f"<sources>\n{config.NO_SOURCES_BLOCK}\n</sources>" in user.content
    # The first reply is never shown on this path; the answer after the tool is.
    assert tool_text not in " ".join(shown)
    assert shown[-1] == answer


def test_with_no_source_and_no_tool_the_fixed_message_is_shown(index):
    """With no chunk and no tool call the model's text is dropped for the fixed message."""
    shown = []
    result, model = _turn(
        index,
        AIMessage("Oats have about 380 kcal per 100 g."),
        question=FOOD_QUESTION,
        on_text=shown.append,
    )
    assert (result.kind, result.text) == ("no_sources", config.NO_SOURCES_MESSAGE)
    assert result.tool_runs == ()
    assert len(model.calls) == 1
    assert shown == []


# --- The profile (AC 2) ---------------------------------------------------------------------------


def test_the_profile_is_in_its_own_block_of_the_user_message(index):
    """The profile goes in <profile> between the sources and the question, never in the prompt."""
    _, model = _turn(index, AIMessage(ANSWER))
    [[system, user]] = model.calls
    block = (
        "<profile>\nWeight: 80 kg\nHeight: 180 cm\nAge: 30 years\nSex: Male\n"
        "Activity: Moderate · exercise 4-5 times a week\nGoal: Build muscle\n</profile>"
    )
    assert block in user.content
    assert user.content.index("</sources>") < user.content.index("<profile>")
    assert user.content.index("</profile>") < user.content.index("<user_input>")
    assert "80 kg" not in system.content and "<profile>" not in system.content


def test_without_a_profile_the_block_says_so(index):
    """With no profile the block says the user has not added their details."""
    _, model = _turn(index, AIMessage(ANSWER), user=None)
    [[_, user]] = model.calls
    assert "<profile>\nNot given: the user has not added their details.\n</profile>" in user.content


def test_without_a_profile_an_energy_tool_returns_profile_needed(index):
    """calculate_macro_targets with no profile tells the model the profile is needed."""
    result, model = _turn(index, tool_reply((MACRO_TOOL, {})), AIMessage(ANSWER), user=None)
    [reply] = _tool_messages(model)
    assert _content(reply)["status"] == "profile_needed"
    assert result.tool_runs[0].status == "profile_needed"


def test_the_energy_tools_use_the_profile_of_the_turn(index):
    """Another profile gives other numbers: the tools read the profile given to the turn."""
    lighter = PROFILE.model_copy(update={"weight_kg": 60.0})
    _, model = _turn(index, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER), user=lighter)
    assert _content(_tool_messages(model)[0])["bmr_kcal"] == 1580


# --- The real client on the wire (AC 1) -----------------------------------------------------------


def _sse(*deltas: tuple[dict, str | None]) -> bytes:
    """Return an OpenAI-style streamed reply: one chunk per (delta, finish_reason), then [DONE]."""
    lines = []
    for delta, finish in deltas:
        chunk = {
            "id": "gen-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": config.DEFAULT_ANSWER_MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    return ("".join(lines) + "data: [DONE]\n\n").encode()


TOOL_CALL_STREAM = _sse(
    (
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": TDEE_TOOL, "arguments": "{}"},
                }
            ],
        },
        None,
    ),
    ({}, "tool_calls"),
)
ANSWER_STREAM = _sse(({"role": "assistant", "content": ANSWER}, None), ({}, "stop"))


class StreamServer:
    """A fake OpenRouter that streams the given replies in turn and records each request body."""

    def __init__(self, *replies: bytes):
        """Keep the streamed replies to send, in order."""
        self.replies = list(replies)
        self.bodies: list[dict] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Record the request body and stream the next reply."""
        self.bodies.append(json.loads(request.content))
        return httpx2.Response(
            200, content=self.replies.pop(0), headers={"content-type": "text/event-stream"}
        )


def _wire_loop(server: StreamServer) -> tuple[str, tuple]:
    """Run the tool loop with the real chat client against the fake server."""
    model = llm.build_chat_model(
        api_key="sk-test-not-a-real-key",
        http_client=httpx2.Client(transport=httpx2.MockTransport(server)),
    )
    messages = chat.build_messages(QUESTION, [], "Test system prompt.", PROFILE)
    tools = registry.build_tools(PROFILE)
    return chat.answer_with_tools(model, messages, tools, on_step=lambda step: None)


def test_the_real_client_sends_the_tools_and_the_tool_round(no_env_key):
    """ChatOpenAI sends the three tools, then the tool call and its result with matching ids."""
    server = StreamServer(TOOL_CALL_STREAM, ANSWER_STREAM)
    answer, runs = _wire_loop(server)
    assert answer == ANSWER
    assert [run.name for run in runs] == [TDEE_TOOL]
    first, second = server.bodies
    for body in (first, second):
        assert sorted(t["function"]["name"] for t in body["tools"]) == sorted(
            registry.build_tools(PROFILE)
        )
        assert "tool_choice" not in body
        # Binding the tools changes neither the model nor the token cap.
        assert body["model"] == config.DEFAULT_ANSWER_MODEL
        assert body["max_completion_tokens"] == config.DEFAULT_MAX_TOKENS
    request, reply = second["messages"][-2:]
    assert request["role"] == "assistant"
    assert request["tool_calls"][0]["id"] == "call_1"
    assert reply == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": reply["content"],
    }
    assert json.loads(reply["content"])["tdee_kcal"] == 2759


def test_the_real_client_sends_tool_choice_none_after_the_last_round(no_env_key):
    """After four tool rounds the fifth request carries tool_choice "none"."""
    rounds = [TOOL_CALL_STREAM] * config.MAX_TOOL_ROUNDS
    server = StreamServer(*rounds, ANSWER_STREAM)
    answer, runs = _wire_loop(server)
    assert answer == ANSWER
    assert len(runs) == config.MAX_TOOL_ROUNDS
    assert ["tool_choice" in body for body in server.bodies] == [False] * 4 + [True]
    assert server.bodies[-1]["tool_choice"] == "none"


# --- USDA names reach the model only inside the tool result (AC 5) --------------------------------


def test_a_usda_name_reaches_the_model_only_inside_the_tool_message(index):
    """A name with Markdown and a delimiter is in the tool message only, as JSON data."""
    _, model = _turn(
        index, tool_reply((FOOD_TOOL, {"food": HOSTILE_FOOD_NAME, "grams": 100})), AIMessage(ANSWER)
    )
    system, user, *_ = model.calls[-1]
    assert HOSTILE_FOOD_NAME not in system.content
    assert HOSTILE_FOOD_NAME not in user.content
    [reply] = _tool_messages(model)
    assert _content(reply)["matched_name"] == HOSTILE_FOOD_NAME
