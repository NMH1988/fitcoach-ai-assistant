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
| O5 | Live checks with the real key: T1.2 (one chat and one embedding call), T2.3 (real index build), T6.1 (evaluation run) | T1.2, T2.3, T6.1 | in progress (T1.2 and T2.3 done 2026-10-19) |
| O6 | Get the course repository URL and confirm how the reviewers read it (files only, or through PRs) | T6.2 | todo |

## Overview and order

Deadline: **2026-11-02**. Target dates leave 1-2 days of buffer.

**Core first, then extras** (owner's decision, 2026-10-19): the brief's core requirements and the optional tasks needed for maximum points (Medium 3, Medium 6, Hard 1) are finished first. The extras (Medium 5 token cost, Medium 7 PDF, the stretch tool) come after them and are still wanted, but never delay a core ticket. T6.2 comes last.

| Ticket | Issue | Title | Size | Depends on | Target | Status |
|---|---|---|---|---|---|---|
| **Core** | | | | | | |
| T1.1 | #1 | Project skeleton, config and CI | S | - | 10-20 | done |
| T1.2 | #2 | OpenRouter clients and error mapping | S | T1.1 | 10-20 | done |
| T1.3 | #3 | Input guard and rate limit | S | T1.1 | 10-21 | done |
| T2.1 | #4 | Source manifest, download script, attribution | M | T1.1, O4 | 10-21 | done |
| T2.2 | #5 | Parse article XML and chunk with metadata | M | T2.1 | 10-22 | done |
| T2.3 | #6 | Build and open the Chroma index | S | T1.2, T2.2 | 10-23 | in review |
| T4.1 | #11 | Profile, units and settings | M | T1.1 | 10-23 | done |
| T4.3 | #13 | USDA food table and lookup | M | T1.1 | 10-23 | done |
| T3.1 | #7 | First answer with sources (vector search) | M | T1.2, T1.3, T2.3, O1 | 10-24 | todo |
| T4.2 | #12 | Energy and macro tools with the calorie floor | M | T4.1, O3 | 10-25 | todo |
| T3.2 | #8 | Query translation and structured filters | M | T3.1 | 10-26 | todo |
| T3.3 | #9 | Hybrid search (BM25 + RRF) | M | T3.2, O2 | 10-27 | todo |
| T3.4 | #10 | Prompt injection hardening | S | T3.1 | 10-27 | todo |
| T4.4 | #14 | Tool-calling loop and tool results UI | M | T3.1, T4.2, T4.3 | 10-28 | todo |
| T5.3 | #18 | Domain guardrails | S | T3.1, T4.2 | 10-29 | todo |
| T6.1 | #19 | Evaluation run and reflection | S | T3.3, T4.4, O2, O5 | 10-30 | todo |
| **Extras** | | | | | | |
| T5.1 | #16 | Token usage and cost | S | T3.2 | 10-30 | todo |
| T5.2 | #17 | Session summary PDF | M | T4.4 | 10-31 | todo |
| T4.5 | #15 | `evaluate_meal_plan` tool (stretch) | S | T4.4 | only if ahead | todo |
| **Last** | | | | | | |
| T6.2 | #20 | README, final checks and transfer to the course repo | S | all, O6 | 11-01 | todo |

**Critical path:** T1.1 -> T1.2 -> T2.1 -> T2.2 -> T2.3 -> T3.1 -> T3.2 -> T3.3 -> T6.1 -> T6.2. T1.3, T4.1 and T4.3 can run alongside it; the extras run after T6.1, or alongside it once their dependencies are done.

**If time runs short, cut in this order:** T4.5, then T5.2 (or keep it with a plain text layout), then T5.1, then chart polish. The core requirements and the optional tasks for maximum points (Medium 3, 6; Hard 1) stay.

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

### T1.2 OpenRouter clients and error mapping (S) · status: done · issue #2
**Serves:** core 4 (LangChain with OpenRouter; error handling).
**Depends on:** T1.1
**Acceptance criteria**
- [x] `src/llm.py` builds the chat model (`ChatOpenAI` with OpenRouter's base URL, model from the allowlist, capped `max_tokens`) and the embeddings client (`OpenAIEmbeddings`, `qwen/qwen3-embedding-8b`, `check_embedding_ctx_length=False`) - verified by unit tests on the built objects' settings.
- [x] 401, 402, 429, timeout and 5xx map to distinct user-readable errors; retries are bounded; the key never appears in an error message - verified by unit tests with a mocked transport.
- [x] One real chat call and one real embedding call succeed - owner live check (O5) with `python scripts/live_check_llm.py` on 2026-10-19, recorded in `docs/TESTING.md`.

### T1.3 Input guard and rate limit (S) · status: done · issue #3
**Serves:** core 4 (input validation), Medium 3, AC-11.
**Depends on:** T1.1
**Acceptance criteria**
- [x] Empty or whitespace-only input and input over the configured length are rejected with a clear message - unit tests (`tests/test_guard.py`: `test_empty_or_whitespace_is_rejected`, `test_input_over_the_limit_is_rejected`, `test_input_at_the_limit_passes`, `test_length_is_counted_after_cleaning`).
- [x] Common prompt-injection patterns are rejected; a set of benign nutrition questions passes (no false positives) - parametrised unit tests with attack and benign strings (`test_injection_attempts_are_rejected`, 104 attacks; `test_benign_questions_pass`, 81 questions, including advice from coaches, labels and official guidelines and the generic "you").
- [x] The per-session rate limit rejects requests above the limit - unit test with a fake clock (`test_rate_limit_rejects_above_the_window_limit`, `test_rate_limit_window_rolls`, `test_rate_limit_rejects_above_the_session_limit`).
- [x] A rejected input makes no LLM or embedding call - unit test with a spy client (`test_rejected_input_makes_no_api_call`, `test_rate_limited_input_makes_no_api_call`, with `test_accepted_input_reaches_the_clients` as the control).
**Notes:** the attack strings are written by us, not copied from other projects with unknown licences. The rate limit counts accepted questions (one per turn), and rejected input does not count (owner's choice, 2026-10-19). T3.1 wires `run_guarded()` into the chat turn.

## Epic 2: Knowledge base

### T2.1 Source manifest, download script, attribution (M) · status: done · issue #4
**Serves:** core 1 and 3 (focused knowledge base), AC-14; the copyright policy (beyond the brief, owner's request).
**Depends on:** T1.1, O4
**Acceptance criteria**
- [x] `data/sources.json` lists every Approved article in `docs/SOURCES.md` (#1-#20 and the correction #18a) with title, authors, year, journal, DOI, PMCID, URL, licence, licence URL, copyright notice, evidence tier and topics - unit test checks the IDs match `docs/SOURCES.md` and no field is empty (`tests/test_sources_manifest.py`: `test_manifest_ids_match_the_approved_list`, `test_manifest_matches_the_approved_list_per_article`, `test_no_manifest_field_is_empty`, plus validation tests).
- [x] `scripts/download_sources.py` fetches each article only through the Europe PMC REST API (`fullTextXML`), with a descriptive User-Agent and a pause between requests, into `data/raw/` - unit test with a mocked HTTP client checks the URLs used (`tests/test_download_sources.py`: `test_every_manifest_article_is_fetched_only_from_the_europe_pmc_rest_api`, `test_requests_are_spaced_out`, `test_fetch_sends_a_descriptive_user_agent_and_a_timeout`).
- [x] The script refuses a file whose `<license>` is not CC BY or CC0 and reports it - unit test with fixture XML for both cases (`tests/test_sources_license.py`; `tests/test_download_sources.py::test_a_file_without_cc_by_or_cc0_is_refused_and_reported`; fixtures in `tests/fixtures/jats/`).
- [x] Source #1 is either downloaded from Europe PMC or read from the file the owner saved by hand (O4) - downloaded from Europe PMC (PMC13665703) in the real run on 2026-10-19 (`docs/TESTING.md`); `test_source_one_comes_from_europe_pmc`.
- [x] `ATTRIBUTION.md` is generated from the manifest with authors, title, year, copyright notice, DOI, licence link and the change made - unit test on the generator (`tests/test_attribution.py`; `test_committed_attribution_credits_every_source` fails while the committed file is out of date).
**Notes:** fixture XML is a tiny made-up document we write ourselves, never a copied article. The hand-saved fallback for #1 was dropped (owner's choice, 2026-10-19): every source now has a PMCID.

### T2.2 Parse article XML and chunk with metadata (M) · status: done · issue #5
**Serves:** core 1 (chunking).
**Depends on:** T2.1
**Acceptance criteria**
- [x] `src/rag/ingest.py` keeps the title, abstract and body sections and drops figures, tables, display formulas (inline formulas keep their plain text, owner's choice in T2.2), supplementary material and references - unit test on fixture XML containing each element (`tests/test_ingest.py`: `test_the_article_title_is_kept`, `test_abstract_and_body_sections_are_kept_in_reading_order`, `test_dropped_content_never_appears`, `test_inline_formulas_keep_their_plain_text`; fixture `tests/fixtures/jats/ingest_article.xml`).
- [x] Chunks are about 1,000 characters with 150 overlap, never span two sections, and start with their section title - unit tests (`test_long_sections_split_into_chunks_of_about_1000_characters`, `test_neighbouring_chunks_overlap_by_at_most_150_characters`, `test_chunks_never_span_two_sections`, `test_text_after_a_subsection_is_its_own_section`, `test_every_chunk_starts_with_its_section_title`, `test_chunks_cut_at_a_paragraph_break_share_no_text`). The overlap (up to 150) applies where a cut falls inside a paragraph; a cut at a paragraph break carries nothing over (owner's confirmation, 2026-10-19).
- [x] Every chunk has `source_id`, `title`, `authors`, `year`, `section`, `topics`, `evidence_tier`, `license`, `source_url`, `chunk_index` - unit test (`test_every_chunk_has_the_source_metadata`, `test_chunk_index_runs_across_sections`, `test_load_chunks_reads_each_downloaded_article`).
**Notes:** back matter that many articles put inside `<body>` (acknowledgements, funding, disclosures, author contributions, data availability, publisher's notes, supplementary, references, appendices of plots) is dropped too (owner's choice). The correction #18a and #18 point to each other through `corrects` / `corrected_by` metadata (owner's choice; serves copyright policy rule 7). Real run on the 21 downloaded articles recorded in `docs/TESTING.md`.

### T2.3 Build and open the Chroma index (S) · status: in review · issue #6
**Serves:** core 1 (embeddings, similarity search).
**Depends on:** T1.2, T2.2
**Acceptance criteria**
- [x] `scripts/build_index.py` embeds all chunks in batches and writes the persistent collection to `chroma/`; `src/rag/store.py` opens it - integration test with `DeterministicFakeEmbedding` in a temp dir (`tests/test_store.py`: `test_build_writes_a_persistent_index_that_open_index_reads`, `test_chunks_are_embedded_in_batches`, `test_article_chunks_keep_their_list_metadata_in_the_index`, `test_a_rebuild_replaces_the_old_index`, `test_a_failed_rebuild_keeps_the_previous_index`; `tests/test_build_index.py::test_the_script_builds_the_index_and_prints_a_summary`).
- [x] A similarity search with a metadata filter returns only matching chunks - integration test (`test_similarity_search_with_a_filter_returns_only_matching_chunks`: topic, minimum year, tier, source, topic and tier, no match).
- [x] If the index is missing, the app says to run the build script instead of crashing (AC-13) - unit test (`test_a_missing_index_says_to_run_the_build_script`, `test_open_index_reports_a_missing_index_even_without_a_key`, plus a directory without the collection, an empty index, an index from another embedding model and an unreadable file). `src/rag/store.py` raises `IndexNotReadyError` with the fixed message; T3.1 shows it in the answer (`docs/UI_DESIGN.md`; owner's choice, 2026-10-19).
- [x] The real index is built once - owner live check (O5), with chunk count and cost recorded in `docs/TESTING.md` (run by the owner on 2026-10-19: 1,810 chunks from 21 sources; cost estimated at about $0.003 from the character count, since langchain does not return the token use of embeddings and OpenRouter's activity chart shows only daily totals, under $0.01 that day; owner's choice to record the estimate).
**Notes:** a build writes a staging collection and renames it only when complete, so a failed build keeps the old index; the collection records the embedding model, and an index from another model is refused. The build embeds approved source text, not user input, so the input guard does not apply to it.

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
- [ ] A missing or unusable index shows `IndexNotReadyError`'s message in the answer and keeps the chat history (AC-13; the UI half of T2.3's criterion, owner's choice in T2.3) - AppTest.

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

### T4.1 Profile, units and settings (M) · status: done · issue #11
**Serves:** PRD features 4 and 7; AC-5, AC-8.
**Depends on:** T1.1
**Acceptance criteria**
- [x] `src/profile.py` validates weight, height, age (18+), sex, activity and goal with clear messages for out-of-range values (AC-5) - verified by `tests/test_profile.py`: `test_metric_weight_out_of_range_is_rejected`, `test_metric_height_out_of_range_is_rejected`, `test_imperial_weight_out_of_range_is_rejected_in_lb`, `test_imperial_height_out_of_range_is_rejected_in_ft_in`, `test_under_18_is_rejected_with_an_adults_only_message`, `test_choices_must_be_one_of_the_options`, `test_every_problem_is_reported_at_once`, the bound and type tests, and `test_user_profile_model_enforces_the_ranges_too`.
- [x] `src/units.py` converts kg/lb and cm/ft-in; a round trip returns the same value within rounding (AC-8) - verified by `tests/test_units.py`: known values both ways, `test_weight_round_trip_is_exact`, `test_height_round_trip_is_exact`, `test_weight_round_trip_through_display_is_within_rounding`, `test_height_round_trip_through_display_is_within_rounding`; and `tests/test_profile.py`: `test_convert_form_values_there_and_back_is_within_rounding`, `test_switching_units_and_back_without_editing_restores_the_typed_values`, `test_first_unedited_switch_after_opening_shows_the_stored_profile`, `test_editing_another_field_between_switches_keeps_the_exact_restore`, `test_saving_with_only_another_field_edited_keeps_the_stored_weight_and_height`, `test_saving_an_edited_height_keeps_the_stored_weight`, `test_editing_the_weight_before_a_switch_still_restores_the_stored_height`, `test_editing_the_height_before_a_switch_still_restores_the_stored_weight`, `test_saving_an_edited_imperial_height_uses_the_typed_feet_and_inches`, `test_saving_the_imperial_form_with_only_the_goal_changed_keeps_the_stored_height`.
- [x] The sidebar has a profile form and a units setting; changing units changes the inputs and displayed values; the profile lives in `st.session_state` only and is never logged - verified by AppTest in `tests/test_app_profile.py`: `test_a_valid_metric_profile_is_saved_and_shown`, `test_invalid_values_show_a_clear_message_and_nothing_is_saved`, `test_switching_units_converts_the_typed_values`, `test_switching_units_twice_gives_back_exactly_what_was_typed`, `test_saving_after_units_switches_only_keeps_the_weight_typed_in_lb`, `test_saving_in_imperial_changes_the_displayed_values_and_back`, `test_the_profile_stays_in_the_session_and_out_of_logs_and_the_url` (log records at DEBUG, stdout/stderr and the URL), plus `tests/test_profile.py::test_profile_module_never_logs_or_prints`. Closing the dialog with X (`on_dismiss`) is shown by the manual browser check (`docs/PROGRESS.md`); the AppTest sets the flag that callback sets.
**Notes:** owner's choices (2026-10-19): the form opens in an `st.dialog`; one Metric / Imperial switch; ranges 30-300 kg, 120-230 cm, 18-100 years; five activity levels with working labels, which T4.2 checks against the source of its activity factors. The owner confirmed (2026-10-19, PR #27) that the units switch inside the dialog opened from the sidebar satisfies the third criterion; the sidebar itself has no separate switch, and its tiles change units on Save.

### T4.2 Energy and macro tools with the calorie floor (M) · status: todo · issue #12
**Serves:** core 2 (tools 1 and 2); AC-7.
**Depends on:** T4.1, O3
**Acceptance criteria**
- [ ] `calculate_tdee` returns BMR and TDEE (Mifflin-St Jeor, activity factors from config) - known-answer unit tests.
- [ ] `calculate_macro_targets` returns kcal, protein, carbohydrate and fat (g and %) for each goal, using the ranges approved in O3 with their source IDs in comments - unit tests.
- [ ] No goal or profile produces a calorie target below the calorie floor (AC-7) - parametrised unit tests over extreme profiles.
- [ ] Tool arguments are validated with Pydantic ranges; invalid input returns a clear error, not an exception - unit tests.

### T4.3 USDA food table and lookup (M) · status: done · issue #13
**Serves:** core 2 (tool 3).
**Depends on:** T1.1
**Acceptance criteria**
- [x] `scripts/prepare_usda.py` turns the Foundation Foods CSV (from the USDA download page) into `data/usda_foods.csv` with description and per-100 g kcal, protein, carbohydrate, fat and fiber; the file credits "USDA FoodData Central" - unit test on a small fixture CSV we write (`tests/test_prepare_usda.py` on made-up `tests/fixtures/usda/` CSVs zipped as USDA ships them: `test_only_complete_foundation_foods_are_written`, `test_values_come_from_the_preferred_nutrient_ids`, `test_the_file_credits_usda_fooddata_central`, plus missing, negative and repeated values, release date, refused zips and the CLI; `test_committed_table_is_valid_and_credits_usda` checks the committed file). Real run on release 2026-04-30 recorded in `docs/TESTING.md`.
- [x] `lookup_food_nutrition(food, grams)` returns the scaled values, the matched USDA name and close alternatives; an unknown food returns a clear "not found" with suggestions - unit tests (`tests/test_food_lookup.py`: `test_values_are_scaled_to_the_requested_grams`, `test_the_matched_usda_name_id_and_source_are_returned`, `test_close_alternatives_are_returned_without_the_match`, `test_names_are_matched_to_the_right_food`, `test_an_unknown_food_is_not_found_with_suggestions`, `test_a_food_not_in_the_table_is_not_found_without_suggestions`; invalid arguments give an error result, not an exception: `test_invalid_grams_give_an_error_result`, `test_invalid_food_names_give_an_error_result`).
**Notes:** owner's choices (2026-10-19): Foundation Foods only (no SR Legacy); energy from Atwater specific factors (nutrient 2048) first, then general factors (2047), then 1008; Claude downloaded the zip once; the branch started from `main` while T2.1 was in progress; after #26 merged, `main` was merged in and the USDA credit added to `ATTRIBUTION.md` through the generator (`test_committed_attribution_credits_usda_fooddata_central`). The LangChain tool wrapper is T4.4's (`src/tools/registry.py`).

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
**Serves:** Medium 5 (extra, after the core); AC-10.
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
