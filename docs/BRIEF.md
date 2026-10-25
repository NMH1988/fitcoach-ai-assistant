# Project brief (summary)

**Read this before starting any ticket** (see `CLAUDE.md`). It summarises the course brief *Sprint 2, Part 5: Building Applications with AI* (Turing College) in our own words; the course text is not copied here. The full brief is on the course platform and the owner keeps a local copy. When this summary and the full brief seem to differ, the full brief wins: ask the owner.

This file says **what the course asks for**. What we decided to build is in `docs/PRD.md`.

## What the brief asks for

Build a specialised chatbot for one domain that uses advanced RAG and tool calling, and that would be useful in a real setting. Frameworks: LangChain, with Streamlit or Next.js for the UI. Estimated effort: 20-25 hours.

The chatbot must:
1. Use advanced RAG with **query translation** and **structured retrieval**.
2. Use **tool calling** for practical tasks.
3. Focus on **one specific domain or use case**.
4. Give detailed, context-aware answers.

### Core requirements

1. **RAG:** a knowledge base relevant to the domain; standard retrieval with embeddings; chunking and similarity search.
2. **Tool calling:** at least **3 different tools**, relevant to the domain (e.g. calculations, data analysis, API integrations).
3. **Domain specialisation:** a chosen domain, a focused knowledge base, domain-specific prompts and responses, and **security measures relevant to the domain**.
4. **Technical:** LangChain with OpenRouter (OpenAI-compatible SDK); proper error handling; user input validation.
5. **UI:** an intuitive Streamlit or Next.js interface that shows the relevant context and sources, shows tool call results, and has progress indicators for long operations.

The brief sets **no minimum number of documents** for the knowledge base; it asks for a relevant, focused one.

### Optional tasks (numbering as in the brief, so tickets can cite them)

- **Easy:** 1 conversation history and export; 2 visualising the RAG process; 3 source citations in answers; 4 an interactive help or guide.
- **Medium:** 1 multi-model support; 2 real-time knowledge base updates; 3 prompt injection protection; 4 user authentication and personalisation; 5 token usage and cost display; 6 visualising tool call results; 7 export to PDF/CSV/JSON; 8 tools from a public remote MCP server; 9 rate limiting and API key management; 10 logging and monitoring.
- **Hard:** 1 hybrid search; 2 A/B testing of RAG strategies; 3 automated knowledge base updates; 4 multi-language support; 5 an analytics dashboard; 6 own tools as MCP servers; 7 RAG evaluation (RAGAs or otherwise).

### Evaluation

- **Core concepts:** explain how RAG works and how tool calling is implemented; good code organisation; identify error scenarios and edge cases.
- **Technical:** use of the front-end library; the app works (you can chat and get answers); a relevant knowledge base; appropriate security.
- **Reflection:** understand the app's problems and suggest improvements.
- **Maximum points:** at least **2 medium and 1 hard** optional task.

### Submission

Through the GitHub repository the course provides, followed by a scheduled review. **Our approach:** the work is done in the owner's personal repo `NMH1988/nutrition-ai-assistant`; when it is finished, the repo (files and commit history) is copied into the course repository, where the reviewers read it. Issues, pull requests and their comments do not travel with the copy, so everything a reviewer needs must be in files (see the transfer checklist in `docs/DEPLOYMENT.md`).

## Using this file

- At the start of every ticket, name the requirement, optional task or evaluation item (by the numbers above) the ticket serves, or "none", together with the Sprint 3 item from `docs/BRIEF_SPRINT3.md`; write "beyond the brief (owner's request)" only when neither brief covers the work. The PR description's Brief section, the plan's **Serves** line and the PROGRESS **Brief:** line carry the same numbers.
- When the exact wording matters, or this summary is unclear, read the full brief (ask the owner for it if it is not at hand). Don't guess from the summary.
- If a ticket, `docs/PRD.md`, the plan or the prompts **contradict** the brief, or a choice changes what the product does, say so and ask the owner.
