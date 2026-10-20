# Nutrition AI Assistant for Gym Enthusiasts

A chatbot that answers nutrition questions for adults who do recreational strength training. It combines retrieval-augmented generation over open-licensed sports nutrition research with tools for personal calculations (energy needs, macro targets) and food lookups.

**Status:** in development (see [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)). Built as the Sprint 2 project of the Turing College AI Engineering course, deadline 2026-11-02.

## Documentation

| Document | Contents |
|---|---|
| [`docs/BRIEF.md`](docs/BRIEF.md) | Summary of the course brief |
| [`docs/PRD.md`](docs/PRD.md) | What we build: features, guardrails, acceptance criteria |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technical design and decisions |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Tickets, order and status |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy and evaluation results |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model and controls |
| [`docs/SOURCES.md`](docs/SOURCES.md) | Knowledge base sources and their licences |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deployment notes |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | What each change did and why |

Stack: Python, Streamlit, LangChain, OpenRouter, Chroma, USDA FoodData Central.

## Run locally

Requires Python 3.14 and an [OpenRouter](https://openrouter.ai/keys) API key.

```bash
python3.14 -m venv .venv      # Windows: py -3.14 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1 (PowerShell)
                              # or source .venv/Scripts/activate (Git Bash)
pip install -e ".[dev]"
```

Set the key in one of two ways (never commit it):

- copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (gitignored) and paste your key there, or
- set the `OPENROUTER_API_KEY` environment variable.

Run every command below in a terminal where `.venv` is active: the prompt starts with `(.venv)`. A new terminal does not have it: activate it again (second line above), or call the venv's programs directly:

- Windows (PowerShell or cmd): `.venv\Scripts\streamlit.exe run app.py`, `.venv\Scripts\python.exe scripts/build_index.py`
- Windows (Git Bash): `.venv/Scripts/streamlit.exe run app.py`, `.venv/Scripts/python.exe scripts/build_index.py`
- macOS and Linux: `.venv/bin/streamlit run app.py`, `.venv/bin/python scripts/build_index.py`

If a command fails with a `ModuleNotFoundError`, such as `No module named 'langchain_chroma'` from the app or `No module named 'src'` from a script, it was started with another Python (the system one), not the venv's.

Before the first question, build the knowledge base once:

```bash
python scripts/download_sources.py   # fetch the approved articles from the Europe PMC API into data/raw/ (no key needed)
python scripts/build_index.py        # embed them into the local index in chroma/ (needs the key; under one US cent at the 2026-10 price)
```

Stop the app before rebuilding the index and start it again afterwards.

Then:

```bash
streamlit run app.py      # start the app
python -m pytest -q       # run the tests (no key needed; all API calls are mocked)
ruff check . && ruff format --check .   # lint and format check
```

The app runs locally only for now; a public deployment needs one of the options in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Content and licences

The knowledge base uses only openly licensed material (CC BY articles and the public-domain USDA FoodData Central data). Each source keeps its own licence and is credited; see [`docs/SOURCES.md`](docs/SOURCES.md).

## Disclaimer

This project gives general information for healthy adults. It is not medical advice and does not replace a doctor or a registered dietitian.
