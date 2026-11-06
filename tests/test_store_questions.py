"""Questions to the coach under an approved review, and the answers, in the store (T9.25, AC-42).

The rule is the review's own (T9.16): the coach reads and answers while the relationship is active
and the client shares nutrition and every scope the review used; the gymer asks by the same rule.
"""

import sqlite3
from datetime import date

import pytest

from src import config
from src.store import access, questions, reviews, users
from src.store.values import StoreValueError
from tests import store_world as world

QUESTION = "CANARY-QUESTION why fewer carbs on rest days?"
ANSWER = "CANARY-ANSWER because you train less then."
# The scopes of the review most tests ask under.
SCOPES_NT = ("nutrition", "training")


@pytest.fixture
def rel(store_conn):
    """Build the made-up world and return its relationship IDs."""
    return world.build(store_conn)


def _review(conn, coach, client, week, scopes=("nutrition",), decision="approve"):
    """Save a review of a week with the scopes and decide it (None leaves it pending)."""
    review = reviews.save_review(
        conn,
        coach,
        client,
        period_start=week,
        metrics={"logged_days": 3},
        data_quality={},
        draft={"observations": ["x"]},
        model_version="m",
        scopes=scopes,
    )
    if decision is not None:
        reviews.decide_review(conn, coach, review, decision)
    return review


def _rows(conn):
    """Return every thread row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM review_questions ORDER BY id")]


def _audit(conn):
    """Return every audit row as a dict."""
    return [dict(row) for row in conn.execute("SELECT * FROM audit_log ORDER BY id")]


@pytest.fixture
def approved(store_conn, rel):
    """An approved review of SHARED by coach A that used nutrition and training."""
    return _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 19), scopes=SCOPES_NT)


# --- The gymer asks -------------------------------------------------------------------------------


def test_the_gymer_asks_under_an_approved_review_without_an_audit_row(store_conn, approved):
    """The question is stored with its review, author and kind; asking one's own is not audited."""
    before = _audit(store_conn)
    question = questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    [row] = _rows(store_conn)
    assert row["id"] == question
    assert (row["review_id"], row["author_id"], row["kind"], row["text"]) == (
        approved,
        world.SHARED,
        "question",
        QUESTION,
    )
    assert row["created_at"].endswith("+00:00")
    assert _audit(store_conn) == before


def _refuse_ask(conn, actor, review_id):
    """Check the question is refused with the one NotFound and nothing is written or audited."""
    rows, audit_rows = _rows(conn), _audit(conn)
    with pytest.raises(access.NotFound) as caught:
        questions.ask_question(conn, actor, review_id, QUESTION)
    assert type(caught.value) is access.NotFound and str(caught.value) == "not found"
    assert _rows(conn) == rows and _audit(conn) == audit_rows


def test_a_pending_or_rejected_review_takes_no_question(store_conn, rel):
    """Only an approved review has a thread."""
    pending = _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 12), decision=None)
    rejected = _review(
        store_conn, world.COACH_A, world.SHARED, date(2026, 10, 5), decision="reject"
    )
    for review in (pending, rejected):
        _refuse_ask(store_conn, world.SHARED, review)


@pytest.mark.parametrize(
    "actor",
    [world.UNSHARED, world.OTHERS, world.ENDED, world.COACH_A, world.COACH_B, world.MISSING, None],
)
def test_only_the_reviewed_gymer_asks(store_conn, approved, actor):
    """Another gymer, a coach (the review's own too) or a missing user gets NotFound."""
    _refuse_ask(store_conn, actor, approved)


def test_another_coach_s_review_takes_no_question_from_another_gymer(store_conn, rel):
    """Coach B's review of OTHERS is not SHARED's to ask under."""
    others = _review(store_conn, world.COACH_B, world.OTHERS, date(2026, 10, 19))
    _refuse_ask(store_conn, world.SHARED, others)


@pytest.mark.parametrize("review_id", [999, None, "1", True, 0, -1, 2**64])
def test_a_missing_or_malformed_review_is_not_found(store_conn, approved, review_id):
    """No such review, or an ID that is not a row ID, gives the same NotFound."""
    _refuse_ask(store_conn, world.SHARED, review_id)


def test_an_ended_relationship_takes_no_question(store_conn, rel, approved):
    """Once either side ends the relationship, its coach could not read it, so nothing is asked."""
    users.end_relationship(store_conn, world.SHARED, rel[world.SHARED])
    _refuse_ask(store_conn, world.SHARED, approved)


@pytest.mark.parametrize("scope", SCOPES_NT)
def test_a_scope_the_review_used_turned_off_takes_no_question(store_conn, rel, approved, scope):
    """Nutrition, or a scope the review's metrics used, turned off: no question is written."""
    users.set_consent(store_conn, world.SHARED, rel[world.SHARED], scope, False)
    _refuse_ask(store_conn, world.SHARED, approved)


def test_a_scope_the_review_did_not_use_does_not_matter(store_conn, rel, approved):
    """Body off does not close a review that used nutrition and training only."""
    users.set_consent(store_conn, world.SHARED, rel[world.SHARED], "body", False)
    assert questions.ask_question(store_conn, world.SHARED, approved, QUESTION)


# --- Turns ----------------------------------------------------------------------------------------


def test_the_thread_takes_turns(store_conn, approved):
    """A second question waits for the answer; the coach answers once per question."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    with pytest.raises(questions.NotYourTurn):
        questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    with pytest.raises(questions.NotYourTurn):
        questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    assert [row["kind"] for row in _rows(store_conn)] == ["question", "answer", "question"]


def test_the_coach_cannot_answer_an_empty_thread(store_conn, approved):
    """No question, nothing to answer: NotYourTurn and no row."""
    with pytest.raises(questions.NotYourTurn) as caught:
        questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    assert str(caught.value) == "the thread waits for the other side"
    assert _rows(store_conn) == []


def test_a_review_takes_at_most_the_configured_number_of_questions(store_conn, approved):
    """After REVIEW_THREAD_MAX_QUESTIONS answered questions, one more is refused."""
    for _ in range(config.REVIEW_THREAD_MAX_QUESTIONS):
        questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
        questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    with pytest.raises(questions.NotYourTurn):
        questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    assert len(_rows(store_conn)) == 2 * config.REVIEW_THREAD_MAX_QUESTIONS


# --- The coach answers ----------------------------------------------------------------------------


def test_an_answer_writes_one_audit_row_without_the_text(store_conn, approved):
    """review_answered, review_questions, the new row's ID, the client; no text in the row."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    before = len(_audit(store_conn))
    answer = questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    [row] = _audit(store_conn)[before:]
    assert (row["actor_id"], row["subject_id"], row["action"]) == (
        world.COACH_A,
        world.SHARED,
        "review_answered",
    )
    assert (row["resource_type"], row["resource_id"]) == ("review_questions", answer)
    assert "CANARY" not in str(row)
    assert _rows(store_conn)[-1]["author_id"] == world.COACH_A


def _refuse_answer(conn, actor, review_id):
    """Check the answer is refused with NotFound and nothing is written or audited."""
    rows, audit_rows = _rows(conn), _audit(conn)
    with pytest.raises(access.NotFound) as caught:
        questions.answer_question(conn, actor, review_id, ANSWER)
    assert str(caught.value) == "not found"
    assert _rows(conn) == rows and _audit(conn) == audit_rows


@pytest.mark.parametrize("actor", [world.COACH_B, world.SHARED, world.UNSHARED, world.MISSING, 5])
def test_only_the_review_s_coach_answers(store_conn, approved, actor):
    """Another coach, the gymer, another gymer or a missing user gets NotFound."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    _refuse_answer(store_conn, actor, approved)


def test_the_coach_cannot_answer_after_the_relationship_ends(store_conn, rel, approved):
    """A question asked before the end stays unanswered: the coach no longer reads the review."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    users.end_relationship(store_conn, world.COACH_A, rel[world.SHARED])
    _refuse_answer(store_conn, world.COACH_A, approved)


@pytest.mark.parametrize("scope", SCOPES_NT)
def test_the_coach_cannot_answer_once_a_used_scope_is_off(store_conn, rel, approved, scope):
    """Nutrition or a scope the review used turned off after the question: no answer."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    users.set_consent(store_conn, world.SHARED, rel[world.SHARED], scope, False)
    _refuse_answer(store_conn, world.COACH_A, approved)


def test_a_pending_review_takes_no_answer(store_conn, rel):
    """A pending review has no thread, so its coach answers nothing."""
    pending = _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 12), decision=None)
    _refuse_answer(store_conn, world.COACH_A, pending)


# --- Reads ----------------------------------------------------------------------------------------


def test_the_gymer_reads_the_thread_also_after_the_end(store_conn, rel, approved):
    """The gymer's threads stay readable once the relationship ends (owner's choice, 2026-11-06)."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    questions.answer_question(store_conn, world.COACH_A, approved, ANSWER)
    users.end_relationship(store_conn, world.SHARED, rel[world.SHARED])
    rows = questions.list_questions(store_conn, world.SHARED, world.SHARED)
    assert [(row["kind"], row["text"]) for row in rows] == [
        ("question", QUESTION),
        ("answer", ANSWER),
    ]
    with pytest.raises(access.NotFound):
        questions.list_questions(store_conn, world.COACH_A, world.SHARED)


def test_the_coach_s_read_is_audited_once_without_text(store_conn, approved):
    """A coach reading a client's threads leaves one read row on review_questions."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    before = len(_audit(store_conn))
    [row] = questions.list_questions(store_conn, world.COACH_A, world.SHARED)
    assert row["text"] == QUESTION
    [audit_row] = _audit(store_conn)[before:]
    assert (audit_row["action"], audit_row["resource_type"], audit_row["subject_id"]) == (
        "read",
        "review_questions",
        world.SHARED,
    )
    assert "CANARY" not in str(audit_row)


def test_the_coach_does_not_read_a_thread_whose_review_used_a_scope_now_off(store_conn, rel):
    """With training off, the thread of a review that used it is hidden; a nutrition one is not."""
    trained = _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 19), SCOPES_NT)
    plain = _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 12))
    for review in (trained, plain):
        questions.ask_question(store_conn, world.SHARED, review, QUESTION)
    users.set_consent(store_conn, world.SHARED, rel[world.SHARED], "training", False)
    rows = questions.list_questions(store_conn, world.COACH_A, world.SHARED)
    assert [row["review_id"] for row in rows] == [plain]
    assert len(questions.list_questions(store_conn, world.SHARED, world.SHARED)) == 2


def test_a_coach_s_own_read_covers_clients_who_share_and_audits_each(store_conn, approved):
    """A coach reading their own gets every sharing client's threads, one read row per client."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    before = len(_audit(store_conn))
    rows = questions.list_questions(store_conn, world.COACH_A, world.COACH_A)
    assert [row["review_id"] for row in rows] == [approved]
    [audit_row] = _audit(store_conn)[before:]
    assert (audit_row["subject_id"], audit_row["resource_type"]) == (
        world.SHARED,
        "review_questions",
    )
    assert questions.list_questions(store_conn, world.COACH_B, world.COACH_B) == []


def test_another_gymer_s_threads_are_never_read(store_conn, rel, approved):
    """OTHERS reads only the threads about them, never SHARED's."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    assert questions.list_questions(store_conn, world.OTHERS, world.OTHERS) == []


# --- Which reviews the gymer may ask under --------------------------------------------------------


def test_askable_reviews_follow_the_review_s_rule(store_conn, rel, approved):
    """Approved and still readable by the coach: listed; training off or the end: not listed."""
    plain = _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 12))
    _review(store_conn, world.COACH_A, world.SHARED, date(2026, 10, 5), decision=None)
    assert questions.askable_reviews(store_conn, world.SHARED) == {approved, plain}
    users.set_consent(store_conn, world.SHARED, rel[world.SHARED], "training", False)
    assert questions.askable_reviews(store_conn, world.SHARED) == {plain}
    users.end_relationship(store_conn, world.SHARED, rel[world.SHARED])
    assert questions.askable_reviews(store_conn, world.SHARED) == frozenset()


def test_askable_reviews_of_a_coach_or_a_missing_user(store_conn, approved):
    """A coach asks under nothing; a missing user is not found."""
    assert questions.askable_reviews(store_conn, world.COACH_A) == frozenset()
    with pytest.raises(access.NotFound):
        questions.askable_reviews(store_conn, world.MISSING)


# --- Limits ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None, 5, "x" * (config.REVIEW_THREAD_MAX_CHARS + 1)])
def test_a_question_or_answer_must_be_text_within_the_limit(store_conn, approved, bad):
    """Empty, blank, non-text or too long is refused, naming the field, never the value."""
    with pytest.raises(StoreValueError) as caught:
        questions.ask_question(store_conn, world.SHARED, approved, bad)
    assert str(caught.value) == "text must be non-empty text within the length limit"
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    with pytest.raises(StoreValueError):
        questions.answer_question(store_conn, world.COACH_A, approved, bad)
    assert len(_rows(store_conn)) == 1


def test_the_longest_text_is_accepted(store_conn, approved):
    """A question of exactly REVIEW_THREAD_MAX_CHARS characters is stored."""
    text = "x" * config.REVIEW_THREAD_MAX_CHARS
    questions.ask_question(store_conn, world.SHARED, approved, text)
    assert _rows(store_conn)[0]["text"] == text


def test_the_limit_fits_the_store_s_text_limit():
    """The thread's limit is within what the store accepts in any text field."""
    assert 0 < config.REVIEW_THREAD_MAX_CHARS <= config.STORE_TEXT_MAX_CHARS
    assert config.REVIEW_THREAD_MAX_QUESTIONS >= 1


def test_the_question_row_cannot_be_changed(store_conn, approved):
    """The table's trigger refuses an UPDATE; a question is never edited in place."""
    questions.ask_question(store_conn, world.SHARED, approved, QUESTION)
    with pytest.raises(sqlite3.IntegrityError, match="never changed in place"):
        store_conn.execute("UPDATE review_questions SET text = 'changed'")
