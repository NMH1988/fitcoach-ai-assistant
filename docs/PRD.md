# Product requirements (PRD)

What we build, for whom, and how we know it is done. The course requirements are in `docs/BRIEF.md`; the technical design is in `docs/ARCHITECTURE.md`. Decisions here were made by the owner on 2026-10-19.

## Goal

A chatbot that gives adults who lift weights clear, evidence-based nutrition answers with their sources, and turns their own numbers into personal targets (energy, macros) and food facts.

## Users and scope

- **For:** healthy adults (18+) doing recreational strength training who want to gain muscle, lose fat or maintain.
- **Out of scope:** minors, pregnancy, medical conditions and medication, competitive weight cuts, professional endurance sport, meal delivery or shopping.
- **Language:** English (answers and sources).
- **Deadline:** submission on **2026-11-02**.

## Features (MVP)

1. **Chat with sources.** The user asks a question; the answer cites the approved sources it used (`[S1]`...) and lists them with title, year, evidence tier, licence and link. Serves core 1 and 5, Easy 3.
2. **Query translation and structured retrieval.** Each question is rewritten into a few variants and filtered by topic, year and evidence tier; the UI shows the rewrites and filters. Serves the brief's advanced RAG requirement (and partly Easy 2).
3. **Hybrid search.** Vector search plus keyword search, merged. Serves Hard 1.
4. **Profile.** Weight, height, age, sex, activity level and goal, entered in the sidebar. Kept for the session only, never stored.
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

**Optional tasks for maximum points** (done first, with the core): Medium 3 and 6; Hard 1. **Extras** (after the core, still wanted): Medium 5 and Medium 7.

## Domain guardrails (core 3, approved by the owner)

- No dosing or use advice on steroids, SARMs or other performance-enhancing drugs.
- A minimum calorie floor enforced in the tool code (value taken from the approved sources, not invented).
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

## Content ownership

The owner drafts the system prompt(s) and the evaluation questions; Claude reviews them (as in Sprint 1).

## Beyond the brief (owner's request)

- The repo is the owner's personal, public portfolio project, viewed by recruiters and possibly opened as open source later; it is copied into the course repository for the review.
- Because of that, a strict copyright policy applies (`.claude/rules/copyright.md`): open licences only (public domain, CC0, CC BY), nothing that needs permission, licence checked on the article itself, text only, attribution, raw documents not committed. The brief only asks for a relevant knowledge base.

## Open items

- The calorie floor value and the exact macro formulas: taken from the approved sources when the tools ticket starts.
- Deployment: the app runs locally for the review; a public demo comes later (`docs/DEPLOYMENT.md`).
- The repo's own code licence (e.g. MIT). Without one, others may view the code but not reuse it.
