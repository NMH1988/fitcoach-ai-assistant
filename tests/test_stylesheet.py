"""Tests for the app's own stylesheet, assets/app.css (T9.23; docs/UI_DESIGN.md).

AppTest draws no CSS, so these read the file: it loads nothing, runs nothing, sets no colour, aims
only at st-key classes and listed test ids, and changes only layout, so a renamed class or test id
leaves Streamlit's own layout in place. The browser checks are in docs/TESTING.md.
"""

import re

import pytest

from src import config

# The data-testid values the stylesheet may aim at. Streamlit renames test ids without notice, so
# each one is a known risk: if it is renamed, its rule stops applying and nothing else changes.
#   stDialog           the st.dialog box (T4.6's rule is scoped to it)
#   InputInstructions  a field's "Press Enter to apply" (and a text field's character counter)
ALLOWED_TEST_IDS = frozenset({"stDialog", "InputInstructions"})
# Text that would load a resource, run script or close the <style> block st.html wraps it in.
FORBIDDEN = ("@import", "url(", "//", "<", "expression(", "javascript:", "behavior:")
# Layout, spacing and visibility only (docs/UI_DESIGN.md).
LAYOUT_PROPERTY = re.compile(r"display|gap|(min-|max-)?width|(margin|padding|flex)(-[a-z]+)*")
# The values a layout property may take: lengths and numbers, and these keywords. No colour name is
# among them, so a colour cannot slip in through a value.
LENGTH = re.compile(r"-?(\d+|\d*\.\d+)(px|rem|em|%|vw|vh|fr)?")
KEYWORDS = frozenset(
    {
        "none",
        "block",
        "inline",
        "inline-block",
        "flex",
        "inline-flex",
        "grid",
        "contents",
        "auto",
        "row",
        "column",
        "row-reverse",
        "column-reverse",
        "wrap",
        "nowrap",
        "wrap-reverse",
        "!important",
    }
)
COLOUR = re.compile(r"#[0-9a-f]{3,8}\b|\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix)\(")
# A selector part: an st-key class, a listed test id, or a combinator.
SELECTOR_PART = re.compile(r'\.st-key-[a-z0-9_-]+|\[data-testid="(?P<id>[A-Za-z]+)"\]|\s+|\s*>\s*')
MEDIA = re.compile(r"@media \(max-width: (\d+)px\)")


def _css() -> str:
    """Return the stylesheet's text."""
    return config.APP_CSS_PATH.read_text(encoding="utf-8")


def _without_comments(css: str) -> str:
    """Return the CSS with its /* ... */ comments removed."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _blocks(css: str) -> list[tuple[str, str]]:
    """Split CSS into (prelude, body) pairs at the top level, keeping nested blocks in the body."""
    blocks, depth, start, prelude = [], 0, 0, ""
    for index, char in enumerate(css):
        if char == "{":
            if depth == 0:
                prelude, start = css[start:index].strip(), index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            assert depth >= 0, "unbalanced braces"
            if depth == 0:
                blocks.append((prelude, css[start:index]))
                start = index + 1
    assert depth == 0 and not css[start:].strip(), "unbalanced braces or text outside a rule"
    return blocks


def _rules(css: str) -> list[tuple[str, str, str | None]]:
    """Return every style rule as (selector, declarations, its @media prelude or None)."""
    found = []
    for prelude, body in _blocks(_without_comments(css)):
        if prelude.startswith("@media"):
            found += [(selector, decls, prelude) for selector, decls in _blocks(body)]
        elif not prelude.startswith("@"):  # another at-rule is refused by problems()
            found.append((prelude, body, None))
    return found


def _declarations(body: str) -> list[tuple[str, str]]:
    """Return a rule's declarations as (property, value) pairs."""
    pairs = []
    for declaration in filter(str.strip, body.split(";")):
        prop, _, value = declaration.partition(":")
        pairs.append((prop.strip().lower(), value.strip().lower()))
    return pairs


def problems(css: str) -> list[str]:
    """Return every way this CSS breaks the stylesheet's rules (empty when it keeps them)."""
    found = [f"forbidden {text!r}" for text in FORBIDDEN if text in css.lower()]
    if found:
        return found
    for prelude, _ in _blocks(_without_comments(css)):
        media = MEDIA.fullmatch(prelude)
        if prelude.startswith("@") and not media:
            found.append(f"at-rule {prelude!r}: only @media (max-width: Npx)")
        elif media and int(media.group(1)) != config.PHONE_MAX_WIDTH_PX:
            found.append(f"{prelude!r}: the width is not config.PHONE_MAX_WIDTH_PX")
    for selector, body, _ in _rules(css):
        for part in selector.split(","):
            left = part.strip()
            for match in SELECTOR_PART.finditer(left):
                test_id = match.group("id")
                if test_id is not None and test_id not in ALLOWED_TEST_IDS:
                    found.append(f"test id {test_id!r} is not on the list")
            if not left or SELECTOR_PART.sub("", left):
                found.append(f"selector {part.strip()!r}: only st-key classes and listed test ids")
        for prop, value in _declarations(body):
            if not LAYOUT_PROPERTY.fullmatch(prop):
                found.append(f"property {prop!r} is not a layout property")
            if COLOUR.search(value):
                found.append(f"{prop}: {value!r} sets a colour")
            elif not all(LENGTH.fullmatch(word) or word in KEYWORDS for word in value.split()):
                found.append(f"{prop}: {value!r} has a value outside the allowed ones")
    return found


def test_the_stylesheet_keeps_its_rules():
    """The committed stylesheet loads nothing, sets no colour and only changes layout."""
    assert problems(_css()) == []


def test_the_stylesheet_path_is_absolute():
    """The path is built from the project root: st.html reads a relative one from the cwd."""
    assert config.APP_CSS_PATH.is_absolute()
    assert config.APP_CSS_PATH == config.PROJECT_ROOT / "assets" / "app.css"


def test_the_dialog_rule_stays_scoped_to_the_dialog():
    """T4.6's rule hides the input instructions inside the dialog only."""
    rules = [rule for rule in _rules(_css()) if "InputInstructions" in rule[0]]
    assert rules == [
        ('[data-testid="stDialog"] [data-testid="InputInstructions"]', rules[0][1], None)
    ]
    assert _declarations(rules[0][1]) == [("display", "none")]


@pytest.mark.parametrize(
    "css",
    [
        '@import "https://example.com/a.css";',
        ".st-key-a { width: 1px; } .st-key-b { display: block } /* url(x) */",
        "/* //cdn.example.com */ .st-key-a { width: 1px; }",
        ".st-key-a { width: 1px; } </style><script>alert(1)</script>",
        ".st-key-a { width: expression(alert(1)); }",
        ".st-key-a { behavior: url(x.htc); }",
        ".st-key-a { width: javascript:alert(1); }",
    ],
)
def test_the_check_refuses_anything_that_loads_or_runs(css):
    """A load, a script, an expression or a way out of the <style> block is refused."""
    assert problems(css)


@pytest.mark.parametrize(
    "css",
    [
        ".st-key-a { color: red; }",
        ".st-key-a { background: #fff; }",
        ".st-key-a { width: 1px; border-color: transparent; }",
        ".st-key-a { padding: rgb(0, 0, 0); }",
        ".st-key-a { margin: currentColor; }",
        ".st-key-a { gap: hsl(0 0% 0%); }",
        ".st-key-a { display: red; }",
    ],
)
def test_the_check_refuses_a_colour(css):
    """A colour by hex, function or name, in any property, is refused."""
    assert problems(css)


@pytest.mark.parametrize(
    "css",
    [
        ".st-key-a { position: absolute; }",
        ".st-key-a { height: 0; }",
        ".st-key-a { visibility: hidden; }",
        ".st-key-a { font-size: 2rem; }",
    ],
)
def test_the_check_refuses_a_property_that_is_not_layout(css):
    """Only display, gap, margins, paddings, flex and widths are allowed."""
    assert problems(css)


@pytest.mark.parametrize(
    "css",
    [
        "div { display: none; }",
        ".stButton { display: none; }",
        '[data-testid="stSidebar"] { display: none; }',
        ".st-key-a:hover { display: none; }",
        "* { margin: 0; }",
        ".st-key-a, p { margin: 0; }",
    ],
)
def test_the_check_refuses_other_selectors(css):
    """Tags, Streamlit's own classes, unlisted test ids and pseudo-classes are refused."""
    assert problems(css)


@pytest.mark.parametrize(
    "css",
    [
        "@media (max-width: 1px) { .st-key-a { display: none; } }",
        "@media (min-width: 641px) { .st-key-a { display: none; } }",
        "@supports (display: grid) { .st-key-a { display: grid; } }",
        "@font-face { font-family: x; }",
    ],
)
def test_the_check_refuses_other_at_rules_and_breakpoints(css):
    """Only @media (max-width: config.PHONE_MAX_WIDTH_PX px) is allowed."""
    assert problems(css)


def test_the_check_accepts_layout_rules_and_the_phone_query():
    """St-key classes, listed test ids, layout values and the phone breakpoint pass."""
    width = config.PHONE_MAX_WIDTH_PX
    css = (
        "/* a comment */\n"
        ".st-key-client_table { display: block; }\n"
        f"@media (max-width: {width}px) {{\n"
        "  .st-key-client_table { display: none !important; }\n"
        "  .st-key-client_cards > .st-key-card { flex-direction: column; gap: 0.5rem; }\n"
        "}\n"
        '[data-testid="stDialog"] [data-testid="InputInstructions"] { margin: 0 auto; }\n'
    )
    assert problems(css) == []
