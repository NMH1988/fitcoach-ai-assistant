"""Tests for src/rag/store.py: building, opening and searching the Chroma index (T2.3)."""

import chromadb
import pytest
from chromadb.api.shared_system_client import SharedSystemClient
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from pydantic import Field

from src import config
from src.rag import store
from src.rag.ingest import chunk_article, parse_article
from src.rag.store import IndexNotReadyError
from tests.test_ingest import ARTICLE_XML, make_source

DIMENSIONS = 32


def _chunk(source_id, index, text, topics, year, tier):
    """Return a made-up chunk with the metadata keys the ingest step sets."""
    return Document(
        page_content=text,
        metadata={
            "source_id": source_id,
            "title": f"Made-up article {source_id}",
            "authors": ["Ann Example", "Ben Sample"],
            "year": year,
            "section": "Results",
            "topics": topics,
            "evidence_tier": tier,
            "license": "CC BY 4.0",
            "source_url": f"https://doi.org/10.1234/made-up.{source_id}",
            "chunk_index": index,
        },
    )


# Text written for these tests; three sources with different topics, years and tiers.
CHUNKS = [
    _chunk("1", 0, "Protein spread over four meals a day.", ["protein"], 2017, 1),
    _chunk("1", 1, "Protein before sleep and overnight recovery.", ["protein"], 2017, 1),
    _chunk("2", 0, "Carbohydrate intake on heavy training days.", ["carbohydrate"], 2021, 2),
    _chunk(
        "2",
        1,
        "Carbohydrate timing around a workout.",
        ["carbohydrate", "nutrient_timing"],
        2021,
        2,
    ),
    _chunk("3", 0, "Creatine and protein after training.", ["protein", "supplements"], 2023, 2),
]


class SpyEmbeddings(DeterministicFakeEmbedding):
    """A fake embedding model that records each batch of documents and each query it embeds."""

    size: int = DIMENSIONS
    batches: list[int] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    # Raise on this batch (1-based), to simulate a failed embedding request.
    fail_on_batch: int | None = None

    def embed_documents(self, texts):
        """Record the batch size, fail if asked to, else return the fake vectors."""
        self.batches.append(len(texts))
        if len(self.batches) == self.fail_on_batch:
            raise RuntimeError("embedding service failed")
        return super().embed_documents(texts)

    def embed_query(self, text):
        """Record the query and return its fake vector."""
        self.queries.append(text)
        return super().embed_query(text)


@pytest.fixture
def index_dir(tmp_path):
    """Return a path for an index directory that does not exist yet."""
    return tmp_path / "chroma"


@pytest.fixture
def built(index_dir):
    """Build the index of CHUNKS and return it opened with the same fake embeddings."""
    embeddings = SpyEmbeddings()
    store.build_index(CHUNKS, embeddings, index_dir, batch_size=2)
    return store.open_index(embeddings, index_dir)


def _ids(index_dir):
    """Return the sorted IDs stored in the index."""
    return sorted(store.open_index(SpyEmbeddings(), index_dir).get()["ids"])


def _collection_names(index_dir):
    """Return the names of every collection in the index directory."""
    client = chromadb.PersistentClient(path=str(index_dir), settings=store._SETTINGS)
    return sorted(collection.name for collection in client.list_collections())


# --- Building and opening (AC1) -----------------------------------------------------------------


def test_build_writes_a_persistent_index_that_open_index_reads(index_dir):
    """Every chunk is embedded and written to disk; open_index finds each one again."""
    assert store.build_index(CHUNKS, SpyEmbeddings(), index_dir, batch_size=2) == len(CHUNKS)
    assert (index_dir / "chroma.sqlite3").is_file()
    assert store.check_index(index_dir) == len(CHUNKS)
    index = store.open_index(SpyEmbeddings(), index_dir)
    for chunk in CHUNKS:
        [found] = index.similarity_search(chunk.page_content, k=1)
        assert found.page_content == chunk.page_content
        assert found.metadata == chunk.metadata


def test_chunk_ids_are_the_source_and_chunk_index(index_dir):
    """Each chunk is stored under "<source_id>-<chunk_index>", so a rebuild keeps the same IDs."""
    store.build_index(CHUNKS, SpyEmbeddings(), index_dir)
    assert _ids(index_dir) == ["1-0", "1-1", "2-0", "2-1", "3-0"]
    assert store.chunk_id(CHUNKS[3]) == "2-1"


def test_chunks_are_embedded_in_batches(index_dir):
    """The chunks go to the embedding model in batches of batch_size, with progress reported."""
    embeddings = SpyEmbeddings()
    progress = []
    store.build_index(
        CHUNKS, embeddings, index_dir, batch_size=2, on_batch=lambda *p: progress.append(p)
    )
    assert embeddings.batches == [2, 2, 1]
    assert progress == [(2, 5), (4, 5), (5, 5)]


def test_the_default_batch_size_comes_from_config(index_dir):
    """Without a batch_size the build uses EMBEDDING_BATCH_SIZE."""
    embeddings = SpyEmbeddings()
    store.build_index(CHUNKS, embeddings, index_dir)
    assert embeddings.batches == [len(CHUNKS)]
    assert config.EMBEDDING_BATCH_SIZE >= len(CHUNKS)


def test_article_chunks_keep_their_list_metadata_in_the_index(index_dir):
    """Chunks from the ingest step keep every metadata value, lists included, after a round trip."""
    chunks = chunk_article(parse_article(ARTICLE_XML), make_source(), {"corrected_by": ["1a"]})
    store.build_index(chunks, SpyEmbeddings(), index_dir)
    stored = store.open_index(SpyEmbeddings(), index_dir).get()
    by_id = dict(zip(stored["ids"], stored["metadatas"], strict=True))
    assert len(by_id) == len(chunks)
    for chunk in chunks:
        assert by_id[store.chunk_id(chunk)] == chunk.metadata
    assert by_id["1-0"]["authors"] == ["Ann Example", "Ben Sample"]
    assert by_id["1-0"]["topics"] == ["protein", "supplements"]


def test_a_rebuild_replaces_the_old_index(index_dir):
    """Building again leaves only the new chunks, under the index's own name."""
    store.build_index(CHUNKS, SpyEmbeddings(), index_dir)
    store.build_index(CHUNKS[:2], SpyEmbeddings(), index_dir)
    assert store.check_index(index_dir) == 2
    assert _ids(index_dir) == ["1-0", "1-1"]
    assert _collection_names(index_dir) == [config.CHROMA_COLLECTION]
    # The rename keeps the distance setting that langchain-chroma's relevance scores rely on.
    index = store.open_index(SpyEmbeddings(), index_dir)
    assert index._collection.configuration["hnsw"]["space"] == "cosine"


def test_a_fresh_process_reads_the_index_from_disk(index_dir):
    """After chromadb's in-process cache is cleared (as in a new process), the index still opens."""
    store.build_index(CHUNKS, SpyEmbeddings(), index_dir, batch_size=2)
    SharedSystemClient.clear_system_cache()
    assert store.check_index(index_dir) == len(CHUNKS)
    [found] = store.open_index(SpyEmbeddings(), index_dir).similarity_search(
        CHUNKS[2].page_content, k=1
    )
    assert found.metadata == CHUNKS[2].metadata


def test_a_failed_rebuild_keeps_the_previous_index(index_dir):
    """An embedding error mid-build leaves the old index untouched and no staging collection."""
    store.build_index(CHUNKS, SpyEmbeddings(), index_dir)
    with pytest.raises(RuntimeError, match="embedding service failed"):
        store.build_index(CHUNKS[:4], SpyEmbeddings(fail_on_batch=2), index_dir, batch_size=2)
    assert store.check_index(index_dir) == len(CHUNKS)
    assert _collection_names(index_dir) == [config.CHROMA_COLLECTION]


def test_a_failed_first_build_leaves_no_index(index_dir):
    """When the very first build fails, the index counts as missing."""
    with pytest.raises(RuntimeError):
        store.build_index(CHUNKS, SpyEmbeddings(fail_on_batch=1), index_dir, batch_size=2)
    with pytest.raises(IndexNotReadyError, match="missing"):
        store.check_index(index_dir)
    assert _collection_names(index_dir) == []


@pytest.mark.parametrize(
    ("chunks", "batch_size", "message"),
    [
        ([], 2, "no chunks"),
        (CHUNKS, 0, "batch_size"),
        ([CHUNKS[0], CHUNKS[1], CHUNKS[0]], 2, "Duplicate chunk IDs: 1-0"),
    ],
    ids=["no-chunks", "zero-batch", "duplicate-ids"],
)
def test_bad_build_input_is_refused_before_any_embedding(index_dir, chunks, batch_size, message):
    """No chunks, a batch size below 1 or a repeated chunk ID stop the build before any call."""
    embeddings = SpyEmbeddings()
    with pytest.raises(ValueError, match=message):
        store.build_index(chunks, embeddings, index_dir, batch_size=batch_size)
    assert embeddings.batches == []
    assert not index_dir.exists()


def test_open_index_embeds_queries_only_with_the_given_client(built):
    """Searches embed the query with our client; the collection has no embedding function."""
    built.similarity_search("protein at night", k=2)
    assert built.embeddings.queries == ["protein at night"]
    assert built._collection._embedding_function is None


def test_opening_keeps_the_index_usable(built, index_dir):
    """Opening the index does not change its metadata, so it can be checked and opened again."""
    assert store.check_index(index_dir) == len(CHUNKS)
    assert len(store.open_index(SpyEmbeddings(), index_dir).get()["ids"]) == len(CHUNKS)


def test_an_index_dropped_while_it_opens_is_not_searched(index_dir, monkeypatch):
    """If a rebuild drops the index just as the app opens it, opening fails instead of using it."""
    store.build_index(CHUNKS, SpyEmbeddings(), index_dir)
    real_chroma = store.Chroma

    def chroma_after_a_drop(**kwargs):
        """Drop the index collection, as a concurrent rebuild would, then open it."""
        kwargs["client"].delete_collection(config.CHROMA_COLLECTION)
        return real_chroma(**kwargs)

    monkeypatch.setattr(store, "Chroma", chroma_after_a_drop)
    with pytest.raises(IndexNotReadyError) as caught:
        store.open_index(SpyEmbeddings(), index_dir)
    _assert_build_hint(caught.value, "empty")


# --- Similarity search with a metadata filter (AC2) ---------------------------------------------


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ({"topics": {"$contains": "protein"}}, {"1-0", "1-1", "3-0"}),
        ({"year": {"$gte": 2021}}, {"2-0", "2-1", "3-0"}),
        ({"evidence_tier": 1}, {"1-0", "1-1"}),
        ({"source_id": "2"}, {"2-0", "2-1"}),
        (
            {"$and": [{"topics": {"$contains": "protein"}}, {"evidence_tier": 2}]},
            {"3-0"},
        ),
        ({"topics": {"$contains": "fat"}}, set()),
    ],
    ids=["topic", "min-year", "tier", "source", "topic-and-tier", "no-match"],
)
def test_similarity_search_with_a_filter_returns_only_matching_chunks(built, where, expected):
    """A metadata filter returns exactly the chunks that match it, however many are asked for."""
    found = built.similarity_search("protein for muscle", k=len(CHUNKS), filter=where)
    assert {store.chunk_id(chunk) for chunk in found} == expected


# --- A missing or unusable index (AC3) ----------------------------------------------------------


def _assert_build_hint(error: IndexNotReadyError, reason: str) -> None:
    """Check that the message names the reason and the command that builds the index."""
    assert reason in str(error)
    assert f"Run `{config.BUILD_INDEX_COMMAND}`" in str(error)


def test_a_missing_index_says_to_run_the_build_script(index_dir):
    """With no index directory, checking says to build it, and creates nothing."""
    with pytest.raises(IndexNotReadyError) as caught:
        store.check_index(index_dir)
    _assert_build_hint(caught.value, "missing")
    assert not index_dir.exists()


def test_open_index_reports_a_missing_index_even_without_a_key(index_dir, monkeypatch, no_env_key):
    """A missing index is reported before the embeddings client needs the API key."""
    monkeypatch.setattr(config.st, "secrets", {})
    with pytest.raises(IndexNotReadyError) as caught:
        store.open_index(persist_dir=index_dir)
    _assert_build_hint(caught.value, "missing")


def test_the_default_index_directory_is_chroma_in_the_repo(tmp_path, monkeypatch):
    """Without a directory argument, the index is looked for in config.CHROMA_DIR."""
    assert config.CHROMA_DIR == config.PROJECT_ROOT / "chroma"
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "elsewhere")
    with pytest.raises(IndexNotReadyError, match="missing"):
        store.check_index()
    store.build_index(CHUNKS, SpyEmbeddings())
    assert store.check_index() == len(CHUNKS)


def test_a_directory_without_the_collection_counts_as_missing(index_dir):
    """A Chroma directory that holds some other collection is reported as a missing index."""
    client = chromadb.PersistentClient(path=str(index_dir), settings=store._SETTINGS)
    client.create_collection("something-else", embedding_function=None)
    with pytest.raises(IndexNotReadyError) as caught:
        store.check_index(index_dir)
    _assert_build_hint(caught.value, "missing")


def test_an_empty_index_says_to_run_the_build_script(index_dir):
    """An index collection with no chunks in it is reported as empty."""
    client = chromadb.PersistentClient(path=str(index_dir), settings=store._SETTINGS)
    client.create_collection(
        config.CHROMA_COLLECTION,
        embedding_function=None,
        metadata={"embedding_model": config.EMBEDDING_MODEL},
    )
    with pytest.raises(IndexNotReadyError) as caught:
        store.check_index(index_dir)
    _assert_build_hint(caught.value, "empty")


def test_an_empty_collection_without_metadata_is_reported_as_empty(index_dir):
    """An empty collection is reported as empty even when it records no embedding model."""
    client = chromadb.PersistentClient(path=str(index_dir), settings=store._SETTINGS)
    client.create_collection(config.CHROMA_COLLECTION, embedding_function=None)
    with pytest.raises(IndexNotReadyError, match="empty"):
        store.check_index(index_dir)


def test_an_index_from_another_embedding_model_must_be_rebuilt(index_dir, monkeypatch):
    """An index built with a different embedding model than the configured one is refused."""
    store.build_index(CHUNKS, SpyEmbeddings(), index_dir)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "some/other-embedding-model")
    with pytest.raises(IndexNotReadyError) as caught:
        store.open_index(SpyEmbeddings(), index_dir)
    _assert_build_hint(caught.value, "different embedding model")


def test_an_unreadable_index_says_to_rebuild_without_chroma_details(index_dir):
    """A corrupt index file gives the fixed rebuild message, not Chroma's error."""
    index_dir.mkdir()
    (index_dir / "chroma.sqlite3").write_bytes(b"this is not a database " * 50)
    with pytest.raises(IndexNotReadyError) as caught:
        store.check_index(index_dir)
    _assert_build_hint(caught.value, "could not be read")
    assert caught.value.__suppress_context__


def test_an_unreadable_index_gives_the_same_message_on_every_check(index_dir):
    """Checking a corrupt index again in the same process (the next chat turn) never crashes."""
    index_dir.mkdir()
    (index_dir / "chroma.sqlite3").write_bytes(b"this is not a database " * 50)
    for _ in range(3):
        with pytest.raises(IndexNotReadyError) as caught:
            store.check_index(index_dir)
        _assert_build_hint(caught.value, "could not be read")
