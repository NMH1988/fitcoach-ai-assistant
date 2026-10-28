"""Export and delete everything about a user (T9.6, AC-34), with foreign keys on."""

import json
import sqlite3
from datetime import date

import pytest

from src.store import access, db, my_data, records, reviews
from tests import store_world as world

NOW = "2026-10-27T10:00:00+00:00"


@pytest.fixture
def full_world(store_conn):
    """Build the world plus reviews, audit rows, an invitation and code attempts."""
    world.build(store_conn)
    review_args = {
        "period_start": date(2026, 10, 19),
        "metrics": {"logged_days": 3},
        "data_quality": {},
        "draft": {"observations": ["x"]},
        "model_version": "m",
        "evidence_refs": [("12", "12-3")],
    }
    approved = reviews.save_review(store_conn, world.COACH_A, world.SHARED, **review_args)
    reviews.save_review(store_conn, world.COACH_A, world.SHARED, **review_args)  # stays pending
    reviews.save_review(store_conn, world.COACH_B, world.OTHERS, **review_args)
    reviews.decide_review(store_conn, world.COACH_A, approved, "approve")
    records.list_meal_items(store_conn, world.COACH_A, world.SHARED)  # an audited read
    records.list_meal_items(store_conn, world.COACH_B, world.OTHERS)
    # T9.12 adds the functions for these two tables; the rows are written directly here.
    for coach in (world.COACH_A, world.COACH_B):
        store_conn.execute(
            "INSERT INTO invitations (coach_id, code_hash, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (coach, coach + "-hash", NOW, NOW),
        )
    for gymer in (world.SHARED, world.OTHERS):
        store_conn.execute(
            "INSERT INTO invite_attempts (user_id, day, count) VALUES (?, '2026-10-27', 2)",
            (gymer,),
        )
    return store_conn


def _user_columns(conn):
    """Return (table, column) for every column that refers to users(id), and users.id itself."""
    found = [("users", "id")]
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        for key in conn.execute(f"PRAGMA foreign_key_list({table})"):
            if key["table"] == "users":
                found.append((table, key["from"]))
    return found


def _rows_naming(conn, user_id):
    """Return {table: count} of rows that refer to the user in any user column."""
    counts = {}
    for table, column in _user_columns(conn):
        query = f"SELECT count(*) FROM {table} WHERE {column} = ?"
        count = conn.execute(query, (user_id,)).fetchone()[0]
        if count:
            counts[f"{table}.{column}"] = count
    return counts


def _all_rows(conn):
    """Return every row of every table, as {table: [tuples]}."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {
        t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in tables
    }


def test_the_store_has_the_columns_this_test_expects(full_world):
    """The scan of user columns finds every reference (a new one must be handled in my_data)."""
    assert set(_user_columns(full_world)) == {
        ("users", "id"),
        ("invitations", "coach_id"),
        ("coach_clients", "coach_id"),
        ("coach_clients", "client_id"),
        ("profile_entries", "user_id"),
        ("body_measurements", "user_id"),
        ("nutrition_targets", "user_id"),
        ("meal_items", "user_id"),
        ("workout_sessions", "user_id"),
        ("preferences", "user_id"),
        ("ai_reviews", "client_id"),
        ("ai_reviews", "coach_id"),
        ("ai_reviews", "reviewed_by"),
        ("audit_log", "actor_id"),
        ("audit_log", "subject_id"),
        ("invite_attempts", "user_id"),
    }


def test_a_gymers_export_holds_a_rejection_but_not_the_rejected_review(full_world):
    """A rejected review stays out of the gymer's export; its review_rejected audit row is in it."""
    rejected = reviews.save_review(
        full_world,
        world.COACH_A,
        world.SHARED,
        period_start=date(2026, 10, 12),
        metrics={"logged_days": 2},
        data_quality={},
        draft={"observations": ["CANARY-REJECTED"]},
        model_version="m",
    )
    reviews.decide_review(full_world, world.COACH_A, rejected, "reject")
    text = my_data.export_user_data(full_world, world.SHARED)
    document = json.loads(text)
    assert rejected not in [review["id"] for review in document["ai_reviews"]]
    assert "CANARY-REJECTED" not in text
    decisions = [
        (row["action"], row["resource_id"])
        for row in document["audit_log"]
        if row["action"].startswith("review_")
    ]
    assert ("review_rejected", rejected) in decisions


def test_a_gymers_export_holds_all_their_rows_as_json(full_world):
    """Every table appears; the gymer's records, relationship, scopes, approved review and audit."""
    document = json.loads(my_data.export_user_data(full_world, world.SHARED))
    tables = {
        r[0] for r in full_world.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert set(document) == (tables - {"users"}) | {"user"}
    assert document["user"]["id"] == world.SHARED
    for table in ("profile_entries", "body_measurements", "nutrition_targets", "meal_items"):
        assert len(document[table]) == 1 and document[table][0]["user_id"] == world.SHARED
    assert len(document["workout_sessions"]) == 1 and len(document["exercise_sets"]) == 2
    assert document["preferences"][0]["text"] == "vegetarian"
    assert len(document["coach_clients"]) == 1 and len(document["consents"]) == 3
    assert [r["status"] for r in document["ai_reviews"]] == ["APPROVED"]
    assert document["ai_reviews"][0]["final"] == {"observations": ["x"]}
    assert len(document["ai_evidence_refs"]) == 1
    # The coach's read of the meals and the approval of the review, both about this gymer.
    assert [r["action"] for r in document["audit_log"]] == ["review_approved", "read"]
    assert document["invite_attempts"][0]["count"] == 2
    assert document["invitations"] == []


def test_a_coachs_export_holds_their_relationships_reviews_and_invitations(full_world):
    """A coach exports the reviews they wrote, pending ones too, and their invitations."""
    document = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert document["user"]["role"] == "coach"
    assert len(document["coach_clients"]) == 3
    assert [r["status"] for r in document["ai_reviews"]] == ["APPROVED", "PENDING_REVIEW"]
    assert len(document["invitations"]) == 1
    assert {r["actor_id"] for r in document["audit_log"]} == {world.COACH_A}
    assert document["meal_items"] == []


def _read_rows(conn):
    """Return (actor, subject, resource type) of every read in the audit log."""
    query = "SELECT actor_id, subject_id, resource_type FROM audit_log WHERE action = 'read'"
    return [tuple(row) for row in conn.execute(query)]


def test_a_coachs_export_audits_one_read_per_client_in_it(full_world):
    """The coach's export reads clients' reviews, so it writes a read row for each client."""
    before = _read_rows(full_world)
    my_data.export_user_data(full_world, world.COACH_A)
    added = _read_rows(full_world)[len(before) :]
    assert added == [(world.COACH_A, world.SHARED, "ai_reviews")]


def test_a_gymers_export_writes_no_audit_row(full_world):
    """Reading one's own data is not audited."""
    before = _read_rows(full_world)
    my_data.export_user_data(full_world, world.SHARED)
    assert _read_rows(full_world) == before


def test_an_export_holds_no_other_users_records(full_world):
    """Another gymer's records and coach B's rows are not in the gymer's export."""
    text = my_data.export_user_data(full_world, world.SHARED)
    for other in (world.OTHERS, world.UNSHARED, world.ENDED, world.COACH_B):
        assert other not in text


def test_exporting_or_deleting_a_missing_user_is_not_found(full_world):
    """A user who does not exist gives NotFound."""
    with pytest.raises(access.NotFound):
        my_data.export_user_data(full_world, world.MISSING)
    with pytest.raises(access.NotFound):
        my_data.delete_user_data(full_world, world.MISSING)


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A, world.OTHERS, world.ENDED])
def test_deleting_a_user_leaves_no_row_about_them_and_every_other_row(full_world, user):
    """After the delete no column names the user, references hold, and others' rows remain."""
    assert _rows_naming(full_world, user)
    before = _rows_naming(full_world, world.UNSHARED)
    my_data.delete_user_data(full_world, user)
    assert _rows_naming(full_world, user) == {}
    assert full_world.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert full_world.execute("PRAGMA foreign_key_check").fetchall() == []
    # UNSHARED is coach A's client: deleting coach A also removes that relationship.
    after = _rows_naming(full_world, world.UNSHARED)
    if user == world.COACH_A:
        before.pop("coach_clients.client_id")
    assert after == before
    with pytest.raises(access.NotFound):
        my_data.delete_user_data(full_world, user)


def test_deleting_a_gymer_removes_the_reviews_about_them(full_world):
    """Every review about the gymer goes, pending ones and their evidence included."""
    my_data.delete_user_data(full_world, world.SHARED)
    assert full_world.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 1  # coach B's
    assert full_world.execute("SELECT count(*) FROM ai_evidence_refs").fetchone()[0] == 1


def test_deleting_a_coach_removes_the_reviews_they_wrote_and_keeps_the_clients_records(full_world):
    """Coach A's reviews, relationships and invitation go; the clients' own records stay."""
    my_data.delete_user_data(full_world, world.COACH_A)
    coaches = [row["coach_id"] for row in full_world.execute("SELECT coach_id FROM ai_reviews")]
    assert coaches == [world.COACH_B]
    assert full_world.execute("SELECT count(*) FROM consents").fetchone()[0] == 3  # coach B's
    assert records.list_meal_items(full_world, world.SHARED, world.SHARED)


def test_deleted_values_are_gone_from_the_files_bytes(tmp_path):
    """After delete_user_data(), the deleted text is nowhere in the database file."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        world.build(conn)
        records.add_preference(conn, world.SHARED, "CANARY-PREF-DELETED")
        records.add_meal_item(
            conn,
            world.SHARED,
            consumed_on=date(2026, 10, 27),
            meal="dinner",
            fdc_id=7,
            food_name="CANARY-FOOD-DELETED",
            grams=100.0,
            kcal=100.0,
            protein_g=1.0,
            carbohydrate_g=1.0,
            fat_g=1.0,
            fiber_g=None,
        )
        before = path.read_bytes()  # the checks below can fail
        assert b"CANARY-FOOD-DELETED" in before and b"CANARY-PREF-DELETED" in before
        my_data.delete_user_data(conn, world.SHARED)
        # Other users' rows are still there, so the pages were reused, not dropped.
        assert records.list_preferences(conn, world.OTHERS, world.OTHERS)
    data = path.read_bytes()
    assert b"CANARY-PREF-DELETED" not in data and b"CANARY-FOOD-DELETED" not in data
    assert not (tmp_path / "s.sqlite3-journal").exists()


def test_a_table_the_delete_forgets_makes_it_fail_and_change_nothing(full_world):
    """A new table referring to users, not in the delete, stops it: no partial delete is left."""
    full_world.execute("CREATE TABLE notes (user_id TEXT NOT NULL REFERENCES users (id)) STRICT")
    full_world.execute("INSERT INTO notes (user_id) VALUES (?)", (world.SHARED,))
    before = _all_rows(full_world)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        my_data.delete_user_data(full_world, world.SHARED)
    assert _all_rows(full_world) == before
