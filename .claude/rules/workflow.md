# Workflow, tickets and pull requests (mandatory)

## Workflow

- For **every coding task** (features, bug fixes, refactors, tickets), invoke the `qrspi` skill (`.claude/skills/qrspi/SKILL.md`) first and follow its phases in order: Question -> Research -> Structure -> Plan -> Implement. Do not edit code before the Implement phase.
- After finishing a ticket and before opening or merging its PR, run the `code-reviewer` agent (`.claude/agents/code-reviewer.md`). For PRs that touch the guard, prompts, tools, retrieval or secrets handling, also run Claude Code's built-in `/security-review`.
- **Run the `compliance-reviewer` agent** (`.claude/agents/compliance-reviewer.md`) after the code-reviewer and before merging, when a PR does any of these (owner's rule, 2026-10-27, T1.10); if its findings change the PR, run the code-reviewer again on those changes. The paths below are examples: the wording decides, and when unsure, run it.
  - adds, removes or changes knowledge base sources or other content that is not our own: `data/sources.json`, `docs/SOURCES.md`, `ATTRIBUTION.md`, `data/usda_foods.csv`, the download, preparation or ingest code (`scripts/download_sources.py`, `scripts/prepare_usda.py`, `src/rag/sources.py`, `src/rag/ingest.py`), fonts or images (`assets/`, `docs/ui/`), or test fixtures that hold text;
  - adds a dependency or changes a pinned version by hand (Dependabot version bumps are exempt: a licence they change or a package they pull in is caught by the licence listing of the whole-repo run before each copy to the course repository);
  - changes which personal data is collected, stored, sent to a model or a third party, logged, traced, exported or deleted: `src/store/`, the profile, what goes into model messages (`<profile>`, `<memories>`, a client's week), `src/observability.py`, sign-in, tracing, export and delete, and the privacy, consent or data text the user sees (`src/i18n.py`, e.g. the profile caption; `views/`);
  - adds a service, host or model provider that the app or a script talks to;
  - changes what the app says it is or does medically: the disclaimer (`DISCLAIMER` in `src/config.py`, its texts in `src/i18n.py`), the domain guardrails and the limits they use (`src/guardrails.py`, `PROFILE_AGE_RANGE` and `CALORIE_FLOOR_KCAL` in `src/config.py`, the guardrails in `docs/PRD.md`), or the guardrail and citation parts of the system prompts (`src/prompts/`);
  - prepares a public deployment or changes `docs/DEPLOYMENT.md`;
  - changes what stays out of the repo or leaves the page: `.gitignore` (raw texts, the index, evaluation reports, secrets, the store), `.streamlit/config.toml` (server address, telemetry, error details); or what the app says it is for (the README, the About and header text in `views/about.py`, `views/header.py` and `src/i18n.py`), or the evaluation questions and good answers (`data/eval_questions*.json`).

  Also run it on the whole repo before each copy or update of the course repository and before the first public deployment (`docs/DEPLOYMENT.md`); once the app is deployed, the runs on the PRs this rule covers are enough. A PR that touches none of these does not need it; its description says so. **Its findings:** a Blocker, as the agent defines it (e.g. a tracked key or real personal data, an excluded or unlicensed text, personal data reaching a third party with no recorded decision), is always fixed before merging, as merged content stays in the history that is copied to the course repository; a High is fixed in the PR, unless the owner decides to merge with it (recorded in the PR's PROGRESS entry); a Medium or Low is fixed or becomes a follow-up ticket, by the owner's choice. A finding is open until it is fixed or the owner's decision to keep it is recorded; a recorded decision does not block a later copy or deployment. The PR's PROGRESS entry records the run (verdict, and what each finding led to). Its "Before a public deployment" items and owner checks go to the Capstone or to the ticket they belong to, not into the PR.
- **The owner writes first** for the system prompt(s) and the evaluation questions: the owner drafts, Claude reviews and suggests changes. Do not write them for the owner.
- **Every task ends with a report**: which acceptance criteria are met (with the test or check for each), what was verified and what was not, then a plain-language "what I did and why" walkthrough: each changed file, what changed, and why that choice was made.

## Tickets

- Tickets are GitHub issues, planned in `docs/IMPLEMENTATION_PLAN.md` with an ID (e.g. `T1.2`) and a status there. **Every ticket has testable acceptance criteria**; a ticket without them is not started until the owner approves criteria.
- The repo will be copied into the course repository without its issues and PRs, so the plan, `docs/PROGRESS.md` and commit messages must carry the record. Name the ticket ID (e.g. `T1.2`) in branch names, PR titles, commit messages and PROGRESS entries, not only the issue number.

## Pull requests

- One ticket per PR, on its own branch from `main` (e.g. `feature/t1.2-short-name`). Never commit directly to `main` once the setup ticket has merged.
- The PR description follows `.github/pull_request_template.md`: `Closes #<issue>` on the first line (not `Refs`), the items it serves by their numbers in `docs/BRIEF_SPRINT3.md` and `docs/BRIEF.md` ("none" for a brief it does not touch, or "beyond the brief (owner's request)" when neither covers it), checked against both briefs and the PRD, changes, **each acceptance criterion with the test or check that proves it**, testing done, sources and copyright checks. `.github/workflows/pr-checks.yml` fails a PR that closes no issue (Dependabot is exempt; a stacked PR is checked by keyword until it targets `main`).
- Closing keywords only fire when the PR merges into `main`. Retarget a stacked PR to `main` after its base PR merges, before merging it.
- **Every PR adds its own entry** at the top of `docs/PROGRESS.md` and updates the ticket's status in `docs/IMPLEMENTATION_PLAN.md` (Dependabot exempt).
- Commit, push, open PRs or merge only when the owner asks.
