"""Cached resources: built once per app process and shared by every view (not built twice)."""

import tempfile
from pathlib import Path

import streamlit as st

from src import account, chat, config, demo, llm
from src.rag import hybrid, store


@st.cache_resource(show_spinner=False)
def index():
    """Open the knowledge base index once per app process; restart the app after a rebuild."""
    return store.open_index()


@st.cache_resource(show_spinner=False)
def keyword_index(_chroma):
    """Build the BM25 index of the knowledge base once per app process (T3.3)."""
    # The leading underscore keeps Streamlit from hashing the Chroma object; the cache is cleared
    # together with index, so it always matches the index the app holds.
    return hybrid.build_keyword_index(_chroma)


@st.cache_resource(show_spinner=False)
def chat_model():
    """Build the answer model's client once per app process."""
    return llm.build_chat_model()


@st.cache_resource(show_spinner=False)
def translation_model():
    """Build the query translation model's client once per app process."""
    return llm.build_chat_model(config.QUERY_TRANSLATION_MODEL, config.QUERY_TRANSLATION_MAX_TOKENS)


@st.cache_resource(show_spinner=False)
def review_model():
    """Build the weekly review model's client once per app process (T9.16)."""
    return llm.build_chat_model(config.REVIEW_MODEL, config.REVIEW_MAX_TOKENS)


@st.cache_resource(show_spinner=False)
def manifest():
    """Read the approved sources once, for the journal and corrections on the source cards."""
    return chat.manifest_by_id()


@st.cache_resource(show_spinner=False)
def demo_store() -> Path:
    """Make the demo database once per app process, seeded with the synthetic users (T9.5, D18)."""
    # A temporary folder that lives as long as the process (the cache holds it); the real store in
    # data/store/ is never opened in demo mode.
    folder = tempfile.TemporaryDirectory(prefix="fitcoach-demo-")
    _DEMO_FOLDERS.append(folder)
    path = Path(folder.name) / "demo.sqlite3"
    with account.open_store(path) as conn:
        demo.seed(conn)
    return path


# Keeps each demo folder alive (and deleted at exit) while the cached path is in use.
_DEMO_FOLDERS: list[tempfile.TemporaryDirectory] = []
