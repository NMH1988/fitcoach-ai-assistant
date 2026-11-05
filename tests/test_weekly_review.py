"""The weekly review's schema, aggregates, messages and checks (T9.16; AC-26, AC-27, AC-35).

The chunk texts below are made up for the tests (copyright policy): they quote no source.
"""

import copy
import json
from datetime import date

import pytest

from src import config, dashboard, i18n, metrics
from src import weekly_review as wr
from src.agent import graph
from src.rag.retriever import RetrievedChunk, chunk_key

MONDAY = date(2026, 10, 19)
ALL = ("nutrition", "training", "body")
PROTEIN_TEXT = (
    "In trained adults, a protein intake of 1.6 to 2.2 g per kg of body weight per day "
    "supported gains in lean mass."
)
TRAINING_TEXT = (
    "Studies in resistance-trained men found that 10–20 sets per muscle group per week "
    "produced more hypertrophy than fewer sets."
)


def _chunk(source_id: str, index: int, text: str, topics: list[str]) -> RetrievedChunk:
    """Return a made-up retrieved chunk with the metadata the index gives."""
    meta = {
        "source_id": source_id,
        "chunk_index": index,
        "title": f"Made-up review {source_id}",
        "year": 2020,
        "evidence_tier": 2,
        "topics": topics,
    }
    return RetrievedChunk(text, meta, 0.3)


CHUNKS = [
    _chunk("12", 3, PROTEIN_TEXT, ["protein"]),
    _chunk("24", 1, TRAINING_TEXT, [config.TRAINING_TOPIC]),
]


def _meal(day: str, kcal: float, protein: float, fiber: float | None = 10.0) -> dict:
    """Return a stored meal item as the store gives it."""
    return {
        "consumed_on": day,
        "kcal": kcal,
        "protein_g": protein,
        "carbohydrate_g": 250.0,
        "fat_g": 70.0,
        "fiber_g": fiber,
    }


def _week(scopes=ALL) -> dashboard.DashboardWeek:
    """Return a made-up client week: 3 of 7 days logged, below target, one squat session."""
    meals = [
        _meal("2026-10-19", 2000.0, 120.0),
        _meal("2026-10-20", 2400.0, 130.0),
        _meal("2026-10-22", 2210.0, 110.0),
    ]
    targets = [
        {
            "id": 1,
            "kcal": 2500.0,
            "protein_g": 160.0,
            "carbs_g": 280.0,
            "fat_g": 80.0,
            "effective_from": "2026-10-01",
            "set_by": "system",
        }
    ]
    weights = [
        {"id": 1, "measured_on": "2026-10-12", "weight_kg": 80.0},
        {"id": 2, "measured_on": "2026-10-24", "weight_kg": 79.5},
    ]
    sessions = [
        {
            "id": 1,
            "performed_on": "2026-10-20",
            "sets": [
                {"exercise_id": "squat", "set_no": n, "reps": 5, "weight_kg": 100.0}
                for n in (1, 2, 3)
            ],
        }
    ]
    sunday = metrics.week_days(MONDAY)[-1]
    return dashboard.DashboardWeek(
        shared=frozenset(scopes),
        nutrition=metrics.week_metrics(meals, weights if "body" in scopes else [], targets, MONDAY),
        training=metrics.training_week(sessions, MONDAY) if "training" in scopes else None,
        volume_by_day=None,
        weight_trend=(
            metrics.weights_between(weights, date(2026, 9, 1), sunday) if "body" in scopes else None
        ),
        reviews=None,
    )


METRICS = wr.aggregates(_week(), ALL)


def _good() -> dict:
    """Return a draft that passes every check."""
    return {
        "observations": [
            {
                "text": "The client logged 3 of 7 days, averaging 2203.3 kcal, 88% of the 2500 "
                "kcal target.",
                "evidence": [],
            },
            {"text": "Average protein was 120 g against a target of 160 g.", "evidence": []},
            {"text": "The client did 3 sets of squat in 1 session.", "evidence": []},
        ],
        "hypotheses": [
            {"text": "The days not logged may hide part of the intake.", "evidence": []}
        ],
        "recommendations": [
            {
                "kind": "nutrition",
                "text": "Raise daily protein toward 1.6 g per kg of body weight [S1].",
                "evidence": ["S1"],
                "model_suggestion": False,
                "direction": None,
                "source_range": None,
                "population": None,
            },
            {
                "kind": "training",
                "text": "Consider more weekly leg work if recovery allows [S2].",
                "evidence": ["S2"],
                "model_suggestion": False,
                "direction": "increase weekly sets for the legs",
                "source_range": "10-20 sets per muscle group per week",
                "population": "resistance-trained men",
            },
        ],
    }


def _with(path: tuple, value) -> dict:
    """Return the good draft with one field replaced (path: list name, index, field)."""
    draft = copy.deepcopy(_good())
    target = draft
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return draft


def test_the_good_draft_passes():
    """The made-up draft above passes every check, so each case below tests one thing."""
    assert wr.validate(_good(), CHUNKS, METRICS) == []


def test_the_schema_parses_a_good_draft_and_strips_texts():
    """WeeklyReview reads the draft; a blank training field becomes None."""
    draft = _with(("recommendations", 0, "direction"), "   ")
    review = wr.WeeklyReview.model_validate(draft)
    assert review.recommendations[0].direction is None
    assert wr.as_draft(review, "de")["language"] == "de"


@pytest.mark.parametrize(
    "draft",
    [
        _with(("observations",), []),
        _with(("recommendations", 0, "kind"), "sleep"),
        _with(("observations", 0, "text"), " "),
        _with(("observations", 0, "text"), "x" * (config.REVIEW_TEXT_MAX_CHARS + 1)),
        _with(("recommendations", 1, "population"), "x" * (config.REVIEW_FIELD_MAX_CHARS + 1)),
        {"observations": [{"text": "x"}]},
    ],
)
def test_a_draft_off_the_schema_fails_on_the_schema(draft):
    """No observation, an unknown kind, a blank or long text, or a missing field: "schema"."""
    assert wr.validate(draft, CHUNKS, METRICS) == ["schema"]


def test_a_label_not_retrieved_in_this_run_is_refused():
    """A citation of [S9], which <sources> did not hold, fails (AC-27)."""
    draft = _with(("observations", 1, "evidence"), ["S9"])
    assert "unknown_evidence" in wr.validate(draft, CHUNKS, METRICS)


@pytest.mark.parametrize(
    "text",
    [
        "Aim for 1100 kcal per day.",
        "Eat 1.100 kcal a day.",
        "Keep intake at 1,000 calories.",
        "Täglich 1100 Kalorien.",
        "Eat about 1100 kcal a day.",
        "Aim for around 1,000 kcal.",
        "Etwa 1.100 kcal am Tag.",
        "Aim for 1,000-1,100 kcal per day.",
        "Aim for 1000 - 1100 kcal.",
        "Aim for 1,000\u20131,600 kcal.",
        "Eat 1000 to 1300 kcal.",
        "Keep intake at 1050 kcal.",
        "Aim for an intake of 1000 kcal.",
        "Averaged 1050 kcal; aim for 1,000 kcal.",
        # No kcal figure below the floor in a recommendation, not even the current one (owner's
        # choice, code review round 2): the current intake belongs in an observation.
        "The client's average of 1050 kcal is below the 2000 kcal target; raise intake gradually.",
        "Raise intake from 1050 kcal to 1500 kcal.",
        "Raise intake from 1100 to 1300 kcal.",
        "Derzeit 1050 kcal; die Zufuhr schrittweise erhöhen.",
        "Aim for an average of 1,000 kcal per day.",
        "Keep averaging 1,000 kcal.",
        "Start from 1,000 kcal a day.",
        "Eat from 1,000 to 1,300 kcal.",
    ],
)
def test_a_recommended_intake_below_the_floor_is_refused(text):
    """A kcal intake below config.CALORIE_FLOOR_KCAL in a recommendation fails (AC-35)."""
    draft = _with(("recommendations", 0, "text"), text)
    assert "calorie_floor" in wr.validate(draft, CHUNKS, METRICS)
    assert "calorie_floor" in wr.check_edit(draft, CHUNKS)


@pytest.mark.parametrize(
    "text",
    [
        "Reduce intake by 300 kcal per day.",
        "A 300 kcal deficit fits the goal.",
        "Eat about 200 kcal more on training days.",
        "Täglich um 300 kcal weniger.",
        "Keep intake at 2500 kcal.",
        "Reduce by around 300 kcal.",
        "Senken um etwa 300 kcal.",
        "A change of -300 kcal.",
        "Keep intake at or above 1,200 kcal per day.",
        "Mindestens 1.200 kcal pro Tag.",
        "Keep intake at 1,500-1,800 kcal.",
        "Raise intake gradually from the current average toward the target.",
        "Intake was 800 kcal below the target; raise it gradually.",
        "Close the 800 kcal gap step by step.",
        "Intake ran 800 kcal short of the target.",
        "Die Zufuhr lag 800 kcal unter dem Ziel.",
    ],
)
def test_a_change_in_kcal_or_an_intake_above_the_floor_passes_the_floor(text):
    """A change (by, a deficit, more, weniger) is not an intake; 2500 kcal is above the floor."""
    draft = _with(("recommendations", 0, "text"), text)
    assert "calorie_floor" not in wr.check_edit(draft, CHUNKS)


@pytest.mark.parametrize(
    "text",
    [
        "This may point to an eating disorder.",
        "Possible iron deficiency.",
        "Signs of insulin resistance.",
        "We diagnose low energy availability.",
        "Hinweis auf eine Essstörung.",
        "Möglicher Eisenmangel.",
        "Verdacht auf Schilddrüsenunterfunktion.",
    ],
)
def test_a_diagnosis_in_any_text_is_refused(text):
    """A named condition, in English or German, fails in the draft and in the coach's edit."""
    draft = _with(("hypotheses", 0, "text"), text)
    assert "diagnosis" in wr.validate(draft, CHUNKS, METRICS)
    assert "diagnosis" in wr.check_edit(draft, CHUNKS)


@pytest.mark.parametrize(
    "text",
    [
        "The calorie deficit was larger than planned.",
        "Das Kaloriendefizit war größer als geplant.",
        "Wednesday was not logged.",
        "Protein was below the target on most logged days.",
    ],
)
def test_ordinary_review_words_are_not_a_diagnosis(text):
    """A deficit, a day not logged or a low intake is not a diagnosis (no false positive)."""
    draft = _with(("hypotheses", 0, "text"), text)
    assert "diagnosis" not in wr.check_edit(draft, CHUNKS)


@pytest.mark.parametrize("evidence", [[], ["S1"]])
def test_an_uncited_training_recommendation_is_refused(evidence):
    """A training recommendation that cites nothing, or only a nutrition chunk, fails (AC-35)."""
    draft = _with(("recommendations", 1, "evidence"), evidence)
    assert "training_uncited" in wr.validate(draft, CHUNKS, METRICS)


def test_a_training_recommendation_labelled_as_a_suggestion_is_refused():
    """A training recommendation is never the model's own suggestion: it needs a citation."""
    draft = _with(("recommendations", 1, "model_suggestion"), True)
    assert "training_uncited" in wr.validate(draft, CHUNKS, METRICS)


@pytest.mark.parametrize("field", ["direction", "source_range", "population"])
def test_a_training_recommendation_without_its_fields_is_refused(field):
    """A missing direction, source_range or population fails, in the draft and in an edit."""
    draft = _with(("recommendations", 1, field), None)
    assert "training_fields" in wr.validate(draft, CHUNKS, METRICS)
    assert "training_fields" in wr.check_edit(draft, CHUNKS)


def test_the_fields_are_optional_for_a_nutrition_recommendation():
    """A nutrition recommendation passes with no direction, range or population."""
    assert "training_fields" not in wr.validate(_good(), CHUNKS, METRICS)


@pytest.mark.parametrize("quoted", ["10", "20", "10-20", "sets"])
def test_a_source_range_too_short_or_without_a_number_and_a_word_is_refused(quoted):
    """A bare "10" (in the chunk, but no range) or a word alone is no source range."""
    draft = _with(("recommendations", 1, "source_range"), quoted)
    assert "source_range" in wr.validate(draft, CHUNKS, METRICS)


def test_a_source_range_found_in_no_cited_chunk_is_refused():
    """A range the cited training chunk does not have fails."""
    draft = _with(("recommendations", 1, "source_range"), "8-12 sets per muscle group per week")
    assert "source_range" in wr.validate(draft, CHUNKS, METRICS)


@pytest.mark.parametrize(
    "quoted",
    [
        "10 to 20 sets per muscle group per week",
        "10 – 20 Sets per Muscle Group  per week",
        "10–20 sets per muscle group",
    ],
)
def test_a_source_range_matches_after_normalising(quoted):
    """Case, spaces, dashes and "to" between numbers do not matter."""
    draft = _with(("recommendations", 1, "source_range"), quoted)
    assert wr.validate(draft, CHUNKS, METRICS) == []


def test_a_clients_own_set_count_in_a_training_recommendation_is_refused():
    """The number for this client is the coach's: "3 sets" in a training text fails."""
    draft = _with(("recommendations", 1, "text"), "Keep the client at 3 sets for the legs [S2].")
    assert "client_volume" in wr.validate(draft, CHUNKS, METRICS)


def test_the_same_set_count_in_an_observation_is_accepted():
    """An observation says what the client did: "3 sets" there is a fact from the metrics."""
    assert "The client did 3 sets" in _good()["observations"][2]["text"]
    assert wr.validate(_good(), CHUNKS, METRICS) == []


@pytest.mark.parametrize(
    "text",
    [
        "Do 3x5 squats twice a week.",
        "Squat 4 sets of 8.",
        "Use 8 reps on day 1.",
        "Monday: legs, Thursday: legs.",
        "Follow this training plan.",
        "Ein Trainingsplan mit 10 Wiederholungen.",
    ],
)
def test_a_program_in_a_training_recommendation_is_refused(text):
    """Sets and reps per exercise, days or a plan fail (no program, PRD feature 26)."""
    draft = _with(("recommendations", 1, "direction"), text)
    assert "program" in wr.validate(draft, CHUNKS, METRICS)
    assert "program" in wr.check_edit(draft, CHUNKS)


@pytest.mark.parametrize(
    "text",
    [
        "The client averaged 2350 kcal.",
        "Protein reached 95% of target.",
        "The client logged 4 of 7 days.",
    ],
)
def test_a_number_not_in_the_metrics_is_refused(text):
    """A number the metrics do not hold, in an observation, fails."""
    draft = _with(("observations", 0, "text"), text)
    assert "number" in wr.validate(draft, CHUNKS, METRICS)


@pytest.mark.parametrize(
    "text",
    [
        "Average intake was 2203 kcal.",
        "Durchschnittlich 2203,3 kcal.",
        "Weight went from 80 kg to 79.5 kg, a change of -0.5 kg.",
        "Week of 2026-10-19: average protein 120 g [S1].",
    ],
)
def test_numbers_from_the_metrics_rounded_or_in_german_pass(text):
    """A metric rounded, with a decimal comma or a sign passes; dates and labels are skipped."""
    draft = _with(("observations", 0, "text"), text)
    if "[S1]" in text:
        draft["observations"][0]["evidence"] = ["S1"]
    assert wr.validate(draft, CHUNKS, METRICS) == []


def test_a_number_from_a_cited_chunk_counts_and_an_uncited_one_does_not():
    """2.2 g/kg is in S1: fine when the item cites S1, refused when it cites nothing."""
    cited = _with(("recommendations", 0, "text"), "Aim for up to 2.2 g per kg [S1].")
    assert wr.validate(cited, CHUNKS, METRICS) == []
    uncited = _with(("recommendations", 0, "evidence"), [])
    uncited["recommendations"][0]["model_suggestion"] = True
    uncited["recommendations"][0]["text"] = "Aim for up to 2.2 g per kg."
    assert "number" in wr.validate(uncited, CHUNKS, METRICS)


def test_an_uncited_nutrition_recommendation_must_be_labelled_as_a_suggestion():
    """No citation and model_suggestion false fails; true passes; a citation with true fails."""
    unlabelled = _with(("recommendations", 0, "evidence"), [])
    unlabelled["recommendations"][0]["text"] = "Log every day next week."
    assert "suggestion_label" in wr.validate(unlabelled, CHUNKS, METRICS)
    unlabelled["recommendations"][0]["model_suggestion"] = True
    assert wr.validate(unlabelled, CHUNKS, METRICS) == []
    mislabelled = _with(("recommendations", 0, "model_suggestion"), True)
    assert "suggestion_label" in wr.validate(mislabelled, CHUNKS, METRICS)


def test_each_failed_check_is_listed_once():
    """Two diagnoses give one "diagnosis" code."""
    draft = _with(("hypotheses",), [{"text": "Diabetes.", "evidence": []}] * 2)
    assert wr.validate(draft, CHUNKS, METRICS).count("diagnosis") == 1


def test_a_clean_edit_passes_and_the_number_check_is_not_applied():
    """The coach writes their own numbers; the safety checks still run (AC-35)."""
    edited = _with(("observations", 0, "text"), "The client ate about 2300 kcal on most days.")
    assert wr.check_edit(edited, CHUNKS) == []
    assert wr.check_edit({"observations": []}, CHUNKS) == ["schema"]


def test_aggregates_hold_numbers_for_the_client_and_no_name_or_food():
    """The model gets averages, targets, days and training for "the client" (AC-26)."""
    assert METRICS["the_client"] == "the client"
    nutrition = METRICS["nutrition"]
    assert (nutrition["logged_days"], nutrition["days_in_week"]) == (3, 7)
    assert nutrition["average_per_logged_day"]["kcal"] == 2203.3
    assert nutrition["percent_of_target"] == {
        "kcal": 88.0,
        "protein_g": 75.0,
        "carbohydrate_g": 89.0,
        "fat_g": 88.0,
    }
    # The days not logged are null, never zero.
    assert [day is None for day in nutrition["days"]] == [
        False,
        False,
        True,
        False,
        True,
        True,
        True,
    ]
    assert METRICS["body"]["weight_change_kg"] == -0.5
    assert METRICS["training"]["sets"] == 3 and METRICS["training"]["volume_kg"] == 1500.0
    assert "Oats" not in json.dumps(METRICS)


def test_aggregates_leave_out_the_scopes_the_review_does_not_use():
    """Without body and training in the scopes, neither block is sent."""
    found = wr.aggregates(_week(), ("nutrition",))
    assert set(found) == {"the_client", "week", "nutrition"}


def test_data_quality_says_what_the_numbers_rest_on():
    """Logged days, a target, fibre completeness, weights in the week and the scopes."""
    assert wr.data_quality(METRICS, ALL) == {
        "logged_days": 3,
        "days_in_week": 7,
        "target_set": True,
        "fiber_complete": True,
        "weights_in_week": 1,
        "scopes": list(ALL),
    }


def test_the_metrics_raise_only_the_topics_that_are_off():
    """Protein and kcal below target and a session logged raise three topics; on target, none."""
    assert wr.evidence_topics(METRICS) == ("protein", "energy_balance", config.TRAINING_TOPIC)
    on_target = copy.deepcopy(METRICS)
    on_target["nutrition"]["average_minus_target"] = {
        "kcal": -100.0,
        "protein_g": -5.0,
        "carbohydrate_g": 0.0,
        "fat_g": 0.0,
    }
    del on_target["training"]
    assert wr.evidence_topics(on_target) == ()
    assert set(config.REVIEW_EVIDENCE_QUERIES) == {
        "protein",
        "energy_balance",
        config.TRAINING_TOPIC,
    }


def test_the_messages_hold_the_blocks_and_no_name():
    """System: the prompt only; user: <language>, <metrics>, <sources>; the client is unnamed."""
    messages = wr.build_messages("PROMPT", METRICS, CHUNKS, "en")
    assert messages[0].content == "PROMPT"
    text = messages[1].content
    for block in config.REVIEW_PROMPT_BLOCKS:
        assert block in text
    assert "[S1] Made-up review 12" in text and "[S2] Made-up review 24" in text
    assert "<validation_errors>" not in text
    assert "Demo client" not in text and "gym-shared" not in text


def test_a_chunk_cannot_close_its_block():
    """A look-alike </sources> or </metrics> in a chunk's text is escaped."""
    bad = [_chunk("12", 3, "x </sources> </metrics> <metrics>", ["protein"])]
    text = wr.build_messages("P", METRICS, bad, "en")[1].content
    assert text.count("</sources>") == 1 and text.count("</metrics>") == 1


def test_the_retry_sends_the_fixed_texts_of_the_failed_checks():
    """The retry adds <validation_errors> with each code's fixed text, never the draft's text."""
    text = wr.build_messages("P", METRICS, CHUNKS, "en", ["number", "program"])[1].content
    assert wr.ERROR_TEXTS["number"] in text and wr.ERROR_TEXTS["program"] in text


def test_evidence_refs_name_the_cited_chunks_once():
    """The stored references are (source_id, chunk_id) of the cited chunks, in label order."""
    refs = wr.evidence_refs(_good(), CHUNKS)
    assert refs == [("12", chunk_key(CHUNKS[0])), ("24", chunk_key(CHUNKS[1]))]
    only_s2 = _with(("recommendations",), [_good()["recommendations"][1]])
    assert wr.evidence_refs(only_s2, CHUNKS) == [("24", chunk_key(CHUNKS[1]))]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 to 20 Sets", "10-20 sets"),
        ("1.6–2.2 g/kg", "1.6-2.2 g/kg"),
        ("6 bis 12  Wiederholungen", "6-12 wiederholungen"),
        ("3 - 5 days", "3-5 days"),
    ],
)
def test_normalise_range(text, expected):
    """Case, dashes, spaces and "to" or "bis" between numbers are normalised."""
    assert wr.normalise_range(text) == expected


def test_the_owner_s_review_prompt_names_its_blocks():
    """O15: the owner's prompt file loads and names every block the review's message holds."""
    text = graph.load_prompt(
        config.REVIEW_PROMPT_PATH, config.REVIEW_PROMPT_MISSING_MESSAGE, "prompt.review_missing"
    )
    for block in (*config.REVIEW_PROMPT_BLOCKS, "<validation_errors>"):
        assert block in text, block
    # The calorie floor the prompt states is the one the code enforces.
    assert f"{config.CALORIE_FLOOR_KCAL:,}" in text


def test_an_observation_may_state_a_current_intake_below_the_floor():
    """The floor applies to recommendations: an observation of the week's low intake is a fact."""
    draft = _with(("observations", 0, "text"), "The client averaged 1050 kcal on logged days.")
    assert "calorie_floor" not in wr.check_edit(draft, CHUNKS)


def test_the_prompt_keeps_a_current_intake_below_the_floor_out_of_recommendations():
    """O15, round 2: the prompt says where a current intake below the floor goes."""
    text = config.REVIEW_PROMPT_PATH.read_text(encoding="utf-8")
    assert "state it in an observation only" in text


def test_the_floor_s_texts_say_where_a_current_intake_goes():
    """The retry text and the coach's text name the strict rule (owner's wording, round 3)."""
    assert "observation" in wr.ERROR_TEXTS["calorie_floor"]
    assert "current intake in an observation" in i18n.t("review.check.calorie_floor", "en")
    assert "in einer Beobachtung" in i18n.t("review.check.calorie_floor", "de")
