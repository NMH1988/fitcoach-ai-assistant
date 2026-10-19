# Project brief (summary)

**Read this before starting any ticket** (see `CLAUDE.md`). It summarises the course brief *Sprint 2, Part 5: Building Applications with AI* (Turing College) in our own words; the course text is not copied here. The full brief is on the course platform and the owner keeps a local copy. When this summary and the full brief seem to differ, the full brief wins: ask the owner.

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

### Optional tasks

- **Easy:** conversation history and export; visualising the RAG process; source citations in answers; an interactive help or guide.
- **Medium:** multi-model support; real-time knowledge base updates; prompt injection protection; user authentication and personalisation; token usage and cost display; visualising tool call results; export to PDF/CSV/JSON; tools from a public remote MCP server; rate limiting and API key management; logging and monitoring.
- **Hard:** hybrid search; A/B testing of RAG strategies; automated knowledge base updates; multi-language support; an analytics dashboard; own tools as MCP servers; RAG evaluation (RAGAs or otherwise).

### Evaluation

- **Core concepts:** explain how RAG works and how tool calling is implemented; good code organisation; identify error scenarios and edge cases.
- **Technical:** use of the front-end library; the app works (you can chat and get answers); a relevant knowledge base; appropriate security.
- **Reflection:** understand the app's problems and suggest improvements.
- **Maximum points:** at least **2 medium and 1 hard** optional task.

Submission: through the GitHub repository the course provides, followed by a scheduled review.

## Our decisions (owner)

- **Domain:** Nutrition AI Assistant for Gym Enthusiasts.
- **Audience and scope:** healthy adults (18+) who do recreational strength training. Out of scope: minors, pregnancy, medical conditions and medication, competitive weight cuts, professional endurance sport.
- **Language:** the chatbot answers in English; all sources are in English.
- **Sources:** only the open-licensed sources in `docs/SOURCES.md`, under the copyright policy in `CLAUDE.md`.
- **Deadline:** submission on **2026-11-02**.

### Product (PRD decisions, 2026-10-19)

- **User profile:** weight, height, age, sex, activity level and goal (gain muscle, lose fat, maintain), entered in the app. It lives in the session only and is not stored (see "Personal data" in `CLAUDE.md`).
- **Tools** (core requirement 2, at least 3):
  1. `calculate_tdee`: daily energy needs from the profile (uses personal data).
  2. `calculate_macro_targets`: protein, carbohydrate and fat targets from the profile, goal and TDEE (uses personal data); enforces the calorie floor.
  3. `lookup_food_nutrition`: nutrients of a food and amount from USDA FoodData Central (no personal data).
  4. `evaluate_meal_plan` (optional, if time allows): compares a meal list with the targets (uses the targets).
- **Units:** kg and cm by default. A settings section lets the user switch to lb and ft/in; internally everything stays in kg and cm.
- **Session summary as PDF:** a download button builds a PDF of the session (profile, computed targets, key answers with their sources, disclaimer) in memory. Nothing is kept on the server. Serves optional Medium task 7 (export in PDF) and Easy task 1 (export).
- **Query translation:** multi-query (the model rewrites the question into a few variants and the results are merged). **Structured retrieval:** metadata filters on `topic`, `year` and `evidence_tier`.
- **Optional tasks for maximum points:** Medium 3 (prompt injection protection), Medium 5 (token usage and cost), Medium 6 (visualising tool results); Hard 1 (hybrid search: Chroma vectors plus keyword search). Medium 7 (PDF export) above is an extra.
- **Domain security measures** (core requirement 3), approved by the owner:
  - No dosing or use advice on steroids, SARMs or other performance-enhancing drugs.
  - A minimum calorie floor enforced in the tool code (value taken from the approved sources, not invented).
  - Refuse or redirect for minors, pregnancy, medical conditions and medication, and signs of disordered eating.
  - A visible "not medical advice" disclaimer.
  - User input and retrieved text are data, not instructions; tool arguments are validated.
- **Evaluation questions and system prompt:** drafted by the owner, reviewed by Claude (as in Sprint 1).

### Technical choices (input for `docs/ARCHITECTURE.md`)

- **UI:** Streamlit. **LLM framework:** LangChain with OpenRouter.
- **Chat models:** the Sprint 1 list, reused by choice (the Sprint 2 brief names no models): `openai/gpt-5-mini` (default), `openai/gpt-5-nano`, `openai/gpt-5`. Checked on OpenRouter's model list on 2026-10-19: all three are listed and support tool calling; none supports `temperature`.
- **Embeddings:** `qwen/qwen3-embedding-8b` through OpenRouter, as in Sprint 1 (listed on OpenRouter's embeddings model list on 2026-10-19).
- **Vector store:** Chroma.
- **Food data:** USDA FoodData Central Foundation Foods, downloaded as CSV by a script. No data.gov API key is needed for the CSV; the API is not used.
- **Repository:** the owner's personal public GitHub repo `NMH1988/nutrition-ai-assistant`. CI, PR checks and rules as in Sprint 1 (`CLAUDE.md`).

### Beyond the brief (owner's request)

- The repo is the owner's personal repository. It is shared with the course for review and is meant to be viewed by recruiters as a portfolio project; it may be opened as open source later. The brief only asks for submission through the course repository.
- Because the repo (and any demo) is public, the strict copyright policy in `CLAUDE.md` applies: open licences only (public domain, CC0, CC BY), nothing that needs permission, licence checked on the article page, text only, attribution, raw documents not committed. The owner chose to keep it strict even for a portfolio-only use, so nothing has to change if the project is opened later. The brief only asks for a relevant knowledge base.

## Not decided yet

These still need the owner's decision or confirmation; they are not requirements:
- **Submission repo:** the brief says to submit through the repository the course provides. Confirm that the course accepts this personal repo (in Sprint 1 the owner's own repo was used).
- The calorie floor value and the exact macro formulas (to be taken from the approved sources when the tools ticket starts).
- The PDF library and the architecture details (`docs/ARCHITECTURE.md`).
- Deployment: the app runs locally for the review; a public demo comes later (`docs/DEPLOYMENT.md`).
- The repo's own code licence (e.g. MIT). Without one, others may view the code but not reuse it.
