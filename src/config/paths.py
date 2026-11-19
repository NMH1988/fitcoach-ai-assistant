"""Where the app's files are: the repository root, data, prompts, the index, the store, assets."""

from pathlib import Path

# The repository's root: this file is src/config/paths.py.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Knowledge base sources (docs/SOURCES.md; docs/ARCHITECTURE.md section 4).
SOURCES_MANIFEST_PATH = PROJECT_ROOT / "data" / "sources.json"
# Downloaded article XML; gitignored (copyright policy rule 8).
RAW_SOURCES_DIR = PROJECT_ROOT / "data" / "raw"
ATTRIBUTION_PATH = PROJECT_ROOT / "ATTRIBUTION.md"

# The vector index (docs/ARCHITECTURE.md section 4): a persistent Chroma collection, embedded in the
# app's process only (never a server; .claude/rules/security-privacy.md). Gitignored and rebuilt by
# BUILD_INDEX_COMMAND (D7).
CHROMA_DIR = PROJECT_ROOT / "chroma"
# The owner's evaluation questions (O2), each with the sources it should find; read by
# scripts/compare_retrieval.py (T3.3) and the evaluation run (T6.1).
EVAL_QUESTIONS_PATH = PROJECT_ROOT / "data" / "eval_questions.json"
# The owner's German evaluation questions (O2, for T7.2), kept apart: compare_retrieval.py searches
# each question as written, with no rewrite into English, so German ones would lower the T3.6 rates.
EVAL_QUESTIONS_DE_PATH = PROJECT_ROOT / "data" / "eval_questions_de.json"
# The owner's training evaluation questions (O17, T9.19), in their own files so the nutrition rates
# can still be compared with the nutrition baseline alone; run them with the file as an argument.
EVAL_QUESTIONS_TRAINING_PATH = PROJECT_ROOT / "data" / "eval_questions_training.json"
EVAL_QUESTIONS_TRAINING_DE_PATH = PROJECT_ROOT / "data" / "eval_questions_training_de.json"
# Where scripts/run_evaluation.py (T6.1) writes its full reports: the answers and the article text
# of the chunks found, for judging the citations. Gitignored: never committed.
EVAL_RUNS_DIR = PROJECT_ROOT / "data" / "eval_runs"
# The committed results of the owner's baseline run (`--repeat 3` on main, T8.4), which
# scripts/check_eval_baseline.py compares a later run with.
EVAL_BASELINE_PATH = PROJECT_ROOT / "data" / "eval_baseline.json"
# The training questions' baseline (T9.20, taking over T9.19's deferred part): an owner's run of
# `data/eval_questions_training.json` with `--repeat 3`, compared with `--baseline`.
EVAL_TRAINING_BASELINE_PATH = PROJECT_ROOT / "data" / "eval_baseline_training.json"

# The store of signed-in users' data (T9.6, D13): one SQLite file in a gitignored folder, local.
# Not encrypted: anyone who can read the file reads the data (docs/SECURITY.md).
STORE_DIR = PROJECT_ROOT / "data" / "store"
STORE_PATH = STORE_DIR / "fitcoach.sqlite3"
# The weekly review workflow's checkpointer (T9.16, D12): a SqliteSaver file next to the store file
# (so in the same gitignored folder, and next to the demo's temporary store in demo mode). It holds
# a review's metrics, evidence and draft only while the run waits for the coach.
REVIEW_THREADS_FILE_NAME = "review_threads.sqlite3"
# The workout log's exercise list we wrote (T9.14), each exercise in one of MUSCLE_GROUPS.
EXERCISES_PATH = PROJECT_ROOT / "data" / "exercises.json"
# The answer system prompt, written by the owner (O1; .claude/rules/workflow.md).
ANSWER_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "answer_system.md"
# The language part of the answer prompt, one file per UI language, written by the owner (O1, T7.2).
# The code joins the chosen language's file to the end of the answer prompt: the language comes from
# the app's language control (en or de), never from the user's text.
ANSWER_LANGUAGE_PROMPT_PATHS = {
    "en": PROJECT_ROOT / "src" / "prompts" / "answer_language_en.md",
    "de": PROJECT_ROOT / "src" / "prompts" / "answer_language_de.md",
}
# The coach's part of the answer prompt (T9.7), written by the owner (O8): when to propose saving a
# preference and how to use <memories>. Joined after the language part in a coach's chat only, so a
# guest's prompt never names the tool.
ANSWER_COACH_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "answer_coach.md"
# The query translation system prompt (T3.2), written by the owner (O7).
QUERY_TRANSLATION_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "query_translation_system.md"
# The app's own stylesheet (T9.23; docs/UI_DESIGN.md, "The custom CSS layer"): layout, spacing and
# visibility rules only, loaded once per run with st.html, which wraps a .css file in <style> and
# sends it to the event container, so it takes no space. A Path built from PROJECT_ROOT: st.html
# reads a relative path from the working directory. Since T9.23 it holds the dialog's rule that hid
# "Press Enter to apply" (T4.6), which until then was its own fixed string.
APP_CSS_PATH = PROJECT_ROOT / "assets" / "app.css"

# USDA FoodData Central, Foundation Foods (docs/SOURCES.md #21; docs/ARCHITECTURE.md section 6).
# The CSV zip from the USDA download page goes here by hand; gitignored.
USDA_RAW_DIR = PROJECT_ROOT / "data" / "usda"
# The trimmed per-100 g table the food tool reads; committed (CC0).
USDA_FOODS_PATH = PROJECT_ROOT / "data" / "usda_foods.csv"
# The weekly review's system prompt (T9.16), written by the owner (O15).
REVIEW_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "weekly_review_system.md"

# The session summary PDF (T5.2; docs/ARCHITECTURE.md section 7). DejaVu Sans 2.37, committed with
# its licence in assets/fonts/: ReportLab's own fonts have no Greek letters, and an approved source
# title has "β".
PDF_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
PDF_BOLD_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
# The fonts' licence, printed word for word at the end of every PDF (T5.2): its notices go with
# every copy, and each PDF embeds the fonts. Only the part before this heading is printed; the rest
# covers DejaVu's math font, which the app does not ship.
PDF_FONT_LICENSE_PATH = PROJECT_ROOT / "assets" / "fonts" / "LICENSE"
PDF_FONT_LICENSE_END = "TeX Gyre DJV Math"
