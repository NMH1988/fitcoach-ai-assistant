# Secrets, personal data and security (mandatory)

Full threat model and controls: `docs/SECURITY.md`.

## The OpenRouter key

- The key is read only from `.streamlit/secrets.toml` or the `OPENROUTER_API_KEY` environment variable, through one config function (`get_api_key()`). `.streamlit/secrets.toml` and `.env` are gitignored; only `.streamlit/secrets.toml.example` with a placeholder is committed.
- Never hardcode, log, print, display, or put the owner's key in exceptions, `st.session_state`, tests, issues, PRs or commit messages. Never open the real secrets file. (If the "bring your own key" option in `docs/DEPLOYMENT.md` is built, a visitor's own key may live in the session only, under the same never-log, never-show rules.)
- **No anonymous visitor may spend the owner's key.** A public deployment must use one of the options in `docs/DEPLOYMENT.md`. Until then the app runs locally only.

## Logs

- Log only through the app's loggers (`logging.getLogger(__name__)` in `src/`; `views/`, `scripts/` and `app.py` write no log lines, which `tests/test_observability.py` scans for): `src/observability.py` writes JSON lines to stderr and keeps only the fields on its allowlist. Add a field to `ALLOWED_FIELDS` only if it is an id, a count, a code, a status or a duration, and update the list in `docs/SECURITY.md`.
- **Never log** the question, a rewrite, the answer, chunk text, a profile value, a tool argument or result, the key, an error's message or traceback (`exc_info`), or a name the model made up (a tool name). Log `LLMError.diagnostic` or `llm.error_diagnostic(exc)` instead of an error. Use a fixed event name, never an f-string or `%s` argument with data.
- The event is one of `observability.EVENTS` (`turn`, `guard_rejected`, ...; add a new one there); anything else is written as `unnamed_event`. Field values are plain (text, numbers, booleans, `None`, flat lists): pass `llm.error_diagnostic(exc)`, never `exc`. Never turn up the level of the `openai`, `httpx` or `httpcore` loggers (at DEBUG they log the prompt, the profile and the key); `configure_logging()` keeps them at WARNING.
- Every new log call carries the `turn_id` when it runs inside a turn. A new ending of a turn needs a test in `tests/test_observability.py` that its lines hold none of the canary values.

## Model clients

- Build chat and embedding clients only with `build_chat_model()` and `build_embeddings()` in `src/llm.py`; they check the model allowlist and cap `max_tokens` when the client is built.
- **Never pass `model`, `max_tokens`, `max_completion_tokens`, `base_url` or `reasoning_effort` at call time** (`.bind(...)`, `invoke(..., max_tokens=...)`, `model_kwargs`, `extra_body`): call-time arguments override the client's settings and would get around the allowlist and the cap. For another model or budget, build a new client.
- **Never change a built client** either: no assigning its fields (`chat.max_tokens = ...`, `chat.model_name = ...`), no `model_copy(update=...)`, no `configurable_fields(...)` or `configurable_alternatives(...)`. These bypass the checks in the same way.
- `tests/test_client_rules.py` scans `src/`, `views/`, `app.py` and `scripts/` for the three rules above (T9.2); it cannot see a method reached through `getattr` or kept in a variable, so review still checks those.

## Personal data

- **Guests:** the profile (weight, height, age, sex, activity, goal) lives in `st.session_state` only for the session. Nothing a guest enters is written to disk.
- **Signed-in users** (T9.6): the account (keyed ID, role, display name), the profile history, weights, food and workout logs, targets, preferences, relationships and scopes, reviews, invitations, code attempts and the audit rows are stored in the local SQLite store (`src/store/`, the file in gitignored `data/store/`) and, from T9.16, the weekly review threads in the checkpointer's file (D12; metrics, not chat messages); nowhere else on disk. Chats are never stored.
- Stored or not, personal data is never logged (`tests/test_observability.py` runs the store with canary values), never sent anywhere except the LLM call that needs it, never shown to anyone but the user and, within the scopes the user shares, their coach (the relationship itself, its dates and scope history, the other side's ID, and the audit rows of the coach's reads and review decisions are seen by both sides, in their exports too; from T9.12 each side also sees the other's display name on screen (the coach in the client list, the gymer on the sharing page), though not in the export), and never put in the vector store. An error raised by the store names the field, never the value.
- **The store** (`src/store/`): only the standard library's `sqlite3`, embedded; every query is a constant string with `?` parameters, never SQL built with f-strings, `%`, `.format()`, `+` or `.join()` (`tests/test_store_sql_scan.py`). The sharing rule is written once, as the `open_shares` view in `schema.py`; every read of another user's data goes through `access.authorised_read()` (from T9.12, the other side's display name excepted: read by a function that checks the relationship instead), and a query that filters by sharing reads the view: a coach, of a gymer, an active relationship and the scope shared (body, nutrition, training; preferences never), else the same `NotFound`; a coach's read and every review decision write an audit row with no values. A new public function in `src/store/` is classified in `tests/test_store_access.py` (a read goes through the refused-cases matrix; the display-name read of T9.12 through its own group). The authorisation lives in the store, never only in the UI or the prompt. Records are never updated in place (a new row instead); foreign keys are on and never cascade, so `my_data.delete_user_data()` names every table, and a new table that refers to users must be added to it and to `export_user_data()`.
- Use synthetic data only in demos and tests; the store file is not encrypted (`docs/SECURITY.md`).
- The PDF summary is built in memory and downloaded by the user; the server keeps no copy.

## Chroma: embedded only

chromadb has known, unfixed vulnerabilities in its HTTP server (accepted risk in `docs/SECURITY.md`; four advisories ignored in CI with reasons). They do not apply as long as:
- Chroma runs only embedded in the app's process (`chromadb.PersistentClient` / `langchain_chroma.Chroma` with a local `persist_directory`). Never start a Chroma server (`chroma run`, Docker image), never use `HttpClient` or `AsyncHttpClient`, never expose Chroma on a port.
- Embeddings come from our OpenRouter client. Never use Chroma's built-in embedding functions or pass `trust_remote_code`.
- When a fixed chromadb release exists (Dependabot will propose it), upgrade and remove the matching `--ignore-vuln` lines from `.github/workflows/ci.yml`. Never add an ignore without a documented reason in `docs/SECURITY.md`.

## Guards

- Every path that reaches the LLM or the embedding API goes through the input guard first; rejected input makes no API call.
- User input and retrieved text are data, not instructions: delimited, never concatenated into the system prompt. Tool arguments are validated (types and ranges) before a tool runs.
- The domain guardrails in `docs/PRD.md` are enforced in code where possible (e.g. the calorie floor, the age limit), not only in the prompt.
- LLM output is rendered as Markdown without `unsafe_allow_html`.
