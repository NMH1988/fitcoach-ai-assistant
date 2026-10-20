"""Tests for src/rag/hybrid.py: the BM25 keyword index and Reciprocal Rank Fusion (T3.3)."""

import pytest
from chromadb.errors import ChromaError

from src import config
from src.rag import hybrid
from src.rag.retriever import RetrievedChunk, chunk_key
from src.rag.store import IndexNotReadyError
from tests.fakes import build_fixture_index, open_fixture_index


def _chunk(source_id: str, index: int = 0, distance: float | None = None) -> RetrievedChunk:
    """Return a made-up retrieved chunk with only the metadata its ID needs."""
    return RetrievedChunk(
        f"Text {source_id}-{index}", {"source_id": source_id, "chunk_index": index}, distance
    )


A, B, C, D = _chunk("1"), _chunk("2"), _chunk("3"), _chunk("4")


@pytest.fixture
def fixture_index(tmp_path):
    """Return the fixture chunks' Chroma index, opened with the keyword embeddings."""
    return open_fixture_index(build_fixture_index(tmp_path / "chroma"))


@pytest.fixture
def keywords(fixture_index):
    """Return the BM25 index of the fixture chunks."""
    return hybrid.build_keyword_index(fixture_index)


def test_rrf_scores_match_a_hand_computed_example():
    """Each chunk scores the sum of 1 / (60 + rank) over the lists it is in."""
    lists = [[A, B, C], [B, D], [C, B]]
    # Worked by hand: A is 1st once; B is 2nd, 1st and 2nd; C is 3rd and 1st; D is 2nd once.
    expected = {
        "1-0": 1 / 61,
        "2-0": 1 / 62 + 1 / 61 + 1 / 62,
        "3-0": 1 / 63 + 1 / 61,
        "4-0": 1 / 62,
    }
    assert config.RRF_K == 60
    assert hybrid.rrf_scores(lists) == pytest.approx(expected)
    # 0.04865 > 0.03227 > 0.01639 > 0.01613
    assert hybrid.rrf(lists) == [B, C, A, D]


def test_rrf_keeps_the_k_best_distinct_chunks():
    """A chunk in several lists is kept once, and only the top k are returned."""
    # A and C score 1/61 + 1/63 each, B 2/62, D 1/61: A and C tie, and A was found first.
    fused = hybrid.rrf([[A, B, C], [C, B, A], [D]], k=2)
    assert [chunk_key(chunk) for chunk in fused] == ["1-0", "3-0"]
    assert len({chunk_key(chunk) for chunk in hybrid.rrf([[A, B], [B, A]])}) == 2


def test_rrf_breaks_ties_by_distance_then_keyword_only_last():
    """Equal scores go to the nearer chunk; a chunk with no distance comes after one with one."""
    near, far, keyword_only = _chunk("1", distance=0.2), _chunk("2", distance=0.5), _chunk("3")
    assert hybrid.rrf([[keyword_only], [far], [near]]) == [near, far, keyword_only]


def test_rrf_keeps_a_true_tie_whatever_the_order_of_the_ranks():
    """The same ranks in another order give the same score, so the tie rule still decides."""
    # Ranks 1, 1, 6 against 6, 1, 1: equal sums that plain float addition put one ulp apart, so
    # the keyword-only chunk came first (found in the review of PR #52).
    near, keyword_only = _chunk("1", distance=0.2), _chunk("2")
    filler = [_chunk("9", n) for n in range(5)]
    lists = [
        [near],
        [near],
        [*filler, near],
        [*filler, keyword_only],
        [keyword_only],
        [keyword_only],
    ]
    scores = hybrid.rrf_scores(lists)
    assert scores["1-0"] == scores["2-0"]
    assert hybrid.rrf(lists, k=2) == [near, keyword_only]


def test_rrf_keeps_the_vector_distance_of_a_chunk_also_found_by_keyword():
    """A chunk found by both searches keeps its cosine distance, not the keyword list's None."""
    by_keyword, by_vector = _chunk("1"), _chunk("1", distance=0.3)
    assert hybrid.rrf([[by_keyword], [by_vector]])[0].distance == 0.3


def test_rrf_of_no_lists_is_empty():
    """Nothing to merge gives nothing."""
    assert hybrid.rrf([]) == []
    assert hybrid.rrf([[], []]) == []


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("How much HMB should I take?", ["hmb", "take"]),
        ("Vitamin B12 and omega-3 for vegans", ["vitamin", "b12", "omega", "vegans"]),
        ("Is 1.6 g/kg of protein enough?", ["kg", "protein", "enough"]),
        ("what is the", []),
    ],
)
def test_tokenize_keeps_terms_and_drops_stopwords_and_single_characters(text, words):
    """Exact terms such as HMB and B12 stay searchable; filler words and lone letters go."""
    assert hybrid.tokenize(text) == words


def test_keyword_search_ranks_the_chunk_with_the_exact_word_first(keywords):
    """A word only one chunk holds finds that chunk."""
    found = keywords.search("Do hormones need dietary fat?")
    assert chunk_key(found[0]) == "4-0"
    assert found[0].distance is None
    assert found[0].metadata["source_id"] == "4"


def test_keyword_search_returns_at_most_k_chunks_that_share_a_word(keywords):
    """Chunks with none of the query's words are not returned, and k caps the list."""
    found = keywords.search("protein", k=2)
    assert len(found) == 2
    assert all("protein" in chunk.text.lower() for chunk in found)
    assert keywords.search("marathon shoes") == []
    assert keywords.search("what is the") == []


def test_keyword_search_keeps_only_the_allowed_chunks(keywords):
    """The allowed IDs (the filter's chunks) limit what keyword search returns."""
    found = keywords.search("protein sleep", allowed={"2-0"})
    assert [chunk_key(chunk) for chunk in found] == ["2-0"]
    assert keywords.search("protein", allowed=set()) == []


def test_filter_ids_uses_the_chroma_filter(fixture_index):
    """The IDs come from Chroma's own filter, so both searches filter the same way."""
    where = {"topics": {"$contains": "fat"}}
    assert hybrid.filter_ids(fixture_index, where) == {"4-0"}
    assert hybrid.filter_ids(fixture_index, None) is None


def test_the_keyword_index_holds_every_chunk_with_its_metadata(keywords):
    """Every chunk of the index is searchable by keyword, with the metadata the cards need."""
    assert set(keywords.ids) == {"1-0", "1-1", "2-0", "3-0", "4-0"}
    chunk = next(c for c in keywords.chunks if chunk_key(c) == "3-0")
    assert chunk.metadata["topics"] == ["carbohydrate"]
    assert chunk.text.startswith("Carbohydrate")


def test_an_index_with_no_words_finds_nothing():
    """Chunks with no searchable word give an empty result, not a division by zero."""
    assert hybrid.KeywordIndex([]).search("protein") == []
    empty = RetrievedChunk("a the of", {"source_id": "1", "chunk_index": 0}, None)
    assert hybrid.KeywordIndex([empty]).search("protein") == []


class _BrokenIndex:
    """A stand-in for a Chroma index whose collection can no longer be read."""

    def get(self, **kwargs):
        """Fail as Chroma does when a rebuild dropped the collection."""
        raise ChromaError("internal detail")


def test_a_broken_index_is_reported_as_not_ready():
    """A Chroma error while reading the chunks gives the fixed 'rebuild the index' message."""
    with pytest.raises(IndexNotReadyError, match="could not be read") as raised:
        hybrid.build_keyword_index(_BrokenIndex())
    assert "internal detail" not in str(raised.value)
    with pytest.raises(IndexNotReadyError):
        hybrid.filter_ids(_BrokenIndex(), {"year": {"$gte": 2020}})
