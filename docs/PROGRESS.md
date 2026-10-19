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
