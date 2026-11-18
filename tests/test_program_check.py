"""The chat answer's program check (T10.5): what it must and must not catch, and what it replaces.

The written answers below are ours, written in the app's style (Markdown, [S#] citations), in
English and German; they fix what the check does (the ticket's criterion 4). The evaluation files'
`good_answer` fields are grading notes, not answers, so they cannot test this. Any other wording
the two patterns get wrong is a known limit in `docs/TESTING.md`, not a new pattern (owner's
choice, 2026-11-06).
"""

from types import SimpleNamespace

import pytest

from src import config, guardrails, i18n
from src.agent import graph
from src.agent.graph import TurnContext
from src.agent.search import SearchLog
from src.chat import TurnResult
from src.tools import registry
from tests.fakes import PROFILE

# Allowed: what a source gives, cited, and the app's own sentences (PRD feature 26).
PASSES_EN = {
    "cited range": (
        "The reviews found that about 10 or more sets per muscle group per week [S1] gave more "
        "growth than fewer sets, in trained adults."
    ),
    "cited rep range": "Loads that allow 6-12 reps [S2] were used in most of the studies.",
    "cited protocol (sets of)": (
        "In that study, untrained young men did 3 sets of 8-12 reps [S1] three times a week."
    ),
    "cited protocol (x)": "The participants trained with 3 x 10 [S2] at about 70% of their 1RM.",
    "redirect to a coach": (
        "For an individual training program or exercise technique, please work with a qualified "
        "coach."
    ),
    "fixed sentence": config.NO_PROGRAM_SENTENCE["en"],
    "training plan in a refusal": (
        "I can't write you a training plan or a workout plan, but the sources describe how volume "
        "was studied [S1]."
    ),
    "frequency": "Training each muscle **2 days per week** [S1] was compared with once a week.",
}
PASSES_DE = {
    "cited range": (
        "Die Übersichtsarbeiten fanden, dass etwa 10 oder mehr Sätze pro Muskelgruppe pro Woche "
        "[S1] bei trainierten Erwachsenen mehr Wachstum brachten."
    ),
    "cited rep range": "In den meisten Studien wurden Lasten für 6-12 Wiederholungen [S2] genutzt.",
    "cited protocol (sets of)": (
        "In dieser Studie machten untrainierte junge Männer 3 Sätze mit 8-12 Wiederholungen [S1]."
    ),
    "cited protocol (x)": "Die Teilnehmenden trainierten mit 3 x 10 [S2] bei etwa 70 % des 1RM.",
    "redirect to a coach": (
        "Für ein individuelles Trainingsprogramm oder die Übungstechnik wenden Sie sich bitte an "
        "einen qualifizierten Coach."
    ),
    "fixed sentence": config.NO_PROGRAM_SENTENCE["de"],
    "Trainingsplan in a refusal": (
        "Einen persönlichen Trainingsplan kann ich nicht schreiben. Die Quellen beschreiben aber "
        "Grundsätze zum Volumen [S1]."
    ),
}
# Caught: a written schedule, plain and in the Markdown the model writes.
FAILS_EN = {
    "weekday schedule": "Monday: squats and leg press.\nThursday: bench press and rows.",
    "weekday schedule in bold": (
        "Here is a split:\n\n- **Monday**: squats, 3 x 10\n- **Wednesday**: bench press, 3 x 10"
    ),
    "day schedule": "Day 1: upper body (bench press, rows)\nDay 2: lower body (squats, lunges)",
    "day schedule in bold": "**Day 1:** push\n\n**Day 2:** pull\n\n**Day 3:** legs",
}
FAILS_DE = {
    "weekday schedule": "Montag: Kniebeugen und Beinpresse.\nDonnerstag: Bankdrücken und Rudern.",
    "weekday schedule in bold": "- **Montag**: Kniebeugen\n- **Mittwoch**: Bankdrücken",
    "day schedule": "Tag 1: Oberkörper (Bankdrücken, Rudern)\nTag 2: Unterkörper (Kniebeugen)",
    "day schedule in bold": "**Tag 1:** Drücken\n\n**Tag 2:** Ziehen",
}


@pytest.mark.parametrize(
    "answer",
    [*PASSES_EN.values(), *PASSES_DE.values()],
    ids=[*(f"en-{k}" for k in PASSES_EN), *(f"de-{k}" for k in PASSES_DE)],
)
def test_what_a_source_gives_and_the_apps_own_sentences_pass(answer):
    """Cited ranges and protocols, the redirect and the fixed sentences are not a program."""
    assert not guardrails.reads_as_program_schedule(answer)


@pytest.mark.parametrize(
    "answer",
    [*FAILS_EN.values(), *FAILS_DE.values()],
    ids=[*(f"en-{k}" for k in FAILS_EN), *(f"de-{k}" for k in FAILS_DE)],
)
def test_a_written_schedule_is_caught(answer):
    """A weekday or day-by-day schedule is caught, with or without Markdown emphasis."""
    assert guardrails.reads_as_program_schedule(answer)


def test_the_check_uses_the_reviews_patterns_not_a_copy():
    """The two schedule patterns are the review's own, and the review still checks them."""
    assert set(config.PROGRAM_SCHEDULE_PATTERNS) < set(config.REVIEW_PROGRAM_PATTERNS)
    assert guardrails.matches_any(config.REVIEW_PROGRAM_PATTERNS, ["Day 1: squats"])


def test_a_list_of_exercises_with_sets_and_reps_is_a_known_limit():
    """Not caught in code: the patterns that would catch it also catch a cited protocol."""
    answer = "- Squat: 3 x 8\n- Bench press: 3 x 10\n- Row: 3 x 12"
    assert not guardrails.reads_as_program_schedule(answer)


# --- finish() ------------------------------------------------------------------------------------


def _finish(answer: str, check_program: bool) -> dict:
    """Run finish() on a state with this answer; return its update."""
    context = TurnContext(
        chat_model=lambda: None,
        tools=lambda: registry.build_tools(PROFILE),
        on_step=lambda step: None,
        search_log=SearchLog(),
        turn_id="turn-1",
    )
    state = {"answer": answer, "check_program": check_program, "runs": []}
    return graph.finish(state, SimpleNamespace(context=context))


def test_finish_replaces_a_program_with_the_fixed_sentence():
    """A checked answer with a schedule becomes the fixed sentence, kind guardrail, no sources."""
    result: TurnResult = _finish(FAILS_EN["day schedule"], check_program=True)["result"]
    assert (result.kind, result.code) == ("guardrail", graph.PROGRAM_CODE)
    assert result.text == config.NO_PROGRAM_SENTENCE["en"]
    assert result.sources == ()
    # Shown in the chosen language by its code (T7.1).
    assert i18n.t(result.code, "de") == config.NO_PROGRAM_SENTENCE["de"]
    assert i18n.t(result.code, "en") == config.NO_PROGRAM_SENTENCE["en"]


def test_finish_keeps_a_checked_answer_with_no_schedule():
    """A cited protocol in a checked answer stays the answer."""
    result = _finish(PASSES_EN["cited protocol (sets of)"], check_program=True)["result"]
    assert (result.kind, result.text) == ("answer", PASSES_EN["cited protocol (sets of)"])


def test_finish_never_checks_a_nutrition_answer():
    """A nutrition-only turn is not checked: a meal plan by weekday stays the answer."""
    answer = "Monday: oats with milk. Tuesday: rice with chicken [S1]."
    result = _finish(answer, check_program=False)["result"]
    assert (result.kind, result.text) == ("answer", answer)


def test_finish_leaves_the_answer_loop_alone_unchecked():
    """A state without check_program (the answer loop alone) is never checked."""
    context = TurnContext(chat_model=lambda: None, tools=dict, on_step=lambda step: None)
    state = {"answer": FAILS_EN["day schedule"], "runs": []}
    result = graph.finish(state, SimpleNamespace(context=context))["result"]
    assert result.kind == "answer"
