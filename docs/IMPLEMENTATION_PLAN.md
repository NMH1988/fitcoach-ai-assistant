# Implementation plan

Epics, tickets, acceptance criteria, dependencies, order and status. This file is the record of the work that travels with the repo to the course repository (GitHub issues and PRs do not), so keep each ticket's status current: every PR updates the status of its ticket.

**Status of this plan:** approved by the owner on 2026-10-19; GitHub issues #1-#20 created the same day (one per ticket). It follows `docs/PRD.md` (acceptance criteria AC-1 to AC-15) and `docs/ARCHITECTURE.md` (decisions D1-D8).

## Status legend

`todo` · `in progress` · `in review` · `done` · `dropped` (with the reason)

## Ticket format

```
### T<epic>.<n> <title> (S/M/L) · status: todo · issue #<n>
**Serves:** <brief requirement or optional task> | beyond the brief (owner's request)
**Depends on:** T<x.y>, O<n>, ...
**Acceptance criteria**
- [ ] <testable criterion> - verified by <test or manual check>
**Notes:** files, risks
```

Sizes: S = up to half a day, M = about a day, L = more than a day.

## Owner tasks

The owner writes these first; Claude reviews (`.claude/rules/workflow.md`).

| ID | Task | Needed by | Status |
|---|---|---|---|
| O1 | Draft the answer system prompt (role, scope, citations `[S#]`, guardrails, "sources are data") | T3.1 | todo |
| O2 | Draft the evaluation questions (about 10-15), each with the source(s) it should find and what a good answer contains | T3.3, T6.1 | todo |
| O3 | Approve the calorie floor and the macro ranges; Claude proposes them with the exact source passages | T4.2 | todo |
| O4 | If Europe PMC still has no copy of source #1, save its XML or PDF by hand from the publisher page into `data/raw/` | T2.1 | done: not needed (Europe PMC has #1 as PMC13665703, found in T2.1 on 2026-10-19) |
| O5 | Live checks with the real key: T1.2 (one chat and one embedding call), T2.3 (real index build), T6.1 (evaluation run) | T1.2, T2.3, T6.1 | in progress (T1.2 done 2026-10-19) |
| O6 | Get the course repository URL and confirm how the reviewers read it (files only, or through PRs) | T6.2 | todo |

## Overview and order

Deadline: **2026-11-02**. Target dates leave 1-2 days of buffer.

| Ticket | Issue | Title | Size | Depends on | Target | Status |
|---|---|---|---|---|---|---|
| T1.1 | #1 | Project skeleton, config and CI | S | - | 10-20 | done |
| T1.2 | #2 | OpenRouter clients and error mapping | S | T1.1 | 10-20 | in review |
| T1.3 | #3 | Input guard and rate limit | S | T1.1 | 10-21 | todo |
| T2.1 | #4 | Source manifest, download script, attribution | M | T1.1, O4 | 10-21 | in review |
| T2.2 | #5 | Parse article XML and chunk with metadata | M | T2.1 | 10-22 | todo |
| T2.3 | #6 | Build and open the Chroma index | S | T1.2, T2.2 | 10-23 | todo |
| T4.1 | #11 | Profile, units and settings | M | T1.1 | 10-23 | todo |
| T4.3 | #13 | USDA food table and lookup | M | T1.1 | 10-23 | todo |
| T3.1 | #7 | First answer with sources (vector search) | M | T1.2, T1.3, T2.3, O1 | 10-24 | todo |
| T4.2 | #12 | Energy and macro tools with the calorie floor | M | T4.1, O3 | 10-25 | todo |
| T3.2 | #8 | Query translation and structured filters | M | T3.1 | 10-26 | todo |
| T3.3 | #9 | Hybrid search (BM25 + RRF) | M | T3.2, O2 | 10-27 | todo |
| T3.4 | #10 | Prompt injection hardening | S | T3.1 | 10-27 | todo |
| T4.4 | #14 | Tool-calling loop and tool results UI | M | T3.1, T4.2, T4.3 | 10-28 | todo |
| T5.1 | #16 | Token usage and cost | S | T3.2 | 10-29 | todo |
| T5.3 | #18 | Domain guardrails | S | T3.1, T4.2 | 10-29 | todo |
| T5.2 | #17 | Session summary PDF | M | T4.4 | 10-30 | todo |
| T6.1 | #19 | Evaluation run and reflection | S | T3.3, T4.4, O2, O5 | 10-31 | todo |
| T6.2 | #20 | README, final checks and transfer to the course repo | S | all, O6 | 11-01 | todo |
| T4.5 | #15 | `evaluate_meal_plan` tool (stretch) | S | T4.4 | only if ahead | todo |

**Critical path:** T1.1 -> T1.2 -> T2.1 -> T2.2 -> T2.3 -> T3.1 -> T3.2 -> T3.3 -> T6.1 -> T6.2. T1.3, T4.1 and T4.3 can run alongside it.

**If time runs short, cut in this order:** T4.5, PDF styling (keep plain text layout), chart polish. The core requirements and the chosen optional tasks (Medium 3, 5, 6; Hard 1) stay.

---

## Epic 1: Foundation

### T1.1 Project skeleton, config and CI (S) · status: done · issue #1
**Serves:** core 4 (technical base); CI as in Sprint 1.
**Depends on:** -
**Acceptance criteria**
- [x] `pyproject.toml` pins the runtime packages from `docs/ARCHITECTURE.md` section 12 and the dev tools (pytest, pytest-cov, ruff, pip-audit); `.python-version` is 3.14; `pip install -e ".[dev]"` works on a clean venv - verified by CI install step.
- [x] `streamlit run app.py` shows the app title and the "not medical advice" disclaimer - verified by an AppTest smoke test.
- [x] `src/config.py` holds the model allowlist, default models (answer `openai/gpt-5-mini`, query translation `openai/gpt-5-nano`), limits and `get_api_key()`, which reads `st.secrets` or `OPENROUTER_API_KEY` and returns a clear "missing key" error without printing the key - verified by unit tests with a fake key and with no key.
- [x] `.github/workflows/ci.yml` runs `ruff check .`, `ruff format --check .`, `pytest` with coverage and `pip-audit` on push to `main` and on PRs, with no API key - verified by a green CI run.
- [x] `CLAUDE.md` "Commands" lists the real commands.
**Notes:** check every new package's licence (`.claude/rules/copyright.md` rule 9). Add `dependabot.yml` as in Sprint 1.

### T1.2 OpenRouter clients and error mapping (S) · status: in review · issue #2
**Serves:** core 4 (LangChain with OpenRouter; error handling).
**Depends on:** T1.1
**Acceptance criteria**
- [x] `src/llm.py` builds the chat model (`ChatOpenAI` with OpenRouter's base URL, model from the allowlist, capped `max_tokens`) and the embeddings client (`OpenAIEmbeddings`, `qwen/qwen3-embedding-8b`, `check_embedding_ctx_length=False`) - verified by unit tests on the built objects' settings.
- [x] 401, 402, 429, timeout and 5xx map to distinct user-readable errors; retries are bounded; the key never appears in an error message - verified by unit tests with a mocked transport.
- [x] One real chat call and one real embedding call succeed - owner live check (O5) with `python scripts/live_check_llm.py` on 2026-10-19, recorded in `docs/TESTING.md`.

### T1.3 Input guard and rate limit (S) · status: todo · issue #3
**Serves:** core 4 (input validation), Medium 3, AC-11.
**Depends on:** T1.1
**Acceptance criteria**
- [ ] Empty or whitespace-only input and input over the configured length are rejected with a clear message - unit tests.
- [ ] Common prompt-injection patterns are rejected; a set of benign nutrition questions passes (no false positives) - parametrised unit tests with attack and benign strings.
- [ ] The per-session rate limit rejects requests above the limit - unit test with a fake clock.
- [ ] A rejected input makes no LLM or embedding call - unit test with a spy client.
**Notes:** the attack strings are written by us, not copied from other projects with unknown licences.

## Epic 2: Knowledge base

### T2.1 Source manifest, download script, attribution (M) · status: in review · issue #4
**Serves:** core 1 and 3 (focused knowledge base), AC-14; the copyright policy (beyond the brief, owner's request).
**Depends on:** T1.1, O4
**Acceptance criteria**
- [x] `data/sources.json` lists every Approved article in `docs/SOURCES.md` (#1-#20 and the correction #18a) with title, authors, year, journal, DOI, PMCID, URL, licence, licence URL, copyright notice, evidence tier and topics - unit test checks the IDs match `docs/SOURCES.md` and no field is empty (`tests/test_sources_manifest.py`: `test_manifest_ids_match_the_approved_list`, `test_manifest_matches_the_approved_list_per_article`, `test_no_manifest_field_is_empty`, plus validation tests).
- [x] `scripts/download_sources.py` fetches each article only through the Europe PMC REST API (`fullTextXML`), with a descriptive User-Agent and a pause between requests, into `data/raw/` - unit test with a mocked HTTP client checks the URLs used (`tests/test_download_sources.py`: `test_every_manifest_article_is_fetched_only_from_the_europe_pmc_rest_api`, `test_requests_are_spaced_out`, `test_fetch_sends_a_descriptive_user_agent_and_a_timeout`).
- [x] The script refuses a file whose `<license>` is not CC BY or CC0 and reports it - unit test with fixture XML for both cases (`tests/test_sources_license.py`; `tests/test_download_sources.py::test_a_file_without_cc_by_or_cc0_is_refused_and_reported`; fixtures in `tests/fixtures/jats/`).
- [x] Source #1 is either downloaded from Europe PMC or read from the file the owner saved by hand (O4) - downloaded from Europe PMC (PMC13665703) in the real run on 2026-10-19 (`docs/TESTING.md`); `test_source_one_comes_from_europe_pmc`.
- [x] `ATTRIBUTION.md` is generated from the manifest with authors, title, year, copyright notice, DOI, licence link and the change made - unit test on the generator (`tests/test_attribution.py`; `test_committed_attribution_credits_every_source` fails while the committed file is out of date).
**Notes:** fixture XML is a tiny made-up document we write ourselves, never a copied article. The hand-saved fallback for #1 was dropped (owner's choice, 2026-10-19): every source now has a PMCID.

### T2.2 Parse article XML and chunk with metadata (M) · status: todo · issue #5
**Serves:** core 1 (chunking).
**Depends on:** T2.1
**Acceptance criteria**
- [ ] `src/rag/ingest.py` keeps the title, abstract and body sections and drops figures, tables, formulas, supplementary material and references - unit test on fixture XML containing each element.
- [ ] Chunks are about 1,000 characters with 150 overlap, never span two sections, and start with their section title - unit tests.
- [ ] Every chunk has `source_id`, `title`, `authors`, `year`, `section`, `topics`, `evidence_tier`, `license`, `source_url`, `chunk_index` - unit test.

### T2.3 Build and open the Chroma index (S) · status: todo · issue #6
**Serves:** core 1 (embeddings, similarity search).
**Depends on:** T1.2, T2.2
**Acceptance criteria**
- [ ] `scripts/build_index.py` embeds all chunks in batches and writes the persistent collection to `chroma/`; `src/rag/store.py` opens it - integration test with `DeterministicFakeEmbedding` in a temp dir.
- [ ] A similarity search with a metadata filter returns only matching chunks - integration test.
- [ ] If the index is missing, the app says to run the build script instead of crashing (AC-13) - unit test.
- [ ] The real index is built once - owner live check (O5), with chunk count and cost recorded in `docs/TESTING.md`.

## Epic 3: Retrieval and answers

### T3.1 First answer with sources (vector search) (M) · status: todo · issue #7
**Serves:** core 1, 4 and 5; Easy 3; AC-1, AC-2, AC-10 (progress), AC-13.
**Depends on:** T1.2, T1.3, T2.3, O1
**Acceptance criteria**
- [ ] One chat turn runs guard -> vector retrieval (top 6) -> answer with the owner's system prompt; the answer cites `[S#]` labels that map to the retrieved chunks - integration test with a scripted fake model.
- [ ] Under the answer, a "Sources" expander shows title, year, tier, licence and link for each cited source (AC-1) - AppTest.
- [ ] With no relevant chunk, the app says the sources do not cover the question and cites nothing (AC-2) - integration test.
- [ ] `st.status` shows the steps while the turn runs - AppTest.
- [ ] LLM errors show the mapped message and keep the chat history (AC-13) - AppTest with a failing fake.

### T3.2 Query translation and structured filters (M) · status: todo · issue #8
**Serves:** the brief's advanced RAG (query translation, structured retrieval); AC-3; partly Easy 2.
**Depends on:** T3.1
**Acceptance criteria**
- [ ] One `openai/gpt-5-nano` call with structured output returns 3 rewrites and optional filters (`topics`, `min_year`, `evidence_tier`); invalid output falls back to the original question with no filter - unit tests with a fake model.
- [ ] Retrieval runs for each rewrite with the filter; with no hits it retries without the filter - integration test.
- [ ] "How this answer was found" shows the rewrites and filters (AC-3) - AppTest.

### T3.3 Hybrid search (BM25 + RRF) (M) · status: todo · issue #9
**Serves:** Hard 1; AC-4.
**Depends on:** T3.2, O2
**Acceptance criteria**
- [ ] `src/rag/hybrid.py` builds a BM25 index over the chunk texts (cached) and merges ranked lists with RRF (`1 / (60 + rank)`) - unit test on a hand-computed example.
- [ ] Each rewrite runs vector and BM25 search with the same filter; all lists are fused; the top 6 distinct chunks are kept - integration test.
- [ ] A query with an exact term (e.g. "HMB") retrieves the HMB source (AC-4) - integration test on a small fixture index.
- [ ] On the owner's evaluation questions (O2), vector-only, keyword-only and hybrid retrieval are compared and the hit rates recorded in `docs/TESTING.md` - owner live check (O5) or a run with the real index.

### T3.4 Prompt injection hardening (S) · status: todo · issue #10
**Serves:** Medium 3; AC-11.
**Depends on:** T3.1
**Acceptance criteria**
- [ ] User text is sent only inside `<user_input>` in the user message, and retrieved text only inside `<sources>`; neither is ever concatenated into the system prompt - unit test on the built messages.
- [ ] A retrieved chunk containing an instruction ("ignore previous instructions...") does not change the system prompt or tool use in the built request, and the system prompt tells the model to treat both blocks as data - unit test with a fixture chunk.
- [ ] LLM output is rendered without `unsafe_allow_html` anywhere in the app - test scanning the app source, as in Sprint 1.

## Epic 4: Profile and tools

### T4.1 Profile, units and settings (M) · status: todo · issue #11
**Serves:** PRD features 4 and 7; AC-5, AC-8.
**Depends on:** T1.1
**Acceptance criteria**
- [ ] `src/profile.py` validates weight, height, age (18+), sex, activity and goal with clear messages for out-of-range values (AC-5) - unit tests.
- [ ] `src/units.py` converts kg/lb and cm/ft-in; a round trip returns the same value within rounding (AC-8) - unit tests.
- [ ] The sidebar has a profile form and a units setting; changing units changes the inputs and displayed values; the profile lives in `st.session_state` only and is never logged - AppTest.

### T4.2 Energy and macro tools with the calorie floor (M) · status: todo · issue #12
**Serves:** core 2 (tools 1 and 2); AC-7.
**Depends on:** T4.1, O3
**Acceptance criteria**
- [ ] `calculate_tdee` returns BMR and TDEE (Mifflin-St Jeor, activity factors from config) - known-answer unit tests.
- [ ] `calculate_macro_targets` returns kcal, protein, carbohydrate and fat (g and %) for each goal, using the ranges approved in O3 with their source IDs in comments - unit tests.
- [ ] No goal or profile produces a calorie target below the calorie floor (AC-7) - parametrised unit tests over extreme profiles.
- [ ] Tool arguments are validated with Pydantic ranges; invalid input returns a clear error, not an exception - unit tests.

### T4.3 USDA food table and lookup (M) · status: todo · issue #13
**Serves:** core 2 (tool 3).
**Depends on:** T1.1
**Acceptance criteria**
- [ ] `scripts/prepare_usda.py` turns the Foundation Foods CSV (from the USDA download page) into `data/usda_foods.csv` with description and per-100 g kcal, protein, carbohydrate, fat and fiber; the file credits "USDA FoodData Central" - unit test on a small fixture CSV we write.
- [ ] `lookup_food_nutrition(food, grams)` returns the scaled values, the matched USDA name and close alternatives; an unknown food returns a clear "not found" with suggestions - unit tests.

### T4.4 Tool-calling loop and tool results UI (M) · status: todo · issue #14
**Serves:** core 2 and 5; Medium 6; AC-6.
**Depends on:** T3.1, T4.2, T4.3
**Acceptance criteria**
- [ ] The answer step binds the tools and runs at most 4 tool rounds; a tool error returns to the model as a message - integration tests with a scripted fake model (one tool, two tools, an error, the round limit).
- [ ] Energy tools read the profile from the session; without a profile they return "profile needed" and the UI points to the form - unit and AppTest.
- [ ] Each tool result appears in a "Tool results" expander as a table; macro targets also as a chart (AC-6) - AppTest.

### T4.5 `evaluate_meal_plan` tool (stretch) (S) · status: todo · issue #15
**Serves:** core 2 (extra tool). Only if ahead of schedule.
**Depends on:** T4.4
**Acceptance criteria**
- [ ] Totals for a list of foods and amounts are compared with the targets, with the gaps listed - unit tests.

## Epic 5: Cost, export and guardrails

### T5.1 Token usage and cost (S) · status: todo · issue #16
**Serves:** Medium 5; AC-10.
**Depends on:** T3.2
**Acceptance criteria**
- [ ] `src/usage.py` sums tokens from every call of a turn (query translation, answer rounds, query embedding) and prices them from OpenRouter's models endpoint (cached a day; "price unknown" on failure) - unit tests with fake usage and prices.
- [ ] The UI shows the turn's tokens and cost under the answer and the session totals in the sidebar - AppTest.

### T5.2 Session summary PDF (M) · status: todo · issue #17
**Serves:** Medium 7 and Easy 1 (extra); AC-9.
**Depends on:** T4.4
**Acceptance criteria**
- [ ] `src/export_pdf.py` builds, in memory with reportlab, a PDF with the profile (in the chosen units), the targets, the questions and answers with their sources, the disclaimer and the credits - unit test reads the PDF text back.
- [ ] A download button offers it; no file is written on the server - AppTest and a unit test that checks no file is created.
- [ ] Non-Latin characters in source titles (e.g. "β") do not break the PDF - unit test.

### T5.3 Domain guardrails (S) · status: todo · issue #18
**Serves:** core 3 (domain security); AC-12.
**Depends on:** T3.1, T4.2
**Acceptance criteria**
- [ ] Requests for steroid, SARM or other performance-enhancing drug dosing get a refusal; a set of benign supplement questions (creatine, caffeine) is not refused - parametrised tests (code-level check plus the owner's prompt rule).
- [ ] Mentions of being under 18, pregnancy, medical conditions or medication, and signs of disordered eating get a redirect message - parametrised tests.
- [ ] The disclaimer is visible on every page state - AppTest.

## Epic 6: Evaluation and submission

### T6.1 Evaluation run and reflection (S) · status: todo · issue #19
**Serves:** evaluation criteria (reflection); supports Hard 1.
**Depends on:** T3.3, T4.4, O2, O5
**Acceptance criteria**
- [ ] The owner's evaluation questions are run against the real app; for each, the sources found, whether the answer cites them correctly, and any guardrail issue are recorded in `docs/TESTING.md` exactly as observed.
- [ ] `docs/TESTING.md` lists the known problems and suggested improvements found.

### T6.2 README, final checks and transfer to the course repo (S) · status: todo · issue #20
**Serves:** submission.
**Depends on:** all tickets, O6
**Acceptance criteria**
- [ ] The README explains what the app does, how to install, download sources, build the index and run it, and links the docs; a clean-clone run following it works - manual check recorded in `docs/PROGRESS.md`.
- [ ] Every ticket's status above is final; `docs/PROGRESS.md` has an entry for every merged PR.
- [ ] The transfer checklist in `docs/DEPLOYMENT.md` is done and the course repo shows the files, history and a green CI.
