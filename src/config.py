"""App-wide settings: models, OpenRouter endpoint, limits, UI text and secrets loading."""

import os
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent

APP_TITLE = "Nutrition AI Assistant"
APP_INTRO = (
    "Evidence-based nutrition answers for adults who lift weights, with the research behind them."
)
# Shown on every page state (docs/PRD.md, domain guardrails).
DISCLAIMER = (
    "This app gives general information for healthy adults. It is not medical advice and does "
    "not replace a doctor or a registered dietitian."
)

# All model calls go through OpenRouter's OpenAI-compatible API (docs/ARCHITECTURE.md, D3).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# The chat models the app may use: the Sprint 1 list, reused by choice (docs/ARCHITECTURE.md).
ALLOWED_MODELS: tuple[str, ...] = ("openai/gpt-5-mini", "openai/gpt-5-nano", "openai/gpt-5")
# Writes the answers and calls the tools.
DEFAULT_ANSWER_MODEL = "openai/gpt-5-mini"
# Rewrites the question for retrieval; a simple task, so the cheapest model (D6).
QUERY_TRANSLATION_MODEL = "openai/gpt-5-nano"
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"

# gpt-5 reasoning effort for every chat call: answers are grounded in retrieved sources, so "low"
# keeps cost and latency down without hurting them (owner's choice in T1.2).
REASONING_EFFORT = "low"
# Seconds one model or embedding request may take before it counts as a timeout.
LLM_TIMEOUT_SECONDS = 60
# Retries the SDK makes after a 408, 409, 429, 5xx, a timeout or a connection error; 401 and 402
# are not retried by default. With the timeout above this bounds one call, to about 7 minutes at
# worst: the SDK also honours a server's Retry-After, up to 2 minutes per retry.
LLM_MAX_RETRIES = 2

# The token budget, input length and rate limits below are the values that worked in Sprint 1.

# gpt-5 models spend reasoning tokens from this budget too, so keep it generous: a low budget can
# be used up by thinking alone and return no text (learned in Sprint 1).
DEFAULT_MAX_TOKENS = 4000
# Every request is clamped to this, whatever a caller asks for, to bound the cost of one reply.
MAX_TOKENS_CAP = 16000

# Longest user message (after cleaning) the guard lets through to the models.
MAX_INPUT_CHARS = 2000
# Longest raw message the guard reads at all: checked before cleaning, so a huge paste (or one
# padded with invisible characters) is rejected without walking through it. Leaves room for
# characters that cleaning drops.
MAX_RAW_INPUT_CHARS = 4 * MAX_INPUT_CHARS

# Questions allowed per browser session: at most this many in any rolling window, and this many
# in all. One accepted question counts once, however many model calls its turn makes; questions
# the guard rejects do not count (owner's choice in T1.3). Reloading the page starts a new session.
RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_PER_SESSION = 50
# The level of the app's JSON log lines (src/observability.py, T8.2): INFO writes one line per chat
# turn, WARNING only the guard rejections, model errors and failed tool calls.
LOG_LEVEL = "INFO"

# Knowledge base sources (docs/SOURCES.md; docs/ARCHITECTURE.md section 4).
SOURCES_MANIFEST_PATH = PROJECT_ROOT / "data" / "sources.json"
# Downloaded article XML; gitignored (copyright policy rule 8).
RAW_SOURCES_DIR = PROJECT_ROOT / "data" / "raw"
ATTRIBUTION_PATH = PROJECT_ROOT / "ATTRIBUTION.md"
# The topics a source can be tagged with; query translation filters on them (T3.2).
TOPICS: tuple[str, ...] = (
    "protein",
    "carbohydrate",
    "fat",
    "energy_balance",
    "nutrient_timing",
    "supplements",
)
# 1 = ISSN position stand, 2 = other peer-reviewed review or meta-analysis (docs/SOURCES.md).
EVIDENCE_TIERS: tuple[int, ...] = (1, 2)

# Chunking of the article text (docs/ARCHITECTURE.md section 4). A chunk is at most CHUNK_SIZE
# characters, its section title included (a chunk joined with a short piece may be up to
# CHUNK_SIZE + CHUNK_MIN_CHARS); neighbouring chunks of a section share CHUNK_OVERLAP.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
# Room always left for the text after a very long section title, so the splitter still works;
# such a chunk may then be longer than CHUNK_SIZE (no approved article comes close). Must stay above
# CHUNK_OVERLAP, or the splitter raises ValueError.
CHUNK_MIN_BODY_CHARS = 400
# A piece of a section shorter than this (title included) is joined to the piece before it, or else
# to the one after it, as long as the result is at most CHUNK_SIZE + CHUNK_MIN_CHARS. The splitter's
# short pieces are often little more than the overlap they repeat, and such chunks were near short,
# generic queries (T3.7). A section that is short as a whole stays one short chunk.
CHUNK_MIN_CHARS = 300
# Section title for paragraphs that sit directly in the body, outside any section (e.g. #18a).
MAIN_TEXT_TITLE = "Main text"
# Back matter that many articles put inside <body>: dropped, as it is not nutrition content (owner's
# choice in T2.2), and so are the registration notes of an abstract, a bare PROSPERO ID that short
# queries matched (T3.7; a Methods "Protocol and registration" section is content and stays).
# Matched on the section's sec-type, or on its title in lower case with numbering and punctuation
# removed; a title starting with "appendix" is dropped too.
INGEST_DROPPED_SEC_TYPES: frozenset[str] = frozenset(
    {
        "ack",
        "ai-statement",
        "app",
        "associated-data",
        "coi-statement",
        "contrib-info",
        "data-availability",
        "data-availability-statement",
        "disclaimer",
        "display-objects",
        "fn-group",
        "history",
        "kwd-group",
        "ref-list",
        "supplementary-material",
        "supplementary-materials",
    }
)
INGEST_DROPPED_SEC_TITLES: frozenset[str] = frozenset(
    {
        "abbreviations",
        "acknowledgement",
        "acknowledgements",
        "acknowledgment",
        "acknowledgments",
        "associated data",
        "author contributions",
        "authors contributions",
        "availability of data and materials",
        "clinical trial registration",
        "competing interests",
        "conflict of interest",
        "conflicts of interest",
        "consent for publication",
        "contributor information",
        "correction note",
        "data availability",
        "data availability statement",
        "declarations",
        "disclaimer",
        "disclaimer publishers note",
        "disclosure",
        "disclosure statement",
        "ethics approval",
        "ethics approval and consent to participate",
        "ethics approval statement",
        "footnotes",
        "funding",
        "funding statement",
        "generative ai statement",
        "infographic",
        "informed consent statement",
        "institutional review board statement",
        "publishers note",
        "references",
        "supplemental material",
        "supplementary information",
        "supplementary material",
        "supplementary materials",
        "supporting information",
        "systematic review registration",
        "trial registration",
    }
)

# The vector index (docs/ARCHITECTURE.md section 4): a persistent Chroma collection, embedded in the
# app's process only (never a server; .claude/rules/security-privacy.md). Gitignored and rebuilt by
# BUILD_INDEX_COMMAND (D7).
CHROMA_DIR = PROJECT_ROOT / "chroma"
# Chroma names need 3-512 characters from [a-zA-Z0-9._-].
CHROMA_COLLECTION = "nutrition-sources"
BUILD_INDEX_COMMAND = "python scripts/build_index.py"
# Chunks sent to the embedding API per request: about 50 KB of text each, so one failed request
# loses little work and the build can show its progress.
EMBEDDING_BATCH_SIZE = 64

# Retrieval and answers for one chat turn (T3.1; query translation and hybrid search extend it in
# T3.2 and T3.3). The best chunks after RRF given to the answer model, labelled [S1]...[S6]; also
# the length of each vector and keyword list that RRF merges.
RETRIEVAL_TOP_K = 6
# Cosine distance (0 = same meaning, up to 2) above which a chunk counts as not relevant to the
# question. Measured on the real index (O5, 2026-10-20, 28 questions; docs/TESTING.md): questions
# the sources cover, short or long, had their nearest chunk at 0.28-0.54; unrelated ones at 0.70
# and above; near-domain ones (a dog's diet, running shoes, insulin) at 0.56-0.70. 0.62 sits midway
# and favours answering: a near-domain question that passes costs one model call, which the
# prompt declines or redirects, while a covered question that is blocked gets no answer at all.
# Measured on questions as asked, so only the question's own nearest chunk decides whether the
# sources cover it; once they do, its rewrites add the chunks within the same limit (T3.8).
RETRIEVAL_MAX_DISTANCE = 0.62
# Reciprocal Rank Fusion (T3.3, Hard 1): a chunk scores the sum of 1 / (RRF_K + rank) over the
# ranked lists it is in (rank 1 is the top). 60 is the constant of the original RRF paper; it
# keeps one list's top rank from outweighing a chunk that several lists rank a little lower.
RRF_K = 60
# The most chunks of one source that come first in the fused list (T8.3): without a cap one article
# filled all six places (q2, q3, q10) and a second source never reached the answer model. Chunks
# over the cap are only used, in fused order, when too few other sources are left to fill the list.
MAX_CHUNKS_PER_SOURCE = 3
# The owner's evaluation questions (O2), each with the sources it should find; read by
# scripts/compare_retrieval.py (T3.3) and the evaluation run (T6.1).
EVAL_QUESTIONS_PATH = PROJECT_ROOT / "data" / "eval_questions.json"
# The owner's German evaluation questions (O2, for T7.2), kept apart: compare_retrieval.py searches
# each question as written, with no rewrite into English, so German ones would lower the T3.6 rates.
EVAL_QUESTIONS_DE_PATH = PROJECT_ROOT / "data" / "eval_questions_de.json"
# Where scripts/run_evaluation.py (T6.1) writes its full reports: the answers and the article text
# of the chunks found, for judging the citations. Gitignored: never committed.
EVAL_RUNS_DIR = PROJECT_ROOT / "data" / "eval_runs"
# The answer system prompt, written by the owner (O1; .claude/rules/workflow.md).
ANSWER_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "answer_system.md"
# The language part of the answer prompt, one file per UI language, written by the owner (O1, T7.2).
# The code joins the chosen language's file to the end of the answer prompt: the language comes from
# the app's EN | DE control, never from the user's text.
ANSWER_LANGUAGE_PROMPT_PATHS = {
    "en": PROJECT_ROOT / "src" / "prompts" / "answer_language_en.md",
    "de": PROJECT_ROOT / "src" / "prompts" / "answer_language_de.md",
}

# Query translation (T3.2; docs/ARCHITECTURE.md section 5): one QUERY_TRANSLATION_MODEL call
# rewrites the question and picks optional filters. Its system prompt is written by the owner (O7).
QUERY_TRANSLATION_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "query_translation_system.md"
# The same budget as the answers: gpt-5 reasoning tokens come out of it too (learned in Sprint 1).
QUERY_TRANSLATION_MAX_TOKENS = DEFAULT_MAX_TOKENS
# Rewrites per question; the question itself is searched as well (owner's choice in T3.2).
QUERY_REWRITES = 3
# Longest rewrite accepted; a longer one makes the whole reply invalid (fallback to the question).
QUERY_REWRITE_MAX_CHARS = 300
# The years a min_year filter may name; the oldest approved source is from 2014. A year with no
# source after it finds nothing, so the search runs again without filters.
QUERY_MIN_YEAR_RANGE = (2000, 2100)
# Shown instead of an answer when no chunk is relevant and the model used no tool (AC-2). Since T4.4
# the model is still called with the tools when the query plan says a tool could answer
# (`needs_tool`, T3.5), as a food lookup or an energy question may match no research passage; its
# own text is never shown on this path (owner's choice, 2026-10-20). Otherwise no model is called.
NO_SOURCES_MESSAGE = (
    "Our sources do not cover this question, so there is no answer from the research. Try a "
    "question about protein, carbohydrate, fat, energy balance, nutrient timing or supplements "
    "for strength training."
)
# What <sources> holds for the model when no chunk is relevant.
NO_SOURCES_BLOCK = "None: no research excerpt is close enough to this question."
API_KEY_NAME = "OPENROUTER_API_KEY"

# Shown in the answer when the key is not set up (AC-13).
MISSING_KEY_MESSAGE = (
    "The OpenRouter API key is missing. Add it to `.streamlit/secrets.toml` or set the "
    f"{API_KEY_NAME} environment variable, then restart the app."
)
SECRETS_FILE_MESSAGE = (
    f"`.streamlit/secrets.toml` could not be read. Fix the file or set the {API_KEY_NAME} "
    "environment variable, then restart the app."
)
# Shown in the answer when the prompt file is missing or empty; no API call is made.
PROMPT_MISSING_MESSAGE = (
    "The answer prompt `src/prompts/answer_system.md` is missing or empty, so no answer can be "
    "written. Restore the file and ask again."
)
QUERY_PROMPT_MISSING_MESSAGE = (
    "The query translation prompt `src/prompts/query_translation_system.md` is missing or empty, "
    "so the question cannot be searched. Restore the file and ask again."
)
LANGUAGE_PROMPT_MISSING_MESSAGE = (
    "The answer language prompt (`src/prompts/answer_language_en.md` or `answer_language_de.md`) "
    "is missing or empty, so no answer can be written. Restore the file and ask again."
)
# Shown in the answer for any other error in a chat turn (a bug, an unexpected library error);
# never the error's own text (T1.8, AC-13).
TURN_ERROR_MESSAGE = "Something went wrong while answering your question. Please try again."
# How the evidence tiers are named in the answer's sources (docs/UI_DESIGN.md).
EVIDENCE_TIER_LABELS: dict[int, str] = {1: "ISSN position stand", 2: "Peer-reviewed review"}
UNKNOWN_TIER_LABEL = "Review"
# The label a turn's status box ends with, by the kind of result; the summary PDF uses the same
# labels for turns with no answer.
STATUS_LABELS: dict[str, str] = {
    "answer": "Answered from the research",
    # An answer that cites no label: the model said the research does not cover the question.
    "answer_uncited": "Answered without citing the research",
    "no_sources": "No matching research found",
    "rejected": "Question not accepted",
    "guardrail": "Not something this assistant can advise on",
    "error": "Something went wrong",
}
# How a source card (and the summary PDF) names a correction notice linked to a cited article.
CORRECTION_LABELS: dict[str, str] = {
    "corrected_by": "A correction to this article was published",
    "corrects": "This notice corrects",
}
# Authors named on a source card before "et al." (the full list is in ATTRIBUTION.md).
CARD_AUTHORS_SHOWN = 3
# Characters of the question shown on the sidebar's "Last answer" card before "…" (T3.2).
CARD_QUESTION_CHARS = 60
# Height of the scrolling message area in the Ask tab; tall enough to read a whole answer on a
# desktop screen (owner's requests, 2026-10-20: 520, then 650, then 750 to fill a tall window).
# On a short window the page scrolls to the chat input.
CHAT_HEIGHT_PX = 750
# Most words of the streamed answer shown per second. The real model sends its answer in fast
# bursts, which looked as if it appeared all at once (owner's request, 2026-10-20). 20 read too
# slowly in the owner's check; at 30 a 200-word answer takes about 7 s. 0 shows the text as it
# arrives.
ANSWER_WORDS_PER_SECOND = 30
# The page uses the wide layout with the content in the middle column: these are the relative
# widths of the left margin, the content and the right margin. The content takes about three
# quarters of a large screen, without lines too long to read.
PAGE_COLUMN_WEIGHTS = (1, 6, 1)

# Article XML comes only from the Europe PMC REST API, which allows automated retrieval
# (copyright policy rule 10); the PMC, Europe PMC and publisher websites are never scripted.
EUROPE_PMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
DOWNLOAD_USER_AGENT = (
    "nutrition-ai-assistant/0.1 (study project; source download; "
    "https://github.com/NMH1988/nutrition-ai-assistant)"
)
# Wait between two requests, to be polite to the API.
DOWNLOAD_PAUSE_SECONDS = 1.0
DOWNLOAD_TIMEOUT_SECONDS = 30
# The largest approved article is under 1 MB; anything far bigger is not an article.
DOWNLOAD_MAX_BYTES = 10_000_000

# Accepted profile values, in kg, cm and years (docs/ARCHITECTURE.md section 8). The app is for
# adults: ages under 18 are out of scope (docs/PRD.md). Bounds are inclusive.
PROFILE_WEIGHT_KG_RANGE = (30.0, 300.0)
PROFILE_HEIGHT_CM_RANGE = (120.0, 230.0)
PROFILE_AGE_RANGE = (18, 100)
# The units the profile form and the sidebar start in; the user can switch to imperial.
DEFAULT_UNIT_SYSTEM = "metric"
# The first line of the "Your details" dialog (T4.6). A typed number is applied when the field
# loses focus, so pressing Save right after typing keeps it (checked in the browser).
PROFILE_FORM_HINT = "Type your values, then press Save. Values are checked when you save."
# Hides Streamlit's in-field "Press Enter to apply" inside the dialog only; the hint above replaces
# it. The one exception to "no custom CSS" in docs/UI_DESIGN.md, approved by the owner (T4.6):
# Streamlit 1.66 has no option for it outside st.form, and the form is not an st.form so the units
# switch can convert typed values. A fixed string, never built from user or model text. If a later
# Streamlit renames the test id, the text comes back and nothing breaks.
# The same test id also shows a text_input's max_chars counter: a text field with max_chars added to
# this dialog would lose its counter too.
PROFILE_DIALOG_CSS = (
    '<style>[data-testid="stDialog"] [data-testid="InputInstructions"] { display: none; }</style>'
)
# The sidebar caption on where to switch light or dark mode (T7.3): Streamlit 1.66 cannot change the
# theme from the script, so users pick System, Light or Dark at the top of Streamlit's own menu
# (there is no Settings entry in 1.66).
THEME_HINT = ":material/dark_mode: Light or dark mode: menu :material/more_vert: at the top right"

# calculate_tdee (docs/ARCHITECTURE.md section 6). Values approved by the owner on 2026-10-19 (O3);
# the numbers in brackets are source IDs in docs/SOURCES.md.
# Mifflin-St Jeor resting energy in kcal/day: 10 x kg + 6.25 x cm - 5 x years, plus 5 for men or
# minus 161 for women [22].
MSJ_KCAL_PER_KG = 10.0
MSJ_KCAL_PER_CM = 6.25
MSJ_KCAL_PER_YEAR = 5.0
MSJ_SEX_CONSTANT_KCAL: dict[str, float] = {"male": 5.0, "female": -161.0}
# Physical activity level that multiplies the resting energy, by how often the user exercises:
# under once a week, 1-3, 4-5, 6-7, and more than 7 times a week with extra heavy workouts [23].
# Keys are src.profile.ActivityLevel.
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "very_active": 1.725,
    "extra_active": 1.9,
}

# calculate_macro_targets. The calorie floor: no target is ever below it, whatever the profile and
# goal (docs/PRD.md guardrails, AC-7). 1200 kcal/day is the top of the low-energy diet range
# (800-1200 kcal/day) defined in [1] and [9], so a target is never below the top of that range. The
# sources define the range; using its top as a floor is the project's choice.
CALORIE_FLOOR_KCAL = 1200
# Lose fat: a weekly weight loss of 0.5-1.0% of body weight [1], [12]; the target uses the lower,
# slower end, as slower loss better keeps lean mass [9].
FAT_LOSS_PCT_PER_WEEK_RANGE = (0.5, 1.0)
FAT_LOSS_PCT_PER_WEEK = 0.5
# Energy in a pound of pure body fat: approximately 3500 kcal [12]. [12] adds that a deficit gives
# the matching loss only in theory, if all the weight lost is fat, so it is a rough estimate.
KCAL_PER_LB_BODY_FAT = 3500
# Build muscle: about 10-20% above maintenance [11]; the target uses 10%, the lower end, which [11]
# advises advanced lifters to aim for, to limit fat gain.
MUSCLE_GAIN_SURPLUS_PCT_RANGE = (10.0, 20.0)
MUSCLE_GAIN_SURPLUS_PCT = 10.0
# Protein in g per kg of body weight per day: 1.6-2.2 [1], [11]. The top for fat loss, as [1] finds
# that 1.6-2.2 g/kg, or more in lean, resistance-trained people, can best keep lean mass in a
# lasting energy deficit; the middle for the other goals.
PROTEIN_G_PER_KG_RANGE = (1.6, 2.2)
PROTEIN_G_PER_KG: dict[str, float] = {"lose_fat": 2.2, "build_muscle": 1.9, "maintain": 1.9}
# Fat as a share of the kcal target: inside both 20-35% [11] and 15-30% for contest dieting [12],
# i.e. their overlap below.
FAT_PCT_OF_KCAL_RANGE = (20.0, 30.0)
FAT_PCT_OF_KCAL = 25.0
# Carbohydrate gets the kcal left after protein and fat [11]. Energy per gram uses the general
# Atwater factors, the same ones USDA uses for its general-factor energy (docs/ARCHITECTURE.md
# section 6): 4 kcal per g of protein and carbohydrate, 9 per g of fat.
KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_CARBOHYDRATE = 4
KCAL_PER_G_FAT = 9
# The TDEE calculate_macro_targets accepts, in kcal/day. Covers every profile within the ranges
# above (about 467 to 8270 kcal/day; tests/test_energy.py checks it), with room either side.
MACRO_TDEE_KCAL_RANGE = (400, 9000)

# USDA FoodData Central, Foundation Foods (docs/SOURCES.md #21; docs/ARCHITECTURE.md section 6).
# The CSV zip from the USDA download page goes here by hand; gitignored.
USDA_RAW_DIR = PROJECT_ROOT / "data" / "usda"
# The trimmed per-100 g table the food tool reads; committed (CC0).
USDA_FOODS_PATH = PROJECT_ROOT / "data" / "usda_foods.csv"
# The largest CSV in the 2026-04-30 zip is about 10 MB unpacked; anything far bigger is refused.
USDA_MAX_MEMBER_BYTES = 100_000_000
# The credit for the table, used in its "#" lines and in ATTRIBUTION.md. The citation follows the
# format USDA suggests on https://fdc.nal.usda.gov/; {release} is the release date (YYYY-MM-DD).
USDA_CITATION = (
    "U.S. Department of Agriculture, Agricultural Research Service, Beltsville Human Nutrition "
    "Research Center. FoodData Central: Foundation Foods, release {release}. "
    "https://fdc.nal.usda.gov/"
)
USDA_LICENSE = "CC0 1.0 Universal (public domain)"
USDA_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
USDA_CHANGES = (
    "Foundation foods only; values per 100 g: energy (kcal; Atwater specific factors where "
    "reported, else general factors), protein, carbohydrate (by difference), total fat and total "
    "dietary fiber. Foods without energy or a macronutrient are left out; a repeated name is kept "
    "once (latest publication); negative values are set to 0; an empty fiber value means not "
    "reported."
)
# The line under a food lookup's values, in the app and the summary PDF.
USDA_SOURCE_LINE = (
    "Source: USDA FoodData Central, Foundation Foods (CC0). Values per 100 g, scaled."
)
# The line under a meal plan check (T4.5), in the app and the summary PDF.
MEAL_PLAN_SOURCE_LINE = USDA_SOURCE_LINE + " Targets: the daily targets from your details."

# lookup_food_nutrition: argument limits and fuzzy name matching (rapidfuzz scores, 0-100).
# A one-letter name matches by chance ("a" scores 100 on "Eggs, Grade A, ..."), so the name, and
# its longest word once punctuation is dropped, must have at least this many characters.
FOOD_MIN_NAME_CHARS = 2
FOOD_MAX_NAME_CHARS = 100
# Grams per lookup; below 0.1 g every value rounds to zero.
FOOD_MIN_GRAMS = 0.1
FOOD_MAX_GRAMS = 2000
# A food scoring at least this is taken as the match; tried on the real table in T4.3.
FOOD_MATCH_MIN_SCORE = 80
# Foods scoring at least this are offered as alternatives or "did you mean" suggestions.
FOOD_SUGGESTION_MIN_SCORE = 60
FOOD_MAX_ALTERNATIVES = 3
# Decimal places of the scaled values (grams of nutrients); kcal are rounded to whole numbers.
FOOD_DECIMALS = 1

# evaluate_meal_plan (T4.5): foods in one day's plan, each looked up like lookup_food_nutrition.
# Bounds the lookups and the tool message's length (each food comes back with its USDA name and
# alternatives); 20 covers a day of meals and snacks.
MEAL_PLAN_MAX_ITEMS = 20

# The tool loop of the answer step (T4.4; docs/ARCHITECTURE.md, D2). A round is one model reply that
# calls tools and the running of those calls. After the last round the model is called once more
# with tool_choice "none", so it writes the answer from the results it has: at most
# MAX_TOOL_ROUNDS + 1 model calls per question, which still counts once in the rate limit.
MAX_TOOL_ROUNDS = 4
# Tool calls run from one reply; the rest are answered with TOO_MANY_TOOL_CALLS_MESSAGE. Each result
# is sent back to the model with every later call, so this bounds the tokens a turn can use.
MAX_TOOL_CALLS_PER_ROUND = 6
# evaluate_meal_plan calls run from one reply (T4.5; owner's choice after code review). A 20-food
# result is about 7,000 characters, against about 500 for a food lookup, so 6 of them in each of 4
# rounds could send about 420,000 characters (about 100k tokens) over a turn's model calls; with 1
# a round the worst case with real food names is about 95,000 (docs/SECURITY.md, "Runaway cost").
# One day's plan needs one call; the rest get TOO_MANY_MEAL_PLANS_MESSAGE.
MAX_MEAL_PLAN_CALLS_PER_ROUND = 1
# Tool messages are data for the model, in English (docs/UI_DESIGN.md, "Language"); the UI shows
# the same text. None of them repeats what the model sent, and none gives the model orders: they
# state facts, and the owner's prompt says what to do with them (it treats tool results as data).
PROFILE_NEEDED_MESSAGE = (
    "Profile needed: the user has not added their details, so this cannot be calculated. The "
    "details are added with the 'Add your details' button in the sidebar."
)
NO_ARGUMENTS_MESSAGE = (
    "Invalid call: this tool takes no arguments; the app supplies the user's profile."
)
UNKNOWN_TOOL_MESSAGE = "Invalid call: there is no tool with that name."
INVALID_TOOL_JSON_MESSAGE = "Invalid call: the arguments were not valid JSON."
TOO_MANY_TOOL_CALLS_MESSAGE = (
    f"Not run: at most {MAX_TOOL_CALLS_PER_ROUND} tool calls are run from one reply."
)
TOO_MANY_MEAL_PLANS_MESSAGE = (
    f"Not run: at most {MAX_MEAL_PLAN_CALLS_PER_ROUND} meal plan check is run from one reply."
)
TOOL_FAILED_MESSAGE = "Not available: the tool could not run, so there is no result."
# Shown in the Tool results when an energy tool had no profile, above the "Add your details" button.
PROFILE_NEEDED_HINT = "This calculation needs your details. Add them, then ask again."
# Height of the macro chart in "Tool results", its axis and legend included: at 140 px the bar was a
# hairline in the browser, at 220 px it is drawn clearly (checked with a fake model, T4.4).
MACRO_CHART_HEIGHT_PX = 220
# The donut of the energy split in the sidebar's My targets card (T4.7): its height with the legend,
# the hole for the daily kcal, and the gap between the parts (radians).
MACRO_DONUT_HEIGHT_PX = 150
MACRO_DONUT_INNER_RADIUS_PX = 46
MACRO_DONUT_PAD_ANGLE = 0.03
# The amount the Food lookup tab starts with, and its +/- step, in grams (T4.7).
FOOD_LOOKUP_DEFAULT_GRAMS = 100.0
FOOD_LOOKUP_STEP_GRAMS = 10.0
# Macro colours in charts (docs/UI_DESIGN.md), in the order the macros are listed. One palette for
# both modes: each has at least 3:1 contrast on the main and sidebar backgrounds of the light and
# the dark theme (WCAG 1.4.11; tests/test_theme.py), so they differ by hue, not lightness (T4.7).
MACRO_COLORS: dict[str, str] = {
    "Protein": "#168A6C",
    "Carbohydrate": "#7A6FD0",
    "Fat": "#B87318",
}

# The session summary PDF (T5.2; docs/ARCHITECTURE.md section 7). DejaVu Sans 2.37, committed with
# its licence in assets/fonts/: ReportLab's own fonts have no Greek letters, and an approved source
# title has "β".
PDF_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
PDF_BOLD_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
# The fonts' licence, printed word for word at the end of every PDF (owner's choice, 2026-10-20):
# its notices go with every copy, and each PDF embeds the fonts. Only the part before this heading
# is printed; the rest covers DejaVu's math font, which the app does not ship.
PDF_FONT_LICENSE_PATH = PROJECT_ROOT / "assets" / "fonts" / "LICENSE"
PDF_FONT_LICENSE_END = "TeX Gyre DJV Math"
# The sidebar button that downloads it; {date} in the file name is the day (YYYY-MM-DD).
PDF_BUTTON_LABEL = "Download summary (PDF)"
PDF_BUTTON_HELP = (
    "Your profile, targets, questions and answers with their sources, as a PDF. Built when you "
    "click; not saved on the server."
)
PDF_BUTTON_EMPTY_HELP = "Add your details or ask a question first."
PDF_FILE_NAME = "nutrition-summary-{date}.pdf"

# Token usage and cost (T5.1, Medium 5; docs/ARCHITECTURE.md section 9). Prices come from
# OpenRouter's public model lists (no key sent): the chat models are in the first, the embedding
# model only in the second. Both are read again after a day; a failed read is not kept, so the
# next turn tries again, and the turn's cost shows as "price unknown".
CHAT_PRICES_URL = f"{OPENROUTER_BASE_URL}/models"
EMBEDDING_PRICES_URL = f"{OPENROUTER_BASE_URL}/embeddings/models"
PRICE_CACHE_SECONDS = 24 * 60 * 60
# Short, as the cost is read at the end of a turn, after its answer is shown.
PRICE_TIMEOUT_SECONDS = 5
# Each list is about 1 MB today; anything far bigger is not a model list.
PRICE_MAX_BYTES = 20_000_000
# The highest price per token accepted from the lists ($10,000 per million tokens, far above any
# model the app may use); a higher one is treated as unusable, so the model's cost is unknown.
PRICE_MAX_PER_TOKEN = "0.01"
# Costs below this many dollars show as "<$0.0001" (a rewrite costs about $0.0001).
COST_SHOWN_MIN = "0.0001"
PRICE_UNKNOWN_LABEL = "price unknown"
# How the Details tab names each call of a turn; {round} counts the answer step's model calls.
USAGE_STEP_REWRITE = "Rewrite the question"
USAGE_STEP_SEARCH = "Embed the searches"
USAGE_STEP_ANSWER = "Answer, round {round}"


class MissingAPIKeyError(RuntimeError):
    """Raised when no OpenRouter API key is configured."""


class SecretsFileError(MissingAPIKeyError):
    """Raised when secrets.toml exists but cannot be parsed, and no env var is set."""


def get_api_key() -> str:
    """Return the OpenRouter key from `st.secrets`, falling back to the environment."""
    file_broken = False
    try:
        value = st.secrets.get(API_KEY_NAME)
    except FileNotFoundError as exc:
        # Streamlit raises this for a missing secrets.toml, and chains the TOML error
        # as the cause when the file exists but cannot be parsed.
        value = None
        file_broken = exc.__cause__ is not None
    secret = value.strip() if isinstance(value, str) else ""
    key = secret or os.environ.get(API_KEY_NAME, "").strip()
    if not key:
        if file_broken:
            # `from None` keeps the parser's message (it may quote file content) out of tracebacks.
            raise SecretsFileError(".streamlit/secrets.toml could not be parsed.") from None
        raise MissingAPIKeyError(f"{API_KEY_NAME} is not set.")
    return key
