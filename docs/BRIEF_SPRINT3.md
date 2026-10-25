# Sprint 3 brief (summary) and the Sprint 2 review

**Read this before starting any ticket**, together with `docs/BRIEF.md` (Sprint 2) (owner's rule, 2026-10-25: both briefs for every ticket). It summarises the course brief *Sprint 3: build an AI agent of your own choosing* (Turing College) and the reviewer's feedback on the Sprint 2 project, in our own words; the course text is not copied here. The owner keeps the full brief and the review. When this summary and the full brief seem to differ, the full brief wins: ask the owner.

The course allows the Sprint 3 project to build on the Sprint 2 project (owner, 2026-10-23), so the nutrition assistant becomes the agent. What we decided to build is in `docs/PRD.md` ("Sprint 3: the agent (coach-first workspace)", added by T9.1).

## What the Sprint 3 brief asks for

Build an app with an AI agent on the backend that solves a real problem for real users. Topics: AI agents, LangChain and LangGraph, short- and long-term memory, prompt engineering, the OpenAI API (we use OpenRouter's OpenAI-compatible API, as in Sprint 2), with Streamlit or Next.js for the UI. Estimated effort: 18 hours.

### Core requirements

1. **Agent purpose:** a clear purpose, why the agent is useful, and who the target users are.
2. **Core functionality:** the main features that make the agent useful, its primary tasks done well, and the user interactions they need.
3. **User interface:** a user-friendly, intuitive interface for every function.
4. **Technical implementation:** suitable tools and libraries, proper error handling, and an agent that copes with real-world use.
5. **Documentation:** how to use the agent, examples of common use cases, and the technical decisions made.

### Optional tasks (numbering ours, so tickets can cite them)

- **Easy:** 1 have an LLM critique the solution for usability, security and prompt engineering; 2 an agent personality (formal, friendly, concise); 3 a choice of LLMs; 4 model settings (temperature, max tokens) as user controls; 5 an interactive help or guide.
- **Medium:** 1 token usage and cost display; 2 long- or short-term memory in LangChain/LangGraph; 3 one more tool that calls an external API; 4 user authentication and personalisation; 5 a feedback loop where users rate answers and the ratings improve the agent; 6 two extra tools (five in total) with a UI to switch tools on and off, or a plugin system; 7 multi-model support; 8 at least one security guard against misuse, with developer settings (model, system prompt) kept apart from the user's screen.
- **Hard:** 1 agentic RAG; 2 an LLM observability tool (LangSmith, Langfuse or similar); 3 an evaluation report with Ragas or DeepEval that shows the app's quality; 4 an agent that learns from user feedback and adjusts its behaviour; 5 an agent that enriches its knowledge from external data sources (APIs or websites).

### Evaluation

- **Problem definition:** a well-defined problem, and how the app addresses it.
- **Core concepts:** how agents work; the differences between agent types; how function calling is implemented; good code organisation; error scenarios and edge cases.
- **Technical:** use of the front-end library; a relevant knowledge base where it applies; appropriate security.
- **Reflection:** the app's problems; suggestions for improving the code and the project; when to use prompt engineering, RAG or an agent.
- **Maximum points:** at least **2 medium and 1 hard** optional task.

### What the course taught (so the design follows it)

LangChain's `create_agent`, and LangGraph underneath it: a `StateGraph` with a `TypedDict` state, nodes, fixed and conditional edges, reducers (`add_messages`), `MessagesState`, input, output and private state schemas, a tool-calling agent built by hand (`bind_tools`, `ToolNode`, `tools_condition`), short-term memory with a checkpointer (`InMemorySaver`, `SqliteSaver`) and a `thread_id`, trimming what the model sees (`trim_messages`) against what is stored (`RemoveMessage`); long-term memory as a SQLite table of facts per user with a "remember" tool (or a LangGraph store with embeddings); human-in-the-loop that pauses before a tool call so a human approves, edits or rejects it (`HumanInTheLoopMiddleware`, `interrupt()`); the LangSmith suite for tracing and evaluation.

## Already done in Sprint 2 that Sprint 3 counts

Medium 1 (token usage and cost, T5.1) and Medium 8 (the input guard, domain guardrails and prompt injection hardening, T1.3, T3.4, T5.3, T7.4; models and prompts live in config and files, never on the user's screen). Four tools exist (`calculate_tdee`, `calculate_macro_targets`, `lookup_food_nutrition`, `evaluate_meal_plan`).

## The Sprint 2 review: areas for improvement

The reviewer's five points, each with the ticket that answers it:

1. **No application logging or request tracing.** Nothing in `src/` or `app.py` logs; `LLMError.diagnostic` is built to be safe to log but is never written; guard rejections, rate limits and tool failures leave no trace. Suggested: one structured record per turn with a turn ID and no user text or personal data; diagnostics and guard reasons at warning; a test that no record holds profile values. **T8.2** (local JSON logs) and **T9.8** (LangSmith, masked).
2. **`app.py` is about 1,380 lines** with about 80 functions (profile form, caching, chart specs, four tabs, usage tables, source cards, the PDF download), against the project's own layering. Suggested: a `views/` package by concern, `app.py` left as composition and routing. **T8.1**.
3. **Tool-only questions still get six unrelated research passages** (q14 and de4: six chunks at 0.53-0.58 reached the answer model). Suggested: drop the sources when the plan needs a tool and the nearest chunk is far. **T9.3** (agentic RAG: the agent decides whether to search at all).
4. **One article can fill all six retrieved places** (q2, q3, q10), so expected second sources (#12 for q5, #8 for q10) never reach the top six. Suggested: a per-source cap in the fused list, or MMR. **T8.3**.
5. **Evaluation is manual** and not part of the development loop: both scripts need the key and the index, results are pasted into `docs/TESTING.md` by hand, and CI runs no evaluation. Suggested: machine-readable results, a committed baseline, a manually dispatched workflow that fails below it, and an offline retrieval suite in ordinary CI. **T8.4**, **T8.5**, **T8.6**; the Ragas or DeepEval report is **T9.10**.

## Using this file

- At the start of every ticket, name the Sprint 3 requirement, optional task or evaluation item (by the numbers above) or the review point it serves, or "none", together with the Sprint 2 item from `docs/BRIEF.md`; write "beyond the brief (owner's request)" only when neither brief covers the work. The PR description's Brief section, the plan's **Serves** line and the PROGRESS **Brief:** line carry the same numbers.
- If a ticket contradicts this brief, `docs/BRIEF.md`, the PRD or the copyright policy, or changes what the product does, say so and ask the owner.
