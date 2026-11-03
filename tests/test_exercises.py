"""The workout log's exercise list (T9.14): `data/exercises.json` loads and keeps its rules."""

import json

import pytest

from src import config, exercises
from src.i18n import LANGUAGES


def test_the_list_loads_with_a_short_list_of_unique_exercises():
    """The committed list loads, holds a short list and every ID once."""
    found = exercises.exercises()
    ids = exercises.exercise_ids()
    assert 10 <= len(found) <= 40
    assert len(set(ids)) == len(ids)
    assert "squat" in ids  # the ID the store's tests and the demo use


def test_every_exercise_has_a_name_per_language_and_a_known_group():
    """Each exercise is named in English and German and belongs to one of config's groups."""
    for exercise in exercises.exercises():
        assert set(exercise.name) == set(LANGUAGES)
        assert exercise.muscle_group in config.MUSCLE_GROUPS


def test_every_muscle_group_has_an_exercise():
    """No group in config is left without an exercise to log."""
    groups = {exercise.muscle_group for exercise in exercises.exercises()}
    assert groups == set(config.MUSCLE_GROUPS)


def test_the_file_says_we_wrote_it():
    """The file's note says the list is the project's own writing, from no third-party list."""
    document = json.loads(config.EXERCISES_PATH.read_text(encoding="utf-8"))
    assert "no third-party list" in document["note"]


def test_exercises_are_found_by_id():
    """by_id() gives each exercise of the list, with its names, under its ID."""
    squat = exercises.by_id()["squat"]
    assert (squat.name["en"], squat.name["de"], squat.muscle_group) == (
        "Squat",
        "Kniebeuge",
        "legs",
    )
    assert set(exercises.by_id()) == set(exercises.exercise_ids())


def _write(tmp_path, items) -> object:
    """Write an exercise list with the given items to a temporary file; return its path."""
    path = tmp_path / "exercises.json"
    path.write_text(json.dumps({"note": "test", "exercises": items}), encoding="utf-8")
    return path


GOOD = {"id": "squat", "name": {"en": "Squat", "de": "Kniebeuge"}, "muscle_group": "legs"}


@pytest.mark.parametrize(
    "items",
    [
        [],
        [GOOD, GOOD],
        [{**GOOD, "id": "Back Squat"}],
        [{**GOOD, "muscle_group": "glutes"}],
        [{**GOOD, "name": {"en": "Squat"}}],
        [{**GOOD, "name": {"en": "Squat", "de": " "}}],
        [{**GOOD, "name": {"en": "S" * (config.EXERCISE_NAME_MAX_CHARS + 1), "de": "K"}}],
        [{**GOOD, "name": {"en": "Squat\nline", "de": "K"}}],
        [{**GOOD, "extra": "field"}],
    ],
)
def test_a_list_that_breaks_a_rule_is_refused(tmp_path, items):
    """No exercise, a repeated ID, a bad ID, group or name, or an unknown field is refused."""
    with pytest.raises(exercises.ExerciseListError):
        exercises.read_exercises(_write(tmp_path, items))


def test_a_missing_or_broken_file_is_refused(tmp_path):
    """A file that is not there or not JSON gives ExerciseListError."""
    with pytest.raises(exercises.ExerciseListError):
        exercises.read_exercises(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(exercises.ExerciseListError):
        exercises.read_exercises(broken)
