# Testing

How the project is tested, and where evaluation results and live checks are recorded. The short rules for writing tests are in `.claude/rules/testing.md`.

## Test levels

| Level | What | How |
|---|---|---|
| Unit | Pure logic: TDEE and macro calculators, calorie floor, unit conversion, profile validation, input guard, JATS parsing and chunking, metadata filters, RRF, citation formatting, token cost, PDF content | pytest; known-answer tests (e.g. TDEE for a fixed profile), conversions tested both ways, RRF on a hand-computed example |
| Integration | The pipeline end to end without the network: ingest -> Chroma -> query translation -> hybrid retrieval -> answer step with tools | `DeterministicFakeEmbedding` (langchain-core); Chroma in-memory or in a temp dir; a scripted fake chat model that returns fixed rewrites, tool calls and answers |
| UI | Visible behaviour of `app.py`: chat, sources, tool results, progress, settings, profile form, PDF button, error messages | `streamlit.testing.v1.AppTest` with the pipeline faked. This is our end-to-end level |
| Live (manual) | Real models and the real index | Run by the owner; results recorded below, never in CI |

Browser end-to-end tests (e.g. Playwright) are not planned: AppTest covers the UI logic, and the deadline is short.

## Rules

- No real network in tests: OpenRouter, embeddings and USDA are always faked. The suite passes with no API key; test keys are obvious fakes like `sk-test-not-a-real-key`.
- Every ticket's acceptance criteria map to tests or to named manual checks listed in the PR.
- Guard tests use attack strings and benign strings, so both missed attacks and false positives are caught.
- Test fixtures use only approved sources or text we wrote ourselves.

## CI

`.github/workflows/ci.yml` (added in the setup ticket, as in Sprint 1) runs on every push to `main` and every PR: `ruff check .`, `ruff format --check .`, `pytest` with coverage, and `pip-audit`.

## Evaluation

- **System prompt and answers:** the owner drafts the evaluation questions; results go here.
- **Retrieval:** a small set of questions with the source each should find, comparing vector-only, keyword-only and hybrid retrieval. This checks the hybrid search (Hard 1); it is not the full RAG evaluation (Hard 7).

No evaluation has been run yet.

## Live checks

Record only what was actually run and observed: date, model, what was checked, result.

How to run the T1.2 check (O5): from the repo root, with the key set up as in the README, `python scripts/live_check_llm.py` (on Windows without an activated venv: `.venv\Scripts\python.exe scripts/live_check_llm.py`). It prints the model, reply length, token use and embedding size (never the key), or the mapped error.

| Date | Ticket | What was checked | Result |
|---|---|---|---|
| 2026-10-19 | T4.3 | `python scripts/prepare_usda.py` on the Foundation Foods CSV zip, release 2026-04-30 (3.8 MB, downloaded once by Claude from the USDA download page with the owner's approval), then `lookup_food_nutrition` on about 40 everyday food names | 469 foundation foods read: 92 left out without energy or a macronutrient (among them olive, canola and the other cooking oils except coconut, butter, dry pasta, lunchmeats, dried beans and most foods added in 2026, which have no values in this release), 49 repeated names merged, 328 written. Found as expected: chicken breast, milk, skim milk, rolled oats, white and brown rice, banana, Greek yogurt, salmon, tuna, sweet potato, peanut butter, ground beef, cottage cheese, almonds, whole egg, egg white, apple, broccoli, spinach, lentils, avocado. Weak or missing: a bare name returns one variant chosen by the tie-breakers, not by nutrition: "egg" gives a raw yolk first (whole egg is an alternative), "chicken" a wing with skin (173 kcal per 100 g; breast is an alternative), "rice" black rice; "olive oil" matches anchovies in olive oil and "butter" almond butter (oils and butter have no values), "raisins" and "oatmeal" match oatmeal cookies with raisins, "pasta" matches pasta sauce, "quinoa" quinoa flour; whey, tofu and pizza are not found; "chicken brest" is not found but suggests the chicken breasts. |
| 2026-10-19 | T2.1 | Real run of `python scripts/download_sources.py` (Europe PMC REST API, 1 s pause), run by Claude with the owner's approval | Exit code 0; all 21 articles saved to `data/raw/` (5.6 MB, 48 s), #1 included as PMC13665703; none refused. `git status` shows nothing under `data/raw/` (gitignored). |
| 2026-10-19 | T1.2 (O5) | One real chat call (`openai/gpt-5-mini`, reasoning effort `low`, `max_tokens` 4000) and one real embedding call (`qwen/qwen3-embedding-8b`, raw text) through OpenRouter, run by the owner | Both succeeded. Chat: 138-character reply, 16 input / 86 output tokens, 94 reasoning tokens reported. Embedding: 4096 dimensions. OpenRouter accepted `max_completion_tokens`, `reasoning_effort` and raw-text embedding input. |

Notes on the T1.2 run: the reported reasoning tokens (94) are more than the output tokens (86), so OpenRouter's `completion_tokens` may not include reasoning; T5.1 must check how reasoning tokens are billed before computing cost. The reply was far below `max_tokens`, so this run does not show that the cap is enforced, only that the parameter is accepted.
