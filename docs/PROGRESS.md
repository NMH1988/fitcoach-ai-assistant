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
