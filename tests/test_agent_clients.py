"""The coach assistant's client tools (T9.17): list_my_clients and get_client_week, AC-21.

The tools run on the test's own temporary store (the made-up world of `tests/store_world.py`, with
canary display names) and, for a whole turn, through `chat.run_turn()` with a scripted model. The
tests check what the store lets through (an active client, the scopes shared), the one "not found"
for every other client, and that no display name or stored user ID reaches a tool result or any
message the model gets: the model knows a client only by the chat's reference (`client-1`).
"""

import json
from datetime import date

import pytest
from langchain_core.messages import AIMessage

from src import chat, config, guard
from src.agent.memory import Conversation
from src.store import db, users
from src.tools import coach_clients, registry
from src.tools.coach_clients import LIST_TOOL, WEEK_TOOL, ClientRefs, CoachClients
from tests import store_world as world
from tests.fakes import (
    PROFILE,
    ScriptedChatModel,
    ScriptedTranslator,
    build_fixture_index,
    open_fixture_index,
    tool_reply,
    write_food_table,
)

TODAY = date(2026, 10, 28)  # in the week of world.DAY (Monday 2026-10-26)
# Display names that appear nowhere else, so a test can look for them where they must not be.
CANARY_NAMES = {
    world.SHARED: "CANARYNAME Shared",
    world.UNSHARED: "CANARYNAME Unshared",
    world.ENDED: "CANARYNAME Ended",
    world.OTHERS: "CANARYNAME Others",
}


@pytest.fixture(autouse=True)
def test_prompt(tmp_path, monkeypatch):
    """Use test prompts and the fixture foods table, so no test depends on the real files."""
    path = tmp_path / "prompt.md"
    path.write_text("Test system prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "ANSWER_PROMPT_PATH", path)
    translation = tmp_path / "translation_prompt.md"
    translation.write_text("Test query translation prompt.", encoding="utf-8")
    monkeypatch.setattr(config, "QUERY_TRANSLATION_PROMPT_PATH", translation)
    monkeypatch.setattr(config, "USDA_FOODS_PATH", write_food_table(tmp_path / "foods.csv"))


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world with canary display names; return the relationship IDs."""
    world_rows = world.build(store_conn)
    rename = "UPDATE users SET display_name = ? WHERE id = ?"
    for user_id, name in CANARY_NAMES.items():
        store_conn.execute(rename, (name, user_id))
    return world_rows


def _clients(refs: ClientRefs | None = None, coach: str = world.COACH_A) -> CoachClients:
    """Return the client tools' session for a coach, on the test's store, today fixed."""
    return CoachClients(
        coach_id=coach, open_store=db.connect, refs=refs or ClientRefs(), today=lambda: TODAY
    )


def _call(clients: CoachClients, name: str, args: dict | None = None):
    """Run one tool call through the registry, as the turn does; return the message and the run."""
    tools = registry.build_tools(None, clients=clients)
    call = {"name": name, "args": args or {}, "id": "call-1", "type": "tool_call"}
    return registry.run_tool_call(tools, call)


def _no_name_or_id(text: str) -> None:
    """Assert that no display name and no stored user ID of the world is in the text."""
    assert "CANARYNAME" not in text
    for user_id in (*world.GYMERS, world.COACH_A, world.COACH_B):
        assert user_id not in text


# --- list_my_clients ----------------------------------------------------------------------------


def test_the_list_holds_the_active_clients_by_reference_only(relationships):
    """Coach A's two active clients, as client-1 and client-2; no name, no user ID (criterion 2)."""
    clients = _clients()
    message, run = _call(clients, LIST_TOOL)
    assert run.status == "ok"
    result = run.result
    assert [item.client for item in result.clients] == ["client-1", "client-2"]
    assert clients.refs.user_id("client-1") == world.SHARED
    assert clients.refs.user_id("client-2") == world.UNSHARED
    assert clients.refs.names() == {
        "client-1": CANARY_NAMES[world.SHARED],
        "client-2": CANARY_NAMES[world.UNSHARED],
    }
    _no_name_or_id(message.content)


def test_the_list_gives_what_each_client_shares(relationships):
    """Logged days and workouts for the scopes shared; null for a scope not shared."""
    _, run = _call(_clients(), LIST_TOOL)
    shared, unshared = run.result.clients
    assert shared.shared_scopes == ["nutrition", "training", "body"]
    assert (shared.logged_days, shared.workouts) == (1, 1)
    assert shared.follow_up_reasons == ["few_logged_days"]  # 1 logged day, a workout
    assert unshared.shared_scopes == []
    assert (unshared.logged_days, unshared.workouts) == (None, None)
    assert unshared.follow_up is False  # nothing shared: nothing to judge


def test_the_references_stay_the_same_for_the_chat(relationships):
    """Listing again keeps each client's reference; a new client gets the next one."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    with db.connect() as conn:
        users.create_user(conn, "gym-new", "gymer", "CANARYNAME New")
        users.start_relationship(conn, world.COACH_A, "gym-new")
    _, run = _call(clients, LIST_TOOL)
    assert [item.client for item in run.result.clients] == ["client-1", "client-2", "client-3"]
    assert clients.refs.user_id("client-3") == "gym-new"


def test_the_list_takes_no_arguments(relationships):
    """Any argument is refused with the fixed message, never repeated."""
    message, run = _call(_clients(), LIST_TOOL, {"client_id": world.OTHERS})
    assert run.status == "invalid"
    assert world.OTHERS not in message.content


def test_another_coach_lists_only_their_own_client(relationships):
    """Coach B's list is their one client, under their own chat's reference."""
    clients = _clients(coach=world.COACH_B)
    _, run = _call(clients, LIST_TOOL)
    assert [item.client for item in run.result.clients] == ["client-1"]
    assert clients.refs.user_id("client-1") == world.OTHERS


# --- get_client_week ----------------------------------------------------------------------------


def test_a_listed_client_s_week_by_reference(relationships):
    """The week's metrics of src/metrics.py, the scopes shared, no name or ID (criteria 1, 2)."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    message, run = _call(clients, WEEK_TOOL, {"client": "client-1"})
    assert run.status == "ok"
    week = run.result
    assert (week.client, week.week_start, week.week_end) == (
        "client-1",
        date(2026, 10, 26),
        date(2026, 11, 1),
    )
    assert week.nutrition.logged_days == 1
    assert week.nutrition.average_over_logged_days.kcal == 571.5
    assert week.nutrition.target.nutrients.kcal == 2345.0
    assert week.body.latest_weight_kg == world.WEIGHT
    assert week.training.sessions == 1
    _no_name_or_id(message.content)
    # Nothing but metrics: no review, question or answer text field in the result.
    assert set(json.loads(message.content)) == {
        "status",
        "message",
        "client",
        "week_start",
        "week_end",
        "shared_scopes",
        "nutrition",
        "body",
        "training",
        "follow_up_reasons",
    }


def test_a_client_sharing_nothing_has_every_section_null(relationships):
    """A client of the coach who shares no scope: the week is read, each section null."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    _, run = _call(clients, WEEK_TOOL, {"client": "client-2"})
    assert (run.result.nutrition, run.result.body, run.result.training) == (None, None, None)


def test_another_week_by_a_day_in_it(relationships):
    """week_of picks the week of that day; a week with nothing logged has 0 logged days."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    _, run = _call(clients, WEEK_TOOL, {"client": "client-1", "week_of": "2026-10-21"})
    assert run.result.week_start == date(2026, 10, 19)
    assert run.result.nutrition.logged_days == 0
    assert all(not day.logged for day in run.result.nutrition.days)


# Every client the coach may not read in this chat gives the same "not found" (AC-21).
NOT_READABLE = {
    "an unknown reference": ("client-9", None),
    "a reference of no client": ("client-1", None),
    "an ended relationship": ("client-1", world.ENDED),
    "another coach's client": ("client-1", world.OTHERS),
    "a missing user": ("client-1", world.MISSING),
    "a coach": ("client-1", world.COACH_B),
    "a stored user ID as the reference": (world.SHARED, None),
}


@pytest.mark.parametrize("case", NOT_READABLE)
def test_every_client_the_coach_may_not_read_is_the_same_not_found(relationships, case):
    """One fixed message, no audit row about anyone (criterion 1, AC-21)."""
    reference, user_id = NOT_READABLE[case]
    refs = ClientRefs()
    if user_id is not None:
        refs.by_reference["client-1"] = (user_id, "CANARYNAME Forged")
    message, run = _call(_clients(refs), WEEK_TOOL, {"client": reference})
    assert run.status == "not_found"
    assert json.loads(message.content) == {
        "status": "not_found",
        "message": config.CLIENT_NOT_FOUND_MESSAGE,
    }
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 0


def test_a_relationship_ended_during_the_chat_is_not_found(relationships):
    """A reference listed earlier stops working once the client ends the relationship."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    with db.connect() as conn:
        users.end_relationship(conn, world.SHARED, relationships[world.SHARED])
    _, run = _call(clients, WEEK_TOOL, {"client": "client-1"})
    assert run.status == "not_found"


def test_a_scope_revoked_during_the_chat_is_left_out(relationships):
    """The next read leaves out a scope the client turned off (AC-22): its section is null."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    with db.connect() as conn:
        users.set_consent(conn, world.SHARED, relationships[world.SHARED], "nutrition", False)
    _, run = _call(clients, WEEK_TOOL, {"client": "client-1"})
    assert run.result.nutrition is None
    assert run.result.shared_scopes == ["training", "body"]


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"client": ""},
        {"client": "client-1", "extra": 1},
        {"client": "c" * (coach_clients.REFERENCE_MAX_CHARS + 1)},
        {"client": "client-1", "week_of": "not a day"},
        {"client": "client-1", "week_of": "2026-10-29"},  # after today
    ],
)
def test_invalid_arguments_get_the_fixed_message(relationships, args):
    """A bad call is refused with one fixed message that repeats nothing the model sent."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    message, run = _call(clients, WEEK_TOOL, args)
    assert run.status == "invalid"
    assert json.loads(message.content)["message"] == config.INVALID_CLIENT_WEEK_MESSAGE


def test_a_reference_is_read_without_case_or_spaces(relationships):
    """ "Client-1 " is client-1: the model may change the case."""
    clients = _clients()
    _call(clients, LIST_TOOL)
    _, run = _call(clients, WEEK_TOOL, {"client": " Client-1 "})
    assert (run.status, run.result.client) == ("ok", "client-1")


def test_a_store_that_fails_gives_the_fixed_tool_failure(relationships):
    """An error opening the store is the tools' one fixed failure, never its text."""

    def broken():
        """Fail to open the store."""
        raise OSError("CANARYNAME /secret/path")

    clients = CoachClients(coach_id=world.COACH_A, open_store=broken, refs=ClientRefs())
    message, run = _call(clients, LIST_TOOL)
    assert run.status == "error"
    assert "CANARYNAME" not in message.content


# --- The page's names in place of references ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "[details](https://x.example/r?c=client-1)",
        "[details](client-1)",
        "https://x.example/client-1",
        "https://x.example/?client-1",
        "<https://x.example/a=client-1>",
        "mail me@client-1",
        # Code review round 2: an angle-bracket target with a space, a URL character that is not
        # a word boundary, a reference-style definition, and www without a scheme.
        "[details](<https://x.example/?n= client-1>)",
        "https://x.example/a;client-1",
        "[r]: https://x.example/?a;client-1",
        "see WWW.x.example/a,client-1",
        "[client-1](https://x.example)",
        # Code review round 3: a reference definition's destination on the next line, with no
        # scheme (a protocol-relative URL).
        "See [details][r].\n[r]:\n//x.example/?n=client-1",
        # Code review round 4: a character that str.splitlines() breaks at but Markdown does
        # not, inside a link destination.
        "[details](https://x.example/?n=\u2028client-1)",
        "[details](https://x.example/?n=\x85client-1)",
    ],
)
def test_no_name_is_put_into_a_line_that_may_hold_a_link(text):
    """A line with a link marker keeps every reference: no name reaches another host."""
    assert coach_clients.name_references(text, {"client-1": "Max"}, str) == text


def test_only_the_line_with_a_link_keeps_its_references():
    """The other lines of the answer still show the name."""
    link = "[more](https://x.example/?c=client-1)"
    text = "\n".join(["client-1 logged 3 days.", link, "Ask client-1 why.", ""])
    shown = coach_clients.name_references(text, {"client-1": "Max"}, str)
    assert shown == "\n".join(["Max logged 3 days.", link, "Ask Max why.", ""])


def test_known_references_become_quoted_names_and_others_stay():
    """Whole references only, any case; an unknown one stays as written."""
    names = {"client-1": "Max_*", "client-2": "Bo"}
    text = "client-1, Client-2, client-12, client-3, subclient-1, client-1x and (client-1)."
    shown = coach_clients.name_references(text, names, lambda name: f"<{name}>")
    assert shown == "<Max_*>, <Bo>, client-12, client-3, subclient-1, client-1x and (<Max_*>)."


# --- A whole coach turn with a scripted model -----------------------------------------------------


@pytest.fixture(scope="module")
def index_path(tmp_path_factory):
    """Build the fixture index once for the module and return its directory."""
    return build_fixture_index(tmp_path_factory.mktemp("index") / "chroma")


def _turn(index_path, clients, *replies, question="Who logged fewer than 4 days this week?"):
    """Run one coach turn with a scripted model; return the result and the model."""
    model = ScriptedChatModel(replies=list(replies), search_first=False)
    result = chat.run_turn(
        question,
        guard.RateLimiter(),
        open_index=lambda: open_fixture_index(index_path),
        chat_model=lambda: model,
        translation_model=lambda: ScriptedTranslator(),
        user=PROFILE,
        conversation=Conversation(),
        clients=clients,
    )
    return result, model


def test_who_logged_fewer_than_4_days_is_answered_from_the_tool_results(relationships, index_path):
    """The model lists the clients, then answers by reference from the result (criterion 3)."""
    clients = _clients()
    answer = "client-1 logged 1 of 7 days this week; client-2 does not share nutrition with you."
    result, model = _turn(index_path, clients, tool_reply((LIST_TOOL, {})), AIMessage(answer))
    assert (result.kind, result.text) == ("answer", answer)
    [run] = result.tool_runs
    assert (run.name, run.status) == (LIST_TOOL, "ok")
    # The second call got the list's result: the logged days the answer rests on.
    [tool_message] = [m for m in model.calls[1] if m.type == "tool"]
    listed = json.loads(tool_message.content)["clients"]
    assert [(item["client"], item["logged_days"]) for item in listed] == [
        ("client-1", 1),
        ("client-2", None),
    ]


def test_no_name_or_user_id_reaches_any_message_of_the_coach_s_chat(relationships, index_path):
    """Every message the model got in a turn that read both tools holds no name and no ID."""
    clients = _clients()
    result, model = _turn(
        index_path,
        clients,
        tool_reply((LIST_TOOL, {})),
        tool_reply((WEEK_TOOL, {"client": "client-1"})),
        AIMessage("client-1 logged one day."),
        question="How did my clients do this week?",
    )
    assert result.kind == "answer"
    for call in model.calls:
        for message in call:
            _no_name_or_id(str(message.content))
    # The tools were offered with their descriptions only: no name there either.
    offered = json.dumps(model.call_kwargs[0]["tools"])
    assert LIST_TOOL in offered and WEEK_TOOL in offered
    _no_name_or_id(offered)


def test_a_guest_turn_is_not_offered_the_client_tools(index_path):
    """Without the coach's session, neither tool is bound and a call to one is unknown."""
    result, model = _turn(
        index_path, None, tool_reply((LIST_TOOL, {})), AIMessage("No."), question="My clients?"
    )
    offered = {tool["function"]["name"] for tool in model.call_kwargs[0]["tools"]}
    assert not {LIST_TOOL, WEEK_TOOL} & offered
    [run] = result.tool_runs
    assert (run.name, run.status) == (None, "invalid")
