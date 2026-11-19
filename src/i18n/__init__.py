"""UI text in English and German (T7.1): one lookup function and number formats per language.

Every string the app shows is here under a key, in both languages; `t(key, lang)` returns it.
`core` holds `t()`, the languages and their number formats; each other module holds the texts of
one page or concern as an `EN` and a `DE` dict with the same keys, and a key is defined in one of
them only (tests/test_i18n.py). The English text of messages that also go to the model or into the
summary PDF (guard and guardrail messages, model errors, profile labels, status labels) keeps
living in its module, and tests check that the English entries here are the same. The German
texts are our own writing, in the formal "Sie", and the owner reviews them before merge (T7.1,
AC-5).
"""

from src.i18n import account, chat, dashboards, food, messages, profile, reviews, shared
from src.i18n.core import (
    LANGUAGE_LABELS,
    LANGUAGES,
    SESSION_KEY,
    TEXT,
    Language,
    add_texts,
    number,
    percent,
    plain,
    t,
)

# The page modules whose texts make up TEXT.
PAGES = (shared, chat, messages, profile, food, dashboards, reviews, account)
for _page in PAGES:
    add_texts(_page.__name__, _page.EN, _page.DE)
del _page

__all__ = [
    "LANGUAGES",
    "LANGUAGE_LABELS",
    "PAGES",
    "SESSION_KEY",
    "TEXT",
    "Language",
    "number",
    "percent",
    "plain",
    "t",
]
