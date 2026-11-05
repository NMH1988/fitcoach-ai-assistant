"""A review's scopes and week in the store (T9.16): each one used must stay shared (AC-22)."""

import json
from datetime import date

import pytest

from src.store import access, my_data, reviews, users, values
from tests import store_world as world

WEEK = date(2026, 10, 19)
ALL = ("nutrition", "training", "body")


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def _save(conn, scopes=ALL, week=WEEK, coach=world.COACH_A, client=world.SHARED, thread_id=None):
    """Save a pending review that used the scopes and return its ID."""
    return reviews.save_review(
        conn,
        coach,
        client,
        period_start=week,
        metrics={"logged_days": 3},
        data_quality={},
        draft={"observations": ["CANARY-DRAFT"]},
        model_version="m",
        evidence_refs=[("12", "12-3")],
        scopes=scopes,
        thread_id=thread_id,
    )


def _revoke(conn, relationships, scope):
    """Turn the scope off for the shared client."""
    users.set_consent(conn, world.SHARED, relationships[world.SHARED], scope, False)


def _audit_count(conn):
    """Return how many audit rows there are."""
    return conn.execute("SELECT count(*) FROM audit_log").fetchone()[0]


def _export(conn, user_id):
    """Return a user's export as a dict."""
    return json.loads(my_data.export_user_data(conn, user_id))


def test_a_review_stores_its_scopes_and_thread(store_conn, relationships):
    """The coach's lists show the scopes in a fixed order and the thread; the gymer's no thread."""
    review_id = _save(store_conn, scopes=["body", "nutrition"], thread_id="review-abc")
    [mine] = reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)
    assert mine["scopes"] == ["nutrition", "body"]
    assert mine["thread_id"] == "review-abc"
    reviews.decide_review(store_conn, world.COACH_A, review_id, "approve")
    [theirs] = reviews.list_reviews(store_conn, world.SHARED, world.SHARED)
    assert theirs["thread_id"] is None and theirs["scopes"] == ["nutrition", "body"]
    assert "review-abc" not in my_data.export_user_data(store_conn, world.SHARED)


@pytest.mark.parametrize(
    "scopes", [(), ("training",), ("body", "training"), ("nutrition", "lunch"), "nutrition", None]
)
def test_a_review_without_nutrition_or_with_an_unknown_scope_is_refused(
    store_conn, relationships, scopes
):
    """Every review uses nutrition; a scope must be one of the three; nothing is saved."""
    with pytest.raises(values.StoreValueError):
        _save(store_conn, scopes=scopes)
    assert store_conn.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 0


@pytest.mark.parametrize("scope", ALL)
def test_a_scope_not_shared_blocks_the_save(store_conn, relationships, scope):
    """Saving a review that used a scope the client no longer shares gives NotFound, no row."""
    _revoke(store_conn, relationships, scope)
    with pytest.raises(access.NotFound):
        _save(store_conn)
    assert store_conn.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 0


@pytest.mark.parametrize("scope", ALL)
def test_revoking_a_used_scope_blocks_the_decision(store_conn, relationships, scope):
    """A pending review cannot be decided once any scope it used is off; no audit row (AC-22)."""
    review_id = _save(store_conn)
    _revoke(store_conn, relationships, scope)
    for decision, final in (("approve", None), ("edit", {"x": "y"}), ("reject", None)):
        with pytest.raises(access.NotFound):
            reviews.decide_review(store_conn, world.COACH_A, review_id, decision, final)
    assert _audit_count(store_conn) == 0
    [status] = store_conn.execute("SELECT status FROM ai_reviews").fetchone()
    assert status == "PENDING_REVIEW"


@pytest.mark.parametrize("scope", ALL)
def test_revoking_a_used_scope_hides_the_review_from_the_coachs_read_of_the_client(
    store_conn, relationships, scope
):
    """The coach's read of the client lists no review that used the revoked scope."""
    _save(store_conn)
    _revoke(store_conn, relationships, scope)
    if scope == "nutrition":
        with pytest.raises(access.NotFound):
            reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)
    else:
        assert reviews.list_reviews(store_conn, world.COACH_A, world.SHARED) == []


@pytest.mark.parametrize("scope", ALL)
def test_revoking_a_used_scope_hides_the_review_from_the_coachs_own_list(
    store_conn, relationships, scope
):
    """The coach's own list holds no review that used the revoked scope, and audits nothing."""
    _save(store_conn)
    _revoke(store_conn, relationships, scope)
    assert reviews.list_reviews(store_conn, world.COACH_A, world.COACH_A) == []
    assert _audit_count(store_conn) == 0


@pytest.mark.parametrize("scope", ALL)
def test_revoking_a_used_scope_keeps_the_review_out_of_the_coachs_export(
    store_conn, relationships, scope
):
    """The coach's export holds neither the review, its evidence nor its scopes, and audits none."""
    _save(store_conn)
    _revoke(store_conn, relationships, scope)
    document = _export(store_conn, world.COACH_A)
    assert document["ai_reviews"] == []
    assert document["ai_evidence_refs"] == []
    assert document["ai_review_scopes"] == []
    assert "CANARY-DRAFT" not in json.dumps(document)
    assert _audit_count(store_conn) == 0


@pytest.mark.parametrize("scope", ["training", "body"])
def test_revoking_a_scope_the_review_did_not_use_changes_nothing(store_conn, relationships, scope):
    """A nutrition-only review stays readable, exportable and decidable when another scope goes."""
    review_id = _save(store_conn, scopes=("nutrition",))
    _revoke(store_conn, relationships, scope)
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.COACH_A, world.SHARED)] == [
        review_id
    ]
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.COACH_A, world.COACH_A)] == [
        review_id
    ]
    document = _export(store_conn, world.COACH_A)
    assert [r["id"] for r in document["ai_reviews"]] == [review_id]
    assert document["ai_review_scopes"] == [{"review_id": review_id, "scope": "nutrition"}]
    reviews.decide_review(store_conn, world.COACH_A, review_id, "approve")


def test_the_gymer_still_reads_an_approved_review_after_a_revoke(store_conn, relationships):
    """The scopes govern the coach's reads; the approved review stays the gymer's to read."""
    review_id = _save(store_conn)
    reviews.decide_review(store_conn, world.COACH_A, review_id, "approve")
    _revoke(store_conn, relationships, "training")
    assert [r["id"] for r in reviews.list_reviews(store_conn, world.SHARED, world.SHARED)] == [
        review_id
    ]
    assert [r["review_id"] for r in _export(store_conn, world.SHARED)["ai_review_scopes"]] == [
        review_id
    ] * 3


@pytest.mark.parametrize("decision", ["approve", None])
def test_a_pending_or_approved_review_of_the_week_blocks_another(
    store_conn, relationships, decision
):
    """While the week's review is pending or approved, saving or preparing another is refused."""
    review_id = _save(store_conn)
    if decision is not None:
        reviews.decide_review(store_conn, world.COACH_A, review_id, decision)
    with pytest.raises(reviews.ReviewExists):
        _save(store_conn)
    with pytest.raises(reviews.ReviewExists):
        reviews.prepare_review(store_conn, world.COACH_A, world.SHARED, WEEK)
    assert store_conn.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 1


def test_a_rejected_review_may_be_run_again(store_conn, relationships):
    """After a rejection, the same week can be prepared and saved again."""
    review_id = _save(store_conn)
    reviews.decide_review(store_conn, world.COACH_A, review_id, "reject")
    assert reviews.prepare_review(store_conn, world.COACH_A, world.SHARED, WEEK) == ALL
    _save(store_conn)


def test_another_week_or_another_coachs_review_does_not_block(store_conn, relationships):
    """The refusal is per coach, client and week."""
    _save(store_conn)
    _save(store_conn, week=date(2026, 10, 26))
    _save(store_conn, coach=world.COACH_B, client=world.OTHERS)


def test_prepare_returns_the_scopes_the_client_shares_now(store_conn, relationships):
    """With body turned off, a new review may use nutrition and training only."""
    _revoke(store_conn, relationships, "body")
    scopes = reviews.prepare_review(store_conn, world.COACH_A, world.SHARED, WEEK)
    assert scopes == ("nutrition", "training")
    assert _audit_count(store_conn) == 0  # nothing of the client's records was read


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
        (world.MISSING, world.SHARED),
        (None, world.SHARED),
    ],
)
def test_prepare_refuses_without_nutrition_access(store_conn, relationships, coach, client):
    """No access, another coach's client, a gymer or the coach themself all get NotFound."""
    with pytest.raises(access.NotFound):
        reviews.prepare_review(store_conn, coach, client, WEEK)
    assert _audit_count(store_conn) == 0


def test_prepare_refuses_after_nutrition_is_revoked(store_conn, relationships):
    """Without nutrition, a review cannot start even if training and body are shared."""
    _revoke(store_conn, relationships, "nutrition")
    with pytest.raises(access.NotFound):
        reviews.prepare_review(store_conn, world.COACH_A, world.SHARED, WEEK)


def test_delete_hands_the_threads_of_the_users_reviews_to_the_callback(store_conn, relationships):
    """Deleting a gymer passes the threads of the reviews about them, and only those."""
    _save(store_conn, thread_id="about-shared")
    _save(store_conn, coach=world.COACH_B, client=world.OTHERS, thread_id="about-others")
    deleted = []
    my_data.delete_user_data(store_conn, world.SHARED, deleted.extend)
    assert deleted == ["about-shared"]
    assert store_conn.execute("SELECT count(*) FROM ai_review_scopes").fetchone()[0] == 3


def test_delete_hands_a_coachs_threads_to_the_callback(store_conn, relationships):
    """Deleting a coach passes the threads of the reviews they started."""
    _save(store_conn, thread_id="by-a")
    _save(store_conn, coach=world.COACH_B, client=world.OTHERS, thread_id="by-b")
    deleted = []
    my_data.delete_user_data(store_conn, world.COACH_A, deleted.extend)
    assert deleted == ["by-a"]


def test_a_failing_thread_delete_deletes_nothing(store_conn, relationships):
    """If the threads cannot be deleted, the store rolls back and the user is still there."""
    _save(store_conn, thread_id="about-shared")

    def refuse(_threads):
        """Fail as a locked checkpointer file would."""
        raise OSError("locked")

    with pytest.raises(OSError):
        my_data.delete_user_data(store_conn, world.SHARED, refuse)
    assert access.role_of(store_conn, world.SHARED) == "gymer"
    assert store_conn.execute("SELECT count(*) FROM ai_review_scopes").fetchone()[0] == 3
