# Nutrition AI Assistant for Gym Enthusiasts

A chatbot that answers nutrition questions for adults who do recreational strength training. It combines retrieval-augmented generation over open-licensed sports nutrition research with tools for personal calculations (energy needs, macro targets, a day's meal plan) and food lookups. Answers cite the research passages they use; when the sources do not cover a question, the app says so.

**Status:** the project serves two course briefs of the Turing College AI Engineering course. Sprint 2 ([`docs/BRIEF.md`](docs/BRIEF.md), deadline 2026-11-02) is complete; this README describes it. Sprint 3 ([`docs/BRIEF_SPRINT3.md`](docs/BRIEF_SPRINT3.md), deadline 2026-11-23) is in progress: it turns the chatbot into a coach-first workspace with an AI agent, where a coach invites gymers, follows their nutrition and training, and approves the weekly reviews the agent drafts ([`docs/PRD.md`](docs/PRD.md), "Sprint 3"). Every ticket and its status are in [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md); what each change did and why is in [`docs/PROGRESS.md`](docs/PROGRESS.md).

## What it does

- **Chat with sources:** ask a nutrition question; the answer cites the research it used (`[S1]`, `[S2]`...) and lists each cited article with its title, authors, year, evidence tier, licence and link. When the sources do not cover a question, the app says so instead of guessing.
- **Conversation memory:** the chat remembers the earlier questions and answers of the session, so a follow-up such as "and for 200 g?" works; "New chat" starts again and deletes the old conversation. It is kept in memory only, never written to disk (T9.4).
- **Personal numbers:** enter your weight, height, age, sex, activity level and goal (in kg and cm, or lb and ft/in). The assistant calls tools for your daily energy needs, your calorie and macro targets, the nutrients of a food, and a check of a whole day's meal plan against your targets. Tool results show as tables, and the macro split as a chart.
- **My targets and Food lookup tabs:** your targets, and a food search, without asking the chatbot.
- **Token use and cost:** under each answer, and in the Details tab per model call of the last answer and for the current chat ("New chat" starts the total again). The Details tab also shows how the last answer was found (each search the model ran, with its rewrites and filters, or that it ran none).
- **Session summary as PDF:** your profile, targets, questions and answers with their sources, built in memory and downloaded; nothing is kept on the server.
- **English and German:** the app starts in the browser's language (German for a German locale, otherwise English); the EN | DE switch in the header changes it. The UI and the answers follow it, whatever language the question is in (the sources stay English). Light and dark mode through Streamlit's menu.
- **Safety:** input validation, prompt injection protection, a per-session rate limit, and domain guardrails: no dosing advice on performance-enhancing drugs, a 1200 kcal/day calorie floor in the tools, and a redirect to a professional for under 18s, pregnancy, medical conditions and signs of disordered eating. A "not medical advice" disclaimer is always visible.

Your profile is kept in the app's memory for this session only and sent to the model (through OpenRouter) only when a question needs it; it is never logged, written to disk or put in the knowledge base.

## How it works

One chat turn runs as a LangGraph agent whose tools include the knowledge base search, so the agent decides whether to search (agentic RAG, T9.3; details in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), section 2):

1. **Input guard** (`src/guard.py`, `src/guardrails.py`): cleans the text and rejects empty, too long or prompt-injection input and high-risk requests before any API call.
2. **The agent decides** (`src/agent/`): the chat model gets the question, after the conversation's latest earlier questions and answers (T9.4; never their tool results or passages), and calls the search, one of the four tools, or both; a food or calculator question searches nothing. A reply with nothing to rest on (no passage found, no tool run) is not shown: the app says the sources do not cover the question.
3. **Search: query translation** (`src/rag/query_translation.py`): a small model rewrites the search query three ways in English and picks optional filters (topic, year, evidence tier) from a fixed schema.
4. **Search: hybrid retrieval** (`src/rag/`): vector search in a local Chroma index plus BM25 keyword search, for the query and each rewrite, merged with Reciprocal Rank Fusion; a distance limit decides whether the sources cover the query at all. The passages come back to the agent as delimited data.
5. **Answer with tools** (`src/chat.py`, `src/tools/`): with the system prompt (`src/prompts/answer_system.md`), the passages found and the tool results (the tools read the profile from the app, so only their results carry profile values to the model; at most 4 rounds and 2 searches), the model writes the answer with `[S#]` citations.

The knowledge base is 20 open-access sports nutrition articles (ISSN position stands and peer-reviewed reviews, all CC BY) and one correction notice, plus 10 open-access resistance training reviews (CC BY; T9.19), split into chunks with their licence and citation data. The rules for answers drawn from those reviews (cited principles only, no workout programs) come with T9.20, which merges right after them. Food values come from USDA FoodData Central Foundation Foods (CC0). Models run through OpenRouter: `openai/gpt-5-mini` for answers, `openai/gpt-5-nano` for query translation, `qwen/qwen3-embedding-8b` for embeddings.

## Course brief coverage

| Brief item | Where |
|---|---|
| Core 1 and advanced RAG: knowledge base, chunking, embeddings, similarity search, query translation, structured retrieval | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) sections 4-5 |
| Core 2: at least 3 tools | four tools, section 6 |
| Core 3: domain, focused knowledge base, domain prompts, security | [`docs/PRD.md`](docs/PRD.md), [`docs/SOURCES.md`](docs/SOURCES.md), [`docs/SECURITY.md`](docs/SECURITY.md), `src/prompts/` |
| Core 4: LangChain with OpenRouter, error handling, input validation | sections 2, 8, 10 |
| Core 5: UI with sources, tool results and progress | section 7, [`docs/UI_DESIGN.md`](docs/UI_DESIGN.md) |
| Optional tasks | Easy 1 and 3, Medium 3, 5, 6 and 7, Hard 1 and 4 (section 15) |
| Reflection: problems and improvements | [`docs/TESTING.md`](docs/TESTING.md), "Known problems and suggested improvements (T6.1)" |

## Run locally

Requires Python 3.14 and an [OpenRouter](https://openrouter.ai/keys) API key.

```bash
python3.14 -m venv .venv      # Windows: py -3.14 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1 (PowerShell)
                              # or source .venv/Scripts/activate (Git Bash)
pip install -e ".[dev]"
```

If PowerShell says "running scripts is disabled on this system", run `Set-ExecutionPolicy -Scope Process RemoteSigned` first (for this window only), or skip activation and call the venv's programs directly (below). The `# ...` notes in the code blocks are for bash and PowerShell; leave them out in cmd.

Set the key in one of two ways (never commit it):

- copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (gitignored) and paste your key there, or
- set the `OPENROUTER_API_KEY` environment variable.

Run every command below in a terminal where `.venv` is active: the prompt starts with `(.venv)`. A new terminal does not have it: activate it again (second line above), or call the venv's programs directly:

- Windows (PowerShell or cmd): `.venv\Scripts\streamlit.exe run app.py`, `.venv\Scripts\python.exe scripts/build_index.py`
- Windows (Git Bash): `.venv/Scripts/streamlit.exe run app.py`, `.venv/Scripts/python.exe scripts/build_index.py`
- macOS and Linux: `.venv/bin/streamlit run app.py`, `.venv/bin/python scripts/build_index.py`

If a command fails with a `ModuleNotFoundError`, such as `No module named 'langchain_chroma'` from the app or `No module named 'chromadb'` or `'src'` from a script (whichever import comes first), it was started with another Python (the system one), not the venv's.

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
ruff check .              # lint
ruff format --check .     # format check
```

The app runs locally only for now; a public deployment needs one of the options in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

### Data and evaluation scripts

These are not needed to run the app:

- **Attribution:** after changing `data/sources.json` or `data/usda_foods.csv`, run `python scripts/generate_attribution.py` to regenerate [`ATTRIBUTION.md`](ATTRIBUTION.md).
- **USDA foods table:** `data/usda_foods.csv` is committed. To rebuild it, download the Foundation Foods CSV zip from https://fdc.nal.usda.gov/download-datasets/ into `data/usda/` (gitignored), then run `python scripts/prepare_usda.py` and `python scripts/generate_attribution.py`.
- **Live checks and evaluation** (need the key, and all but `scripts/live_check_llm.py` the index): `scripts/live_check_llm.py`, `scripts/live_check_retrieval.py`, `scripts/compare_retrieval.py` and `scripts/run_evaluation.py`. How to run each one and their results are in [`docs/TESTING.md`](docs/TESTING.md). `scripts/check_eval_baseline.py` (no key needed) compares an evaluation run's results file with the committed baseline.

## Documentation

| Document | Contents |
|---|---|
| [`docs/BRIEF.md`](docs/BRIEF.md) | Summary of the Sprint 2 course brief |
| [`docs/BRIEF_SPRINT3.md`](docs/BRIEF_SPRINT3.md) | Summary of the Sprint 3 course brief and of the review of Sprint 2 |
| [`docs/PRD.md`](docs/PRD.md) | What we build: features, guardrails, acceptance criteria |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technical design and decisions |
| [`docs/UI_DESIGN.md`](docs/UI_DESIGN.md) | Layout, tabs, language and themes |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Tickets, acceptance criteria, order and status |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy, evaluation results, known problems and live checks |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model and controls |
| [`docs/SOURCES.md`](docs/SOURCES.md) | Knowledge base sources and their licences |
| [`ATTRIBUTION.md`](ATTRIBUTION.md) | Credits for every source and the food data |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deployment notes and the transfer checklist |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | What each change did and why |

Numbers such as `#76` in the docs and commit messages are issues and pull requests in the repository where the work was done, https://github.com/NMH1988/nutrition-ai-assistant; a source number such as "#18a" is a row in `docs/SOURCES.md`. Issue and PR numbers in the course repository, if it has any, are unrelated.

Stack: Python, Streamlit, LangChain, OpenRouter, Chroma, rank-bm25, reportlab, USDA FoodData Central.

## Content and licences

The knowledge base uses only openly licensed material (CC BY articles and the public-domain USDA FoodData Central data). Each source keeps its own licence and is credited; see [`docs/SOURCES.md`](docs/SOURCES.md) and [`ATTRIBUTION.md`](ATTRIBUTION.md). The article texts are not committed: `scripts/download_sources.py` fetches them. No author, journal, society or USDA endorses this app. The PDF summary uses the bundled DejaVu fonts, under their own licence (`assets/fonts/LICENSE`).

## Disclaimer

This project gives general information for healthy adults. It is not medical advice and does not replace a doctor, a registered dietitian, a coach or a physiotherapist. It explains training principles from research but does not write training programs. Its answers are generated by an AI model: check them against the sources.
