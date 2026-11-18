"""The injection check's measured miss rate and false alarms (T10.1).

`tests/fixtures/red_team_injections.json` holds attacks and harmless gym questions written for this
repo. The check is `memory.flags_answer()`: the guard's patterns on its detection views, the same
check the guard runs on a question; the chat's memory runs it on an answer without its citations
(`memory.drops_answer()`), which the app-style answers below go through. The counts are a
ratchet: the test fails when either count, or the size of either set, differs from the fixture's
`recorded` numbers, so a worse result fails, a better one must be written down (after which it
cannot slip back), and a changed set shows as an edit of its totals.
"""

import json
from pathlib import Path

import pytest

from src.agent import memory

FIXTURE = Path(__file__).parent / "fixtures" / "red_team_injections.json"
KINDS = {
    "role_change",
    "rule_override",
    "prompt_leak",
    "output_hijack",
    "exfiltration",
    "source_instruction",
}

# Answers in the app's own style, written for this test (criterion 4): cited answers, refusals,
# "not covered" replies and a coach's answers about a client, in English and German. None may be
# flagged, or the chat would forget ordinary answers. The evaluation files' `good_answer` fields are
# grading notes, not answers, so they are not used here.
APP_STYLE_ANSWERS = [
    "Spread your protein over three or four meals of about 0.4 g per kg each [S1]; a larger "
    "single meal is not harmful, but the extra is used less for muscle building [S2].",
    "80 g of rolled oats have about 300 kcal and 10 g of protein (USDA FoodData Central).",
    "Your estimated energy need is 2,650 kcal a day at a moderate activity level; this is an "
    "estimate, so watch your weight over two or three weeks and adjust.",
    "Creatine monohydrate at 3 to 5 g a day is the form most studied [S1]. Loading is not "
    "needed; the stores fill within about a month at that dose [S3].",
    "The sources found do not cover the offside rule in football, so I cannot answer that here.",
    "I can't give you a training program, sets or reps. The research says that weekly volume "
    "matters more than how it is split [S2]; your coach can turn that into a plan.",
    "I can't help with medication or doses. Please ask your doctor or pharmacist.",
    "Follow your coach's instructions on load; the sources say progressive overload drives "
    "strength gains over time [S1].",
    "Your nervous system adapts early in a program, which is why strength rises before muscle "
    "size does [S2].",
    "Ignore the scale for a few days after a high-carb day: water weight can swing by 1 to 2 kg.",
    "client-1 logged five of seven days last week, about 2,100 kcal a day on average, below "
    "their 2,400 kcal target; protein was on target on four days.",
    "client-2 shares only training data with you, so I can't see their meals.",
    "Verteilen Sie Ihr Eiweiß auf drei bis vier Mahlzeiten mit je etwa 0,4 g pro kg [S1].",
    "80 g Haferflocken haben etwa 300 kcal und 10 g Eiweiß (USDA FoodData Central).",
    "Die gefundenen Quellen behandeln diese Frage nicht, daher kann ich sie hier nicht "
    "beantworten.",
    "Ein Trainingsprogramm mit Sätzen und Wiederholungen kann ich nicht erstellen. Laut den "
    "Quellen zählt das wöchentliche Volumen mehr als seine Aufteilung [S2].",
    "Zu Medikamenten und Dosierungen kann ich nicht beraten. Bitte fragen Sie Ihre Ärztin oder "
    "Ihren Arzt.",
    "Halten Sie sich bei der Last an die Anweisungen Ihres Trainers; die Quellen zeigen, dass "
    "eine schrittweise Steigerung die Kraft erhöht [S1].",
    "client-1 hat letzte Woche an fünf von sieben Tagen protokolliert, im Schnitt etwa 2.100 kcal "
    "am Tag, unter dem Ziel von 2.400 kcal.",
    "Ab sofort gilt für client-2 das neue Ziel von 2.300 kcal, das Sie gesetzt haben.",
]


def _fixture() -> dict:
    """Return the red-team fixture."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_has_enough_attacks_and_harmless_questions_in_both_languages():
    """At least 40 attacks of every kind in English and German, and 20 harmless questions."""
    data = _fixture()
    attacks, harmless = data["attacks"], data["harmless"]
    assert len(attacks) >= 40 and len(harmless) >= 20
    assert {(item["kind"], item["lang"]) for item in attacks} == {
        (kind, lang) for kind in KINDS for lang in ("en", "de")
    }
    assert {item["wording"] for item in attacks} == {"known", "new"}
    assert {item["lang"] for item in harmless} == {"en", "de"}
    texts = [item["text"] for item in [*attacks, *harmless]]
    assert len(texts) == len(set(texts))


def _counts() -> tuple[list[dict], list[dict]]:
    """Return the attacks the check misses and the harmless questions it flags."""
    data = _fixture()
    missed = [item for item in data["attacks"] if not memory.flags_answer(item["text"])]
    flagged = [item for item in data["harmless"] if memory.flags_answer(item["text"])]
    return missed, flagged


def test_the_miss_and_false_alarm_counts_match_the_recorded_ratchet():
    """A worse count fails; a better one fails too, until the fixture records it."""
    data = _fixture()
    recorded = data["recorded"]
    # The sizes are pinned too, so deleting a missed attack cannot pass for a better pattern, and
    # an added attack changes the totals in the same edit as the counts.
    assert (len(data["attacks"]), len(data["harmless"])) == (
        recorded["attacks_total"],
        recorded["harmless_total"],
    ), "the set changed: update the totals and the counts in 'recorded' and docs/TESTING.md"
    missed, flagged = _counts()
    for name, count in (("attacks_missed", len(missed)), ("harmless_flagged", len(flagged))):
        assert count <= recorded[name], f"{name} rose from {recorded[name]} to {count}"
        assert count >= recorded[name], (
            f"{name} fell from {recorded[name]} to {count}: lower 'recorded' in the fixture and "
            "the rates in docs/TESTING.md"
        )


def test_the_known_wordings_are_mostly_caught():
    """The patterns catch the paraphrases they were written for; the misses are new wordings."""
    missed, _ = _counts()
    known = [item for item in _fixture()["attacks"] if item["wording"] == "known"]
    known_missed = [item for item in missed if item["wording"] == "known"]
    # A control: the fixture would show nothing if the check caught nothing at all.
    assert len(known_missed) < len(known) / 4


@pytest.mark.parametrize("answer", APP_STYLE_ANSWERS)
def test_an_answer_in_the_apps_style_is_not_flagged(answer):
    """The memory check raises no false alarm on the app's own kinds of answer."""
    assert not memory.drops_answer(answer)
