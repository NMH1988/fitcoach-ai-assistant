# Architecture

**Status:** approved by the owner on 2026-10-19, including decisions **D1-D8** (section 13). Inputs: `docs/BRIEF.md` (course requirements), `docs/PRD.md` (product decisions), `docs/SOURCES.md` (approved sources), `.claude/rules/` (rules).

**Models** (the Sprint 1 list, reused by choice; the Sprint 2 brief names none): `openai/gpt-5-mini` (default for answers), `openai/gpt-5-nano` (query translation), `openai/gpt-5` (selectable). Embeddings: `qwen/qwen3-embedding-8b`. All through OpenRouter. Checked on OpenRouter's model lists on 2026-10-19: all are listed; the three chat models support tool calling and none supports `temperature`.

## 1. Overview

```mermaid
flowchart LR
    U[User] --> UI[Streamlit UI<br/>chat, profile, settings]
    UI --> G[Input guard<br/>validation, injection, rate limit]
    G -->|rejected| UI
    G --> QT[Query translation<br/>multi-query + filters]
    QT --> HR[Hybrid retrieval<br/>Chroma vectors + BM25, RRF]
    HR --> AG[Answer step<br/>LLM + tool loop]
    AG <--> T[Tools<br/>TDEE, macros, food lookup]
    T --- USDA[(USDA foods table)]
    HR --- KB[(Chroma index<br/>CC BY chunks)]
    AG --> UI
    QT -.-> OR{{OpenRouter}}
    AG -.-> OR
    HR -.->|query embedding| OR
```

One chat turn runs a fixed pipeline: guard, query translation, hybrid retrieval, then an answer step in which the model may call tools. The UI shows the answer with its sources, the tool results, the retrieval steps and the token cost.

## 2. One chat turn, step by step

1. **UI** receives the message. A `st.status` box shows each step while it runs (the brief's progress indicator).
2. **Input guard** (`src/guard.py`), before any API call: raw input over `MAX_RAW_INPUT_CHARS` is rejected before anything else; then the text is cleaned (Unicode NFC, control and invisible characters dropped, trimmed; this is the text the model gets) and checked for empty or too long input (`MAX_INPUT_CHARS`, after cleaning) and for prompt-injection patterns, which run on NFKC-folded copies (with invisible characters removed and as spaces, and with accents stripped) (English; instruction overrides, requests for the hidden prompt, role changes and jailbreak phrases, fake role markers and look-alikes of our `<user_input>`/`<sources>` delimiters), and last the per-session rate limit (`RateLimiter`, kept in `st.session_state`). The rate limit counts accepted questions, one per turn however many model calls the turn makes; rejected input does not count. Rejected input makes no API call and gets a fixed message that never quotes it. The turn runs through `run_guarded(text, limiter, call)`, which calls the rest of the turn with the cleaned text only when the guard accepts it.
3. **Query translation** (`src/rag/query_translation.py`): one call to a small model (`openai/gpt-5-nano`) with structured output: 3 rewrites of the question plus optional filters (`topics`, `min_year`, `evidence_tier`). Skipped filters mean "no filter".
4. **Hybrid retrieval** (`src/rag/retriever.py`): for each rewrite, a vector search in Chroma and a BM25 keyword search, both with the same metadata filter. All ranked lists are merged with Reciprocal Rank Fusion (RRF); the top 6 distinct chunks become the context. If nothing passes the filter, the search runs again without it; if still nothing, the answer says the sources do not cover the question.
5. **Answer step** (`src/chat.py`): the chat model (default `openai/gpt-5-mini`) gets the owner's system prompt, the profile summary (if the user filled it in), the retrieved chunks inside a delimited `<sources>` block labelled `[S1]`...`[S6]`, and the user's message inside `<user_input>`. It can call tools; the loop stops after at most 4 tool rounds.
6. **Result** back to the UI: the answer with `[S1]`-style citations, a "Sources" expander (title, year, tier, licence, link, the chunk), a "Tool results" expander (table and chart), a "How this answer was found" expander (rewrites and filters), and the token use and cost of the turn.

## 3. Folder layout

```
app.py                      Streamlit UI only (thin)
src/
  config.py                 models, limits, calorie floor, k values, paths, get_api_key()
  guard.py                  input validation, injection checks, rate limit
  llm.py                    chat and embedding clients for OpenRouter, error mapping
  profile.py                UserProfile model (Pydantic), validation ranges
  units.py                  kg/lb and cm/ft-in conversion
  chat.py                   one chat turn: guard -> retrieve -> answer loop -> TurnResult
  usage.py                  token counting and cost from OpenRouter prices
  export_pdf.py             session summary PDF, built in memory
  rag/
    sources.py              manifest model, licence and DOI check on article XML, ATTRIBUTION.md text
    ingest.py               JATS XML -> text sections -> chunks with metadata
    store.py                build and open the Chroma collection
    query_translation.py    rewrites + filters (structured output)
    hybrid.py               BM25 index and Reciprocal Rank Fusion
    retriever.py            the retrieval pipeline used by chat.py
  tools/
    energy.py               calculate_tdee, calculate_macro_targets
    food.py                 lookup_food_nutrition
    meal_plan.py            evaluate_meal_plan (optional)
    registry.py             LangChain tool wrappers and argument schemas
scripts/
  download_sources.py       fetch article XML listed in the manifest, check the licence
  generate_attribution.py   write ATTRIBUTION.md from the manifest
  build_index.py            chunk, embed and write the Chroma index
  prepare_usda.py           turn the USDA Foundation Foods CSV into a small foods table
  live_check_llm.py         owner's live check: one real chat and one real embedding call
data/
  sources.json              manifest of approved sources (committed)
  usda_foods.csv            trimmed USDA table (committed, CC0)
  raw/                      downloaded article XML (gitignored)
chroma/                     vector index (gitignored, rebuilt by the script)
ATTRIBUTION.md              credits for every source, generated from the manifest
tests/
```

## 4. Knowledge base pipeline

**Manifest** (`data/sources.json`): one entry per approved source with `id`, `title`, `authors`, `year`, `journal`, `doi`, `pmcid`, `url`, `license`, `license_url`, `copyright_notice`, `evidence_tier`, `topics`, and for a correction notice `corrects` (the ID of the article it corrects, e.g. #18a corrects #18) (`src/rag/sources.py` validates them). Title, authors, DOI and copyright notice come from each article's own front matter; `url` is the DOI link. There is no `fetch_url`: the script builds the Europe PMC URL from the checked PMCID, so the manifest cannot point it anywhere else. `ATTRIBUTION.md` is generated from it (`scripts/generate_attribution.py`); a test fails while the committed file is out of date.

**Download** (`scripts/download_sources.py`):
- Articles with a PMCID come from the Europe PMC REST API as JATS XML (`https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML`). Tested on 2026-10-19 for PMC5477153: HTTP 200, XML with a `<license>` element.
- Source #1 (diets for body weight reduction, 2026) had no PMCID at first; by T2.1 (2026-10-19) Europe PMC had it as PMC13665703, so it is downloaded like the others and the hand-saved fallback was dropped. Scripted access to tandfonline.com is never used.
- **Access terms:** the script uses only the Europe PMC REST API (allowed for automated retrieval by Europe PMC's copyright page); it never scrapes the PMC, Europe PMC or publisher websites. It sends a descriptive User-Agent, waits between requests and never follows a redirect (a 3xx is an error), so no request leaves the REST API.
- **Copyright guard in code:** the script reads the `<license>` element of the article's own front matter (a link, an `ali:license_ref` or a URL in the text) and refuses the file if it names any other Creative Commons licence (NC, ND, SA), a machine-readable licence ID (`license/@xlink:href`, `ali:license_ref`) that is not Creative Commons, wording that contradicts CC BY ("NonCommercial", "NoDerivatives", "ShareAlike", "All rights reserved", "BY-NC"/"BY-ND"/"BY-SA", with any hyphen, a space or nothing between the parts; the `license-type` attribute counts too), a ported licence (e.g. `/by/3.0/us/`), no CC BY or CC0 licence, a licence other than the manifest's, or a DOI other than the manifest's. CC BY wins over CC0 when both appear (BioMed Central's CC0 waiver covers the data, not the text). A refused file is never written, an older copy of it is deleted, and the run exits with 1. Raw XML stays in `data/raw/<PMCID>.xml` (gitignored).

**Parsing** (`src/rag/ingest.py`, standard library `xml.etree`): `load_chunks()` reads `data/raw/<PMCID>.xml` for every manifest entry, runs the T2.1 licence and DOI check (`check_article()`) again, then parses. It keeps the article title, the abstract and the body sections (section titles, paragraphs, list items as "- " lines). It drops figures, tables, display formulas, supplementary material, the reference list, footnotes, labels and anything that carries its own `<permissions>` (third-party content), as the copyright policy requires (text only, rules 5 and 7). Inline formulas keep their plain text so sentences stay whole, with scripts, fences and accents written out (`I^2`, `β_x`, `P(>0)`, `R̂`); other superscripts are written as exponents too (`10^-3`, `kg^-1`), so numbers keep their meaning. The XML's own line breaks and indentation become single spaces. Numeric citation markers (`xref` to the reference list) are removed with the brackets they leave, and only those brackets (text brackets such as `(-)-epicatechin` stay); an author-year citation keeps its words. Passages credited to someone else (`<attrib>`) are dropped like those with their own `<permissions>`. Back matter that many articles put inside `<body>` (acknowledgements, funding, disclosures, author contributions, data availability, ethics, publisher's notes, supplementary, references, appendices) is dropped by `sec-type` or title (lists in `src/config.py`). `<back>`, `<floats-group>` and sub-articles are never read. A section is the innermost `<sec>` holding text; its title is the path of titles ("Protein timing > Pre-exercise"), abstract sections start with "Abstract", and paragraphs outside any section (the correction #18a) are titled "Main text". A missing, refused or empty article stops the build with an `IngestError` that lists every problem.

**Chunking:** `RecursiveCharacterTextSplitter` (langchain-text-splitters), at most 1,000 characters (`CHUNK_SIZE`, the section title included) with up to 150 overlap (`CHUNK_OVERLAP`), split inside a section so a chunk never mixes two sections. Each chunk text starts with its section title for context. Metadata per chunk: `source_id`, `title`, `authors`, `year`, `section`, `topics`, `evidence_tier`, `license`, `source_url`, `chunk_index` (from 0 across the article); `authors` and `topics` are lists, which chromadb 1.5.9 accepts. A correction's chunks also carry `corrects` and the corrected article's chunks `corrected_by` (a list), so answers can cite both (copyright policy rule 7); the keys are absent otherwise.

**Topics** (set per source in the manifest): `protein`, `carbohydrate`, `fat`, `energy_balance` (weight loss or gain), `nutrient_timing`, `supplements`.

**Embeddings and index** (`scripts/build_index.py`): `qwen/qwen3-embedding-8b` through OpenRouter, batched, written to a persistent Chroma collection in `chroma/`. A rough estimate for about 20 articles is a few hundred thousand tokens, which is well under one US cent at the listed price ($0.01 per million tokens on 2026-10-19). The index is built once and rebuilt only when the sources change.

**BM25 index:** built in memory at app start from the chunk texts stored in Chroma, cached with `st.cache_resource`.

## 5. Query translation and structured retrieval

- **Why:** users ask short or vague questions ("bulk diet?"). Several rewrites ("energy surplus for muscle gain", "protein intake during a bulking phase", ...) find chunks that one phrasing would miss.
- **How:** one structured-output call returns `{"queries": [3 strings], "topics": [...], "min_year": int | null, "evidence_tier": 1 | 2 | null}`. The filters are the brief's "structured retrieval": Chroma's `where` filter and the same filter on the BM25 candidate set.
- **Hybrid search (Hard 1):** vectors catch meaning, BM25 catches exact terms (food names, "HMB", "creatine monohydrate"). RRF merges the ranked lists without needing comparable scores: each chunk scores the sum of `1 / (60 + rank)` over the lists it appears in.

## 6. Tools

| Tool | Input (validated with Pydantic) | Output | Personal data | Where the numbers come from |
|---|---|---|---|---|
| `calculate_tdee` | weight kg, height cm, age, sex, activity level | BMR and TDEE in kcal | yes (profile) | Mifflin-St Jeor equation and standard activity factors (equations are facts, not copyrighted text); the ticket confirms the factors |
| `calculate_macro_targets` | weight kg, goal, TDEE | kcal target, protein/carb/fat in g and % | yes (profile) | ranges from approved sources (e.g. #7 protein, #1 and #9 energy balance), read when the ticket starts; enforces the calorie floor |
| `lookup_food_nutrition` | food name, amount in g | kcal, protein, carbs, fat, fiber, plus the matched USDA name and close alternatives | no | USDA FoodData Central Foundation Foods (CC0), fuzzy name match with rapidfuzz |
| `evaluate_meal_plan` (optional) | list of food + amount, targets | totals vs targets, gaps | uses the targets | the two tools above |

- The profile is read from `st.session_state` by the app and passed to the tools; the model may not change it. If the profile is missing, the tool returns "profile needed" and the UI points to the profile form.
- Tool errors come back to the model as a short message (not a crash), and the UI shows them.
- **USDA data:** the Foundation Foods CSV zip (about 3.8 MB, release 2026-04-30, checked 2026-10-19) is turned by `scripts/prepare_usda.py` into `data/usda_foods.csv` (description and per-100 g values). CC0 allows committing it, which keeps tests and deployment simple. No data.gov key is needed.

## 7. User interface

- **Sidebar:** "Your profile": the goal as a segmented control, the profile as small tiles in the chosen units, and an "Edit details" button that opens the profile form in an `st.dialog` (T4.1, owner's choice). The form has one Metric / Imperial switch (kg and cm, or lb and ft/in); switching converts the values already typed, and Save checks them with `src/profile.py`. Later tickets may add a collapsed developer section with the model choice, the session token use and cost, and a link to the sources and credits. Where each piece sits is in `docs/UI_DESIGN.md`.
- **Main area:** the chat. Under each answer: "Sources", "Tool results" (table and a bar chart of the macro split), "How this answer was found".
- **Progress:** `st.status` with the steps "Checking your question", "Rewriting the question", "Searching the research", "Writing the answer", "Running tool: ...".
- **PDF download:** a button builds the session summary (profile in the chosen units, computed targets, the questions and answers with their sources, the disclaimer, the credits) with reportlab in memory and hands it to `st.download_button`.

## 8. Security

The threat model and every control are in `docs/SECURITY.md`. In short: the guard runs before any API call; user input and retrieved text are delimited data (Medium 3); tool arguments are validated with Pydantic ranges (e.g. weight 30-300 kg, height 120-230 cm, age 18-100; `config.PROFILE_*_RANGE`); the calorie floor and age limit live in code; output is Markdown without raw HTML; one `get_api_key()`; model allowlist, capped `max_tokens`, at most 4 tool rounds, per-session rate limit.

## 9. Token usage and cost (Medium 5)

Each LLM call (query translation, every answer round) reports its token use (`usage_metadata`); the query embedding is counted too. `src/usage.py` multiplies by the prices from OpenRouter's models endpoint (cached for a day; "price unknown" if the call fails) and keeps per-turn and per-session totals in `st.session_state`.

## 10. Error handling

| Situation | What the user sees |
|---|---|
| No API key | A setup message, no crash |
| 401 (bad key) | "The OpenRouter API key was rejected"; not retried by default |
| 402 (no credit) | "The OpenRouter account is out of credit"; not retried by default |
| 429 / timeout (ours or a 408) / 5xx | Retried up to `LLM_MAX_RETRIES` (2) times by the OpenAI SDK, then a message of its own for each: too many requests, took too long, temporarily unavailable |
| A 200 reply carrying an error, no result, or an empty or cut-off body (provider failed mid-request) | "Temporarily unavailable", like a 5xx |
| Structured output stopped by the token limit | "The answer was cut off" |
| Structured output that fails its schema (wrong or missing field, not JSON), is refused by the model, or comes back empty | "Not in the expected format" (`InvalidReplyError`, separate from an outage so a caller can fall back) |
| Service unreachable, other SDK errors (e.g. a content filter) | "Could not reach the model service" / a generic "try again" |
| Chroma index missing | "Run `python scripts/build_index.py` first" |
| No relevant chunks | "Our sources do not cover this"; no invented citation |
| Tool error or bad arguments | The tool's message, the turn continues |
| Failure mid-answer | Chat history stays intact |

The mapping lives in `src/llm.py`: callers wrap a model or embedding call in `with mapped_errors():`, which turns any OpenAI SDK error, and a malformed reply the client could not read, into an `LLMError` subclass whose message is fixed text (never the server's response, so never the key) and drops the original from the traceback. The original stays on `__context__` and its request holds the key, so it is never logged or shown; each `LLMError` carries a `diagnostic` instead (the error type and the function that raised it, no message text), which is safe to log. Malformed replies raise plain `ValueError`/`KeyError`/`TypeError`, so those are mapped only when the traceback passes through `openai` or `langchain_openai`; a bug of ours that langchain raises is mapped too, and the diagnostic shows where it came from. Each request has a `LLM_TIMEOUT_SECONDS` (60) timeout. Clients are built only through `src/llm.py`, and `model` and `max_tokens` are never passed at call time or changed on a built client (`.claude/rules/security-privacy.md`), so the allowlist and the cap are not bypassed as long as that rule is followed; no code or test enforces it.

## 11. Testing

Full strategy in `docs/TESTING.md`. In short: unit tests for pure logic; integration tests with `DeterministicFakeEmbedding` (langchain-core) and Chroma in a temp dir, and the tool loop with a scripted fake chat model that returns tool calls; UI tests with `streamlit.testing.v1.AppTest`; no network and no key in CI. Each tool has known-answer tests (e.g. TDEE for a fixed profile), unit conversion is tested both ways, RRF has a hand-computed example.

## 12. Dependencies

Checked on PyPI on 2026-10-19. Licences are permissive, as the copyright policy prefers.

| Package | Version | Licence | Use |
|---|---|---|---|
| streamlit | 1.66.0 | Apache-2.0 | UI |
| langchain | 1.4.6 | MIT | framework |
| langchain-openai | 1.7.2 | MIT | chat and embeddings through OpenRouter's OpenAI-compatible API |
| langchain-chroma | 1.1.0 | MIT | vector store integration |
| chromadb | 1.5.9 | Apache-2.0 | vector store, embedded only (pulls in onnxruntime, MIT, which we do not use for embeddings). Four unfixed advisories in its HTTP server are an accepted risk: `docs/SECURITY.md` |
| langchain-text-splitters | 1.1.3 | MIT | chunking |
| openai | 3.35.1 | Apache-2.0 | the SDK under langchain-openai; pinned in T1.2 because `src/llm.py` maps its error classes and relies on its retries |
| rank-bm25 | 0.2.2 | Apache-2.0 | BM25 (small and stable; last release 2022) |
| rapidfuzz | 3.14.6 | MIT | fuzzy food-name match |
| reportlab | 5.0.1 | BSD | PDF |
| pydantic | 2.14.1 | MIT | schemas |

Dev (as in Sprint 1, pinned in the `dev` extra): pytest 9.1.1 (MIT), pytest-cov 7.1.0 (MIT), ruff 0.17.1 (MIT), pip-audit 2.10.1 (Apache-2.0), and httpx2 2.14.0 (BSD-3-Clause; the OpenAI SDK's HTTP library, whose `MockTransport` the T1.2 tests use). Not chosen: fpdf2 (LGPL-3.0, not permissive). Python **3.14** as in Sprint 1; every package above has a wheel or pure-Python build for it.

## 13. Decisions (approved by the owner on 2026-10-19)

| # | Decision | Alternative considered | Why |
|---|---|---|---|
| D1 | **Always retrieve** before answering (fixed pipeline) | Retrieval as a tool the model may call | Every answer is grounded and cites sources; matches the brief's flow (retrieval, then reasoning and tools); easier to explain and test |
| D2 | **Own tool loop** with `bind_tools`, max 4 rounds | LangChain v1 `create_agent` | Each step is visible and testable with a fake model; the round limit is explicit |
| D3 | **langchain-openai** (`ChatOpenAI`, `OpenAIEmbeddings`) with OpenRouter's base URL | `langchain-openrouter` (official integration, v0.2.9) | Matches the brief's "OpenAI-compatible SDK" and Sprint 1; one package for chat and embeddings |
| D4 | **Own RRF + rank-bm25** for hybrid search | `EnsembleRetriever` (now in `langchain-classic`) | About 20 lines we can explain in the review; no legacy package |
| D5 | **reportlab** for the PDF | fpdf2 | BSD vs LGPL-3.0 |
| D6 | **gpt-5-nano** for query translation, **gpt-5-mini** for answers | One model for both | The rewrite step is simple; cheaper and faster |
| D7 | Commit the manifest and the trimmed USDA table; do not commit raw XML or the Chroma index | Commit the index | Copyright policy rule 8 (raw documents not committed); the index is cheap to rebuild |
| D8 | Python 3.14 | 3.13 | Same as Sprint 1; all dependencies support it. Check the host's Python options at deploy time |

## 14. Risks and early checks

- **Embeddings through OpenRouter with `OpenAIEmbeddings`:** by default it may send token arrays instead of text, which OpenRouter may not accept; set `check_embedding_ctx_length=False`. Set in T1.2 (`src/llm.py`, and a unit test checks the raw text goes out); confirmed by one live call run by the owner (O5, `scripts/live_check_llm.py`).
- **Source #1 download:** resolved in T2.1 (Europe PMC has it); see section 4.
- **gpt-5 models:** no `temperature`; reasoning tokens add cost, so `max_tokens` and the reasoning effort (`low`, T1.2) are set in config.
- **Long waits:** the OpenAI SDK honours a server's `Retry-After` up to 2 minutes per retry, so in the worst case one call waits about 7 minutes (3 timeouts of 60 s plus 2 waits of 120 s) before the error shows, and a turn makes several calls. The 60 s limit applies to each phase of a request (connect, each read), not the whole request: a server that keeps sending bytes (e.g. keep-alive whitespace) could keep one request open longer, so 7 minutes is not a hard limit. Not observed with OpenRouter so far. Abandoned requests after our timeout may still be billed by the provider. Accepted in T1.2; lower `LLM_MAX_RETRIES` or the timeout if it is a problem in practice.
- **Deadline (2026-11-02, 14 days):** if time runs short, cut in this order: `evaluate_meal_plan`, the PDF (or its styling), token cost, chart polish. The core requirements and the optional tasks for maximum points (Medium 3, 6; Hard 1) come first (`docs/IMPLEMENTATION_PLAN.md`).

## 15. Brief coverage

| Brief item | Where |
|---|---|
| Core 1: RAG, embeddings, chunking, similarity search | sections 4-5 |
| Advanced RAG: query translation, structured retrieval | section 5 |
| Core 2: at least 3 tools | section 6 |
| Core 3: domain, focused KB, domain prompts, security | `docs/PRD.md`, `docs/SOURCES.md`, `docs/SECURITY.md` |
| Core 4: LangChain + OpenRouter, error handling, input validation | sections 2, 8, 10 |
| Core 5: UI with sources, tool results, progress | section 7 |
| Medium 3 prompt injection, Medium 5 tokens and cost, Medium 6 tool result charts | sections 8, 9, 7 |
| Hard 1 hybrid search | section 5 |
| Medium 7 PDF export (extra) | section 7 |
