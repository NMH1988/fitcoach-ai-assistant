"""The weekly review workflow's threads: a SqliteSaver file next to the store (T9.16, D12).

One thread per review run. A run that waits for the coach's decision keeps its state here, so the
review survives a restart; the state holds the client's week as aggregates, the evidence chunks and
the draft (never a name or a chat message). Every checkpoint carries the coach's and the client's
IDs as metadata, so deleting a user's data deletes every thread about them or by them, a run that
crashed before its review was saved included (AC-34). A run's thread is deleted as soon as the run
ends (no review, a refusal, or the coach's decision), so only pending reviews keep one.

The file is prepared like the store's (owner-only on POSIX), opened per unit of work with
`secure_delete` on, and checkpointed out of its write-ahead log after a delete, so deleted state is
overwritten in the file and not left in the `-wal` file (docs/SECURITY.md).
"""

import sqlite3
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from src import config
from src.store import db

# The metadata keys every checkpoint of a run carries (the run's config, src/agent/review.py).
COACH_KEY = "coach_id"
CLIENT_KEY = "client_id"
_SECURE_DELETE_ON = "PRAGMA secure_delete = ON"
_CHECKPOINT_WAL = "PRAGMA wal_checkpoint(TRUNCATE)"


def threads_path(store_path: Path) -> Path:
    """Return the checkpointer file that belongs to the store file."""
    return store_path.with_name(config.REVIEW_THREADS_FILE_NAME)


def new_thread_id() -> str:
    """Return a new, random thread ID for one review run."""
    return f"review-{uuid.uuid4().hex}"


@contextmanager
def open_saver(store_path: Path) -> Iterator[SqliteSaver]:
    """Open the checkpointer file next to the store, set up, and close it after the block."""
    target = threads_path(store_path)
    db.prepare_file(target, own_folder=store_path == config.STORE_PATH)
    # SqliteSaver serialises its own use of the connection with a lock; Streamlit may run the
    # graph's nodes on another thread than the one that opened it.
    conn = sqlite3.connect(
        target, check_same_thread=False, timeout=config.STORE_BUSY_TIMEOUT_SECONDS
    )
    try:
        conn.execute(_SECURE_DELETE_ON)
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def _threads_of(saver: SqliteSaver, user_id: str) -> set[str]:
    """Return the threads whose checkpoints name the user as the coach or the client."""
    found: set[str] = set()
    for key in (COACH_KEY, CLIENT_KEY):
        for checkpoint in saver.list(None, filter={key: user_id}):
            found.add(checkpoint.config["configurable"]["thread_id"])
    return found


def delete_threads(saver: SqliteSaver, thread_ids: Iterable[str]) -> None:
    """Delete the threads and move the deletion out of the write-ahead log."""
    for thread_id in thread_ids:
        saver.delete_thread(thread_id)
    saver.conn.execute(_CHECKPOINT_WAL)


def delete_for_user(store_path: Path, user_id: str, thread_ids: Iterable[str] = ()) -> None:
    """Delete the given threads and every thread about or by the user (my_data's callback)."""
    with open_saver(store_path) as saver:
        delete_threads(saver, set(thread_ids) | _threads_of(saver, user_id))
