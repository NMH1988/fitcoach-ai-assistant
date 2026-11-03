"""The workout log's exercise list (T9.14): `data/exercises.json`, which we wrote ourselves.

Each exercise has an ID (what the store keeps with a set), its name in each UI language and one
muscle group from `config.MUSCLE_GROUPS`. The store accepts only these IDs, so a set always names
an exercise of the list; the names are shown, never sent to a model.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src import config
from src.i18n import LANGUAGES, Language

# A plain ID: lower-case words joined by "_" ("bench_press").
ID_PATTERN = r"[a-z]+(?:_[a-z]+)*"


class ExerciseListError(RuntimeError):
    """The exercise list is missing or does not have the expected fields and values."""


class Exercise(BaseModel):
    """One exercise of the list: its ID, its name per language and its muscle group."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=f"^{ID_PATTERN}$")
    name: dict[Language, str]
    muscle_group: str

    @field_validator("name")
    @classmethod
    def _every_language(cls, name: dict[Language, str]) -> dict[Language, str]:
        """Require a short name in every UI language, with no line breaks."""
        if set(name) != set(LANGUAGES):
            raise ValueError("needs a name in every UI language")
        for text in name.values():
            if not text.strip() or len(text) > config.EXERCISE_NAME_MAX_CHARS or "\n" in text:
                raise ValueError("needs a short name on one line")
        return name

    @field_validator("muscle_group")
    @classmethod
    def _known_group(cls, group: str) -> str:
        """Require one of the muscle groups in config."""
        if group not in config.MUSCLE_GROUPS:
            raise ValueError("is not a known muscle group")
        return group


def read_exercises(path: Path) -> tuple[Exercise, ...]:
    """Read and check an exercise list file; ExerciseListError if it cannot be used."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        found = tuple(Exercise.model_validate(item) for item in document["exercises"])
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
        raise ExerciseListError(f"{path.name} cannot be read as an exercise list") from exc
    ids = [exercise.id for exercise in found]
    if not found or len(set(ids)) != len(ids):
        raise ExerciseListError(f"{path.name} needs at least one exercise and unique IDs")
    return found


@lru_cache(maxsize=1)
def exercises() -> tuple[Exercise, ...]:
    """Return the app's exercise list, read once per process."""
    return read_exercises(config.EXERCISES_PATH)


def exercise_ids() -> tuple[str, ...]:
    """Return the IDs of the app's exercises, in the list's order."""
    return tuple(exercise.id for exercise in exercises())


def by_id() -> dict[str, Exercise]:
    """Return the app's exercises by their IDs."""
    return {exercise.id: exercise for exercise in exercises()}
