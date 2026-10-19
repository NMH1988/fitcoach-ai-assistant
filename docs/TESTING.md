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

How to run the T2.3 check (O5): after `python scripts/download_sources.py`, from the repo root with the key set up, `python scripts/build_index.py` (or `.venv\Scripts\python.exe scripts/build_index.py`). It prints its progress per batch and then the chunk, source and character counts (never the key). Stop the app first if it is running (it keeps the old collection open) and restart it afterwards. Read the cost of the run from the OpenRouter activity page (langchain does not return the token use of embeddings); its chart shows only daily totals, so if the run's requests cannot be told apart, estimate the cost from the printed character count (about 4 characters per token) and say it is an estimate. Record both here.

How to run the T3.1 check (O5): after the index is built, from the repo root with the key set up, `python scripts/live_check_retrieval.py "<question>" "<question>" ...` (or `.venv\Scripts\python.exe scripts/live_check_retrieval.py ...`). Give a few questions the sources cover and a few they do not; it prints the 6 nearest chunks of each with their cosine distance and whether they pass `RETRIEVAL_MAX_DISTANCE`. Choose a limit between the two groups, set it in `src/config.py`, and record the questions, distances and chosen value here. Then ask one real question in the app (`streamlit run app.py`) and record whether the answer cites `[S#]` labels and lists their sources.

| Date | Ticket | What was checked | Result |
|---|---|---|---|
| 2026-10-19 | T2.3 (O5) | Real index build: `.venv/Scripts/python.exe scripts/build_index.py`, run by the owner (`qwen/qwen3-embedding-8b` through OpenRouter, batches of 64), then the index read back by Claude with no API call | Exit code 0: 1,810 chunks from 21 sources (1,375,759 characters) embedded in 29 batches into `chroma/` (46 MB, gitignored: `git check-ignore` confirms). Read back: `check_index()` gives 1,810; one collection, `nutrition-sources` (no staging collection left), cosine distance, `embedding_model` metadata set; 1,810 unique IDs; 4,096-dimension vectors; 21 sources; the filter `topics $contains protein` returns 933 chunks; #18a carries `corrects: 18` and #18 `corrected_by: [18a]`. Cost (an estimate, not a billed figure): about $0.003 (range $0.0031-0.0039), from 1,375,759 characters at 3.5-4.5 characters per token (about 306,000-393,000 tokens) and the listed price of $0.01 per million tokens (2026-10-19). The exact cost was not read: the OpenRouter activity chart shows daily totals only, and its 2026-10-19 point, which also holds the T1.2 live check, is barely above $0, well under $0.01. |
| 2026-10-19 | T4.3 | `python scripts/prepare_usda.py` on the Foundation Foods CSV zip, release 2026-04-30 (3.8 MB, downloaded once by Claude from the USDA download page with the owner's approval), then `lookup_food_nutrition` on about 40 everyday food names | 469 foundation foods read: 92 left out without energy or a macronutrient (among them olive, canola and the other cooking oils except coconut, butter, dry pasta, lunchmeats, dried beans and most foods added in 2026, which have no values in this release), 49 repeated names merged, 328 written. Found as expected: chicken breast, milk, skim milk, rolled oats, white and brown rice, banana, Greek yogurt, salmon, tuna, sweet potato, peanut butter, ground beef, cottage cheese, almonds, whole egg, egg white, apple, broccoli, spinach, lentils, avocado. Weak or missing: a bare name returns one variant chosen by the tie-breakers, not by nutrition: "egg" gives a raw yolk first (whole egg is an alternative), "chicken" a wing with skin (173 kcal per 100 g; breast is an alternative), "rice" black rice; a lone filler word is matched too: "of" gives eye of round roast, "in" canned tuna, "with" apricot, "raw" beets (one-letter names such as "a" or "a." are refused); "olive oil" matches anchovies in olive oil and "butter" almond butter (oils and butter have no values), "raisins" and "oatmeal" match oatmeal cookies with raisins, "pasta" matches pasta sauce, "quinoa" quinoa flour; whey, tofu and pizza are not found; "chicken brest" is not found but suggests the chicken breasts. |
| 2026-10-19 | T2.2 | `load_chunks()` on the 21 downloaded articles in `data/raw/`, run by Claude (no network, no API call) | All 21 accepted by the licence check and parsed: 1,810 chunks, 1.38 M characters, longest 1,000, mean 760, shortest 64; per source from 22 (#18a) to 183 (#2). Of 1,318 neighbouring chunk pairs in the same section, 676 share text (overlap up to 150); the other 642 are cut at a paragraph break, where the splitter carries nothing over and no sentence is cut. Formulas and exponents read as in the articles (`I^2`, `τ^2`, `P(>0)=`, `R̂`, `N(0, 100^2)`, `kg^−1`); no line break is left inside a sentence. The kept top-level section titles were read through by hand: no acknowledgements, funding, disclosure, publisher's note, supplementary or reference section is left (a results section of #17 about the funding of the reviewed studies is content and stays). One plain-text citation without markup is left (`[189–192,194]` in #3). #18 carries `corrected_by: ["18a"]` and #18a `corrects: "18"`. |
| 2026-10-19 | T2.1 | Real run of `python scripts/download_sources.py` (Europe PMC REST API, 1 s pause), run by Claude with the owner's approval | Exit code 0; all 21 articles saved to `data/raw/` (5.6 MB, 48 s), #1 included as PMC13665703; none refused. `git status` shows nothing under `data/raw/` (gitignored). |
| 2026-10-19 | T1.2 (O5) | One real chat call (`openai/gpt-5-mini`, reasoning effort `low`, `max_tokens` 4000) and one real embedding call (`qwen/qwen3-embedding-8b`, raw text) through OpenRouter, run by the owner | Both succeeded. Chat: 138-character reply, 16 input / 86 output tokens, 94 reasoning tokens reported. Embedding: 4096 dimensions. OpenRouter accepted `max_completion_tokens`, `reasoning_effort` and raw-text embedding input. |

Notes on the T1.2 run: the reported reasoning tokens (94) are more than the output tokens (86), so OpenRouter's `completion_tokens` may not include reasoning; T5.1 must check how reasoning tokens are billed before computing cost. The reply was far below `max_tokens`, so this run does not show that the cap is enforced, only that the parameter is accepted.
