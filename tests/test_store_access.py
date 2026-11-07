"""Who may read whose data (T9.6, D16): cross-client tests for every read function (AC-21, AC-22).

Every read function takes the acting user and the user whose data it reads. A user reads their own
data; a coach reads a gymer's only while the relationship is active and the scope is shared; every
other case raises the same `NotFound` and writes no audit row. A coach's allowed read writes one
audit row with no values.
"""

import ast
import importlib
import inspect
import re
from pathlib import Path

import pytest

from src.store import access, invitations, records, reviews, users
from src.store.values import StoreValueError
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
    # The user's own relationships, the other side's name read through display_name_of (T9.12).
    "users.list_relationships",
    "invitations.list_invitations",
    "records.delete_record",
    "my_data.export_user_data",
    "my_data.delete_user_data",
    # T9.16: the status of the coach's own review, asked after the store refused a decision.
    "reviews.is_pending",
    # T9.29: the user's own notifications, from their own relationships, the scope history both
    # sides see and the approved reviews about a gymer; not audited (owner's choice, 2026-11-06).
    # Their isolation is tested in tests/test_store_notifications.py.
    "notifications.list_notifications",
}
WRITES = {
    # Each takes the user it writes for; the ones that change shared data check that it is the
    # acting user's to make. create_user (T9.5, at the first sign-in) and start_relationship
    # (T9.12, after a valid code) take no acting user: only their callers may decide.
    "users.create_user",
    "users.start_relationship",
    "users.set_consent",
    "users.set_scopes",
    "users.end_relationship",
    # T9.12: a coach's own codes; a gymer accepts one for themself (a valid code, D15).
    "invitations.create_invitation",
    "invitations.cancel_invitation",
    "invitations.accept_invitation",
    "records.add_profile_entry",
    "records.add_body_measurement",
    "records.add_target",
    "records.add_meal_item",
    "records.add_workout_session",
    # Replaces only the acting user's own workout (T9.14): NotFound for anyone else's.
    "records.replace_workout_session",
    "records.add_preference",
    # T9.13: a profile save in one transaction, and a meal edit (the user's own item only).
    "records.add_profile_with_target",
    "records.replace_meal_item",
    "reviews.save_review",
    "reviews.decide_review",
    # T9.16: the review workflow's authorise step, the check before save_review; it reads only the
    # client's open shares and the coach's own reviews of that week (tests/test_store_reviews.py).
    "reviews.prepare_review",
    # T9.16: removes the coach's own pending review of a run that failed after saving it.
    "reviews.discard_pending",
    # T9.29: the acting user's own read mark only.
    "notifications.mark_all_read",
}
INTERNALS = {
    # No user data in or out: opening the file, checks, and the access layer itself.
    "db.connect",
    "db.migrate",
    "db.prepare_file",
    "db.schema_version",
    "db.transaction",
    "access.audit",
    "access.authorise_read",
    "access.authorised_read",
    "access.role_of",
    "invitations.normalise_code",
    *(
        f"values.{name}"
        for name in ("choice", "date_text", "in_range", "is_row_id", "is_utf8", "number")
    ),
    *(f"values.{name}" for name in ("text", "user_id", "utc_text", "whole_number")),
}


# A coach's writes into a client's records (T9.17): each runs access.authorise_read() for the
# scope the record belongs to inside its write transaction, so it is refused exactly where a read
# is (REFUSED, a scope not shared, the coach's own ID), with no row and no audit row.
COACH_WRITES = {"records.add_client_target": "nutrition"}


# The one read of another user's data that does not go through access.authorised_read() (T9.12):
# the other side's display name, allowed for both sides of an active or ended relationship, checked
# by the function itself and not audited (owner's choices, 2026-10-28 and 2026-11-03).
NAME_READS = {"users.display_name_of"}


# SQL that filters on a relationship being active or not ended (a comparison, IN, LIKE, GLOB or
# IS), or on ended_at being NULL, under any table alias, spacing, case or value quote, with the
# column written first and unquoted and the value first in an IN list (docs/SECURITY.md lists what
# needs review). Writing a status as a value (INSERT ... VALUES, SET status = 'ended') is not one.
ACTIVE_FILTER = re.compile(
    r"status\s*(?:=|==|<>|!=|\bNOT\s+IN\b|\bIN\b|\bNOT\s+LIKE\b|\bLIKE\b|\bGLOB\b"
    r"|\bIS(?:\s+NOT)?\b)\s*\(?\s*['\"]active['\"]"
    r"|status\s*(?:<>|!=|\bNOT\s+IN\b|\bNOT\s+LIKE\b|\bIS\s+NOT\b)\s*\(?\s*['\"]ended['\"]"
    r"|ended_at\s+(?:IS\s+(?:NOT\s+)?NULL|ISNULL|NOTNULL|NOT\s+NULL)",
    re.IGNORECASE,
)
# The consent half of the rule: only open_shares, and users' two statements that manage
# consents, may test revoked_at for NULL (IS [NOT] NULL, ISNULL, NOTNULL, NOT NULL).
OPEN_CONSENT = re.compile(
    r"revoked_at\s+(?:IS\s+(?:NOT\s+)?NULL|ISNULL|NOTNULL|NOT\s+NULL)", re.IGNORECASE
)


def _sql_texts(path: Path) -> list[str]:
    """Return every string literal in a module (its SQL constants among them)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_only_the_view_filters_on_an_active_relationship():
    """No SQL outside schema.py filters on status 'active': sharing is read from open_shares."""
    for path in sorted(STORE.rglob("*.py")):
        if path.name == "schema.py":
            continue
        for text in _sql_texts(path):
            assert not ACTIVE_FILTER.search(text), (path, text)
    for path in ("access.py", "reviews.py", "my_data.py"):
        assert "open_shares" in (STORE / path).read_text(encoding="utf-8"), path


@pytest.mark.parametrize(
    "sql",
    [
        "AND consent.revoked_at IS NULL",
        "AND c.REVOKED_AT  is\n null",
        "AND revoked_at ISNULL",
        "AND revoked_at NOTNULL",
        "AND revoked_at IS NOT NULL",
        "AND revoked_at NOT NULL",
    ],
)
def test_the_open_consent_check_catches_each_spelling(sql):
    """The consent check finds a NULL test on revoked_at under any spelling SQLite accepts."""
    assert OPEN_CONSENT.search(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE consents SET revoked_at = ? WHERE id = ?",
        "INSERT INTO consents (relationship_id, scope, granted_at) VALUES (?, ?, ?)",
    ],
)
def test_the_open_consent_check_lets_a_write_pass(sql):
    """Setting revoked_at, or adding a consent, is not a test for an open consent."""
    assert not OPEN_CONSENT.search(sql)


def test_only_the_view_and_the_consent_statements_test_for_an_open_consent():
    """revoked_at is tested for NULL outside schema.py only in users' two consent statements."""
    allowed = {users._OPEN_CONSENT, users._REVOKE_ALL}
    for path in sorted(STORE.rglob("*.py")):
        if path.name == "schema.py":
            continue
        for text in _sql_texts(path):
            if OPEN_CONSENT.search(text):
                assert text in allowed, (path, text)


@pytest.mark.parametrize(
    "sql",
    [
        "WHERE relationship.status = 'active'",
        "WHERE cc.status='active'",
        "where CC.STATUS\n   =  'Active'",
        "AND status IN ('active')",
        "AND status <> 'active'",
        "AND r.ended_at IS NULL",
        "AND status <> 'ended'",
        "AND status NOT IN ('ended')",
        'AND status = "active"',
        "AND status LIKE 'active'",
        "AND r.ended_at ISNULL",
        "AND r.ended_at NOTNULL",
        "AND r.ended_at NOT NULL",
    ],
)
def test_the_active_filter_check_catches_each_spelling(sql):
    """The check above finds the filter under an alias, other spacing, case or operator."""
    assert ACTIVE_FILTER.search(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO coach_clients (status) VALUES ('active')",
        "UPDATE coach_clients SET status = 'ended', ended_at = ? WHERE id = ?",
    ],
)
def test_the_active_filter_check_lets_a_write_pass(sql):
    """Writing a status as a value, or setting a relationship to ended, is not a filter."""
    assert not ACTIVE_FILTER.search(sql)


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
    groups = [reads, OWN_ONLY, WRITES, INTERNALS, NAME_READS, set(COACH_WRITES)]
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
    """Even with every scope on, a coach cannot read preferences of a client (scope None)."""
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


@pytest.mark.parametrize("relationship_id", [999, None, "1", True, 0, -1, 2**64])
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
    with pytest.raises(ValueError, match="the gymer has a coach already"):
        users.start_relationship(store_conn, world.COACH_A, world.SHARED)
    assert users.start_relationship(store_conn, world.COACH_A, world.ENDED)


def test_the_database_refuses_a_second_active_row_for_the_same_pair(store_conn, relationships):
    """Below the one-coach check, the coach_clients_one_active index refuses the same pair."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store_conn.execute(
            "INSERT INTO coach_clients (coach_id, client_id, status, accepted_at)"
            " VALUES (?, ?, 'active', '2026-11-03T10:00:00+00:00')",
            (world.COACH_A, world.SHARED),
        )


def test_set_scopes_changes_every_scope_in_one_transaction(store_conn, relationships, monkeypatch):
    """The scopes are set together: a failure part-way leaves every scope as it was."""
    rel = relationships[world.SHARED]
    users.set_scopes(store_conn, world.SHARED, rel, {"nutrition": False, "body": True})
    [mine] = users.list_relationships(store_conn, world.SHARED)
    assert mine["scopes"] == ("training", "body")
    real = users._set
    calls = []

    def fail_on_the_second(conn, relationship_id, scope, shared):
        """Change the first scope, then fail like a busy store."""
        calls.append(scope)
        if len(calls) == 2:
            raise users.values.StoreValueError("store", "is busy")
        real(conn, relationship_id, scope, shared)

    monkeypatch.setattr(users, "_set", fail_on_the_second)
    with pytest.raises(ValueError):
        users.set_scopes(store_conn, world.SHARED, rel, {"training": False, "body": False})
    [mine] = users.list_relationships(store_conn, world.SHARED)
    assert mine["scopes"] == ("training", "body")


@pytest.mark.parametrize(
    "choices",
    [{"preferences": True}, {"body": "False"}, {"body": True, "nutrition": 1}, [("body", True)]],
)
def test_set_scopes_refuses_a_bad_choice_before_writing(store_conn, relationships, choices):
    """An unknown scope or a value that is not a bool changes nothing."""
    rel = relationships[world.UNSHARED]
    with pytest.raises(ValueError):
        users.set_scopes(store_conn, world.UNSHARED, rel, choices)
    [mine] = users.list_relationships(store_conn, world.UNSHARED)
    assert mine["scopes"] == ()


@pytest.mark.parametrize("scope", [["body"], {"body": True}, None, "everything"])
def test_set_consent_refuses_a_scope_that_is_not_one_of_the_three(store_conn, relationships, scope):
    """Even an unhashable value gets the store's own value error, never a TypeError."""
    with pytest.raises(StoreValueError):
        users.set_consent(store_conn, world.UNSHARED, relationships[world.UNSHARED], scope, True)


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


# --- The other side's display name (T9.12): its own group, not authorised_read() ---------------

# (actor, other) pairs whose relationship lets each see the other's name.
NAME_ALLOWED = {
    "a coach, their active client": (world.COACH_A, world.SHARED),
    "an active client, their coach": (world.SHARED, world.COACH_A),
    "a coach, a client sharing nothing": (world.COACH_A, world.UNSHARED),
    "a coach, a former client": (world.COACH_A, world.ENDED),
    "a former client, their coach": (world.ENDED, world.COACH_A),
}
NAME_REFUSED = {
    "a missing user": (world.COACH_A, world.MISSING),
    "a missing actor": (world.MISSING, world.SHARED),
    "a stranger coach": (world.COACH_B, world.SHARED),
    "a stranger gymer": (world.UNSHARED, world.SHARED),
    "another coach's client": (world.COACH_A, world.OTHERS),
    "a gymer and another gymer's coach": (world.SHARED, world.COACH_B),
    "a coach and another coach": (world.COACH_A, world.COACH_B),
    "oneself": (world.COACH_A, world.COACH_A),
    "an actor ID that is not text": (None, world.SHARED),
    "an other ID that is not text": (world.COACH_A, 5),
    "an ID that is too long": (world.COACH_A, "x" * 1000),
}


@pytest.mark.parametrize("case", NAME_ALLOWED)
def test_both_sides_of_a_relationship_read_each_others_name_without_audit(
    store_conn, relationships, case
):
    """An active or ended relationship shows each side the other's name; nothing is audited."""
    actor, other = NAME_ALLOWED[case]
    expected = "Coach A" if other == world.COACH_A else other
    assert users.display_name_of(store_conn, actor, other) == expected
    assert _audit_rows(store_conn) == []


@pytest.mark.parametrize("case", NAME_REFUSED)
def test_a_name_without_a_relationship_is_not_found(store_conn, relationships, case):
    """No relationship (or a bad ID) gives the same NotFound and no audit row."""
    actor, other = NAME_REFUSED[case]
    with pytest.raises(access.NotFound) as caught:
        users.display_name_of(store_conn, actor, other)
    assert str(caught.value) == "not found"
    assert _audit_rows(store_conn) == []


def test_a_gymer_does_not_see_a_coachs_name_before_accepting(store_conn, relationships):
    """An invitation joins nobody: the coach's name is not found until the code is accepted."""
    users.create_user(store_conn, "gym-new", "gymer", "Newcomer")
    new = invitations.create_invitation(store_conn, world.COACH_B)
    with pytest.raises(access.NotFound):
        users.display_name_of(store_conn, "gym-new", world.COACH_B)
    invitations.accept_invitation(store_conn, "gym-new", new.code, [])
    assert users.display_name_of(store_conn, "gym-new", world.COACH_B) == "Coach B"


def test_the_relationship_lists_read_names_through_display_name_of(
    store_conn, relationships, monkeypatch
):
    """The coach's client list and the gymer's coach both come from the same name function."""
    calls = []
    real = users.display_name_of

    def spy(conn, actor, other):
        """Record the call and read the name."""
        calls.append((actor, other))
        return real(conn, actor, other)

    monkeypatch.setattr(users, "display_name_of", spy)
    clients = users.list_relationships(store_conn, world.COACH_A)
    assert [row["other_name"] for row in clients] == [world.SHARED, world.UNSHARED, world.ENDED]
    [coach] = users.list_relationships(store_conn, world.SHARED)
    assert coach["other_name"] == "Coach A"
    assert calls == [
        (world.COACH_A, world.SHARED),
        (world.COACH_A, world.UNSHARED),
        (world.COACH_A, world.ENDED),
        (world.SHARED, world.COACH_A),
    ]


def test_the_relationship_list_shows_status_and_the_scopes_on(store_conn, relationships):
    """Each row has its status; only an active relationship lists scopes (from open_shares)."""
    rows = {row["other_id"]: row for row in users.list_relationships(store_conn, world.COACH_A)}
    assert rows[world.SHARED]["status"] == "active"
    assert rows[world.SHARED]["scopes"] == ("nutrition", "training", "body")
    assert rows[world.UNSHARED]["scopes"] == ()
    assert rows[world.ENDED]["status"] == "ended"
    assert rows[world.ENDED]["scopes"] == ()
    assert rows[world.ENDED]["ended_at"] is not None
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], "training", False)
    [mine] = users.list_relationships(store_conn, world.SHARED)
    assert mine["scopes"] == ("nutrition", "body")
    assert _audit_rows(store_conn) == []


def test_an_ended_pair_that_starts_again_lists_scopes_only_on_the_active_row(
    store_conn, relationships
):
    """The old, ended relationship of the same pair never shows the new one's scopes."""
    rel = users.start_relationship(store_conn, world.COACH_A, world.ENDED)
    users.set_consent(store_conn, world.ENDED, rel, "body", True)
    rows = users.list_relationships(store_conn, world.ENDED)
    assert [(row["status"], row["scopes"]) for row in rows] == [
        ("ended", ()),
        ("active", ("body",)),
    ]


@pytest.mark.parametrize("user", [world.MISSING, None])
def test_the_relationship_list_of_a_missing_user(store_conn, relationships, user):
    """A missing user gets NotFound; an ID that is not text a value error."""
    with pytest.raises((access.NotFound, ValueError)):
        users.list_relationships(store_conn, user)


# --- T9.17: a coach's writes into a client's records -------------------------------------------

COACH_WRITE_CALLS = {
    "records.add_client_target": lambda conn, coach, client: records.add_client_target(
        conn,
        coach,
        client,
        kcal=2100.0,
        protein_g=170.0,
        carbs_g=200.0,
        fat_g=65.0,
        effective_from=world.DAY,
    ),
}


def _target_count(conn):
    """Return the number of stored targets."""
    return conn.execute("SELECT count(*) FROM nutrition_targets").fetchone()[0]


def test_every_coach_write_has_a_call_here():
    """Each function of the coach-writes group is run by the tests below."""
    assert set(COACH_WRITE_CALLS) == set(COACH_WRITES)


@pytest.mark.parametrize("write", COACH_WRITES)
@pytest.mark.parametrize("case", REFUSED)
def test_every_refused_pair_gives_not_found_and_writes_nothing(
    store_conn, relationships, write, case
):
    """A coach's write is refused where a read is: one NotFound, no row, no audit row."""
    actor, subject = REFUSED[case]
    before = _target_count(store_conn)
    with pytest.raises(access.NotFound) as caught:
        COACH_WRITE_CALLS[write](store_conn, actor, subject)
    assert type(caught.value) is access.NotFound
    assert str(caught.value) == "not found"
    assert _target_count(store_conn) == before
    assert _audit_rows(store_conn) == []


@pytest.mark.parametrize("write", COACH_WRITES)
def test_a_coach_write_into_their_own_records_is_refused(store_conn, relationships, write):
    """authorise_read() is False for the coach's own ID, which the write refuses too."""
    before = _target_count(store_conn)
    with pytest.raises(access.NotFound):
        COACH_WRITE_CALLS[write](store_conn, world.COACH_A, world.COACH_A)
    assert _target_count(store_conn) == before
    assert _audit_rows(store_conn) == []


@pytest.mark.parametrize("write", COACH_WRITES)
def test_a_coach_write_needs_its_scope_while_others_are_shared(store_conn, relationships, write):
    """A client sharing body and training but not the write's scope refuses it (AC-22)."""
    users.set_consent(
        store_conn, world.SHARED, relationships[world.SHARED], COACH_WRITES[write], False
    )
    before = _target_count(store_conn)
    with pytest.raises(access.NotFound):
        COACH_WRITE_CALLS[write](store_conn, world.COACH_A, world.SHARED)
    assert _target_count(store_conn) == before
    assert _audit_rows(store_conn) == []
    scope = COACH_WRITES[write]
    users.set_consent(store_conn, world.SHARED, relationships[world.SHARED], scope, True)
    COACH_WRITE_CALLS[write](store_conn, world.COACH_A, world.SHARED)  # allowed once shared again
    [row] = _audit_rows(store_conn)
    assert row["action"] == "target_set"
