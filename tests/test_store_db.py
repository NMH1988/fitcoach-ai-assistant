"""The store's file, schema and migrations (T9.6): tables, foreign keys, checks, UTC, no updates."""

import os
import sqlite3
import stat
from datetime import UTC, date, datetime, timedelta, timezone
from typing import get_args

import pytest

from src import config, profile
from src.store import db, schema, values

ROOT = config.PROJECT_ROOT
TABLES = {
    "users",
    "invitations",
    "coach_clients",
    "consents",
    "profile_entries",
    "body_measurements",
    "nutrition_targets",
    "meal_items",
    "workout_sessions",
    "exercise_sets",
    "preferences",
    "ai_reviews",
    "ai_evidence_refs",
    "audit_log",
    "invite_attempts",
}
NOW = "2026-10-27T10:00:00+00:00"
DAY = "2026-10-27"
# A valid row for every table; the rows they refer to are made by _seed().
VALID_ROWS = {
    "users": {"id": "g2", "role": "gymer", "display_name": "Gym Two", "created_at": NOW},
    "invitations": {
        "coach_id": "c1",
        "code_hash": "h1",
        "created_at": NOW,
        "expires_at": NOW,
        "used_at": None,
    },
    "coach_clients": {
        "coach_id": "c1",
        "client_id": "g1",
        "status": "ended",
        "accepted_at": NOW,
        "ended_at": NOW,
    },
    "consents": {"relationship_id": 1, "scope": "body", "granted_at": NOW, "revoked_at": NOW},
    "profile_entries": {
        "user_id": "g1",
        "height_cm": 181.0,
        "age": 30,
        "sex": "male",
        "activity": "moderate",
        "goal": "maintain",
        "recorded_at": NOW,
    },
    "body_measurements": {
        "user_id": "g1",
        "weight_kg": 80.0,
        "measured_on": DAY,
        "recorded_at": NOW,
    },
    "nutrition_targets": {
        "user_id": "g1",
        "kcal": 2500.0,
        "protein_g": 150.0,
        "carbs_g": 300.0,
        "fat_g": 70.0,
        "set_by": "system",
        "calc_version": "1",
        "effective_from": DAY,
        "created_at": NOW,
    },
    "meal_items": {
        "user_id": "g1",
        "consumed_on": DAY,
        "meal": "lunch",
        "fdc_id": 1,
        "food_name": "Oats",
        "grams": 150.0,
        "kcal": 570.0,
        "protein_g": 20.0,
        "carbohydrate_g": 100.0,
        "fat_g": 10.0,
        "fiber_g": None,
        "recorded_at": NOW,
    },
    "workout_sessions": {"user_id": "g1", "performed_on": DAY, "recorded_at": NOW},
    "exercise_sets": {
        "session_id": 1,
        "exercise_id": "squat",
        "set_no": 2,
        "reps": 5,
        "weight_kg": 100.0,
        "rpe": 8.0,
    },
    "preferences": {"user_id": "g1", "text": "vegetarian", "created_at": NOW},
    "ai_reviews": {
        "client_id": "g1",
        "coach_id": "c1",
        "period_start": DAY,
        "metrics": "{}",
        "data_quality": "{}",
        "draft": "{}",
        "final": None,
        "status": "PENDING_REVIEW",
        "edited_by_coach": 0,
        "model_version": "m",
        "created_at": NOW,
        "reviewed_by": None,
        "reviewed_at": None,
    },
    "ai_evidence_refs": {"review_id": 1, "source_id": "s1", "chunk_id": "s1-0"},
    "audit_log": {
        "actor_id": "c1",
        "subject_id": "g1",
        "action": "read",
        "resource_type": "meal_items",
        "resource_id": None,
        "created_at": NOW,
    },
    "invite_attempts": {"user_id": "g1", "day": DAY, "count": 1},
}
NON_NEGATIVE = [
    ("profile_entries", "age"),
    ("nutrition_targets", "kcal"),
    ("nutrition_targets", "protein_g"),
    ("nutrition_targets", "carbs_g"),
    ("nutrition_targets", "fat_g"),
    ("meal_items", "kcal"),
    ("meal_items", "protein_g"),
    ("meal_items", "carbohydrate_g"),
    ("meal_items", "fat_g"),
    ("meal_items", "fiber_g"),
    ("exercise_sets", "reps"),
    ("exercise_sets", "weight_kg"),
    ("exercise_sets", "rpe"),
    ("invite_attempts", "count"),
]
ABOVE_ZERO = [
    ("profile_entries", "height_cm"),
    ("body_measurements", "weight_kg"),
    ("meal_items", "grams"),
    ("meal_items", "fdc_id"),
]
IMMUTABLE = [
    "profile_entries",
    "body_measurements",
    "nutrition_targets",
    "meal_items",
    "workout_sessions",
    "exercise_sets",
    "preferences",
    "audit_log",
]


def _insert(conn, table, row):
    """Insert one row into a table (test-only SQL built from the test's own names)."""
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(row.values()))


def _seed(conn):
    """Insert the rows the valid rows refer to: users, a relationship, a session, a review."""
    _insert(conn, "users", {"id": "c1", "role": "coach", "display_name": "C", "created_at": NOW})
    _insert(conn, "users", {"id": "g1", "role": "gymer", "display_name": "G", "created_at": NOW})
    _insert(
        conn, "coach_clients", {**VALID_ROWS["coach_clients"], "status": "active", "ended_at": None}
    )
    _insert(conn, "workout_sessions", VALID_ROWS["workout_sessions"])
    _insert(conn, "ai_reviews", VALID_ROWS["ai_reviews"])


def _columns(conn, table):
    """Return the column names of a table."""
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_connect_creates_the_file_in_the_configured_folder_with_every_table(store_conn):
    """A new file is made at config.STORE_PATH and migrated to the latest version."""
    assert config.STORE_PATH.is_file()
    names = {
        row["name"]
        for row in store_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert names == TABLES
    assert db.schema_version(store_conn) == len(schema.MIGRATIONS) == 1


def test_the_store_folder_is_gitignored_and_inside_the_project():
    """The real file lives in data/store/, which .gitignore keeps out of the repo."""
    # conftest points the config at a temporary file, so read the real values from the module text.
    source = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
    assert 'STORE_DIR = PROJECT_ROOT / "data" / "store"' in source
    assert 'STORE_PATH = STORE_DIR / "fitcoach.sqlite3"' in source
    assert "data/store/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_a_given_path_is_used_instead_of_the_config(tmp_path):
    """connect(path) opens that file and makes its folder."""
    path = tmp_path / "nested" / "other.sqlite3"
    with db.connect(path) as conn:
        assert db.schema_version(conn) == 1
    assert path.is_file()
    assert not config.STORE_PATH.exists()


def test_every_table_is_strict(store_conn):
    """A value of the wrong type is refused by every table."""
    strict = {row["name"]: row["strict"] for row in store_conn.execute("PRAGMA table_list")}
    assert all(strict[table] == 1 for table in TABLES)
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(
            store_conn,
            "body_measurements",
            {**VALID_ROWS["body_measurements"], "weight_kg": "heavy"},
        )


def test_foreign_keys_are_on_in_every_connection(store_conn):
    """A row that refers to a missing user is refused."""
    assert store_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _insert(store_conn, "preferences", VALID_ROWS["preferences"])


def test_temporary_data_stays_in_memory(store_conn):
    """temp_store is MEMORY, so SQLite writes no temporary file with stored values."""
    assert store_conn.execute("PRAGMA temp_store").fetchone()[0] == 2


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_the_store_folder_and_file_are_owner_only():
    """The app's folder is 0700 and the file 0600, also when the folder already existed."""
    config.STORE_DIR.mkdir(mode=0o755, parents=True)
    os.chmod(config.STORE_DIR, 0o755)
    with db.connect():
        pass
    assert stat.S_IMODE(config.STORE_DIR.stat().st_mode) == 0o700
    assert stat.S_IMODE(config.STORE_PATH.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_a_file_made_before_the_permissions_were_set_is_made_owner_only():
    """An existing 0644 file (from an older version) is changed to 0600 at the next connect."""
    with db.connect():
        pass
    os.chmod(config.STORE_PATH, 0o644)
    with db.connect():
        pass
    assert stat.S_IMODE(config.STORE_PATH.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_a_failed_chmod_closes_the_store(monkeypatch):
    """If the file cannot be made owner-only, connect() raises and nothing is opened."""

    def refuse(*args, **kwargs):
        """Fail as chmod does on a file owned by another account."""
        raise PermissionError("not ours")

    monkeypatch.setattr(os, "chmod", refuse)
    with pytest.raises(PermissionError):
        with db.connect():
            pytest.fail("the store must not open")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_a_folder_a_caller_passes_keeps_its_permissions(tmp_path):
    """connect(path) makes the file owner-only but leaves an existing folder as it was."""
    os.chmod(tmp_path, 0o755)
    with db.connect(tmp_path / "s.sqlite3"):
        pass
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o755
    assert stat.S_IMODE((tmp_path / "s.sqlite3").stat().st_mode) == 0o600


def test_deleted_rows_are_overwritten_in_the_file(tmp_path):
    """secure_delete is on, so a deleted value is no longer in the file's bytes."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
        _seed(conn)
        _insert(conn, "preferences", {**VALID_ROWS["preferences"], "text": "CANARY-DELETED"})
        conn.execute("DELETE FROM preferences")
    assert b"CANARY-DELETED" not in path.read_bytes()


@pytest.mark.parametrize("table", sorted(TABLES))
def test_every_valid_row_is_accepted(store_conn, table):
    """The test's valid rows really are valid, so the refusals below test one thing each."""
    _seed(store_conn)
    _insert(store_conn, table, VALID_ROWS[table])


@pytest.mark.parametrize(("table", "column"), NON_NEGATIVE + ABOVE_ZERO)
def test_negative_quantities_are_refused(store_conn, table, column):
    """Every quantity column refuses a value below zero."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, table, {**VALID_ROWS[table], column: -1})


@pytest.mark.parametrize(("table", "column"), ABOVE_ZERO)
def test_weights_heights_and_grams_must_be_above_zero(store_conn, table, column):
    """Zero is refused where it means nothing (a weight, a height, grams eaten, a food ID)."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, table, {**VALID_ROWS[table], column: 0})


def _time_columns(conn):
    """Return (table, column) for every timestamp column, by its name."""
    return [
        (table, column)
        for table in sorted(TABLES)
        for column in _columns(conn, table)
        if column.endswith("_at")
    ]


def test_every_timestamp_column_refuses_a_time_that_is_not_utc(store_conn):
    """A local time, or one with another offset, is refused in every *_at column (D21)."""
    columns = _time_columns(store_conn)
    assert len(columns) == 17
    _seed(store_conn)
    for table, column in columns:
        for bad in ("2026-10-27T10:00:00", "2026-10-27T10:00:00+01:00", "27.10.2026 10:00"):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                _insert(store_conn, table, {**VALID_ROWS[table], column: bad})


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("body_measurements", "measured_on"),
        ("nutrition_targets", "effective_from"),
        ("meal_items", "consumed_on"),
        ("workout_sessions", "performed_on"),
        ("ai_reviews", "period_start"),
        ("invite_attempts", "day"),
    ],
)
def test_day_columns_hold_iso_dates_only(store_conn, table, column):
    """A day is YYYY-MM-DD; a timestamp or another format is refused."""
    _seed(store_conn)
    for bad in (NOW, "27.10.2026", "2026-10-7"):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert(store_conn, table, {**VALID_ROWS[table], column: bad})


@pytest.mark.parametrize(
    ("column", "literal"),
    [("sex", profile.Sex), ("activity", profile.ActivityLevel), ("goal", profile.Goal)],
)
def test_profile_choices_match_the_profile_model(store_conn, column, literal):
    """The table accepts exactly the values src/profile.py allows."""
    _seed(store_conn)
    for value in get_args(literal):
        _insert(store_conn, "profile_entries", {**VALID_ROWS["profile_entries"], column: value})
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, "profile_entries", {**VALID_ROWS["profile_entries"], column: "other"})


@pytest.mark.parametrize("table", IMMUTABLE)
def test_stored_records_are_never_changed_in_place(store_conn, table):
    """An UPDATE on a record table is refused by its trigger; only a delete and a new row work."""
    _seed(store_conn)
    _insert(store_conn, table, VALID_ROWS[table])
    column = next(c for c in _columns(store_conn, table) if c != "id")
    with pytest.raises(sqlite3.IntegrityError, match="never changed in place"):
        store_conn.execute(f"UPDATE {table} SET {column} = {column}")


def test_one_active_relationship_per_pair_and_one_open_consent_per_scope(store_conn):
    """A second active relationship, or a second open consent for a scope, is refused."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _insert(
            store_conn,
            "coach_clients",
            {**VALID_ROWS["coach_clients"], "status": "active", "ended_at": None},
        )
    _insert(store_conn, "consents", {**VALID_ROWS["consents"], "revoked_at": None})
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _insert(store_conn, "consents", {**VALID_ROWS["consents"], "revoked_at": None})


def test_a_relationship_with_oneself_is_refused(store_conn):
    """A coach cannot be their own client."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, "coach_clients", {**VALID_ROWS["coach_clients"], "client_id": "c1"})


def test_connecting_again_keeps_the_data_and_the_version(tmp_path):
    """A second connect() runs no migration again and finds the rows of the first."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        _seed(conn)
    with db.connect(path) as conn:
        assert db.schema_version(conn) == 1
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2


def test_a_file_from_a_newer_version_is_refused(tmp_path):
    """A schema version above the code's migrations raises StoreError and changes nothing."""
    path = tmp_path / "s.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 99")
    raw.close()
    with pytest.raises(db.StoreError, match="newer version"):
        with db.connect(path):
            pass
    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 99
    raw.close()


def test_a_failing_migration_leaves_the_file_as_it_was(tmp_path, monkeypatch):
    """A migration that fails halfway is rolled back: no table and version 0."""
    broken = (
        "CREATE TABLE a (x INTEGER) STRICT; CREATE TABLE a (x INTEGER); PRAGMA user_version = 1;"
    )
    monkeypatch.setattr(db, "MIGRATIONS", (broken,))
    path = tmp_path / "s.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        with db.connect(path):
            pass
    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    assert raw.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0
    raw.close()


def test_a_transaction_rolls_back_on_error(store_conn):
    """Everything written in a transaction that raises is undone."""
    with pytest.raises(RuntimeError):
        with db.transaction(store_conn):
            _seed(store_conn)
            raise RuntimeError("stop")
    assert store_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0


def test_the_connection_is_closed_after_the_block(tmp_path):
    """connect() closes its connection, also when the block raises."""
    with pytest.raises(RuntimeError):
        with db.connect(tmp_path / "s.sqlite3") as conn:
            raise RuntimeError("stop")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


# --- values: what the store functions check before writing ----------------------------------------


def test_utc_text_converts_to_utc_and_refuses_a_naive_time():
    """An aware time is written in UTC with +00:00; a naive one is refused."""
    berlin_summer = timezone(timedelta(hours=2))
    assert values.utc_text(datetime(2026, 7, 1, 12, 0, tzinfo=berlin_summer)) == (
        "2026-07-01T10:00:00+00:00"
    )
    assert values.utc_text().endswith("+00:00")
    with pytest.raises(values.StoreValueError):
        values.utc_text(datetime(2026, 7, 1, 12, 0))


def test_date_text_takes_a_date_only():
    """A date is written as ISO text; a datetime or text is refused."""
    assert values.date_text(date(2026, 1, 5), "day") == "2026-01-05"
    for bad in (datetime(2026, 1, 5, tzinfo=UTC), "2026-01-05"):
        with pytest.raises(values.StoreValueError):
            values.date_text(bad, "day")


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), -float("inf"), -0.1, True, "1", None, 10**400]
)
def test_number_refuses_what_is_not_a_finite_non_negative_number(bad):
    """NaN, infinities, negatives, booleans, text and huge integers are refused, value unnamed."""
    with pytest.raises(values.StoreValueError) as caught:
        values.number(bad, "grams")
    assert str(caught.value).startswith("grams ")
    assert repr(bad) not in str(caught.value)


def test_number_with_positive_refuses_zero():
    """Zero passes as a quantity and fails where the value must be above zero."""
    assert values.number(0, "kcal") == 0.0
    with pytest.raises(values.StoreValueError, match="above zero"):
        values.number(0, "grams", positive=True)


@pytest.mark.parametrize("bad", ["", "   ", 5, None, "x" * (config.STORE_TEXT_MAX_CHARS + 1)])
def test_text_refuses_empty_long_or_non_text(bad):
    """Empty, blank, too long or non-text values are refused."""
    with pytest.raises(values.StoreValueError):
        values.text(bad, "text")


@pytest.mark.parametrize("bad", ["", 5, None, "x" * (config.STORE_ID_MAX_CHARS + 1)])
def test_user_id_refuses_empty_long_or_non_text(bad):
    """A user ID is non-empty text within the limit."""
    with pytest.raises(values.StoreValueError):
        values.user_id(bad)


def test_the_error_message_names_the_field_and_a_fixed_problem():
    """str() joins the field and the problem; the arguments are the same two texts."""
    error = values.StoreValueError("weight_kg", "must be above zero")
    assert str(error) == "weight_kg must be above zero"
    assert error.args == ("weight_kg", "must be above zero")


def test_a_transaction_inside_another_is_refused(store_conn):
    """Nesting raises StoreError with a fixed message, and the outer transaction rolls back."""
    with pytest.raises(db.StoreError, match="inside another"):
        with db.transaction(store_conn):
            _seed(store_conn)
            with db.transaction(store_conn):
                pass
    assert not store_conn.in_transaction
    assert store_conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0


def test_an_error_after_sqlite_rolled_back_keeps_the_real_error(store_conn):
    """When the block already ended the transaction, the block's own error is what is raised."""
    with pytest.raises(RuntimeError, match="the real error"):
        with db.transaction(store_conn):
            store_conn.execute("ROLLBACK")  # as SQLite does on a full disk or an I/O error
            raise RuntimeError("the real error")
    assert not store_conn.in_transaction


def test_a_failed_commit_leaves_no_open_transaction(tmp_path):
    """If COMMIT fails (here: a reader holds the file), the transaction is rolled back."""
    path = tmp_path / "s.sqlite3"
    with db.connect(path) as conn:
        _seed(conn)
        reader = sqlite3.connect(path, timeout=0)
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM users").fetchall()  # holds a SHARED lock
        conn.execute("PRAGMA busy_timeout = 0")
        with pytest.raises(sqlite3.OperationalError):
            with db.transaction(conn):
                conn.execute("DELETE FROM preferences")
                conn.execute("DELETE FROM audit_log")
                conn.execute(
                    "INSERT INTO users (id, role, display_name, created_at) VALUES (?, ?, ?, ?)",
                    ("g9", "gymer", "G9", NOW),
                )
        reader.close()
        assert not conn.in_transaction
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2


@pytest.mark.parametrize(
    ("table", "column", "bad"),
    [
        ("body_measurements", "measured_on", "2026-02-30"),
        ("body_measurements", "measured_on", "2026-13-45"),
        ("body_measurements", "recorded_at", "2026-99-99T+00:00"),
        ("body_measurements", "recorded_at", "2026-10-27T25:00:00+00:00"),
        ("body_measurements", "recorded_at", "2026-02-30T10:00:00+00:00"),
    ],
)
def test_a_day_or_time_that_does_not_exist_is_refused(store_conn, table, column, bad):
    """The shape is not enough: the day and the time must parse."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, table, {**VALID_ROWS[table], column: bad})


def test_a_decided_review_is_never_changed(store_conn):
    """The pending review can be decided; once decided, any UPDATE is refused."""
    _seed(store_conn)
    decide = "UPDATE ai_reviews SET status = 'REJECTED', reviewed_by = 'c1', reviewed_at = ?"
    store_conn.execute(decide, (NOW,))
    with pytest.raises(sqlite3.IntegrityError, match="never changed"):
        store_conn.execute("UPDATE ai_reviews SET status = 'PENDING_REVIEW' WHERE id = 1")
