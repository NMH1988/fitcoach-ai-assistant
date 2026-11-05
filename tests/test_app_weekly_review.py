"""UI tests for the weekly review on the coach's Client week and the gymer's My week (T9.16).

The run goes through the real workflow (src/agent/review.py) with a fake model, no index (the
evidence search is replaced) and a stand-in prompt, written for these tests only (the owner writes
the real one, O15). AC-28, AC-29, AC-30, AC-35, AC-41.
"""

import json
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from src import config, llm, metrics
from src.agent import review
from src.store import db, reviews, users
from tests.fakes import ScriptedTranslator
from tests.test_app_account import PROFILE, USER_ID, signed_in, start, store_account
from tests.test_app_dashboards import ALEX, BO, MONDAY, _gymer_with_week, _pair
from tests.test_app_sharing import open_page, page_text
from views import client_week, navigation, resources
from views import weekly_review as view

pytestmark = pytest.mark.usefixtures("no_env_key")

TODAY = date(2026, 11, 5)  # the week of 2026-10-26 is over; the week of 2026-11-02 is not
STAND_IN_PROMPT = "Stand-in review prompt for the tests (the owner writes the real one, O15)."
NUTRITION = {
    "kind": "nutrition",
    "text": "Log every day next week.",
    "evidence": [],
    "model_suggestion": True,
    "direction": None,
    "source_range": None,
    "population": None,
}
GOOD = json.dumps(
    {
        "observations": [{"text": "The client logged 3 of 7 days.", "evidence": []}],
        "hypotheses": [{"text": "Weekends may be harder to log.", "evidence": []}],
        "recommendations": [NUTRITION],
    }
)


@pytest.fixture(autouse=True)
def setting(monkeypatch, tmp_path):
    """Fix today, write the stand-in prompt and leave the evidence search out (no index)."""
    monkeypatch.setattr(metrics, "berlin_day", lambda moment=None: TODAY)
    prompt = tmp_path / "weekly_review_system.md"
    prompt.write_text(STAND_IN_PROMPT, encoding="utf-8")
    monkeypatch.setattr(config, "REVIEW_PROMPT_PATH", prompt)
    monkeypatch.setattr(review, "_search", lambda context, topics: [])


@pytest.fixture
def coach_world():
    """Store the canary coach with Alex (nutrition, body) and Bo (training only)."""
    store_account("coach", name="Coach Sam")
    with db.connect() as conn:
        for user_id, name in ((ALEX, "Alex"), (BO, "Bo")):
            _gymer_with_week(conn, user_id, name)
        _pair(conn, USER_ID, ALEX, ("nutrition", "body"))
        _pair(conn, USER_ID, BO, ("training",))


def _model(monkeypatch, *replies) -> ScriptedTranslator:
    """Make the review model a fake that gives the replies in order."""
    fake = ScriptedTranslator(plans=list(replies), model_name=config.REVIEW_MODEL)
    monkeypatch.setattr(resources, "review_model", lambda: fake)
    return fake


def _week(monkeypatch, client: str = ALEX, monday: date = MONDAY, language="en") -> AppTest:
    """Open the client's week on the Client week page as the canary coach."""
    at = open_page(start(monkeypatch, user=signed_in(), language=language), navigation.CLIENT_WEEK)
    at.selectbox(key=client_week.PICK_KEY).set_value(client).run(timeout=30)
    at.date_input(key=client_week.WEEK_KEY).set_value(monday).run(timeout=30)
    return at


def _button(at: AppTest, label: str):
    """Return the main area's button with the label."""
    [found] = [item for item in at.main.button if item.label == label]
    return found


def _labels(at: AppTest) -> list[str]:
    """Return the labels of the main area's buttons."""
    return [item.label for item in at.main.button]


def _stored() -> list[dict]:
    """Return every stored review, oldest first."""
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM ai_reviews ORDER BY id")]


def _drafted(monkeypatch, *replies, language="en") -> AppTest:
    """Open Alex's finished week and draft a review with the fake model's replies."""
    _model(monkeypatch, *replies)
    at = _week(monkeypatch, language=language)
    _button(at, {"en": "Draft weekly review", "de": "Wochenbericht entwerfen"}[language]).click()
    return at.run(timeout=30)


def test_the_coach_drafts_a_review_of_a_finished_week_and_it_waits(monkeypatch, coach_world):
    """The draft is saved as pending and shown with Approve, Edit and Reject (AC-28)."""
    at = _drafted(monkeypatch, GOOD)
    page = page_text(at)
    assert "The draft is ready below for your decision." in page
    assert "Draft for the week of 2026-10-26, waiting for your decision" in page
    assert "The client logged 3 of 7 days." in page
    assert "The model's suggestion, no source cited" in page
    assert {"Approve", "Edit", "Reject"} <= set(_labels(at))
    [row] = _stored()
    assert row["status"] == "PENDING_REVIEW" and row["client_id"] == ALEX
    assert "AI model, reached through OpenRouter" in page


def test_the_week_in_progress_offers_no_review(monkeypatch, coach_world):
    """A week whose Sunday has not passed says so and has no button."""
    _model(monkeypatch, GOOD)
    at = _week(monkeypatch, monday=date(2026, 11, 2))
    assert "A week can be reviewed once it is over" in page_text(at)
    assert "Draft weekly review" not in _labels(at)


def test_a_client_who_does_not_share_nutrition_gets_no_review(monkeypatch, coach_world):
    """Bo shares training only: the section says nutrition is needed and offers nothing."""
    at = _week(monkeypatch, client=BO)
    assert "A weekly review needs the client to share Nutrition." in page_text(at)
    assert "Draft weekly review" not in _labels(at)


def test_approving_releases_the_review_to_the_client(monkeypatch, coach_world):
    """Approve stores the decision; the page shows the approved review with its AI label."""
    at = _drafted(monkeypatch, GOOD)
    _button(at, "Approve").click()
    at.run(timeout=30)
    page = page_text(at)
    assert "Approved: the client can now read the review." in page
    assert "AI draft, approved by the coach" in page
    assert "Week of 2026-10-26" in page
    [row] = _stored()
    assert row["status"] == "APPROVED" and row["reviewed_by"] == USER_ID
    with db.connect() as conn:
        [seen] = reviews.list_reviews(conn, ALEX, ALEX)
    assert seen["final"]["observations"][0]["text"] == "The client logged 3 of 7 days."


def test_rejecting_keeps_it_from_the_client_and_allows_a_new_draft(monkeypatch, coach_world):
    """Reject: the client never sees it, and the week can be drafted again."""
    at = _drafted(monkeypatch, GOOD)
    _button(at, "Reject").click()
    at.run(timeout=30)
    page = page_text(at)
    assert "Rejected: the client will not see this draft." in page
    assert "You rejected the draft for this week." in page
    assert "Draft weekly review" in _labels(at)
    with db.connect() as conn:
        assert reviews.list_reviews(conn, ALEX, ALEX) == []


def _edit(at: AppTest, text: str) -> AppTest:
    """Open the edit form, change the first observation and approve the edit."""
    _button(at, "Edit").click()
    at.run(timeout=30)
    at.text_area[0].set_value(text)
    [submit] = [item for item in at.button if item.label == "Approve my edit"]
    submit.click()
    return at.run(timeout=30)


def test_an_edit_with_a_diagnosis_is_refused_and_the_review_keeps_waiting(monkeypatch, coach_world):
    """The coach's edit passes the same checks: a diagnosis is refused, nothing released (AC-35)."""
    at = _edit(_drafted(monkeypatch, GOOD), "Signs of an eating disorder.")
    page = page_text(at)
    assert "Your edit was not saved: a text names a medical condition or a diagnosis." in page
    [row] = _stored()
    assert row["status"] == "PENDING_REVIEW"
    # The form stays open with the coach's text, so it can be fixed.
    assert at.text_area[0].value == "Signs of an eating disorder."


def test_a_clean_edit_is_released_as_edited(monkeypatch, coach_world):
    """An edit that passes is approved, marked as edited, and the client reads the coach's text."""
    at = _edit(_drafted(monkeypatch, GOOD), "Three days logged; ask about the weekend.")
    page = page_text(at)
    assert "Your edited review was approved: the client can now read it." in page
    assert "AI draft, edited and approved by the coach" in page
    with db.connect() as conn:
        [seen] = reviews.list_reviews(conn, ALEX, ALEX)
    assert seen["edited_by_coach"] is True
    assert seen["final"]["observations"][0]["text"] == "Three days logged; ask about the weekend."


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "The model service took too long to answer. Please try again."),
        ("de", "Der Modelldienst hat zu lange"),
    ],
)
def test_a_model_timeout_saves_nothing_and_shows_a_fixed_message(
    monkeypatch, coach_world, language, message
):
    """AC-30: no review, the fixed message in the chosen language, the button still there."""
    at = _drafted(monkeypatch, llm.LLMTimeoutError(diagnostic="x"), language=language)
    assert any(message in item.value for item in at.error)
    assert _stored() == []
    start_label = {"en": "Draft weekly review", "de": "Wochenbericht entwerfen"}[language]
    assert start_label in _labels(at)


def test_two_failed_drafts_save_nothing_and_say_so(monkeypatch, coach_world):
    """A draft that fails its checks twice: no review, and the coach may try again."""
    bad = json.dumps(
        {
            "observations": [{"text": "Diabetes is likely.", "evidence": []}],
            "hypotheses": [],
            "recommendations": [],
        }
    )
    at = _drafted(monkeypatch, bad, bad)
    assert "did not pass the app's checks twice" in page_text(at)
    assert _stored() == []


def test_a_missing_prompt_stops_the_run_with_its_message(monkeypatch, coach_world, tmp_path):
    """Without the owner's prompt file, no model is called and a fixed message says why."""
    monkeypatch.setattr(config, "REVIEW_PROMPT_PATH", tmp_path / "missing.md")
    fake = _model(monkeypatch, GOOD)
    at = _week(monkeypatch)
    _button(at, "Draft weekly review").click()
    at.run(timeout=30)
    assert any("weekly_review_system.md" in item.value for item in at.error)
    assert fake.calls == [] and _stored() == []


def test_the_section_in_german(monkeypatch, coach_world):
    """The buttons and the AI notice in German."""
    at = _drafted(monkeypatch, GOOD, language="de")
    assert {"Freigeben", "Bearbeiten", "Verwerfen"} <= set(_labels(at))
    assert "über OpenRouter" in page_text(at)


def test_the_edited_text_drops_emptied_items_and_keeps_the_rest():
    """edited_text(): new texts replace old ones, an empty text leaves its item out."""
    draft = json.loads(GOOD)
    found = view.edited_text(
        draft,
        {("observations", 0, "text"): " New. ", ("hypotheses", 0, "text"): "  "},
    )
    assert found["observations"][0]["text"] == "New."
    assert found["hypotheses"] == []
    assert found["recommendations"] == [NUTRITION]


def test_a_gymer_reads_an_approved_review_s_sections_and_label(monkeypatch):
    """My week shows the sections, the suggestion label and the AI label (AC-41)."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, "coach-kai", "coach", "Coach Kai")
        _pair(conn, "coach-kai", USER_ID, ("nutrition",))
        found = reviews.save_review(
            conn,
            "coach-kai",
            USER_ID,
            period_start=MONDAY,
            metrics={},
            data_quality={},
            draft={**json.loads(GOOD), "language": "en", "sources": {}},
            model_version=config.REVIEW_MODEL,
        )
        reviews.decide_review(conn, "coach-kai", found, "approve")
    at = open_page(start(monkeypatch, user=signed_in()), navigation.MY_WEEK)
    page = page_text(at)
    for line in ("Observations", "Possible reasons", "Recommendations"):
        assert line in page
    assert "The model's suggestion, no source cited" in page
    assert any(item.value.endswith("AI draft, approved by the coach") for item in at.caption)


def test_the_session_rate_limit_stops_a_new_run(monkeypatch, coach_world):
    """A review counts against the session's limit: at the limit no model is called."""
    from src import guard

    fake = _model(monkeypatch, GOOD)
    at = _week(monkeypatch)
    limiter = guard.session_limiter(at.session_state)
    limiter.total = limiter.per_session
    _button(at, "Draft weekly review").click()
    at.run(timeout=30)
    assert any("reached its limit" in item.value for item in at.warning)
    assert fake.calls == [] and _stored() == []


def test_a_store_that_fails_during_a_run_shows_its_fixed_message(monkeypatch, coach_world):
    """The store's fixed message shows after the rerun, not lost to it (code review round 2)."""
    from src import account as accounts

    def unavailable(*args, **kwargs):
        """Fail as a store that cannot be used does."""
        raise accounts.StoreUnavailable

    _model(monkeypatch, GOOD)
    at = _week(monkeypatch)
    monkeypatch.setattr(view.review, "start_review", unavailable)
    _button(at, "Draft weekly review").click()
    at.run(timeout=30)
    assert any("cannot be opened right now" in item.value for item in at.error)


def test_too_many_starts_in_the_window_are_refused_with_the_wait(monkeypatch, coach_world):
    """The window limit: the coach is told how long to wait, and no model is called."""
    from src import guard

    fake = _model(monkeypatch, GOOD)
    at = _week(monkeypatch)
    limiter = guard.session_limiter(at.session_state)
    for _ in range(limiter.per_window):
        assert limiter.try_acquire() is None
    _button(at, "Draft weekly review").click()
    at.run(timeout=30)
    assert any("starting reviews too fast" in item.value for item in at.warning)
    assert fake.calls == [] and _stored() == []


def test_a_store_that_fails_on_a_decision_shows_its_fixed_message(monkeypatch, coach_world):
    """Approve with the store failing: its fixed message shows after the rerun, nothing changes."""
    from src import account as accounts

    def unavailable(*args, **kwargs):
        """Fail as a store that cannot be used does."""
        raise accounts.StoreUnavailable

    at = _drafted(monkeypatch, GOOD)
    monkeypatch.setattr(view.review, "decide_review", unavailable)
    _button(at, "Approve").click()
    at.run(timeout=30)
    assert any("cannot be opened right now" in item.value for item in at.error)
    [row] = _stored()
    assert row["status"] == "PENDING_REVIEW"
