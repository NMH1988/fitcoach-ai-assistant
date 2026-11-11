[Progress log](../PROGRESS.md)

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
