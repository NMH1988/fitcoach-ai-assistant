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
    f"Your message is too long. Please keep it to at most {config.MAX_INPUT_CHARS} characters."
)
# Worded so a nutrition question caught by mistake is told how to get through, not accused.
INJECTION_MESSAGE = (
    "Your message looks like it tries to change how the assistant works, so it was not sent. "
    "If it is a nutrition question, please rephrase it."
)
RATE_WINDOW_MESSAGE = "You are sending questions too fast. Please wait {seconds} s and try again."
RATE_SESSION_MESSAGE = "This session has reached its limit of {limit} questions."

# Key under which the session's rate limiter lives in st.session_state.
SESSION_LIMITER_KEY = "rate_limiter"

# "Ignore ..." is an attack only when it points at the assistant's own instructions. Nutrition
# questions say "ignore" about coaches, labels and official guidelines all the time ("should I
# ignore the previous guidelines on saturated fat?", "can I disregard the prior instructions my
# dietitian gave me?"), so the words between the verb and the noun come from a short list, and
# qualifiers that could describe someone else's advice ("previous", "all", "these") only count
# when nothing names a third party after the noun.
_OVERRIDE_VERBS = r"(?:ignore|disregard|forget|override|bypass)"
_STRONG_NOUNS = (
    r"(?:instructions?|prompts?|directives?|directions|commands|programming|guardrails?"
    r"|system message)"
)
_WEAK_NOUNS = r"(?:rules|guidelines|restrictions|constraints|policies)"
# Qualifiers that only ever mean the assistant's own setup.
_OWN_QUALIFIERS = r"(?:your|above|system|developer)"
# Qualifiers that could also describe advice from someone else.
_OTHER_QUALIFIERS = r"(?:previous|prior|earlier|preceding|all|these|those|initial|original)"
_FILLER = (
    r"(?:all|of|the|your|previous|prior|above|earlier|preceding|these|those|system|initial"
    r"|original|developer|safety|current|existing|any|and|or)"
)
# A few filler words between the parts, e.g. "ignore all of your previous instructions".
_GAP = rf"(?: {_FILLER}){{0,3}}"
# What follows "instructions" when they are someone else's: "... my dietitian gave me",
# "... on the tub", "... from my coach".
_NOT_THIRD_PARTY = (
    r"(?! (?:on|from|in|for|of|about|my|his|her|their|our|the|that|which|i|we|written"
    r"|printed|given by|provided by)\b)"
)

# Matched against the casefolded text with whitespace collapsed to single spaces.
_FOLDED_PATTERNS = [
    # Overriding the instructions.
    rf"\b{_OVERRIDE_VERBS}{_GAP} {_OWN_QUALIFIERS}{_GAP} (?:{_STRONG_NOUNS}|{_WEAK_NOUNS})\b",
    rf"\b{_OVERRIDE_VERBS}{_GAP} {_OTHER_QUALIFIERS}{_GAP} {_STRONG_NOUNS}\b{_NOT_THIRD_PARTY}",
    rf"\b{_OVERRIDE_VERBS} (?:the )?{_STRONG_NOUNS} (?:above|you were given)\b",
    rf"\b{_OVERRIDE_VERBS} (?:the |everything |anything |all )?(?:above|before this)\b",
    rf"\b{_OVERRIDE_VERBS} (?:what|everything|anything) you(?: were|'ve been| have been) told\b",
    r"\b(?:rules|instructions|guidelines) you (?:were|have been) (?:given|told)\b",
    r"\bnew instructions ?:",
    # Asking for the hidden prompt.
    r"\b(?:system|developer|hidden|secret) prompt\b",
    r"\bdeveloper message\b",
    r"\b(?:hidden|secret) instructions\b",
    r"\byour (?:initial|original|hidden|secret|system) (?:instructions|prompt|message)\b",
    r"\b(?:reveal|repeat|print|show|output|display|leak|dump|recite|tell me) (?:me )?"
    r"(?:all )?(?:of )?your (?:instructions|prompt|configuration)\b",
    r"\bwhat (?:are|were) your instructions\b",
    # Changing the assistant's role or switching off its rules.
    r"\byou(?: are|'re|re) now (?:an?|the|my|in) (?:\w+ ){0,2}?"
    r"(?:ai|assistant|bot|chatbot|model|mode|character|persona)\b",
    r"\byou(?: are|'re|re) now (?:dan|unrestricted|unfiltered|uncensored|jailbroken|free)\b",
    r"\bfrom now on,? you(?: will| must| should| are|'re| have)? (?:ignore|disregard|forget"
    r"|answer as|respond as|reply as|act as|answer without|respond without|not follow"
    r"|no longer|have no|dan\b|unrestricted|unfiltered)",
    r"\b(?:developer|god|dan|debug|jailbreak|unrestricted|unfiltered|admin) mode\b",
    r"\bjailbr(?:eak|oken)\b",
    r"\bdo anything now\b",
    r"\b(?:pretend|imagine) (?:that )?(?:you are|you're|to be) (?:an? )?"
    r"(?:unrestricted|unfiltered|uncensored|different|evil|another|dan)\b",
    r"\bact as (?:an? )?(?:unrestricted|unfiltered|uncensored|jailbroken|evil|different|dan)\b",
    r"\b(?:no longer|not) (?:bound|restricted) by (?:your|any) "
    r"(?:rules|instructions|guidelines|restrictions|policies)\b",
]

# Matched against the cleaned text with its line breaks: fake role markers and look-alikes of the
# delimiters the answer step wraps around user text and sources (docs/ARCHITECTURE.md, step 5).
# Written so no two unbounded repeats sit next to each other (linear time on any input).
_RAW_PATTERNS = [
    r"<\s*(?:/\s*)?(?:system|user_input|sources|assistant|user|developer|instructions?)\s*>",
    r"<\|[a-z_]+\|>",
    r"\[/?(?:inst|sys)\]",
    r"<<\s*(?:/\s*)?sys\s*>>",
    r"(?m)^[ \t]*(?:#+[ \t]*)?(?:system|assistant|developer)[ \t]*:",
]

_FOLDED_RE = [re.compile(p) for p in _FOLDED_PATTERNS]
_RAW_RE = [re.compile(p, re.IGNORECASE) for p in _RAW_PATTERNS]

# Line breaks and tabs are the only control characters a question keeps; other line and
# paragraph separators become "\n", so a role marker after one is still at the start of a line.
_KEPT_CONTROLS = {"\n", "\t"}
_LINE_BREAKS = str.maketrans(dict.fromkeys("\r\x0b\x0c\x85  ", "\n"))
# Curly apostrophes (smart punctuation on phones) become "'", which the patterns use.
_APOSTROPHES = str.maketrans(dict.fromkeys("‘’ʼ", "'"))
# Invisible characters outside the "C" categories: the combining grapheme joiner, Hangul fillers,
# Khmer inherent vowels, Mongolian and other variation selectors.
_INVISIBLE = frozenset(
    [0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x3164, 0xFFA0]
    + list(range(0x180B, 0x1810))
    + list(range(0xFE00, 0xFE10))
    + list(range(0xE0100, 0xE01F0))
)


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
    """Per-session limit on accepted questions: a rolling-window cap and a session total."""

    def __init__(
        self,
        per_window: int = config.RATE_LIMIT_PER_MINUTE,
        window_seconds: float = config.RATE_LIMIT_WINDOW_SECONDS,
        per_session: int = config.RATE_LIMIT_PER_SESSION,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Set the limits and the clock (tests pass a fake one); every limit must be positive."""
        if per_window < 1 or per_session < 1 or window_seconds <= 0:
            raise ValueError("Rate limits must be positive.")
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
    """Normalise Unicode (NFKC) and line breaks, drop control and invisible characters, trim."""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n")
    text = text.translate(_LINE_BREAKS).translate(_APOSTROPHES)
    kept = (
        ch
        for ch in text
        if ch in _KEPT_CONTROLS
        or (unicodedata.category(ch)[0] != "C" and ord(ch) not in _INVISIBLE)
    )
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
