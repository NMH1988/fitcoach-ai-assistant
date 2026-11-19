"""Lengths, ranges and counts the app enforces, the calorie floor and the tool loop's limits."""

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

# The store of signed-in users' data (T9.6, D13; the file is STORE_PATH). How long a write waits
# for another session's write to finish before it fails.
STORE_BUSY_TIMEOUT_SECONDS = 5
# Longest user ID the store accepts (T9.5's keyed hash is 64 hex characters).
STORE_ID_MAX_CHARS = 128
# Longest text the store accepts in any text field (a display name, a preference, a review's JSON
# is longer and checked by STORE_JSON_MAX_CHARS); T9.5 and T9.7 set tighter limits for their input.
STORE_TEXT_MAX_CHARS = 500
STORE_JSON_MAX_CHARS = 100_000
# The display name a user picks at the first sign-in: letters, digits, spaces, dots, hyphens and
# apostrophes, starting with a letter or digit, 2 to 40 characters after cleaning. It is shown on
# screen only and never sent to a model (docs/PRD.md, Sprint 3 guardrails).
DISPLAY_NAME_CHARS = (2, 40)
DISPLAY_NAME_PATTERN = r"[^\W_][\w .'\-]*"
# Invitations (T9.12, D15): a coach's single-use code, passed on by hand. It is drawn with the
# secrets module from 32 characters that are hard to mix up (no 0, O, 1 or I), so 12 of them give
# 60 bits; the store keeps only its SHA-256 hash. It is shown in groups of INVITE_CODE_GROUP with a
# hyphen; a gymer may type it with or without the hyphens and spaces, in either case.
INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 12
INVITE_CODE_GROUP = 4
# The longest text the code field takes (the code with its hyphens, and some spaces).
INVITE_CODE_INPUT_MAX_CHARS = 24
INVITE_TTL_DAYS = 7
# Codes a gymer may try per day (Berlin), counted in the store, so a reload does not reset them;
# every try counts, a valid one too.
INVITE_MAX_ATTEMPTS = 5
# The food and weight diary (T9.13): a gymer logs today or up to this many days back, never a
# future day (owner's choice, 2026-11-03); a food's grams keep FOOD_MIN_GRAMS to FOOD_MAX_GRAMS.
DIARY_MAX_DAYS_BACK = 30
DIARY_DEFAULT_GRAMS = 100.0
DIARY_STEP_GRAMS = 10.0
# The coach assistant (T9.17). A client is flagged for follow-up in the client list (and in
# list_my_clients) with fewer logged days than this in the week, or no workout when they share
# training. The coach's target form: the largest values its fields take (a typing guard for the
# form only; the store keeps the calorie floor, CALORIE_FLOOR_KCAL, whoever sets a target).
FOLLOW_UP_MIN_LOGGED_DAYS = 4
TARGET_INPUT_MAX_KCAL = 10000
TARGET_INPUT_MAX_GRAMS = 1000
# The foods a coach suggests to a client (T9.34): at most this many items in one list, each with
# grams in the food log's range (FOOD_MIN_GRAMS to FOOD_MAX_GRAMS) and a food at most once per
# meal slot; the store checks them all (owner's choice, 2026-11-12).
MAX_SUGGESTED_FOODS = 20
# In-app notifications (T9.29, D23): the Notifications page lists at most this many, newest first,
# and at most NOTIFICATIONS_MAX_TOASTS show as toasts in one run (the rest as one "and N more"
# toast). A scope granted within NOTIFICATIONS_SAME_EVENT_SECONDS after a code was accepted counts
# as shared at the start (the store writes the two times apart, so they can be a second apart).
NOTIFICATIONS_MAX_SHOWN = 50
NOTIFICATIONS_MAX_TOASTS = 3
NOTIFICATIONS_SAME_EVENT_SECONDS = 5
# The agent's knowledge base search (T9.3, D10): the most searches one turn runs (each costs a
# query translation call and an embedding call, and adds up to RETRIEVAL_TOP_K chunks to every later
# model call), and the longest query the model may write (the question's own limit is the guard's).
MAX_SEARCHES_PER_TURN = 2
SEARCH_QUERY_MAX_CHARS = 500

# Accepted profile values, in kg, cm and years (docs/ARCHITECTURE.md section 8). The app is for
# adults: ages under 18 are out of scope (docs/PRD.md). Bounds are inclusive.
PROFILE_WEIGHT_KG_RANGE = (30.0, 300.0)
PROFILE_HEIGHT_CM_RANGE = (120.0, 230.0)
PROFILE_AGE_RANGE = (18, 100)

# The calorie floor (calculate_macro_targets, the store and the weekly review): no target is ever
# below it, whatever the profile and goal (docs/PRD.md guardrails, AC-7). 1200 kcal/day is the top
# of the low-energy diet range (800-1200 kcal/day) defined in [1] and [9], so a target is never
# below the top of that range. The sources define the range; using its top as a floor is the
# project's choice.
CALORIE_FLOOR_KCAL = 1200

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

# The chat's short-term memory (T9.4, D12): the thread keeps each answered turn's question and
# answer only (owner's choice, 2026-10-30), in memory for the browser session. The thread holds at
# most HISTORY_MAX_MESSAGES of them (a question and its answer are two), the oldest removed first
# (what is stored); the model gets the latest of them that fit HISTORY_MAX_TOKENS, counted
# approximately without a network call (what the model sees). Both bound the cost: each earlier
# message is sent again with every model call of a turn. Kept after the owner's live check (O13,
# 2026-10-30): a meal plan exchange, the longest answer measured, is an estimated 450-500 tokens of
# history a call, so 2000 holds the last three or four such exchanges, more of shorter ones
# (docs/TESTING.md, "Conversation memory").
HISTORY_MAX_MESSAGES = 20
HISTORY_MAX_TOKENS = 2000
# The coach's long-term memory (T9.7, D12): `remember_preference`, offered only in a coach's chat,
# proposes one of the coach's own working preferences; it is saved only when the coach approves it
# on the card. The longest text a preference may have, the most proposals per turn, and how many
# of the newest saved preferences reach the model (in <memories>, before the question).
PREFERENCE_MAX_CHARS = 200
MAX_PREFERENCE_PROPOSALS_PER_TURN = 1
MEMORY_PREFERENCES_IN_PROMPT = 20
