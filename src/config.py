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

# Model requests allowed per browser session: at most this many in any rolling window, and this
# many in all. Reloading the page starts a new session.
RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_PER_SESSION = 50

# USDA FoodData Central, Foundation Foods (docs/SOURCES.md #21; docs/ARCHITECTURE.md section 6).
# The CSV zip from the USDA download page goes here by hand; gitignored.
USDA_RAW_DIR = PROJECT_ROOT / "data" / "usda"
# The trimmed per-100 g table the food tool reads; committed (CC0).
USDA_FOODS_PATH = PROJECT_ROOT / "data" / "usda_foods.csv"
# The largest CSV in the 2026-04-30 zip is about 10 MB unpacked; anything far bigger is refused.
USDA_MAX_MEMBER_BYTES = 100_000_000

# lookup_food_nutrition: argument limits and fuzzy name matching (rapidfuzz scores, 0-100).
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

API_KEY_NAME = "OPENROUTER_API_KEY"


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
