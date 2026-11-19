"""The languages, their number formats, and `t()`, which returns a key's text in a language."""

from typing import Literal

Language = Literal["en", "de"]
LANGUAGES: tuple[Language, ...] = ("en", "de")
# What the sidebar's language control shows for each language, the same in both UIs (T9.23).
LANGUAGE_LABELS: dict[Language, str] = {"en": "English", "de": "Deutsch"}
# Key of the chosen language in st.session_state (docs/UI_DESIGN.md, "Language").
SESSION_KEY = "language"

# Every text by language and key, filled once at import by src/i18n/__init__.py through
# add_texts(), from the page modules.
TEXT: dict[Language, dict[str, str]] = {"en": {}, "de": {}}

# German swaps the thousands and decimal marks: 2,500.5 (en) is 2.500,5 (de).
_DE_MARKS = str.maketrans({",": ".", ".": ","})


def number(value: float, lang: Language) -> str:
    """Show a number with thousands marks in the language's style: 2,500.5 or 2.500,5."""
    if isinstance(value, int):
        text = f"{value:,}"
    else:
        text = f"{value:,g}"
    return text.translate(_DE_MARKS) if lang == "de" else text


def percent(value: int | str, lang: Language) -> str:
    """Show a percentage as the language writes it: "20%" or "20 %"."""
    return f"{value} %" if lang == "de" else f"{value}%"


def plain(value: float, lang: Language) -> str:
    """Show a number without thousands marks, with the language's decimal mark: 1.5 or 1,5."""
    text = f"{value:g}"
    return text.replace(".", ",") if lang == "de" else text


def de_number(value: int) -> str:
    """Return a whole number with German thousands marks, for texts built at import."""
    return number(value, "de")


def t(key: str, lang: Language, **params: object) -> str:
    """Return the UI text of a key in a language, with its {placeholders} filled in."""
    # Numbers are shown without thousands marks in the language's decimal style (a limit of 2000
    # characters, 18 years, 2.5 s); callers pass a formatted string where marks are wanted.
    filled = {
        name: plain(value, lang)
        if isinstance(value, int | float) and not isinstance(value, bool)
        else value
        for name, value in params.items()
    }
    return TEXT[lang][key].format(**filled)


def add_texts(page: str, en: dict[str, str], de: dict[str, str]) -> None:
    """Add a page's texts to TEXT; refuse a page whose languages differ or a key seen before."""
    if set(en) != set(de):
        raise ValueError(f"{page}: the English and German keys differ")
    taken = set(en) & set(TEXT["en"])
    if taken:
        raise ValueError(f"{page}: keys already defined by another page: {sorted(taken)}")
    TEXT["en"].update(en)
    TEXT["de"].update(de)
