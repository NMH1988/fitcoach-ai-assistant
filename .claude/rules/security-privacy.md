# Secrets, personal data and security (mandatory)

Full threat model and controls: `docs/SECURITY.md`.

## The OpenRouter key

- The key is read only from `.streamlit/secrets.toml` or the `OPENROUTER_API_KEY` environment variable, through one config function (`get_api_key()`). `.streamlit/secrets.toml` and `.env` are gitignored; only `.streamlit/secrets.toml.example` with a placeholder is committed.
- Never hardcode, log, print, display, or put the owner's key in exceptions, `st.session_state`, tests, issues, PRs or commit messages. Never open the real secrets file. (If the "bring your own key" option in `docs/DEPLOYMENT.md` is built, a visitor's own key may live in the session only, under the same never-log, never-show rules.)
- **No anonymous visitor may spend the owner's key.** A public deployment must use one of the options in `docs/DEPLOYMENT.md`. Until then the app runs locally only.

## Model clients

- Build chat and embedding clients only with `build_chat_model()` and `build_embeddings()` in `src/llm.py`; they check the model allowlist and cap `max_tokens` when the client is built.
- **Never pass `model`, `max_tokens`, `max_completion_tokens`, `base_url` or `reasoning_effort` at call time** (`.bind(...)`, `invoke(..., max_tokens=...)`, `model_kwargs`, `extra_body`): call-time arguments override the client's settings and would get around the allowlist and the cap. For another model or budget, build a new client.

## Personal data

- The user's profile (weight, height, age, sex, activity, goal) lives in `st.session_state` only for the session. It is never logged, written to disk, sent anywhere except the LLM call that needs it, or put in the vector store.
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
