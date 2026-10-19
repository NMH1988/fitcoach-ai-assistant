"""Chunk every downloaded article, embed the chunks and write the Chroma index to chroma/.

Run from the repo root after `python scripts/download_sources.py`, with the key set up as in the
README:

    python scripts/build_index.py

It replaces the previous index only once every chunk is embedded, never prints the key, and costs
well under one US cent (docs/ARCHITECTURE.md section 4). Record the output in docs/TESTING.md.
"""

import sys

from chromadb.errors import ChromaError

from src import config, llm
from src.rag import store
from src.rag.ingest import IngestError, load_chunks
from src.rag.sources import ManifestError


def _show_progress(done: int, total: int) -> None:
    """Print how many chunks are embedded so far."""
    print(f"Embedded {done}/{total} chunks", flush=True)


def main() -> int:
    """Build the index; print a summary and return 0, or print the error and return 1."""
    try:
        chunks = load_chunks()
        embeddings = llm.build_embeddings()
        with llm.mapped_errors():
            count = store.build_index(chunks, embeddings, on_batch=_show_progress)
    # ChromaError, OSError (e.g. chroma/ not writable) and ValueError (bad chunks or metadata) carry
    # no key: only mapped LLM errors could, and those have fixed messages.
    except (
        ManifestError,
        IngestError,
        config.MissingAPIKeyError,
        llm.LLMError,
        ChromaError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Index build failed: {exc}", file=sys.stderr)
        return 1
    sources = len({chunk.metadata["source_id"] for chunk in chunks})
    characters = sum(len(chunk.page_content) for chunk in chunks)
    print(
        f"Indexed {count} chunks from {sources} sources ({characters:,} characters) with "
        f"{config.EMBEDDING_MODEL} into {config.CHROMA_DIR.name}/ "
        f"(collection {config.CHROMA_COLLECTION})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
