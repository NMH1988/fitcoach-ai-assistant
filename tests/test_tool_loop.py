"""Integration tests for the answer step's tool loop with a scripted model (T4.4, AC 1, 2, 5).

Since T9.3 the agent decides whether to search: these turns call the tools directly (the scripted
model does not search first unless a test asks), as a food or calculator question does. The T9.3
section checks which questions search, what reaches the model, and when a turn ends with no answer
call (AC-2); `tests/test_agent_search.py` checks the search tool itself.
"""

import html
import json

import httpx2
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src import chat, config, guard, llm
from src.chat import Step
from src.tools import registry
from src.tools.registry import FOOD_TOOL, MACRO_TOOL, MEAL_PLAN_TOOL, TDEE_TOOL
from tests.fakes import (
    HOSTILE_FOOD_NAME,
    PROFILE,
    SEARCH_TOOL,
    ScriptedChatModel,
    ScriptedTranslator,
    build_fixture_index,
    open_fixture_index,
    plan_json,
    tool_reply,
    write_food_table,
)

QUESTION = "How much protein per meal?"
ANSWER = "About 0.4 g/kg per meal [S1]."
OATS = {"food": "rolled oats", "grams": 80}
NO_SOURCES = config.NO_SOURCES_MESSAGE
# Matches no fixture chunk (no keyword of tests.fakes.KEYWORDS), like a food question in the app.
FOOD_QUESTION = "How many kcal are in 80 g of rolled oats?"
OFF_TOPIC_QUESTION = "What is the offside rule in football?"
# The rewrites match no fixture chunk, like the question.
OFF_TOPIC_REWRITES = ["offside rule football", "football offside law", "offside position"]
# The values of the test profile as the <profile> block wrote them before T9.3.
PROFILE_VALUES = ("80 kg", "180 cm", "30 years", "Male", "Build muscle")
ALL_TOOLS = sorted([TDEE_TOOL, MACRO_TOOL, FOOD_TOOL, MEAL_PLAN_TOOL, SEARCH_TOOL])


@pytest.fixture(autouse=True)
def test_prompt(tmp_path, monkeypatch):
    """Use a test prompt and the fixture foods table, so no test depends on the real files."""
    path = tmp_path / "prompt.md"
    path.write_text("Test system prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_PROMPT_PATH", path)
    translation = tmp_path / "translation_prompt.md"
    translation.write_text("Test query translation prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "QUERY_TRANSLATION_PROMPT_PATH", translation)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", write_food_table(tmp_path / "foods.csv"))


@pytest.fixture(scope="module")
def index_path(tmp_path_factory):
    """Build the fixture index once for the module and return its directory."""
    return build_fixture_index(tmp_path_factory.mktemp("index") / "chroma")


@pytest.fixture
def index(index_path):
    """Open the fixture index with the keyword embeddings."""
    return open_fixture_index(index_path)


def _turn(
    index,
    *replies: AIMessage,
    user=PROFILE,
    on_step=None,
    on_text=None,
    question=QUESTION,
    plan: str | None = None,
    search_first: bool = False,
    translator: ScriptedTranslator | None = None,
):
    """Run one turn on the fixture index with a model scripted with these replies."""
    model = ScriptedChatModel(replies=list(replies), search_first=search_first)
    # With no plan given, the translator's rewrites repeat the query (tests/fakes.py).
    translator = translator or ScriptedTranslator(plans=[plan] if plan is not None else [])
    result = chat.run_turn(
        question,
        guard.RateLimiter(),
        open_index=lambda: index,
        chat_model=lambda: model,
        translation_model=lambda: translator,
        on_step=on_step,
        on_text=on_text,
        user=user,
    )
    return result, model


def _tool_messages(model: ScriptedChatModel, call: int = -1) -> list[ToolMessage]:
    """Return the tools' messages (no search's) the model received in a call (the last default)."""
    return [m for m in model.calls[call] if isinstance(m, ToolMessage) and m.name != SEARCH_TOOL]


def _search_messages(model: ScriptedChatModel, call: int = -1) -> list[ToolMessage]:
    """Return the searches' <sources> messages the model received in a call (the last default)."""
    return [m for m in model.calls[call] if isinstance(m, ToolMessage) and m.name == SEARCH_TOOL]


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


def test_every_call_binds_the_four_tools_and_the_search(index):
    """Each model call gets the five tools' schemas and no forced tool choice before the limit."""
    _, model = _turn(index, tool_reply((TDEE_TOOL, {})), AIMessage(ANSWER))
    for kwargs in model.call_kwargs:
        names = [tool["function"]["name"] for tool in kwargs["tools"]]
        assert sorted(names) == ALL_TOOLS
        assert kwargs["tool_choice"] is None


def test_a_meal_plan_call_runs_and_its_result_reaches_the_model(index):
    """The model calls evaluate_meal_plan from the chat; the totals and gaps come back to it."""
    plan = {"items": [OATS, {"food": "chicken breast", "grams": 200}]}
    result, model = _turn(
        index,
        tool_reply((MEAL_PLAN_TOOL, plan)),
        AIMessage(ANSWER),
        question="How does 80 g of oats and 200 g of chicken breast compare with my targets?",
    )
    assert result.kind == "answer"
    assert [(run.name, run.status) for run in result.tool_runs] == [(MEAL_PLAN_TOOL, "ok")]
    [reply] = _tool_messages(model)
    content = _content(reply)
    assert content["totals"]["kcal"] == 544
    assert [check["gap"] for check in content["comparison"]] == [2491, 96.4, 363.6, 73.7]


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
    assert steps == [Step.CHECK, Step.PLAN, Step.TOOLS, Step.ANSWER, Step.TOOLS, Step.ANSWER]
    assert result.steps == tuple(steps)


def test_a_tool_error_returns_to_the_model_as_a_message(index, monkeypatch, tmp_path):
    """A missing foods table gives the fixed message as the tool result; the turn goes on."""
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "missing.csv")
    # After a search found passages: a failed tool alone is no basis (next test).
    result, model = _turn(
        index, tool_reply((FOOD_TOOL, OATS)), AIMessage(ANSWER), search_first=True
    )
    [reply] = _tool_messages(model)
    assert reply.status == "error"
    assert _content(reply) == {"status": "error", "message": config.TOOL_FAILED_MESSAGE}
    assert (result.kind, result.tool_runs[0].status) == ("answer", "error")


def test_a_failed_tool_alone_is_no_basis(index, monkeypatch, tmp_path):
    """A tool that failed gives no basis: the next reply stays hidden, "not covered" (PR #46)."""
    monkeypatch.setattr(config, "USDA_FOODS_PATH", tmp_path / "missing.csv")
    shown = []
    result, _ = _turn(
        index,
        tool_reply((FOOD_TOOL, OATS)),
        AIMessage("Oats have about 380 kcal per 100 g."),
        question=FOOD_QUESTION,
        on_text=shown.append,
    )
    assert (result.kind, result.text) == ("no_sources", NO_SOURCES)
    assert not [text for text in shown if text]
    assert config.BASIS_TOOL_STATUSES == {"ok", "found", "not_found", "profile_needed"}


def test_profile_needed_is_a_basis_so_the_answer_points_to_the_form(index):
    """With no profile, the answer after "profile needed" is shown with its tool result (T3.5)."""
    result, _ = _turn(
        index, tool_reply((MACRO_TOOL, {})), AIMessage("Add your details."), user=None
    )
    assert (result.kind, result.text) == ("answer", "Add your details.")
    assert [run.status for run in result.tool_runs] == ["profile_needed"]


def test_invalid_arguments_return_to_the_model_as_a_message(index):
    """Arguments that fail the schema come back as the fixed message, and the model answers."""
    result, model = _turn(
        index,
        tool_reply((TDEE_TOOL, {"weight_kg": 50}), (FOOD_TOOL, {"food": "oats"})),
        AIMessage(ANSWER),
        # Refused calls are no basis for an answer: the passages found are (AC-2).
        search_first=True,
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


def test_one_meal_plan_runs_per_reply_and_the_rest_get_the_fixed_message(index):
    """A second meal plan in one reply is refused; the other tools of that reply still run."""
    plan = {"items": [OATS]}
    result, model = _turn(
        index,
        tool_reply((MEAL_PLAN_TOOL, plan), (FOOD_TOOL, OATS), (MEAL_PLAN_TOOL, plan)),
        AIMessage(ANSWER),
    )
    assert config.MAX_MEAL_PLAN_CALLS_PER_ROUND == 1
    assert [(run.name, run.status) for run in result.tool_runs] == [
        (MEAL_PLAN_TOOL, "ok"),
        (FOOD_TOOL, "found"),
        (None, "invalid"),
    ]
    first, food, refused = _tool_messages(model)
    assert refused.tool_call_id == "call-2"
    assert _content(refused)["message"] == config.TOO_MANY_MEAL_PLANS_MESSAGE
    assert config.TOO_MANY_MEAL_PLANS_MESSAGE == (
        "Not run: at most 1 meal plan check is run from one reply."
    )


def test_the_meal_plan_limit_is_per_round(index):
    """A meal plan in each of two rounds runs both times."""
    plan = {"items": [OATS]}
    result, _ = _turn(
        index,
        tool_reply((MEAL_PLAN_TOOL, plan)),
        tool_reply((MEAL_PLAN_TOOL, plan)),
        AIMessage(ANSWER),
    )
    assert [(run.name, run.status) for run in result.tool_runs] == [(MEAL_PLAN_TOOL, "ok")] * 2


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
    result, model = _turn(index, broken, AIMessage(ANSWER), search_first=True)
    [reply] = _tool_messages(model)
    assert reply.tool_call_id == "bad-1"
    assert _content(reply)["message"] == config.INVALID_TOOL_JSON_MESSAGE
    assert result.kind == "answer"


def test_a_cut_off_tool_call_is_not_run(index):
    """A reply cut off by the token limit is an error, and its tool calls never run."""
    cut = tool_reply((FOOD_TOOL, OATS))
    cut.response_metadata = {"finish_reason": "length"}
    # After a search found passages, so the reply is not a hidden one (those end "not covered").
    result, model = _turn(index, cut, search_first=True)
    assert (result.kind, result.text) == ("error", llm.ReplyCutOffError.user_message)
    assert len(model.calls) == 2
    assert result.tool_runs == ()


def test_text_before_tool_calls_is_cleared_from_the_screen(index):
    """Text the model writes in a tool round is cleared before the answer streams in."""
    shown = []
    _turn(
        index,
        tool_reply((TDEE_TOOL, {}), text="Let me check."),
        AIMessage(ANSWER),
        on_text=shown.append,
        # Replies are shown once the answer has a basis: here the passages found.
        search_first=True,
    )
    # The last clearing: the search round before it clears too, with nothing shown yet.
    cleared = len(shown) - 1 - shown[::-1].index("")
    assert shown[cleared - 1] == "Let me check."
    assert shown[-1] == ANSWER


# --- No basis yet: replies stay hidden until a tool runs (owner's choice, B2; AC-2) -------------


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
    assert result.searches == ()
    assert "<sources>" not in _all_text(model)
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


@pytest.mark.parametrize(
    "refused",
    [
        tool_reply(("web_search", {"q": "oats"})),
        AIMessage(
            "",
            invalid_tool_calls=[{"name": FOOD_TOOL, "args": "oats", "id": "bad-1", "error": None}],
            response_metadata={"finish_reason": "tool_calls"},
        ),
        tool_reply((FOOD_TOOL, {"food": "oats", "grams": "a lot"})),
    ],
    ids=["unknown tool", "not JSON", "bad arguments"],
)
def test_with_no_source_a_refused_call_does_not_count_as_a_tool(index, refused):
    """A call that was refused runs no tool, so the next reply stays hidden; no answer is shown."""
    shown = []
    result, model = _turn(
        index,
        refused,
        AIMessage("Oats have about 380 kcal per 100 g."),
        question=FOOD_QUESTION,
        on_text=shown.append,
    )
    assert (result.kind, result.text) == ("no_sources", config.NO_SOURCES_MESSAGE)
    assert len(model.calls) == 2
    assert not [text for text in shown if text]


def test_with_no_source_a_retry_after_a_refused_call_is_shown(index):
    """After a refused call, a tool that really runs makes the next reply the answer."""
    answer = "The app's food lookup gives 304 kcal for 80 g of rolled oats."
    result, _ = _turn(
        index,
        tool_reply(("web_search", {"q": "oats"})),
        tool_reply((FOOD_TOOL, OATS)),
        AIMessage(answer),
        question=FOOD_QUESTION,
    )
    assert (result.kind, result.text) == ("answer", answer)
    assert [run.status for run in result.tool_runs] == ["invalid", "found"]


def test_with_no_source_a_cut_off_hidden_reply_says_not_covered(index):
    """A hidden reply cut off by the token limit ends as "not covered", not as a cut-off error."""
    cut = AIMessage("Oats have", response_metadata={"finish_reason": "length"})
    result, _ = _turn(index, cut, question=FOOD_QUESTION)
    assert (result.kind, result.text) == ("no_sources", config.NO_SOURCES_MESSAGE)


# --- The profile: only the tools have it (T9.3) --------------------------------------------------


def _all_text(model: ScriptedChatModel) -> str:
    """Return the text of every message of every call the model received."""
    return "\n".join(message.text for call in model.calls for message in call)


def test_the_profile_is_never_in_the_models_messages(index):
    """No <profile> block and no profile value in any request; the user message is the question."""
    _, model = _turn(index, AIMessage(ANSWER), search_first=True)
    sent = _all_text(model)
    assert "<profile>" not in sent
    for value in PROFILE_VALUES:
        assert value not in sent
    assert model.calls[0][1].content == f"<user_input>\n{QUESTION}\n</user_input>"


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


def test_an_energy_result_still_names_some_profile_values(index):
    """No <profile>, but tool results name the weight, goal and activity (docs/SECURITY.md)."""
    # Pins the known limit in docs/SECURITY.md: these result fields reach the model when it calls
    # an energy or meal plan tool.
    day = {"items": [OATS, {"food": "chicken breast", "grams": 200}]}
    calls = ((MACRO_TOOL, {}), (TDEE_TOOL, {}), (MEAL_PLAN_TOOL, day))
    _, model = _turn(index, tool_reply(*calls), AIMessage(ANSWER))
    assert "<profile>" not in _all_text(model)
    macro, tdee, meal_plan = (_content(message) for message in _tool_messages(model))
    targets = macro["targets"]
    assert (targets["weight_kg"], targets["goal"]) == (80.0, "build_muscle")
    assert macro["energy_needs"]["activity_factor"] == tdee["activity_factor"] == 1.55
    assert "'Build muscle'" in meal_plan["message"]
    # No tool message has a height, age or sex field, nor the stored height or sex.
    sent = _all_text(model)
    for key in ('"height_cm"', '"age"', '"sex"'):
        assert key not in sent
    assert "180" not in sent and "male" not in sent.casefold()


# --- T9.3: the agent decides whether to search (AC-32, AC-2) -------------------------------------


def test_a_food_question_makes_no_search_and_sends_no_passages(index):
    """Like q14: the model calls the food lookup only; no rewrite, no embedding, no <sources>."""
    answer = "The app's food lookup gives 304 kcal for 80 g of rolled oats."
    translator = ScriptedTranslator()
    result, model = _turn(
        index,
        tool_reply((FOOD_TOOL, OATS)),
        AIMessage(answer),
        question=FOOD_QUESTION,
        translator=translator,
    )
    assert (result.kind, result.text, result.sources) == ("answer", answer, ())
    assert [(run.name, run.status) for run in result.tool_runs] == [(FOOD_TOOL, "found")]
    assert result.searches == ()
    assert translator.calls == []
    assert [call.step for call in result.usage if not call.step.startswith("Answer")] == []
    assert "<sources>" not in _all_text(model) and "[S1]" not in _all_text(model)
    assert Step.SEARCH not in result.steps


def test_a_research_question_searches_and_cites(index):
    """The model searches, gets the passages in a <sources> tool message, and cites [S1]."""
    steps = []
    result, model = _turn(index, AIMessage(ANSWER), search_first=True, on_step=steps.append)
    assert (result.kind, result.text) == ("answer", ANSWER)
    assert [card.labels for card in result.sources] == [("S1",)]
    [search] = result.searches
    assert search.query == QUESTION and search.labels == (1, 2, 3)
    [sources] = _search_messages(model)
    assert sources.name == SEARCH_TOOL
    assert sources.content.startswith("<sources>\n[S1] ")
    assert sources.content.endswith("</sources>")
    assert steps == [Step.CHECK, Step.PLAN, Step.SEARCH, Step.ANSWER]


def test_a_targets_question_may_search_and_use_a_tool(index):
    """One round may search and calculate; the answer cites the passage and has the tool result."""
    both = tool_reply((SEARCH_TOOL, {"query": QUESTION}), (MACRO_TOOL, {}))
    result, model = _turn(index, both, AIMessage(ANSWER))
    assert [card.labels for card in result.sources] == [("S1",)]
    assert [run.name for run in result.tool_runs] == [MACRO_TOOL]
    [sources], [macro] = _search_messages(model), _tool_messages(model)
    assert sources.content.startswith("<sources>\n[S1] ")
    assert _content(macro)["targets"]["kcal_target"] == 3035
    assert len(result.searches) == 1


def test_an_off_topic_search_that_finds_nothing_makes_no_further_call(index):
    """Nothing found and no tool run: "not covered" after the one routing call (AC-2)."""
    shown = []
    plan = plan_json(OFF_TOPIC_REWRITES)
    result, model = _turn(
        index,
        question=OFF_TOPIC_QUESTION,
        plan=plan,
        search_first=True,
        on_text=shown.append,
    )
    assert (result.kind, result.text, result.sources) == ("no_sources", NO_SOURCES, ())
    assert len(model.calls) == 1
    [search] = result.searches
    assert search.labels == () and not search.fell_back
    # The status never says "Writing the answer" when no answer is written.
    assert result.steps == (Step.CHECK, Step.PLAN, Step.SEARCH)
    assert not [text for text in shown if text]


def test_an_off_topic_question_answered_with_no_tool_is_not_shown(index):
    """A first reply that calls nothing has no basis: it is hidden and the turn says not covered."""
    shown = []
    result, model = _turn(
        index,
        AIMessage("Offside is when a player is nearer the goal line."),
        question=OFF_TOPIC_QUESTION,
        on_text=shown.append,
    )
    assert (result.kind, result.text) == ("no_sources", NO_SOURCES)
    assert len(model.calls) == 1 and result.searches == ()
    assert shown == []
    assert result.steps == (Step.CHECK, Step.PLAN)


def test_a_search_that_finds_nothing_beside_a_tool_that_runs_goes_on(index):
    """An empty search with a food lookup in the same round: the answer comes from the lookup."""
    answer = "The app's food lookup gives 304 kcal for 80 g of rolled oats."
    both = tool_reply((SEARCH_TOOL, {"query": OFF_TOPIC_QUESTION}), (FOOD_TOOL, OATS))
    result, model = _turn(
        index, both, AIMessage(answer), question=FOOD_QUESTION, plan=plan_json(OFF_TOPIC_REWRITES)
    )
    assert (result.kind, result.text, result.sources) == ("answer", answer, ())
    [sources] = _search_messages(model)
    assert sources.content == f"<sources>\n{config.NO_SOURCES_BLOCK}\n</sources>"


@pytest.mark.parametrize(
    "reply", ["not JSON at all", plan_json([QUESTION] * 2)], ids=["not JSON", "two rewrites"]
)
def test_with_no_usable_plan_the_search_runs_on_the_query_alone(index, reply):
    """An unusable rewrite reply falls back to the query, unfiltered; the answer still cites."""
    result, _ = _turn(index, AIMessage(ANSWER), plan=reply, search_first=True)
    assert result.kind == "answer"
    [search] = result.searches
    assert search.fell_back and search.rewrites == ()
    assert [card.labels for card in result.sources] == [("S1",)]


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
    messages = chat.build_messages(QUESTION, "Test system prompt.")
    tools = registry.build_tools(PROFILE)
    return chat.answer_with_tools(model, messages, tools, on_step=lambda step: None)


def test_the_real_client_sends_the_tools_and_the_tool_round(no_env_key):
    """ChatOpenAI sends the four tools, then the tool call and its result with matching ids."""
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
    assert html.unescape(_content(reply)["matched_name"]) == HOSTILE_FOOD_NAME


def test_a_usda_name_in_a_meal_plan_reaches_the_model_only_inside_the_tool_message(index):
    """In a meal plan result, the hostile name is in the escaped tool message only (T4.5)."""
    plan = {"items": [{"food": HOSTILE_FOOD_NAME, "grams": 100}]}
    _, model = _turn(index, tool_reply((MEAL_PLAN_TOOL, plan)), AIMessage(ANSWER))
    system, user, *_ = model.calls[-1]
    assert HOSTILE_FOOD_NAME not in system.content + user.content
    [reply] = _tool_messages(model)
    assert "<" not in reply.content and ">" not in reply.content
    assert html.unescape(_content(reply)["items"][0]["matched_name"]) == HOSTILE_FOOD_NAME
