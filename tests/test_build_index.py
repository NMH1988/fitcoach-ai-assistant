"""Tests for scripts/build_index.py with fake chunks and embeddings (the real run is O5)."""

import httpx2
import pytest

from scripts import build_index
from src import config, llm
from src.rag import store
from src.rag.ingest import IngestError
from tests.test_store import CHUNKS, SpyEmbeddings

FAKE_KEY = "sk-test-not-a-real-key"


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    """Point the index at a temp directory and return it."""
    path = tmp_path / "chroma"
    monkeypatch.setattr(config, "CHROMA_DIR", path)
    return path


def _use(monkeypatch, chunks=CHUNKS, embeddings=None):
    """Make the script read the given chunks and embed them with the given client."""
    monkeypatch.setattr(build_index, "load_chunks", lambda: list(chunks))
    monkeypatch.setattr(llm, "build_embeddings", lambda: embeddings or SpyEmbeddings())


def test_the_script_builds_the_index_and_prints_a_summary(monkeypatch, capsys, index_dir):
    """All chunks are embedded in batches into chroma/, with progress and a summary printed."""
    monkeypatch.setattr(config, "EMBEDDING_BATCH_SIZE", 2)
    _use(monkeypatch)
    assert build_index.main() == 0
    out = capsys.readouterr().out
    assert "Embedded 2/5 chunks" in out
    assert "Embedded 5/5 chunks" in out
    assert f"Indexed 5 chunks from 3 sources ({sum(len(c.page_content) for c in CHUNKS):,}" in out
    assert config.EMBEDDING_MODEL in out
    assert store.check_index(index_dir) == len(CHUNKS)


def test_missing_articles_stop_the_build(monkeypatch, capsys, index_dir):
    """An ingest error (e.g. articles not downloaded) is printed and no index is written."""

    def fail():
        """Raise the error load_chunks() gives for a missing article."""
        raise IngestError("Cannot build the chunks:\n- #1 (PMC1): missing or unreadable")

    monkeypatch.setattr(build_index, "load_chunks", fail)
    assert build_index.main() == 1
    assert "missing or unreadable" in capsys.readouterr().err
    assert not index_dir.exists()


def test_an_unwritable_index_directory_fails_cleanly(monkeypatch, capsys, tmp_path):
    """If chroma/ cannot be created (a file is in the way), the script says so and exits 1."""
    blocker = tmp_path / "chroma"
    blocker.write_text("not a directory")
    monkeypatch.setattr(config, "CHROMA_DIR", blocker)
    _use(monkeypatch)
    assert build_index.main() == 1
    assert capsys.readouterr().err.startswith("Index build failed:")


def test_a_missing_key_fails_cleanly(monkeypatch, capsys, index_dir, no_env_key):
    """With no key configured the script says so and exits 1 without touching the index."""
    monkeypatch.setattr(build_index, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(config.st, "secrets", {})
    assert build_index.main() == 1
    assert config.API_KEY_NAME in capsys.readouterr().err
    assert not index_dir.exists()


def test_a_rejected_key_shows_the_mapped_message_without_the_key(monkeypatch, capsys, index_dir):
    """A 401 from OpenRouter prints the fixed message, never the key, and leaves no index."""
    requests = []

    def server(request):
        """Answer every request with a 401 whose body echoes the key, like a careless server."""
        requests.append(request)
        return httpx2.Response(401, json={"error": {"message": f"bad key {FAKE_KEY}"}})

    client = httpx2.Client(transport=httpx2.MockTransport(server))
    real_build = llm.build_embeddings
    monkeypatch.setattr(build_index, "load_chunks", lambda: list(CHUNKS))
    monkeypatch.setattr(
        llm, "build_embeddings", lambda: real_build(api_key=FAKE_KEY, http_client=client)
    )
    assert build_index.main() == 1
    output = capsys.readouterr()
    assert llm.InvalidAPIKeyError.user_message in output.err
    assert FAKE_KEY not in output.err + output.out
    assert len(requests) == 1
    assert str(requests[0].url) == f"{config.OPENROUTER_BASE_URL}/embeddings"
    with pytest.raises(store.IndexNotReadyError, match="missing"):
        store.check_index(index_dir)
