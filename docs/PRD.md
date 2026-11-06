# Product requirements (PRD)

What we build, for whom, and how we know it is done. The course requirements are in `docs/BRIEF.md` (Sprint 2) and `docs/BRIEF_SPRINT3.md` (Sprint 3); the technical design is in `docs/ARCHITECTURE.md`. The Sprint 2 decisions below were made by the owner on 2026-10-19; the Sprint 3 decisions ("Sprint 3: the agent (coach-first workspace)") on 2026-10-25, and the training principles (feature 26, T9.19 and T9.20) on 2026-10-26; the coach-first rework (the AI serves the coach, a gymer has no AI chat; T9.24) on 2026-11-02.

## Goal

A chatbot that gives adults who lift weights clear, evidence-based nutrition answers with their sources, and turns their own numbers into personal targets (energy, macros) and food facts. Sprint 3 turns it into a coach-first workspace: a coach invites gymers, follows their nutrition and training, and approves the weekly reviews an AI agent drafts, which the gymer then reads; the AI serves the coach (and guests), and a gymer logs their own data with no AI chat (T9.24); the agent also explains evidence-based resistance training principles with their sources, but writes no training programs (section "Sprint 3" below). The Sprint 2 sections that follow describe what Sprint 2 built and stay as its record.

## Users and scope

- **For:** healthy adults (18+) doing recreational strength training who want to gain muscle, lose fat or maintain.
- **Out of scope:** minors, pregnancy, medical conditions and medication, competitive weight cuts, professional endurance sport, meal delivery or shopping.
- **Language:** English first (answers, UI and sources). German UI and answers are an extra (Epic 7, owner's decision 2026-10-20); the sources stay English.
- **Deadline:** submission on **2026-11-02** (Sprint 2); Sprint 3 on **2026-11-23**.

## Features (MVP)

1. **Chat with sources.** The user asks a question; the answer cites the approved sources it used (`[S1]`...) and lists them with title, year, evidence tier, licence and link. Serves core 1 and 5, Easy 3.
2. **Query translation and structured retrieval.** Each question is rewritten into a few variants and filtered by topic, year and evidence tier; the UI shows the rewrites and filters. Serves the brief's advanced RAG requirement (and partly Easy 2).
3. **Hybrid search.** Vector search plus keyword search, merged. Serves Hard 1.
4. **Profile.** Weight, height, age, sex, activity level and goal, entered in the sidebar. For a guest, kept for the session only, never stored. Since Sprint 3 (T9.6), a signed-in gymer's saved profile is kept in the local store as dated entries (the weight as a dated body measurement), with the targets worked out from it; T9.5 added the sign-in and the Save that writes them (and the goal control, which adds an entry and a target without a weight; owner's choice, 2026-11-02). The privacy change below says what is stored and who sees it.
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
12. **English and German** (extra). A language switch at the end of the sidebar, "Language" with "English | Deutsch" (default from the browser; in the header as EN | DE until T9.23, owner's decision, 2026-10-30); UI text and answers in the chosen language, sources and food names in English; the guard and the guardrails work in both languages. Serves Hard 4.
13. **Light and dark mode** (extra). Both themes are defined; users switch in Streamlit's built-in menu (top right), and a sidebar hint says where. Beyond the brief (owner's request).

**Optional tasks for maximum points** (done first, with the core): Medium 3 and 6; Hard 1. **Extras** (after the core, still wanted): Medium 5, Medium 7, Hard 4 (English and German), and light and dark mode.

## Domain guardrails (core 3, approved by the owner)

- No dosing or use advice on steroids, SARMs or other performance-enhancing drugs.
- A minimum calorie floor enforced in the tool code (value taken from the approved sources, not invented): 1200 kcal/day, the top of the low-energy diet range in sources #1 and #9 (owner's choice in T4.2).
- Refuse or redirect for minors, pregnancy, medical conditions and medication, and signs of disordered eating; since T9.19a also pain, injuries and rehabilitation (Sprint 3, AC-39).
- A visible "not medical advice" disclaimer; since T9.20 it also says the app explains training principles from research but writes no training programs, replaces no coach or physiotherapist, and that its answers are generated by an AI model and should be checked against the sources (AC-41).
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

Decided by the owner on 2026-10-25 for the Sprint 3 project (`docs/BRIEF_SPRINT3.md`), which builds on this app. Submission on **2026-11-23**. It is a coach-first slice of the owner's longer-term product plan; what it leaves out moves to a later Capstone project (below). Technical decisions: `docs/ARCHITECTURE.md` D9-D22 (D22, the training principles, added on 2026-10-26); tickets: Epic 9 in `docs/IMPLEMENTATION_PLAN.md`. Reworked by the owner on 2026-11-02 (T9.24), while trying T9.5's sign-in: the AI serves the coach; a gymer has no AI chat and no tools, logs their own data and reads what the coach approved.

### Problem and why an agent

- **Problem:** coaches who follow gym clients' nutrition and training gather the data by hand from messages, spreadsheets and apps, and a weekly review of each client takes time; clients get feedback late. This is the owner's working assumption, not yet checked with coaches (interviews are planned for the Capstone).
- **How the app addresses it:** the client logs meals, workouts and weight in one place and chooses what the coach sees; the coach sees each client's week and gets a weekly review drafted by an agent, which the coach approves, edits or rejects before the client reads it. The agent works for the coach: it drafts, the coach decides, and the client reads only what the coach approved (P1: and may ask the coach a question under it, feature 27); the client has no AI chat (owner's decision, 2026-11-02, T9.24).
- **Why an agent:** the review takes several steps the model should not do alone in one call: check access, compute the numbers, search the evidence, check the citations, and wait for a person. A LangGraph graph makes each step a node with its own rule and pauses where the coach decides. The chat (for guests and coaches) is a tool-calling agent that decides whether to search the research, call a calculator or the food lookup (the four Sprint 2 tools, with a profile kept for the session only, as a guest's is) or, for a coach, propose saving one of the coach's working preferences; from T9.17 (should), a coach's chat also reads the coach's clients (owner's decision, 2026-11-02: the coach keeps the chat T9.5 gives it).

### Users and roles

- **Coach:** one role for nutrition coaches and personal trainers. Qualifications are not verified, and the app says so. The AI agent works for the coach: the chat (the guest's chat as T9.5 builds it: the four Sprint 2 tools and the knowledge base search, with a session-only profile in the sidebar; plus long-term memory of the coach's working preferences, feature 22), the weekly review drafts (feature 19) and the coach assistant (feature 25, its client tools in the chat).
- **Gymer:** the client, a healthy adult (18+) doing recreational strength training, as in Sprint 2. No AI chat and no agent tools (owner's decision, 2026-11-02, T9.24; one accepted exception: a signed-in gymer whose store cannot be opened runs as a guest, with the guest's chat and nothing stored, after the stored profile leaves the session, T9.5, owner's decision, 2026-11-02): the gymer logs their own food, weight and workouts, chooses what the coach sees (scopes, revoke, end), edits their profile and language, exports or deletes their data (My data), and reads the weekly reviews the coach approved; everything the coach writes (reviews, coach-set targets) is read-only for the gymer. P1: asks the coach a question under an approved review (feature 27).
- **Guest:** no account; the agent's chat (session memory, agentic search, the Sprint 2 tools) with nothing stored. Only in a copy with no Google sign-in set up (a clone run with just the API key); once sign-in is set up, every visitor signs in (owner's choice, 2026-11-02, T9.5).
- **Demo users:** a synthetic coach and gymers, for a clone with no Google client (`DEMO_MODE`, off unless set, and only without an `[auth]` section).

One role per account, chosen at the first sign-in; no admin role. Out of scope as in Sprint 2, plus real client data (demos and tests use synthetic data only), any public deployment, and for training: personal programs, exercise technique coaching, and pain, injury or rehabilitation (feature 26).

### Features

**P0, needed for the submission** (numbering continues the Sprint 2 list):

14. **Sign-in** with Google (`st.login`), the role chosen once, a display name the user picks; guest and demo modes. Serves Sprint 3 Medium 4.
15. **Invitations and sharing:** the coach creates a single-use code and passes it on; the gymer accepts it and turns each scope on or off (nutrition, training, body); the gymer can revoke a scope or end the relationship at any time. A gymer has one coach at a time (owner's choice, 2026-11-03, T9.12): to change coach, the gymer ends the relationship first.
16. **Food and weight diary:** foods from the USDA table logged in grams with a nutrient snapshot; dated weight entries.
17. **Workout log:** a fixed exercise list we wrote ourselves; sessions with sets of reps, kg and an optional RPE.
18. **Dashboards:** the coach's client list and one client's week (only what that client shares); the gymer's own week and approved reviews, read-only. A day with no entries shows as "not logged", never as "ate nothing".
19. **Weekly review:** an agent workflow drafts observations, hypotheses and recommendations with citations; the coach approves, edits or rejects it (human in the loop); only approved reviews reach the gymer.
20. **Agentic chat** for the guest and the coach (a gymer has no chat, T9.24): searching the knowledge base is one of the agent's tools, so a food or calculator question sends no research passages. Serves Sprint 3 Hard 1.
21. **Conversation memory:** the chats of guests and coaches remember earlier turns of the session; "New chat" starts a new conversation and deletes the old one; chats are never written to disk. Serves Sprint 3 Medium 2.
22. **Long-term memory for the coach:** the coach's own working preferences ("keep answers short", "most of my clients are vegetarian") that the agent proposes with `remember_preference` and the coach approves before anything is saved; not for a client's personal or health data (each proposal is checked against the guardrails and the names of the coach's current and former clients, and the proposal card says so); guests and gymers have none (owner's decision, 2026-11-02, T9.24; was: for a signed-in user, the profile history, logs and targets, and preferences such as "vegetarian" that the gymer approves; the profile, logs and targets are still stored, features 4, 16 and 17). Serves Sprint 3 Medium 2.
23. **My data:** export everything as JSON, delete one entry or everything.

**P0, added on 2026-10-26** (numbered after features 24 and 25, the P1 items of that day, which keep their numbers; beyond the brief, so the first P0 feature cut if time runs short, as the plan says): 26. **Training principles with citations** (owner's decision, 2026-10-26): the agent answers general questions about resistance training for muscle and strength (volume, load and repetition range, proximity to failure, frequency, rest between sets, progression, exercise selection) from a set of approved, openly licensed training sources (`docs/SOURCES.md`, "Training sources"), and cites them. It gives the ranges a source gives, never a program built for the user (no weekly plan, no sets and reps per exercise for the user, no technique coaching). A weekly review may recommend a training change to the coach only with a citation. Pain, injury and rehabilitation questions are redirected before any model or embedding call, and the fixed message also tells the user to call the emergency number (112 in Germany and the EU) for sudden, severe or chest symptoms; the rejected message is not kept in the history a later turn sends to a model. Tickets T9.19a (the injury guard), T9.19 (the sources) and T9.20 (the behaviour in the chat).

**Should, after P0:** first 25. a coach assistant (read-only tools over the coach's clients, a follow-up flag, coach-set targets within the calorie floor, read-only for the gymer), raised from P1 to right after P0 by the owner on 2026-11-02 (T9.24), as the AI now serves the coach; then LangSmith tracing with personal data masked (Sprint 3 Hard 2) and a Ragas or DeepEval report (Sprint 3 Hard 3).

**P1, if time allows** (Sprint 3 if time allows, else the Capstone): 27. **Questions to the coach** (owner's decision, 2026-11-02, T9.25): under an approved weekly review, the gymer asks the coach a question and the coach answers in the app; one simple question-and-answer thread per review, stored with the review it belongs to (so the coach reads and answers it by the same rule as that review, T9.16: while the relationship is active and the client shares nutrition and every scope its metrics used), in both sides' export and deleted with their data, never sent to a model; no real time, no notifications of its own (a new question or answer can become a kind in feature 28's list later), no attachments (full messaging stays in the Capstone). Beyond the brief (owner's request).

**Moved to the Capstone by T9.24** (owner's decision, 2026-11-02; the number is kept): 24. logging by chat ("I had 150 g of oats"), saved only after the gymer approves, as a gymer has no chat.

**Extras:** the USDA FoodData Central API (Sprint 3 Medium 3, Hard 5) and evaluation in CI (the Sprint 2 review, point 5). Added on 2026-11-06 (owner's request; beyond the brief, the first extra cut if time runs short): 28. **In-app notifications** (T9.29): a signed-in user sees in the app what changed for them: a coach, that a gymer connected, started or stopped sharing a scope, or that the relationship ended; a gymer, that they are connected with their coach, that the coach approved a weekly review about them, or that the relationship ended. A notification shows only its kind, its time, the other side's display name, the scope and the week, never a value or a review's text, and only to a side who may already see that relationship or review; it shows on the page's next run (a bell with the unread count in the sidebar, a list, "Mark all as read"), with no email, push or real time; guests have none; when either side deletes their data, the other side's notifications about them go with it; whether or when a notification was read is seen only by its reader. Moved from the Capstone by the owner (2026-11-06); the realtime chat's notifications stay there.

**Sprint 3 optional tasks for maximum points** (at least 2 medium and 1 hard, from new work alone): Medium 2, Medium 4, Hard 1; Medium 1 and Medium 8 are kept from Sprint 2. After T9.24 none of them rests on a gymer's chat: Medium 2 is the guest's and coach's short-term memory (feature 21) and the coach's long-term memory (feature 22), Medium 4 the sign-in, roles and store (features 14 and 23), Hard 1 the agentic chat of the guest and the coach (feature 20).

### Guardrails added in Sprint 3

- Every domain guardrail above applies to every role: to the chat of guests and coaches, to the weekly review, and to what a gymer enters (the profile's age limit, for example); a gymer has no chat (T9.24), except as a guest when the store fails (below).
- **Training principles only, always cited** (feature 26; replaces the "facts only" rule of 2026-10-25, owner's decision of 2026-10-26): the logs and dashboards still show training as facts (sessions, sets, volume, top weights). The agent explains training principles only from approved training sources and cites them; a training claim it cannot cite is not made, and the agent says the sources do not cover it (stricter than nutrition, where an uncited recommendation in a review is labelled as the model's suggestion). It never writes a program for the user or coaches technique. A range is quoted with the population the source studied, and a recommendation to a named client in a review names a direction and the source's range, leaving the number for this client to the coach.
- **Pain, injury and rehabilitation** are redirected to a professional (a doctor or physiotherapist) by the input guard, before any model or embedding call, in English and German; the fixed message adds the emergency number (112) for sudden, severe or chest symptoms, and the rejected message is not sent to a model in a later turn through the history.
- **The answers are AI-generated:** the About text and the disclaimer say so and tell the user to check the sources (owner's decision, 2026-10-28, after the compliance review; the EU AI Act's transparency rules point the same way); the gymer sees a weekly review as an AI draft approved by the coach.
- A review must not recommend an intake below the calorie floor or make a diagnosis: the prompt forbids both, a check in code refuses the common wordings, and the coach, who approves every draft, is the first check (the code check's known limits are in `docs/SECURITY.md`); a nutrition recommendation without a citation is labelled as the model's suggestion, never as evidence (a training recommendation needs a citation, above).
- A coach reads a client's data only while the relationship is active and the scope is shared. This is checked in the data layer, not in the prompt or the UI.
- The model gets aggregates and "the client", never a name; the Google name, email and picture are never stored or logged. (The Capstone plan adds a text that is not an aggregate: the gymer's shared preferences, delimited, "Moved to the Capstone" below, T9.26.)
- A gymer has no chat, so none of a gymer's stored profile, logs or questions to the coach go to a model in a chat (T9.24): the app sends a gymer's stored details to a model only as the week's metrics, in a weekly review the coach starts (T9.16) and, from T9.17, through the coach assistant's `get_client_week` in the coach's chat, both within the scopes the gymer shares (the Capstone plans a third flow, a gymer's own preferences shared through an opt-in scope, "Moved to the Capstone" below, T9.26). Two other flows can bring a gymer's details to a model (compliance review of T9.24): a coach can type a client's details into the coach's chat or the coach's session-only profile, where the coach's privacy note asks for made-up data only (what a coach types there is the coach's own responsibility); and a signed-in gymer whose store fails runs as a guest, with the guest's chat, so what that gymer types reaches the model as a guest's does (the stored profile leaves the session first, T9.5; an accepted exception, owner's decision, 2026-11-02).

### The privacy change

Until Sprint 3 the profile lived in the session only and was never written to disk. Since T9.6, for signed-in users, the app keeps the account (a keyed ID, the role and the display name), the profile history, weights, food and workout logs, targets, preferences, relationships and scopes, reviews, invitations, code attempts and the audit rows in a local SQLite file (`data/store/`, gitignored), and shares a gymer's records and reviews with a coach only within the scopes the gymer turned on (the relationship, its scope history and the audit rows of the coach's reads and review decisions are seen by both sides, in their exports too; owner's choice, 2026-10-28) (T9.6 builds the store; T9.5 and later tickets write to it):

- **Who sees what:** a user always sees their own records (profile entries, weights, logs, targets, preferences); reviews as below. A coach sees a gymer's data only while their relationship is active and the gymer shares the scope: **body** (weights and profile entries), **nutrition** (food log, targets and the reviews that coach wrote) or **training** (workouts). Sharing a scope shows all of its data, the days logged while it was off included. A weekly review counts as nutrition and records every scope its metrics used (the weight figures under body, the training week under training, T9.16): the coach reads, exports or decides it only while every one of them is shared (owner's choice, 2026-10-27). Preferences are never shared with a coach (from T9.24 they are a coach's own working preferences, T9.7, and are never shared with anyone; the Capstone plans the gymer's own preferences and an opt-in scope to share them, "Moved to the Capstone" below, T9.26). A gymer sees only the approved reviews about them: the text the coach approved (the model's text when approved unchanged) or wrote in an edit, never a pending or rejected review, or the model's text a coach replaced. Everything else gets the same "not found" (owner's choices, 2026-10-27).
- **Audit:** every coach read of a client's data and every review decision leaves an audit row with who, what kind of data, about whom and when, never a value (planned: from T9.17 also every target a coach sets for a client, from T9.25 every answer a coach writes).
- **Export:** a user exports all their rows as JSON: their records, relationships and scopes, the audit rows by or about them, and the reviews they may read (a gymer the approved reviews about them, without the model's draft; a coach the reviews they wrote about clients who still share nutrition and every other scope each review used, and each such client gets an audit row). A gymer's pending or rejected reviews are not in the export; the owner accepts this as meeting AC-34 (2026-10-27).
- **Delete:** a user deletes all of it: their records, relationships and scopes, the reviews about them and those they wrote as a coach, and the audit rows by or about them. So when a coach deletes their account, the approved reviews their clients were reading go too. Deleted rows are overwritten in the database file; the copy SQLite's rollback journal takes during the delete is removed afterwards without being overwritten, so the deleted values may stay in free disk space (`docs/SECURITY.md`, known limits). The screens come with T9.5 ("My data").
- **Not settled yet (Capstone, before any real user):** the stored data is health data (GDPR Art. 9), so storing it for real users needs explicit consent, separate from sharing a scope with a coach (the `consents` table records the sharing scopes, not that consent); there is no retention period yet (rows stay until the user deletes them, ended relationships, revoked scopes, expired invitations and audit rows included); whoever runs the app is the controller of what it stores, and a coach who uses it for paying clients may be one too. Until then the app holds synthetic data only.
- **Limits:** the file is not encrypted, so anyone who can read it (a shared computer account, a copy of the file, a backup) reads the data; demos and tests use synthetic data only, and since T9.5 the sidebar's privacy note asks signed-in users not to enter real health data (the coach's names the chat too, as earlier questions and answers go to the model with each turn; a gymer has no chat), and a gymer's first Save needs a tick (since T9.13 its text names the food and weights logged on the Today page too, and since T9.14 the workouts logged on the Workouts page; both pages wait for it) that they understand the details are stored (owner's choice, 2026-11-02).

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
| AC-35 | A review draft that names an intake below the calorie floor in a recommendation, or in a possible reason that cites a source, in one of the common wordings is refused in code, and the coach approves every draft before the client sees it (the check's known limits are in `docs/SECURITY.md`); a training recommendation in a review cites a training source retrieved for that review, is not a program, and gives the source's range with its population, leaving the number for the client to the coach. |
| AC-36 | A coach's working preference is checked against the guardrails and the coach's current and former clients' names before saving, is saved only after the coach approves it (every save), and reaches the model of the coach's chat inside a delimited `<memories>` block, never in the system prompt; guests and gymers have no long-term memory (reworded for the coach by T9.24, 2026-11-02, and to what the code enforces after its compliance review, in place of "never holds a client's personal or health data"; was: a preference saved after the user approves it). |
| AC-37 | (Moved to the Capstone by T9.24, owner's decision, 2026-11-02: a gymer has no chat.) Was (P1): a food or weight typed in the chat is saved only after the gymer approves the proposal. |
| AC-38 | A training-principle question searches the knowledge base and cites at least one approved training source; a request for a personal program gets the general principles with citations and a sentence that the app does not write programs. |
| AC-39 | A question about pain, an injury or rehabilitation is redirected to a professional before any model or embedding call, in English and German; ordinary muscle soreness and recovery questions are not redirected; the message also names the emergency number for sudden, severe or chest symptoms, and a rejected message is not sent to a model in a later turn through the history. |
| AC-40 | Every training chunk comes from a source approved under the training criteria in `docs/SOURCES.md`, carries the `resistance_training` topic, and is credited in `ATTRIBUTION.md`; no nutrition source carries that topic. |
| AC-41 | The About text and the disclaimer say the answers are generated by an AI model and should be checked against the sources, and a gymer sees a weekly review as an AI draft approved by the coach, in English and German. |
| AC-42 | (P1, T9.25) Under an approved review, a gymer asks the coach a question and the coach answers in the app; only that gymer and their coach (by the same rule as the review it belongs to (T9.16: the coach reads a review while the relationship is active and the client shares nutrition and every scope its metrics used)) read the thread, it is never sent to a model, and it is in the export of each side that may read it and deleted with the user's data (AC-34). |
| AC-43 | (Extra, T9.29) A signed-in coach or gymer sees a notification, on the page's next run, for each relationship or review event of feature 28 that concerns them, and none about anyone else's; a notification holds no value or review text, is never sent to a model, and what the user marked read is seen only by them, is in their own export only and is deleted with their data (AC-34), as are the notifications about a user who deletes their data; a guest has none. |

### Beyond the brief (owner's request)

The coach role, invitations and sharing, the workout log and the dashboards. Neither brief asks for them; they give the agent its users and its problem (Sprint 3 core 1 and 2). The training principles (feature 26) are the owner's request too: the briefs ask for a relevant knowledge base and useful core functions, not for training content. So are the coach-first product model of 2026-11-02 (T9.24: the AI serves the coach, the gymer logs and reads what the coach approved) and the questions to the coach under an approved review (feature 27, P1, T9.25), and the in-app notifications (feature 28, extra, T9.29, 2026-11-06).

### Moved to the Capstone

PostgreSQL (and pgvector instead of Chroma), a REST API, separate nutrition coach and personal trainer roles, accounts with several roles, email invitations, an admin role, asynchronous review jobs, meal plans, workout programs (personal training plans; Sprint 3 gives principles only, feature 26), exercise technique instruction, full coach-client messaging (real time, attachments, and the chat's notifications, a new message pushed over the chat's WebSocket into feature 28's list (owner, 2026-11-06; the in-app notifications of relationship and review events moved to Sprint 3 that day, feature 28, T9.29); Sprint 3 has only feature 27's questions under an approved review, P1), moved here by T9.24 (owner's decision, 2026-11-02): the gymer's AI chat and its tools (`get_my_week` as a gymer's chat tool, `remember_preference` for gymers), logging by chat (feature 24, T9.18) and the gymer's preferences; recipes and shopping lists, food scanning, health devices, billing, chat summaries in long-term memory, a 375 px phone layout (except the coach's client list, shown as cards on phones in Sprint 3: owner's decision, 2026-10-30, T9.15) and a WCAG 2.2 AA review, Docker and a staging environment, EU hosting, a GDPR assessment, and interviews and pilot metrics with real coaches. The frontend is open: the Sprint 3 brief allows Streamlit or Next.js, so another framework needs the Capstone brief's approval. Open Food Facts stays excluded at every stage (ODbL, `docs/SOURCES.md`).

Planned for the Capstone by T9.26 (owner's request, 2026-11-04; nothing of it is built in Sprint 3, where feature 22 and AC-36 still hold):

- **Per-client memory, owned by the gymer:** the gymer's preferences ("vegetarian", "I like to draft my own meal plans") are saved by the gymer, with the gymer's approval in the gymer's chat or in a form; never written by the coach or the coach's model about a client. The gymer may share them with their coach through a new `preferences` scope, off by default and revoked like the other scopes; the coach's agent then reads them through a client tool as delimited data, under the client's opaque reference, never by name. As with T9.7, every saved or edited preference passes the input guard and the domain guardrails and is checked against the gymer's own display name before it is saved, as it is the first text a gymer writes that reaches another user's model; a preference has a length limit from config, and the form or proposal card says, in English and German, that it holds no names, contact details or other people's data (as T9.7's card does for a coach); a write tool in the coach's chat never acts on a preference's text without the coach's approval.
- **Gymer-drafted meal plans:** a gymer drafts a meal plan and sends it to their coach, who approves, edits or rejects it (the approve, edit or reject flow of the weekly review, feature 19); the gymer sees the draft and the coach's decision. Which rule governs the coach's read, whether a model ever sees a plan, and the calorie floor on a coach's edit are left to the Capstone.
- **Before any real user:** both need explicit Art. 9 consent apart from the sharing scopes, as both can hold special category data: health (an allergy, say) and the religious or philosophical beliefs a diet can reveal (halal, kosher, vegan). For preferences, the consent covers that they are sent to the AI model and its provider (named in the scope's text) in the coach's chat, and in the gymer's chat if preferences are saved there. Withdrawing it takes one click, as turning a scope off does, and stops every flow to a model: the coach's chat drops or replaces the preference results it already holds, or starts a new chat. The gymer sees, exports and deletes both preferences and meal plans (AC-34); whether the coach's export holds the coach's meal-plan decisions is left to the Capstone.

## Content ownership

The owner drafts the system prompt(s) and the evaluation questions; Claude reviews them (as in Sprint 1). In Sprint 3 that includes the agent's answer prompt (O8), the weekly review and coach assistant prompts (O15), and the training evaluation questions (O17); the owner also approves each training source (O16).

## Beyond the brief (owner's request)

- The repo is the owner's personal, public portfolio project, viewed by recruiters and possibly opened as open source later; it is copied into the course repository for the review.
- Because of that, a strict copyright policy applies (`.claude/rules/copyright.md`): open licences only (public domain, CC0, CC BY), nothing that needs permission, licence checked on the article itself, text only, attribution, raw documents not committed. The brief only asks for a relevant knowledge base.
- Light and dark mode (T7.3). German support (T7.1, T7.2) is an optional task in the brief (Hard 4) but goes beyond this PRD's original English-only scope.
- Sprint 3: the coach role, invitations and sharing, the workout log and the dashboards (section "Sprint 3" above), the training principles (feature 26), the coach-first product model (T9.24) and the questions to the coach (feature 27, P1).
- README screenshots and a short GIF (T9.27) and a presentation video with offline narration (T9.28) (owner's request, 2026-11-06): they show recruiters what the app does, as it is not deployed; synthetic data from demo mode only, and the video file stays out of the repo.
- In-app notifications for coaches and gymers (feature 28, T9.29) (owner's request, 2026-11-06): moved from the Capstone; neither brief asks for them (they serve Sprint 3 core 3 in part).

## Open items

- Deployment: the app runs locally for the review; a public demo comes later (`docs/DEPLOYMENT.md`). Not deployed for now because of the hosting cost (owner's decision, 2026-11-06); a public deployment would also need the privacy notice and the GDPR review first ("Sprint 3" above: out of scope, and the privacy change). The README images and the video (T9.27, T9.28) show the app instead.
- The repo's own code licence (e.g. MIT). Without one, others may view the code but not reuse it.
- The Capstone project: the parts of the owner's product plan that Sprint 3 leaves out ("Moved to the Capstone" above).
