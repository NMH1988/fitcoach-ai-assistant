# Progress log

What each PR did and why, newest first. **Read this before starting a ticket**, together with the open PRs (`gh pr list --state open`), so earlier decisions and loose ends are not lost.

**Adding an entry:** every PR (Dependabot exempt) adds one entry at the top of the log below, in the same PR, so the log reaches `main` together with the work. Keep it short and record what the code does not say. Parallel PRs all add at the top, so they conflict here: keep both entries. `.gitattributes` sets `merge=union` for this file, which handles local merges; GitHub's web conflict editor ignores it.

```
## YYYY-MM-DD · T<x.y> <title> · #<PR> (closes #<issue>)
- **Brief:** the requirement or optional task served, or "beyond the brief (owner's request)".
- **What:** files/behaviour changed.
- **Why:** reason for the approach chosen.
- **Decisions & gotchas:** anything a future session must know.
- **Follow-ups:** what is left, with ticket numbers.
```

---

## 2026-10-19 · T1.1 Project skeleton, config and CI · #21 (closes #1)
- **Brief:** core requirement 4 (technical base); CI as in Sprint 1.
- **What:**
  - `pyproject.toml`: the runtime packages pinned as in `docs/ARCHITECTURE.md` section 12; the dev tools pinned too (pip-audit 2.10.1, pytest 9.1.1, pytest-cov 7.1.0, ruff 0.17.1) so a new tool release cannot break CI on an unrelated PR; ruff and pytest settings as in Sprint 1. `.python-version` 3.14.
  - `src/config.py`: app title, intro and disclaimer; OpenRouter base URL; allowed models with `gpt-5-mini` for answers and `gpt-5-nano` for query translation; embedding model; token budget and cap; input length and rate limits; `get_api_key()` reused from Sprint 1 (secrets first, then the env var; never shows the key; its own error for a broken secrets file).
  - `app.py`: title, intro and the disclaimer only.
  - Tests: `tests/test_config.py` (models, limits, the Sprint 1 key tests with fake `sk-test-` keys, the missing-key message holds no key), `tests/test_app_smoke.py` (AppTest with no key: no exception, the title, the disclaimer).
  - `.github/workflows/ci.yml` (lint, tests with coverage, pip-audit) and `.github/dependabot.yml`, as in Sprint 1. `CLAUDE.md` lists the real commands.
- **Why:** the smallest base every later ticket builds on, with CI from the first PR.
- **Decisions & gotchas:**
  - `pip-audit` found four advisories in chromadb 1.5.9 (the latest; no fix yet), all in Chroma's HTTP server. The owner chose to keep Chroma: CI ignores exactly those four IDs with the reason next to them, `docs/SECURITY.md` lists them as accepted risks, and `.claude/rules/security-privacy.md` forbids running Chroma as a server or using its embedding functions. Dependabot will propose a fixed release; then remove the ignores.
  - The app does not read the key yet; the missing-key message in the UI comes with the first model call (T3.1).
  - Limits for retrieval, tools and the calorie floor are added by the tickets that use them, not here.
  - Checked locally on Python 3.14.8: ruff clean, 26 tests pass (coverage 99%), pip-audit clean with the four ignores.
  - Code review (round 1, before the PR): pip-audit added to the dev extra and the dev tools pinned; the unused `packaging` dev dependency dropped; config notes that the limits come from Sprint 1 and the reasoning effort from T1.2. `actions/checkout@v4` and `setup-python@v5` are left for Dependabot.
- **Follow-ups:** T1.2 (#2) builds the OpenRouter clients on this config.

## 2026-10-19 · Implementation plan and GitHub issues · direct commit (no ticket, before the setup ticket)
- **Brief:** plans the work for every core requirement and the chosen optional tasks (Medium 3, 5, 6, 7; Hard 1).
- **What:** `docs/IMPLEMENTATION_PLAN.md`: 6 epics, 19 tickets plus the stretch T4.5, each with testable acceptance criteria mapped to tests or checks; owner tasks O1-O6; order, target dates, critical path and cut order. GitHub issues #1-#20 created, one per ticket (T1.1 = #1 ... T6.2 = #20), and their numbers filled into the plan.
- **Why:** phase 4 of the owner's six-phase process; the owner approved the plan on 2026-10-19.
- **Decisions & gotchas:** issue bodies copy the ticket text from the plan; if a ticket changes, update both. Owner tasks are tracked in the plan only, not as issues.
- **Follow-ups:** T1.1 (#1) starts next on its own branch.

## 2026-10-19 · Legal check of sources and access terms · direct commit (no ticket, before the setup ticket)
- **Brief:** beyond the brief (owner's request): the copyright policy.
- **What:** `.claude/rules/copyright.md`: attribution now keeps the article's copyright and licence notices and implies no endorsement; new rule 7 (do not distort sources; leave out third-party content inside articles); new rule 10 (access terms: automated downloads only through the Europe PMC REST API or PMC's OAI-PMH/FTP/Cloud services; reading, saving or copying a single CC BY article by hand is allowed). `docs/SOURCES.md`: how the licences were checked, the access terms of PMC, Europe PMC and Taylor & Francis, and a summary of the CC BY 4.0 and 2.0 legal codes. `docs/ARCHITECTURE.md`: the download script uses only the Europe PMC REST API.
- **Why:** the owner asked for confirmation that reading, saving and copying the sources breaks no law or licence.
- **Decisions & gotchas:** the licence check on 2026-10-19 read 20 PMC article pages with a short script, which PMC's terms forbid (automated retrieval from its website). Only licence lines were read and no article text was stored; recorded in `docs/SOURCES.md`, and rule 10 prevents a repeat.
- **Follow-ups:** none.

## 2026-10-19 · Project structure, PRD and architecture · direct commit (no ticket, before the setup ticket)
- **Brief:** prepares the whole project; serves the brief's requirements through `docs/PRD.md` and `docs/ARCHITECTURE.md`.
- **What:**
  - `docs/PRD.md` (new): the product decisions moved out of `docs/BRIEF.md`, plus product-level acceptance criteria AC-1 to AC-15. `docs/BRIEF.md` now only summarises the course brief (optional tasks numbered) and the submission approach.
  - `docs/ARCHITECTURE.md` (new): the technical design; decisions D1-D8 approved by the owner.
  - `CLAUDE.md` slimmed to an overview, mandatory reading, a map of the docs, code conventions and commands. Its rules moved to `.claude/rules/`: `copyright.md`, `workflow.md`, `security-privacy.md` (always loaded) and `testing.md` (loaded for `tests/**`).
  - `docs/TESTING.md`, `docs/SECURITY.md` (vulnerability reporting, threat model, controls) and `docs/IMPLEMENTATION_PLAN.md` (format only; tickets come in phase 4) added.
  - `docs/DEPLOYMENT.md`: a checklist for copying the repo to the course repository. README: a docs table. QRSPI skill, code-reviewer and PR template point to the new files and ask for ticket IDs and plan status.
- **Why:** the owner's proposed structure; the repo will be copied to the course repository without issues and PRs, so the record of work must live in files.
- **Decisions & gotchas:**
  - One plan file (`IMPLEMENTATION_PLAN.md`) holds tickets and their status; no separate `TASKS.md`, so the two cannot drift.
  - Only `.streamlit/secrets.toml.example`, no `.env.example`.
  - GitHub shows `docs/SECURITY.md` as the repo's security policy, so it starts with a reporting section.
- **Follow-ups:** write the epics and tickets (phase 4) and the GitHub issues; setup ticket (pyproject, CI, app skeleton); `ATTRIBUTION.md` comes with the source-download ticket.

## 2026-10-19 · Project setup: rules, brief and sources · initial commit (no ticket)
- **Brief:** prepares the whole project; the copyright policy and the public-portfolio goal are beyond the brief (owner's request).
- **What:** `CLAUDE.md` (mandatory reading, QRSPI workflow, PR and ticket rules, testing, secrets, personal data, copyright policy); `docs/BRIEF.md` (course brief summary and the owner's PRD decisions); `docs/SOURCES.md` (21 approved open-licensed sources, excluded sources with reasons); `docs/DEPLOYMENT.md` (notes for a later deploy); `.claude/` QRSPI skill and code-reviewer agent adapted from Sprint 1; PR template and PR checks workflow; `.gitignore` for secrets, downloaded data and the vector store.
- **Why:** the owner wanted the rules, the brief and a legally clean source list settled before any code.
- **Decisions & gotchas:**
  - Licences of all 20 approved articles (and the correction to #18) were read from the article itself on 2026-10-19; #12 is CC BY 2.0, the rest CC BY 4.0.
  - Sprint 1 models (`openai/gpt-5-mini` default, `gpt-5-nano`, `gpt-5`) and `qwen/qwen3-embedding-8b` are on OpenRouter and the chat models support tool calling (checked 2026-10-19); none supports `temperature`.
  - No separate security agent: the code-reviewer's security section now covers user input, retrieved text and tool arguments, and `/security-review` runs on security-relevant PRs.
  - CI (`ci.yml`) is not added yet: it needs `pyproject.toml`, so it comes with the setup ticket.
- **Follow-ups:** confirm the course accepts this personal repo; write `docs/ARCHITECTURE.md`; write `docs/PLAN.md` and the GitHub issues; setup ticket (pyproject, CI, app skeleton).
