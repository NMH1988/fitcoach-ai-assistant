"""The models the app may call, their settings and token budgets, prompt versions, and prices."""

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
# keeps cost and latency down without hurting them (T1.2).
REASONING_EFFORT = "low"
# Seconds one model or embedding request may take before it counts as a timeout.
LLM_TIMEOUT_SECONDS = 60
# Retries the SDK makes after a 408, 409, 429, 5xx, a timeout or a connection error; 401 and 402
# are not retried by default. With the timeout above this bounds one call, to about 7 minutes at
# worst: the SDK also honours a server's Retry-After, up to 2 minutes per retry.
LLM_MAX_RETRIES = 2

# The token budgets below are the values that worked in Sprint 1, as are the input length and the
# rate limits (src/config/limits.py).

# gpt-5 models spend reasoning tokens from this budget too, so keep it generous: a low budget can
# be used up by thinking alone and return no text (learned in Sprint 1).
DEFAULT_MAX_TOKENS = 4000
# Every request is clamped to this, whatever a caller asks for, to bound the cost of one reply.
MAX_TOKENS_CAP = 16000
# A prompt's version (T10.4): the first PROMPT_VERSION_LENGTH hex characters of the SHA-256 of the
# exact text the model receives, so a trace, a log line, a stored review and an evaluation's results
# say which prompt produced them. A hash of the content, not a number kept by hand: no edit to a
# prompt can leave it unchanged, and it needs no release step. Migration 7's CHECK on
# ai_reviews.prompt_version fixes it at 12 (a shipped migration is never edited), so a new length
# needs a new migration (tests/test_store_db.py checks the two agree).
PROMPT_VERSION_LENGTH = 12
# The version stored for a weekly review written before migration 7 recorded one.
PROMPT_VERSION_UNKNOWN = "unknown"
# Query translation's budget (T3.2): the same as the answers', as gpt-5 reasoning tokens come out of
# it too (learned in Sprint 1).
QUERY_TRANSLATION_MAX_TOKENS = DEFAULT_MAX_TOKENS
# The weekly review (T9.16, D17; src/weekly_review.py, src/agent/review.py): the model that drafts
# it (on the allowlist, built by build_chat_model()) and its token cap.
REVIEW_MODEL = DEFAULT_ANSWER_MODEL
REVIEW_MAX_TOKENS = DEFAULT_MAX_TOKENS

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
