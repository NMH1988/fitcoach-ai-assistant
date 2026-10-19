# Deployment notes

Not deployed yet. For the course review the app runs locally. This file collects what must be true before a public deployment, so the first deploy is not done from memory. Check the hosting provider's current documentation at deploy time; the details below were not re-checked against it.

## Target

**Streamlit Community Cloud** (free, deploys straight from this GitHub repo, redeploys on every push to `main`). Alternatives if it does not fit: Hugging Face Spaces, Render.

## Rule zero: nobody spends the owner's OpenRouter key

The owner's key must never be usable by an anonymous visitor. The key also stops working after the course, so the public demo must not depend on it. Choose one option before deploying:

1. **Bring your own key (recommended for the portfolio demo).** The visitor pastes their own OpenRouter key into a password field. It is kept only for that browser session, never logged, stored, or shown, and the app explains this. The owner's key is not configured on the server at all.
2. **Access gate plus spending limit.** Only invited people can open the app (private app or a password check), the owner's key is stored in the host's secrets settings, and the key has a credit limit set in OpenRouter's key settings, plus the in-app per-session rate limit.

Either way:
- The key is never in the repo, in logs, in error messages or in the page.
- When the key is missing, invalid or out of credit (401/402), the app shows a clear message instead of crashing.
- GitHub secret scanning and push protection are on for the repo (Settings -> Code security), so an accidentally committed key is blocked or reported.
- If a key ever leaks: revoke it on https://openrouter.ai/keys first, then clean up.

## Checklist before the first deploy

1. **Runs from a clean clone.** Follow the README on a fresh checkout: install, download sources, build the index, run. Fix anything that needs a file that is not in the repo.
2. **Dependencies.** Runtime packages pinned in `pyproject.toml`. Check which dependency file and Python version the host reads, and set the Python version in the host's settings to match `.python-version`.
3. **Secrets.** Only through the host's secrets settings (TOML, same names as `.streamlit/secrets.toml.example`). Never commit `.streamlit/secrets.toml`.
4. **Knowledge base on an ephemeral disk.** The host's disk is reset on restart. Decide in `docs/ARCHITECTURE.md` whether the Chroma index is rebuilt at startup (embedding cost on every cold start) or a built index is committed (allowed only under the copyright policy: approved CC BY sources, attribution in place).
5. **USDA data.** A trimmed copy of the Foundation Foods CSV (CC0) is committed as `data/usda_foods.csv` (T4.3), so a deploy needs no download.
6. **Limits.** Check the host's memory and CPU limits against Chroma, the embeddings and the PDF builder.
7. **Personal data.** The profile and chat stay in the session only; logs contain no profile values or chat text.
8. **Costs.** Default model `openai/gpt-5-mini`, `max_tokens` capped, rate limit on; the token and cost display works.
9. **Legal text on the page.** The "not medical advice" disclaimer and a link to the sources and attribution are visible.

## Deploy steps (Streamlit Community Cloud, first time)

1. Sign in at https://share.streamlit.io with the GitHub account that owns the repo.
2. Create an app: repo `NMH1988/nutrition-ai-assistant`, branch `main`, main file `app.py`.
3. In advanced settings: choose the Python version; paste secrets only if option 2 above is used.
4. Deploy, open the URL, and run the checks below.
5. Optional: set the repo variable `APP_URL` and add the Sprint 1 style CD workflow that waits for CI on `main` and then calls `<APP_URL>/_stcore/health`.

## Copying the repo to the course repository

The work happens in `NMH1988/nutrition-ai-assistant`; when it is finished, it is copied into the repository the course provides, where the reviewers read it. Only files and commit history travel; issues, pull requests, PR descriptions and review comments stay behind.

Before copying:
1. `docs/IMPLEMENTATION_PLAN.md` shows every ticket's final status, and `docs/PROGRESS.md` has an entry for every merged PR.
2. The README explains how to install, download the sources, build the index and run the app, and links the docs.
3. CI is green on `main`; no secrets in the history (GitHub secret scanning shows no alerts).
4. Docs refer to tickets by ID (`T1.2`); any remaining `#<n>` issue links are full URLs to the personal repo, or removed.

Copying (keeps the full history):
1. Clone the course repository and check that it is empty, or note what the course put there (e.g. its own README) so nothing of theirs is overwritten without asking.
2. From the personal repo: `git remote add course <course repo URL>` and `git push course main` (add `--force` only if the course repo is empty apart from a placeholder and the course allows it).
3. In the course repo: check that the README renders and CI runs. If the reviewers work through pull requests, disable or delete `.github/workflows/pr-checks.yml` there: it fails any PR that does not close an issue, and the course repo has no issues.
4. Update the repo links in `docs/BRIEF.md` and this file if the reviewers should only see the course repo.

## After each deploy

- The app loads and answers one question with sources.
- Each tool runs once and its result shows.
- The PDF download works.
- The key does not appear in the page, the browser's network tab or the logs.
- A request without a valid key shows the friendly error.
