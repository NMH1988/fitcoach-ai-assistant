"""The answer prompt: its file, its version and the parts joined into the system prompt."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src import config


def prompt_version(text: str) -> str:
    """Return a prompt's version: the start of the SHA-256 hex digest of its exact text (T10.4)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[: config.PROMPT_VERSION_LENGTH]


@dataclass(frozen=True)
class Prompt:
    """A prompt's text as the model receives it; its version is worked out from that text."""

    text: str

    @property
    def version(self) -> str:
        """Return the version of this exact text, so the two can never disagree (T10.4)."""
        return prompt_version(self.text)


def load_system_prompt(path: Path | None = None) -> str:
    """Return the owner's answer system prompt from its file."""
    text = (path or config.ANSWER_PROMPT_PATH).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("The answer system prompt is empty.")
    return text


def answer_system_prompt(prompt: str, language_part: str, coach_part: str | None = None) -> str:
    """Return the owner's answer prompt, the chosen language's part, then a coach's part if any."""
    # All are the owner's fixed text (O1, O8); the app's language control picks the part (T7.2),
    # and only a coach's chat gets the part on remember_preference and <memories> (T9.7).
    parts = [prompt, language_part, *([coach_part] if coach_part is not None else [])]
    return "\n\n".join(parts)
