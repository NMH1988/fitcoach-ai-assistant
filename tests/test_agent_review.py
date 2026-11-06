"""The weekly review workflow (T9.16, D17): each node and edge, with fake models and a real store.

AC-21, AC-22 (access at every step), AC-27, AC-28 (pending before the pause), AC-29 (decisions),
AC-30 (a model error saves nothing), AC-34 (threads deleted), AC-35 (the checks on edits).
"""

import io
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from src import account, config, llm, observability
from src.agent import review, review_threads
from src.rag.retriever import RetrievedChunk, chunk_key
from src.store import access, my_data, records, reviews, users
from tests import store_world as world
from tests.fakes import ScriptedTranslator

ARCHITECTURE = Path(__file__).resolve().parents[1] / "docs" / "ARCHITECTURE.md"
MONDAY = date(2026, 10, 26)  # world.DAY's week: one meal, one weight, one squat session
TODAY = date(2026, 11, 5)
PROMPT = "STAND-IN REVIEW PROMPT (tests only; the owner writes the real one, O15)."
TRAINING_TEXT = (
    "Made-up text: trained adults in these studies did 10 to 20 sets per muscle group per week."
)


def _draft(**changes) -> str:
    """Return a draft as the model's JSON reply: valid for the world's week unless changed."""
    body = {
        "observations": [{"text": "The client logged 1 of 7 days.", "evidence": []}],
        "hypotheses": [],
        "recommendations": [
            {
                "kind": "nutrition",
                "text": "Log every day next week.",
                "evidence": [],
                "model_suggestion": True,
                "direction": None,
                "source_range": None,
                "population": None,
            }
        ],
    }
    body.update(changes)
    return json.dumps(body)


DIAGNOSIS = _draft(hypotheses=[{"text": "Possible eating disorder.", "evidence": []}])


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def _model(*replies) -> ScriptedTranslator:
    """Return a fake review model that gives the replies in order and records each request."""
    return ScriptedTranslator(plans=list(replies), model_name=config.REVIEW_MODEL)


def _context(model=None, **changes) -> review.ReviewContext:
    """Return a run's context on the test's store, with a fake model and no index."""
    fake = model if model is not None else _model(_draft())
    values = {
        "store_path": config.STORE_PATH,
        "chat_model": lambda: fake,
        "open_index": None,
        "prompt": PROMPT,
        "today": TODAY,
        **changes,
    }
    return review.ReviewContext(**values)


def _start(context, coach=world.COACH_A, client=world.SHARED, monday=MONDAY, language="en"):
    """Start a review run and return its result."""
    return review.start_review(context, coach, client, monday, language)


def _stored(conn):
    """Return every review row as a dict, oldest first."""
    return [dict(row) for row in conn.execute("SELECT * FROM ai_reviews ORDER BY id")]


def _threads() -> set[str]:
    """Return every thread in the test store's checkpointer file."""
    with review_threads.open_saver(config.STORE_PATH) as saver:
        return {c.config["configurable"]["thread_id"] for c in saver.list(None)}


def _revoke(conn, relationships, scope, on=False):
    """Turn a scope off (or on again) for the shared client."""
    users.set_consent(conn, world.SHARED, relationships[world.SHARED], scope, on)


def _pending(conn) -> dict:
    """Return the coach's one pending review of the shared client."""
    [row] = [
        r
        for r in reviews.list_reviews(conn, world.COACH_A, world.SHARED)
        if r["status"] == "PENDING_REVIEW"
    ]
    return row


def test_a_run_saves_a_pending_review_and_waits_for_the_coach(store_conn, relationships):
    """The draft is saved as PENDING_REVIEW with its scopes and thread before the pause (AC-28)."""
    model = _model(_draft())
    result = _start(_context(model))
    assert result.outcome == "pending" and result.errors == ()
    [row] = _stored(store_conn)
    assert (row["id"], row["status"], row["final"]) == (result.review_id, "PENDING_REVIEW", None)
    assert row["model_version"] == config.REVIEW_MODEL
    draft = json.loads(row["draft"])
    assert draft["language"] == "en" and draft["observations"][0]["text"].startswith("The client")
    assert _pending(store_conn)["scopes"] == ["nutrition", "training", "body"]
    assert _threads() == {row["thread_id"]}
    # The draft is on a client from build_chat_model's settings with structured output only.
    assert model.structured_kwargs == [{"method": "json_schema", "include_raw": True}]


def test_the_model_gets_aggregates_for_the_client_and_never_a_name(store_conn, relationships):
    """The messages hold the week's numbers and "the client"; no name, ID or food (AC-26)."""
    model = _model(_draft())
    _start(_context(model))
    [messages] = model.calls
    assert messages[0].content == PROMPT
    text = messages[1].content
    assert "<metrics>" in text and "<sources>" in text and "<language>\nen\n</language>" in text
    assert '"the_client": "the client"' in text
    assert '"logged_days": 1' in text and '"latest_weight_kg": 87.3' in text
    for secret in (world.SHARED, world.COACH_A, "Coach A", "Oats", str(world.HEIGHT)):
        assert secret not in text


def test_a_scope_not_shared_stays_out_of_the_messages_and_the_review(store_conn, relationships):
    """With body off, no weight goes to the model and the review uses nutrition and training."""
    _revoke(store_conn, relationships, "body")
    model = _model(_draft())
    _start(_context(model))
    text = model.calls[0][1].content
    assert '"body"' not in text and "latest_weight_kg" not in text
    assert str(world.WEIGHT) not in text
    assert _pending(store_conn)["scopes"] == ["nutrition", "training"]


@pytest.mark.parametrize(
    ("coach", "client"),
    [
        (world.COACH_A, world.UNSHARED),
        (world.COACH_A, world.ENDED),
        (world.COACH_A, world.OTHERS),
        (world.COACH_A, world.MISSING),
        (world.SHARED, world.SHARED),
        (world.COACH_B, world.SHARED),
    ],
)
def test_authorise_ends_with_not_found_and_calls_no_model(store_conn, relationships, coach, client):
    """No access gives "not found" with no model call, no review and no thread (AC-21)."""
    model = _model(_draft())
    assert _start(_context(model), coach, client).outcome == "not_found"
    assert model.calls == [] and _stored(store_conn) == [] and _threads() == set()


def test_a_week_that_is_not_over_cannot_be_reviewed(store_conn, relationships):
    """The current week (its Sunday not yet past) ends with "not finished", no model call."""
    model = _model(_draft())
    result = _start(_context(model, today=date(2026, 11, 1)))
    assert result.outcome == "not_finished" and model.calls == []
    assert _start(_context(model, today=date(2026, 11, 2))).outcome == "pending"


def test_a_pending_or_approved_week_refuses_a_new_run_and_a_rejected_one_allows_it(
    store_conn, relationships
):
    """A second run of the same week ends with "exists" until the first is rejected."""
    first = _start(_context())
    model = _model(_draft())
    assert _start(_context(model)).outcome == "exists" and model.calls == []
    thread = _pending(store_conn)["thread_id"]
    review.decide_review(_context(), world.COACH_A, first.review_id, thread, "reject")
    assert _start(_context(_model(_draft()))).outcome == "pending"


def test_a_draft_that_fails_once_is_retried_with_the_failed_checks(store_conn, relationships):
    """The retry sends the fixed texts of the failed checks; the second draft is saved."""
    model = _model(DIAGNOSIS, _draft())
    assert _start(_context(model)).outcome == "pending"
    first, second = (call[1].content for call in model.calls)
    assert "<validation_errors>" not in first
    assert "<validation_errors>" in second and "medical condition or diagnosis" in second
    assert "eating disorder" not in second  # the draft's own text is never sent back


@pytest.mark.parametrize(
    "replies",
    [
        (DIAGNOSIS, DIAGNOSIS),
        (llm.InvalidReplyError(diagnostic="x"), llm.InvalidReplyError(diagnostic="x")),
        (llm.ReplyCutOffError(diagnostic="x"), DIAGNOSIS),
    ],
)
def test_two_failed_drafts_end_the_run_with_no_review(store_conn, relationships, replies):
    """After the one retry the run ends: no review, no thread, the failed checks reported."""
    model = _model(*replies)
    result = _start(_context(model))
    assert result.outcome == "invalid" and len(model.calls) == config.REVIEW_MAX_DRAFTS
    assert result.errors
    assert _stored(store_conn) == [] and _threads() == set()


@pytest.mark.parametrize(
    "error",
    [llm.LLMTimeoutError(diagnostic="x"), llm.ServiceUnavailableError(503, diagnostic="x")],
)
def test_a_model_error_saves_no_review_and_loses_no_log_entry(store_conn, relationships, error):
    """A timeout or outage: no review, no thread, the client's logs kept, one line (AC-30)."""
    before = records.list_meal_items(store_conn, world.SHARED, world.SHARED)
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    result = _start(_context(_model(error)))
    assert result.outcome == "error" and result.error_code == error.code
    assert _stored(store_conn) == [] and _threads() == set()
    assert records.list_meal_items(store_conn, world.SHARED, world.SHARED) == before
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [line["event"] for line in lines] == ["llm_error"]
    assert lines[0]["code"] == error.code and lines[0]["kind"] == "weekly_review"


def test_a_missing_key_ends_the_run_with_its_fixed_message(store_conn, relationships):
    """No key: the error outcome with the key's message code, nothing saved."""

    def no_key():
        """Fail as build_chat_model() does without a key."""
        raise config.MissingAPIKeyError(config.MISSING_KEY_MESSAGE)

    result = _start(_context(chat_model=no_key))
    assert (result.outcome, result.error_code) == ("error", "key.missing")
    assert _stored(store_conn) == [] and _threads() == set()


def test_the_run_and_decision_log_lines_hold_no_values(store_conn, relationships):
    """The weekly_review lines carry the outcome, counts and check codes only (AC-33)."""
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    result = _start(_context(_model(DIAGNOSIS, _draft())))
    thread = _pending(store_conn)["thread_id"]
    review.decide_review(_context(), world.COACH_A, result.review_id, thread, "approve")
    text = stream.getvalue()
    lines = [json.loads(line) for line in text.splitlines()]
    assert [(line["event"], line["code"]) for line in lines] == [
        ("weekly_review", "pending"),
        ("weekly_review", "approved"),
    ]
    assert lines[0]["attempts"] == 2 and lines[0]["checks"] == []
    for secret in (world.SHARED, world.COACH_A, "logged 1 of 7", str(world.WEIGHT), "disorder"):
        assert secret not in text


@pytest.mark.parametrize(
    ("decision", "final", "outcome", "status", "edited"),
    [
        ("approve", None, "approved", "APPROVED", False),
        ("reject", None, "rejected", "REJECTED", False),
    ],
)
def test_approve_and_reject_resume_the_run_and_store_the_decision(
    store_conn, relationships, decision, final, outcome, status, edited
):
    """Command(resume=...) stores the decision with an audit row and deletes the thread (AC-29)."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    result = review.decide_review(_context(), world.COACH_A, started.review_id, thread, decision)
    assert result.outcome == outcome
    [row] = _stored(store_conn)
    assert (row["status"], bool(row["edited_by_coach"]), row["reviewed_by"]) == (
        status,
        edited,
        world.COACH_A,
    )
    actions = [r["action"] for r in store_conn.execute("SELECT action FROM audit_log")]
    assert f"review_{'approved' if decision == 'approve' else 'rejected'}" in actions
    assert _threads() == set()
    gymer = reviews.list_reviews(store_conn, world.SHARED, world.SHARED)
    assert [r["id"] for r in gymer] == ([started.review_id] if decision == "approve" else [])


def test_an_edit_that_passes_the_checks_is_released_as_edited(store_conn, relationships):
    """The coach's text is saved as the final review, marked as edited, with the language."""
    started = _start(_context(), language="de")
    thread = _pending(store_conn)["thread_id"]
    edited = json.loads(_draft())
    edited["observations"][0]["text"] = "Nur ein Tag protokolliert."
    result = review.decide_review(
        _context(), world.COACH_A, started.review_id, thread, "edit", edited
    )
    assert result.outcome == "edited"
    [gymer_view] = reviews.list_reviews(store_conn, world.SHARED, world.SHARED)
    assert gymer_view["edited_by_coach"] is True
    assert gymer_view["final"]["observations"][0]["text"] == "Nur ein Tag protokolliert."
    assert gymer_view["final"]["language"] == "de"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"hypotheses": [{"text": "Clear signs of bulimia.", "evidence": []}]}, "diagnosis"),
        ({"observations": []}, "schema"),
    ],
)
def test_an_edit_that_fails_a_check_waits_for_another_decision(
    store_conn, relationships, change, code
):
    """A refused edit stores nothing and the run waits again; an approval then works (AC-35)."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    edited = {**json.loads(_draft()), **change}
    result = review.decide_review(
        _context(), world.COACH_A, started.review_id, thread, "edit", edited
    )
    assert (result.outcome, result.errors) == ("edit_invalid", (code,))
    assert _pending(store_conn)["status"] == "PENDING_REVIEW"
    decisions = "SELECT count(*) FROM audit_log WHERE action <> 'read'"
    assert store_conn.execute(decisions).fetchone()[0] == 0
    again = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert again.outcome == "approved"


@pytest.mark.parametrize("scope", ["nutrition", "training", "body"])
def test_a_scope_revoked_while_the_review_waits_blocks_its_resume(store_conn, relationships, scope):
    """The decision is refused, the review waits; sharing again lets it through (AC-22)."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    _revoke(store_conn, relationships, scope)
    result = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert result.outcome == "not_found"
    [row] = _stored(store_conn)
    assert row["status"] == "PENDING_REVIEW" and _threads() == {thread}
    _revoke(store_conn, relationships, scope, on=True)
    again = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert again.outcome == "approved"


def test_only_the_coach_who_started_the_run_may_resume_it(store_conn, relationships):
    """Another coach gets "not found"; a review ID that is not the thread's gets "gone"."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    other = review.decide_review(_context(), world.COACH_B, started.review_id, thread, "approve")
    assert other.outcome == "not_found"
    wrong = review.decide_review(_context(), world.COACH_A, 999, thread, "approve")
    assert wrong.outcome == "gone"
    missing = review.decide_review(_context(), world.COACH_A, started.review_id, "nope", "approve")
    assert missing.outcome == "gone"
    assert _pending(store_conn)["status"] == "PENDING_REVIEW"


def test_deleting_the_client_deletes_the_waiting_thread(store_conn, relationships):
    """my_data's delete with the threads callback leaves no thread about the client (AC-34)."""
    _start(_context())
    my_data.delete_user_data(
        store_conn,
        world.SHARED,
        lambda threads: review_threads.delete_for_user(config.STORE_PATH, world.SHARED, threads),
    )
    assert _threads() == set()


def _training_chunk() -> RetrievedChunk:
    """Return a made-up training chunk as the index would give it."""
    meta = {
        "source_id": "24",
        "chunk_index": 2,
        "title": "Made-up training review",
        "year": 2021,
        "evidence_tier": 2,
        "topics": [config.TRAINING_TOPIC],
    }
    return RetrievedChunk(TRAINING_TEXT, meta, 0.3)


def test_cited_evidence_is_stored_with_the_review(store_conn, relationships, monkeypatch):
    """A training recommendation citing [S1] passes, and S1's chunk is the stored evidence."""
    chunk = _training_chunk()
    monkeypatch.setattr(review, "_search", lambda context, topics: [chunk])
    training = {
        "kind": "training",
        "text": "Consider more weekly leg work if recovery allows [S1].",
        "evidence": ["S1"],
        "model_suggestion": False,
        "direction": "increase",
        "source_range": "10 to 20 sets per muscle group per week",
        "population": "trained adults",
    }
    model = _model(_draft(recommendations=[training]))
    assert _start(_context(model)).outcome == "pending"
    assert "[S1] Made-up training review" in model.calls[0][1].content
    assert _pending(store_conn)["evidence_refs"] == [
        {"source_id": "24", "chunk_id": chunk_key(chunk)}
    ]


def test_a_citation_of_a_chunk_not_retrieved_is_refused(store_conn, relationships):
    """With no chunk retrieved, a draft citing [S1] fails twice and no review is saved (AC-27)."""
    cited = _draft(observations=[{"text": "The client logged 1 of 7 days.", "evidence": ["S1"]}])
    result = _start(_context(_model(cited, cited)))
    assert result.outcome == "invalid" and "unknown_evidence" in result.errors


def test_search_queries_each_raised_topic_with_its_filter(monkeypatch):
    """One embedding call for the fixed queries; each topic searched with its topic filter."""
    embedded, searched = [], []
    chunks = {
        "protein": [_chunk_for("1", n) for n in range(4)],
        config.TRAINING_TOPIC: [_chunk_for("24", n) for n in range(4)],
    }

    def embed(index, queries, recorder=None):
        """Record the queries and return one vector each."""
        embedded.append(list(queries))
        return [[0.0]] * len(queries)

    def search(index, queries, vectors, where, keyword_index):
        """Record the filter and return that topic's chunks."""
        topic = where["topics"]["$contains"]
        searched.append(topic)
        return chunks[topic]

    monkeypatch.setattr(review, "embed_queries", embed)
    monkeypatch.setattr(review.hybrid, "hybrid_search", search)
    context = _context(open_index=lambda: object())
    found = review._search(context, ("protein", config.TRAINING_TOPIC))
    assert embedded == [
        [
            config.REVIEW_EVIDENCE_QUERIES["protein"],
            config.REVIEW_EVIDENCE_QUERIES["resistance_training"],
        ]
    ]
    assert searched == ["protein", config.TRAINING_TOPIC]
    # Taken in turns, up to the cap: both topics get places.
    assert len(found) == config.REVIEW_MAX_CHUNKS
    assert [c.metadata["source_id"] for c in found[:2]] == ["1", "24"]


def _chunk_for(source_id: str, index: int) -> RetrievedChunk:
    """Return a made-up chunk of a source."""
    return RetrievedChunk(
        f"made-up text {source_id}-{index}",
        {"source_id": source_id, "chunk_index": index, "topics": []},
        0.3,
    )


def test_search_with_no_topic_opens_no_index():
    """When the metrics raise no topic, the index is not opened and nothing is embedded."""

    def refuse():
        """Fail if the index is opened."""
        raise AssertionError("opened")

    assert review._search(_context(open_index=refuse), ()) == []


@pytest.mark.parametrize(
    ("state", "route"),
    [
        ({"errors": []}, "save"),
        ({"errors": ["number"], "attempts": 1}, "draft"),
        ({"errors": ["number"], "attempts": 2}, "invalid"),
    ],
)
def test_after_validate(state, route):
    """Valid: save; failed once: draft again; failed twice: end with no review."""
    assert review.after_validate(state) == route


@pytest.mark.parametrize(
    ("state", "route"),
    [
        ({"decision": None}, "decide"),
        ({"decision": {"decision": "approve", "final": None}}, "release"),
        ({"decision": {"decision": "edit", "final": {}}}, "release"),
        ({"decision": {"decision": "reject", "final": None}}, "reject"),
    ],
)
def test_after_decide(state, route):
    """A refused or unusable answer waits again; approve and edit release; reject rejects."""
    assert review.after_decide(state) == route


@pytest.mark.parametrize(
    ("outcome", "route"),
    [
        ("approved", "__end__"),
        ("edited", "__end__"),
        ("rejected", "__end__"),
        ("not_found", "decide"),
    ],
)
def test_after_decision(outcome, route):
    """A stored decision ends the run; a refusal by the store waits again."""
    assert review.after_decision({"outcome": outcome}) == route


@pytest.mark.parametrize(
    "answer",
    [
        None,
        "approve",
        {"decision": "publish"},
        {"decision": "edit"},
        {"decision": "approve", "final": {}},
    ],
)
def test_an_answer_of_the_wrong_shape_is_no_decision(answer):
    """Only {decision, final} with a final for an edit, and only then, is a decision."""
    assert review._decision(answer) is None


def test_the_graph_has_the_nodes_and_edges_of_d17():
    """authorise, compute, retrieve, draft, validate, save, decide, release, reject (D17)."""
    graph = review._builder().compile().get_graph()
    assert set(graph.nodes) == {
        "__start__",
        "authorise",
        "compute",
        "retrieve",
        "draft",
        "validate",
        "invalid",
        "save",
        "decide",
        "release",
        "reject",
        "__end__",
    }
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert {
        ("__start__", "authorise"),
        ("authorise", "compute"),
        ("authorise", "__end__"),
        ("compute", "retrieve"),
        ("retrieve", "draft"),
        ("draft", "validate"),
        ("validate", "draft"),
        ("validate", "save"),
        ("validate", "invalid"),
        ("save", "decide"),
        ("decide", "release"),
        ("decide", "reject"),
        ("decide", "decide"),
        ("release", "decide"),
        ("release", "__end__"),
        ("reject", "__end__"),
    } <= edges


def test_the_committed_diagram_matches_the_graph():
    """docs/ARCHITECTURE.md shows the Mermaid diagram of the compiled review graph as it is now."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)
    assert review.mermaid() in blocks, (
        "Regenerate the review graph diagram in docs/ARCHITECTURE.md with "
        '`python -c "from src.agent.review import mermaid; print(mermaid())"`.'
    )


def test_a_coach_cannot_read_a_review_through_another_coachs_thread(store_conn, relationships):
    """The store still decides: a resumed run with the wrong coach never reaches decide_review."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    with pytest.raises(access.NotFound):
        reviews.decide_review(store_conn, world.COACH_B, started.review_id, "approve")
    other = review.decide_review(_context(), world.COACH_B, started.review_id, thread, "reject")
    assert other.outcome == "not_found"
    assert _pending(store_conn)["status"] == "PENDING_REVIEW"


class _FailingOnce:
    """Make a store function raise StoreUnavailable on its first call, then work as before."""

    def __init__(self, function):
        """Keep the function to call after the first failure."""
        self.function = function
        self.failed = False

    def __call__(self, *args, **kwargs):
        """Fail once, then call the real function."""
        if not self.failed:
            self.failed = True
            raise account.StoreUnavailable
        return self.function(*args, **kwargs)


def test_a_decision_stuck_after_a_store_failure_is_finished_next_time(
    store_conn, relationships, monkeypatch
):
    """Approve fails in the store once; the next click finishes it instead of "gone"."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    monkeypatch.setattr(review.reviews, "decide_review", _FailingOnce(reviews.decide_review))
    with pytest.raises(account.StoreUnavailable):
        review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert _pending(store_conn)["status"] == "PENDING_REVIEW" and _threads() == {thread}
    again = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert again.outcome == "approved" and _threads() == set()


def test_a_review_saved_by_a_run_that_then_failed_is_discarded(
    store_conn, relationships, monkeypatch
):
    """The review is saved, then the run fails: no pending review is left and the week reruns."""

    def failing_save(state, runtime):
        """Save the review as the node does, then fail as a lost checkpoint write would."""
        review.save(state, runtime)
        raise RuntimeError("checkpoint write failed")

    builder, graph_of = review._builder, review.review_graph

    def patched():
        """Return the graph builder with the failing save node."""
        found = builder()
        found.nodes["save"].runnable = failing_save  # type: ignore[attr-defined]
        return found

    monkeypatch.setattr(review, "_builder", patched)
    monkeypatch.setattr(
        review,
        "review_graph",
        lambda saver: patched().compile(checkpointer=saver),
    )
    with pytest.raises(RuntimeError):
        _start(_context())
    assert _stored(store_conn) == [] and _threads() == set()
    # Put back only these two: monkeypatch.undo() would also undo the fixture that points the
    # store at a temporary file, and the next run would open the real data/store/ file.
    monkeypatch.setattr(review, "_builder", builder)
    monkeypatch.setattr(review, "review_graph", graph_of)
    assert _start(_context()).outcome == "pending"


def test_a_pending_review_with_no_run_can_be_rejected_but_not_approved(store_conn, relationships):
    """With its thread lost, Approve and Edit say "gone"; Reject decides it in the store."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    with review_threads.open_saver(config.STORE_PATH) as saver:
        review_threads.delete_threads(saver, [thread])
    approve = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert approve.outcome == "gone"
    other = review.decide_review(_context(), world.COACH_B, started.review_id, thread, "reject")
    assert other.outcome == "not_found"
    reject = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "reject")
    assert reject.outcome == "rejected"
    assert _start(_context()).outcome == "pending"  # the week can be drafted again


def test_a_review_decided_in_another_tab_ends_its_run(store_conn, relationships):
    """Decided outside the run (another tab), the run's resume ends with "gone", thread deleted."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    reviews.decide_review(store_conn, world.COACH_A, started.review_id, "reject")
    result = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    assert result.outcome == "gone" and _threads() == set()
    [row] = _stored(store_conn)
    assert row["status"] == "REJECTED"


def test_a_threads_file_that_cannot_be_used_gives_the_store_s_fixed_error(monkeypatch):
    """An error of the threads file is StoreUnavailable, with the class name logged only."""

    def locked(*args, **kwargs):
        """Fail as a file locked past the busy timeout does."""
        raise sqlite3.OperationalError("database is locked: C:/secret/path")

    monkeypatch.setattr(review_threads.sqlite3, "connect", locked)
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    with pytest.raises(account.StoreUnavailable) as caught:
        _start(_context())
    # As account.open_store(): the fixed message, the OS error's text never shown or chained.
    assert caught.value.__suppress_context__ and "secret" not in str(caught.value)
    [line] = [json.loads(text) for text in stream.getvalue().splitlines()]
    assert (line["event"], line["code"]) == ("store_unavailable", "OperationalError")
    assert "secret" not in stream.getvalue()


def test_a_stuck_decision_takes_the_coach_s_new_click(store_conn, relationships, monkeypatch):
    """Approve fails in the store once; Reject then rejects: the client never reads the draft."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    monkeypatch.setattr(review.reviews, "decide_review", _FailingOnce(reviews.decide_review))
    with pytest.raises(account.StoreUnavailable):
        review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    result = review.decide_review(_context(), world.COACH_A, started.review_id, thread, "reject")
    assert result.outcome == "rejected" and _threads() == set()
    assert reviews.list_reviews(store_conn, world.SHARED, world.SHARED) == []


def test_a_stuck_decision_replaced_by_an_edit_runs_the_edit_s_checks(
    store_conn, relationships, monkeypatch
):
    """A refused edit leaves the stuck run as it was; a clean edit then replaces the approval."""
    started = _start(_context())
    thread = _pending(store_conn)["thread_id"]
    monkeypatch.setattr(review.reviews, "decide_review", _FailingOnce(reviews.decide_review))
    with pytest.raises(account.StoreUnavailable):
        review.decide_review(_context(), world.COACH_A, started.review_id, thread, "approve")
    bad = {**json.loads(_draft()), "hypotheses": [{"text": "Diabetes.", "evidence": []}]}
    stream = io.StringIO()
    observability.configure_logging(stream=stream)
    refused = review.decide_review(
        _context(), world.COACH_A, started.review_id, thread, "edit", bad
    )
    assert (refused.outcome, refused.errors) == ("edit_invalid", ("diagnosis",))
    # The refusal is logged by its codes only, as at the decide node (code review round 4).
    [line] = [json.loads(text) for text in stream.getvalue().splitlines()]
    assert (line["event"], line["code"], line["checks"]) == (
        "weekly_review",
        "edit_invalid",
        ["diagnosis"],
    )
    assert "Diabetes" not in stream.getvalue()
    good = json.loads(_draft())
    good["observations"][0]["text"] = "One day logged."
    edited = review.decide_review(
        _context(), world.COACH_A, started.review_id, thread, "edit", good
    )
    assert edited.outcome == "edited"
    [seen] = reviews.list_reviews(store_conn, world.SHARED, world.SHARED)
    assert seen["final"]["observations"][0]["text"] == "One day logged."
