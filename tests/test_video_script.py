"""What the presentation video's approved script must and must not say (T9.28, criteria 5 and 6)."""

import re

from scripts import make_video

SCENES = make_video.load_script()
NARRATION = [text for scene in SCENES for text in scene.narration]
SPOKEN = " ".join(NARRATION)
CARDS = {scene.id: scene.card for scene in SCENES if scene.card}
DESCRIPTION = make_video.ROOT / "docs" / "video" / "description.md"
ATTRIBUTION_URL = "https://github.com/NMH1988/fitcoach-ai-assistant/blob/main/ATTRIBUTION.md"
# Medical claims and implied endorsement (copyright rule 6; the ticket's criterion 5).
FORBIDDEN = re.compile(
    r"\b(diagnos\w*|treat\w*|prevent\w*|monitor\w*|cure\w*|endors\w*|affiliat\w*|partner\w*|"
    r"recommended by|approved by (?!the coach))",
    re.IGNORECASE,
)


def _scene(scene_id: str) -> str:
    """Return one scene's narration as one text."""
    return " ".join(next(scene for scene in SCENES if scene.id == scene_id).narration)


def test_the_video_says_its_voice_is_synthetic():
    """The opening says the narration is a synthetic voice, and the first card shows it too."""
    assert "synthetic voice" in _scene("opening")
    # The owner's own project: the video names no course (owner's choice, 2026-11-09).
    shown = " ".join(line for card in CARDS.values() for line in card)
    assert "Turing" not in SPOKEN + shown + DESCRIPTION.read_text(encoding="utf-8")
    assert any("Synthetic voice" in line for line in CARDS["opening"])


def test_the_video_says_the_answers_and_drafts_are_made_by_an_ai_model():
    """The chat's answer and the weekly review's draft are each said to be made by an AI model."""
    assert "written by an AI model" in _scene("chat")
    assert "made by an AI model" in _scene("review")


def test_the_video_says_the_coach_approves_a_draft_before_the_client_sees_it():
    """AC-41: the draft goes nowhere until the coach decides, and the client sees only approved."""
    review = _scene("review")
    assert "until the coach approves, edits or rejects it" in review
    assert "only after the coach has approved it" in review
    assert "approved by the coach" in _scene("client-side")


def test_the_video_says_not_medical_advice_exactly_once():
    """The narration says once that the app is not medical advice."""
    assert len(re.findall(r"not medical advice", SPOKEN, re.IGNORECASE)) == 1


def test_no_line_claims_a_medical_use_or_an_endorsement():
    """No narration or card line names a medical use or implies an endorsement or affiliation."""
    credits = CARDS["credits"]
    # The credits' last line is the one that says no one named is affiliated or endorses it.
    lines = [*NARRATION, *(line for card in CARDS.values() for line in card if card is not credits)]
    lines += list(credits[:-1])
    assert [line for line in lines if FORBIDDEN.search(line)] == []
    assert "No author, journal, organisation or service" in credits[-1]
    assert "is affiliated with or endorses it" in credits[-1]


def test_the_credits_name_the_voice_its_licence_and_the_sources():
    """The last scene is the credits: the voice and its licence, and ATTRIBUTION.md's full URL."""
    assert SCENES[-1].id == "credits" and not SCENES[-1].narration
    text = " ".join(CARDS["credits"])
    for words in ("Piper", "GPL-3.0-or-later", "en_US-ljspeech", "LJ Speech", "public domain"):
        assert words in text
    assert ATTRIBUTION_URL in text
    # The client scene shows foods from USDA's table (compliance run 1, Low 2).
    assert "USDA FoodData Central" in text
    assert "DejaVu Sans" in text


def test_the_draft_description_carries_the_same_credits_and_statements():
    """The upload's description repeats each credits line and the AI, approval and advice notes."""
    description = DESCRIPTION.read_text(encoding="utf-8")
    for line in CARDS["credits"][1:]:
        assert line in description
    assert "made by an AI model" in description
    assert "the coach approves, edits or rejects before the client sees it" in description
    assert "not medical advice" in description


def test_the_narration_lasts_two_to_four_minutes():
    """At about the voice's pace, the words and pauses fit the ticket's 2 to 4 minutes."""
    words = len(SPOKEN.split())
    pauses = (len(NARRATION) - len(SCENES)) * make_video.SENTENCE_PAUSE
    pauses += len(SCENES) * make_video.SCENE_PAUSE + sum(scene.seconds for scene in SCENES)
    seconds = words / make_video.WORDS_PER_MINUTE * 60 + pauses
    assert make_video.MIN_SECONDS <= seconds <= make_video.MAX_SECONDS
