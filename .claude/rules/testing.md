---
paths:
  - "tests/**"
---

# Testing rules

Full strategy: `docs/TESTING.md`.

- **Unit tests** for pure logic: calculators, unit conversion, input guard, chunking, metadata filters, RRF, citation formatting, PDF content.
- **Integration tests** with fakes: ingest -> Chroma (in-memory or a temp dir) -> retrieval -> answer, with `DeterministicFakeEmbedding`; the tool-calling loop with a scripted fake chat model.
- **UI tests** with `streamlit.testing.v1.AppTest` for visible UI changes. This is our end-to-end level; browser E2E is not planned.
- **All LLM, embedding and network calls are mocked.** The suite and CI run with no API key; test keys are obvious fakes like `sk-test-not-a-real-key`. Tests that touch the key remove the env var first.
- Every acceptance criterion of the ticket maps to a test, or to a named manual check recorded in the PR.
- Guard tests are parametrised with attack strings and benign strings (no false positives).
- Test data uses only approved sources or text we wrote ourselves (`.claude/rules/copyright.md`).
- Every test function, fixture and helper has a one-line docstring.
