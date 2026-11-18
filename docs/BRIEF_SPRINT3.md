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

What makes a system an agent rather than a pipeline (a ReAct loop that picks its next step from what its tools return), and the kinds of agent from the simplest to the most complex, in the course's order: simple reflex, model-based reflex, goal-based, learning, utility-based, multi-agent. LangChain's `create_agent`, and LangGraph underneath it: a `StateGraph` with a `TypedDict` state, nodes, fixed and conditional edges, reducers (`add_messages`), `MessagesState`, input, output and private state schemas, a tool-calling agent built by hand (`bind_tools`, `ToolNode`, `tools_condition`), short-term memory with a checkpointer (`InMemorySaver`, `SqliteSaver`) and a `thread_id`, trimming what the model sees (`trim_messages`) against what is stored (`RemoveMessage`); long-term memory as a SQLite table of facts per user with a "remember" tool (or a LangGraph store with embeddings); human-in-the-loop that pauses before a tool call so a human approves, edits or rejects it (`HumanInTheLoopMiddleware`, `interrupt()`); the LangSmith suite for tracing and evaluation.

## Already done in Sprint 2 that Sprint 3 counts

Medium 1 (token usage and cost, T5.1) and Medium 8 (the input guard, domain guardrails and prompt injection hardening, T1.3, T3.4, T5.3, T7.4; models and prompts live in config and files, never on the user's screen). Four tools exist (`calculate_tdee`, `calculate_macro_targets`, `lookup_food_nutrition`, `evaluate_meal_plan`).

## The Sprint 2 review: areas for improvement

The reviewer's five points, each with the ticket that answers it:

1. **No application logging or request tracing.** Nothing in `src/` or `app.py` logs; `LLMError.diagnostic` is built to be safe to log but is never written; guard rejections, rate limits and tool failures leave no trace. Suggested: one structured record per turn with a turn ID and no user text or personal data; diagnostics and guard reasons at warning; a test that no record holds profile values. **T8.2** (local JSON logs) and **T9.8** (LangSmith, masked).
2. **`app.py` is about 1,380 lines** with about 80 functions (profile form, caching, chart specs, four tabs, usage tables, source cards, the PDF download), against the project's own layering. Suggested: a `views/` package by concern, `app.py` left as composition and routing. **T8.1**.
3. **Tool-only questions still get six unrelated research passages** (q14 and de4: six chunks at 0.53-0.58 reached the answer model). Suggested: drop the sources when the plan needs a tool and the nearest chunk is far. **T9.3** (agentic RAG: the agent decides whether to search at all).
4. **One article can fill all six retrieved places** (q2, q3, q10), so expected second sources (#12 for q5, #8 for q10) never reach the top six. Suggested: a per-source cap in the fused list, or MMR. **T8.3**.
5. **Evaluation is manual** and not part of the development loop: both scripts need the key and the index, results are pasted into `docs/TESTING.md` by hand, and CI runs no evaluation. Suggested: machine-readable results, a committed baseline, a manually dispatched workflow that fails below it, and an offline retrieval suite in ordinary CI. **T8.4**, **T8.5**, **T8.6**; the Ragas or DeepEval report is **T9.10**.

## Reviewer comments during Sprint 3

Comments the owner received on the Sprint 3 project before its deadline, in our words (the owner keeps the original), each with the ticket that answers it:

1. **LangSmith is little used** (2026-11-12): the project traces to LangSmith (T9.8), but every trace is masked, so LangSmith shows only the shape of a turn, and the evaluation never reaches it. **T9.33** (the evaluation as LangSmith experiments, and the evaluation lifecycle documented in `docs/TESTING.md`); **T9.35** (unmasked traces of the app's own runs in demo mode only, so a reviewer can read what a trace holds).
2. **A gymer chooses every food alone** (2026-11-12): letting the gymer choose every food is weak; the coach should recommend foods to the gymer. **T9.34** (foods the coach suggests, logged by the client in one click; beyond the brief, owner's request), after a comparison of similar coaching apps the same day; a coach-built meal plan stays a Capstone idea (`docs/PRD.md`, "Moved to the Capstone").

## The Sprint 3 review: areas for improvement

The reviewer's five points from the Sprint 3 review (received by the owner on 2026-11-18), in our words (the owner keeps the original), each with the ticket that answers it (Epic 10 in `docs/IMPLEMENTATION_PLAN.md`):

1. **Injection detection is a pattern list.** `guard.looks_like_injection()` matches known phrasings, so a paraphrase passes; and since an answer is kept in the chat's memory, an instruction the model once repeated is read again in later turns (`docs/TESTING.md`, Sprint 3 known problem 5). Suggested: keep the patterns as a cheap first filter; check an answer before the thread keeps it; an offline red-team fixture that records the miss rate; a small classifier on retrieved or remembered text weighed against its cost. **T10.1**.
2. **The weekly review's safety checks read numbers out of free text** in English and German (`config.REVIEW_*_PATTERNS`), so a kcal change ("a 300 kcal deficit") is not checked against the floor (known problem 8). Suggested: numeric fields on `Recommendation` (a target and a change in kcal), checked with plain arithmetic in `validate()`, the patterns kept as a fallback for prose. **T10.2**.
3. **Prompt management.** (a) The query translation prompt repeats the JSON schema that `with_structured_output` already sends; (b) it still describes `needs_tool`, `needs_profile` and a `<profile>` block the app dropped in T9.3; (c) the structured output models carry constraints but no field descriptions, so a field's meaning lives only in prompt prose; (d) prompts have no version, so a stored review, a trace or a log line cannot say which prompt produced it. Suggested: the owner removes the duplicate and the dead sections, the two fields are dropped, field descriptions move into the models, and a content hash of each prompt goes into traces, logs and stored reviews. **T10.3** (a-c), **T10.4** (d).
4. **Maintainability.** `src/i18n.py`, `src/config.py` and `src/chat.py` are very large and mix concerns; `chat.run_turn()` takes 19 parameters (17 of them keyword-only); comments record ticket history rather than intent. Suggested: a `TurnDeps` dataclass for the turn's dependencies, `config` and `i18n` split by concern, and comments that explain the code as it is now, the history kept in `docs/progress/`. **T10.7**, **T10.8**, **T10.9**.
5. **Every tool is offered on every turn** (known problem 3), so a training question can call an energy or meal plan tool, the "no program" rule rests on the prompt alone, and each tool schema and the long system prompt are sent on every one of up to five answer calls. Suggested: offer the tools by the question's domain, reuse the review's program check on the chat's answer, and show per turn how much of the input the provider's prompt cache served, with the system prompt kept byte-identical within a turn. **T10.5**, **T10.6**.

## Using this file

- At the start of every ticket, name the Sprint 3 requirement, optional task or evaluation item (by the numbers above) or the review point it serves, or "none", together with the Sprint 2 item from `docs/BRIEF.md`; write "beyond the brief (owner's request)" only when neither brief covers the work. The PR description's Brief section, the plan's **Serves** line and the PROGRESS **Brief:** line carry the same numbers.
- If a ticket contradicts this brief, `docs/BRIEF.md`, the PRD or the copyright policy, or changes what the product does, say so and ask the owner.
