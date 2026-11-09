"""Export and delete everything about a user (T9.6, AC-34), with foreign keys on."""

import json
import sqlite3
from datetime import date

import pytest

from src.store import access, db, my_data, questions, records, reviews, users
from tests import store_world as world
from tests.store_world import no_threads

NOW = "2026-10-27T10:00:00+00:00"
QUESTION = "CANARY-QUESTION why fewer carbs?"
ANSWER = "CANARY-ANSWER rest days need less."


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
    # Another week: a second review of a week that has a pending or approved one is refused.
    next_week = {**review_args, "period_start": date(2026, 10, 26)}
    reviews.save_review(store_conn, world.COACH_A, world.SHARED, **next_week)  # stays pending
    reviews.save_review(store_conn, world.COACH_B, world.OTHERS, **review_args)
    reviews.decide_review(store_conn, world.COACH_A, approved, "approve")
    records.list_meal_items(store_conn, world.COACH_A, world.SHARED)  # an audited read
    records.list_meal_items(store_conn, world.COACH_B, world.OTHERS)
    # T9.25: a question and the coach's answer under the approved review (an audited answer).
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
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
        ("review_questions", "author_id"),
        ("notification_reads", "user_id"),
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
    assert document["preferences"] == []  # only coaches keep preferences (T9.7)
    assert len(document["coach_clients"]) == 1 and len(document["consents"]) == 3
    assert [r["status"] for r in document["ai_reviews"]] == ["APPROVED"]
    assert document["ai_reviews"][0]["final"] == {"observations": ["x"]}
    assert len(document["ai_evidence_refs"]) == 1
    # The coach's read of the meals and the approval of the review, both about this gymer.
    assert [r["action"] for r in document["audit_log"]] == [
        "review_approved",
        "read",
        "review_answered",
    ]
    assert [(r["kind"], r["text"]) for r in document["review_questions"]] == [
        ("question", QUESTION),
        ("answer", ANSWER),
    ]
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
    assert added == [
        (world.COACH_A, world.SHARED, "ai_reviews"),
        (world.COACH_A, world.SHARED, "review_questions"),
    ]


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
        my_data.delete_user_data(full_world, world.MISSING, no_threads)


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A, world.OTHERS, world.ENDED])
def test_deleting_a_user_leaves_no_row_about_them_and_every_other_row(full_world, user):
    """After the delete no column names the user, references hold, and others' rows remain."""
    assert _rows_naming(full_world, user)
    before = _rows_naming(full_world, world.UNSHARED)
    my_data.delete_user_data(full_world, user, no_threads)
    assert _rows_naming(full_world, user) == {}
    assert full_world.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert full_world.execute("PRAGMA foreign_key_check").fetchall() == []
    # UNSHARED is coach A's client: deleting coach A also removes that relationship.
    after = _rows_naming(full_world, world.UNSHARED)
    if user == world.COACH_A:
        before.pop("coach_clients.client_id")
    assert after == before
    with pytest.raises(access.NotFound):
        my_data.delete_user_data(full_world, user, no_threads)


def test_deleting_a_gymer_removes_the_reviews_about_them(full_world):
    """Every review about the gymer goes, pending ones and their evidence included."""
    my_data.delete_user_data(full_world, world.SHARED, no_threads)
    assert full_world.execute("SELECT count(*) FROM ai_reviews").fetchone()[0] == 1  # coach B's
    assert full_world.execute("SELECT count(*) FROM ai_evidence_refs").fetchone()[0] == 1


def test_deleting_a_coach_removes_the_reviews_they_wrote_and_keeps_the_clients_records(full_world):
    """Coach A's reviews, relationships and invitation go; the clients' own records stay."""
    my_data.delete_user_data(full_world, world.COACH_A, no_threads)
    coaches = [row["coach_id"] for row in full_world.execute("SELECT coach_id FROM ai_reviews")]
    assert coaches == [world.COACH_B]
    assert full_world.execute("SELECT count(*) FROM consents").fetchone()[0] == 3  # coach B's
    assert records.list_meal_items(full_world, world.SHARED, world.SHARED)


def test_deleted_values_are_gone_from_the_files_bytes(tmp_path):
    """After delete_user_data(), the deleted text is nowhere in the database file."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        world.build(conn)
        records.add_preference(conn, world.COACH_A, "CANARY-PREF-DELETED")
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
        my_data.delete_user_data(conn, world.SHARED, no_threads)
        my_data.delete_user_data(conn, world.COACH_A, no_threads)
        # Other users' rows are still there, so the pages were reused, not dropped.
        assert records.list_preferences(conn, world.COACH_B, world.COACH_B)
    data = path.read_bytes()
    assert b"CANARY-PREF-DELETED" not in data and b"CANARY-FOOD-DELETED" not in data
    assert not (tmp_path / "s.sqlite3-journal").exists()


def test_a_table_the_delete_forgets_makes_it_fail_and_change_nothing(full_world):
    """A new table referring to users, not in the delete, stops it: no partial delete is left."""
    full_world.execute("CREATE TABLE notes (user_id TEXT NOT NULL REFERENCES users (id)) STRICT")
    full_world.execute("INSERT INTO notes (user_id) VALUES (?)", (world.SHARED,))
    before = _all_rows(full_world)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        my_data.delete_user_data(full_world, world.SHARED, no_threads)
    assert _all_rows(full_world) == before


def test_a_coachs_export_holds_their_preferences_and_delete_removes_them(store_conn):
    """A coach's preferences are in their export and gone after "delete everything" (AC-34)."""
    world.build(store_conn)
    records.add_preference(store_conn, world.COACH_A, "most of my clients are vegetarian")
    document = json.loads(my_data.export_user_data(store_conn, world.COACH_A))
    assert [row["text"] for row in document["preferences"]] == [
        world.PREFERENCE,
        "most of my clients are vegetarian",
    ]
    assert {row["user_id"] for row in document["preferences"]} == {world.COACH_A}
    my_data.delete_user_data(store_conn, world.COACH_A, no_threads)
    count = "SELECT count(*) FROM preferences WHERE user_id = ?"
    assert store_conn.execute(count, (world.COACH_A,)).fetchone()[0] == 0
    assert records.list_preferences(store_conn, world.COACH_B, world.COACH_B)


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_both_sides_export_the_target_set_row_and_the_gymer_the_target(full_world, user):
    """A coach's target is in the gymer's export; its audit row is in both sides' (T9.17)."""
    target_id = records.add_client_target(
        full_world,
        world.COACH_A,
        world.SHARED,
        kcal=2100.0,
        protein_g=170.0,
        carbs_g=200.0,
        fat_g=65.0,
        effective_from=date(2026, 10, 27),
    )
    document = json.loads(my_data.export_user_data(full_world, user))
    rows = [row for row in document["audit_log"] if row["action"] == "target_set"]
    assert [(row["resource_id"], row["subject_id"]) for row in rows] == [(target_id, world.SHARED)]
    if user == world.SHARED:
        targets = {row["id"]: row["set_by"] for row in document["nutrition_targets"]}
        assert targets[target_id] == "coach"


# --- The questions to the coach (T9.25, AC-42) ----------------------------------------------------


def _thread_texts(document):
    """Return the texts of the thread rows in an export."""
    return [row["text"] for row in document["review_questions"]]


def test_a_coachs_export_holds_the_threads_they_may_read(full_world):
    """The coach exports the thread under the review they wrote; another coach does not."""
    document = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert _thread_texts(document) == [QUESTION, ANSWER]
    other = json.loads(my_data.export_user_data(full_world, world.COACH_B))
    assert other["review_questions"] == []
    assert QUESTION not in json.dumps(other)


def test_a_coachs_export_leaves_out_a_thread_once_the_client_stops_sharing(full_world):
    """With nutrition off (or the relationship ended), the coach's export holds no thread."""
    [relationship] = users.list_relationships(full_world, world.SHARED)
    users.set_consent(full_world, world.SHARED, relationship["id"], "nutrition", False)
    document = json.loads(my_data.export_user_data(full_world, world.COACH_A))
    assert document["review_questions"] == []
    gymer = json.loads(my_data.export_user_data(full_world, world.SHARED))
    assert _thread_texts(gymer) == [QUESTION, ANSWER]


def test_a_gymers_export_keeps_the_thread_after_the_end(full_world):
    """The gymer still reads the thread once the relationship ends (owner's choice, 2026-11-06)."""
    [relationship] = users.list_relationships(full_world, world.SHARED)
    users.end_relationship(full_world, world.SHARED, relationship["id"])
    document = json.loads(my_data.export_user_data(full_world, world.SHARED))
    assert _thread_texts(document) == [QUESTION, ANSWER]


@pytest.mark.parametrize("user", [world.SHARED, world.COACH_A])
def test_deleting_either_side_removes_the_thread(full_world, user):
    """The thread goes with its review, whoever deletes; its text is gone from the table."""
    my_data.delete_user_data(full_world, user, no_threads)
    assert full_world.execute("SELECT count(*) FROM review_questions").fetchone()[0] == 0


def test_deleting_a_user_removes_every_row_they_wrote(full_world):
    """A row by the user under another user's review goes too (no reference is left)."""
    reviewed = full_world.execute(
        "SELECT id FROM ai_reviews WHERE coach_id = ? AND status = 'APPROVED'", (world.COACH_A,)
    ).fetchone()[0]
    # Written directly: no store function lets a third user write here; the delete must still hold.
    full_world.execute(
        "INSERT INTO review_questions (review_id, author_id, kind, text, created_at)"
        " VALUES (?, ?, 'question', 'x', ?)",
        (reviewed, world.OTHERS, NOW),
    )
    my_data.delete_user_data(full_world, world.OTHERS, no_threads)
    count = "SELECT count(*) FROM review_questions WHERE author_id = ?"
    assert full_world.execute(count, (world.OTHERS,)).fetchone()[0] == 0
    assert full_world.execute("SELECT count(*) FROM review_questions").fetchone()[0] == 2
