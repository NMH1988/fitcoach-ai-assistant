"""Fakes for chat-turn tests: keyword embeddings, a scripted chat model, a small fixture index."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from src.rag import store

# Bound at import, so UI tests that replace store.open_index can still open the fixture index.
_open_index = store.open_index

# Each keyword is one dimension; the last dimension is a small constant, so no vector is zero.
KEYWORDS = ("protein", "creatine", "carbohydrate", "sleep", "fat")
_BIAS = 0.1


class KeywordEmbeddings(Embeddings):
    """Embed a text as the counts of a few keywords, so tests control which chunks are close."""

    def _vector(self, text: str) -> list[float]:
        """Return the keyword counts of the text plus the small constant dimension."""
        words = text.lower()
        return [float(words.count(keyword)) for keyword in KEYWORDS] + [_BIAS]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one keyword vector per text."""
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return the keyword vector of the query."""
        return self._vector(text)


class ScriptedChatModel(BaseChatModel):
    """A chat model that returns scripted replies (or raises) and records every request."""

    replies: list[AIMessage] = Field(default_factory=list)
    error: Exception | None = None
    # When set with error, streaming raises the error after this many chunks.
    fail_after_chunks: int | None = None
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        """Name the fake for langchain."""
        return "scripted-fake"

    def _generate(self, messages: list[BaseMessage], stop: Any = None, **kwargs: Any) -> ChatResult:
        """Record the messages, then raise the scripted error or return the next reply."""
        self.calls.append(list(messages))
        if self.error is not None:
            raise self.error
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

    def _stream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        """Record the messages, then yield the next reply word by word (or raise)."""
        self.calls.append(list(messages))
        if self.error is not None and self.fail_after_chunks is None:
            raise self.error
        reply = self.replies.pop(0)
        pieces = re.findall(r"\S+\s*|\s+", reply.text) or [""]
        for number, piece in enumerate(pieces):
            if number == self.fail_after_chunks:
                raise self.error
            # The finish reason comes with the last chunk, as in OpenAI's stream.
            last = number == len(pieces) - 1
            metadata = reply.response_metadata if last else {}
            yield ChatGenerationChunk(message=AIMessageChunk(piece, response_metadata=metadata))


def chunk(source_id: str, index: int, text: str, **extra: Any) -> Document:
    """Return a made-up chunk with the metadata keys the ingest step sets."""
    return Document(
        page_content=text,
        metadata={
            "source_id": source_id,
            "title": f"Made-up article {source_id}",
            "authors": ["Ann Example"],
            "year": 2020 + int(source_id[0]),
            "section": "Results",
            "topics": ["protein"],
            "evidence_tier": 1 if source_id == "1" else 2,
            "license": "CC BY 4.0",
            "source_url": f"https://doi.org/10.1234/made-up.{source_id}",
            "chunk_index": index,
            **extra,
        },
    )


# Text written for these tests. Source 1 has two protein chunks, so one article can be cited twice.
CHUNKS = [
    chunk("1", 0, "Protein: spread protein over four meals."),
    chunk("1", 1, "Protein before sleep: casein protein supports overnight sleep recovery."),
    chunk("2", 0, "Creatine with protein before sleep."),
    chunk("3", 0, "Carbohydrate: carbohydrate on heavy training days."),
    chunk("4", 0, "Fat: dietary fat and hormones."),
]


def build_fixture_index(path: Path, chunks: list[Document] | None = None) -> Path:
    """Build the fixture chunks into a Chroma index at path and return the path."""
    store.build_index(chunks or CHUNKS, KeywordEmbeddings(), path)
    return path


def open_fixture_index(path: Path):
    """Open the fixture index at path with the keyword embeddings."""
    return _open_index(KeywordEmbeddings(), path)
