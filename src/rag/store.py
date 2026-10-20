"""Build and open the persistent Chroma index of the knowledge base chunks.

Chroma runs embedded in the app's process only, never as a server
(.claude/rules/security-privacy.md).
Vectors always come from the embeddings client we pass in (OpenRouter through `src/llm.py`, or a
fake in tests): collections are created and opened with `embedding_function=None`, so Chroma's own
embedding functions are never used.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.errors import ChromaError, NotFoundError
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src import config, llm

# Every client for a path must use the same settings, or chromadb raises ValueError.
_SETTINGS = Settings(anonymized_telemetry=False)
# The file chromadb keeps in its directory; checked so opening never creates an empty index.
_DB_FILE = "chroma.sqlite3"
# Collection metadata naming the embedding model of the index; queries must use the same one.
_MODEL_KEY = "embedding_model"
# A build writes here first and takes the final name only when every chunk is in.
_STAGING_COLLECTION = f"{config.CHROMA_COLLECTION}-building"
_HNSW_CONFIGURATION = {"hnsw": {"space": "cosine"}}

_MISSING = "The knowledge base index is missing."
# Also used by the retriever when a search fails on a broken index.
UNREADABLE = "The knowledge base index could not be read."
_EMPTY = "The knowledge base index is empty."
_OTHER_MODEL = "The knowledge base index was built with a different embedding model."


class IndexNotReadyError(RuntimeError):
    """The index is missing, unreadable, empty or from another model; `str()` is safe to show."""

    def __init__(self, reason: str) -> None:
        """Build the fixed message: the reason, then the command that builds the index."""
        super().__init__(f"{reason} Run `{config.BUILD_INDEX_COMMAND}` to build it.")


def chunk_id(chunk: Document) -> str:
    """Return the stable index ID of a chunk: its source ID and its index in the article."""
    return f"{chunk.metadata['source_id']}-{chunk.metadata['chunk_index']}"


def _client(persist_dir: Path) -> chromadb.ClientAPI:
    """Return the embedded Chroma client for a directory (created if missing)."""
    return chromadb.PersistentClient(path=str(persist_dir), settings=_SETTINGS)


def _drop(client: chromadb.ClientAPI, name: str) -> None:
    """Delete a collection if it exists."""
    try:
        client.delete_collection(name)
    except NotFoundError:
        pass


def check_index(persist_dir: Path | None = None) -> int:
    """Return the chunk count of the index; raise IndexNotReadyError if it cannot be used."""
    persist_dir = persist_dir or config.CHROMA_DIR
    if not (persist_dir / _DB_FILE).is_file():
        raise IndexNotReadyError(_MISSING)
    try:
        collection = _client(persist_dir).get_collection(
            config.CHROMA_COLLECTION, embedding_function=None
        )
        count = collection.count()
    except NotFoundError:
        raise IndexNotReadyError(_MISSING) from None
    except ChromaError:
        # Its message may quote internals; the user only needs to know to rebuild.
        raise IndexNotReadyError(UNREADABLE) from None
    except AttributeError:
        # chromadb 1.5.9: after a broken file fails to open, the half-started client stays cached,
        # and the next try in the same process (the next chat turn) fails while releasing it.
        raise IndexNotReadyError(UNREADABLE) from None
    if count == 0:
        raise IndexNotReadyError(_EMPTY)
    if (collection.metadata or {}).get(_MODEL_KEY) != config.EMBEDDING_MODEL:
        raise IndexNotReadyError(_OTHER_MODEL)
    return count


def open_index(embeddings: Embeddings | None = None, persist_dir: Path | None = None) -> Chroma:
    """Open the built index for search; raise IndexNotReadyError if it cannot be used."""
    persist_dir = persist_dir or config.CHROMA_DIR
    # Checked first, so a missing index is reported even when no API key is set.
    check_index(persist_dir)
    index = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings or llm.build_embeddings(),
        client=_client(persist_dir),
    )
    # Chroma(...) creates the collection if it is gone, which happens when a rebuild drops it
    # between the check above and this line; checked again so an empty one is never searched.
    check_index(persist_dir)
    return index


def build_index(
    chunks: Sequence[Document],
    embeddings: Embeddings,
    persist_dir: Path | None = None,
    batch_size: int | None = None,
    on_batch: Callable[[int, int], None] | None = None,
) -> int:
    """Embed the chunks in batches into a new index that replaces the old one; return the count."""
    # on_batch(done, total) is called after each batch, so the script can show progress.
    batch_size = config.EMBEDDING_BATCH_SIZE if batch_size is None else batch_size
    if not chunks:
        raise ValueError("There are no chunks to index.")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    ids = [chunk_id(chunk) for chunk in chunks]
    # Chroma's upsert would silently keep only the last chunk of a repeated ID.
    duplicates = sorted(id_ for id_, n in Counter(ids).items() if n > 1)
    if duplicates:
        raise ValueError(f"Duplicate chunk IDs: {', '.join(duplicates[:5])}")
    persist_dir = persist_dir or config.CHROMA_DIR
    persist_dir.mkdir(parents=True, exist_ok=True)
    client = _client(persist_dir)
    # The chunks go into a staging collection, which takes the index's name only once all of them
    # are in, so a failed build leaves the previous index as it was.
    _drop(client, _STAGING_COLLECTION)
    staging = client.create_collection(
        _STAGING_COLLECTION,
        embedding_function=None,
        configuration=_HNSW_CONFIGURATION,
        metadata={_MODEL_KEY: config.EMBEDDING_MODEL},
    )
    store = Chroma(
        collection_name=_STAGING_COLLECTION, embedding_function=embeddings, client=client
    )
    try:
        for start in range(0, len(chunks), batch_size):
            end = min(start + batch_size, len(chunks))
            store.add_documents(list(chunks[start:end]), ids=ids[start:end])
            if on_batch is not None:
                on_batch(end, len(chunks))
    except BaseException:
        # Also on Ctrl+C: a half-built staging collection is never left behind.
        _drop(client, _STAGING_COLLECTION)
        raise
    # A crash between these two lines leaves no index, which check_index() reports.
    _drop(client, config.CHROMA_COLLECTION)
    staging.modify(name=config.CHROMA_COLLECTION)
    return len(chunks)
