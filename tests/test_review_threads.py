"""The weekly review's checkpointer file (T9.16, D12): where it is, deleting a user's threads."""

import dataclasses
import sqlite3
from typing import TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src import config
from src.agent import review_threads
from src.store import my_data
from tests import store_world as world

ROOT = config.PROJECT_ROOT
CANARY = "CANARY-THREAD-7342"


class _State(TypedDict, total=False):
    """A tiny state that holds one text, as a review's metrics would."""

    text: str


BUILT: list[str] = []


@dataclasses.dataclass
class _Planted:
    """A class an attacker could name in the threads file: building it records the build."""

    note: str

    def __post_init__(self) -> None:
        """Record that the class was built (in a real attack: run the attacker's code)."""
        BUILT.append(self.note)


def _hold(state: _State) -> dict:
    """Wait for a decision, as the review's decide node does."""
    interrupt({"waiting": True})
    return {}


def _graph(saver):
    """Return a one-node graph that pauses, as the review's decide node does."""
    builder = StateGraph(_State)
    builder.add_node("hold", _hold)
    builder.add_edge(START, "hold")
    builder.add_edge("hold", END)
    return builder.compile(checkpointer=saver)


def _paused_run(saver, thread_id: str, coach: str, client: str, text: object = None) -> None:
    """Run a one-node graph to its pause, with the coach and client as checkpoint metadata."""
    _graph(saver).invoke(
        {"text": f"{CANARY} {thread_id}" if text is None else text},
        {
            "configurable": {"thread_id": thread_id},
            "metadata": {review_threads.COACH_KEY: coach, review_threads.CLIENT_KEY: client},
        },
    )


def _threads(store_path) -> set[str]:
    """Return every thread in the checkpointer file."""
    with review_threads.open_saver(store_path) as saver:
        return {c.config["configurable"]["thread_id"] for c in saver.list(None)}


def test_the_file_sits_next_to_the_store_in_the_gitignored_folder():
    """The checkpointer file is in the store's folder, data/store/, which .gitignore keeps out."""
    assert review_threads.threads_path(config.STORE_PATH).parent == config.STORE_PATH.parent
    source = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
    assert 'STORE_DIR = PROJECT_ROOT / "data" / "store"' in source
    assert "data/store/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_a_demo_store_gets_its_own_threads_file(tmp_path):
    """Another store file (the demo's temporary one) gets the threads file beside it."""
    demo = tmp_path / "demo.sqlite3"
    assert review_threads.threads_path(demo) == tmp_path / config.REVIEW_THREADS_FILE_NAME


def test_thread_ids_are_new_each_time():
    """Every run gets its own random thread."""
    ids = {review_threads.new_thread_id() for _ in range(50)}
    assert len(ids) == 50 and all(i.startswith("review-") for i in ids)


def test_a_paused_run_survives_closing_the_file():
    """A thread written in one unit of work is read back in the next (a restart)."""
    with review_threads.open_saver(config.STORE_PATH) as saver:
        _paused_run(saver, "t-1", world.COACH_A, world.SHARED)
    assert _threads(config.STORE_PATH) == {"t-1"}


def test_the_saver_refuses_classes_outside_the_safe_list():
    """A class planted in the threads file is never built when the run is read back."""
    BUILT.clear()
    # The attacker writes the file with LangGraph's default, permissive serializer.
    path = review_threads.threads_path(config.STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        attacker = SqliteSaver(conn)
        attacker.setup()
        _paused_run(attacker, "t-planted", world.COACH_A, world.SHARED, _Planted("planted"))
    finally:
        conn.close()
    BUILT.clear()
    with review_threads.open_saver(config.STORE_PATH) as saver:
        state = _graph(saver).get_state({"configurable": {"thread_id": "t-planted"}})
    assert BUILT == []
    assert not isinstance(state.values.get("text"), _Planted)


def test_a_paused_run_reads_back_with_the_strict_serializer():
    """A review run's plain values and its pause survive the strict serializer."""
    with review_threads.open_saver(config.STORE_PATH) as saver:
        _paused_run(saver, "t-plain", world.COACH_A, world.SHARED)
    with review_threads.open_saver(config.STORE_PATH) as saver:
        state = _graph(saver).get_state({"configurable": {"thread_id": "t-plain"}})
    assert state.values["text"] == f"{CANARY} t-plain"
    assert state.next == ("hold",) and state.tasks[0].interrupts


@pytest.mark.parametrize(
    ("user", "left"),
    [
        (world.SHARED, {"t-others"}),
        (world.COACH_A, {"t-others"}),
        (world.OTHERS, {"t-shared", "t-crashed"}),
        (world.COACH_B, {"t-shared", "t-crashed"}),
    ],
)
def test_delete_for_user_removes_every_thread_about_or_by_them(user, left):
    """The client's and the coach's threads go, a crashed run's with no review included."""
    with review_threads.open_saver(config.STORE_PATH) as saver:
        _paused_run(saver, "t-shared", world.COACH_A, world.SHARED)
        _paused_run(saver, "t-crashed", world.COACH_A, world.SHARED)
        _paused_run(saver, "t-others", world.COACH_B, world.OTHERS)
    review_threads.delete_for_user(config.STORE_PATH, user)
    assert _threads(config.STORE_PATH) == left


def test_delete_for_user_also_removes_the_listed_threads():
    """A thread the store names is deleted even if its metadata named nobody."""
    with review_threads.open_saver(config.STORE_PATH) as saver:
        _paused_run(saver, "t-listed", "someone", "someone-else")
    review_threads.delete_for_user(config.STORE_PATH, world.SHARED, ["t-listed"])
    assert _threads(config.STORE_PATH) == set()


def test_deleted_state_is_gone_from_the_files_bytes():
    """secure_delete and the WAL checkpoint leave no trace of the deleted state on disk."""
    with review_threads.open_saver(config.STORE_PATH) as saver:
        _paused_run(saver, "t-shared", world.COACH_A, world.SHARED)
    review_threads.delete_for_user(config.STORE_PATH, world.SHARED)
    path = review_threads.threads_path(config.STORE_PATH)
    for file in path.parent.glob(path.name + "*"):
        assert CANARY.encode() not in file.read_bytes(), file.name


def test_deleting_a_users_data_deletes_their_threads(store_conn):
    """my_data.delete_user_data() with the threads callback removes the user's threads (AC-34)."""
    world.build(store_conn)
    with review_threads.open_saver(config.STORE_PATH) as saver:
        _paused_run(saver, "t-shared", world.COACH_A, world.SHARED)
        _paused_run(saver, "t-others", world.COACH_B, world.OTHERS)
    my_data.delete_user_data(
        store_conn,
        world.SHARED,
        lambda threads: review_threads.delete_for_user(config.STORE_PATH, world.SHARED, threads),
    )
    assert _threads(config.STORE_PATH) == {"t-others"}
