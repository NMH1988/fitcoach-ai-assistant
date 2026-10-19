# Security

## Reporting a vulnerability

This is a student portfolio project. If you find a security problem, contact the owner through their GitHub profile ([NMH1988](https://github.com/NMH1988)). Please do not open a public issue with a working exploit, and never post an API key anywhere.

## What we protect

| Asset | Why it matters |
|---|---|
| The owner's OpenRouter API key | Anyone holding it can spend the owner's credit |
| The user's profile (weight, height, age, sex, activity, goal) | Personal health data |
| The users themselves | Wrong or harmful nutrition advice can hurt people |
| The repo's legal state | It is public; everything in it must be redistributable (`.claude/rules/copyright.md`) |

## Threats and controls

| Threat | Control | Where |
|---|---|---|
| Key leaked in the repo | Secrets files gitignored; only a placeholder example committed; GitHub secret scanning and push protection on | `.gitignore`, repo settings |
| Key leaked by the app | Read only through `get_api_key()`; never logged, shown, stored in session state or put in errors | `src/config.py` |
| Strangers spending the key on a public deploy | "Bring your own key" or access gate plus spending limit; local only until then | `docs/DEPLOYMENT.md` |
| Prompt injection in user input | Input guard (patterns, length); user text delimited in the user message, never in the system prompt; attack and benign test strings | `src/guard.py`, prompts |
| Indirect injection in retrieved text | Retrieved chunks delimited as data; the system prompt says to ignore instructions inside them; only approved, licence-checked sources are indexed | `src/chat.py`, `docs/SOURCES.md` |
| Malicious or wrong tool arguments | Pydantic schemas with ranges; the profile comes from the session, not from the model; tools never touch files, URLs or code | `src/tools/` |
| Runaway cost | Guard before any API call; per-session rate limit; capped `max_tokens`; at most 4 tool rounds; cheap model for query translation; cost shown to the user | `src/config.py`, `src/guard.py`, `src/usage.py` |
| Harmful advice | Domain guardrails: no performance-enhancing drug dosing; calorie floor in code; age 18+ in the profile; redirect pregnancy, medical and disordered-eating cases; disclaimer always visible | `src/tools/energy.py`, `src/profile.py`, system prompt, UI |
| Answers without evidence | Every answer is grounded in retrieved sources and cites them; "not covered" when nothing is found | `src/chat.py` |
| Personal data leaks | Profile in session state only; never logged, stored, indexed; PDF built in memory | `src/profile.py`, `src/export_pdf.py` |
| Script injection through model output | Markdown rendering without `unsafe_allow_html` | `app.py` |
| Vulnerable or badly licensed dependencies | `pip-audit` in CI; permissive licences checked before adding a package | `.github/workflows/ci.yml`, `docs/ARCHITECTURE.md` section 12 |

## Known limits

- Pattern-based injection checks catch common attacks, not all of them; the delimiting and the system prompt are the second line.
- The guardrails in the system prompt depend on the model following them; the ones in code (calorie floor, age limit, argument ranges) do not.
- The app gives general information for healthy adults and is not medical advice.
