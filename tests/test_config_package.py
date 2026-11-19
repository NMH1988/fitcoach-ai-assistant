"""Tests for the src/config package (old names, one module per name, root) and package sizes."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import paths

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = (ROOT / "src" / "config", ROOT / "src" / "i18n", ROOT / "src" / "chat")
# The most lines a module of these packages may have (T10.8, T10.10, Sprint 3 review point 4).
MAX_MODULE_LINES = 600
# The public names of the config module before T10.8 split it into a package (at 0051dba): the
# package must still give every one of them as config.<NAME>, and no other.
OLD_NAMES = frozenset(
    """
    PROJECT_ROOT APP_TITLE APP_INTRO DISCLAIMER OPENROUTER_BASE_URL ALLOWED_MODELS
    DEFAULT_ANSWER_MODEL QUERY_TRANSLATION_MODEL EMBEDDING_MODEL REASONING_EFFORT
    LLM_TIMEOUT_SECONDS LLM_MAX_RETRIES DEFAULT_MAX_TOKENS MAX_TOKENS_CAP MAX_INPUT_CHARS
    MAX_RAW_INPUT_CHARS RATE_LIMIT_PER_MINUTE RATE_LIMIT_WINDOW_SECONDS RATE_LIMIT_PER_SESSION
    LOG_LEVEL LANGSMITH_API_KEY_NAME TRACING_FLAG_NAME TRACING_ON_VALUES LANGSMITH_ENDPOINT
    LANGSMITH_PROJECT TRACING_DEMO_UNMASKED_FLAG_NAME LANGSMITH_DEMO_PROJECT TRACE_MASK
    TRACE_MASKED_KEY SOURCES_MANIFEST_PATH RAW_SOURCES_DIR ATTRIBUTION_PATH TRAINING_TOPIC TOPICS
    EVIDENCE_TIERS CHUNK_SIZE CHUNK_OVERLAP CHUNK_MIN_BODY_CHARS CHUNK_MIN_CHARS MAIN_TEXT_TITLE
    INGEST_DROPPED_SEC_TYPES INGEST_DROPPED_SEC_TITLES CHROMA_DIR CHROMA_COLLECTION
    BUILD_INDEX_COMMAND EMBEDDING_BATCH_SIZE RETRIEVAL_TOP_K RETRIEVAL_MAX_DISTANCE RRF_K
    MAX_CHUNKS_PER_SOURCE EVAL_QUESTIONS_PATH EVAL_QUESTIONS_DE_PATH EVAL_QUESTIONS_TRAINING_PATH
    EVAL_QUESTIONS_TRAINING_DE_PATH EVAL_GUARDED_QUESTION_IDS EVAL_RUNS_DIR
    EVAL_RESULTS_SCHEMA_VERSION EVAL_BASELINE_PATH EVAL_TOLERANCE EVAL_TRAINING_BASELINE_PATH
    EVAL_TRAINING_TOLERANCE EVAL_TOLERANCES_BY_QUESTIONS_FILE EVAL_GIT_TIMEOUT_SECONDS
    EVAL_JUDGE_MODEL EVAL_JUDGE_MAX_TOKENS EVAL_SCORE_METRICS EVAL_DATASET_PREFIX
    EVAL_EXPERIMENT_PREFIX EVAL_EXPERIMENT_FLUSH_SECONDS STORE_DIR STORE_PATH
    STORE_BUSY_TIMEOUT_SECONDS REVIEW_THREADS_FILE_NAME STORE_ID_MAX_CHARS STORE_TEXT_MAX_CHARS
    STORE_JSON_MAX_CHARS AUTH_SECTION ACCOUNT_SECTION USER_KEY_SECRET_NAME USER_KEY_SECRET_MIN_CHARS
    COOKIE_SECRET_MIN_CHARS USER_KEY_SECRET_PLACEHOLDER COOKIE_SECRET_PLACEHOLDER DISPLAY_NAME_CHARS
    DISPLAY_NAME_PATTERN DEMO_MODE_NAME DEMO_MODE_ON_VALUES TIME_ZONE INVITE_CODE_ALPHABET
    INVITE_CODE_LENGTH INVITE_CODE_GROUP INVITE_CODE_INPUT_MAX_CHARS INVITE_TTL_DAYS
    INVITE_MAX_ATTEMPTS DIARY_MAX_DAYS_BACK DIARY_DEFAULT_GRAMS DIARY_STEP_GRAMS TARGET_CALC_VERSION
    EXERCISES_PATH MUSCLE_GROUPS EXERCISE_NAME_MAX_CHARS WORKOUT_REPS_RANGE WORKOUT_WEIGHT_KG_RANGE
    WORKOUT_RPE_RANGE WORKOUT_RPE_STEP WORKOUT_MAX_SETS WORKOUT_DEFAULT_REPS WORKOUT_WEIGHT_STEP
    WEIGHT_TREND_WEEKS DASHBOARD_CHART_HEIGHT_PX FOLLOW_UP_MIN_LOGGED_DAYS TARGET_INPUT_MAX_KCAL
    TARGET_INPUT_MAX_GRAMS MAX_SUGGESTED_FOODS NOTIFICATIONS_MAX_SHOWN NOTIFICATIONS_MAX_TOASTS
    NOTIFICATIONS_SAME_EVENT_SECONDS TRAINING_ADVICE_WORDS ANSWER_PROMPT_PATH
    ANSWER_LANGUAGE_PROMPT_PATHS ANSWER_COACH_PROMPT_PATH PROMPT_VERSION_LENGTH
    PROMPT_VERSION_UNKNOWN QUERY_TRANSLATION_PROMPT_PATH QUERY_TRANSLATION_MAX_TOKENS QUERY_REWRITES
    QUERY_REWRITE_MAX_CHARS QUERY_MIN_YEAR_RANGE NO_SOURCES_MESSAGE NO_PROGRAM_SENTENCE
    NO_SOURCES_BLOCK MAX_SEARCHES_PER_TURN BASIS_TOOL_STATUSES SEARCH_QUERY_MAX_CHARS
    INVALID_SEARCH_QUERY_MESSAGE TOO_MANY_SEARCHES_MESSAGE API_KEY_NAME MISSING_KEY_MESSAGE
    SECRETS_FILE_MESSAGE PROMPT_MISSING_MESSAGE QUERY_PROMPT_MISSING_MESSAGE
    LANGUAGE_PROMPT_MISSING_MESSAGE COACH_PROMPT_MISSING_MESSAGE REVIEW_PROMPT_MISSING_MESSAGE
    TURN_ERROR_MESSAGE EVIDENCE_TIER_LABELS UNKNOWN_TIER_LABEL STATUS_LABELS CORRECTION_LABELS
    CARD_AUTHORS_SHOWN CARD_QUESTION_CHARS CHAT_HEIGHT_PX ANSWER_WORDS_PER_SECOND
    PAGE_COLUMN_WEIGHTS EUROPE_PMC_FULLTEXT_URL DOWNLOAD_USER_AGENT DOWNLOAD_PAUSE_SECONDS
    DOWNLOAD_TIMEOUT_SECONDS DOWNLOAD_MAX_BYTES PROFILE_WEIGHT_KG_RANGE PROFILE_HEIGHT_CM_RANGE
    PROFILE_AGE_RANGE DEFAULT_UNIT_SYSTEM DEFAULT_LANGUAGE PROFILE_FORM_HINT APP_CSS_PATH
    TITLE_GRADIENT TITLE_FALLBACK PHONE_MAX_WIDTH_PX THEME_HINT MSJ_KCAL_PER_KG MSJ_KCAL_PER_CM
    MSJ_KCAL_PER_YEAR MSJ_SEX_CONSTANT_KCAL ACTIVITY_FACTORS CALORIE_FLOOR_KCAL
    FAT_LOSS_PCT_PER_WEEK_RANGE FAT_LOSS_PCT_PER_WEEK KCAL_PER_LB_BODY_FAT
    MUSCLE_GAIN_SURPLUS_PCT_RANGE MUSCLE_GAIN_SURPLUS_PCT PROTEIN_G_PER_KG_RANGE PROTEIN_G_PER_KG
    FAT_PCT_OF_KCAL_RANGE FAT_PCT_OF_KCAL KCAL_PER_G_PROTEIN KCAL_PER_G_CARBOHYDRATE KCAL_PER_G_FAT
    MACRO_TDEE_KCAL_RANGE USDA_RAW_DIR USDA_FOODS_PATH USDA_MAX_MEMBER_BYTES USDA_CITATION
    USDA_LICENSE USDA_LICENSE_URL USDA_CHANGES USDA_SOURCE_LINE MEAL_PLAN_SOURCE_LINE
    FOOD_MIN_NAME_CHARS FOOD_MAX_NAME_CHARS FOOD_MIN_GRAMS FOOD_MAX_GRAMS FOOD_MATCH_MIN_SCORE
    FOOD_SUGGESTION_MIN_SCORE FOOD_MAX_ALTERNATIVES FOOD_DECIMALS FOOD_API_URL FOOD_API_KEY_NAME
    FOOD_API_KEY_PLACEHOLDER FOOD_API_DATA_TYPES FOOD_API_PAGE_SIZE FOOD_API_TIMEOUT_SECONDS
    FOOD_API_MAX_ATTEMPTS FOOD_API_RETRY_PAUSE_SECONDS FOOD_API_MAX_BYTES
    FOOD_API_MAX_CALLS_PER_TURN FOOD_API_MAX_WORDS FOOD_API_MAX_DIGITS
    FOOD_API_MAX_DESCRIPTION_CHARS FOOD_API_MAX_KCAL FOOD_API_MAX_GRAMS_PER_100G FOOD_API_SOURCE
    FOOD_API_NO_MATCH_SOURCE FOOD_API_SOURCE_LINE FOOD_API_CITATION FOOD_API_CHANGES
    MEAL_PLAN_MAX_ITEMS MAX_TOOL_ROUNDS MAX_TOOL_CALLS_PER_ROUND MAX_MEAL_PLAN_CALLS_PER_ROUND
    HISTORY_MAX_MESSAGES HISTORY_MAX_TOKENS PROFILE_NEEDED_MESSAGE NO_ARGUMENTS_MESSAGE
    UNKNOWN_TOOL_MESSAGE INVALID_TOOL_JSON_MESSAGE TOO_MANY_TOOL_CALLS_MESSAGE
    TOO_MANY_MEAL_PLANS_MESSAGE TOOL_FAILED_MESSAGE CLIENT_NOT_FOUND_MESSAGE
    INVALID_CLIENT_WEEK_MESSAGE PREFERENCE_MAX_CHARS MAX_PREFERENCE_PROPOSALS_PER_TURN
    MEMORY_PREFERENCES_IN_PROMPT ANSWERED_PROPOSAL PREFERENCE_PROPOSED_MESSAGE
    PREFERENCE_REFUSED_MESSAGES REVIEW_MODEL REVIEW_MAX_TOKENS REVIEW_PROMPT_PATH
    REVIEW_PROMPT_BLOCKS REVIEW_PROTEIN_GAP_SHARE REVIEW_KCAL_GAP_SHARE REVIEW_EVIDENCE_QUERIES
    REVIEW_MAX_DRAFTS REVIEW_MAX_STEPS REVIEW_SOURCE_RANGE_MIN_CHARS REVIEW_MAX_CHUNKS
    REVIEW_MAX_ITEMS REVIEW_TEXT_MAX_CHARS REVIEW_FIELD_MAX_CHARS REVIEW_TARGET_KCAL_RANGE
    REVIEW_KCAL_CHANGE_RANGE REVIEW_THREAD_MAX_CHARS REVIEW_THREAD_MAX_QUESTIONS
    REVIEW_DIAGNOSIS_PATTERNS PROGRAM_SCHEDULE_PATTERNS REVIEW_PROGRAM_PATTERNS
    REVIEW_CLIENT_VOLUME_PATTERNS REVIEW_KCAL_CHANGE_BEFORE REVIEW_KCAL_CHANGE_VERBS
    REVIEW_KCAL_CHANGE_WORDS REVIEW_KCAL_SIGNS REVIEW_KCAL_APPROXIMATE REVIEW_KCAL_CHANGE_AFTER
    PROFILE_NEEDED_HINT MACRO_CHART_HEIGHT_PX MACRO_DONUT_HEIGHT_PX MACRO_DONUT_INNER_RADIUS_PX
    MACRO_DONUT_PAD_ANGLE FOOD_LOOKUP_DEFAULT_GRAMS FOOD_LOOKUP_STEP_GRAMS MACRO_COLORS
    SIDEBAR_MACRO_COLORS PDF_FONT_PATH PDF_BOLD_FONT_PATH PDF_FONT_LICENSE_PATH PDF_FONT_LICENSE_END
    PDF_BUTTON_LABEL PDF_BUTTON_HELP PDF_BUTTON_EMPTY_HELP PDF_FILE_NAME CHAT_PRICES_URL
    EMBEDDING_PRICES_URL PRICE_CACHE_SECONDS PRICE_TIMEOUT_SECONDS PRICE_MAX_BYTES
    PRICE_MAX_PER_TOKEN COST_SHOWN_MIN PRICE_UNKNOWN_LABEL USAGE_STEP_REWRITE USAGE_STEP_SEARCH
    USAGE_STEP_ANSWER MissingAPIKeyError SecretsFileError get_api_key get_food_api_key
    secrets_file_broken auth_configured user_key_secret sign_in_ready demo_mode
    get_langsmith_api_key tracing_requested tracing_demo_unmasked
    """.split()
)


def defined_names(module_path: Path) -> list[str]:
    """Return the public names a module defines at its top level: assignments, defs, classes."""
    names = []
    for node in ast.parse(module_path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            names += [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.append(node.name)
    return [name for name in names if not name.startswith("_")]


def _config_modules() -> list[Path]:
    """Return the package's modules, its __init__ left out."""
    return sorted(p for p in (ROOT / "src" / "config").glob("*.py") if p.name != "__init__.py")


def test_the_package_defines_the_old_module_s_names_each_once():
    """The modules define exactly the old names between them, none of them in two modules."""
    defined = [name for path in _config_modules() for name in defined_names(path)]
    assert len(defined) == len(set(defined)), sorted({n for n in defined if defined.count(n) > 1})
    assert set(defined) == OLD_NAMES


def test_every_old_name_is_read_through_the_package_from_its_own_module():
    """config.<NAME> is the object its module defines, so a caller sees the one value."""
    # In a fresh interpreter: this one's conftest has patched some names on the package.
    check = (
        "import sys\n"
        "from src import config\n"
        "for module_name, names in __import__('json').loads(sys.argv[1]).items():\n"
        "    module = getattr(config, module_name)\n"
        "    wrong = [n for n in names if getattr(config, n) is not getattr(module, n)]\n"
        "    assert not wrong, wrong\n"
    )
    defined = {path.stem: defined_names(path) for path in _config_modules()}
    done = subprocess.run(
        [sys.executable, "-c", check, json.dumps(defined)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr


def test_the_init_only_gathers_the_modules():
    """The package's __init__ defines no setting of its own: it imports every module, no more."""
    init = ROOT / "src" / "config" / "__init__.py"
    assert defined_names(init) == []
    imported = {
        node.module
        for node in ast.parse(init.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ImportFrom)
    }
    assert imported == {f"src.config.{path.stem}" for path in _config_modules()}


def test_the_paths_resolve_to_the_gitignored_folders_at_the_repository_root():
    """PROJECT_ROOT is the repo root, so the store and the index sit in their gitignored folders."""
    # Read from the module: conftest points config.STORE_DIR and STORE_PATH at a temporary folder.
    assert paths.PROJECT_ROOT == ROOT
    assert paths.STORE_DIR == ROOT / "data" / "store"
    assert paths.STORE_PATH.parent == paths.STORE_DIR
    assert paths.CHROMA_DIR == ROOT / "chroma"
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/store/" in ignored
    assert "chroma/" in ignored


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_no_module_of_the_package_is_over_the_size_limit(package):
    """Every module of src/config, src/i18n and src/chat has at most MAX_MODULE_LINES lines."""
    modules = sorted(package.glob("*.py"))
    assert len(modules) > 1
    sizes = {path.name: len(path.read_text(encoding="utf-8").splitlines()) for path in modules}
    assert {name: size for name, size in sizes.items() if size > MAX_MODULE_LINES} == {}


def _called_inside_environment() -> set[str]:
    """Return the public functions of config.environment that another of its functions calls."""
    tree = ast.parse((ROOT / "src" / "config" / "environment.py").read_text(encoding="utf-8"))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    called = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                    called.add(inner.func.id)
    return {name for name in called & functions if not name.startswith("_")}


def test_tests_patch_the_environment_s_inner_calls_through_patch_config():
    """No test patches only the package for a function config.environment calls internally."""
    # Such a patch would miss the caller inside the module (e.g. tracing_demo_unmasked() calling
    # demo_mode()), so a test could pass whatever the gate does; tests.fakes.patch_config() sets
    # both.
    called = _called_inside_environment()
    assert {"demo_mode", "tracing_requested"} <= called
    found = [
        f"{path.name}:{call.lineno}"
        for path in sorted((ROOT / "tests").glob("*.py"))
        if path.name != "fakes.py"
        for call in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if _patches_only_the_package(call, called)
    ]
    assert found == []


def _patches_only_the_package(node: ast.AST, names: set[str]) -> bool:
    """Return True for setattr(config, "<name>", ...) or setattr("src.config.<name>", ...)."""
    if not (isinstance(node, ast.Call) and node.args):
        return False
    func = node.func
    if not (getattr(func, "attr", None) == "setattr" or getattr(func, "id", None) == "setattr"):
        return False
    first = node.args[0]
    if isinstance(first, ast.Name) and first.id == "config" and len(node.args) > 1:
        second = node.args[1]
        return isinstance(second, ast.Constant) and second.value in names
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value in {f"src.config.{name}" for name in names}
    return False
