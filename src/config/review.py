"""The weekly review: its evidence search, its limits, its questions, its check patterns."""

from src.config.knowledge import TRAINING_TOPIC
from src.config.limits import TARGET_INPUT_MAX_KCAL

# The weekly review (T9.16, D17; src/weekly_review.py, src/agent/review.py); its model and token
# cap are REVIEW_MODEL and REVIEW_MAX_TOKENS, its prompt REVIEW_PROMPT_PATH.
# The blocks the review's user message holds, which the owner's prompt names (a test checks it).
REVIEW_PROMPT_BLOCKS: tuple[str, ...] = ("<metrics>", "<sources>", "<language>")
# The evidence search covers only the topics the metrics raise (D17): protein when the week's
# average is below its target by more than this share of the target, energy balance when the
# average kcal is off its target by more than this share either way, and training when the
# training scope is in the review and a session was logged. One fixed query per topic, written by
# us in English (the sources are English), searched with that topic as the filter, so no client
# text reaches the embedding API.
REVIEW_PROTEIN_GAP_SHARE = 0.10
REVIEW_KCAL_GAP_SHARE = 0.10
REVIEW_EVIDENCE_QUERIES: dict[str, str] = {
    "protein": "daily protein intake per kilogram of body weight for muscle gain with resistance "
    "training",
    "energy_balance": "energy intake, energy deficit and surplus for body composition in "
    "resistance-trained adults",
    TRAINING_TOPIC: "weekly training volume, number of sets per muscle group and training "
    "frequency for muscle hypertrophy",
}
# Every attempt at a draft: the first and the one retry (D17).
REVIEW_MAX_DRAFTS = 2
# The most supersteps one invoke of a review run may take: one per node with two drafts, and
# a decision (LangGraph counts per invoke; a refused edit waits for the coach again).
REVIEW_MAX_STEPS = 12
# The shortest source_range a training recommendation may quote; it must also hold a number
# and a word (a unit), so a bare "10" cannot match any chunk that has a 10.
REVIEW_SOURCE_RANGE_MIN_CHARS = 6
# The most chunks the review's <sources> holds, over all its topics (labelled [S1]...).
REVIEW_MAX_CHUNKS = 6
# The schema's limits: items per list, and characters per text (the coach's edit too).
REVIEW_MAX_ITEMS = 6
REVIEW_TEXT_MAX_CHARS = 600
REVIEW_FIELD_MAX_CHARS = 200
# The values a recommendation's kcal fields may take, ends included (the coach's edit form too).
# A value outside them fails the schema; inside them, the calorie floor is checked by arithmetic,
# so the lower ends sit well below CALORIE_FLOOR_KCAL on purpose: a low target gets the floor's
# own retry text, not the schema's.
REVIEW_TARGET_KCAL_RANGE = (1, TARGET_INPUT_MAX_KCAL)
REVIEW_KCAL_CHANGE_RANGE = (-2000, 2000)
# Questions to the coach under an approved review (T9.25, PRD feature 27): the longest question or
# answer (within STORE_TEXT_MAX_CHARS), and the most questions a gymer asks under one review, one
# at a time (each waits for the coach's answer; owner's choice, 2026-11-06).
REVIEW_THREAD_MAX_CHARS = 500
REVIEW_THREAD_MAX_QUESTIONS = 3
# Validation (AC-27, AC-35; docs/PRD.md guardrails). Regular expressions, matched without case.
# A diagnosis: a medical condition named for the client (English and German).
REVIEW_DIAGNOSIS_PATTERNS: tuple[str, ...] = (
    r"\bdiagnos",
    r"\beating disorder",
    r"\banorexi",
    r"\bbulimi",
    r"\bbinge[- ]eating",
    r"\borthorexi",
    r"\bdiabet",
    r"\bthyroid",
    r"\binsulin resistan",
    r"\bdeficiency\b",
    r"\bmalnutrition",
    r"\bmalnourish",
    r"\bdepressi",
    r"\bsyndrome\b",
    r"\bdisorder",
    r"\bessst[öo]rung",
    r"\bmagersucht",
    r"\banorexie",
    r"\bbulimie",
    r"\bdiabetes",
    r"\bschilddr[üu]s",
    r"\binsulinresistenz",
    r"mangel\b",
    r"\bunterern[äa]hr",
    r"\bsyndrom\b",
    r"st[öo]rung\b",
)
# A written schedule: "Day 1" or "Tag 1", and a weekday followed by a colon (English and German).
# The chat's answer is checked with these two alone (T10.5, guardrails.reads_as_program_schedule()):
# the review's other program patterns also match a cited protocol ("3 x 10 [S2]"), the redirect to
# a coach ("an individual training program") and "Trainingsplan" in a refusal.
PROGRAM_SCHEDULE_PATTERNS: tuple[str, ...] = (
    r"\b(?:day|tag)\s*\d+\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|montag|dienstag|mittwoch|"
    r"donnerstag|freitag|samstag|sonntag)\s*:",
)
# A program in a review's training recommendation: sets and reps per exercise, a day-by-day plan
# (English and German).
REVIEW_PROGRAM_PATTERNS: tuple[str, ...] = (
    r"\b\d+\s*[x×]\s*\d+",
    r"\b\d+\s*sets?\s+of\s+\d+",
    r"\b\d+\s*(?:reps?|repetitions|wiederholungen|wdh)\b",
    *PROGRAM_SCHEDULE_PATTERNS,
    r"\b(?:training|workout)\s*(?:plan|program|programme|split)\b",
    r"\btrainingsplan",
)
# A client's own set count or weekly volume in a training recommendation: the number for this
# client is the coach's (PRD feature 26). The source's range is checked against its chunk instead.
REVIEW_CLIENT_VOLUME_PATTERNS: tuple[str, ...] = (
    r"\b\d+\s*(?:sets?|s[äa]tze?)\b",
    r"\b\d+(?:[.,]\d+)*\s*kg\s*(?:total|volume|volumen|per week|pro woche)",
    r"\bvolume\s+(?:of|von)\s+\d",
)
# A kcal figure in a recommendation is an intake, checked against the calorie floor, unless it is
# a change: the word before it (after an approximate word, if any) is one of these or it carries a
# sign, or the word after it is one of the others. "About 1100 kcal" alone is an intake.
REVIEW_KCAL_CHANGE_BEFORE: tuple[str, ...] = ("by", "um")
# "by" and "um" make a change only with one of these verb stems in the same sentence, before or
# after the figure: "um 1.000 kcal" alone means "around 1,000 kcal" (code review rounds 6 and 7).
# A stem is found inside any word, so none may occur in a common word that is no change verb:
# "fall" is in "ebenfalls" and "gegebenenfalls", hence "fall by" (code review round 8). The
# participles of the separable German verbs ("angepasst", "herabgesetzt") are not stems: they are
# also adjectives ("Die angepasste Zufuhr sollte um 1.000 kcal liegen") (code review round 9). So
# the passive ("Die Zufuhr wird um 300 kcal angepasst") and the split imperative ("Passen Sie die
# Zufuhr um 300 kcal an") are not read, and their figure counts as an intake, which fails safe.
REVIEW_KCAL_CHANGE_VERBS: tuple[str, ...] = (
    "raise",
    "increase",
    "reduce",
    "lower",
    "cut",
    "drop",
    "decrease",
    "rise",
    "go up",
    "go down",
    "bring",
    "adjust",
    "fall by",
    "falls by",
    "boost",
    "trim",
    "anpass",
    "zurückfahr",
    "herabsetz",
    "erhöh",
    "senk",
    "reduzier",
    "steiger",
    "verringer",
    "anheb",
    "kürz",
    "sinken",
)
# The zu-infinitives of the separable German verbs, as whole words only: "anzupassende" is an
# adjective (code review round 9).
REVIEW_KCAL_CHANGE_WORDS: tuple[str, ...] = ("anzupassen", "zurückzufahren", "herabzusetzen")
REVIEW_KCAL_SIGNS: tuple[str, ...] = ("+", "-", "−", "±")
REVIEW_KCAL_APPROXIMATE: tuple[str, ...] = (
    "about",
    "around",
    "roughly",
    "approximately",
    "some",
    "etwa",
    "rund",
    "ungefähr",
    "ca.",
    "circa",
)
REVIEW_KCAL_CHANGE_AFTER: tuple[str, ...] = (
    "deficit",
    "surplus",
    "less",
    "more",
    "fewer",
    "lower",
    "higher",
    "defizit",
    "überschuss",
    "weniger",
    "mehr",
    # "an 800 kcal gap" (code review round 3). "800 kcal below the target", "short of" and
    # "unter" are not changes: they also read as an intake ("1,000 kcal under supervision", "unter
    # der Woche"), and every attempt to tell the two apart by the words around them left a hole
    # (code review rounds 4 and 5), so the owner chose (2026-11-06) to drop them; the prompt asks
    # for a gap as a change ("raise intake by ...") or as percent_of_target.
    "gap",
)
