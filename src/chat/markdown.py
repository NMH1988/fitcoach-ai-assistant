"""Text shown as Markdown: escaping, safe URLs, images removed and the paced answer."""

import os
import re
import time
import urllib.parse
from collections.abc import Callable

# A Markdown image, inline (![alt](url)) or by reference (![alt][ref]): the browser would load
# its URL with no click, so an injected one could send text to another server. A bare ![alt]
# is left to the escape in remove_images(), so "protein![S1]" keeps its citation.
_MARKDOWN_IMAGE = re.compile(r"!\[([^\[\]]*)\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\])")
# One word of a paced answer with the spaces before it (or the rest of a word already begun).
_PACED_WORD = re.compile(r"\s*\S+")
# Characters Streamlit's Markdown would read as formatting, HTML, LaTeX, strikethrough (~) or an
# emoji or icon shortcode (:) in a title.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>$~:])")


def escape_markdown(text: str) -> str:
    """Escape the characters Markdown would read as formatting, so the text shows as written."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def markdown_url(url: str) -> str:
    """Percent-encode a URL so none of its characters can end a Markdown link early."""
    return urllib.parse.quote(url, safe=":/%#?=&")


class PacedWriter:
    """Show a growing answer word by word, at most words_per_second, through show(text)."""

    def __init__(
        self,
        show: Callable[[str], None],
        words_per_second: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the display function, the pause between words (0 = none) and the clock."""
        self._show = show
        self._pause = 1 / words_per_second if words_per_second > 0 else 0.0
        self._sleep = sleep
        self._shown = ""

    def __call__(self, text: str) -> None:
        """Reveal the words of text not shown yet, one at a time, pausing after each."""
        # Empty text clears what was shown (the text of a reply that called tools).
        if self._pause == 0 or not text:
            self._shown = text
            self._show(text)
            return
        # Usually the text only grows; if an earlier part changed (an image removed once its
        # syntax was complete), the reveal starts where the shown text and the new text differ.
        start = len(os.path.commonprefix([self._shown, text]))
        for word in _PACED_WORD.finditer(text, start):
            self._shown = text[: word.end()]
            self._show(self._shown)
            self._sleep(self._pause)


def remove_images(answer: str) -> str:
    """Replace each Markdown image with its alt text, then escape any "![" left, so none loads."""
    without_images = _MARKDOWN_IMAGE.sub(lambda image: image.group(1), answer)
    # The pattern misses alt text with nested brackets (![a[b]c](url)), which CommonMark still
    # reads as an image; with its bracket escaped, any "![" left is plain text.
    return without_images.replace("![", "!\\[")
