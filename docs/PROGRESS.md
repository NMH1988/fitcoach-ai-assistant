# Progress log

What each PR did and why, newest first. **Read this before starting a ticket**, together with the open PRs (`gh pr list --state open`), so earlier decisions and loose ends are not lost.

**Adding an entry:** every PR (Dependabot exempt) adds one entry at the top of the log below, in the same PR, so the log reaches `main` together with the work. Keep it short and record what the code does not say. Parallel PRs all add at the top, so they conflict here: keep both entries. `.gitattributes` sets `merge=union` for this file, which handles local merges; GitHub's web conflict editor ignores it.

```
## YYYY-MM-DD · T<x.y> <title> · #<PR> (closes #<issue>)
- **Brief:** the requirement or optional task served, or "beyond the brief (owner's request)".
- **What:** files/behaviour changed.
- **Why:** reason for the approach chosen.
- **Decisions & gotchas:** anything a future session must know.
- **Follow-ups:** what is left, with ticket numbers.
```

---

## 2026-10-19 · T1.3 Input guard and rate limit · #25 (closes #3)
- **Brief:** core requirement 4 (user input validation), Medium 3 (prompt injection protection); AC-11.
- **What:**
  - First commit: the plan reorder the owner approved on 2026-10-19 ("core first, then extras"). `docs/IMPLEMENTATION_PLAN.md` "Overview and order" now lists the core tickets (through T6.1), then the extras T5.1, T5.2, T4.5, then T6.2 last, with adjusted target dates, critical-path note and cut order; `docs/PRD.md` names Medium 3, 6 and Hard 1 as the optional tasks for maximum points and Medium 5 and 7 as extras; `docs/ARCHITECTURE.md` section 14 cut order matches. T1.2 marked done (PR #24 merged).
  - `src/guard.py` (new): `clean_input()` (NFKC; other line and paragraph separators turned into line breaks; curly apostrophes into "'"; control characters, the other "C" categories and the invisible marks outside them (combining grapheme joiner, Hangul fillers, variation selectors) dropped, except line breaks and tabs; trimmed); `looks_like_injection()` (regexes on the casefolded, whitespace-collapsed text for instruction overrides, requests for the hidden prompt, role changes and jailbreak phrases; and on the cleaned text for fake role markers and look-alikes of `<user_input>`/`<sources>`); `check_message()` (empty, too long, injection, then the rate limit); `RateLimiter` (rolling window plus a session total, injectable clock); `session_limiter(state)` (one limiter per `st.session_state`); `run_guarded(text, limiter, call)` (calls the rest of the turn only for accepted text). Each rejection has a fixed message that never quotes the input; the injection message asks the user to rephrase if it was a nutrition question.
  - `src/config.py`: the rate-limit comment now says it counts questions, not model requests.
  - Tests: `tests/test_guard.py` (43 attack strings and 36 benign nutrition questions, all written for this project; empty, whitespace, invisible-only and over-length input; the length counted after cleaning; the rolling window and the session cap with a fake clock; rejected input not using the quota; a spy OpenRouter server behind the real chat and embedding clients, which sees no request for any rejected input and both requests for an accepted one). 224 tests pass.
  - Docs: `docs/ARCHITECTURE.md` section 2 step 2; `docs/SECURITY.md` known limits.
- **Why:** the guard is pure Python with no Streamlit import, so it is unit-testable and T3.1 only has to store the limiter in session state and call `run_guarded()`. Putting the rate limit last means only questions that would reach a model use the quota. `run_guarded()` puts the "no call on rejection" guarantee in `src/`, so the test checks the code, not a copy of the wiring.
- **Decisions & gotchas:**
  - Owner's choices: the rate limit counts accepted questions (one per turn, however many model calls the turn makes), and rejected messages do not count.
  - False positives were the main risk: "ignore", "rules", "guidelines", "system", "role", "act as", "prompt" and "instructions" all appear in real nutrition questions. "Rules"/"guidelines" only count as an attack with a qualifier pointing at the assistant ("your", "previous", "above"...); "the"/"any" are not enough for "instructions" either ("can I skip the loading instructions on the creatine tub?" passes). `skip` is not an override verb. "DAN" only counts as "DAN mode", since Dan is a name.
  - The session-limit message does not mention reloading the page, although a reload starts a new quota (`docs/SECURITY.md`).
  - Regex cost checked by hand on 2,000-character adversarial inputs (repeated "ignore your ", "you are now ", "<", "<" plus spaces or line breaks): under 3 ms each after the review fix (the first version took up to about 200 ms on the delimiter patterns, which had two `\s*` next to each other). The length check runs before the patterns; cleaning still runs on the raw text, so T3.1 caps the chat input size.
  - Not wired into the UI: the app has no chat input yet; T3.1 does it.
  - Code review (round 1, before the PR): the first patterns rejected common questions about coaches, labels and guidelines ("the original instructions on the creatine tub", "ignore the previous dietary guidelines", "if you are now cutting"). The words between the verb and the noun now come from a short list; "your", "above", "system" and "developer" always count, while "previous", "prior", "all", "these" and the like only count when no third party follows the noun ("from my coach", "my dietitian gave me", "on the tub"). "You are now" and "from now on" need a role change or an override after them. Classic attacks added ("ignore the above directions", "you're now DAN", "forget what you were told"), with curly apostrophes, invisible marks and other line separators handled in cleaning. The delimiter patterns made linear. The limiter rejects non-positive limits. The injection message no longer accuses the user.
- **Follow-ups:** T3.1 stores `session_limiter(st.session_state)` and wraps the turn in `run_guarded()`, showing `GuardResult.message` for a rejection, and sets `st.chat_input(max_chars=config.MAX_INPUT_CHARS)` so cleaning never sees huge input; T3.4 adds the delimiting and the system-prompt rule (the second line of defence); T5.3 handles domain refusals (drug dosing, minors and so on), which this guard does not.

## 2026-10-19 · T1.2 OpenRouter clients and error mapping · #24 (closes #2)
- **Brief:** core requirement 4 (LangChain with OpenRouter; error handling).
- **What:**
  - `src/llm.py` (new): `build_chat_model()` (`ChatOpenAI` on OpenRouter's base URL, allowlisted model only, `max_tokens` clamped to `MAX_TOKENS_CAP`, reasoning effort, timeout, retries, Chat Completions forced) and `build_embeddings()` (`OpenAIEmbeddings`, `qwen/qwen3-embedding-8b`, `check_embedding_ctx_length=False`). Both take the key from `get_api_key()` unless one is passed, and an optional `http_client` that the tests use for a mocked transport.
  - Error mapping: `LLMError` and one subclass each for 401, 402, 429, timeout (ours or a 408), 5xx, an unreachable service, a structured reply cut off by the token limit (`ReplyCutOffError`) and an unusable structured reply (`InvalidReplyError`: schema mismatch, refusal or empty), plus a generic one; each has a fixed message. A 200 reply that carries an error, no result, or an empty or cut-off body (the provider failed mid-request) counts as "unavailable". Callers wrap a call in `with mapped_errors():`.
  - `src/config.py`: `REASONING_EFFORT = "low"`, `LLM_TIMEOUT_SECONDS = 60`, `LLM_MAX_RETRIES = 2` (owner's choice).
  - `scripts/live_check_llm.py` (new): the owner's live check O5, one real chat and one real embedding call.
  - `pyproject.toml`: `openai==3.35.1` pinned (used directly; its retry policy is what the tests check) and `httpx2==2.14.0` in the dev extra (the tests' mock transport); both listed in `docs/ARCHITECTURE.md` section 12.
  - Tests: `tests/test_llm.py` (settings, what goes on the wire, each status and timeout mapped, retry counts, malformed and unreadable 200 replies, a reply cut off by the token limit, a structured reply that breaks its schema, is refused or is empty, SDK errors outside `APIError`, diagnostics, a server that echoes the key), `tests/test_live_check_llm.py` (the script with fake clients). 112 tests pass.
  - Rules and docs: `.claude/rules/security-privacy.md` (model clients section); `docs/ARCHITECTURE.md` sections 3, 10, 12 and 14; `docs/SECURITY.md` key and cost rows; `docs/TESTING.md` how to run the live check; T1.1 marked done in the plan (PR #21 had merged).
- **Why:** retries are left to the OpenAI SDK (it already retries 408, 409, 429, 5xx and timeouts with back-off and does not retry 401/402 unless the server sends `x-should-retry: true`), so we only set the bound. Errors are mapped by the SDK's base classes, which covers both chat (langchain re-wraps them as subclasses) and embeddings (raw SDK errors). Fixed messages, raised `from None`, mean nothing from the server's reply can reach the user or a traceback.
- **Decisions & gotchas:**
  - The SDK (openai 3.35) uses `httpx2`, not `httpx`; mocks must be `httpx2.MockTransport` (BSD-3-Clause, pulled in by openai). Tests patch the SDK's `time.sleep` so retries run instantly.
  - `use_responses_api=False` is set on purpose: langchain picks the Responses API for some model names, and OpenRouter is used through Chat Completions.
  - `ChatOpenAI` sends `max_tokens` as `max_completion_tokens`; no `temperature` is sent (gpt-5).
  - 401 and 402 now have separate messages (the ticket's criterion), so `docs/ARCHITECTURE.md` section 10 was updated.
  - Malformed replies: langchain raises `ValueError`/`KeyError`/`TypeError` for them, so `mapped_errors()` maps those types only when a frame of the traceback is in `openai` or `langchain_openai`; the same errors from the caller's code pass through unchanged.
  - Accepted risk: the SDK honours a server's `Retry-After` up to 2 minutes per retry, so one call can wait about 7 minutes at worst, and requests abandoned after our timeout may still be billed. Lower `LLM_MAX_RETRIES` or the timeout if that matters in practice.
  - `mapped_errors()` uses `from None`: the original error is hidden from tracebacks but is still on `__context__`, and its request holds the key (a test shows it). Never log or show it; written into `docs/SECURITY.md`.
  - The live check also fails if the reply used more tokens than `max_tokens`.
  - Live check O5 run by the owner on 2026-10-19: both calls succeeded (chat 16 in / 86 out tokens, 94 reasoning reported; embedding 4096 dimensions), recorded in `docs/TESTING.md`. Reasoning tokens reported above output tokens: T5.1 must check how OpenRouter counts and bills them. The reply stayed far under the cap, so the cap being enforced is not shown, only accepted.
  - Code review (round 1, before the PR): 408 mapped to the timeout error, malformed replies mapped, `openai` and `httpx2` pinned, the `__context__` caveat and the real worst-case wait documented.
  - Code review on PR #24: `mapped_errors()` now catches every `openai.OpenAIError`, not only `APIError` (structured output stopped by the token limit gets its own `ReplyCutOffError`, which T3.2's gpt-5-nano call can hit; a content filter gets the generic error). Malformed replies are mapped when any frame of the traceback is in `openai`/`langchain_openai`, which also covers an empty or cut-off JSON body (raised from `json`). Every `LLMError` has a `diagnostic` (error type and raising function, no message) that is safe to log, so a bug of ours raised inside langchain stays traceable. The 60 s timeout is per phase, not per request (noted in `docs/ARCHITECTURE.md` section 14). New rule in `.claude/rules/security-privacy.md` (owner's decision): never pass `model`, `max_tokens` and the like at call time, as that bypasses the allowlist and the cap.
  - Code review on PR #24, round 2: scanning the whole traceback also caught Pydantic's `ValidationError` (a `ValueError`) from a structured reply that breaks its schema, which then looked like an outage. It now gets its own `InvalidReplyError`, so T3.2 can tell "bad answer" from "provider down". The rule also forbids changing a built client (field assignment, `model_copy`, `configurable_fields`); ARCHITECTURE section 10 no longer claims the bypass is impossible, only that the rule prevents it.
  - Code review on PR #24, round 3: two more unusable structured replies on the default path now give `InvalidReplyError` too: a refusal (langchain's `OpenAIRefusalError`, a plain `Exception` that escaped the mapping and every `except LLMError`) and an empty or null reply (a `ValueError` from langchain's structured-output parser, which looked like an outage).
  - Code review on PR #24, round 4: ready to merge; only docs nits (the dict-schema note above corrected, a test docstring), no code changes.
- **Follow-ups:** T3.2 decides what to do on `InvalidReplyError` and `ReplyCutOffError` from the query translation call: fall back silently to the original question with no filter (as its criterion says for invalid output) rather than show the error, since retrying with the same token budget may hit the same limit. `InvalidReplyError` covers the default `with_structured_output` method (the SDK's `parse`); with `method="function_calling"` langchain's own parser raises Pydantic's `ValidationError` after the client returns, so it passes through unmapped and its message quotes the reply (checked with a mocked reply on 2026-10-19): T3.2 should use the default method or handle that error itself, and pass a Pydantic class rather than a JSON-schema dict: with a dict, non-JSON content raises langchain-core's `OutputParserException` after the client returns, so it passes through unmapped with the reply in its message (checked with a mocked reply on 2026-10-19). T5.1 checks how reasoning tokens are counted in the cost; T3.1 shows the mapped messages and the missing-key message in the UI (the 401 message points to the local secrets file; revisit if "bring your own key" is built); T2.3 uses `build_embeddings()`.

## 2026-10-19 · T1.1 Project skeleton, config and CI · #21 (closes #1)
- **Brief:** core requirement 4 (technical base); CI as in Sprint 1.
- **What:**
  - `pyproject.toml`: the runtime packages pinned as in `docs/ARCHITECTURE.md` section 12; the dev tools pinned too (pip-audit 2.10.1, pytest 9.1.1, pytest-cov 7.1.0, ruff 0.17.1) so a new tool release cannot break CI on an unrelated PR; ruff and pytest settings as in Sprint 1. `.python-version` 3.14.
  - `src/config.py`: app title, intro and disclaimer; OpenRouter base URL; allowed models with `gpt-5-mini` for answers and `gpt-5-nano` for query translation; embedding model; token budget and cap; input length and rate limits; `get_api_key()` reused from Sprint 1 (secrets first, then the env var; never shows the key; its own error for a broken secrets file).
  - `app.py`: title, intro and the disclaimer only.
  - Tests: `tests/test_config.py` (models, limits, the Sprint 1 key tests with fake `sk-test-` keys, the missing-key message holds no key), `tests/test_app_smoke.py` (AppTest with no key: no exception, the title, the disclaimer).
  - `.github/workflows/ci.yml` (lint, tests with coverage, pip-audit) and `.github/dependabot.yml`, as in Sprint 1. `CLAUDE.md` lists the real commands.
  - `README.md`: status "in development" and a "Run locally" section (Python 3.14, install, key setup, run, test and lint commands).
- **Why:** the smallest base every later ticket builds on, with CI from the first PR.
- **Decisions & gotchas:**
  - `pip-audit` found four advisories in chromadb 1.5.9 (the latest; no fix yet), all in Chroma's HTTP server. The owner chose to keep Chroma: CI ignores exactly those four IDs with the reason next to them, `docs/SECURITY.md` lists them as accepted risks, and `.claude/rules/security-privacy.md` forbids running Chroma as a server or using its embedding functions. Dependabot will propose a fixed release; then remove the ignores.
  - The app does not read the key yet; the missing-key message in the UI comes with the first model call (T3.1).
  - Limits for retrieval, tools and the calorie floor are added by the tickets that use them, not here.
  - Checked locally on Python 3.14.8: ruff clean, 26 tests pass (coverage 99%), pip-audit clean with the four ignores.
  - Code review (round 1, before the PR): pip-audit added to the dev extra and the dev tools pinned; the unused `packaging` dev dependency dropped; config notes that the limits come from Sprint 1 and the reasoning effort from T1.2. `actions/checkout@v4` and `setup-python@v5` are left for Dependabot.
  - Code review on PR #21 (rounds 1-2, approved): README run steps added; dev tool versions and licences recorded in `docs/ARCHITECTURE.md` section 12; `docs/SECURITY.md` says `pip-audit .` audits only the runtime dependencies (it reads `[project].dependencies`, not the dev extra); the pip-audit pin in `ci.yml` must be bumped by hand, as Dependabot does not update `run:` lines.
- **Follow-ups:** T1.2 (#2) builds the OpenRouter clients on this config.

## 2026-10-19 · Implementation plan and GitHub issues · direct commit (no ticket, before the setup ticket)
- **Brief:** plans the work for every core requirement and the chosen optional tasks (Medium 3, 5, 6, 7; Hard 1).
- **What:** `docs/IMPLEMENTATION_PLAN.md`: 6 epics, 19 tickets plus the stretch T4.5, each with testable acceptance criteria mapped to tests or checks; owner tasks O1-O6; order, target dates, critical path and cut order. GitHub issues #1-#20 created, one per ticket (T1.1 = #1 ... T6.2 = #20), and their numbers filled into the plan.
- **Why:** phase 4 of the owner's six-phase process; the owner approved the plan on 2026-10-19.
- **Decisions & gotchas:** issue bodies copy the ticket text from the plan; if a ticket changes, update both. Owner tasks are tracked in the plan only, not as issues.
- **Follow-ups:** T1.1 (#1) starts next on its own branch.

## 2026-10-19 · Legal check of sources and access terms · direct commit (no ticket, before the setup ticket)
- **Brief:** beyond the brief (owner's request): the copyright policy.
- **What:** `.claude/rules/copyright.md`: attribution now keeps the article's copyright and licence notices and implies no endorsement; new rule 7 (do not distort sources; leave out third-party content inside articles); new rule 10 (access terms: automated downloads only through the Europe PMC REST API or PMC's OAI-PMH/FTP/Cloud services; reading, saving or copying a single CC BY article by hand is allowed). `docs/SOURCES.md`: how the licences were checked, the access terms of PMC, Europe PMC and Taylor & Francis, and a summary of the CC BY 4.0 and 2.0 legal codes. `docs/ARCHITECTURE.md`: the download script uses only the Europe PMC REST API.
- **Why:** the owner asked for confirmation that reading, saving and copying the sources breaks no law or licence.
- **Decisions & gotchas:** the licence check on 2026-10-19 read 20 PMC article pages with a short script, which PMC's terms forbid (automated retrieval from its website). Only licence lines were read and no article text was stored; recorded in `docs/SOURCES.md`, and rule 10 prevents a repeat.
- **Follow-ups:** none.

## 2026-10-19 · Project structure, PRD and architecture · direct commit (no ticket, before the setup ticket)
- **Brief:** prepares the whole project; serves the brief's requirements through `docs/PRD.md` and `docs/ARCHITECTURE.md`.
- **What:**
  - `docs/PRD.md` (new): the product decisions moved out of `docs/BRIEF.md`, plus product-level acceptance criteria AC-1 to AC-15. `docs/BRIEF.md` now only summarises the course brief (optional tasks numbered) and the submission approach.
  - `docs/ARCHITECTURE.md` (new): the technical design; decisions D1-D8 approved by the owner.
  - `CLAUDE.md` slimmed to an overview, mandatory reading, a map of the docs, code conventions and commands. Its rules moved to `.claude/rules/`: `copyright.md`, `workflow.md`, `security-privacy.md` (always loaded) and `testing.md` (loaded for `tests/**`).
  - `docs/TESTING.md`, `docs/SECURITY.md` (vulnerability reporting, threat model, controls) and `docs/IMPLEMENTATION_PLAN.md` (format only; tickets come in phase 4) added.
  - `docs/DEPLOYMENT.md`: a checklist for copying the repo to the course repository. README: a docs table. QRSPI skill, code-reviewer and PR template point to the new files and ask for ticket IDs and plan status.
- **Why:** the owner's proposed structure; the repo will be copied to the course repository without issues and PRs, so the record of work must live in files.
- **Decisions & gotchas:**
  - One plan file (`IMPLEMENTATION_PLAN.md`) holds tickets and their status; no separate `TASKS.md`, so the two cannot drift.
  - Only `.streamlit/secrets.toml.example`, no `.env.example`.
  - GitHub shows `docs/SECURITY.md` as the repo's security policy, so it starts with a reporting section.
- **Follow-ups:** write the epics and tickets (phase 4) and the GitHub issues; setup ticket (pyproject, CI, app skeleton); `ATTRIBUTION.md` comes with the source-download ticket.

## 2026-10-19 · Project setup: rules, brief and sources · initial commit (no ticket)
- **Brief:** prepares the whole project; the copyright policy and the public-portfolio goal are beyond the brief (owner's request).
- **What:** `CLAUDE.md` (mandatory reading, QRSPI workflow, PR and ticket rules, testing, secrets, personal data, copyright policy); `docs/BRIEF.md` (course brief summary and the owner's PRD decisions); `docs/SOURCES.md` (21 approved open-licensed sources, excluded sources with reasons); `docs/DEPLOYMENT.md` (notes for a later deploy); `.claude/` QRSPI skill and code-reviewer agent adapted from Sprint 1; PR template and PR checks workflow; `.gitignore` for secrets, downloaded data and the vector store.
- **Why:** the owner wanted the rules, the brief and a legally clean source list settled before any code.
- **Decisions & gotchas:**
  - Licences of all 20 approved articles (and the correction to #18) were read from the article itself on 2026-10-19; #12 is CC BY 2.0, the rest CC BY 4.0.
  - Sprint 1 models (`openai/gpt-5-mini` default, `gpt-5-nano`, `gpt-5`) and `qwen/qwen3-embedding-8b` are on OpenRouter and the chat models support tool calling (checked 2026-10-19); none supports `temperature`.
  - No separate security agent: the code-reviewer's security section now covers user input, retrieved text and tool arguments, and `/security-review` runs on security-relevant PRs.
  - CI (`ci.yml`) is not added yet: it needs `pyproject.toml`, so it comes with the setup ticket.
- **Follow-ups:** confirm the course accepts this personal repo; write `docs/ARCHITECTURE.md`; write `docs/PLAN.md` and the GitHub issues; setup ticket (pyproject, CI, app skeleton).
