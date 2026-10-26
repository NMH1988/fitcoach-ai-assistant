"""The owner's evaluation questions (O2): the file format and its loader.

Read by scripts/compare_retrieval.py (T3.3, T3.6) and scripts/run_evaluation.py (T6.1); the files
are config.EVAL_QUESTIONS_PATH and config.EVAL_QUESTIONS_DE_PATH (T7.2).
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.profile import UserProfile


class EvalQuestion(BaseModel):
    """One of the owner's evaluation questions and the sources it should find."""

    # Other fields (e.g. the good answer, for T6.1) are allowed and ignored.
    model_config = ConfigDict(extra="ignore")

    id: str
    question: str
    expected_sources: list[str]


class EvalItem(EvalQuestion):
    """An evaluation question with its good answer and, for a profile question, a fixed profile."""

    good_answer: str = Field(min_length=1)
    # A made-up session profile (test data, not a user's), e.g. for q13's daily targets.
    profile: UserProfile | None = None


class QuestionsFileError(ValueError):
    """The questions file is missing or not in the expected format; `str()` says which."""


def load_questions[Q: EvalQuestion](path: Path, model: type[Q] = EvalQuestion) -> list[Q]:
    """Read and check the questions file, each question as `model`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise QuestionsFileError(f"No questions file at {path}.") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuestionsFileError(f"Could not read {path}: {exc}") from None
    if not isinstance(data, list) or not data:
        raise QuestionsFileError(f"{path} must hold a non-empty JSON list of questions.")
    try:
        questions = [model.model_validate(item) for item in data]
    except ValidationError as exc:
        raise QuestionsFileError(f"{path} has a question in the wrong format: {exc}") from None
    # The results file of an evaluation run counts runs per ID (T8.4), so an ID must be unique.
    ids = [question.id for question in questions]
    repeated = sorted({question_id for question_id in ids if ids.count(question_id) > 1})
    if repeated:
        raise QuestionsFileError(f"{path} uses an ID for more than one question: {repeated}")
    return questions


def load_eval_items(path: Path) -> list[EvalItem]:
    """Read and check the questions file for the evaluation run, with good answers and profiles."""
    return load_questions(path, EvalItem)
