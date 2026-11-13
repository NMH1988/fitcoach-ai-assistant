# Implementation plan

Epics, tickets, acceptance criteria, dependencies, order and status. This file is the record of the work that travels with the repo to the course repository (GitHub issues and PRs do not), so keep each ticket's status current: every PR updates the status of its ticket.

**Where the tickets are:** this file is the index (owner tasks, the order table, and each epic's introduction and list of tickets); each ticket is a file of its own, `docs/tickets/T<x.y>.md`, split out of this file word for word by T1.15. A ticket's status is in two places, which change together: the heading in its file and its row in the order table ("Overview and order"). A new ticket gets its file (first line: the link back to this index and its epic, e.g. `[Implementation plan](../IMPLEMENTATION_PLAN.md) · Epic 1: Foundation`, then an empty line, then the ticket in the format below), a row in the order table and a line in its epic's list: `- [<the heading up to " · status:", without "### ">](tickets/T<x.y>.md)`. `tests/test_docs_layout.py` checks that these agree.

**Status of this plan:** approved by the owner on 2026-10-19; GitHub issues #1-#20 created the same day (one per ticket). Epic 7 (T7.1-T7.3, issues #33-#35) added by the owner on 2026-10-20; T7.4 (issue #63) split from T7.1 by the owner on 2026-10-21. Epic 8 (the Sprint 2 review's follow-ups) and Epic 9 (the Sprint 3 agent) added by the owner on 2026-10-25, from `docs/BRIEF_SPRINT3.md`; GitHub issues #90-#106 created the same day (one per ticket), and #107 for the PR that added them. Epic 9 rewritten by T9.1 on 2026-10-25 for the coach-first scope the owner chose that day (`docs/PRD.md`, "Sprint 3"): T9.4-T9.7 and T9.11 reworked, T9.12-T9.18 added (issues #112-#118). T9.19 and T9.20 added on 2026-10-26 for the training principles the owner chose that day (PRD feature 26), and T9.14, T9.16 and T9.11 changed with them; the owner approved them the same day, and their issues, NMH1988/fitcoach-ai-assistant#30 and #31, and #32 for the PR that added them, were created in https://github.com/NMH1988/fitcoach-ai-assistant, where the work continues; these three are always written with the repository name, because a bare `#30`-`#32` in this plan is an issue of the personal repository named below. T9.22 and T9.23 added on 2026-10-30 from the owner's UI decisions of that day, and T9.15 changed with them; the owner approved their criteria the same day, and their issues, NMH1988/fitcoach-ai-assistant#52 and #53, were created then. T9.24 added on 2026-11-02 from the owner's decisions of that day (the coach-first rework: gymers without the AI chat; issue NMH1988/fitcoach-ai-assistant#60): T9.7, T9.11, T9.13, T9.15, T9.17 and T9.18 reworked, and T9.25 planned (its issue NMH1988/fitcoach-ai-assistant#61). T9.26 added on 2026-11-04 at the owner's request (a Capstone plan recorded in `docs/PRD.md`, docs only; issue NMH1988/fitcoach-ai-assistant#67), the owner approving its criteria the same day. T9.27 and T9.28 added on 2026-11-06 at the owner's request (README images and a presentation video, beyond the brief), the owner approving their criteria the same day; their issues are NMH1988/fitcoach-ai-assistant#71 and NMH1988/fitcoach-ai-assistant#72, and NMH1988/fitcoach-ai-assistant#73 for the PR that adds them; in the same PR T9.11a (NMH1988/fitcoach-ai-assistant#75) is split from T9.11, as the owner chose to do T9.11 in two PRs with T9.27 between them. T9.29 added on 2026-11-06 at the owner's request (in-app notifications for coaches and gymers, beyond the brief; moved from the Capstone, where only the realtime chat's notifications stay), the owner approving its criteria the same day; its issue is NMH1988/fitcoach-ai-assistant#76, and NMH1988/fitcoach-ai-assistant#77 for the PR that adds it. T1.12 added on 2026-11-06 by T9.9 (a follow-up found in passing; issue NMH1988/fitcoach-ai-assistant#84), its criteria awaiting the owner's approval. T9.30 added on 2026-11-07 by T9.25 (code review round 4 of NMH1988/fitcoach-ai-assistant#80; the owner chose a new ticket for the notifications of a new question or answer), its criteria approved by the owner on 2026-11-08 (with the middle way for the audit of a coach's question notifications); its issue is NMH1988/fitcoach-ai-assistant#87. T9.11b split from T9.11 on 2026-11-09 by the owner (the copy to the Sprint 3 course repository; issue NMH1988/fitcoach-ai-assistant#99). T9.33 added on 2026-11-12 at the owner's request, after a reviewer's comment that LangSmith is little used (the evaluation as LangSmith experiments, and the evaluation lifecycle documented), the owner approving its criteria the same day; its issue is NMH1988/fitcoach-ai-assistant#116. T9.34 added on 2026-11-12 at the owner's request, after a reviewer's comment that the coach should recommend foods rather than leave every choice to the gymer (foods the coach suggests to a client, logged in one click; beyond the brief, cut first if time runs short), the owner approving its criteria the same day; its issue is NMH1988/fitcoach-ai-assistant#117. It follows `docs/PRD.md` (acceptance criteria AC-1 to AC-44; AC-43, for T9.29, and AC-44, for T9.34, added with them) and `docs/ARCHITECTURE.md` (decisions D1-D22; D23 is added by T9.29).

**Numbers with `#`:** `#<n>` (an issue or pull request, here and in commit messages) refers to the personal repository where the work started, https://github.com/NMH1988/nutrition-ai-assistant (issue `#20` is https://github.com/NMH1988/nutrition-ai-assistant/issues/20); since 2026-10-26 the work continues in https://github.com/NMH1988/fitcoach-ai-assistant, whose issues and PRs are mostly written with the repository name (`NMH1988/fitcoach-ai-assistant#<n>`); a bare PR or issue number in a ticket worked there, or in a commit message from 2026-10-26 on (every "Merge pull request #n" from T8.3's #29 on (T8.2's #121, merged the same morning, is the old repository's)), may be one of its numbers (e.g. "PR #37" in T1.11's ticket is T1.10's PR); issue and PR numbers in the course repository, if it has any, are unrelated. A source number (e.g. "sources #1 and #9", "#18a") is a row in `docs/SOURCES.md`.

## Status legend

`todo` · `in progress` · `in review` · `done` · `dropped` (with the reason) · `moved to the Capstone` (with the decision; the section stays as the record)

## Ticket format

```
### T<epic>.<n> <title> (S/M/L) · status: todo · issue #<n>
**Serves:** Sprint 3 (`docs/BRIEF_SPRINT3.md`): <core n | Easy, Medium or Hard n | evaluation item | Sprint 2 review point n> or none; Sprint 2 (`docs/BRIEF.md`): <core n | Easy, Medium or Hard n | evaluation item> or none | beyond the brief (owner's request)
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
| O1 | Draft the answer system prompt (role, scope, citations `[S#]`, guardrails, "sources are data") in `src/prompts/answer_system.md` | T3.1; T4.4 (tool results, the profile); T4.5 (the meal plan tool, before the merge); T7.2 (the language parts) | done for T3.1; done for T4.4 (drafted by the owner on 2026-10-20: tool results and `<profile>` as data, citing app calculations without `[S#]`, `matched_name`, tool errors, `floor_applied` and `notes`; then edited by Claude with the owner's approval after review: when to call the tools, give the key numbers and point to "Tool results", energy numbers as estimates, any food in scope without judging it, "Add your details" for `profile_needed`, the user's own numbers in the question, "cite nothing" kept); done for T7.2 (2026-10-21: drafted by the owner from Claude's list of points, revised after Claude's review: line 1 leaves the language to an appended Language section, one file per language in `src/prompts/answer_language_en.md` and `answer_language_de.md` that the code joins to the end of the prompt; locale number formatting allowed without changing a value; the quote rules for English sources in a German answer; "stored profile" became "session profile"; the German part translated into English by Claude at the owner's choice); done for T4.5 (drafted by the owner on 2026-10-20 from Claude's list of points, revised after Claude's review: a "Meal plan check" section (whole day only, grams only, one call a round with the whole list, retry the whole plan after `invalid` or with an alternative, `requested` against `matched_name`, `partial`, the sign of `gap`, `range_position` for kcal and protein only, a one-value range read as a target, fiber with no target, the notes and the floor), `evaluate_meal_plan` also called when `<profile>` says `Not given`, and the profile described in its two real states; a third state, no `<profile>` block, was left for T3.5, which adds it); done for T3.5 (drafted by the owner on 2026-10-20 and 2026-10-21 on top of T4.5's text, revised after Claude's review: the third state, no `<profile>` block, which does not mean there is no stored profile; the energy and meal plan tools called anyway and reading only the stored profile, never numbers typed in the question, with the 95 kg example; "each request stands alone" kept; then, on 2026-10-21 after the branch reviews, a typed value is compared with `<profile>` or with the value a tool result names (`weight_kg`), and "cannot verify" is kept only when neither has it; a rule for a single food with no amount, looked up for 100 g and said to be per 100 g, added by Claude at the owner's request; then, after the first live check of 2026-10-21 (option D), never ask for profile values before calling a tool, and for personal advice that depends on the targets call the daily-target tool first, also with `Not given` or no block, so `profile_needed` shows the "Add your details" button; the 100 g rule rewritten by the owner (grams as given, a serving asked again in grams); "always" label an app calculation and the no-block line for personal advice added by Claude at the owner's request). T3.1: drafted by the owner, edited with Claude's review (wording, citation forms, caffeine allowed, partial answers, each turn alone), in the file on 2026-10-20 |
| O2 | Draft the evaluation questions (about 10-15), each with the source(s) it should find and what a good answer contains | T3.6 (from T3.3), T6.1; T7.2 (3-5 German questions, one about a food) | done (2026-10-21, in T3.6): 16 English questions in `data/eval_questions.json` (10 the sources cover, 2 near-domain they do not, 2 tool, 2 guardrail) and 5 German ones in `data/eval_questions_de.json` for T7.2; drafted by the owner, revised after two Claude reviews against the articles |
| O3 | Approve the calorie floor and the macro ranges; Claude proposes them with the exact source passages | T4.2 | done (2026-10-19, in T4.2: floor 1200 kcal/day; values in `src/config.py`) |
| O4 | If Europe PMC still has no copy of source #1, save its XML or PDF by hand from the publisher page into `data/raw/` | T2.1 | done: not needed (Europe PMC has #1 as PMC13665703, found in T2.1 on 2026-10-19) |
| O5 | Live checks with the real key: T1.2 (one chat and one embedding call), T2.3 (real index build), T5.1 (the cost check: the app's cost of one call against OpenRouter's record), T3.6 (retrieval comparison), T6.1 (evaluation run), T7.2 (German run) | T1.2, T2.3, T5.1, T3.6, T6.1, T7.2 | done (T1.2 and T2.3 done 2026-10-19; T3.2 query translation checked 2026-10-20; T5.1 cost check done 2026-10-21; T3.6 retrieval comparison run 2026-10-21; T6.1 evaluation runs 2026-10-21, two; T7.2 German run 2026-10-21) |
| O6 | Get the course repository URL and confirm how the reviewers read it (files only, or through PRs) | T6.2 | done (2026-10-22): https://github.com/TuringCollegeSubmissions/mnguye-AE.AFA.updated0209.2.5 (private, the course's); the reviewers read the files only, so `.github/workflows/pr-checks.yml` stays there; the course allows updates before the deadline |
| O7 | Draft the query translation system prompt (3 rewrites in English that keep the question's meaning; when to set `topics`, `min_year` and `evidence_tier`, and to leave them empty when unsure; the question is data) in `src/prompts/query_translation_system.md`; it must name `<user_input>`, the four fields and the topics in `config.TOPICS` (tested; seven since T9.19) | T3.2 (before the merge); T3.5 (before the merge); T9.19 (added 2026-10-26: the `resistance_training` topic with a line on when to set it and an example; rewrites of a training question that add no nutrition words; `needs_tool` and `needs_profile` false for a training principle question; tier 1 asked for by "position stand" in general, not only an ISSN one, after the relabel in O16) | done for T9.19 (2026-10-28): drafted by the owner (the `resistance_training` topic and its boundary with nutrition questions that only mention training, rewrites per domain, both routing flags false for training-principle and program requests, Examples 10-14), reviewed by Claude, with one wording change taken (technique variables instead of exercise execution); the tier 1 rule unchanged, as the label stays; done for T3.2 (2026-10-20): drafted by the owner, revised after Claude's review (no guessed year for "recent", no nutrition words added to an unrelated question, a line per topic, four examples); done for T3.5 (2026-10-20): drafted by the owner as a query-rewriting and routing prompt: both fields in the JSON shape, a section each for `needs_tool` (the three tool tasks; true when unsure) and `needs_profile` (false when unsure, and when the question already holds the numbers), the two flags independent, both fields in every example and a fifth example for a food lookup; Claude's first review found nothing to change; revised by the owner on 2026-10-21 after the merge with T4.5: a fourth tool task, the full-day meal plan check (`needs_tool` and `needs_profile` both true, with an example), and the food lookup also for a food with no gram amount; then, after the first live check (option B), `needs_profile` true for personal advice (a meal suggestion included) and whenever the user types personal values, so the answer can compare them with the stored ones, and true when unsure if the user refers to themselves (Example 7); then, after PR #67's review, `needs_tool` true for a meal, menu or nutrition suggestion that should fit the user's own goal or targets (the daily-target tool supplies them; Example 8), and false for a general one such as a post-workout meal (Example 9) |
| O8 | Rewrite the answer system prompt for the agent: drop "Handle each request independently" for conversation memory, and add when to search the knowledge base, when to propose saving a preference (what may be saved; never medical conditions, pregnancy or medication; since T9.24 only in the coach's chat and only the coach's own working preferences, never a client's personal or health data), how to use `<memories>`, a line in the Safety section that pain, injuries and rehabilitation are redirected to a doctor or physiotherapist (the second line of defence after T9.19a's guard; with T9.4, so it stays if T9.20 is cut; owner's choice, 2026-10-28), the training rules (T9.20, replacing "training is reported as facts only" on 2026-10-26; they go into the prompt only with T9.20, so T9.3 and T9.4 get the other parts first: widen the identity and the Scope section from "a nutrition assistant" to nutrition and training principles; explain training principles only from the training sources and cite them; say the sources do not cover a training claim it cannot cite; give the ranges a source gives, each with the population the source studied, never a program for the user, sets and reps per exercise for the user, or technique coaching; a program request gets the principles and a sentence that the app does not write programs), no endorsement by any society, not only the ISSN (T9.20), and (P1, T9.18) when to propose a log entry (moved to the Capstone with T9.18 by T9.24); chat summaries moved to the Capstone (T9.1); Claude reviews | T9.3, T9.4, T9.7, T9.20 | in progress (T9.3's part done 2026-10-29: the search rules, `<sources>` from the search tool, no `<profile>`; T9.20's part done 2026-10-29: the owner's training rules, the pain and injury line and the fixed no-program sentence, reviewed by Claude, joined with T9.3's search rules when T9.20 merged `main`; T9.4's part done 2026-10-30: "each request independently" dropped, the conversation rules (history as context, never evidence; fresh support every turn; no earlier labels or tool results), reviewed by Claude; the rest with T9.7; T9.18's part moved to the Capstone by T9.24) |
| O9 | Create a Google OAuth client (web application, redirect `http://localhost:8501/oauth2callback`; the consent screen in Testing mode with only the `openid`, `email` and `profile` scopes, free), add the Google accounts that will play the coach and the gymers as test users, and put the client's values in the gitignored `.streamlit/secrets.toml`; Claude never creates accounts or enters credentials | T9.5 | done (2026-11-02) |
| O10 | Create a LangSmith account and key, and set it only in the gitignored secrets or environment | T9.8 | done (2026-11-07, EU region) |
| O11 | Create a separate OpenRouter key with a credit limit for the evaluation workflow and store it as the repository secret `OPENROUTER_API_KEY_EVAL` (Settings > Secrets and variables > Actions, or `gh secret set OPENROUTER_API_KEY_EVAL`), then start the workflow once on `main` (`gh workflow run eval.yml`) | T8.6 (its dispatched run, after the merge) | open: a separate key of the owner's own. Done on 2026-11-09: the first run passed (`docs/TESTING.md`), with the school's course key, as the owner has no other OpenRouter key; the owner does not want that key exposed in any way, so the secret was deleted right after the run (owner's decision, 2026-11-09). The terms pages compliance run 1 named were read by Claude at the owner's request (`docs/PROGRESS.md`); the OpenRouter account and its privacy settings are the school's |
| O12 | Request a FoodData Central API key (api.data.gov), and approve or reject the change to copyright policy rule 10 | T9.9 | in progress (rule 10's change approved 2026-11-06; the key to come, needed only for T9.9's live check) |
| O13 | Live checks with the real key for Epics 8 and 9: T8.1 (one answered question), T8.3 (retrieval comparison and evaluation), T8.4 (the baseline run), T9.2 and T9.3 (evaluation against the baseline), T9.4 (a follow-up question), T9.5 (sign in and out as a coach and as a gymer), T9.7 (a coach's preference proposed and saved, since T9.24), T9.12 (an invitation accepted by a second account), T9.16 (one review drafted and approved), T9.9 (a food missing from the table found through the API, with O12's key), T9.19 (the nutrition baseline and the training retrieval after re-indexing), T9.20 (the run of the O17 questions), T9.8 (one trace), T9.10 (the scored run) | those tickets | todo (T8.1 done 2026-10-25, T8.3 done 2026-10-26, T8.4 done 2026-10-26, T9.2 done 2026-10-26, T9.19 done 2026-10-28 (the nutrition baseline and the training retrieval; the training baseline moved to T9.20), T9.3 done 2026-10-29, T9.4 done 2026-10-30, T9.12 done 2026-11-03, T9.7 done 2026-11-04, T9.16 done 2026-11-06, T9.10 done 2026-11-06, the scored run, T9.8 done 2026-11-07 (one trace; the roles of a model call re-checked 2026-11-08)) |
| O14 | Write a reference answer for each evaluation question with expected sources, if context precision and recall are wanted in T9.10 (the owner writes the evaluation content, as for O2); Claude reviews | T9.10 | not now (owner's choice, 2026-11-06, T9.10's Question phase: T9.10 scores faithfulness and answer relevancy only; context precision and recall can be added once the reference answers exist) |
| O15 | Draft the weekly review system prompt (observations as facts from the metrics, hypotheses as tentative, recommendations for the coach; a training recommendation only with a citation to a training source and never as a program, filled as the schema asks: the direction, the source's range quoted exactly as the chunk has it, and the population the source studied, with the number for this client left to the coach (changed on 2026-10-26 with the training principles, PRD feature 26; was "training as facts only", which comes back if T9.20 is cut); cite only `<sources>`; no diagnosis; missing days are "not logged") and, for T9.17, the coach assistant's part; Claude reviews | T9.16, T9.17 | done (the review prompt on 2026-11-05: the owner's draft with Claude's review changes the owner approved; the coach assistant's part for T9.17 on 2026-11-07: the owner's draft of the client section in `src/prompts/answer_coach.md`, with the changes from Claude's review the owner approved: a review prompt copied into the draft left out, as it lives in `weekly_review_system.md`; the model names clients by reference in the answer, as the page shows the name in its place; a name the coach types is answered by listing the references, as the model cannot map it; the follow-up flag read against the week so far, as the chat has no date; the tool's averages used, never computed; the threshold read from `follow_up_min_logged_days`; no link, '<' or '@' in a paragraph that names a client; the draft's 1,200 kcal line left out, as the main prompt has it; then, after compliance run 2: a null section told apart from a null inside a shared one, a logged average below the floor reported with the floor and a pointer to a professional, and the follow-up line limited to the current week; then, after code review round 7 (2026-11-08): `today` from the tool results for a relative week and for days still to come, the `body` nulls, a low average that may mean partly logged days, a line that client questions are in scope, and "Client week" in the German language part) |
| O16 | Confirm the training source criteria (`docs/SOURCES.md`, "Training sources", "Selection criteria"; first approved 2026-10-26, the clarifications of the same day still wait for your confirmation), then each candidate Claude proposes with its licence line read on the article itself; approve or change the tier 1 label (from "ISSN position stand" to "Position stand", so another society's position stand fits) | T9.19 | done (2026-10-28): criteria confirmed; 10 rows approved (#24-#33), K and the others excluded with reasons; licence lines read by the owner on the article pages; the tier 1 label stays "ISSN position stand" |
| O17 | Draft the training evaluation questions (about 6-8 in English and 2 in German): principle questions each with the training source it should find, one personal-program request, one pain or injury question, one question the training sources do not cover; in their own files (`data/eval_questions_training.json`, `data/eval_questions_training_de.json`), so the nutrition baseline can be checked alone; Claude reviews against the articles (as for O2) | T9.19, T9.20 | done (2026-10-28): 10 English (t1-t10) and 2 German (tde1-tde2) questions by the owner; Claude's review against the articles led to two changes the owner took (t4 expects #27 and #32; t10 says the evidence generally favours periodized training for strength, with its caveat) |

## Overview and order

Deadline: **2026-11-02** (Sprint 2, already submitted by the owner, 2026-10-28). Target dates leave 1-2 days of buffer.

**Sprint 3** (deadline **2026-11-23**; owner's order, 2026-10-25): T9.1 first, then Epic 8's T1.8, T8.2, T8.3 and T8.4, then the Epic 9 P0 tickets in the table's order, then the "should" tickets (T9.17 first, raised from P1 by T9.24, then T9.8, T9.10), then P1 (T9.25; T9.18 moved to the Capstone by T9.24), then the extras (T9.9, T8.5, T8.6, and T9.29 after T9.16 and before T9.27, added on 2026-11-06, then T9.30 after T9.25 and T9.29 and before T9.27, added on 2026-11-07), and T9.11 last, done in two PRs with T9.27 between them (owner's choice, 2026-11-06): T9.11a (the app's title, intro and chat texts, split from T9.11), then T9.27, then T9.11 (the README work and the copy to the course repository; if T9.27 is cut, T9.11 drops that dependency and follows T9.11a); T9.28 is the one ticket that may come after T9.11 (T9.27 and T9.28 added on 2026-11-06). The targets assume about 12 hours of work a day and leave about a week of buffer. Estimate: P0 about 96-132 hours (Epic 8's four tickets included), should 15-21 (T9.17's 5-7 included since T9.24), P1 5-8 (T9.25; was 11-15 for T9.17 and T9.18), extras 10-15, plus T9.27 and T9.28 about 12-20, T9.29 about 6-9 and T9.30 about 3-5 (beyond the brief, from the buffer). **If time runs short, cut in this order:** T9.30 (added on 2026-11-07; it needs T9.29), T9.29, T9.28, T9.27 (all three added on 2026-11-06), T9.9, T8.6, T8.5, T9.25, T9.10, T9.8, T9.17 (T9.24: T9.17 now goes last, as the first ticket after P0; was T9.9, T8.6, T8.5, T9.18, T9.17, T9.10, T9.8); the P0 tickets stay, as they carry Sprint 3's core requirements and its optional tasks for maximum points (Medium 2, Medium 4, Hard 1). **Training principles** (owner's decision, 2026-10-26): T9.19 and T9.20 are P0, about 14-22 hours more, taken from the week of buffer; T9.19 runs once T8.4's baseline exists (owner's decision, 2026-10-28: now, before T9.3 and T9.4, as its only hard dependencies are T8.4 and the owner tasks O7, O16 and O17; it was planned after T9.4), and T9.20 after T9.3 and before T9.16; T9.19 merges only right before T9.20, as the answer prompt turns training chunks into advice, programs included, until T9.20's rules are in it (owner's choice, 2026-10-28). They are beyond the brief, so if time runs short they are cut after T9.8 and before the other P0 tickets. **The owner's UI decisions of 2026-10-30** (T9.22, T9.23 and T9.15's phone cards; owner's choice, 2026-10-30): about 1-1.5 days more, taken from the buffer; T9.22 and T9.23 run before T9.5. If time runs short, T9.23 and T9.15's card criterion are cut first, before T9.9 (the app keeps today's theme and the header's language control; T9.15 then drops its dependency on T9.23), and T9.22 stays, as it is small. **T9.20 first:** the AI-disclosure sentence of its About and disclaimer criterion moves to T9.11 (the disclosure covers the nutrition chat too, so it is not dropped with T9.20); O8 then leaves the training rules out; while T9.19 stays unmerged, no training chunk is in an index built from `main`, which keeps training advice out of the chat, O15 and T9.16's validation allow no training recommendation (a recommendation of kind "training" fails), and the rule of 2026-10-25 (training reported as facts only) applies again in the PRD. **Then T9.19's sources and indexing:** T9.19a's injury guard stays, as it is small and protects the chat too; T9.19 itself is not merged (without T9.20 the chat would write training programs from its chunks), or merges only with its training chunks kept out of retrieval; T9.16 drops its dependency on T9.19.

**The coach-first rework** (T9.24; owner's decisions, 2026-11-02, while trying T9.5's sign-in on PR NMH1988/fitcoach-ai-assistant#59): the AI serves the coach and a gymer has no AI chat. The gymer's chat tools (`get_my_week`, `remember_preference` for gymers) and logging by chat (T9.18) move to the Capstone; T9.7 becomes long-term memory for the coach; T9.17 is raised from P1 to "should", right after the P0 tickets; T9.25 (questions to the coach under an approved review) is the new P1 ticket, after T9.16. The P0 tickets T9.7, T9.13 and T9.15 are reworked, not enlarged, so the estimate for P0 does not change (T9.24 itself, docs only, comes from the buffer); Sprint 3 still reaches its optional tasks for maximum points ("For maximum points" in Epic 9).

**README images and the presentation video** (T9.27, T9.28; owner's request, 2026-11-06; beyond the brief): images and a video that show recruiters what the app does, as the app runs locally only and is not deployed (hosting cost, owner's decision, 2026-11-06). Both are extras, made once the tickets that change the UI are done (T9.11a's title and chat texts included), so the images match the app the reviewer sees; T9.27 lands after T9.11a and before T9.11, so the copy to the course repository carries its images. If time runs short they are cut right after T9.29 (added later the same day), T9.28 before T9.27, before T9.9; T9.28 may also be done after 2026-11-23, as it is for recruiters, not for the review.

**In-app notifications** (T9.29; owner's request, 2026-11-06; beyond the brief): a coach and a gymer see in the app what changed for them (a new client, a scope turned on or off, an approved weekly review, a relationship that ended), shown on the page's next run, with no email, push or real time. The PRD had them in the Capstone with full messaging (T9.24); the owner moved these to Sprint 3 on 2026-11-06, and only the notifications of the Capstone's realtime chat stay there. T9.29 lands after T9.16 and before T9.27, so the README images show it; after T9.30 it is the first ticket cut if time runs short (T9.30 needs it, owner's choice of 2026-11-07 to plan the question and answer kinds as T9.30), and T9.27 then captures the pages without it.

**Core first, then extras** (owner's decision, 2026-10-19): the brief's core requirements and the optional tasks needed for maximum points (Sprint 2: Medium 3, Medium 6, Hard 1) are finished first. The extras (Medium 5 token cost, Medium 7 PDF, the stretch tool, and Epic 7: English/German and light/dark mode) come after them and are still wanted, but never delay a core ticket. T6.2 comes last.

| Ticket | Issue | Title | Size | Depends on | Target | Status |
|---|---|---|---|---|---|---|
| **Core** | | | | | | |
| [T1.1](tickets/T1.1.md) | #1 | Project skeleton, config and CI | S | - | 10-20 | done |
| [T1.2](tickets/T1.2.md) | #2 | OpenRouter clients and error mapping | S | T1.1 | 10-20 | done |
| [T1.3](tickets/T1.3.md) | #3 | Input guard and rate limit | S | T1.1 | 10-21 | done |
| [T2.1](tickets/T2.1.md) | #4 | Source manifest, download script, attribution | M | T1.1, O4 | 10-21 | done |
| [T2.2](tickets/T2.2.md) | #5 | Parse article XML and chunk with metadata | M | T2.1 | 10-22 | done |
| [T2.3](tickets/T2.3.md) | #6 | Build and open the Chroma index | S | T1.2, T2.2 | 10-23 | done |
| [T4.1](tickets/T4.1.md) | #11 | Profile, units and settings | M | T1.1 | 10-23 | done |
| [T4.3](tickets/T4.3.md) | #13 | USDA food table and lookup | M | T1.1 | 10-23 | done |
| [T3.1](tickets/T3.1.md) | #7 | First answer with sources (vector search) | M | T1.2, T1.3, T2.3, O1 | 10-24 | done |
| [T4.2](tickets/T4.2.md) | #12 | Energy and macro tools with the calorie floor | M | T4.1, O3 | 10-25 | done |
| [T1.5](tickets/T1.5.md) | #42 | Docs: run commands use the project's venv | S | T1.1 | 10-20 | done |
| [T1.6](tickets/T1.6.md) | #55 | CI: accept the pillow 12.3.0 advisories until Streamlit allows pillow 13 | S | T1.1 | 10-20 | done |
| [T1.6a](tickets/T1.6a.md) | #77 | CI: upgrade streamlit to 1.66.1 so pillow 13 replaces the pillow ignores (owner's request after PR #76's security job failed) | S | T1.6 | 10-22 | done |
| [T1.7](tickets/T1.7.md) | #81 | Streamlit runs on localhost only, without telemetry or error details (owner's request after the 2026-10-22 security audit) | S | T1.1 | 10-22 | done |
| [T1.8](tickets/T1.8.md) | #82 | A fixed message for unexpected errors in a chat turn (split from T1.7) | S | T1.7 | 10-26 (before T8.2; Epic 8 order, owner, 2026-10-25) | done |
| [T1.9](tickets/T1.9.md) | #110 | Workflow files: read and check both briefs for every ticket (owner's request after PR #109) | S | - | 10-25 | done |
| [T1.10](tickets/T1.10.md) | NMH1988/fitcoach-ai-assistant#36 | Compliance reviewer agent: copyright, data protection, legal (owner's request) | S | T1.4 | 10-27 | done |
| [T1.11](tickets/T1.11.md) | NMH1988/fitcoach-ai-assistant#38 | CI: offline licence check of the runtime dependencies, Dependabot's bumps included (owner's request after T1.10's review) | S | T1.10 (criterion 7 only) | 10-27 | done |
| [T1.12](tickets/T1.12.md) | NMH1988/fitcoach-ai-assistant#84 | Keep the httpx2, httpcore2 and authlib loggers at WARNING (found in passing by T9.9) | S | T8.2 | 11-09 | done |
| [T1.13](tickets/T1.13.md) | NMH1988/fitcoach-ai-assistant#104 | Docs: record the Dependabot bumps of 2026-11-09 in the dependency table (owner's request after merging them) | S | - | 11-09 | done |
| [T1.14](tickets/T1.14.md) | NMH1988/fitcoach-ai-assistant#105 | Docs: the repo's own code stays all rights reserved (copyright notice) (owner's request) | S | T1.13 (order only) | 11-09 | done |
| [T1.15](tickets/T1.15.md) | NMH1988/fitcoach-ai-assistant#112 | Docs: split PROGRESS and IMPLEMENTATION_PLAN into an index and one file per entry (owner's request) | M | - (before T9.11b) | 11-11 | done |
| [T1.16](tickets/T1.16.md) | NMH1988/fitcoach-ai-assistant#114 | Docs: diagrams of the app, the RAG search, the tool loop and the store's sharing (owner's request) | S | - | 11-11 | done |
| [T3.2](tickets/T3.2.md) | #8 | Query translation and structured filters | M | T3.1, O7 | 10-26 | done |
| [T3.3](tickets/T3.3.md) | #9 | Hybrid search (BM25 + RRF) | M | T3.2 | 10-27 | done |
| [T3.4](tickets/T3.4.md) | #10 | Prompt injection hardening | S | T3.1 | 10-27 | done |
| [T4.4](tickets/T4.4.md) | #14 | Tool-calling loop and tool results UI | M | T3.1, T4.2, T4.3 | 10-28 | done |
| [T4.7](tickets/T4.7.md) | #44 | My targets: sidebar target, targets tab and Food lookup tab (split from T4.4, owner's decision) | M | T4.4 | 10-29 | done |
| [T4.8](tickets/T4.8.md) | #85 | Food lookup tab: a searchable dropdown of the USDA foods (owner's request after T4.7) | S | T4.7 | 10-22 | done |
| [T3.9](tickets/T3.9.md) | #88 | The "About the answers" block opens as a modal instead of an expander in the sidebar (owner's request) | S | T3.1 | 10-22 | done |
| [T3.5](tickets/T3.5.md) | #50 | Skip the answer call for off-topic questions with no source (owner's request after T4.4) | S | T4.4, T3.2, O7, O1 | 10-29 | done |
| [T5.3](tickets/T5.3.md) | #18 | Domain guardrails | S | T3.1, T4.2 | 10-29 | done |
| [T3.6](tickets/T3.6.md) | #51 | Retrieval comparison on the owner's evaluation questions (split from T3.3, owner's decision) | S | T3.3, O2, O5 | 10-30 | done |
| [T3.7](tickets/T3.7.md) | #66 | Drop registration boilerplate and merge short chunk pieces at ingest (found in T3.5's live check) | S | T2.2, T2.3, O5 | 10-29 | done |
| [T3.8](tickets/T3.8.md) | #71 | Only the question itself decides whether the sources cover it (found in T3.5's live check after T3.7) | S | T3.2, T3.3, T3.5, O5 | 10-29 | done |
| [T6.1](tickets/T6.1.md) | #19 | Evaluation run and reflection | S | T3.3, T3.6, T4.4, O2, O5 | 10-30 | done |
| **Extras** | | | | | | |
| [T1.4](tickets/T1.4.md) | #32 | Security reviewer agent (beyond the brief; owner's request, done early as it is dev tooling with no product change) | S | T1.1 | 10-20 | done |
| [T5.1](tickets/T5.1.md) | #16 | Token usage and cost | S | T3.2 | 10-30 | done |
| [T5.1a](tickets/T5.1a.md) | #68 | Live-check tests ignore a local secrets.toml (follow-up to T5.1; owner's request) | S | T5.1 | 10-21 | done |
| [T5.2](tickets/T5.2.md) | #17 | Session summary PDF | M | T4.4 | 10-31 | done |
| [T7.3](tickets/T7.3.md) | #35 | Light and dark mode | S | T3.1 | 10-31 | done |
| [T7.4](tickets/T7.4.md) | #63 | German input guard and guardrails (split from T7.1, owner's decision) | M | T1.3, T5.3 | 10-31 | done |
| [T7.1](tickets/T7.1.md) | #33 | Language switch: English and German UI | M | T4.4, T4.7, T5.3, T1.3, T7.4 | 10-31 | done |
| [T7.2](tickets/T7.2.md) | #34 | German answers end to end | M | T7.1, T3.2, O1, O2, O5 | 11-01 | done |
| [T4.5](tickets/T4.5.md) | #15 | `evaluate_meal_plan` tool (stretch; done early by the owner's choice) | S | T4.4 | only if ahead | done |
| [T4.6](tickets/T4.6.md) | #40 | Profile form: a hint instead of "Press Enter to apply" (beyond the brief; owner's request, done early as a small fix) | S | T4.1, T3.1 | 10-20 | done |
| **Epic 8: Sprint 2 review follow-ups** | | | | | | |
| [T8.1](tickets/T8.1.md) | #90 | Split `app.py` into a `views/` package, no behaviour change | L | - | 10-25 | done |
| [T8.2](tickets/T8.2.md) | #91 | Structured turn logging with no personal data | M | T1.8, T8.1 | 10-27 | done |
| [T8.3](tickets/T8.3.md) | #92 | At most three chunks per source in the fused list | S | T8.1, O13 | 10-27 | done |
| [T8.4](tickets/T8.4.md) | #93 | Evaluation results as JSON and a committed baseline | M | T8.3, O13 | 10-28 | done |
| [T8.5](tickets/T8.5.md) | #94 | An offline retrieval regression suite in CI (extra) | M | T8.4 | 11-15 | done |
| [T8.6](tickets/T8.6.md) | #95 | A manually started live evaluation workflow (extra) | S | T8.4, O11 | 11-15 | done, except the separate key (owner's decision, 2026-11-09) |
| **Epic 9: Sprint 3 agent, P0** | | | | | | |
| [T9.1](tickets/T9.1.md) | #96 | Sprint 3 product and design decisions (coach-first scope) | M | - | 10-25 | done |
| [T9.2](tickets/T9.2.md) | #97 | The chat turn as a LangGraph `StateGraph`, same behaviour | L | T9.1, T8.1, T8.2, T8.4 | 10-30 | done |
| [T9.19a](tickets/T9.19a.md) | NMH1988/fitcoach-ai-assistant#41 | The pain and injury guard (split from T9.19 by the owner, 2026-10-28) | S | - | 10-28 | done |
| [T9.19](tickets/T9.19.md) | NMH1988/fitcoach-ai-assistant#30 | Training sources and indexing (moved before T9.3 by the owner, 2026-10-28; the dates after it were not moved; its injury guard split into T9.19a the same day) | M | T8.4, T9.19a, O7, O16, O17 | 11-08 (merges right before T9.20) | done |
| [T9.21](tickets/T9.21.md) | NMH1988/fitcoach-ai-assistant#44 | Checks: the manifest's authors against the article, and the evaluated code's git state (follow-up of T9.19's reviews, owner's choice, 2026-10-29) | S | T2.1, T8.4 | 10-30 | done |
| [T9.3](tickets/T9.3.md) | #98 | Agentic RAG: searching the knowledge base is the agent's tool | M | T9.2, T8.4, O8 | 10-31 | done |
| [T9.4](tickets/T9.4.md) | #99 | Short-term memory: a conversation that remembers earlier turns | M | T9.2, O8 | 10-31 | done |
| [T9.22](tickets/T9.22.md) | NMH1988/fitcoach-ai-assistant#52 | The app's new name: Fitcoach AI Assistant (owner's decision, 2026-10-30; beyond the brief) | S | - | 10-31 | done |
| [T9.23](tickets/T9.23.md) | NMH1988/fitcoach-ai-assistant#53 | Brand sidebar, language control in the sidebar and a custom CSS layer (owner's decisions, 2026-10-30; beyond the brief in part) | M | T9.22 | 11-01 (before T9.5; the dates after it were not moved) | done |
| [T9.6](tickets/T9.6.md) | #101 | The SQLite store and the authorisation layer | L | T9.1, T8.2 | 11-02 | done |
| [T9.5](tickets/T9.5.md) | #100 | Sign in with Google, roles, guest and demo mode, My data | L | T9.6, T8.1, O9 | 11-03 | done |
| [T9.24](tickets/T9.24.md) | NMH1988/fitcoach-ai-assistant#60 | Coach-first rework: gymers without the AI chat (planning; owner's decisions, 2026-11-02; beyond the brief in part) | M | T9.5 | 11-03 | done |
| [T9.12](tickets/T9.12.md) | #112 (NMH1988/fitcoach-ai-assistant#15) | Invitations and sharing | M | T9.5 | 11-04 | done |
| [T9.26](tickets/T9.26.md) | NMH1988/fitcoach-ai-assistant#67 | Capstone plan: the gymer's own preferences shared with the coach, and gymer-drafted meal plans (planning, docs only; owner's request, 2026-11-04; in the P0 block by its date, as T9.24) | S | T9.24 | 11-04 | done |
| [T9.13](tickets/T9.13.md) | #113 (NMH1988/fitcoach-ai-assistant#16) | Food and weight diary, and the weekly nutrition metrics | M | T9.5, T9.2 | 11-05 | done |
| [T9.14](tickets/T9.14.md) | #114 (NMH1988/fitcoach-ai-assistant#17) | Workout log and the weekly training metrics | M | T9.5 | 11-05 | done |
| [T9.15](tickets/T9.15.md) | #115 (NMH1988/fitcoach-ai-assistant#18) | Coach and gymer dashboards | M | T9.12, T9.13, T9.14, T9.23 | 11-06 | done |
| [T9.7](tickets/T9.7.md) | #102 (NMH1988/fitcoach-ai-assistant#10) | Long-term memory for the coach: `remember_preference` with the coach's approval (reworked by T9.24) | M | T9.4, T9.5, T9.12, O8 | 11-07 | done |
| [T9.20](tickets/T9.20.md) | NMH1988/fitcoach-ai-assistant#31 | Training principles in the chat | M | T9.3, T9.19, O8, O17 | 11-08 | done |
| [T9.16](tickets/T9.16.md) | #116 | Weekly review with the coach's approval | L | T9.3, T9.15, T9.19, O15 | 11-09 | done |
| [T9.11a](tickets/T9.11a.md) | NMH1988/fitcoach-ai-assistant#75 | The app's title, intro and chat texts name training principles (split from T9.11, owner's choice, 2026-11-06) | S | T9.20 | 11-15 | done |
| [T9.11](tickets/T9.11.md) | #106 (NMH1988/fitcoach-ai-assistant#14) | Sprint 3 documentation and reflection | M | the P0 tickets, T9.11a, T9.27 (dropped if T9.27 is cut) | 11-17 (was 11-16; after T9.27) | done |
| [T9.11b](tickets/T9.11b.md) | NMH1988/fitcoach-ai-assistant#99 | Copy the repo into the Sprint 3 course repository (split from T9.11, owner's choice, 2026-11-09) | S | T9.11, the course repository's URL | before 11-23 | todo |
| **Epic 9: should, P1 and extras** | | | | | | |
| [T9.17](tickets/T9.17.md) | #117 | Coach assistant: client tools, a follow-up flag, coach-set targets (should; raised from P1 by T9.24) | M | T9.16, O15 | 11-10 (right after P0, T9.24; the dates after it were not moved) | done |
| [T9.8](tickets/T9.8.md) | #103 (NMH1988/fitcoach-ai-assistant#11) | LangSmith tracing with personal data masked (should) | M | T9.2, T8.2, O10 | 11-10 | done |
| [T9.10](tickets/T9.10.md) | #105 (NMH1988/fitcoach-ai-assistant#13) | Evaluation report with Ragas or DeepEval (should; DeepEval, as Ragas cannot be installed with our pins) | M | T8.4, T9.3 | 11-11 | done |
| [T9.25](tickets/T9.25.md) | NMH1988/fitcoach-ai-assistant#61 | Questions to the coach under an approved review (P1; owner's request, 2026-11-02, T9.24) | M | T9.16, T9.15 | 11-13 | done |
| [T9.18](tickets/T9.18.md) | #118 | Logging by chat with the gymer's approval (was P1; moved to the Capstone by T9.24) | M | T9.7, T9.13, O8 | - | moved to the Capstone |
| [T9.9](tickets/T9.9.md) | #104 (NMH1988/fitcoach-ai-assistant#12) | Food lookup through the USDA FoodData Central API (extra) | M | T9.2, O12 | 11-14 (done 11-06, owner's request) | done |
| [T9.29](tickets/T9.29.md) | NMH1988/fitcoach-ai-assistant#76 | In-app notifications for coaches and gymers (extra; beyond the brief, owner's request, 2026-11-06) | M | T9.12, T9.15, T9.16, T9.23 | 11-14 (after T9.16, before T9.27) | done |
| [T9.30](tickets/T9.30.md) | NMH1988/fitcoach-ai-assistant#87 | Notifications of a new question or answer (extra; beyond the brief, owner's request, 2026-11-06; split out of T9.25, 2026-11-07) | S | T9.25, T9.29 | 11-15 (after T9.25 and T9.29, before T9.27) | done |
| [T9.27](tickets/T9.27.md) | NMH1988/fitcoach-ai-assistant#71 | README screenshots and a short GIF of the app (extra; beyond the brief, owner's request, 2026-11-06) | M | T9.16, T9.23, T9.11a; T9.17, T9.25, T9.29 and T9.30 when built | 11-16 (after T9.11a, before T9.11) | done |
| [T9.28](tickets/T9.28.md) | NMH1988/fitcoach-ai-assistant#72 | A presentation video of the app with offline narration (extra; beyond the brief, owner's request, 2026-11-06) | M | T9.27 | 11-18 (or after 11-23, owner's choice) | done |
| [T9.31](tickets/T9.31.md) | NMH1988/fitcoach-ai-assistant#108 | Docs: Medium 3 and Hard 5 claimed in part only (owner's request after a check against the full Sprint 3 brief) | S | T9.9, T9.11 | 11-10 | done |
| [T9.32](tickets/T9.32.md) | NMH1988/fitcoach-ai-assistant#110 | The README links the presentation video (extra; beyond the brief, owner's request, 2026-11-10) | S | T9.28, the owner's upload | 11-10 | done |
| [T9.33](tickets/T9.33.md) | NMH1988/fitcoach-ai-assistant#116 | The evaluation as LangSmith experiments, and the agent's evaluation lifecycle documented (extra; owner's request after a reviewer's comment, 2026-11-12) | M | T9.8, T9.10, T8.4, O10 | before T9.11b | in review |
| [T9.34](tickets/T9.34.md) | NMH1988/fitcoach-ai-assistant#117 | Foods the coach suggests to a client, logged by the client in one click (extra; beyond the brief, owner's request after a reviewer's comment, 2026-11-12; cut first if time runs short) | M | T9.13, T9.15, T9.17 | before T9.11b | done |
| [T9.35](tickets/T9.35.md) | NMH1988/fitcoach-ai-assistant#121 | Unmasked LangSmith traces in demo mode only, for the reviewer's demo (extra; owner's request, 2026-11-13) | S | T9.8, T9.5 | before T9.11b | in progress |
| **Last** | | | | | | |
| [T6.2](tickets/T6.2.md) | #20 | README, final checks and transfer to the course repo | S | all, O6 | 11-01 | done |

**Critical path:** T1.1 -> T1.2 -> T2.1 -> T2.2 -> T2.3 -> T3.1 -> T3.2 -> T3.3 -> T3.6 -> T6.1 -> T6.2. T1.3, T4.1 and T4.3 can run alongside it; the extras run after T6.1, or alongside it once their dependencies are done.

**If time runs short, cut in this order:** T4.5, then T7.2 (keep the English answers), then T7.1, then T7.4 (German input still reaches an English UI), then T7.3 (both themes stay from T3.1; only its test, toolbar check and hint go), then T5.2 (or keep it with a plain text layout), then T5.1, then chart polish. T7.3 is beyond the brief, so it goes before T5.2 and T5.1, which the brief asks for (Medium 7, Medium 5). The core requirements and the optional tasks for maximum points (Sprint 2: Medium 3, 6; Hard 1) stay.

---

## Epic 1: Foundation

- [T1.1 Project skeleton, config and CI (S)](tickets/T1.1.md)
- [T1.2 OpenRouter clients and error mapping (S)](tickets/T1.2.md)
- [T1.3 Input guard and rate limit (S)](tickets/T1.3.md)
- [T1.4 Security reviewer agent (S)](tickets/T1.4.md)
- [T1.5 Docs: run commands use the project's venv (S)](tickets/T1.5.md)
- [T1.6 CI: accept the pillow 12.3.0 advisories until Streamlit allows pillow 13 (S)](tickets/T1.6.md)
- [T1.6a CI: upgrade streamlit to 1.66.1 so pillow 13 replaces the pillow ignores (S)](tickets/T1.6a.md)
- [T1.7 Streamlit runs on localhost only, without telemetry or error details (S)](tickets/T1.7.md)
- [T1.8 A fixed message for unexpected errors in a chat turn (S)](tickets/T1.8.md)
- [T1.9 Workflow files: read and check both briefs for every ticket (S)](tickets/T1.9.md)
- [T1.10 Compliance reviewer agent (S)](tickets/T1.10.md)
- [T1.11 CI: offline licence check of the runtime dependencies (S)](tickets/T1.11.md)
- [T1.12 Keep the httpx2, httpcore2 and authlib loggers at WARNING (S)](tickets/T1.12.md)
- [T1.13 Docs: record the Dependabot bumps of 2026-11-09 in the dependency table (S)](tickets/T1.13.md)
- [T1.14 Docs: the repo's own code stays all rights reserved (copyright notice) (S)](tickets/T1.14.md)
- [T1.15 Docs: split PROGRESS and IMPLEMENTATION_PLAN into an index and one file per entry (M)](tickets/T1.15.md)
- [T1.16 Docs: diagrams of the app, the RAG search, the tool loop and the store's sharing (S)](tickets/T1.16.md)

## Epic 2: Knowledge base

- [T2.1 Source manifest, download script, attribution (M)](tickets/T2.1.md)
- [T2.2 Parse article XML and chunk with metadata (M)](tickets/T2.2.md)
- [T2.3 Build and open the Chroma index (S)](tickets/T2.3.md)

## Epic 3: Retrieval and answers

- [T3.1 First answer with sources (vector search) (M)](tickets/T3.1.md)
- [T3.2 Query translation and structured filters (M)](tickets/T3.2.md)
- [T3.3 Hybrid search (BM25 + RRF) (M)](tickets/T3.3.md)
- [T3.6 Retrieval comparison on the owner's evaluation questions (S)](tickets/T3.6.md)
- [T3.7 Drop registration boilerplate and merge short chunk pieces at ingest (S)](tickets/T3.7.md)
- [T3.8 Only the question itself decides whether the sources cover it (S)](tickets/T3.8.md)
- [T3.9 The "About the answers" block opens as a modal (S)](tickets/T3.9.md)
- [T3.4 Prompt injection hardening (S)](tickets/T3.4.md)
- [T3.5 Skip the answer call for off-topic questions with no source (S)](tickets/T3.5.md)

## Epic 4: Profile and tools

- [T4.1 Profile, units and settings (M)](tickets/T4.1.md)
- [T4.2 Energy and macro tools with the calorie floor (M)](tickets/T4.2.md)
- [T4.3 USDA food table and lookup (M)](tickets/T4.3.md)
- [T4.4 Tool-calling loop and tool results UI (M)](tickets/T4.4.md)
- [T4.5 `evaluate_meal_plan` tool (stretch) (S)](tickets/T4.5.md)
- [T4.6 Profile form: a hint instead of "Press Enter to apply" (S)](tickets/T4.6.md)
- [T4.7 My targets: sidebar target, targets tab and Food lookup tab (M)](tickets/T4.7.md)
- [T4.8 Food lookup tab: a searchable dropdown of the USDA foods (S)](tickets/T4.8.md)

## Epic 5: Cost, export and guardrails

- [T5.1 Token usage and cost (S)](tickets/T5.1.md)
- [T5.1a Live-check tests ignore a local secrets.toml (S)](tickets/T5.1a.md)
- [T5.2 Session summary PDF (M)](tickets/T5.2.md)
- [T5.3 Domain guardrails (S)](tickets/T5.3.md)

## Epic 6: Evaluation and submission

- [T6.1 Evaluation run and reflection (S)](tickets/T6.1.md)
- [T6.2 README, final checks and transfer to the course repo (S)](tickets/T6.2.md)

## Epic 7: Language and appearance (extras)

Added by the owner on 2026-10-20. All three tickets are extras: they come after the core and never delay a core ticket. Concept and layout in `docs/UI_DESIGN.md` ("Language" and "Light and dark mode").

- [T7.4 German input guard and guardrails (M)](tickets/T7.4.md)
- [T7.1 Language switch: English and German UI (M)](tickets/T7.1.md)
- [T7.2 German answers end to end (M)](tickets/T7.2.md)
- [T7.3 Light and dark mode (S)](tickets/T7.3.md)

## Epic 8: Sprint 2 review follow-ups

Added by the owner on 2026-10-25 from the reviewer's feedback on the Sprint 2 project (summarised in `docs/BRIEF_SPRINT3.md`, "The Sprint 2 review"). Order agreed with the owner: T8.1, then T1.8 and T8.2, then T8.3 and T8.4, before Epic 9; T8.5 and T8.6 after the agent works. On 2026-10-25 the owner put T9.1 (docs only) before T1.8; the rest of the order stands. Review point 3 (tool questions get unrelated passages) is not a ticket here: T9.3's agentic RAG answers it.

- [T8.1 Split `app.py` into a `views/` package, no behaviour change (L)](tickets/T8.1.md)
- [T8.2 Structured turn logging with no personal data (M)](tickets/T8.2.md)
- [T8.3 At most three chunks per source in the fused list (S)](tickets/T8.3.md)
- [T8.4 Evaluation results as JSON and a committed baseline (M)](tickets/T8.4.md)
- [T8.5 An offline retrieval regression suite in CI (M)](tickets/T8.5.md)
- [T8.6 A manually started live evaluation workflow (S)](tickets/T8.6.md)

## Epic 9: Sprint 3 agent

Added by the owner on 2026-10-25 for the Sprint 3 project, which builds on this app (`docs/BRIEF_SPRINT3.md`); deadline **2026-11-23**. Rewritten the same day by T9.1 for the **coach-first scope** the owner chose (`docs/PRD.md`, "Sprint 3: the agent (coach-first workspace)"; decisions D9-D21 in `docs/ARCHITECTURE.md`; the planned design in its section 16): a coach invites gymers, follows their nutrition and training, and approves the weekly reviews the agent drafts. Earlier owner decisions that stand: a hand-built LangGraph `StateGraph`; conversations never written to disk ("level 2"); real sign-in with `st.login` (Google, OIDC) before any body data is stored, with a guest mode with nothing stored; observability as local JSON logs (T8.2) plus LangSmith with personal data masked. Chat summaries in long-term memory moved to the Capstone (T9.1). Reworked on 2026-11-02 by T9.24 for the coach-first product model the owner chose that day: the AI serves the coach, and a gymer has no AI chat; the gymer logs, shares and reads what the coach approved (`docs/PRD.md`, "Sprint 3").

**This changes the privacy rule:** today the profile lives in the session only and is never written to disk (`.claude/rules/security-privacy.md`, PRD feature 4). T9.6, which adds the store, changes this for signed-in users and updates the rule, the PRD and `docs/SECURITY.md` in the same PR.

**For maximum points (P0):** Medium 2 (memory: T9.4's short-term memory, done; T9.7's long-term memory for the coach), Medium 4 (authentication and personalisation: T9.5, T9.6), Hard 1 (agentic RAG: T9.3, done); Medium 1 and Medium 8 are kept from Sprint 2. **Still met after T9.24** (checked against `docs/BRIEF_SPRINT3.md`): Sprint 3 still reaches "at least 2 medium and 1 hard" from new work alone, as none of the three rests on a gymer's chat. Medium 2 asks for long- or short-term memory in LangChain or LangGraph: the guest's and the coach's chats keep T9.4's short-term memory, and T9.7 moves long-term memory, the course's "remember" tool with a person's approval, to the coach. Medium 4 asks for user authentication and personalisation: T9.5 signs coaches and gymers in with their own role and pages, T9.6 keeps each user's data, and T9.7's preferences personalise the coach's chat. Hard 1 is agentic RAG: the search tool of the guest's and the coach's chats (T9.3). **Should:** T9.17 (raised from P1 by T9.24, right after P0, as the AI now serves the coach), T9.8 (Hard 2), T9.10 (Hard 3). **P1:** T9.25 (new in T9.24). **Moved to the Capstone:** T9.18 (T9.24). **Extras:** T9.9 (Medium 3 and Hard 5 in part only, not counted for maximum points: a fallback inside the food tool, not a tool of its own, T9.31), T8.5, T8.6.

- [T9.1 Sprint 3 product and design decisions (coach-first scope) (M)](tickets/T9.1.md)
- [T9.2 The chat turn as a LangGraph `StateGraph`, same behaviour (L)](tickets/T9.2.md)
- [T9.3 Agentic RAG: searching the knowledge base is the agent's tool (M)](tickets/T9.3.md)
- [T9.4 Short-term memory: a conversation that remembers earlier turns (M)](tickets/T9.4.md)
- [T9.6 The SQLite store and the authorisation layer (L)](tickets/T9.6.md)
- [T9.5 Sign in with Google, roles, guest and demo mode, My data (L)](tickets/T9.5.md)
- [T9.12 Invitations and sharing (M)](tickets/T9.12.md)
- [T9.13 Food and weight diary, and the weekly nutrition metrics (M)](tickets/T9.13.md)
- [T9.14 Workout log and the weekly training metrics (M)](tickets/T9.14.md)
- [T9.15 Coach and gymer dashboards (M)](tickets/T9.15.md)
- [T9.7 Long-term memory for the coach: `remember_preference` with the coach's approval (M)](tickets/T9.7.md)
- [T9.16 Weekly review with the coach's approval (L)](tickets/T9.16.md)
- [T9.19a The pain and injury guard (S)](tickets/T9.19a.md)
- [T9.19 Training sources and indexing (M)](tickets/T9.19.md)
- [T9.20 Training principles in the chat (M)](tickets/T9.20.md)
- [T9.21 Checks: the manifest's authors against the article, and the evaluated code's git state (S)](tickets/T9.21.md)

### The owner's UI decisions of 2026-10-30 (T9.22, T9.23, and T9.15's phone cards)

Made by the owner while reviewing the T9.15 dashboard mockups on a Claude Design canvas (outside the repo, so this section carries them): (1) the app is renamed "Fitcoach AI Assistant"; (2) the language control moves from the header to the sidebar, labelled "Language", with the options "English" and "Deutsch" and no icon; (3) a custom CSS layer is allowed for the whole app: one fixed stylesheet in the repo, loaded with `st.html`, aimed at the classes `st.container(key=...)` gives (`st-key-<key>`) and a few stable test ids, never a CDN or any external CSS (visitors' IPs stay off third-party hosts, as with the fonts); this replaces the "native first" principle of `docs/UI_DESIGN.md` and widens the single `st.html` exception in `docs/SECURITY.md`; (4) a brand sidebar: a deep green background with light text through the sidebar theme of `.streamlit/config.toml`, and `st.logo`; (5) on phones the coach's client list shows as cards, while tablets and desktops keep the table (a CSS media query, as Streamlit cannot read the screen width). The owner's answers of the same day, after the draft: a week in progress says "4 of 7 days logged" (AC-26's wording, unchanged); the German UI keeps the same name, the language label is "Sprache" in German, the PDF's file name stays, the stylesheet sets no colours, and the cut order below stands. The planned look is described in `docs/UI_DESIGN.md`, "Planned: the owner's UI decisions of 2026-10-30".

- [T9.22 The app's new name: Fitcoach AI Assistant (S)](tickets/T9.22.md)
- [T9.23 Brand sidebar, language control in the sidebar and a custom CSS layer (M)](tickets/T9.23.md)

### The other Epic 9 tickets

- [T9.24 Coach-first rework: gymers without the AI chat (planning) (M)](tickets/T9.24.md)
- [T9.11a The app's title, intro and chat texts name training principles (S)](tickets/T9.11a.md)
- [T9.11 Sprint 3 documentation and reflection (M)](tickets/T9.11.md)
- [T9.11b Copy the repo into the Sprint 3 course repository (S)](tickets/T9.11b.md)
- [T9.8 LangSmith tracing with personal data masked (M, should)](tickets/T9.8.md)
- [T9.10 Evaluation report with Ragas or DeepEval (M, should)](tickets/T9.10.md)
- [T9.17 Coach assistant: client tools, a follow-up flag, coach-set targets (M, should)](tickets/T9.17.md)
- [T9.25 Questions to the coach under an approved review (M, P1)](tickets/T9.25.md)
- [T9.18 Logging by chat with the gymer's approval (M, P1)](tickets/T9.18.md)
- [T9.9 Food lookup through the USDA FoodData Central API (M, extra)](tickets/T9.9.md)
- [T9.26 Capstone plan: the gymer's own preferences shared with the coach, and gymer-drafted meal plans (S)](tickets/T9.26.md)
- [T9.27 README screenshots and a short GIF of the app (M, extra)](tickets/T9.27.md)
- [T9.28 A presentation video of the app with offline narration (M, extra)](tickets/T9.28.md)
- [T9.29 In-app notifications for coaches and gymers (M, extra)](tickets/T9.29.md)
- [T9.30 Notifications of a new question or answer (S, extra)](tickets/T9.30.md)
- [T9.31 Docs: Medium 3 and Hard 5 claimed in part only (S)](tickets/T9.31.md)
- [T9.32 The README links the presentation video (S, extra)](tickets/T9.32.md)
- [T9.33 The evaluation as LangSmith experiments, and the agent's evaluation lifecycle documented (M, extra)](tickets/T9.33.md)
- [T9.34 Foods the coach suggests to a client, logged by the client in one click (M, extra)](tickets/T9.34.md)
- [T9.35 Unmasked LangSmith traces in demo mode only, for the reviewer's demo (S, extra)](tickets/T9.35.md)
