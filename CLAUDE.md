# CLAUDE.md

Nutrition AI Assistant for Gym Enthusiasts: a domain-specialised RAG chatbot with tool calling (Turing College, Sprint 2 project, deadline 2026-11-02). Status: in development; see `docs/IMPLEMENTATION_PLAN.md`.

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
| `.claude/agents/security-reviewer.md` | Optional attacker-minded security audit (injection, guard before spend, key, personal data); read-only, no API or network calls except GitHub through `git`/`gh` |

## Code conventions

- Every function, method and class (tests and fixtures included) gets a one-line docstring saying in plain words what it does. Review checks this; no test enforces it.
- Business logic lives in `src/`, not `app.py`. Defaults and limits (models, max lengths, calorie floor, tool loop limit) live in config, not as magic numbers.
- Internally everything uses kg and cm; other units are converted only at input and display.
- All LLM, embedding and network calls are mocked in tests (`docs/TESTING.md`).

## Commands

Python 3.14 (`.python-version`), in a local `.venv`. Every command below assumes the venv is active; otherwise call its programs directly (`.venv\Scripts\python.exe` in PowerShell, `.venv/Scripts/python.exe` in Git Bash, `.venv/bin/python` on macOS and Linux). The system Python lacks the project's packages: the app then fails with `ModuleNotFoundError: No module named 'langchain_chroma'`, a script with a `ModuleNotFoundError` for its first import (e.g. `'chromadb'` or `'src'`). If another project is installed in the system Python with its own `src` package, `src` points there instead and a script fails later, e.g. `ModuleNotFoundError: No module named 'src.rag'`; run it with the venv's Python.

- Install: `pip install -e ".[dev]"`
- Run: `streamlit run app.py` with `.venv` active, or `.venv\Scripts\streamlit.exe run app.py` (PowerShell), `.venv/Scripts/streamlit.exe run app.py` (Git Bash), `.venv/bin/streamlit run app.py` (macOS and Linux)
- Download sources: `python scripts/download_sources.py` (Europe PMC REST API only, into gitignored `data/raw/`); after changing `data/sources.json` or `data/usda_foods.csv`, `python scripts/generate_attribution.py`
- Build the vector index: `python scripts/build_index.py` (needs the key and the downloaded articles; writes gitignored `chroma/`; rerun after the sources or the chunking change; stop the app before rebuilding and restart it afterwards)
- USDA foods table: download the Foundation Foods CSV zip from https://fdc.nal.usda.gov/download-datasets/ into gitignored `data/usda/`, then `python scripts/prepare_usda.py`, `python scripts/generate_attribution.py`, and commit `data/usda_foods.csv` and `ATTRIBUTION.md`
- Retrieval live check (owner, needs the key and the index): `python scripts/live_check_retrieval.py "<question>" ...` prints the nearest chunks' distances, to set `RETRIEVAL_MAX_DISTANCE`
- Retrieval comparison (owner, needs the key, the index and the evaluation questions in `data/eval_questions.json`): `python scripts/compare_retrieval.py` prints vector-only, keyword-only and hybrid hit rates (T3.6; format in `docs/TESTING.md`)
- Evaluation run (owner, needs the key, the index and `data/eval_questions.json`): `python scripts/run_evaluation.py [--repeat N] [--language en|de] [questions file]` asks every evaluation question through the app's chat turn, prints the sources found and cited, tools, tokens and cost, and writes a full report to gitignored `data/eval_runs/` (T6.1; how to record it in `docs/TESTING.md`). German run (T7.2): `python scripts/run_evaluation.py --language de data/eval_questions_de.json`
- Lint/format: `ruff check .` / `ruff format .`
- Test: `python -m pytest -q` (LLM, embedding and network calls must be mocked)
- Audit: `pip-audit .` with the `--ignore-vuln` flags listed in `.github/workflows/ci.yml` (reasons in `docs/SECURITY.md`)

CI (`.github/workflows/ci.yml`) runs lint, tests with coverage and `pip-audit` on every push to `main` and every PR.
