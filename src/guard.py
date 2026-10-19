"""Input guard: cleans and checks each user message before any model or embedding call.

Checks run in this order: empty, too long, prompt-injection patterns, then the per-session rate
limit. Only a message that passes every check counts against the rate limit (owner's choice in
T1.3), and a rejected message never reaches a model: callers go through `run_guarded()`.
"""

import math
import re
import time
import unicodedata
from collections import deque
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src import config

# Fixed messages: they never quote the user's text back.
EMPTY_MESSAGE = "Please type a question first."
TOO_LONG_MESSAGE = (
    f"Your message is too long. Please keep it under {config.MAX_INPUT_CHARS} characters."
)
INJECTION_MESSAGE = (
    "Your message looks like an attempt to change how the assistant works, so it was not sent. "
    "Please ask a nutrition question."
)
RATE_WINDOW_MESSAGE = "You are sending questions too fast. Please wait {seconds} s and try again."
RATE_SESSION_MESSAGE = "This session has reached its limit of {limit} questions."

# Key under which the session's rate limiter lives in st.session_state.
SESSION_LIMITER_KEY = "rate_limiter"

# Words that turn "ignore ..." into an attack. Strong nouns are almost always the assistant's own
# instructions, but "the" or "any" in front of them is not enough ("can I ignore the instructions
# on the tub?"). Weak nouns ("rules", "guidelines") are common in nutrition questions ("can I
# ignore the guidelines on sodium?"), so they need a qualifier that points at the assistant.
_OVERRIDE_VERBS = r"(?:ignore|disregard|forget|override|bypass)"
_STRONG_NOUNS = r"(?:instructions?|prompts?|directives?|programming|guardrails?|system message)"
_WEAK_NOUNS = r"(?:rules|guidelines|restrictions|constraints)"
_STRONG_QUALIFIERS = (
    r"(?:your|previous|prior|above|earlier|preceding|all|these|those|system|initial|original"
    r"|developer)"
)
_WEAK_QUALIFIERS = r"(?:your|previous|prior|above|earlier|preceding|system|initial|original)"
# Up to a few filler words between the parts, e.g. "ignore all of your previous instructions".
_GAP = r"(?: \S+){0,3}?"

# Matched against the casefolded text with whitespace collapsed to single spaces.
_FOLDED_PATTERNS = [
    # Overriding the instructions.
    rf"\b{_OVERRIDE_VERBS}\b{_GAP} {_STRONG_QUALIFIERS}\b{_GAP} {_STRONG_NOUNS}\b",
    rf"\b{_OVERRIDE_VERBS}\b{_GAP} {_WEAK_QUALIFIERS}\b{_GAP} {_WEAK_NOUNS}\b",
    rf"\b{_OVERRIDE_VERBS}\b{_GAP} (?:the )?{_STRONG_NOUNS} (?:above|before|you were given)\b",
    rf"\b{_OVERRIDE_VERBS}\b{_GAP} (?:everything|anything|all) (?:above|before|you were told)\b",
    r"\bnew instructions ?:",
    # Asking for the hidden prompt.
    r"\b(?:system|developer|hidden|initial|original|secret) (?:prompt|message|instructions)\b",
    r"\b(?:reveal|repeat|print|show|output|display|leak|dump|recite|tell me) (?:me )?"
    r"(?:all )?(?:of )?your (?:instructions|prompt|configuration)\b",
    r"\bwhat (?:are|were) your (?:instructions|initial instructions|original instructions)\b",
    # Changing the assistant's role or switching off its rules.
    r"\byou are now\b",
    r"\bfrom now on,? you (?:are|will|must|should|act|have)\b",
    r"\b(?:developer|god|dan|debug|jailbreak|unrestricted|unfiltered|admin) mode\b",
    r"\bjailbr(?:eak|oken)\b",
    r"\bdo anything now\b",
    r"\b(?:pretend|imagine) (?:that )?(?:you are|you're|to be) (?:an? )?"
    r"(?:unrestricted|unfiltered|uncensored|different|evil|another)\b",
    r"\bact as (?:an? )?(?:unrestricted|unfiltered|uncensored|jailbroken|evil|different)\b",
    r"\b(?:no longer|not) (?:bound|restricted) by (?:your|any) "
    r"(?:rules|instructions|guidelines|restrictions|policies)\b",
]

# Matched against the cleaned text with its line breaks: fake role markers and look-alikes of the
# delimiters the answer step wraps around user text and sources (docs/ARCHITECTURE.md, step 5).
_RAW_PATTERNS = [
    r"<\s*/?\s*(?:system|user_input|sources|assistant|user|developer|instructions?)\s*>",
    r"<\|[a-z_]+\|>",
    r"\[/?(?:inst|sys)\]",
    r"<<\s*/?\s*sys\s*>>",
    r"(?m)^\s*(?:#+\s*)?(?:system|assistant|developer)\s*:",
]

_FOLDED_RE = [re.compile(p) for p in _FOLDED_PATTERNS]
_RAW_RE = [re.compile(p, re.IGNORECASE) for p in _RAW_PATTERNS]

# Line breaks and tabs are the only control characters a question keeps.
_KEPT_CONTROLS = {"\n", "\t"}


class Rejection(StrEnum):
    """Why the guard rejected a message."""

    EMPTY = "empty"
    TOO_LONG = "too_long"
    INJECTION = "injection"
    RATE_WINDOW = "rate_window"
    RATE_SESSION = "rate_session"


@dataclass(frozen=True)
class GuardResult:
    """The guard's decision on one message: the cleaned text if accepted, else a reason."""

    allowed: bool
    text: str = ""
    reason: Rejection | None = None
    message: str | None = None


def _reject(reason: Rejection, message: str) -> GuardResult:
    """Build a rejected result with its fixed message and no text."""
    return GuardResult(allowed=False, reason=reason, message=message)


class RateLimiter:
    """Per-session limit: at most `per_window` accepted questions in any rolling window, and
    `per_session` in all."""

    def __init__(
        self,
        per_window: int = config.RATE_LIMIT_PER_MINUTE,
        window_seconds: float = config.RATE_LIMIT_WINDOW_SECONDS,
        per_session: int = config.RATE_LIMIT_PER_SESSION,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Set the limits and the clock (tests pass a fake one)."""
        self.per_window = per_window
        self.window_seconds = window_seconds
        self.per_session = per_session
        self._clock = clock
        self._recent: deque[float] = deque()
        self.total = 0

    def try_acquire(self) -> GuardResult | None:
        """Count one question and return None, or return the rejection if a limit is reached."""
        if self.total >= self.per_session:
            return _reject(
                Rejection.RATE_SESSION, RATE_SESSION_MESSAGE.format(limit=self.per_session)
            )
        now = self._clock()
        while self._recent and self._recent[0] <= now - self.window_seconds:
            self._recent.popleft()
        if len(self._recent) >= self.per_window:
            wait = max(1, math.ceil(self._recent[0] + self.window_seconds - now))
            return _reject(Rejection.RATE_WINDOW, RATE_WINDOW_MESSAGE.format(seconds=wait))
        self._recent.append(now)
        self.total += 1
        return None


def session_limiter(state: MutableMapping[str, Any]) -> RateLimiter:
    """Return the session's rate limiter from `state` (st.session_state), creating it once."""
    limiter = state.get(SESSION_LIMITER_KEY)
    if limiter is None:
        limiter = RateLimiter()
        state[SESSION_LIMITER_KEY] = limiter
    return limiter


def clean_input(text: str) -> str:
    """Normalise Unicode (NFKC), drop control and invisible characters, and trim the text."""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    kept = (ch for ch in text if ch in _KEPT_CONTROLS or unicodedata.category(ch)[0] != "C")
    return "".join(kept).strip()


def looks_like_injection(text: str) -> bool:
    """Return True if the cleaned text matches a known prompt-injection pattern."""
    folded = " ".join(text.casefold().split())
    if any(p.search(folded) for p in _FOLDED_RE):
        return True
    return any(p.search(text) for p in _RAW_RE)


def check_message(text: str, limiter: RateLimiter) -> GuardResult:
    """Clean `text` and run every check; only an accepted message counts against `limiter`."""
    cleaned = clean_input(text)
    if not cleaned:
        return _reject(Rejection.EMPTY, EMPTY_MESSAGE)
    if len(cleaned) > config.MAX_INPUT_CHARS:
        return _reject(Rejection.TOO_LONG, TOO_LONG_MESSAGE)
    if looks_like_injection(cleaned):
        return _reject(Rejection.INJECTION, INJECTION_MESSAGE)
    rejection = limiter.try_acquire()
    if rejection is not None:
        return rejection
    return GuardResult(allowed=True, text=cleaned)


def run_guarded[T](
    text: str, limiter: RateLimiter, call: Callable[[str], T]
) -> tuple[GuardResult, T | None]:
    """Call `call` on the cleaned text only if the guard accepts it; return decision and result."""
    decision = check_message(text, limiter)
    if not decision.allowed:
        return decision, None
    return decision, call(decision.text)
