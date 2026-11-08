"""The store's file, schema and migrations (T9.6): tables, foreign keys, checks, UTC, no updates."""

import os
import re
import sqlite3
import stat
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

import pytest

from src import config, profile
from src.store import access, db, schema, values

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
    "ai_review_scopes",
    "audit_log",
    "invite_attempts",
    "review_questions",
    "notification_reads",
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
    "ai_review_scopes": {"review_id": 1, "scope": "training"},
    "audit_log": {
        "actor_id": "c1",
        "subject_id": "g1",
        "action": "read",
        "resource_type": "meal_items",
        "resource_id": None,
        "created_at": NOW,
    },
    "invite_attempts": {"user_id": "g1", "day": DAY, "count": 1},
    "review_questions": {
        "review_id": 1,
        "author_id": "g1",
        "kind": "question",
        "text": "Why fewer carbs?",
        "created_at": NOW,
    },
    "notification_reads": {"user_id": "g1", "read_up_to": NOW},
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
    "review_questions",
    "notification_reads",
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
    assert db.schema_version(store_conn) == len(schema.MIGRATIONS) == 5


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
        assert db.schema_version(conn) == len(schema.MIGRATIONS)
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
    """temp_store is MEMORY, and this SQLite build honours it (not compiled with TEMP_STORE=0)."""
    assert store_conn.execute("PRAGMA temp_store").fetchone()[0] == 2
    options = {row[0] for row in store_conn.execute("PRAGMA compile_options")}
    # TEMP_STORE=0 always uses files and ignores the pragma; 1 (the default) and 2 honour it.
    assert "TEMP_STORE=0" not in options


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
    """If the file cannot be made owner-only, connect() raises StoreError and opens nothing."""

    def refuse(*args, **kwargs):
        """Fail as chmod does on a file owned by another account."""
        raise PermissionError("not ours")

    monkeypatch.setattr(os, "chmod", refuse)
    with pytest.raises(db.StoreError, match="folder or permissions could not be set") as caught:
        with db.connect():
            pytest.fail("the store must not open")
    # The OS error, whose text names the path, is neither the cause nor the context.
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_a_folder_that_cannot_be_made_closes_the_store(monkeypatch):
    """If mkdir fails (here with a path in its text), connect() raises StoreError, path-free."""

    def refuse(*args, **kwargs):
        """Fail as mkdir does on a read-only parent, naming the path."""
        raise PermissionError(13, "Permission denied", "CANARY-PATH/data/store")

    monkeypatch.setattr(Path, "mkdir", refuse)
    with pytest.raises(db.StoreError) as caught:
        with db.connect():
            pytest.fail("the store must not open")
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "CANARY-PATH" not in str(caught.value) + repr(caught.value)


def test_a_file_where_the_folder_should_be_closes_the_store():
    """A file named like the store's folder makes connect() raise StoreError, on every OS."""
    config.STORE_DIR.parent.mkdir(parents=True, exist_ok=True)
    config.STORE_DIR.write_text("not a folder", encoding="utf-8")
    with pytest.raises(db.StoreError, match="could not be set") as caught:
        with db.connect():
            pytest.fail("the store must not open")
    assert caught.value.__context__ is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_the_file_is_private_before_sqlite_opens_it(monkeypatch):
    """With an existing 0755 folder, the folder is 0700 and the file 0600 when SQLite opens it."""
    config.STORE_DIR.mkdir(mode=0o755, parents=True)
    os.chmod(config.STORE_DIR, 0o755)
    seen = []
    real_connect = sqlite3.connect

    def watching(path, *args, **kwargs):
        """Record the folder's and the file's modes at the moment SQLite opens the file."""
        seen.append(
            (stat.S_IMODE(config.STORE_DIR.stat().st_mode), stat.S_IMODE(Path(path).stat().st_mode))
        )
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(db.sqlite3, "connect", watching)
    with db.connect():
        pass
    assert seen == [(0o700, 0o600)]


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_an_existing_database_is_never_opened_outside_sqlite(monkeypatch):
    """A second connect() opens no descriptor of the existing file (closing one drops locks)."""
    with db.connect():
        pass
    opened = []
    real_open = os.open

    def watching(path, *args, **kwargs):
        """Record every path os.open returns a descriptor for (a refused O_EXCL opens none)."""
        descriptor = real_open(path, *args, **kwargs)
        opened.append(Path(path))
        return descriptor

    monkeypatch.setattr(db.os, "open", watching)
    with db.connect():
        pass
    assert config.STORE_PATH not in opened


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
def test_a_read_only_database_is_made_0600_and_opens():
    """An existing 0400 file (made read-only by hand) still opens and ends at 0600."""
    with db.connect():
        pass
    os.chmod(config.STORE_PATH, 0o400)
    with db.connect() as conn:
        assert db.schema_version(conn) == len(schema.MIGRATIONS)
    assert stat.S_IMODE(config.STORE_PATH.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses profile ACLs")
@pytest.mark.parametrize("refused", ["open", "chmod"])
def test_a_file_that_cannot_be_made_private_closes_the_store(tmp_path, monkeypatch, refused):
    """For a caller's path (no folder chmod), a refused os.open or chmod raises StoreError."""

    def refuse(*args, **kwargs):
        """Fail as the OS does on a file owned by another account."""
        raise PermissionError(13, "Permission denied", "CANARY-PATH")

    monkeypatch.setattr(db.os, refused, refuse)
    with pytest.raises(db.StoreError) as caught:
        with db.connect(tmp_path / "s.sqlite3"):
            pytest.fail("the store must not open")
    assert caught.value.__context__ is None
    assert "CANARY-PATH" not in str(caught.value) + repr(caught.value)


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
    assert len(columns) == 18  # review_questions.created_at since T9.25
    _seed(store_conn)
    for table, column in columns:
        for bad in ("2026-10-27T10:00:00", "2026-10-27T10:00:00+01:00", "27.10.2026 10:00"):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                _insert(store_conn, table, {**VALID_ROWS[table], column: bad})


def test_a_read_mark_holds_a_utc_time_only(store_conn):
    """notification_reads.read_up_to refuses a local time, another offset or a day (T9.29, D21)."""
    _seed(store_conn)
    for bad in (
        "2026-10-27T10:00:00",
        "2026-10-27T10:00:00+01:00",
        DAY,
        "2026-02-30T10:00:00+00:00",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert(store_conn, "notification_reads", {"user_id": "g1", "read_up_to": bad})


def test_a_version_2_file_gets_the_read_mark_table_with_its_data_kept(tmp_path):
    """Migration 3 (T9.29) adds notification_reads, empty, and keeps the rows already there."""
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema.MIGRATIONS[0])
    conn.executescript(schema.MIGRATIONS[1])
    _seed(conn)
    conn.close()
    with db.connect(path) as conn:
        assert db.schema_version(conn) == len(schema.MIGRATIONS)
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM notification_reads").fetchone()[0] == 0


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
        assert db.schema_version(conn) == len(schema.MIGRATIONS)
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


def test_a_version_1_file_gets_its_reviews_filed_under_nutrition(tmp_path):
    """Migration 2 (T9.16) gives an older review the nutrition scope and no thread, data kept."""
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema.MIGRATIONS[0])
    _seed(conn)
    conn.close()
    with db.connect(path) as conn:
        assert db.schema_version(conn) == len(schema.MIGRATIONS)
        rows = conn.execute("SELECT review_id, scope FROM ai_review_scopes")
        scopes = [tuple(row) for row in rows]
        assert scopes == [(1, "nutrition")]
        assert conn.execute("SELECT thread_id FROM ai_reviews").fetchone()[0] is None


@pytest.mark.parametrize("bad", ["", "lunch"])
def test_a_review_scope_must_be_a_known_scope(store_conn, bad):
    """ai_review_scopes refuses an empty or unknown scope."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, "ai_review_scopes", {"review_id": 1, "scope": bad})


def test_an_empty_thread_id_is_refused(store_conn):
    """A review's thread_id is NULL or a non-empty text."""
    _seed(store_conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(store_conn, "ai_reviews", {**VALID_ROWS["ai_reviews"], "thread_id": ""})


# --- Migration 4 (T9.25): the questions table and audit_log rebuilt with review_answered ----------


def _audit_table_sql(text: str) -> str:
    """Return audit_log's CREATE TABLE statement with its action list taken out, normalised."""
    # ALTER TABLE ... RENAME writes the new name quoted.
    text = text.replace('CREATE TABLE "audit_log"', "CREATE TABLE audit_log")
    start = text.index("CREATE TABLE audit_log")
    end = text.find(") STRICT", start)
    statement = text[start : len(text) if end < 0 else end + len(") STRICT")]
    statement = re.sub(r"action IN \([^)]*\)", "action IN (...)", statement)
    return " ".join(statement.split())


def _check_actions(conn) -> tuple[str, ...]:
    """Return the actions audit_log's CHECK lists, in order."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'audit_log'").fetchone()[0]
    found = re.search(r"action IN \(([^)]*)\)", sql)
    return tuple(re.findall(r"'([a-z_]+)'", found.group(1)))


def _old_file(path: Path, migrations: int):
    """Write a store file at an older version with two audit rows; return the rows."""
    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for script in schema.MIGRATIONS[:migrations]:
        conn.executescript(script)
    _seed(conn)
    _insert(conn, "audit_log", VALID_ROWS["audit_log"])
    _insert(conn, "audit_log", {**VALID_ROWS["audit_log"], "action": "review_rejected"})
    rows = [tuple(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]
    conn.close()
    return rows


def test_the_rebuilt_audit_table_is_v1_s_apart_from_the_action_list(store_conn):
    """STRICT, both foreign keys and the created_at check stay; only the action list grows."""
    built = store_conn.execute("SELECT sql FROM sqlite_master WHERE name = 'audit_log'").fetchone()
    assert _audit_table_sql(built[0]) == _audit_table_sql(schema._V1)
    assert _check_actions(store_conn) == (*get_args(access.Action),)
    keys = {row["from"] for row in store_conn.execute("PRAGMA foreign_key_list(audit_log)")}
    assert keys == {"actor_id", "subject_id"}


def test_the_audit_check_and_access_action_list_the_same_actions(store_conn):
    """A new action is added in both places, or neither."""
    assert set(_check_actions(store_conn)) == set(get_args(access.Action))
    assert {"review_answered", "target_set"} <= set(get_args(access.Action))


@pytest.mark.parametrize("migrations", [1, 2, 3, 4])
def test_upgrading_an_older_file_keeps_every_audit_row_index_and_trigger(tmp_path, migrations):
    """A version 1 to 4 file with audit rows reaches version 5, its rows, IDs and guards kept."""
    path = tmp_path / "old.sqlite3"
    before = _old_file(path, migrations)
    with db.connect(path) as conn:
        assert db.schema_version(conn) == len(schema.MIGRATIONS) == 5
        after = [tuple(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]
        assert after == before
        indexes = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE tbl_name = 'audit_log'")
        }
        assert {"audit_log_actor", "audit_log_subject", "audit_log_never_changed"} <= indexes
        with pytest.raises(sqlite3.IntegrityError, match="never changed in place"):
            conn.execute("UPDATE audit_log SET resource_type = 'x'")
        _insert(conn, "audit_log", {**VALID_ROWS["audit_log"], "action": "review_answered"})
        _insert(conn, "audit_log", {**VALID_ROWS["audit_log"], "action": "target_set"})
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert(conn, "audit_log", {**VALID_ROWS["audit_log"], "action": "deleted"})
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert "review_questions" in {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master")
        }


def test_a_question_kind_must_be_question_or_answer(store_conn):
    """review_questions refuses another kind and an empty text."""
    _seed(store_conn)
    for bad in ({"kind": "note"}, {"text": ""}):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            _insert(store_conn, "review_questions", {**VALID_ROWS["review_questions"], **bad})


def test_a_question_refers_to_a_review_and_a_user(store_conn):
    """A question under a missing review, or by a missing user, is refused by its foreign keys."""
    _seed(store_conn)
    for bad in ({"review_id": 99}, {"author_id": "nobody"}):
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            _insert(store_conn, "review_questions", {**VALID_ROWS["review_questions"], **bad})


def test_a_migration_4_that_fails_halfway_leaves_the_version_3_file_as_it_was(tmp_path):
    """A clash part-way through migration 4 rolls all of it back: version 3, audit rows kept."""
    path = tmp_path / "old.sqlite3"
    before = _old_file(path, 3)
    raw = sqlite3.connect(path, autocommit=True)
    # A table with the name migration 4 builds audit_log under makes its CREATE fail after
    # review_questions and its trigger were made in the same transaction.
    raw.execute("CREATE TABLE audit_log_v4 (x INTEGER) STRICT")
    raw.close()
    with pytest.raises(sqlite3.OperationalError):
        with db.connect(path):
            pass
    raw = sqlite3.connect(path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 3
        names = {row[0] for row in raw.execute("SELECT name FROM sqlite_master")}
        assert "review_questions" not in names and "audit_log_never_changed" in names
        assert [tuple(row) for row in raw.execute("SELECT * FROM audit_log ORDER BY id")] == before
    finally:
        raw.close()


def test_a_migration_5_that_fails_halfway_leaves_the_version_4_file_as_it_was(tmp_path):
    """A clash part-way through migration 5 (T9.17) rolls it back: version 4, audit rows kept."""
    path = tmp_path / "old.sqlite3"
    before = _old_file(path, 4)
    raw = sqlite3.connect(path, autocommit=True)
    # The name migration 5 builds audit_log under is taken, so its CREATE fails.
    raw.execute("CREATE TABLE audit_log_v5 (x INTEGER) STRICT")
    raw.close()
    with pytest.raises(sqlite3.OperationalError):
        with db.connect(path):
            pass
    raw = sqlite3.connect(path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 4
        sql = raw.execute("SELECT sql FROM sqlite_master WHERE name = 'audit_log'").fetchone()[0]
        assert "target_set" not in sql
        assert [tuple(row) for row in raw.execute("SELECT * FROM audit_log ORDER BY id")] == before
    finally:
        raw.close()
