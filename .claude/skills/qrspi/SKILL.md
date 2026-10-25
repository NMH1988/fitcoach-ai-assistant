---
name: qrspi
description: Enforces the QRSPI workflow (Question, Research, Structure, Plan, Implement) for any coding task in this repo - new features, bug fixes, refactors, tickets from GitHub issues. Use before writing or changing code.
---

# QRSPI workflow

Run the five phases **in order** for every coding task. Do not write or edit code before the Implement phase. Announce each phase with a heading (`## Q`, `## R`, `## S`, `## P`, `## I`) so progress is visible.

Trivial edits (typo, comment, formatting, a one-line config change) may collapse Q-R-S-P into a single sentence, but must still state the plan before editing.

## 1. Question
First read `CLAUDE.md` and `.claude/rules/` (rules and the copyright policy), **both briefs, for every ticket**: `docs/BRIEF.md` (what the Sprint 2 course brief asks) and `docs/BRIEF_SPRINT3.md` (what the Sprint 3 brief asks, and the reviewer's points on Sprint 2), then `docs/PRD.md` (what we build), the ticket's entry in `docs/IMPLEMENTATION_PLAN.md` and `docs/PROGRESS.md`, and run `gh pr list --state open`, so the brief, earlier decisions, open work and follow-ups shape the questions. If the task touches the knowledge base, data, prompts, tests, fixtures or docs content, also read `docs/SOURCES.md`. If `gh` is not installed or not logged in, say so and go on with only the log. Then break the task into clarifying questions.
- List every unknown that affects the solution: scope, inputs/outputs, edge cases, acceptance criteria, constraints, affected files.
- If the task comes from a GitHub issue, read it (`gh issue view <n>`) and turn each acceptance criterion into at least one question. A ticket without testable acceptance criteria is a **needs the user** question: propose criteria and get them approved before going on.
- Name what the ticket serves **by its number in each brief**: from `docs/BRIEF_SPRINT3.md` a core requirement (1-5), an optional task (Easy, Medium or Hard n), an evaluation item or a Sprint 2 review point (1-5); from `docs/BRIEF.md` a core requirement or optional task. Write "none" for a brief it does not touch, and "beyond the brief (owner's request)" only when neither brief covers the work. Check a "beyond the brief" claim against both files before writing it (the evaluation sections count too). Read the full brief when the exact wording matters; ask the owner for it if it is not at hand. If the ticket, `docs/IMPLEMENTATION_PLAN.md` or the prompts **contradict** either brief, `docs/PRD.md` or the copyright policy, or a choice changes **what the product does** (which users it serves, what advice it gives, what data it keeps), list it as a **needs the user** question instead of inferring an answer.
- Mark each question as **answerable from the code/docs** or **needs the user**.
- Ask the user the "needs the user" questions and wait for answers before moving on, unless a sensible default exists; if so, state the default explicitly. A brief or policy contradiction, or a choice that changes what the product does, is never settled by a default: always ask. When the user requested the change, still flag it if it contradicts the brief or goes beyond it ("beyond the brief (owner's request)"); a requested change in line with the brief needs no second question.

## 2. Research
Answer each question **using only facts from the codebase or provided documents** (files, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/PROGRESS.md`, `docs/SOURCES.md`, issues, README, the user's messages).
- Read the relevant files; run read-only commands (grep, tests, `git log`) as needed.
- For each answer, cite the source (`path:line`, issue number, or document).
- Never answer from assumption or memory. If the repo does not contain the answer, write "Not found in codebase" and either ask the user or record it as an explicit assumption.
- Do not propose solutions yet.

## 3. Structure
Organize the work into **vertical slices**.
- Each slice delivers a thin, end-to-end, independently verifiable behaviour (e.g. UI -> guard -> retriever -> LLM -> answer with sources for one path), not a horizontal layer ("all tools first").
- Order slices so the first one is the smallest working path; later slices extend it.
- For each slice give: goal, files touched, how it is verified (which unit, integration or UI test, or which manual check), and which acceptance criteria it satisfies.

## 4. Plan
Produce a detailed implementation plan from the slices.
- Numbered steps per slice: exact files/functions to create or change, tests to write first or alongside, commands to run.
- Map every acceptance criterion to the test or check that proves it.
- Include risks and rollback notes where relevant.
- Present the plan to the user and **wait for approval** before implementing, unless the user already said to proceed.

## 5. Implement
Execute the plan step by step.
- Work one slice at a time; after each slice run `ruff check .`, `ruff format --check .` and `python -m pytest -q` and fix failures before continuing.
- Mock all LLM, embedding and network calls in tests; never put API keys in code or the repo.
- Use only approved sources from `docs/SOURCES.md`; follow the copyright policy in `.claude/rules/copyright.md`.
- Give every new function, method and class (tests and fixtures included) a one-line docstring saying what it does (review checks this; no test enforces it).
- Stay inside the plan. If new information invalidates it, stop, go back to the relevant phase, and update the plan.
- Add an entry at the top of `docs/PROGRESS.md` (format at the top of that file) in the same PR: what changed, why, decisions/gotchas, follow-ups. Update the ticket's status in `docs/IMPLEMENTATION_PLAN.md`. Name the ticket ID (e.g. `T1.2`) in the branch, commits and PR title.
- Write the brief items named in the Question phase, by their numbers, in the PR description's "Brief" section (one line per brief, as in `.github/pull_request_template.md`), the plan's **Serves** line and the PROGRESS **Brief:** line; the three say the same.
- Finish by reporting which acceptance criteria are met (with the test or check for each), what was verified, and anything not done, followed by a plain-language "what I did and why" walkthrough (each changed file, what changed, why that choice). Commit/push only when the user asks.
