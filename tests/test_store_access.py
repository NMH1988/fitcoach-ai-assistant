"""Who may read whose data (T9.6, D16): cross-client tests for every read function (AC-21, AC-22).

Every read function takes the acting user and the user whose data it reads. A user reads their own
data; a coach reads a gymer's only while the relationship is active and the scope is shared; every
other case raises the same `NotFound` and writes no audit row. A coach's allowed read writes one
audit row with no values.
"""

import importlib
import inspect
from pathlib import Path

import pytest

from src.store import access, records, reviews, users
from tests import store_world as world

STORE = Path(__file__).resolve().parents[1] / "src" / "store"

# Every read function of the store, with the scope its data belongs to (None: never shared).
READS = {
    "list_profile_entries": (records.list_profile_entries, "body"),
    "list_body_measurements": (records.list_body_measurements, "body"),
    "list_targets": (records.list_targets, "nutrition"),
    "list_meal_items": (records.list_meal_items, "nutrition"),
    "list_workout_sessions": (records.list_workout_sessions, "training"),
    "list_preferences": (records.list_preferences, None),
    "list_reviews": (reviews.list_reviews, "nutrition"),
}
# (actor, subject) pairs that must give NotFound for every read function.
REFUSED = {
    "a missing user": (world.COACH_A, world.MISSING),
    "another coach's client": (world.COACH_A, world.OTHERS),
    "an ended relationship": (world.COACH_A, world.ENDED),
    "a client sharing nothing": (world.COACH_A, world.UNSHARED),
    "a coach reading a coach": (world.COACH_B, world.COACH_A),
    "a gymer reading a gymer": (world.UNSHARED, world.SHARED),
    "a gymer reading their coach": (world.SHARED, world.COACH_A),
    "a missing actor": (world.MISSING, world.SHARED),
    "an actor ID that is not text": (None, world.SHARED),
    "a subject ID that is not text": (world.COACH_A, 5),
}


@pytest.fixture
def relationships(store_conn):
    """Build the made-up world in the test's store and return its relationship IDs."""
    return world.build(store_conn)


def _audit_rows(conn):
    """Return every audit row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


# Every other public function of the store, by how it is protected. A new function must be put in
# one of these groups (or in READS), so none escapes a review of who may call it.
OWN_ONLY = {
    # The acting user's own data only; the caller passes the signed-in user (T9.5).
    "users.find_user",
    "records.delete_record",
    "my_data.export_user_data",
    "my_data.delete_user_data",
}
WRITES = {
    # Each checks that the change is the acting user's to make (tested in this file and beside it).
    "users.create_user",
    "users.start_relationship",
    "users.set_consent",
    "users.end_relationship",
    "records.add_profile_entry",
    "records.add_body_measurement",
    "records.add_target",
    "records.add_meal_item",
    "records.add_workout_session",
    "records.add_preference",
    "reviews.save_review",
    "reviews.decide_review",
}
INTERNALS = {
    # No user data in or out: opening the file, checks, and the access layer itself.
    "db.connect",
    "db.migrate",
    "db.schema_version",
    "db.transaction",
    "access.audit",
    "access.authorise_read",
    "access.authorised_read",
    "access.role_of",
    *(f"values.{name}" for name in ("choice", "date_text", "in_range", "number", "text")),
    *(f"values.{name}" for name in ("user_id", "utc_text", "whole_number")),
}


def test_every_public_store_function_is_classified():
    """Every public function in src/store/ is a tested read, own-only, a write or an internal."""
    found = set()
    for path in sorted(STORE.rglob("*.py")):
        module = importlib.import_module("src.store." + path.stem)
        found |= {
            f"{path.stem}.{name}"
            for name, value in vars(module).items()
            if inspect.isfunction(value)
            and value.__module__ == module.__name__
            and not name.startswith("_")
        }
    reads = {f"{READS[name][0].__module__.rsplit('.', 1)[1]}.{name}" for name in READS}
    groups = [reads, OWN_ONLY, WRITES, INTERNALS]
    assert found == set().union(*groups)
    assert sum(len(group) for group in groups) == len(found)  # no function in two groups


@pytest.mark.parametrize("read", READS)
@pytest.mark.parametrize("case", REFUSED)
def test_every_refused_read_gives_the_same_not_found_and_no_audit(
    store_conn, relationships, read, case
):
    """A missing, foreign, ended or unshared resource, or a wrong role, gives one NotFound."""
    function, _ = READS[read]
    actor, subject = REFUSED[case]
    with pytest.raises(access.NotFound) as caught:
        function(store_conn, actor, subject)
    assert type(caught.value) is access.NotFound
    assert str(caught.value) == "not found"
    assert _audit_rows(store_conn) == []


@pytest.mark.parametrize("read", [name for name, (_, scope) in READS.items() if scope])
def test_a_scope_not_shared_is_refused_while_the_others_are_on(store_conn, relationships, read):
    """With every scope but the data's own shared, the read is refused (AC-22)."""
    function, scope = READS[read]
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], scope, False)
    with pytest.raises(access.NotFound):
        function(store_conn, world.COACH_A, world.SHARED)
    assert _audit_rows(store_conn) == []


@pytest.mark.parametrize("read", [name for name, (_, scope) in READS.items() if scope])
def test_revoking_the_scope_blocks_the_next_read(store_conn, relationships, read):
    """A read that worked fails as soon as the client turns the scope off (AC-22)."""
    function, scope = READS[read]
    function(store_conn, world.COACH_A, world.SHARED)
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], scope, False)
    with pytest.raises(access.NotFound):
        function(store_conn, world.COACH_A, world.SHARED)


@pytest.mark.parametrize("read", READS)
def test_ending_the_relationship_blocks_the_next_read(store_conn, relationships, read):
    """Once either side ends the relationship, the coach reads nothing (AC-22)."""
    function, _ = READS[read]
    users.end_relationship(store_conn, world.COACH_A, relationships[world.SHARED])
    with pytest.raises(access.NotFound):
        function(store_conn, world.COACH_A, world.SHARED)


def test_preferences_are_never_shared_with_a_coach(store_conn, relationships):
    """Even with every scope on, a coach cannot read a client's preferences."""
    with pytest.raises(access.NotFound):
        records.list_preferences(store_conn, world.COACH_A, world.SHARED)


@pytest.mark.parametrize("read", [name for name, (_, scope) in READS.items() if scope])
def test_a_coach_reads_a_shared_scope_and_leaves_one_audit_row_without_values(
    store_conn, relationships, read
):
    """The allowed read returns the client's rows and writes one audit row of IDs and names."""
    function, _ = READS[read]
    function(store_conn, world.COACH_A, world.SHARED)
    [row] = _audit_rows(store_conn)
    assert row["actor_id"] == world.COACH_A
    assert row["subject_id"] == world.SHARED
    assert row["action"] == "read"
    assert row["resource_id"] is None
    assert row["created_at"].endswith("+00:00")
    # Only these columns exist, so no value can be in the row.
    assert set(row) == {
        "id",
        "actor_id",
        "subject_id",
        "action",
        "resource_type",
        "resource_id",
        "created_at",
    }
    assert str(world.WEIGHT) not in str(row) and str(world.HEIGHT) not in str(row)


@pytest.mark.parametrize("read", READS)
def test_a_user_reads_their_own_data_without_an_audit_row(store_conn, relationships, read):
    """Reading one's own data needs no relationship or scope and is not audited."""
    function, _ = READS[read]
    function(store_conn, world.UNSHARED, world.UNSHARED)
    assert _audit_rows(store_conn) == []


def test_a_coach_sees_only_the_clients_own_rows(store_conn, relationships):
    """The coach's read returns the client's weight, never another gymer's rows."""
    [weight] = records.list_body_measurements(store_conn, world.COACH_A, world.SHARED)
    assert weight["weight_kg"] == world.WEIGHT
    [meal] = records.list_meal_items(store_conn, world.COACH_A, world.SHARED)
    own = records.list_meal_items(store_conn, world.SHARED, world.SHARED)
    assert [meal] == own


def test_sharing_again_after_a_revoke_opens_the_scope_again(store_conn, relationships):
    """Turning a scope off and on keeps both consents and allows the read again."""
    rel = relationships[world.SHARED]
    users.set_consent(store_conn, world.SHARED, rel, "body", False)
    users.set_consent(store_conn, world.SHARED, rel, "body", True)
    assert records.list_body_measurements(store_conn, world.COACH_A, world.SHARED)
    rows = store_conn.execute(
        "SELECT revoked_at FROM consents WHERE relationship_id = ? AND scope = 'body'", (rel,)
    ).fetchall()
    assert [row["revoked_at"] is None for row in rows] == [False, True]


# --- Who may change a relationship or a scope ---------------------------------------------------


def test_only_the_client_sets_their_scopes(store_conn, relationships):
    """The coach, another gymer or a missing user gets NotFound when setting a client's scope."""
    rel = relationships[world.UNSHARED]
    for actor in (world.COACH_A, world.SHARED, world.MISSING):
        with pytest.raises(access.NotFound):
            users.set_consent(store_conn, actor, rel, "body", True)
    with pytest.raises(access.NotFound):
        records.list_body_measurements(store_conn, world.COACH_A, world.UNSHARED)


@pytest.mark.parametrize("relationship_id", [999, None, "1", True])
def test_a_missing_relationship_is_not_found(store_conn, relationships, relationship_id):
    """Setting a scope on, or ending, a relationship that does not exist gives NotFound."""
    with pytest.raises(access.NotFound):
        users.set_consent(store_conn, world.SHARED, relationship_id, "body", True)
    with pytest.raises(access.NotFound):
        users.end_relationship(store_conn, world.SHARED, relationship_id)


def test_an_ended_relationship_cannot_be_shared_again(store_conn, relationships):
    """The client of an ended relationship cannot turn a scope back on."""
    with pytest.raises(access.NotFound):
        users.set_consent(store_conn, world.ENDED, relationships[world.ENDED], "body", True)


def test_either_side_ends_a_relationship_and_nobody_else(store_conn, relationships):
    """Another coach or gymer cannot end it; the coach can, which revokes every open scope."""
    rel = relationships[world.SHARED]
    for actor in (world.COACH_B, world.UNSHARED):
        with pytest.raises(access.NotFound):
            users.end_relationship(store_conn, actor, rel)
    users.end_relationship(store_conn, world.COACH_A, rel)
    open_scopes = store_conn.execute(
        "SELECT count(*) FROM consents WHERE relationship_id = ? AND revoked_at IS NULL", (rel,)
    ).fetchone()[0]
    assert open_scopes == 0


@pytest.mark.parametrize(
    ("coach", "client"),
    [
        (world.SHARED, world.UNSHARED),
        (world.COACH_A, world.COACH_B),
        (world.COACH_A, world.MISSING),
    ],
)
def test_a_relationship_needs_a_coach_and_a_gymer(store_conn, relationships, coach, client):
    """start_relationship refuses any other pair of roles."""
    with pytest.raises(ValueError, match="needs a coach and a gymer"):
        users.start_relationship(store_conn, coach, client)


def test_a_second_active_relationship_for_the_same_pair_is_refused(store_conn, relationships):
    """An active pair cannot be started twice; after it ends, a new one can be."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        users.start_relationship(store_conn, world.COACH_A, world.SHARED)
    assert users.start_relationship(store_conn, world.COACH_A, world.ENDED)


@pytest.mark.parametrize("shared", ["False", "no", 1, 1.0, [0], None])
def test_a_scope_is_shared_only_with_true(store_conn, relationships, shared):
    """A value that is not a bool (a form's text, a model's argument) shares nothing."""
    rel = relationships[world.UNSHARED]
    with pytest.raises(ValueError, match="shared must be true or false"):
        users.set_consent(store_conn, world.UNSHARED, rel, "body", shared)
    assert (
        store_conn.execute(
            "SELECT count(*) FROM consents WHERE relationship_id = ?", (rel,)
        ).fetchone()[0]
        == 0
    )
