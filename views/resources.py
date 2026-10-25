"""Cached resources: built once per app process and shared by every view (not built twice)."""

import streamlit as st

from src import chat, config, llm
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
def manifest():
    """Read the approved sources once, for the journal and corrections on the source cards."""
    return chat.manifest_by_id()
