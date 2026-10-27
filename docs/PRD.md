# Product requirements (PRD)

What we build, for whom, and how we know it is done. The course requirements are in `docs/BRIEF.md` (Sprint 2) and `docs/BRIEF_SPRINT3.md` (Sprint 3); the technical design is in `docs/ARCHITECTURE.md`. The Sprint 2 decisions below were made by the owner on 2026-10-19; the Sprint 3 decisions ("Sprint 3: the agent (coach-first workspace)") on 2026-10-25.

## Goal

A chatbot that gives adults who lift weights clear, evidence-based nutrition answers with their sources, and turns their own numbers into personal targets (energy, macros) and food facts. Sprint 3 turns it into a coach-first workspace: a coach invites gymers, follows their nutrition and training, and approves the weekly reviews an AI agent drafts (section "Sprint 3" below). The Sprint 2 sections that follow describe what Sprint 2 built and stay as its record.

## Users and scope

- **For:** healthy adults (18+) doing recreational strength training who want to gain muscle, lose fat or maintain.
- **Out of scope:** minors, pregnancy, medical conditions and medication, competitive weight cuts, professional endurance sport, meal delivery or shopping.
- **Language:** English first (answers, UI and sources). German UI and answers are an extra (Epic 7, owner's decision 2026-10-20); the sources stay English.
- **Deadline:** submission on **2026-11-02** (Sprint 2); Sprint 3 on **2026-11-23**.

## Features (MVP)

1. **Chat with sources.** The user asks a question; the answer cites the approved sources it used (`[S1]`...) and lists them with title, year, evidence tier, licence and link. Serves core 1 and 5, Easy 3.
2. **Query translation and structured retrieval.** Each question is rewritten into a few variants and filtered by topic, year and evidence tier; the UI shows the rewrites and filters. Serves the brief's advanced RAG requirement (and partly Easy 2).
3. **Hybrid search.** Vector search plus keyword search, merged. Serves Hard 1.
4. **Profile.** Weight, height, age, sex, activity level and goal, entered in the sidebar. For a guest, kept for the session only, never stored. Since Sprint 3 (T9.6), a signed-in gymer's saved profile is kept in the local store as dated entries (the weight as a dated body measurement), with the targets worked out from it; T9.5 adds the sign-in and the Save that writes them. The privacy change below says what is stored and who sees it.
5. **Tools** (core 2, at least 3):
   1. `calculate_tdee`: daily energy needs from the profile (uses personal data).
   2. `calculate_macro_targets`: protein, carbohydrate and fat targets from the profile, goal and TDEE (uses personal data); enforces the calorie floor.
   3. `lookup_food_nutrition`: nutrients of a food and amount from USDA FoodData Central (no personal data).
   4. `evaluate_meal_plan` (optional, only if time allows): compares a list of foods with the targets.
6. **Tool results shown** as a table and a macro chart. Serves core 5 and Medium 6.
7. **Units setting.** kg and cm by default; the user can switch to lb and ft/in. Internally everything stays in kg and cm.
8. **Session summary as PDF.** A download button builds a PDF (profile, targets, questions and answers with sources, disclaimer, credits) in memory; nothing is kept on the server. Serves Medium 7 and Easy 1 (extra beyond the minimum).
9. **Token usage and cost** per answer and per session. Serves Medium 5.
10. **Progress indicator** for each step of a turn. Serves core 5.
11. **Security:** input validation, prompt injection protection, rate limit, the domain guardrails below. Serves core 3 and 4, Medium 3. Details in `docs/SECURITY.md`.
12. **English and German** (extra). A language switch in the header (EN | DE, default from the browser); UI text and answers in the chosen language, sources and food names in English; the guard and the guardrails work in both languages. Serves Hard 4.
13. **Light and dark mode** (extra). Both themes are defined; users switch in Streamlit's built-in menu (top right), and a sidebar hint says where. Beyond the brief (owner's request).

**Optional tasks for maximum points** (done first, with the core): Medium 3 and 6; Hard 1. **Extras** (after the core, still wanted): Medium 5, Medium 7, Hard 4 (English and German), and light and dark mode.

## Domain guardrails (core 3, approved by the owner)

- No dosing or use advice on steroids, SARMs or other performance-enhancing drugs.
- A minimum calorie floor enforced in the tool code (value taken from the approved sources, not invented): 1200 kcal/day, the top of the low-energy diet range in sources #1 and #9 (owner's choice in T4.2).
- Refuse or redirect for minors, pregnancy, medical conditions and medication, and signs of disordered eating.
- A visible "not medical advice" disclaimer.
- User input and retrieved text are data, not instructions; tool arguments are validated.

## Acceptance criteria (product level)

Each ticket in `docs/IMPLEMENTATION_PLAN.md` refines one or more of these into testable criteria.

| ID | Criterion |
|---|---|
| AC-1 | A nutrition question gets an answer that cites at least one approved source, and the "Sources" list shows title, year, tier, licence and link for each cited source. |
| AC-2 | When no relevant source is found, the app says the sources do not cover the question and cites nothing. |
| AC-3 | "How this answer was found" shows the query rewrites and the filters used. |
| AC-4 | Retrieval combines a vector list and a keyword list (RRF); a query with an exact term (e.g. "HMB") retrieves the source on that term. |
| AC-5 | The profile accepts values in the chosen units; ages under 18 and out-of-range values are rejected with a clear message. |
| AC-6 | Each of the three tools can be triggered from the chat, and its result appears as a table; macro targets also appear as a chart. |
| AC-7 | `calculate_macro_targets` never returns a calorie target below the calorie floor. |
| AC-8 | Switching units changes inputs and displayed values; converting there and back returns the same values (within rounding). |
| AC-9 | The PDF download contains the profile, targets, questions and answers with sources, the disclaimer and the credits; no file is written on the server. |
| AC-10 | Each turn shows a progress indicator, and the token use and cost of the turn and the session. |
| AC-11 | Empty, too long and injection inputs are rejected without any API call; the per-session rate limit works. |
| AC-12 | Requests for performance-enhancing drug dosing are refused; minors, pregnancy, medical and disordered-eating cases are redirected; the disclaimer is always visible. |
| AC-13 | A missing or invalid key, rate limiting, timeouts and a missing index give a clear message, never a crash, and the chat history stays intact. |
| AC-14 | Every knowledge base chunk comes from an approved CC BY source, `ATTRIBUTION.md` credits all of them, and the download script rejects a file without a CC BY or CC0 licence. |
| AC-15 | `ruff check .`, `ruff format --check .` and `python -m pytest -q` pass in CI with no API key. |
| AC-16 | (Extra) Switching EN/DE changes all UI text and the answer language; a German question retrieves English sources and cites them; German injection inputs and German high-risk requests are caught like English ones. |
| AC-17 | (Extra) The app offers Light, Dark and System appearance through Streamlit's built-in menu, the UI says where to find it, and the main screens are readable in both modes. |

## Sprint 3: the agent (coach-first workspace)

Decided by the owner on 2026-10-25 for the Sprint 3 project (`docs/BRIEF_SPRINT3.md`), which builds on this app. Submission on **2026-11-23**. It is a coach-first slice of the owner's longer-term product plan; what it leaves out moves to a later Capstone project (below). Technical decisions: `docs/ARCHITECTURE.md` D9-D21; tickets: Epic 9 in `docs/IMPLEMENTATION_PLAN.md`.

### Problem and why an agent

- **Problem:** coaches who follow gym clients' nutrition and training gather the data by hand from messages, spreadsheets and apps, and a weekly review of each client takes time; clients get feedback late. This is the owner's working assumption, not yet checked with coaches (interviews are planned for the Capstone).
- **How the app addresses it:** the client logs meals, workouts and weight in one place and chooses what the coach sees; the coach sees each client's week and gets a weekly review drafted by an agent, which the coach approves, edits or rejects before the client reads it.
- **Why an agent:** the review takes several steps the model should not do alone in one call: check access, compute the numbers, search the evidence, check the citations, and wait for a person. A LangGraph graph makes each step a node with its own rule and pauses where the coach decides. The chat is a tool-calling agent that decides whether to search the research, call a calculator or propose saving a preference.

### Users and roles

- **Coach:** one role for nutrition coaches and personal trainers. Qualifications are not verified, and the app says so.
- **Gymer:** the client, a healthy adult (18+) doing recreational strength training, as in Sprint 2.
- **Guest:** no account; the agent's chat (session memory, agentic search, the Sprint 2 tools) with nothing stored.
- **Demo users:** a synthetic coach and gymers, for a clone with no Google client (`DEMO_MODE`, off unless set, and only without an `[auth]` section).

One role per account, chosen at the first sign-in; no admin role. Out of scope as in Sprint 2, plus real client data (demos and tests use synthetic data only) and any public deployment.

### Features

**P0, needed for the submission** (numbering continues the Sprint 2 list):

14. **Sign-in** with Google (`st.login`), the role chosen once, a display name the user picks; guest and demo modes. Serves Sprint 3 Medium 4.
15. **Invitations and sharing:** the coach creates a single-use code and passes it on; the gymer accepts it and turns each scope on or off (nutrition, training, body); the gymer can revoke a scope or end the relationship at any time.
16. **Food and weight diary:** foods from the USDA table logged in grams with a nutrient snapshot; dated weight entries.
17. **Workout log:** a fixed exercise list we wrote ourselves; sessions with sets of reps, kg and an optional RPE.
18. **Dashboards:** the coach's client list and one client's week (only what that client shares); the gymer's own week and approved reviews. A day with no entries shows as "not logged", never as "ate nothing".
19. **Weekly review:** an agent workflow drafts observations, hypotheses and recommendations with citations; the coach approves, edits or rejects it (human in the loop); only approved reviews reach the gymer.
20. **Agentic chat:** searching the knowledge base is one of the agent's tools, so a food or calculator question sends no research passages. Serves Sprint 3 Hard 1.
21. **Conversation memory:** the chat remembers earlier turns of the session; "New chat" starts a new conversation and deletes the old one; chats are never written to disk. Serves Sprint 3 Medium 2.
22. **Long-term memory:** for a signed-in user, the profile history, logs and targets, and preferences ("vegetarian") that the agent proposes with `remember_preference` and the user approves before anything is saved. Serves Sprint 3 Medium 2.
23. **My data:** export everything as JSON, delete one entry or everything.

**P1, if time allows:** 24. logging by chat ("I had 150 g of oats"), saved only after the gymer approves; 25. a coach assistant (read-only tools over the coach's clients, a follow-up flag, coach-set targets within the calorie floor).

**Should, after P0:** LangSmith tracing with personal data masked (Sprint 3 Hard 2) and a Ragas or DeepEval report (Sprint 3 Hard 3). **Extras:** the USDA FoodData Central API (Sprint 3 Medium 3, Hard 5) and evaluation in CI (the Sprint 2 review, point 5).

**Sprint 3 optional tasks for maximum points** (at least 2 medium and 1 hard, from new work alone): Medium 2, Medium 4, Hard 1; Medium 1 and Medium 8 are kept from Sprint 2.

### Guardrails added in Sprint 3

- Every domain guardrail above applies to gymers and coaches alike.
- **Training is reported as facts only** (sessions, sets, volume, top weights): the knowledge base holds no approved training sources, so the app gives no training advice.
- A review never recommends an intake below the calorie floor and never makes a diagnosis; a recommendation without a citation is labelled as the model's suggestion, never as evidence.
- A coach reads a client's data only while the relationship is active and the scope is shared. This is checked in the data layer, not in the prompt or the UI.
- The model gets aggregates and "the client", never a name; the Google name, email and picture are never stored or logged.

### The privacy change

Until Sprint 3 the profile lived in the session only and was never written to disk. Since T9.6, for signed-in users, the app keeps the account (a keyed ID, the role and the display name), the profile history, weights, food and workout logs, targets, preferences, relationships and scopes, and reviews in a local SQLite file (`data/store/`, gitignored), and shares them with a coach only within the scopes the user turned on (T9.6 builds the store; T9.5 and later tickets write to it):

- **Who sees what:** a user always sees their own records (profile entries, weights, logs, targets, preferences); reviews as below. A coach sees a gymer's data only while their relationship is active and the gymer shares the scope: **body** (weights and profile entries), **nutrition** (food log, targets and the reviews that coach wrote) or **training** (workouts). Sharing a scope shows all of its data, the days logged while it was off included. A weekly review counts as nutrition: the week's metrics in it, the weight trend and training volume included (T9.16), stay readable by the coach while nutrition is shared, even if body or training is turned off; T9.16 makes a review readable only while every scope its metrics used is shared (owner's choice, 2026-10-27). Preferences are never shared with a coach. A gymer sees only the approved reviews about them, never the model's draft. Everything else gets the same "not found" (owner's choices, 2026-10-27).
- **Audit:** every coach read of a client's data and every review decision leaves an audit row with who, what kind of data, about whom and when, never a value.
- **Export:** a user exports all their rows as JSON: their records, relationships and scopes, the audit rows by or about them, and the reviews they may read (a gymer the approved reviews about them, without the model's draft; a coach the reviews they wrote about clients who still share nutrition, and each such client gets an audit row). A gymer's pending or rejected reviews are not in the export; the owner accepts this as meeting AC-34 (2026-10-27).
- **Delete:** a user deletes all of it: their records, relationships and scopes, the reviews about them and those they wrote as a coach, and the audit rows by or about them. So when a coach deletes their account, the approved reviews their clients were reading go too. Deleted rows are overwritten in the database file (not in SQLite's temporary journal). The screens come with T9.5 ("My data").
- **Not settled yet (Capstone, before any real user):** the stored data is health data (GDPR Art. 9), so storing it for real users needs explicit consent, separate from sharing a scope with a coach (the `consents` table records the sharing scopes, not that consent); there is no retention period yet (rows stay until the user deletes them, ended relationships, revoked scopes, expired invitations and audit rows included); whoever runs the app is the controller of what it stores, and a coach who uses it for paying clients may be one too. Until then the app holds synthetic data only.
- **Limits:** the file is not encrypted, so anyone who can read it (a shared computer account, a copy of the file, a backup) reads the data; demos and tests use synthetic data only, and the sidebar will ask not to enter real health data (T9.5).

The rule (`.claude/rules/security-privacy.md`), feature 4 and `docs/SECURITY.md` were updated in the same PR. Chats stay in memory only; guests are unchanged. The app stays local: a public deployment needs a privacy notice and a GDPR review first (Capstone).

### Acceptance criteria (product level, Sprint 3)

| ID | Criterion |
|---|---|
| AC-18 | A user signs in with Google, chooses Coach or Gymer once, and lands on that role's home. |
| AC-19 | Without an `[auth]` section the sign-in is hidden: a guest can use the chat with nothing stored, and demo mode (synthetic users only) works when `DEMO_MODE` is on. |
| AC-20 | A coach-client relationship is active only after the gymer accepts a valid, unexpired, unused code. |
| AC-21 | A coach reading a client who is not theirs, not active or not shared gets the same "not found", through the data layer and through every agent tool. |
| AC-22 | Revoking a scope blocks the next read and any pending review that needs it. |
| AC-23 | 150 g of a food stores exactly 1.5 times its per-100 g values, and the snapshot stays the same when the food table changes. |
| AC-24 | Saved workout sets persist and show with the right volume. |
| AC-25 | The weekly metrics use the chosen week in `Europe/Berlin` time. |
| AC-26 | Three logged days out of seven are reported as "3 of 7 days logged" and averaged over those three days, never as four days without eating. |
| AC-27 | A review cites only chunks retrieved for that review. |
| AC-28 | A review passes the schema check, starts as PENDING_REVIEW, and the graph is paused before anything is released. |
| AC-29 | Approve, edit and reject store the reviewer and the time and write an audit row; only approved reviews reach the gymer. |
| AC-30 | A model timeout or error saves no review, loses no log entry and shows a clear message. |
| AC-31 | The chat remembers earlier turns of the session; "New chat" starts a new conversation and deletes the old one from memory; nothing of the chat is on disk. |
| AC-32 | A food question makes no knowledge base search; a research question searches and cites. |
| AC-33 | No log line or trace holds a question, an answer, a profile value or a logged value (canary tests). |
| AC-34 | A user exports all their data as JSON and deletes all of it. |
| AC-35 | A review never recommends an intake below the calorie floor and gives no training advice. |
| AC-36 | A preference is saved only after the user approves it, and it reaches the model inside a delimited `<memories>` block, never in the system prompt. |
| AC-37 | (P1) A food or weight typed in the chat is saved only after the gymer approves the proposal. |

### Beyond the brief (owner's request)

The coach role, invitations and sharing, the workout log and the dashboards. Neither brief asks for them; they give the agent its users and its problem (Sprint 3 core 1 and 2).

### Moved to the Capstone

PostgreSQL (and pgvector instead of Chroma), a REST API, separate nutrition coach and personal trainer roles, accounts with several roles, email invitations, an admin role, asynchronous review jobs, meal plans, workout programs, messaging, recipes and shopping lists, food scanning, health devices, billing, chat summaries in long-term memory, a 375 px phone layout and a WCAG 2.2 AA review, Docker and a staging environment, EU hosting, a GDPR assessment, and interviews and pilot metrics with real coaches. The frontend is open: the Sprint 3 brief allows Streamlit or Next.js, so another framework needs the Capstone brief's approval. Open Food Facts stays excluded at every stage (ODbL, `docs/SOURCES.md`).

## Content ownership

The owner drafts the system prompt(s) and the evaluation questions; Claude reviews them (as in Sprint 1). In Sprint 3 that includes the agent's answer prompt (O8) and the weekly review and coach assistant prompts (O15).

## Beyond the brief (owner's request)

- The repo is the owner's personal, public portfolio project, viewed by recruiters and possibly opened as open source later; it is copied into the course repository for the review.
- Because of that, a strict copyright policy applies (`.claude/rules/copyright.md`): open licences only (public domain, CC0, CC BY), nothing that needs permission, licence checked on the article itself, text only, attribution, raw documents not committed. The brief only asks for a relevant knowledge base.
- Light and dark mode (T7.3). German support (T7.1, T7.2) is an optional task in the brief (Hard 4) but goes beyond this PRD's original English-only scope.
- Sprint 3: the coach role, invitations and sharing, the workout log and the dashboards (section "Sprint 3" above).

## Open items

- Deployment: the app runs locally for the review; a public demo comes later (`docs/DEPLOYMENT.md`).
- The repo's own code licence (e.g. MIT). Without one, others may view the code but not reuse it.
- The Capstone project: the parts of the owner's product plan that Sprint 3 leaves out ("Moved to the Capstone" above).
