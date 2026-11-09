"""Offline retrieval regression suite (T8.5): the real search pipeline on a fixture index, no key.

The fixture (`tests/fixtures/retrieval/`) holds made-up sources and short texts we wrote ourselves
(copyright policy rule 8). They are chunked by `ingest.chunk_article()` and indexed by
`store.build_index()`, as the real index is, with `ConceptEmbeddings` in place of the embedding
model. Each fixture question runs through `chat.find_chunks()`, the search the agent's
`search_knowledge_base` tool runs (filters, the coverage gate, BM25, RRF, the per-source cap and
the filter retry), with the plan the fixture gives in place of the query translation model.

Two rates are scored, and each must stay at or above the rate recorded in the fixture:
- the hit rate: expected chunks found in the top RETRIEVAL_TOP_K, over all expected chunks
  (owner's choice, 2026-11-09: per chunk, so losing a question's second chunk counts);
- the no-sources rate: off-topic questions (no expected chunk) that get nothing back.

This catches pipeline bugs, not embedding quality: the real model is T8.6's.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src import chat, config
from src.rag import hybrid, ingest, query_translation, store
from src.rag.hybrid import KeywordIndex
from src.rag.query_translation import QueryPlan
from src.rag.retriever import chunk_key
from src.rag.sources import Source, load_manifest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "retrieval"

# Each concept is one dimension of the fake embedding; a text's value there is how many of its
# words are among the concept's words. Words outside every concept (a made-up compound, "cycling")
# add nothing, so only keyword search can find them. Written for this suite.
CONCEPTS: dict[str, frozenset[str]] = {
    "protein": frozenset({"protein", "proteins"}),
    "creatine": frozenset({"creatine"}),
    "carbohydrate": frozenset({"carbohydrate", "carbohydrates"}),
    "fat": frozenset({"fat", "fats"}),
    "energy": frozenset({"calorie", "calories", "deficit", "surplus"}),
    "meal": frozenset({"meal", "meals"}),
    "sleep": frozenset({"sleep"}),
    "caffeine": frozenset({"caffeine", "coffee"}),
    "fluid": frozenset({"water", "fluid", "hydration"}),
    "recovery": frozenset({"recovery", "soreness"}),
    "strength": frozenset({"strength", "stronger"}),
    "muscle": frozenset({"muscle", "hypertrophy"}),
    "volume": frozenset({"volume", "sets"}),
    "rest": frozenset({"rest"}),
}
# A small constant last dimension, so no vector is zero; an off-topic text points almost only
# along it and is far from every chunk.
_BIAS = 0.1
_WORD = re.compile(r"[a-z]+")


# Modelled on tests/fakes.py's KeywordEmbeddings, with word groups in place of substrings.
# langchain's DeterministicFakeEmbedding gives random vectors, about 1.0 apart in cosine, so no
# question would pass the coverage gate (RETRIEVAL_MAX_DISTANCE); these vectors put texts that
# share concepts close, so the gate and the ranking behave as they do on real vectors.
class ConceptEmbeddings(Embeddings):
    """Embed a text as counts of a fixed set of concept words: deterministic, and meaningful."""

    def _vector(self, text: str) -> list[float]:
        """Return the concept counts of the text plus the constant dimension."""
        words = _WORD.findall(text.casefold())
        return [float(sum(word in group for word in words)) for group in CONCEPTS.values()] + [
            _BIAS
        ]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one concept vector per text."""
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return the concept vector of the query."""
        return self._vector(text)


@dataclass(frozen=True)
class Question:
    """A fixture question: its query, the plan in place of query translation, expected chunks."""

    id: str
    query: str
    plan: QueryPlan | None
    expected: tuple[str, ...]
    # The expected chunks today's pipeline does not find (a known limit), recorded in the fixture.
    known_missed: tuple[str, ...] = ()
    # When set, every chunk found must carry this topic (the training retry, T9.20).
    only_topic: str | None = None


@dataclass(frozen=True)
class Scores:
    """The suite's two rates and, per question, the expected chunks it missed."""

    hit_rate: float
    no_sources_rate: float
    missed: dict[str, tuple[str, ...]]
    # Off-topic questions that got chunks back, with the chunk IDs they got.
    answered_off_topic: dict[str, tuple[str, ...]]
    # Questions with only_topic that got a chunk without that topic, with those chunk IDs.
    wrong_topic: dict[str, tuple[str, ...]]


def load_suite() -> dict[str, Any]:
    """Return the suite file: the texts, the questions and the recorded rates."""
    return json.loads((FIXTURE_DIR / "suite.json").read_text(encoding="utf-8"))


def load_sources() -> list[Source]:
    """Return the made-up sources, checked by the same loader as data/sources.json."""
    return load_manifest(FIXTURE_DIR / "sources.json")


def fixture_chunks(suite: dict[str, Any], sources: list[Source]) -> list[Document]:
    """Chunk every source's texts with the ingest step, as the real articles are chunked."""
    chunks = []
    for source in sources:
        sections = [ingest.Section(s["title"], s["text"]) for s in suite["texts"][source.id]]
        article = ingest.ParsedArticle(title=source.title, sections=sections)
        chunks.extend(ingest.chunk_article(article, source))
    return chunks


def load_questions(suite: dict[str, Any]) -> list[Question]:
    """Return the fixture questions, each plan checked by the real QueryPlan schema."""
    questions = []
    for item in suite["questions"]:
        plan = item["plan"]
        # The two flags are required by the schema but read by no search step (T9.3).
        parsed = (
            None
            if plan is None
            else QueryPlan.model_validate({"needs_tool": False, "needs_profile": False, **plan})
        )
        questions.append(
            Question(
                item["id"],
                item["query"],
                parsed,
                tuple(item["expected"]),
                tuple(item.get("known_missed", ())),
                item.get("only_topic"),
            )
        )
    return questions


def run_suite(index, questions: list[Question], keyword_index=hybrid.build_keyword_index) -> Scores:
    """Search every question with chat.find_chunks() and score the two rates."""
    expected_total = found_total = off_topic_total = empty_total = 0
    missed: dict[str, tuple[str, ...]] = {}
    answered: dict[str, tuple[str, ...]] = {}
    wrong_topic: dict[str, tuple[str, ...]] = {}
    for question in questions:
        found, _ = chat.find_chunks(
            question.query, question.plan, index, keyword_index=keyword_index
        )
        top = found[: config.RETRIEVAL_TOP_K]
        ids = [chunk_key(chunk) for chunk in top]
        if question.only_topic is not None:
            stray = tuple(
                chunk_key(chunk)
                for chunk in top
                if question.only_topic not in chunk.metadata.get("topics", [])
            )
            if stray:
                wrong_topic[question.id] = stray
        if question.expected:
            lost = tuple(chunk for chunk in question.expected if chunk not in ids)
            expected_total += len(question.expected)
            found_total += len(question.expected) - len(lost)
            if lost:
                missed[question.id] = lost
        else:
            off_topic_total += 1
            if ids:
                answered[question.id] = tuple(ids)
            else:
                empty_total += 1
    return Scores(
        hit_rate=found_total / expected_total,
        no_sources_rate=empty_total / off_topic_total,
        missed=missed,
        answered_off_topic=answered,
        wrong_topic=wrong_topic,
    )


@pytest.fixture(scope="module")
def suite() -> dict[str, Any]:
    """Return the suite file."""
    return load_suite()


@pytest.fixture(scope="module")
def questions(suite) -> list[Question]:
    """Return the fixture questions."""
    return load_questions(suite)


@pytest.fixture(scope="module")
def fixture_index(suite, tmp_path_factory):
    """Build the fixture index once for the module, in a temporary folder, and open it."""
    path = tmp_path_factory.mktemp("retrieval") / "chroma"
    store.build_index(fixture_chunks(suite, load_sources()), ConceptEmbeddings(), path)
    return store.open_index(ConceptEmbeddings(), path)


def _report(scores: Scores) -> str:
    """Describe the rates and what each question lost, for a failure message."""
    return (
        f"hit rate {scores.hit_rate:.4f}, no-sources rate {scores.no_sources_rate:.4f}; "
        f"missed {scores.missed}; off-topic questions answered {scores.answered_off_topic}; "
        f"chunks of another topic {scores.wrong_topic}"
    )


def test_the_rates_do_not_drop_below_the_recorded_ones(fixture_index, questions, suite):
    """The real pipeline finds at least the recorded share of chunks and of off-topic refusals."""
    scores = run_suite(fixture_index, questions)
    assert scores.hit_rate >= suite["recorded_hit_rate"], _report(scores)
    assert scores.no_sources_rate >= suite["recorded_no_sources_rate"], _report(scores)
    # The training retry keeps its topic: no nutrition chunk joins a training answer (T9.20).
    assert scores.wrong_topic == {}, _report(scores)


def test_only_the_known_misses_are_missed(fixture_index, questions):
    """Today's misses are exactly the known limits the fixture records, nothing else."""
    scores = run_suite(fixture_index, questions)
    known = {q.id: q.known_missed for q in questions if q.known_missed}
    assert known, "The fixture records its known miss."
    assert scores.missed == known, _report(scores)
    assert scores.answered_off_topic == {}, _report(scores)


def test_the_fixture_index_is_built_by_the_ingest_and_store_code(suite, fixture_index):
    """Each section is one chunk with the ingest step's metadata, all of them in the index."""
    sources = load_sources()
    chunks = fixture_chunks(suite, sources)
    sections = sum(len(suite["texts"][source.id]) for source in sources)
    assert len(chunks) == sections
    stored = fixture_index.get(include=["metadatas"])
    assert sorted(stored["ids"]) == sorted(store.chunk_id(chunk) for chunk in chunks)
    by_id = dict(zip(stored["ids"], stored["metadatas"], strict=True))
    for source in sources:
        metadata = by_id[f"{source.id}-0"]
        assert metadata["year"] == source.year
        assert metadata["evidence_tier"] == source.evidence_tier
        assert metadata["source_url"] == source.url
        assert metadata["license"] == source.license
    # Every source of the fixture has text, and every text belongs to a listed source.
    assert set(suite["texts"]) == {source.id for source in sources}
    # A chunk with no concept word points along the constant alone, as an off-topic question
    # does, and would pass the gate for it (found while calibrating T8.5).
    embeddings = ConceptEmbeddings()
    for chunk in chunks:
        assert any(embeddings.embed_query(chunk.page_content)[:-1]), store.chunk_id(chunk)


def test_the_fixture_questions_and_recorded_rates_are_well_formed(suite, questions):
    """Every expected chunk exists, IDs are unique, and the rates are shares of four decimals."""
    sources = load_sources()
    ids = {store.chunk_id(chunk) for chunk in fixture_chunks(suite, sources)}
    assert len({question.id for question in questions}) == len(questions)
    for question in questions:
        assert set(question.expected) <= ids, question.id
        # A typo here would show up as a missed or stray chunk, not as a fixture error.
        assert set(question.known_missed) <= set(question.expected), question.id
        assert question.only_topic is None or question.only_topic in config.TOPICS, question.id
    # Both rates need questions to count: some with expected chunks, some off topic.
    assert any(question.expected for question in questions)
    assert any(not question.expected for question in questions)
    for key in ("recorded_hit_rate", "recorded_no_sources_rate"):
        rate = suite[key]
        assert 0 <= rate <= 1
        assert round(rate, 4) == rate


def test_the_concept_embeddings_put_shared_concepts_close_and_off_topic_text_far():
    """Texts with the same concepts get the same direction; words outside every concept add none."""
    embeddings = ConceptEmbeddings()
    protein, also_protein, off_topic = embeddings.embed_documents(
        ["Protein at meals.", "More protein per meal, velorin.", "The offside rule in football."]
    )
    assert protein == also_protein
    assert off_topic == [0.0] * len(CONCEPTS) + [_BIAS]
    assert embeddings.embed_query("Protein at meals.") == protein


def _cap_of_one(monkeypatch):
    """Break the pipeline: keep one chunk per source."""
    monkeypatch.setattr(config, "MAX_CHUNKS_PER_SOURCE", 1)


def _no_cap(monkeypatch):
    """Break the pipeline: no per-source cap."""
    monkeypatch.setattr(config, "MAX_CHUNKS_PER_SOURCE", 10_000)


def _no_filter(monkeypatch):
    """Break the pipeline: the plan's filters are ignored."""
    monkeypatch.setattr(query_translation, "build_filter", lambda plan: None)


def _no_gate(monkeypatch):
    """Break the pipeline: every distance passes the coverage gate."""
    monkeypatch.setattr(config, "RETRIEVAL_MAX_DISTANCE", 2.0)


def _nothing_else(monkeypatch):
    """Leave the rest of the pipeline as it is (the break is in the keyword index given)."""


def _no_keywords(built) -> KeywordIndex:
    """Break the pipeline: keyword search finds nothing (BM25 removed)."""
    return KeywordIndex([])


@pytest.mark.parametrize(
    ("breaks", "keyword_index", "rate", "lost"),
    [
        (_cap_of_one, hybrid.build_keyword_index, "hit_rate", "cap_second_chunk"),
        (_no_cap, hybrid.build_keyword_index, "hit_rate", "cap"),
        (_nothing_else, _no_keywords, "hit_rate", "keyword"),
        (_no_filter, hybrid.build_keyword_index, "hit_rate", "year_filter"),
        (_no_gate, hybrid.build_keyword_index, "no_sources_rate", None),
    ],
    ids=["cap of one", "no cap", "no BM25", "no filter", "no gate"],
)
def test_a_deliberate_break_drops_a_rate_below_the_recorded_one(
    fixture_index, questions, suite, monkeypatch, breaks, keyword_index, rate, lost
):
    """Each broken step of the pipeline makes the suite fail, so the fixture stays sensitive."""
    breaks(monkeypatch)
    scores = run_suite(fixture_index, questions, keyword_index)
    assert getattr(scores, rate) < suite[f"recorded_{rate}"], _report(scores)
    if lost is not None:
        assert lost in scores.missed, _report(scores)


def test_a_retry_that_searches_everything_lets_a_nutrition_chunk_into_the_training_answer(
    fixture_index, questions, monkeypatch
):
    """Breaking the training retry (it falls through to an unfiltered search) fails the suite."""
    # No plan's topic is the training topic any more, and the nutrition-only retry filters
    # nothing, so a training-only plan whose filter found nothing is searched over everything.
    # The stray chunk is then 6-0, which BM25 finds through the rewrite's word "time".
    monkeypatch.setattr(config, "TRAINING_TOPIC", "not_a_topic")
    monkeypatch.setattr(chat, "_NUTRITION_ONLY", None)
    scores = run_suite(fixture_index, questions)
    assert "training_retry" in scores.wrong_topic, _report(scores)
