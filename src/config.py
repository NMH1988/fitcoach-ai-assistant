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
# characters, its section title included; neighbouring chunks of a section share CHUNK_OVERLAP.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
# Room always left for the text after a very long section title, so the splitter still works;
# such a chunk may then be longer than CHUNK_SIZE (no approved article comes close). Must stay above
# CHUNK_OVERLAP, or the splitter raises ValueError.
CHUNK_MIN_BODY_CHARS = 400
# Section title for paragraphs that sit directly in the body, outside any section (e.g. #18a).
MAIN_TEXT_TITLE = "Main text"
# Back matter that many articles put inside <body>: dropped, as it is not nutrition content (owner's
# choice in T2.2). Matched on the section's sec-type, or on its title in lower case with numbering
# and punctuation removed; a title starting with "appendix" is dropped too.
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
# T3.2 and T3.3). The nearest chunks given to the answer model, labelled [S1]...[S6].
RETRIEVAL_TOP_K = 6
# Cosine distance (0 = same meaning, up to 2) above which a chunk counts as not relevant to the
# question. Measured on the real index (O5, 2026-10-20, 28 questions; docs/TESTING.md): questions
# the sources cover, short or long, had their nearest chunk at 0.28-0.54; unrelated ones at 0.70
# and above; near-domain ones (a dog's diet, running shoes, insulin) at 0.56-0.70. 0.62 sits midway
# and favours answering: a near-domain question that passes costs one model call, which the
# prompt declines or redirects, while a covered question that is blocked gets no answer at all.
RETRIEVAL_MAX_DISTANCE = 0.62
# The answer system prompt, written by the owner (O1; .claude/rules/workflow.md).
ANSWER_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "answer_system.md"
# Shown instead of an answer when no chunk is relevant; no model call is made (AC-2).
NO_SOURCES_MESSAGE = (
    "Our sources do not cover this question, so there is no answer from the research. Try a "
    "question about protein, carbohydrate, fat, energy balance, nutrient timing or supplements "
    "for strength training."
)
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
# How the evidence tiers are named in the answer's sources (docs/UI_DESIGN.md).
EVIDENCE_TIER_LABELS: dict[int, str] = {1: "ISSN position stand", 2: "Peer-reviewed review"}
UNKNOWN_TIER_LABEL = "Review"
# Authors named on a source card before "et al." (the full list is in ATTRIBUTION.md).
CARD_AUTHORS_SHOWN = 3
# Height of the scrolling message area in the Ask tab, so the chat input stays in view; tall
# enough to read a whole answer on a desktop screen (owner's request, 2026-10-20).
CHAT_HEIGHT_PX = 650
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
