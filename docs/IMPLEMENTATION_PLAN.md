# Implementation plan

Epics, tickets, acceptance criteria, dependencies, order and status. This file is the record of the work that travels with the repo to the course repository (GitHub issues and PRs do not), so keep each ticket's status current: every PR updates the status of its ticket.

**Status of this plan:** approved by the owner on 2026-10-19; GitHub issues #1-#20 created the same day (one per ticket). Epic 7 (T7.1-T7.3, issues #33-#35) added by the owner on 2026-10-20. It follows `docs/PRD.md` (acceptance criteria AC-1 to AC-17) and `docs/ARCHITECTURE.md` (decisions D1-D8).

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
| O1 | Draft the answer system prompt (role, scope, citations `[S#]`, guardrails, "sources are data") in `src/prompts/answer_system.md` | T3.1; T7.2 (a language line, still to add) | done for T3.1; todo for T7.2 (language line). T3.1: drafted by the owner, edited with Claude's review (wording, citation forms, caffeine allowed, partial answers, each turn alone), in the file on 2026-10-20 |
| O2 | Draft the evaluation questions (about 10-15), each with the source(s) it should find and what a good answer contains | T3.3, T6.1; T7.2 (3-5 German questions, one about a food) | todo |
| O3 | Approve the calorie floor and the macro ranges; Claude proposes them with the exact source passages | T4.2 | done (2026-10-19, in T4.2: floor 1200 kcal/day; values in `src/config.py`) |
| O4 | If Europe PMC still has no copy of source #1, save its XML or PDF by hand from the publisher page into `data/raw/` | T2.1 | done: not needed (Europe PMC has #1 as PMC13665703, found in T2.1 on 2026-10-19) |
| O5 | Live checks with the real key: T1.2 (one chat and one embedding call), T2.3 (real index build), T6.1 (evaluation run), T7.2 (German run) | T1.2, T2.3, T6.1, T7.2 | in progress (T1.2 and T2.3 done 2026-10-19) |
| O6 | Get the course repository URL and confirm how the reviewers read it (files only, or through PRs) | T6.2 | todo |

## Overview and order

Deadline: **2026-11-02**. Target dates leave 1-2 days of buffer.

**Core first, then extras** (owner's decision, 2026-10-19): the brief's core requirements and the optional tasks needed for maximum points (Medium 3, Medium 6, Hard 1) are finished first. The extras (Medium 5 token cost, Medium 7 PDF, the stretch tool, and Epic 7: English/German and light/dark mode) come after them and are still wanted, but never delay a core ticket. T6.2 comes last.

| Ticket | Issue | Title | Size | Depends on | Target | Status |
|---|---|---|---|---|---|---|
| **Core** | | | | | | |
| T1.1 | #1 | Project skeleton, config and CI | S | - | 10-20 | done |
| T1.2 | #2 | OpenRouter clients and error mapping | S | T1.1 | 10-20 | done |
| T1.3 | #3 | Input guard and rate limit | S | T1.1 | 10-21 | done |
| T2.1 | #4 | Source manifest, download script, attribution | M | T1.1, O4 | 10-21 | done |
| T2.2 | #5 | Parse article XML and chunk with metadata | M | T2.1 | 10-22 | done |
| T2.3 | #6 | Build and open the Chroma index | S | T1.2, T2.2 | 10-23 | done |
| T4.1 | #11 | Profile, units and settings | M | T1.1 | 10-23 | done |
| T4.3 | #13 | USDA food table and lookup | M | T1.1 | 10-23 | done |
| T3.1 | #7 | First answer with sources (vector search) | M | T1.2, T1.3, T2.3, O1 | 10-24 | done |
| T4.2 | #12 | Energy and macro tools with the calorie floor | M | T4.1, O3 | 10-25 | done |
| T1.5 | #42 | Docs: run commands use the project's venv | S | T1.1 | 10-20 | done |
| T3.2 | #8 | Query translation and structured filters | M | T3.1 | 10-26 | todo |
| T3.3 | #9 | Hybrid search (BM25 + RRF) | M | T3.2, O2 | 10-27 | todo |
| T3.4 | #10 | Prompt injection hardening | S | T3.1 | 10-27 | done |
| T4.4 | #14 | Tool-calling loop and tool results UI | M | T3.1, T4.2, T4.3 | 10-28 | todo |
| T5.3 | #18 | Domain guardrails | S | T3.1, T4.2 | 10-29 | in review |
| T6.1 | #19 | Evaluation run and reflection | S | T3.3, T4.4, O2, O5 | 10-30 | todo |
| **Extras** | | | | | | |
| T1.4 | #32 | Security reviewer agent (beyond the brief; owner's request, done early as it is dev tooling with no product change) | S | T1.1 | 10-20 | done |
| T5.1 | #16 | Token usage and cost | S | T3.2 | 10-30 | todo |
| T5.2 | #17 | Session summary PDF | M | T4.4 | 10-31 | todo |
| T7.3 | #35 | Light and dark mode | S | T3.1 | 10-31 | todo |
| T7.1 | #33 | Language switch: English and German UI | M | T4.4, T5.3, T1.3 | 10-31 | todo |
| T7.2 | #34 | German answers end to end | M | T7.1, T3.2, O1, O2, O5 | 11-01 | todo |
| T4.5 | #15 | `evaluate_meal_plan` tool (stretch) | S | T4.4 | only if ahead | todo |
| T4.6 | #40 | Profile form: a hint instead of "Press Enter to apply" (beyond the brief; owner's request, done early as a small fix) | S | T4.1, T3.1 | 10-20 | done |
| **Last** | | | | | | |
| T6.2 | #20 | README, final checks and transfer to the course repo | S | all, O6 | 11-01 | todo |

**Critical path:** T1.1 -> T1.2 -> T2.1 -> T2.2 -> T2.3 -> T3.1 -> T3.2 -> T3.3 -> T6.1 -> T6.2. T1.3, T4.1 and T4.3 can run alongside it; the extras run after T6.1, or alongside it once their dependencies are done.

**If time runs short, cut in this order:** T4.5, then T7.2 (keep the English answers), then T7.1, then T7.3 (both themes stay from T3.1; only its test, toolbar check and hint go), then T5.2 (or keep it with a plain text layout), then T5.1, then chart polish. T7.3 is beyond the brief, so it goes before T5.2 and T5.1, which the brief asks for (Medium 7, Medium 5). The core requirements and the optional tasks for maximum points (Medium 3, 6; Hard 1) stay.

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

### T1.4 Security reviewer agent (S) · status: done · issue #32
**Serves:** beyond the brief (owner's request); supports core 3 (security measures relevant to the domain) and Medium 3 (prompt injection protection).
**Depends on:** T1.1
**Acceptance criteria**
- [x] `.claude/agents/security-reviewer.md` exists, with the same frontmatter fields and style as `.claude/agents/code-reviewer.md` - checked by the code-reviewer agent.
- [x] The agent maps every path from user input, retrieved text and tool calls to the LLM, tools and UI, and for each surface (direct prompt injection, indirect injection through retrieved text, model-produced tool arguments, Markdown/HTML/link output injection, Chroma metadata/filter injection, path and command injection in scripts, guard before spend, key handling, personal-data leaks) checks the existing controls against `docs/SECURITY.md` and says what an attacker could still do - checked by reading the agent file (Step 1 and Step 2).
- [x] Safety rules: read-only for the repo; never opens `.streamlit/secrets.toml` or `.env`, never prints a key, never calls OpenRouter or any other service (its only network use is GitHub, through `git` and `gh`); its own attack cases run only as offline tests with mocked LLM and embeddings in a scratch directory outside the repo and are never committed; new test cases are only proposed in its report - checked by reading the agent file (Ground rules, Step 3) and by `git status` showing no change after the run against `main`.
- [x] The report gives each finding a severity, `path:line`, a concrete attack string or scenario, the impact and the smallest fix, plus a list of controls that held - checked by one run against `main` (recorded in `docs/PROGRESS.md`).
- [x] `CLAUDE.md` ("Where things are") and `docs/SECURITY.md` name the agent - checked by reading them.
**Notes:** owner's choices (2026-10-20): read-only (tests are only proposed), never a live run against the real model, optional tool (not added to `.claude/rules/workflow.md`); criterion 3 reworded to allow GitHub through `git`/`gh` (owner's choice in the PR #39 review). Attack strings are our own, not copied from other projects.

### T1.5 Docs: run commands use the project's venv (S) · status: done · issue #42
**Serves:** the evaluation's technical item "the app works (you can chat and get answers)" (`docs/BRIEF.md`), when run as documented; prepares T6.2 (README).
**Depends on:** T1.1
**Acceptance criteria** (approved by the owner, 2026-10-20)
- [x] Right before the run commands, the README says they must run in a terminal with `.venv` active (`(.venv)` at the start of the prompt), gives the way without activating (`.venv\Scripts\streamlit.exe run app.py` on Windows, `.venv/bin/streamlit run app.py` on macOS and Linux), and names the symptom of the wrong Python (`ModuleNotFoundError: No module named 'langchain_chroma'`) - review.
- [x] The README lists the steps before the first question: set the key, `python scripts/download_sources.py`, `python scripts/build_index.py`, then run the app, with the note to stop the app before rebuilding the index - review.
- [x] The "Run" line in `CLAUDE.md` says to use the venv too - review.
- [x] The documented command `.venv\Scripts\streamlit.exe run app.py` is run in a new terminal and the app loads without error; CI passes - manual check done (2026-10-20: typed as written in a new PowerShell tab; the app loaded with its title and four tabs and no error; local ruff and pytest pass); CI green on PR #43, merged 2026-10-20.
**Notes:** found on 2026-10-20 when the owner started the app with the system Python's `streamlit` (1.64, without the project's packages) after PR #41 merged.

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

### T2.3 Build and open the Chroma index (S) · status: done · issue #6
**Serves:** core 1 (embeddings, similarity search).
**Depends on:** T1.2, T2.2
**Acceptance criteria**
- [x] `scripts/build_index.py` embeds all chunks in batches and writes the persistent collection to `chroma/`; `src/rag/store.py` opens it - integration test with `DeterministicFakeEmbedding` in a temp dir (`tests/test_store.py`: `test_build_writes_a_persistent_index_that_open_index_reads`, `test_chunks_are_embedded_in_batches`, `test_a_fresh_process_reads_the_index_from_disk`, `test_article_chunks_keep_their_list_metadata_in_the_index`, `test_a_rebuild_replaces_the_old_index`, `test_a_failed_rebuild_keeps_the_previous_index`; `tests/test_build_index.py::test_the_script_builds_the_index_and_prints_a_summary`).
- [x] A similarity search with a metadata filter returns only matching chunks - integration test (`test_similarity_search_with_a_filter_returns_only_matching_chunks`: topic, minimum year, tier, source, topic and tier, no match).
- [x] If the index is missing, the app says to run the build script instead of crashing (AC-13) - unit test (`test_a_missing_index_says_to_run_the_build_script`, `test_open_index_reports_a_missing_index_even_without_a_key`, plus a directory without the collection, an empty index, an index from another embedding model and an unreadable file). `src/rag/store.py` raises `IndexNotReadyError` with the fixed message; T3.1 shows it in the answer (`docs/UI_DESIGN.md`; owner's choice, 2026-10-19).
- [x] The real index is built once - owner live check (O5), with chunk count and cost recorded in `docs/TESTING.md` (run by the owner on 2026-10-19: 1,810 chunks from 21 sources; cost estimated at about $0.003 from the character count, since langchain does not return the token use of embeddings and OpenRouter's activity chart shows only daily totals, under $0.01 that day; owner's choice to record the estimate).
**Notes:** a build writes a staging collection and renames it only when complete, so a failed build keeps the old index; the collection records the embedding model, and an index from another model is refused. The build embeds approved source text, not user input, so the input guard does not apply to it.

## Epic 3: Retrieval and answers

### T3.1 First answer with sources (vector search) (M) · status: done · issue #7
**Serves:** core 1, 4 and 5; Easy 3; AC-1, AC-2, AC-10 (progress), AC-13.
**Depends on:** T1.2, T1.3, T2.3, O1
**Acceptance criteria**
- [x] One chat turn runs guard -> vector retrieval (top 6) -> answer with the owner's system prompt; the answer cites `[S#]` labels that map to the retrieved chunks - integration test with a scripted fake model (`tests/test_chat.py`: `test_a_turn_runs_the_guard_retrieval_and_the_answer_in_order`, `test_the_labels_map_to_the_retrieved_chunks`, `test_retrieval_keeps_at_most_the_top_k_chunks`, `test_the_question_and_the_chunks_are_delimited_in_the_user_message`, `test_rejected_input_opens_nothing_and_calls_no_model`). The owner's prompt is in (O1; `test_the_answer_prompt_is_the_owners`); real answers with labels and source cards checked by the owner (O5, 2026-10-20), and again with streaming, the paced reveal and the larger layout. The answer streams in (owner's request; `test_the_answer_is_reported_as_it_streams_in`, `test_the_streamed_answer_is_replaced_by_the_full_result`).
- [x] Under the answer, a "Sources" expander shows one card per cited source with title, authors (the first three, then "et al."; owner's choice in T3.1), evidence tier badge, journal, year, licence with its link, and the article link (AC-1; cards as in `docs/UI_DESIGN.md`, owner's choice in T3.1) - AppTest (`tests/test_app_chat.py`: `test_an_answer_shows_under_the_question_with_its_sources`, `test_a_source_card_shows_title_year_tier_licence_and_link`, `test_a_tier_2_source_has_its_own_badge`).
- [x] With no relevant chunk, the app says the sources do not cover the question and cites nothing (AC-2) - integration test (`test_with_no_relevant_chunk_the_app_says_the_sources_do_not_cover_it`, `test_retrieval_drops_chunks_beyond_the_distance_limit`, `test_an_answer_that_cites_nothing_lists_no_sources`) and AppTest (`test_no_relevant_source_shows_the_fixed_message_and_no_sources`). "Relevant" means a cosine distance up to `RETRIEVAL_MAX_DISTANCE` (owner's choice: a limit in code plus the prompt); set to 0.62 from live checks on 28 questions (O5, 2026-10-20, `docs/TESTING.md`; first 0.5 from 4 short questions, which blocked a long covered question).
- [x] `st.status` shows the steps while the turn runs - AppTest (`test_the_status_shows_each_step_of_the_turn`, `test_the_history_stays_across_turns`) and a manual check in the browser with a fake model (all three steps visible).
- [x] LLM errors show the mapped message and keep the chat history (AC-13) - AppTest with a failing fake (`test_a_model_error_shows_the_mapped_message_and_keeps_the_history`); unit tests for a mapped SDK error, a cut-off and an empty answer (`test_a_model_error_becomes_its_fixed_message`, `test_a_cut_off_answer_says_so`, `test_an_empty_answer_gives_the_generic_error`); a missing key gives a setup message (`test_a_missing_key_shows_the_setup_message`).
- [x] A missing or unusable index shows `IndexNotReadyError`'s message in the answer and keeps the chat history (AC-13; the UI half of T2.3's criterion, owner's choice in T2.3) - AppTest (`test_a_missing_or_unusable_index_shows_the_build_command`, missing and corrupt, two turns each); `tests/test_store.py::test_an_unreadable_index_gives_the_same_message_on_every_check`.

**Notes:** owner's choices (2026-10-19): code first with the prompt in its own file, written by the owner before the merge (O1); a distance limit plus the prompt for "not covered"; each turn stands alone (the model does not see earlier turns; T3.2 may use the history for rewrites); the UI follows `docs/UI_DESIGN.md` (theme, header badge, four tabs, source cards), keeping the app name "Nutrition AI Assistant". The profile is not sent to the model yet (T4.4).

### T3.2 Query translation and structured filters (M) · status: todo · issue #8
**Serves:** the brief's advanced RAG (query translation, structured retrieval); AC-3; partly Easy 2.
**Depends on:** T3.1
**Acceptance criteria**
- [ ] One `openai/gpt-5-nano` call with structured output returns 3 rewrites and optional filters (`topics`, `min_year`, `evidence_tier`); invalid output falls back to the original question with no filter - unit tests with a fake model.
- [ ] Retrieval runs for each rewrite with the filter; with no hits it retries without the filter - integration test.
- [ ] "How this answer was found" shows the rewrites and filters (AC-3) - AppTest.
- [ ] The query-translation call gets the question only inside `<user_input>` in the user message, escaped with `escape_prompt_data()`, never in its system prompt, so a delimiter look-alike or a `**System:**` line stays data; its messages are built with `SystemMessage` / `HumanMessage` like the answer step's, with no LangChain prompt template at all (no `PromptTemplate`, `ChatPromptTemplate`, `from_template`, `from_messages` or `MessagesPlaceholder` in `app.py` or `src/`) - parametrised unit test on the built messages, as in T3.4's `tests/test_prompt_injection.py`, and `test_no_prompt_template_is_used_in_the_app` still passing (follow-up from T3.4; owner's choices, 2026-10-20: the template ban stays, stricter than "never as template text", so both steps build messages one way).

### T3.3 Hybrid search (BM25 + RRF) (M) · status: todo · issue #9
**Serves:** Hard 1; AC-4.
**Depends on:** T3.2, O2
**Acceptance criteria**
- [ ] `src/rag/hybrid.py` builds a BM25 index over the chunk texts (cached) and merges ranked lists with RRF (`1 / (60 + rank)`) - unit test on a hand-computed example.
- [ ] Each rewrite runs vector and BM25 search with the same filter; all lists are fused; the top 6 distinct chunks are kept - integration test.
- [ ] A query with an exact term (e.g. "HMB") retrieves the HMB source (AC-4) - integration test on a small fixture index.
- [ ] On the owner's evaluation questions (O2), vector-only, keyword-only and hybrid retrieval are compared and the hit rates recorded in `docs/TESTING.md` - owner live check (O5) or a run with the real index.

### T3.4 Prompt injection hardening (S) · status: done · issue #10
**Serves:** Medium 3; AC-11.
**Depends on:** T3.1
**Acceptance criteria**
- [x] User text is sent only inside `<user_input>` in the user message, and retrieved text only inside `<sources>`; neither is ever concatenated into the system prompt - unit test on the built messages (`tests/test_prompt_injection.py`: `test_a_look_alike_in_the_question_stays_inside_user_input`, `test_a_look_alike_in_chunk_text_stays_inside_sources`, which check that the four delimiters are the only tags, in order, and that the system message is the prompt alone; `tests/test_chat.py::test_the_question_and_the_chunks_are_delimited_in_the_user_message`).
- [x] A retrieved chunk containing an instruction ("ignore previous instructions...") does not change the system prompt or tool use in the built request, and the system prompt tells the model to treat both blocks as data - unit test with a fixture chunk (`test_an_injected_chunk_does_not_change_the_system_prompt_or_tool_use`: a turn on a fixture index with a made-up injected chunk sends the same system prompt and request shape as a clean one, with no tool calls, and the chunk only escaped inside `<sources>`; `test_the_answer_prompt_tells_the_model_both_blocks_are_data` on the owner's prompt).
- [x] LLM output is rendered without `unsafe_allow_html` anywhere in the app - test scanning the app source, as in Sprint 1 (`test_nothing_in_the_app_renders_with_unsafe_allow_html`: an AST scan of `app.py` and `src/`, so comments do not count, for `unsafe_allow_html` and `unsafe_allow_javascript`; `test_the_app_uses_no_raw_html_components`).
- [x] User text, chunk text and any chunk metadata put in the prompt are escaped before they are wrapped, so a delimiter look-alike (`</user_input>`, `</user-input>`, `<user_input id="2">`, `</sources lang="en">`, `<sources/>`) cannot close or open a block and a `**System:**` or `> System:` line stays data; user text is passed as message content, never as prompt-template text - parametrised unit test on the built messages (follow-up from the T1.4 security audit, finding 3) (the three `test_a_look_alike_in_...` tests over seven look-alikes each, in the question, the chunk text and the title and year; `test_the_escape_keeps_the_text_exact_and_marks_typed_entities`, `test_braces_in_the_question_are_passed_as_text_not_as_a_template`, `test_no_prompt_template_is_used_in_the_app`).
**Notes:** owner's choices (2026-10-20): the guard's patterns are widened too (attributes, `-` or a space in "user input", a closing slash, `<source>`, role lines after `**`, `>` or `_`), with new attack and benign strings and a speed test in `tests/test_guard.py`; the answer prompt is not changed (it already says both blocks are data, and models read `&lt;` as `<`). Escaping is `html.escape` without quotes (`escape_prompt_data()` in `src/prompt_data.py`, a module that imports nothing from `src`, so T3.2's query translation in `src/rag/` and T4.4's tool loop can use it without an import cycle; `test_the_escape_module_imports_nothing_from_src`), after folding full-width and small-form brackets (`test_full_width_and_small_form_brackets_in_a_chunk_are_escaped`). After code review round 1 the guard's tag pattern only counts attribute-shaped text, so comparisons such as "(<sources say 25%) and > 1200 kcal" pass, and the AC3 scan also flags `unsafe_allow_html` passed by position, `*` or `**` (`test_the_render_scan_finds_every_way_to_allow_html`).

## Epic 4: Profile and tools

### T4.1 Profile, units and settings (M) · status: done · issue #11
**Serves:** PRD features 4 and 7; AC-5, AC-8.
**Depends on:** T1.1
**Acceptance criteria**
- [x] `src/profile.py` validates weight, height, age (18+), sex, activity and goal with clear messages for out-of-range values (AC-5) - verified by `tests/test_profile.py`: `test_metric_weight_out_of_range_is_rejected`, `test_metric_height_out_of_range_is_rejected`, `test_imperial_weight_out_of_range_is_rejected_in_lb`, `test_imperial_height_out_of_range_is_rejected_in_ft_in`, `test_under_18_is_rejected_with_an_adults_only_message`, `test_choices_must_be_one_of_the_options`, `test_every_problem_is_reported_at_once`, the bound and type tests, and `test_user_profile_model_enforces_the_ranges_too`.
- [x] `src/units.py` converts kg/lb and cm/ft-in; a round trip returns the same value within rounding (AC-8) - verified by `tests/test_units.py`: known values both ways, `test_weight_round_trip_is_exact`, `test_height_round_trip_is_exact`, `test_weight_round_trip_through_display_is_within_rounding`, `test_height_round_trip_through_display_is_within_rounding`; and `tests/test_profile.py`: `test_convert_form_values_there_and_back_is_within_rounding`, `test_switching_units_and_back_without_editing_restores_the_typed_values`, `test_first_unedited_switch_after_opening_shows_the_stored_profile`, `test_editing_another_field_between_switches_keeps_the_exact_restore`, `test_saving_with_only_another_field_edited_keeps_the_stored_weight_and_height`, `test_saving_an_edited_height_keeps_the_stored_weight`, `test_editing_the_weight_before_a_switch_still_restores_the_stored_height`, `test_editing_the_height_before_a_switch_still_restores_the_stored_weight`, `test_saving_an_edited_imperial_height_uses_the_typed_feet_and_inches`, `test_saving_the_imperial_form_with_only_the_goal_changed_keeps_the_stored_height`.
- [x] The sidebar has a profile form and a units setting; changing units changes the inputs and displayed values; the profile lives in `st.session_state` only and is never logged - verified by AppTest in `tests/test_app_profile.py`: `test_a_valid_metric_profile_is_saved_and_shown`, `test_invalid_values_show_a_clear_message_and_nothing_is_saved`, `test_switching_units_converts_the_typed_values`, `test_switching_units_twice_gives_back_exactly_what_was_typed`, `test_saving_after_units_switches_only_keeps_the_weight_typed_in_lb`, `test_saving_in_imperial_changes_the_displayed_values_and_back`, `test_the_profile_stays_in_the_session_and_out_of_logs_and_the_url` (log records at DEBUG, stdout/stderr and the URL), plus `tests/test_profile.py::test_profile_module_never_logs_or_prints`. Closing the dialog with X (`on_dismiss`) is shown by the manual browser check (`docs/PROGRESS.md`); the AppTest sets the flag that callback sets.
**Notes:** owner's choices (2026-10-19): the form opens in an `st.dialog`; one Metric / Imperial switch; ranges 30-300 kg, 120-230 cm, 18-100 years; five activity levels with working labels, which T4.2 checks against the source of its activity factors. The owner confirmed (2026-10-19, PR #27) that the units switch inside the dialog opened from the sidebar satisfies the third criterion; the sidebar itself has no separate switch, and its tiles change units on Save.

### T4.2 Energy and macro tools with the calorie floor (M) · status: done · issue #12
**Serves:** core 2 (tools 1 and 2); AC-7.
**Depends on:** T4.1, O3
**Acceptance criteria**
- [x] `calculate_tdee` returns BMR and TDEE (Mifflin-St Jeor, activity factors from config) - known-answer unit tests (`tests/test_energy.py`: `test_tdee_known_answers` (five profiles, both sexes, every activity level), `test_tdee_uses_the_unrounded_bmr`, `test_each_activity_level_multiplies_the_same_bmr`, `test_config_holds_the_source_values`, `test_every_profile_option_has_a_factor_and_a_protein_target`, `test_tdee_names_its_method_and_sources`, `test_activity_labels_name_the_frequencies_of_the_factor_source`).
- [x] `calculate_macro_targets` returns kcal, protein, carbohydrate and fat (g and %) for each goal, using the ranges approved in O3 with their source IDs in comments - unit tests (`test_maintain_known_answer`, `test_lose_fat_known_answer`, `test_build_muscle_known_answer`, `test_targets_sit_inside_the_source_ranges`, `test_macro_targets_cite_the_approved_sources`, `test_macro_targets_chain_from_calculate_tdee`, `test_protein_is_lowered_when_it_does_not_fit_the_target`; source IDs in the comments of the energy block in `src/config.py`).
- [x] No goal or profile produces a calorie target below the calorie floor (AC-7) - parametrised unit tests over extreme profiles (`test_no_profile_gets_a_target_below_the_calorie_floor`: every goal over 450 profiles, the corners of every range included, checking the target, the range and the macro grams; `test_the_lowest_tdees_are_raised_to_the_floor`, `test_a_target_below_the_floor_is_raised_and_noted`, `test_a_floor_above_the_needs_says_it_will_not_lead_to_fat_loss`, `test_a_floor_equal_to_the_needs_says_it_will_not_lead_to_fat_loss`, `test_a_floor_above_the_needs_is_noted_for_the_other_goals`, `test_a_target_at_the_floor_is_not_marked_as_raised`).
- [x] Tool arguments are validated with Pydantic ranges; invalid input returns a clear error, not an exception - unit tests (`test_invalid_tdee_arguments_give_an_error_result`, `test_invalid_macro_arguments_give_an_error_result`: out of range, strings, booleans, NaN, infinity, None, unknown options; `test_every_bad_tdee_argument_is_reported_at_once`, `test_invalid_messages_do_not_echo_the_input`, `test_the_argument_schemas_carry_the_ranges`, `test_the_tdee_range_covers_every_profile`).
**Notes:** owner's choices (2026-10-19, O3 and copyright rule 4): two new formula sources, #22 (Mifflin-St Jeor coefficients) and #23 (activity factors), CC BY, licence read on the publisher pages, credited in `ATTRIBUTION.md`; the activity labels now follow #23 (times a week; moderate is 4-5); calorie floor 1200 kcal/day for everyone (top of the low-energy diet range in #1 and #9); lose fat -0.5% of body weight a week at about 3500 kcal per lb (#1, #12); build muscle +10% (#11); protein 2.2 g/kg for fat loss and 1.9 otherwise (range 1.6-2.2, #1, #11); fat 25% of kcal (#11, #12); carbohydrate the rest (#11); when protein and fat do not fit (very heavy body, low target), protein is lowered and carbohydrate is 0, with a note. The LangChain wrappers and reading the profile from the session are T4.4's.

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
- [ ] Each tool is built with an explicit `args_schema` that holds only the model's fields: `lookup_food_nutrition` takes only `food` and `grams` (never `table`), the energy tools take no profile fields; `FoodLookupArgs` has `extra="forbid"`; a call with `table`, a profile field or any extra field is refused with the fixed message and runs no lookup - unit test on the built tools (follow-up from the T1.4 security audit, finding 2).
- [ ] USDA names in a tool result (`matched_name`, `alternatives`, `message`) reach the model only inside the tool result and appear in the UI as plain text, so a name with Markdown or a delimiter cannot add a link, an image or a block - unit test and AppTest with a fixture table (follow-up from the T1.4 security audit, finding 4).
- [ ] An instruction in a retrieved chunk does not change the tools bound or `tool_choice`: a clean and an injected turn pass the same tool arguments to the model - extend `tests/test_prompt_injection.py::test_an_injected_chunk_does_not_change_the_system_prompt_or_tool_use` to compare `ScriptedChatModel.call_kwargs` with tools bound (follow-up from T3.4; owner's choice, 2026-10-20).
- [ ] The profile summary and tool results that go into the prompt are escaped with `escape_prompt_data()` and sit only in their own delimited block or tool message, never in the system prompt, so a look-alike in a USDA name cannot close or open a block - parametrised unit test on the built messages (follow-up from T3.4; owner's choice, 2026-10-20).
**Notes:** `tests/fakes.py::ScriptedChatModel` must implement `bind_tools` (LangChain's `BaseChatModel.bind_tools` raises `NotImplementedError`) and keep recording the bound tools in `call_kwargs`, so the tool-use check above compares real arguments (PR #45 review, 2026-10-20). Import `escape_prompt_data()` from `src/prompt_data.py`.

### T4.5 `evaluate_meal_plan` tool (stretch) (S) · status: todo · issue #15
**Serves:** core 2 (extra tool). Only if ahead of schedule.
**Depends on:** T4.4
**Acceptance criteria**
- [ ] Totals for a list of foods and amounts are compared with the targets, with the gaps listed - unit tests.

### T4.6 Profile form: a hint instead of "Press Enter to apply" (S) · status: done · issue #40
**Serves:** beyond the brief (owner's request, 2026-10-20).
**Depends on:** T4.1, T3.1
**Acceptance criteria** (approved by the owner, 2026-10-20)
- [x] In the "Your details" dialog, Streamlit's in-field "Press Enter to apply" no longer appears in any input (weight, age, height in cm or ft/in) - manual browser check, metric and imperial, with a screenshot (2026-10-20: the instruction element stays in the DOM while a value is typed but is never shown; screenshot `docs/ui/t4.6-profile-dialog-hint.jpg`, imperial, "11" being typed in Height (in)).
- [x] The CSS rule targets only `[data-testid="InputInstructions"]` inside the dialog and is drawn only while the dialog is open; inputs elsewhere are unchanged - AppTest (`test_the_css_is_drawn_only_while_the_dialog_is_open`, `test_the_css_is_gone_after_the_dialog_is_dismissed`, `test_the_dialog_css_is_one_fixed_rule_scoped_to_the_dialog`). Wording adjusted with the owner's approval: a style-only `st.html` lives in Streamlit's event container, so it is "drawn only while the dialog is open" rather than "in the dialog".
- [x] The first line of the dialog is the hint "Type your values, then press Save. Values are checked when you save." - AppTest (`test_the_hint_is_the_first_line_of_the_dialog`).
- [x] A value typed and then saved by clicking Save directly (no Enter, no click elsewhere first) is saved - manual browser check (AppTest cannot simulate it): 77.3 kg in metric and 5 ft 11 in ("11" typed last) in imperial were saved.
- [x] The CSS is a fixed string with no script and no user or model content; `docs/UI_DESIGN.md` records the exception, its reason and its risk (a later Streamlit could rename the test id: the text would come back, nothing breaks); `docs/SECURITY.md` notes that `st.html` is used only with this fixed CSS - code review and tests (`test_the_dialog_css_is_one_fixed_rule_scoped_to_the_dialog`, `test_st_html_is_used_only_with_the_fixed_dialog_css`).
- [x] Existing profile tests pass; `ruff check .`, `ruff format --check .` and `python -m pytest -q` pass (1,035 tests).
**Notes:** Streamlit 1.66 has no option to hide the text outside `st.form(enter_to_submit=False)`, and T4.1 chose not to use a form (the Metric/Imperial switch converts typed values), so the owner approved one scoped CSS rule as an exception to the "native first" principle.

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
- [ ] Answers are unescaped with `html.unescape`, so an entity the model copied from the escaped prompt (`&lt;`, `&gt;`, `&amp;`) shows as the character, as it does in the app's Markdown; then, since reportlab's `Paragraph` reads its text as markup (`<b>`, `<font>`, `<link href=...>`), they are escaped for it with `xml.sax.saxutils.escape` before any `Paragraph` (or drawn as plain text), so a `<` cannot break the PDF and model text cannot add a link or formatting - unit test: an answer holding "p &lt; 0.05" reads back "p < 0.05", and a raw `<b>x</b>` or `<link href="https://example.com">x</link>` reads back as literal text with no link annotation (follow-up from T3.4; owner's choices, 2026-10-20).

### T5.3 Domain guardrails (S) · status: in review · issue #18
**Serves:** core 3 (domain security); AC-12.
**Depends on:** T3.1, T4.2
**Acceptance criteria**
- [x] Requests for steroid, SARM or other performance-enhancing drug dosing get a refusal; a set of benign supplement questions (creatine, caffeine) is not refused - parametrised tests (code-level check plus the owner's prompt rule) (`tests/test_guardrails.py`: `test_flagged_questions_get_their_guardrail_message` (the `PED_DOSING` strings), `test_benign_questions_are_not_refused_or_redirected` (creatine and caffeine doses, steroids without a dose request, plus the guard's benign list), `test_drug_dosing_wins_over_a_redirect`, `test_a_guardrail_rejection_makes_no_call`; `tests/test_chat.py`: `test_a_guardrail_question_opens_nothing_and_calls_no_model`, `test_the_answer_prompt_keeps_the_domain_guardrails`; `tests/test_app_chat.py`: `test_a_guardrail_question_shows_its_message_and_calls_no_model`, `test_a_creatine_or_caffeine_dose_question_is_answered`).
- [x] Mentions of being under 18, pregnancy, medical conditions or medication, and signs of disordered eating get a redirect message - parametrised tests (`tests/test_guardrails.py`: `test_flagged_questions_get_their_guardrail_message` (the `MINOR`, `PREGNANCY`, `MEDICAL` and `DISORDERED_EATING` strings, intakes below the calorie floor included), `test_benign_questions_are_not_refused_or_redirected` (near misses: "I'm 16 weeks into my cut", "I'm 17% body fat", "Does creatine harm the kidneys?", "I'm lactose intolerant", "a 500 kcal deficit per day"), `test_every_concern_has_a_message_and_a_flagged_example`, `test_the_low_intake_check_follows_the_configured_floor`, `test_a_guardrail_rejection_does_not_use_the_quota`; `tests/test_app_chat.py`: `test_a_guardrail_question_shows_its_message_and_calls_no_model`, one case per kind).
- [x] The disclaimer is visible on every page state - AppTest (`tests/test_app_chat.py`: `test_the_disclaimer_is_visible_in_every_chat_state`: new session, answer, no sources, rejected, guardrail, error; `tests/test_app_profile.py`: `test_disclaimer_stays_visible_in_every_profile_state`: dialog open, dialog with an error, profile saved, editing the profile; `tests/test_app_smoke.py`: `test_app_shows_disclaimer`).
**Notes:** owner's choices (2026-10-20): drug questions are refused only when they ask for a dose or use in the same sentence as the drug ("are SARMs safe?" reaches the model, which follows the prompt rule); redirects are fixed messages with no model call; medical conditions count when said about the user or a group ("I have diabetes", "people with kidney disease"), medication on any mention, breastfeeding and the time after birth with pregnancy, lactose intolerance and allergies not at all; an intake per day below the calorie floor counts as a sign of disordered eating. The messages were drafted by Claude and approved by the owner. German patterns are T7.1's.

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

## Epic 7: Language and appearance (extras)

Added by the owner on 2026-10-20. All three tickets are extras: they come after the core and never delay a core ticket. Concept and layout in `docs/UI_DESIGN.md` ("Language" and "Light and dark mode").

### T7.1 Language switch: English and German UI (M) · status: todo · issue #33
**Serves:** Hard 4 (multi-language support), as an extra after the core; AC-16. Changes the PRD's English-only decision: beyond the PRD (owner's request, 2026-10-20).
**Depends on:** T4.4, T5.3 (so most UI text and the guardrails exist before they are translated), T1.3
**Acceptance criteria**
- [ ] `src/i18n.py` holds every user-facing UI string in English and German behind one lookup function; a test fails if a key exists in one language but not the other - unit test.
- [ ] The header has a language control (a `:material/translate:` icon next to an EN | DE segmented control labelled "Language", label collapsed, `required=True` so it can never be deselected to `None`); switching it changes all UI text (sidebar, tabs, buttons, errors, guard and guardrail messages, disclaimer) - AppTest in both languages.
- [ ] The default language follows the browser locale (`st.context.locale`: German for `de*`, English otherwise, including `None`) and the user's choice is kept for the session - unit test on the locale mapping and AppTest.
- [ ] The input guard rejects German prompt-injection strings and passes German benign nutrition questions - parametrised tests with our own strings.
- [ ] The domain guardrails' code-level checks catch German requests (performance-enhancing drug dosing, under 18, pregnancy, medical conditions, disordered eating) - parametrised tests with German attack and benign strings.
- [ ] Source titles, licence names and USDA food names stay in English; the Food lookup tab tells German users to enter English food names - AppTest.
- [ ] The German texts, the medical disclaimer in particular, are reviewed by the owner or a German speaker before merge - manual check recorded in `docs/PROGRESS.md`.
**Notes:**
- The German safety checks are in this ticket, not T7.2, because a German UI invites German input even if T7.2 is cut.
- Many messages come from `src/` (guard rejections and rate limit in `src/guard.py`, LLM errors in `src/llm.py`, `IndexNotReadyError` in `src/rag/store.py`, profile validation in `src/profile.py`). `src/` returns message keys or codes and the UI translates them. Tool notes stay English, so the tool result the UI shows matches what the model received. Recheck the M size at the start.
- The guard's folded patterns (`_FOLDED_PATTERNS` in `src/guard.py`) run on casefolded NFKC text, once with accents and once without (`detection_views()`), so ü is seen as both ü and u, and ß always becomes ss. Write the German folded patterns with ss and u/o/a, also accept the typed spellings ue/oe/ae, and include ß, ss and ue spellings among the German attack strings. Update `docs/SECURITY.md` and `docs/ARCHITECTURE.md`, which say the patterns are English only.
- The German UI texts are our own writing. Every UI string added after T7.1 needs both languages.

### T7.2 German answers end to end (M) · status: todo · issue #34
**Serves:** Hard 4 (multi-language support), as an extra after the core; AC-16. Beyond the PRD (owner's request, 2026-10-20).
**Depends on:** T7.1, T3.2, O1 (a language line in the system prompt), O2 (German evaluation questions), O5 (German live run)
**Acceptance criteria**
- [ ] The chosen language reaches the answer step as a fixed value (`en` or `de`), never taken from user text; the answer uses that language and the same `[S#]` citations - integration test with a scripted fake model on the built messages.
- [ ] Query translation turns a German question into English rewrites, so vector and BM25 retrieval run in English - unit test with a fake model.
- [ ] The food tool's description tells the model to pass English food names, so a German food question still finds the USDA food - test on the tool description, plus one German food question in O2.
- [ ] Guardrail refusals and redirects are answered in the chosen language - parametrised tests.
- [ ] Source passages are never presented as translated quotes; summaries keep the meaning (`.claude/rules/copyright.md` rule 7) - prompt rule plus a test on the built system prompt.
- [ ] If T5.2 is built, the PDF uses the chosen language - unit test reads back German headings.
- [ ] The owner's German evaluation questions are run against the real app and the results recorded in `docs/TESTING.md` - owner live check (O5).
**Notes:** the knowledge base stays English.

### T7.3 Light and dark mode (S) · status: todo · issue #35
**Serves:** beyond the brief (owner's request, 2026-10-20); supports core 5 (intuitive UI); AC-17.
**Depends on:** T3.1 (writes both themes in `.streamlit/config.toml`)
**Decision (owner, 2026-10-20):** use Streamlit's built-in appearance switch (menu -> Settings -> Light / Dark / System). Streamlit 1.66 cannot change the theme from the script, and a custom CSS toggle would break the "no custom CSS" rule and be fragile.
**Acceptance criteria**
- [ ] `.streamlit/config.toml` defines both `[theme.light]` and `[theme.dark]` with the colours in `docs/UI_DESIGN.md`, so the settings menu offers Light, Dark and System - test that parses the config.
- [ ] The toolbar setting (`client.toolbarMode`) keeps the Settings entry available to users - test on the config value plus a manual check.
- [ ] A short hint in the sidebar tells users where to switch light or dark mode (in both languages once T7.1 is merged) - AppTest.
- [ ] The macro bar, badges and source cards are readable in both modes - manual check in both modes, recorded in `docs/TESTING.md`.
- [ ] No `unsafe_allow_html` is added, and `st.html` is used only with T4.6's fixed CSS constant (`config.PROFILE_DIALOG_CSS`, allowlisted by name) - a source-scan test (T4.6's `st.html` test, T3.4's, or added here if neither covers it).
**Notes:** T3.1 already writes both theme sections; this ticket adds the config test, the toolbar check, the hint and the two-mode check.
