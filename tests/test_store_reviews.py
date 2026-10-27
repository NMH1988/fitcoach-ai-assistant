"""Weekly reviews in the store (T9.6): who saves and decides them, the audit, who reads them."""

import json
from datetime import date

import pytest

from src.store import access, my_data, reviews, users, values
from tests import store_world as world

WEEK = date(2026, 10, 19)
METRICS = {"logged_days": 3, "avg_kcal": 2210.5}
DRAFT = {"observations": ["CANARY-DRAFT logged 3 of 7 days"]}


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def _save(conn, coach=world.COACH_A, client=world.SHARED):
    """Save a pending review of the test week and return its ID."""
    return reviews.save_review(
        conn,
        coach,
        client,
        period_start=WEEK,
        metrics=METRICS,
        data_quality={"logged_days": 3},
        draft=DRAFT,
        model_version="openai/gpt-5-mini",
        evidence_refs=[("12", "12-3"), ("8", "8-1")],
    )


def _audit_rows(conn):
    """Return every audit row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


def test_a_saved_review_starts_pending_with_its_evidence(store_conn, relationships):
    """The coach's own list shows the review as PENDING_REVIEW, with no final text or reviewer."""
    review_id = _save(store_conn)
    assert _audit_rows(store_conn) == []  # saving is not a read
    [review] = reviews.list_reviews(store_conn, world.COACH_A, world.COACH_A)
    assert review["id"] == review_id
    assert review["status"] == "PENDING_REVIEW"
    assert (review["final"], review["reviewed_by"], review["reviewed_at"]) == (None, None, None)
    assert review["metrics"] == METRICS and review["draft"] == DRAFT
    assert review["evidence_refs"] == [
        {"source_id": "12", "chunk_id": "12-3"},
        {"source_id": "8", "chunk_id": "8-1"},
    ]
    # The coach's own list reads client data: one audit row for the one client in it.
    [row] = _audit_rows(store_conn)
    assert (row["actor_id"], row["subject_id"], row["action"]) == (
        world.COACH_A,
        world.SHARED,
        "read",
    )


@pytest.mark.parametrize(
    ("coach", "client"),
    [
        (world.COACH_A, world.UNSHARED),
        (world.COACH_A, world.ENDED),
        (world.COACH_A, world.OTHERS),
        (world.COACH_A, world.MISSING),
        (world.COACH_A, world.COACH_A),
        (world.SHARED, world.SHARED),
        (world.UNSHARED, world.SHARED),
    ],
)
def test_a_review_is_saved_only_for_a_client_sharing_nutrition(
    store_conn, relationships, coach, client
):
    """Without an active relationship and the nutrition scope, saving gives NotFound and no row."""
    with pytest.raises(access.NotFound):
        _save(store_conn, coach, client)
    assert store_conn.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("decision", "final", "status", "action", "edited"),
    [
        ("approve", None, "APPROVED", "review_approved", False),
        ("edit", {"observations": ["CANARY-EDIT"]}, "APPROVED", "review_edited", True),
        ("reject", None, "REJECTED", "review_rejected", False),
    ],
)
def test_each_decision_stores_the_reviewer_the_time_and_an_audit_row(
    store_conn, relationships, decision, final, status, action, edited
):
    """Approve, edit and reject store who and when, and write one audit row with no values."""
    review_id = _save(store_conn)
    reviews.decide_review(store_conn, world.COACH_A, review_id, decision, final)
    [row] = _audit_rows(store_conn)
    [review] = reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)
    assert review["status"] == status
    assert review["reviewed_by"] == world.COACH_A
    assert review["reviewed_at"].endswith("+00:00")
    assert review["edited_by_coach"] is edited
    assert review["final"] == {"approve": DRAFT, "edit": final, "reject": None}[decision]
    assert (row["actor_id"], row["subject_id"], row["action"]) == (
        world.COACH_A,
        world.SHARED,
        action,
    )
    assert (row["resource_type"], row["resource_id"]) == ("ai_reviews", review_id)
    assert "CANARY" not in str(row)


def test_only_an_approved_review_reaches_the_gymer(store_conn, relationships):
    """The gymer's own list holds the approved review only, never a pending or rejected one."""
    pending = _save(store_conn)
    rejected = _save(store_conn)
    approved = _save(store_conn)
    reviews.decide_review(store_conn, world.COACH_A, rejected, "reject")
    reviews.decide_review(store_conn, world.COACH_A, approved, "approve")
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.SHARED, world.SHARED)] == [
        approved
    ]
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)] == [
        pending,
        rejected,
        approved,
    ]


def test_a_coach_reading_a_client_sees_only_their_own_reviews_of_that_client(
    store_conn, relationships
):
    """Coach B's review of their own client never shows up in coach A's read of coach A's client."""
    mine = _save(store_conn)
    _save(store_conn, world.COACH_B, world.OTHERS)
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)] == [
        mine
    ]
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.COACH_A, world.COACH_A)] == [
        mine
    ]


def test_revoking_nutrition_blocks_a_pending_review(store_conn, relationships):
    """A review saved before the client turned nutrition off cannot be decided (AC-22)."""
    review_id = _save(store_conn)
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], "nutrition", False)
    for decision in ("approve", "reject"):
        with pytest.raises(access.NotFound):
            reviews.decide_review(store_conn, world.COACH_A, review_id, decision)
    assert _audit_rows(store_conn) == []
    [status] = store_conn.execute("SELECT status FROM ai_reviews").fetchone()
    assert status == "PENDING_REVIEW"


def test_ending_the_relationship_blocks_a_pending_review(store_conn, relationships):
    """A review cannot be decided once the relationship has ended."""
    review_id = _save(store_conn)
    users.end_relationship(store_conn, world.SHARED, relationships[world.SHARED])
    with pytest.raises(access.NotFound):
        reviews.decide_review(store_conn, world.COACH_A, review_id, "approve")


@pytest.mark.parametrize("actor", [world.COACH_B, world.SHARED, world.MISSING])
def test_only_the_coach_who_wrote_it_decides_a_review(store_conn, relationships, actor):
    """Another coach, the client or a missing user gets NotFound."""
    review_id = _save(store_conn)
    with pytest.raises(access.NotFound):
        reviews.decide_review(store_conn, actor, review_id, "approve")


def test_a_review_is_decided_once(store_conn, relationships):
    """A decided review, or a review ID that does not exist, gives NotFound."""
    review_id = _save(store_conn)
    reviews.decide_review(store_conn, world.COACH_A, review_id, "approve")
    for target in (review_id, 999, None, "1", 0, 2**64):
        with pytest.raises(access.NotFound):
            reviews.decide_review(store_conn, world.COACH_A, target, "reject")
    assert len(_audit_rows(store_conn)) == 1


@pytest.mark.parametrize(
    ("decision", "final"),
    [
        ("edit", None),
        ("approve", {"x": 1}),
        ("reject", {"x": 1}),
        ("publish", None),
        ("edit", {"x": float("nan")}),
    ],
)
def test_a_decision_with_the_wrong_final_text_is_refused(
    store_conn, relationships, decision, final
):
    """Only an edit carries a final text, it must be JSON, and the decision must be known."""
    review_id = _save(store_conn)
    with pytest.raises(values.StoreValueError):
        reviews.decide_review(store_conn, world.COACH_A, review_id, decision, final)


@pytest.mark.parametrize("bad", [[1, 2], {"x": object()}, {"x": float("inf")}, "{}"])
def test_review_fields_must_be_json_mappings(store_conn, relationships, bad):
    """metrics, data quality and the draft are JSON objects; anything else is refused."""
    with pytest.raises(values.StoreValueError):
        reviews.save_review(
            store_conn,
            world.COACH_A,
            world.SHARED,
            period_start=WEEK,
            metrics=bad,
            data_quality={},
            draft={},
            model_version="m",
        )


@pytest.mark.parametrize("change", ["revoke nutrition", "end the relationship"])
def test_a_coachs_own_list_and_export_hide_a_client_no_longer_sharing(
    store_conn, relationships, change
):
    """After a revoke or an end, the coach's own list and export hold no review of that client."""
    _save(store_conn)
    rel = relationships[world.SHARED]
    if change == "revoke nutrition":
        users.set_consent(store_conn, world.SHARED, rel, "nutrition", False)
    else:
        users.end_relationship(store_conn, world.SHARED, rel)
    assert reviews.list_reviews(store_conn, world.COACH_A, world.COACH_A) == []
    assert _audit_rows(store_conn) == []
    document = json.loads(my_data.export_user_data(store_conn, world.COACH_A))
    assert document["ai_reviews"] == [] and document["ai_evidence_refs"] == []
    assert "CANARY-DRAFT" not in json.dumps(document)
    # The export read nothing about the client, so it audited nothing either.
    assert _audit_rows(store_conn) == []


def test_an_edited_draft_never_reaches_the_gymer(store_conn, relationships):
    """The model's draft that the coach replaced is in neither the gymer's list nor their export."""
    review_id = _save(store_conn)
    reviews.decide_review(store_conn, world.COACH_A, review_id, "edit", {"text": "coach's text"})
    [review] = reviews.list_reviews(store_conn, world.SHARED, world.SHARED)
    assert review["draft"] is None and review["final"] == {"text": "coach's text"}
    export = my_data.export_user_data(store_conn, world.SHARED)
    assert "CANARY-DRAFT" not in export and "coach's text" in export
