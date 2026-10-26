"""Tests for src/rag/hybrid.py: the BM25 keyword index and Reciprocal Rank Fusion (T3.3)."""

import pytest
from chromadb.errors import ChromaError

from src import config
from src.rag import hybrid
from src.rag.retriever import RetrievedChunk, chunk_key
from src.rag.store import IndexNotReadyError
from tests.fakes import build_fixture_index, open_fixture_index
from tests.fakes import chunk as fixture_chunk


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


def _sources_of(chunks: list[RetrievedChunk]) -> list[str]:
    """Return the chunks' source IDs, in order."""
    return [str(chunk.metadata["source_id"]) for chunk in chunks]


def test_the_cap_is_three_chunks_per_source():
    """The configured cap is three, and the list is still six long."""
    assert config.MAX_CHUNKS_PER_SOURCE == 3
    assert config.RETRIEVAL_TOP_K == 6


def test_rrf_keeps_at_most_three_chunks_of_a_source_then_fills_with_the_skipped_ones():
    """Six chunks of A and two of B give 3 A, 2 B, then the first skipped A to fill the place."""
    a_chunks = [_chunk("A", n) for n in range(6)]
    b_chunks = [_chunk("B", n) for n in range(2)]
    fused = hybrid.rrf([[*a_chunks, *b_chunks]])
    assert _sources_of(fused) == ["A", "A", "A", "B", "B", "A"]
    assert [chunk_key(chunk) for chunk in fused] == ["A-0", "A-1", "A-2", "B-0", "B-1", "A-3"]


def test_rrf_with_enough_other_sources_leaves_the_skipped_chunks_out():
    """When other sources fill the places, no chunk over the cap is added."""
    a_chunks = [_chunk("A", n) for n in range(5)]
    others = [_chunk("B", 0), _chunk("C", 0), _chunk("D", 0)]
    fused = hybrid.rrf([[*a_chunks, *others]])
    assert _sources_of(fused) == ["A", "A", "A", "B", "C", "D"]


def test_rrf_with_one_source_still_gives_six_chunks():
    """A single-source list is not shortened: the skipped chunks fill the places in fused order."""
    only_a = [_chunk("A", n) for n in range(8)]
    fused = hybrid.rrf([only_a])
    assert [chunk_key(chunk) for chunk in fused] == [f"A-{n}" for n in range(6)]


def test_rrf_cap_keeps_the_order_of_equal_scores():
    """With equal scores the nearer chunk comes first, then the first found, capped or not."""
    a_near, a_next = _chunk("A", 0, distance=0.1), _chunk("A", 1, distance=0.15)
    b_near, b_far = _chunk("B", 0, distance=0.2), _chunk("B", 1, distance=0.3)
    # Four lists of one chunk each: equal scores, so the distance decides. The cap drops A's second.
    lists = [[b_far], [a_next], [b_near], [a_near]]
    assert hybrid.rrf(lists, k=2, max_per_source=2) == [a_near, a_next]
    assert hybrid.rrf(lists, k=2, max_per_source=1) == [a_near, b_near]
    # No distances at all: the order found decides, and the fill follows it.
    found = [_chunk("A", 0), _chunk("A", 1), _chunk("B", 0), _chunk("B", 1)]
    fused = hybrid.rrf([[chunk] for chunk in found], k=3, max_per_source=1)
    assert [chunk_key(chunk) for chunk in fused] == ["A-0", "B-0", "A-1"]


def test_rrf_cap_keeps_the_smallest_distance_of_each_chunk():
    """A kept chunk found by keyword and by vector keeps its vector distance."""
    by_keyword, by_vector = _chunk("A", 0), _chunk("A", 0, distance=0.3)
    other = [_chunk("A", n) for n in range(1, 5)]
    fused = hybrid.rrf([[by_keyword, *other], [by_vector]])
    assert fused[0].distance == 0.3


def test_rrf_cap_can_be_set_per_call():
    """A cap of one gives one chunk per source first, then the fill."""
    fused = hybrid.rrf(
        [[_chunk("A", 0), _chunk("A", 1), _chunk("B", 0), _chunk("A", 2)]], max_per_source=1
    )
    assert [chunk_key(chunk) for chunk in fused] == ["A-0", "B-0", "A-1", "A-2"]


def test_hybrid_search_lets_a_second_source_in_before_a_fourth_chunk_of_the_first(tmp_path):
    """Five chunks of source 7 sit nearer than source 6's, which still comes fourth, not last."""
    chunks = [fixture_chunk("7", n, f"Protein note {n}: training.") for n in range(5)]
    # "Proteins" counts for the keyword embeddings but is not the search word "protein".
    chunks.append(fixture_chunk("6", 0, "Proteins and sleep."))
    index = open_fixture_index(build_fixture_index(tmp_path / "chroma", chunks))
    vectors = index.embeddings.embed_documents(["protein"])
    fused = hybrid.hybrid_search(
        index, ["protein"], vectors, None, lambda built: hybrid.build_keyword_index(built)
    )
    assert _sources_of(fused) == ["7", "7", "7", "6", "7", "7"]
    assert fused[3].distance is not None and fused[3].distance > fused[2].distance


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
