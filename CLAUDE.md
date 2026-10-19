# CLAUDE.md

Nutrition AI Assistant for Gym Enthusiasts: a domain-specialised RAG chatbot with tool calling (Turing College, Sprint 2 project). Brief: `docs/BRIEF.md`. Sources: `docs/SOURCES.md`. Plan and tickets: `docs/PLAN.md` (once written) and the GitHub issues. Status: planning; no code yet.

The owner writes in Vietnamese: reply in Vietnamese. Everything in the repo is in English: code, comments, docstrings, documentation, commit messages, issues and PRs.

## Mandatory reading (non-negotiable)

1. **Before writing or changing any code**, in every session: read this whole file, including the copyright policy below.
2. **Before starting any ticket**: read `docs/BRIEF.md` and check the ticket against it, then read `docs/PROGRESS.md` (what earlier PRs did, decisions, follow-ups) and run `gh pr list --state open`. If the ticket touches the knowledge base, data, prompts, tests, fixtures or docs content, also read `docs/SOURCES.md`.
3. If a ticket, plan or prompt contradicts the brief or the copyright policy, or a choice changes what the product does, stop, say so and ask the owner. Don't guess what the brief or the policy probably means. Always flag work the brief does not ask for, even when the owner asked for it (label it "beyond the brief (owner's request)").

## Workflow (mandatory)

- For **every coding task** (features, bug fixes, refactors, tickets), invoke the `qrspi` skill (`.claude/skills/qrspi/SKILL.md`) first and follow its phases in order: Question -> Research -> Structure -> Plan -> Implement. Do not edit code before the Implement phase.
- After finishing a ticket and before opening or merging its PR, run the `code-reviewer` agent (`.claude/agents/code-reviewer.md`). For PRs that touch the guard, prompts, tools, retrieval or secrets handling, also run Claude Code's built-in `/security-review`.
- **The owner writes first** for the system prompt(s) and the evaluation questions: the owner drafts, Claude reviews and suggests changes. Do not write them for the owner.
- **Every task ends with a report**: which acceptance criteria are met (with the test or check for each), what was verified and what was not, then a plain-language "what I did and why" walkthrough: each changed file, what changed, and why that choice was made.

## Tickets and pull requests

- Tickets are GitHub issues, planned in `docs/PLAN.md`. **Every ticket has testable acceptance criteria**; a ticket without them is not started until the owner approves criteria.
- One ticket per PR, on its own branch from `main` (e.g. `feature/t1.2-short-name`). Never commit directly to `main` once the project setup is done.
- The PR description follows `.github/pull_request_template.md`: `Closes #<issue>` on the first line (not `Refs`), the brief requirement it serves, changes, **each acceptance criterion with the test or check that proves it**, testing done, sources and copyright checks. `.github/workflows/pr-checks.yml` fails a PR that closes no issue (Dependabot is exempt; a stacked PR is checked by keyword until it targets `main`).
- Closing keywords only fire when the PR merges into `main`. Retarget a stacked PR to `main` after its base PR merges, before merging it.
- **Every PR adds its own entry** at the top of `docs/PROGRESS.md` (Dependabot exempt).
- Commit, push, open PRs or merge only when the owner asks.

## Code conventions

- Every function, method and class (tests and fixtures included) gets a one-line docstring saying in plain words what it does. Review checks this; no test enforces it.
- Business logic lives in `src/`, not `app.py`. Defaults and limits (models, max lengths, calorie floor, tool loop limit) live in config, not as magic numbers.
- Internally everything uses kg and cm; other units are converted only at input and display.

## Testing

- **Unit tests** for pure logic: calculators, unit conversion, input guard, chunking, metadata filters, citation formatting, PDF content.
- **Integration tests** with fakes: ingest -> Chroma (in-memory or a temp dir) -> retrieval -> answer, and the tool-calling loop with a scripted fake model.
- **UI tests** with `streamlit.testing.v1.AppTest` for visible UI changes. This is our end-to-end level; browser E2E (e.g. Playwright) is not planned.
- **All LLM, embedding and network calls are mocked.** The suite and CI run with no API key.
- **Live checks** (real model, real key) are manual, run by the owner, and recorded faithfully in `docs/PROGRESS.md` or the evaluation file; they are never part of CI.
- CI (`.github/workflows/ci.yml`, added in the setup ticket) runs lint, tests and `pip-audit` on every push and PR, as in Sprint 1.

## Commands

Added in the setup ticket, when `pyproject.toml` exists. Expected, as in Sprint 1: install `pip install -e ".[dev]"`, run `streamlit run app.py`, lint `ruff check .` / `ruff format .`, test `python -m pytest -q`.

## Secrets and the OpenRouter key

- The key is read only from `.streamlit/secrets.toml` or the `OPENROUTER_API_KEY` environment variable, through one config function. Both files are gitignored; only `.streamlit/secrets.toml.example` with a placeholder is committed.
- Never hardcode, log, print, display, or put the owner's key in exceptions, `st.session_state`, tests, issues, PRs or commit messages. Never open the real secrets file. (If the "bring your own key" option in `docs/DEPLOYMENT.md` is built, a visitor's own key may live in the session only, under the same never-log, never-show rules.)
- **No anonymous visitor may spend the owner's key.** A public deployment must use one of the options in `docs/DEPLOYMENT.md` (the visitor brings their own key, or an access gate plus a spending limit). Until then the app runs locally only.

## Personal data

- The user's profile (weight, height, age, sex, goal) lives in `st.session_state` only for the session. It is never logged, written to disk, sent anywhere except the LLM call that needs it, or put in the vector store.
- The PDF summary is built in memory and downloaded by the user; the server keeps no copy.

## Copyright and licensing policy (non-negotiable)

This is the owner's personal, public repository: shared with the course for review, viewed by recruiters, and possibly opened as open source later. Everything in it must be legally reusable and redistributable by anyone, without asking for permission. The owner chose this strict level on purpose; do not relax it without their explicit decision.

1. **Only open-licensed content.** Allowed: public domain, CC0, and CC BY (any version), or an equivalent licence that allows redistribution, derivatives and commercial use with attribution only.
2. **Everything that needs permission or a licence grant is excluded.** That includes: all rights reserved, "free to read" without a reuse licence, paywalled content, CC BY-NC, CC BY-ND, CC BY-NC-ND, share-alike database licences (ODbL), and any source whose licence we could not verify. Unknown licence = excluded.
3. **The approved list is `docs/SOURCES.md`.** Use nothing else in the knowledge base, prompts, tests, fixtures, examples or docs. Do not copy or closely paraphrase excluded sources. A plain link to an official page is not copying, but nothing from that page goes into the project.
4. **Adding a source** requires: reading the licence line on the publisher or article page itself (aggregator metadata alone is not enough), recording the licence, URL and check date in `docs/SOURCES.md`, and the owner's approval before it is used.
5. **Text only.** Do not extract figures, tables or images from articles. They may be reproduced from third parties under other terms.
6. **Attribution.** Keep an `ATTRIBUTION.md` (authors, title, year, DOI/URL, licence link, "split into chunks" as the change made). Every chunk carries `source_url`, `license`, `authors`, `year` metadata so the app can cite it.
7. **Raw documents are not committed by default.** Commit a manifest and a download script. Commit a text only when its row in `docs/SOURCES.md` is marked verified on the article page.
8. **Code and dependencies.** Do not paste code, prompts or text from sources with an incompatible or unknown licence. Prefer permissively licensed libraries (MIT, BSD, Apache-2.0) and check a new dependency's licence before adding it. The repo's own code licence (if one is added) does not relicense the third-party content; each document keeps its own licence.
9. **When in doubt, stop and ask the owner.** This policy is a working rule, not legal advice; the owner makes the final call.
