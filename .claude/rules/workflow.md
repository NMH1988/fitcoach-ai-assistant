# Workflow, tickets and pull requests (mandatory)

## Workflow

- For **every coding task** (features, bug fixes, refactors, tickets), invoke the `qrspi` skill (`.claude/skills/qrspi/SKILL.md`) first and follow its phases in order: Question -> Research -> Structure -> Plan -> Implement. Do not edit code before the Implement phase.
- After finishing a ticket and before opening or merging its PR, run the `code-reviewer` agent (`.claude/agents/code-reviewer.md`). For PRs that touch the guard, prompts, tools, retrieval or secrets handling, also run Claude Code's built-in `/security-review`.
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
