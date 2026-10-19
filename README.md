# Nutrition AI Assistant for Gym Enthusiasts

A chatbot that answers nutrition questions for adults who do recreational strength training. It combines retrieval-augmented generation over open-licensed sports nutrition research with tools for personal calculations (energy needs, macro targets) and food lookups.

**Status:** planning. No code yet. Built as the Sprint 2 project of the Turing College AI Engineering course, deadline 2026-11-02.

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

Planned stack: Python, Streamlit, LangChain, OpenRouter, Chroma, USDA FoodData Central.

## Content and licences

The knowledge base uses only openly licensed material (CC BY articles and the public-domain USDA FoodData Central data). Each source keeps its own licence and is credited; see [`docs/SOURCES.md`](docs/SOURCES.md).

## Disclaimer

This project gives general information for healthy adults. It is not medical advice and does not replace a doctor or a registered dietitian.
