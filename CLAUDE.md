# CLAUDE.md

Nutrition AI Assistant for Gym Enthusiasts: a domain-specialised RAG chatbot with tool calling (Turing College, Sprint 2 project, deadline 2026-11-02). Status: planning; no code yet.

The owner writes in Vietnamese: reply in Vietnamese. Everything in the repo is in English: code, comments, docstrings, documentation, commit messages, issues and PRs.

## Mandatory reading (non-negotiable)

1. **Before writing or changing any code**, in every session: read this whole file and the rules in `.claude/rules/` (the unconditional ones load automatically: `copyright.md`, `workflow.md`, `security-privacy.md`; `testing.md` loads when working on `tests/`).
2. **Before starting any ticket**: read `docs/BRIEF.md` (what the course asks) and `docs/PRD.md` (what we build) and check the ticket against them, then read `docs/PROGRESS.md` and run `gh pr list --state open`. If the ticket touches the knowledge base, data, prompts, tests, fixtures or docs content, also read `docs/SOURCES.md`.
3. If a ticket, plan or prompt contradicts the brief, the PRD or the copyright policy, or a choice changes what the product does, stop, say so and ask the owner. Don't guess. Always flag work the brief does not ask for, even when the owner asked for it (label it "beyond the brief (owner's request)").

## Where things are

| File | What it holds |
|---|---|
| `docs/BRIEF.md` | Summary of the course brief (requirements, optional tasks, evaluation) |
| `docs/PRD.md` | Product decisions, features, guardrails, product-level acceptance criteria |
| `docs/ARCHITECTURE.md` | Technical design and the approved decisions D1-D8 |
| `docs/IMPLEMENTATION_PLAN.md` | Epics, tickets, acceptance criteria, dependencies, order, status |
| `docs/TESTING.md` | Test strategy, evaluation results, live-check records |
| `docs/SECURITY.md` | Vulnerability reporting, threat model and controls |
| `docs/SOURCES.md` | Approved and excluded knowledge base sources with licences |
| `docs/DEPLOYMENT.md` | Deploy notes and the checklist for copying the repo to the course repository |
| `docs/PROGRESS.md` | What each PR did and why, newest first |
| `.claude/rules/` | Copyright, workflow, security and privacy, testing rules |
| `.claude/skills/qrspi/`, `.claude/agents/code-reviewer.md` | The coding workflow and the reviewer |

## Code conventions

- Every function, method and class (tests and fixtures included) gets a one-line docstring saying in plain words what it does. Review checks this; no test enforces it.
- Business logic lives in `src/`, not `app.py`. Defaults and limits (models, max lengths, calorie floor, tool loop limit) live in config, not as magic numbers.
- Internally everything uses kg and cm; other units are converted only at input and display.
- All LLM, embedding and network calls are mocked in tests (`docs/TESTING.md`).

## Commands

Added in the setup ticket, when `pyproject.toml` exists. Expected, as in Sprint 1: install `pip install -e ".[dev]"`, run `streamlit run app.py`, lint `ruff check .` / `ruff format .`, test `python -m pytest -q`.
