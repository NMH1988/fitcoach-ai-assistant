"""Checks on the owner's evaluation question files (O2): read by T3.6, T6.1 and T7.2."""

import json

import pytest

from scripts.compare_retrieval import load_questions
from src import config
from src.rag.sources import load_manifest

FILES = [config.EVAL_QUESTIONS_PATH, config.EVAL_QUESTIONS_DE_PATH]


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
