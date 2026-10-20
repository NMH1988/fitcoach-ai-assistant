"""Escaping for text put inside a delimited prompt block (<sources>, <user_input>), T3.4.

Imports nothing from `src`, so every step that builds a prompt (the answer step in `src/chat.py`,
query translation in `src/rag/`, the tool loop) can use it without an import cycle.
"""

import html

# Full-width and small-form "<", ">" and "&", which NFKC reads as the ASCII characters: folded
# before escaping, so "＜/sources＞" in a chunk is escaped like "</sources>". Look-alikes NFKC does
# not fold ("‹", "〈") are a known limit (docs/SECURITY.md).
PROMPT_BRACKET_FORMS = str.maketrans(
    {"＜": "<", "﹤": "<", "＞": ">", "﹥": ">", "＆": "&", "﹠": "&"}
)


def escape_prompt_data(text: object) -> str:
    """Escape &, < and > as HTML entities, so the text can never close or open a prompt block."""
    # With no "<" or ">" left, no look-alike (</user-input>, <sources lang="en">, <sources/>) can
    # end a block early; "&" too, so a typed "&lt;/sources&gt;" stays text. The model reads the
    # entities as the characters. html.unescape gives the text back, with full-width and
    # small-form brackets as their ASCII forms: a chunk never passes the guard's NFKC check, so
    # they are folded here.
    return html.escape(str(text).translate(PROMPT_BRACKET_FORMS), quote=False)
