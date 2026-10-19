# Nutrition AI Assistant for Gym Enthusiasts

A chatbot that answers nutrition questions for adults who do recreational strength training. It combines retrieval-augmented generation over open-licensed sports nutrition research with tools for personal calculations (energy needs, macro targets) and food lookups.

**Status:** planning. No code yet. Built as the Sprint 2 project of the Turing College AI Engineering course, deadline 2026-11-02.

- Project brief and decisions: [`docs/BRIEF.md`](docs/BRIEF.md)
- Knowledge base sources and their licences: [`docs/SOURCES.md`](docs/SOURCES.md)
- Deployment notes: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Progress log: [`docs/PROGRESS.md`](docs/PROGRESS.md)

Planned stack: Python, Streamlit, LangChain, OpenRouter, Chroma, USDA FoodData Central.

## Content and licences

The knowledge base uses only openly licensed material (CC BY articles and the public-domain USDA FoodData Central data). Each source keeps its own licence and is credited; see [`docs/SOURCES.md`](docs/SOURCES.md).

## Disclaimer

This project gives general information for healthy adults. It is not medical advice and does not replace a doctor or a registered dietitian.
