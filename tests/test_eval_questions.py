"""Checks on the owner's evaluation question files (O2): read by T3.6, T6.1 and T7.2."""
# The German file is loaded with the evaluation run's loader too, so it stays runnable for T7.2.

import json

import pytest

from src import config
from src.eval_questions import QuestionsFileError, load_eval_items, load_questions
from src.rag.sources import load_manifest
from src.tools import registry

FILES = [
    config.EVAL_QUESTIONS_PATH,
    config.EVAL_QUESTIONS_DE_PATH,
    # The training questions (O17, T9.19), in their own files.
    config.EVAL_QUESTIONS_TRAINING_PATH,
    config.EVAL_QUESTIONS_TRAINING_DE_PATH,
]
TRAINING_FILES = [config.EVAL_QUESTIONS_TRAINING_PATH, config.EVAL_QUESTIONS_TRAINING_DE_PATH]


@pytest.fixture(params=FILES, ids=lambda path: path.name)
def questions(request):
    """Load one evaluation question file with the comparison script's loader."""
    return load_questions(request.param)


def test_each_file_loads_with_the_comparison_scripts_loader(questions):
    """The file is a non-empty list in the format `load_questions()` accepts."""
    assert questions


def test_question_ids_are_unique_within_a_file(questions):
    """No two questions share an ID, so results can be recorded per question."""
    ids = [question.id for question in questions]
    assert len(ids) == len(set(ids))


def test_a_file_with_a_repeated_id_is_refused(tmp_path):
    """Two questions with one ID would be counted as one in the results file, so it is refused."""
    item = {"id": "q1", "question": "How much protein per meal?", "expected_sources": ["1"]}
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([item, {**item, "question": "Another one?"}]), encoding="utf-8")
    with pytest.raises(QuestionsFileError, match="q1"):
        load_questions(path)


def test_every_expected_source_is_in_the_manifest(questions):
    """Every expected source ID names an approved article in `data/sources.json`."""
    known = {source.id for source in load_manifest()}
    unknown = {
        f"{question.id}: {source_id}"
        for question in questions
        for source_id in question.expected_sources
        if source_id not in known
    }
    assert not unknown


@pytest.mark.parametrize("path", TRAINING_FILES, ids=lambda path: path.name)
def test_training_questions_expect_only_training_sources(path):
    """A training question expects only sources with the training topic (T9.19, AC-40)."""
    training = {s.id for s in load_manifest() if "resistance_training" in s.topics}
    for question in load_questions(path):
        assert set(question.expected_sources) <= training, question.id


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.name)
def test_each_file_loads_with_the_evaluation_runs_loader(path):
    """The file has the good answers and valid profiles `scripts/run_evaluation.py` needs."""
    assert len(load_eval_items(path)) == len(load_questions(path))


def test_q13s_fixed_profile_gives_the_targets_its_good_answer_expects():
    """q13's session profile is valid and the app's tools give the values its good answer names."""
    [q13] = [item for item in load_eval_items(config.EVAL_QUESTIONS_PATH) if item.id == "q13"]
    result = registry.macro_targets(q13.profile)
    targets = result.targets
    assert result.energy_needs.tdee_kcal == 2759
    assert targets.kcal_target == 3035
    assert (targets.protein.grams, targets.carbohydrate.grams, targets.fat.grams) == (152, 418, 84)
    for value in ("2759 kcal", "3035 kcal", "protein 152 g", "carbohydrate 418 g", "fat 84 g"):
        assert value in q13.good_answer


def test_only_q13_runs_with_a_session_profile():
    """Every other question runs with no profile, as a new visitor asks it."""
    items = load_eval_items(config.EVAL_QUESTIONS_PATH)
    assert [item.id for item in items if item.profile is not None] == ["q13"]


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.name)
def test_every_question_has_a_good_answer_for_the_evaluation_run(path):
    """Each question carries a non-empty `good_answer`, which T6.1 and T7.2 judge answers by."""
    items = json.loads(path.read_text(encoding="utf-8"))
    missing = [
        item["id"]
        for item in items
        if not isinstance(item.get("good_answer"), str) or not item["good_answer"].strip()
    ]
    assert not missing
