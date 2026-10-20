"""Input guard: cleans and checks each user message before any model or embedding call.

Checks run in this order: too long (raw), empty, too long (cleaned), prompt-injection
patterns, the domain guardrails (`src/guardrails.py`, T5.3), then the per-session rate limit.
Only a message that passes every check counts against the rate limit (owner's choice in T1.3),
and a rejected message never reaches a model: callers go through `run_guarded()`.
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

from src import config, guardrails

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
    r"(?:all|of|about|the|your|previous|prior|above|earlier|preceding|these|those|system"
    r"|initial|original|developer|safety|current|existing|any|and|or|following)"
)
# A few filler words between the parts, e.g. "ignore all of your previous instructions".
_GAP = rf"(?: {_FILLER}){{0,3}}"
# The instructions are someone else's only when a third party is named right after the noun:
# "... my dietitian gave me", "... that my coach wrote", "... from my coach", "... on the tub".
# Anything else ("... in this conversation", "... that you received") still counts as an attack.
_POSSESSIVES = r"(?:my|his|her|their|our)"
# Words that mean the chat itself, not someone else's advice.
_CHAT_NOUNS = r"(?:conversation|chat|prompt|message|thread|system|assistant|chatbot|ai|bot)"
# Food and training words that make a chat word part of a plan's name ("this AI meal plan").
_FOOD_WORDS = r"meal|meals|diet|plan|plans|food|recipe|recipes|workout|training|program|programme"
_FOOD_COMPOUND = rf"(?:{_FOOD_WORDS})"
# Any longer name built on a chat word ("the AI app", "a chatbot coach", "an AI fitness tracker").
_COMPOUND = (
    rf"(?:{_FOOD_WORDS}|app|apps|coach|tracker|nutrition|fitness|tool|calculator|scale|generated)"
)
# A chat word owned by someone else: "the bot's meal plan", "the message from my dietitian",
# "the chat with my trainer". "'s" counts only before a plan word, so "the assistant's role" or
# "the bot's safety filter" still names the chat.
_OWNED = rf"'s (?:{_FOOD_WORDS})\b| (?:(?:from|with|by|that|which) )?(?:my|his|her|their)\b"
# After "this" or "our" a chat word (and "session" or "model", which are gym and science words
# otherwise: "my session tomorrow", "a model of protein synthesis") means this chat, even inside
# a longer name ("this chat app", "this AI tool"), unless it names a plan ("this AI meal plan").
# Elsewhere a chat word in a longer name or owned by someone else is not the chat ("the
# AI-generated meal plan", "the AI meal plan my app made", "the message from my dietitian").
# Owner's choice in T1.3: "this AI app I downloaded" is rejected with the attacks.
_CHAT_WORDS = (
    rf"(?:(?:(?<=this )|(?<=our ))(?:{_CHAT_NOUNS}|session|model)"
    rf"(?!\w|-(?:generated|powered|written|made|based)\b| {_FOOD_COMPOUND}\b)"
    rf"|{_CHAT_NOUNS}(?![\w-]| {_COMPOUND}\b|{_OWNED}))"
)
# "System prompt" is the assistant's prompt unless a body or energy system comes first: "does the
# immune system prompt inflammation?" uses "prompt" as a verb. One fixed-width lookbehind per
# word, with a space or a hyphen ("immune-system").
_BODY_SYSTEMS = (
    "immune",
    "nervous",
    "digestive",
    "endocrine",
    "hormonal",
    "hormone",
    "reward",
    "dopamine",
    "limbic",
    "satiety",
    "gut",
    "lymphatic",
    "circulatory",
    "cardiovascular",
    "vascular",
    "respiratory",
    "metabolic",
    "muscular",
    "skeletal",
    "renal",
    "urinary",
    "reproductive",
    "sympathetic",
    "parasympathetic",
    "energy",
    "aerobic",
    "anaerobic",
    "glycolytic",
    "oxidative",
    "phosphagen",
    "acid",
    "lactate",
    "pc",
    "stress",
    "hunger",
    "gi",
    "thermoregulatory",
)
_NOT_BODY_SYSTEM = "".join(rf"(?<!{word}{sep})" for word in _BODY_SYSTEMS for sep in (" ", "-"))
_NOT_THIRD_PARTY = (
    rf"(?! (?:(?:that|which|i got|we got|i was given) )?{_POSSESSIVES}\b)"
    rf"(?! (?:on|from|given by|provided by|printed on|written on) (?:the|an?|{_POSSESSIVES})\b)"
    # "... in the old WHO report", "... for this meal plan", but not "... in this conversation".
    rf"(?! (?:in|for|about) (?:the|that|this|an?|my|our) (?!{_CHAT_WORDS}))"
)
# After "instructions" or "rules": a how-to request ("your instructions for meal prepping"),
# unless it points at the chat itself ("your instructions for this conversation").
_NOT_HOW_TO = (
    r"(?! (?:for|on|about|of|by|at|from)\b"
    rf"(?! (?:the |this |that |your |my |our )?{_CHAT_WORDS}))"
)
# "Above" as a word of its own, not "above-average".
_ABOVE = r"above(?![\w-])"

# Matched against the casefolded text with whitespace collapsed to single spaces.
_FOLDED_PATTERNS = [
    # Overriding the instructions.
    rf"\b{_OVERRIDE_VERBS}{_GAP} {_OWN_QUALIFIERS}{_GAP} (?:{_STRONG_NOUNS}|{_WEAK_NOUNS})\b",
    rf"\b{_OVERRIDE_VERBS}{_GAP} {_OTHER_QUALIFIERS}{_GAP} {_STRONG_NOUNS}\b{_NOT_THIRD_PARTY}",
    rf"\b{_OVERRIDE_VERBS} (?:the )?{_STRONG_NOUNS} (?:{_ABOVE}|you were given)",
    # Also rejects a self-correction such as "ignore the above, I meant 80 kg": owner's choice in
    # T1.3 (docs/SECURITY.md, known limits); the message asks the user to rephrase.
    rf"\b{_OVERRIDE_VERBS} (?:the |everything |anything |all )?(?:{_ABOVE}|before this\b)",
    rf"\b{_OVERRIDE_VERBS} (?:what|everything|anything) you(?: were|'ve been| have been) told\b",
    rf"\b(?:rules|instructions|guidelines) you (?:were|have been) (?:given|told)\b{_NOT_HOW_TO}",
    r"\b(?:stop following|do not follow|don't follow|dont follow) your "
    r"(?:rules|instructions|guidelines|programming)\b",
    r"\b(?:override|bypass|disable|turn off|switch off) (?:the |all |any |your )?"
    r"(?:safety|content) (?:guidelines|restrictions|rules|filters?)\b",
    r"\byour new instructions\b",
    # Asking for the hidden prompt.
    # The lookahead first, so the many lookbehinds only run where "system prompt" starts.
    rf"\b(?=system prompts?\b){_NOT_BODY_SYSTEM}system prompts?\b",
    r"\b(?:developer|hidden|secret) prompts?\b",
    r"\bdeveloper message\b",
    rf"\b(?:hidden|secret) instructions\b{_NOT_HOW_TO}",
    r"\byour (?:initial|original|hidden|secret|system) (?:instructions|prompts?)\b",
    # Not "your original message": a follow-up may quote an earlier answer.
    r"\byour (?:hidden|secret|system) message\b",
    r"\b(?:reveal|repeat|print|show|output|display|leak|dump|recite|tell me) (?:me )?"
    rf"(?:all )?(?:of )?your (?:instructions|prompt|configuration|rules|guidelines)\b{_NOT_HOW_TO}",
    rf"\bwhat (?:are|were) your instructions\b(?! to me){_NOT_HOW_TO}",
    rf"\b(?:print|repeat|output|recite) (?:everything|all|the (?:text|words)) {_ABOVE}",
    # Changing the assistant's role or switching off its rules. "Mode" is left out here, as
    # "you're now in cutting mode" is gym talk; the jailbreak modes have their own pattern below.
    r"\byou(?: are|'re|re) now (?:an?|the|my|in) (?:\w+ ){0,2}?"
    r"(?:ai|assistant|bot|chatbot|model|character|persona)\b",
    r"\byou(?: are|'re|re) now (?:dan|unrestricted|unfiltered|uncensored|jailbroken|free)\b",
    r"\bfrom now on,? you(?: will| must| should| are|'re| have)? (?:ignore|disregard|forget"
    r"|answer as|respond as|reply as|act as|answer without|respond without|not follow"
    r"|no longer|have no (?:rules|restrictions|limits|filters|guidelines)|dan\b|unrestricted"
    r"|unfiltered)",
    r"\b(?:developer|god|dan|debug|jailbreak|unrestricted|unfiltered|admin) mode\b",
    r"\bjailbr(?:eak|oken)\b",
    r"\bdo anything now\b",
    r"\b(?:pretend|imagine) (?:that )?(?:you are|you're|to be) (?:an? )?"
    r"(?:unrestricted|unfiltered|uncensored|evil|dan)\b",
    r"\bact as (?:an? )?(?:unrestricted|unfiltered|uncensored|jailbroken|evil|dan)\b",
    r"\b(?:no longer|not) (?:bound|restricted) by (?:your|any) "
    r"(?:rules|instructions|guidelines|restrictions|policies)\b",
]

# Matched against the cleaned text with its line breaks: fake role markers and look-alikes of the
# delimiters the answer step wraps around user text and sources (docs/ARCHITECTURE.md, step 5).
# Written so no two unbounded repeats sit next to each other (linear time on any input).
# The answer step escapes "<" and ">" anyway (T3.4), so these only stop an attempt before any API
# call. A tag may carry up to five attributes (name=value, value quoted or not) and a closing
# slash (<user_input id="2">, </sources lang="en">, <sources/>), and "user input" may be written
# with "_", "-" or a space. Only attribute-shaped text counts, so "<" and ">" used as "less than"
# and "more than" around a word ("(<sources say 25%) and > 1200 kcal") pass. A role line may follow
# Markdown heading, quote, bold or italic markers (**System:**, > System:, __Assistant__:).
_RAW_PATTERNS = [
    r"<\s*(?:/\s*)?(?:system|user[\s_-]*input|sources?|assistant|user|developer|instructions?)"
    r"(?:\s+[\w:-]{1,40}\s*=\s*(?:\"[^\"<>\n]{0,100}\"|'[^'<>\n]{0,100}'|[^\s\"'<>]{1,100})){0,5}"
    r"\s*(?:/\s*)?>",
    r"<\|[a-z_]+\|>",
    r"\[/?(?:inst|sys)\]",
    r"<<\s*(?:/\s*)?sys\s*>>",
    r"(?m)^[ \t]*(?:[#>*_][ \t]*){0,10}(?:system|assistant|developer|new instructions)"
    r"[ \t]*(?:[*_]{1,3}[ \t]*)?:",
]

_FOLDED_RE = [re.compile(p) for p in _FOLDED_PATTERNS]
_RAW_RE = [re.compile(p, re.IGNORECASE) for p in _RAW_PATTERNS]

# Line breaks and tabs are the only control characters a question keeps; other line and
# paragraph separators become "\n", so a role marker after one is still at the start of a line.
_KEPT_CONTROLS = {"\n", "\t"}
_LINE_BREAKS = str.maketrans(dict.fromkeys("\r\x0b\x0c\x85\u2028\u2029", "\n"))
# Curly apostrophes (smart punctuation on phones) become "'", which the patterns use.
_APOSTROPHES = str.maketrans(dict.fromkeys("\u2018\u2019\u02bc", "'"))
# Invisible characters outside the "C" categories: the combining grapheme joiner, Hangul fillers,
# Khmer inherent vowels, the blank Braille pattern, Mongolian and other variation selectors.
_INVISIBLE = frozenset(
    [0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0]
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
    # A domain guardrail refuses or redirects the question (`GuardResult.concern` says which).
    GUARDRAIL = "guardrail"


@dataclass(frozen=True)
class GuardResult:
    """The guard's decision on one message: the cleaned text if accepted, else a reason."""

    allowed: bool
    text: str = ""
    reason: Rejection | None = None
    message: str | None = None
    concern: guardrails.Concern | None = None


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


def clean_input(text: str, dropped: str = "", form: str = "NFC") -> str:
    """Normalise Unicode (`form`) and line breaks, swap control and invisible chars, trim."""
    text = unicodedata.normalize(form, text).replace("\r\n", "\n")
    text = text.translate(_LINE_BREAKS).translate(_APOSTROPHES)
    kept = (
        ch
        if ch in _KEPT_CONTROLS
        or (unicodedata.category(ch)[0] != "C" and ord(ch) not in _INVISIBLE)
        else dropped
        for ch in text
    )
    return "".join(kept).strip()


def _strip_marks(text: str) -> str:
    """Decompose the text (NFKD) and drop every mark (M*), so an accented "ignore" reads plain."""
    decomposed = unicodedata.normalize("NFKD", text)
    # All mark categories: non-spacing (accents, overlays), spacing and enclosing (circles).
    return "".join(ch for ch in decomposed if unicodedata.category(ch)[0] != "M")


def detection_views(text: str) -> set[str]:
    """Return the forms of the raw text that the injection patterns are run on."""
    # NFKC folds full-width and other compatibility letters. An invisible character can hide a
    # word ("Ign\u200bore") or stand in for a space ("Ignore\u200ball"), so it is both removed
    # and turned into a space; accents and overlay marks ("Ig\u0301nore") are stripped too.
    views = {clean_input(text, form="NFKC"), clean_input(text, dropped=" ", form="NFKC")}
    return views | {_strip_marks(view) for view in views}


def looks_like_injection(text: str) -> bool:
    """Return True if the cleaned text matches a known prompt-injection pattern."""
    folded = " ".join(text.casefold().split())
    if any(p.search(folded) for p in _FOLDED_RE):
        return True
    return any(p.search(text) for p in _RAW_RE)


def _first_concern(views: set[str]) -> guardrails.Concern | None:
    """Return the guardrail any detection view falls under, drug dosing first, or None."""
    found = {concern for view in views if (concern := guardrails.find_concern(view)) is not None}
    # The order of Concern, so the same text always gets the same message.
    return next((concern for concern in guardrails.Concern if concern in found), None)


def check_message(text: str, limiter: RateLimiter) -> GuardResult:
    """Clean `text` and run every check; only an accepted message counts against `limiter`."""
    if len(text) > config.MAX_RAW_INPUT_CHARS:
        return _reject(Rejection.TOO_LONG, TOO_LONG_MESSAGE)
    # The model gets NFC text, so "10\u00b3 kcal" stays as typed; NFKC is only for detection.
    cleaned = clean_input(text)
    if not cleaned:
        return _reject(Rejection.EMPTY, EMPTY_MESSAGE)
    if len(cleaned) > config.MAX_INPUT_CHARS:
        return _reject(Rejection.TOO_LONG, TOO_LONG_MESSAGE)
    views = detection_views(text)
    if any(looks_like_injection(view) for view in views):
        return _reject(Rejection.INJECTION, INJECTION_MESSAGE)
    concern = _first_concern(views)
    if concern is not None:
        return GuardResult(
            allowed=False,
            reason=Rejection.GUARDRAIL,
            message=guardrails.MESSAGES[concern],
            concern=concern,
        )
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
