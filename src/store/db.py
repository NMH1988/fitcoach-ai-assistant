"""Opening the store: a SQLite connection with foreign keys on, migrated to its schema (T9.6).

The connection is opened in autocommit mode, so the module's `transaction()` is the only place a
transaction starts or ends: every store function that writes (an audit row counts) runs inside one,
and an error rolls the whole of it back. Open a connection per unit of work with `connect()`;
Streamlit runs each session in its own thread, and a connection is not shared between threads.
Every transaction takes the write lock (`BEGIN IMMEDIATE`), reads included, so sessions use the
file one at a time: fine for a local app, and it keeps a read and its audit row together.
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src import config
from src.store.schema import MIGRATIONS

_FOREIGN_KEYS_ON = "PRAGMA foreign_keys = ON"
# Deleted rows are overwritten with zeros instead of left in the file's free pages, so a deleted
# entry cannot be read back from a copy of the file (docs/SECURITY.md).
_SECURE_DELETE_ON = "PRAGMA secure_delete = ON"
# Temporary tables and indices stay in memory, so no temporary file holds stored values
# (the rollback journal of a write in progress still holds old pages).
_TEMP_STORE_MEMORY = "PRAGMA temp_store = MEMORY"
# Owner-only permissions on POSIX, so other accounts on a shared computer cannot read the
# store; Windows applies the user profile's access rules instead (docs/SECURITY.md).
_PRIVATE_FOLDER = 0o700
_PRIVATE_FILE = 0o600
_SCHEMA_VERSION = "PRAGMA user_version"
# IMMEDIATE takes the write lock at once, so two sessions migrating (or writing) at the same time
# wait for each other (up to the busy timeout) instead of failing halfway.
_BEGIN = "BEGIN IMMEDIATE"
_COMMIT = "COMMIT"
_ROLLBACK = "ROLLBACK"


# The one message for a store file that cannot be prepared: an OS error's text names the path.
_CANNOT_PREPARE = "The data file's folder or permissions could not be set."


class StoreError(RuntimeError):
    """Raised when the store file cannot be used, e.g. it has a newer schema than this code."""


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the block in one transaction: commit at the end, roll back on any error."""
    if conn.in_transaction:
        # SQLite would only say "cannot start a transaction within a transaction".
        raise StoreError("A store transaction was opened inside another one.")
    conn.execute(_BEGIN)
    try:
        yield conn
        conn.execute(_COMMIT)
    except BaseException:
        # SQLite may have rolled back already (a full disk, an I/O error); a second ROLLBACK
        # would raise and hide the real error. A failed COMMIT leaves the transaction open.
        if conn.in_transaction:
            conn.execute(_ROLLBACK)
        raise


def schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version the database is at (0 for a new file)."""
    return conn.execute(_SCHEMA_VERSION).fetchone()[0]


def migrate(conn: sqlite3.Connection) -> None:
    """Run the migrations the database has not had yet, all in one transaction."""
    with transaction(conn):
        version = schema_version(conn)
        if version > len(MIGRATIONS):
            raise StoreError("The data file was written by a newer version of the app.")
        for script in MIGRATIONS[version:]:
            conn.executescript(script)


def _make_folder(folder: Path) -> bool:
    """Make the store's folder (owner-only where the OS applies the mode); False if refused."""
    try:
        folder.mkdir(mode=_PRIVATE_FOLDER, parents=True, exist_ok=True)
    except OSError:  # e.g. the folder's name is taken by a file, or its parent is read-only
        return False
    return True


def _make_owner_only(target: Path, own_folder: bool) -> bool:
    """On POSIX, make the folder 0700 and the file 0600 before SQLite opens it; False if refused."""
    # mkdir's mode is masked by the umask and leaves an existing folder as it was, so the folder
    # is set first (only the app's own, never a folder a caller passed), then the file is made with
    # 0600 if it is new, and set to 0600 if it was made by an older version: no other account can
    # open the file between its creation and the chmod.
    try:
        if own_folder:
            os.chmod(target.parent, _PRIVATE_FOLDER)
        os.close(os.open(target, os.O_CREAT | os.O_WRONLY, _PRIVATE_FILE))
        os.chmod(target, _PRIVATE_FILE)
    except OSError:
        return False
    return True


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open the store (config.STORE_PATH by default), migrate it, and close it after the block."""
    target = config.STORE_PATH if path is None else path
    # Fail closed with one fixed message: a folder that cannot be made, or a file that cannot be
    # made owner-only, is never used. StoreError is raised outside the `except`, so the OS error
    # (whose text and filename name the path) is not even its __context__ (T9.5 catches StoreError).
    if not _make_folder(target.parent):
        raise StoreError(_CANNOT_PREPARE)
    if os.name == "posix" and not _make_owner_only(target, own_folder=path is None):
        raise StoreError(_CANNOT_PREPARE)
    conn = sqlite3.connect(target, timeout=config.STORE_BUSY_TIMEOUT_SECONDS, autocommit=True)
    try:
        conn.row_factory = sqlite3.Row
        # Off by default in SQLite, and set per connection: without it no reference is checked.
        conn.execute(_FOREIGN_KEYS_ON)
        conn.execute(_SECURE_DELETE_ON)
        conn.execute(_TEMP_STORE_MEMORY)
        migrate(conn)
        yield conn
    finally:
        conn.close()
