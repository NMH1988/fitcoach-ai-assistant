"""Tests for the app's own stylesheet, assets/app.css (T9.23; docs/UI_DESIGN.md).

AppTest draws no CSS, so these read the file: it loads nothing, runs nothing, sets no colour, aims
only at st-key classes and listed test ids, and changes only layout, so a renamed class or test id
leaves Streamlit's own layout in place. Three exceptions (T9.5, owner's choices of 2026-11-02): the
app's title, one selector with a short list of type properties and only the gradient colours of
config.TITLE_GRADIENT and its fallback, each readable on both modes' backgrounds; the page menu's
labels, one selector with a font size only; and the start page's sign-in button, two selectors, the
one @keyframes and the one reduced-motion query, with the same colours and white text. The browser
checks are in docs/TESTING.md.
"""

import re
import tomllib

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
# The app's title (T9.5): the only rule that may set colour or type, outside any @media.
TITLE_SELECTOR = ".st-key-app_title h1"
TITLE_COLOURS = frozenset(c.lower() for c in (*config.TITLE_GRADIENT, config.TITLE_FALLBACK))
GRADIENT = re.compile(r"linear-gradient\(\d{1,3}deg((?:, #[0-9a-f]{6})+)\)")
HEX = re.compile(r"#[0-9a-f]{6}")
TITLE_VALUES = {
    "display": re.compile(r"inline-block"),
    "font-size": re.compile(r"[1-5](\.\d)?rem"),
    "font-weight": re.compile(r"[1-9]00"),
    "color": HEX,
    "background-image": GRADIENT,
    "-webkit-background-clip": re.compile(r"text"),
    "background-clip": re.compile(r"text"),
    "-webkit-text-fill-color": re.compile(r"transparent"),
}
# The sidebar's page menu (T9.5, owner's choice): one exact selector on two test ids (a link's
# label), a font size in rem, nothing else. Not on ALLOWED_TEST_IDS: no other rule may use them.
NAV_SELECTOR = '[data-testid="stSidebarNavLink"] [data-testid="stMarkdownContainer"]'
NAV_VALUES = {"font-size": re.compile(r"1(\.\d{1,2})?rem")}
# Large text (the title is over 24 px) needs 3:1 against the page (WCAG 1.4.3).
MIN_TITLE_CONTRAST = 3.0
# The start page's sign-in button (T9.5, owner's choice): the only animation. Its colours are the
# title's gradient and white text; its label is large bold text (at least 1.2rem and 700, so over
# 18.66 px bold), which needs 3:1 too; the one @keyframes slides the gradient and the glow; a
# visitor who asks for less motion gets none.
SIGN_IN_SELECTOR = ".st-key-sign_in button"
SIGN_IN_LABEL_SELECTOR = ".st-key-sign_in button p"
SIGN_IN_TEXT = "#ffffff"
# The gradient and the glow use the title gradient's colours only (white is the text's alone).
SIGN_IN_GRADIENT = frozenset(c.lower() for c in config.TITLE_GRADIENT)
KEYFRAMES = "@keyframes sign-in-glow"
REDUCED_MOTION = "@media (prefers-reduced-motion: reduce)"
GLOW = re.compile(r"drop-shadow\(0 0 \d*\.?\d+rem #[0-9a-f]{6}\)")
POSITION = re.compile(r"\d{1,3}% \d{1,3}%")
SIGN_IN_VALUES = {
    "padding": re.compile(r"\d*\.?\d+rem( \d*\.?\d+rem)?"),
    "border": re.compile(r"none"),
    "border-radius": re.compile(r"\d+px"),
    "color": re.compile(SIGN_IN_TEXT),
    "background-image": GRADIENT,
    "background-size": POSITION,
    "filter": GLOW,
    "animation": re.compile(r"sign-in-glow \d{1,2}s ease-in-out infinite"),
}
SIGN_IN_LABEL_VALUES = {
    "font-size": re.compile(r"(1\.[2-9]\d?|2(\.\d{1,2})?)rem"),
    "font-weight": re.compile(r"[7-9]00"),
}
KEYFRAME_SELECTOR = re.compile(r"\d{1,3}%(, \d{1,3}%)*")
KEYFRAME_VALUES = {"background-position": POSITION, "filter": GLOW}


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
    for prelude, body in _blocks(_without_comments(css)):
        media = MEDIA.fullmatch(prelude)
        if prelude == KEYFRAMES:
            found += _keyframe_problems(body)
        elif prelude == REDUCED_MOTION:
            continue  # its rules are checked with the others below
        elif prelude.startswith("@") and not media:
            found.append(f"at-rule {prelude!r}: only @media (max-width: Npx)")
        elif media and int(media.group(1)) != config.PHONE_MAX_WIDTH_PX:
            found.append(f"{prelude!r}: the width is not config.PHONE_MAX_WIDTH_PX")
    for selector, body, media in _rules(css):
        if selector in (SIGN_IN_SELECTOR, SIGN_IN_LABEL_SELECTOR) or media == REDUCED_MOTION:
            found += _sign_in_problems(selector, body, media)
            continue
        if selector == TITLE_SELECTOR:
            found += _title_problems(body, media)
            continue
        if selector == NAV_SELECTOR:
            if media is not None:
                found.append(f"{NAV_SELECTOR} inside {media!r}")
            found += [
                f"{NAV_SELECTOR}: {prop}: {value!r} is not allowed"
                for prop, value in _declarations(body)
                if prop not in NAV_VALUES or not NAV_VALUES[prop].fullmatch(value)
            ]
            continue
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


def _title_problems(body: str, media: str | None) -> list[str]:
    """Return how the app title's rule breaks its own narrower rules."""
    found = [] if media is None else [f"{TITLE_SELECTOR} inside {media!r}"]
    for prop, value in _declarations(body):
        pattern = TITLE_VALUES.get(prop)
        if pattern is None:
            found.append(f"{TITLE_SELECTOR}: property {prop!r} is not allowed")
        elif not pattern.fullmatch(value):
            found.append(f"{TITLE_SELECTOR}: {prop}: {value!r} is not an allowed value")
        elif any(colour not in TITLE_COLOURS for colour in HEX.findall(value)):
            found.append(f"{TITLE_SELECTOR}: {prop}: {value!r} uses a colour not in config")
    return found


def _values_problems(where: str, body: str, allowed: dict[str, re.Pattern]) -> list[str]:
    """Return how a rule's declarations leave the allowed properties, values or gradient colours."""
    found = []
    for prop, value in _declarations(body):
        pattern = allowed.get(prop)
        if pattern is None:
            found.append(f"{where}: property {prop!r} is not allowed")
        elif not pattern.fullmatch(value):
            found.append(f"{where}: {prop}: {value!r} is not an allowed value")
        elif prop != "color" and any(c not in SIGN_IN_GRADIENT for c in HEX.findall(value)):
            found.append(f"{where}: {prop}: {value!r} uses a colour not in config")
    return found


def _sign_in_problems(selector: str, body: str, media: str | None) -> list[str]:
    """Return how a sign-in button rule, or a rule in the reduced-motion query, breaks its rules."""
    if media == REDUCED_MOTION:
        if selector != SIGN_IN_SELECTOR or _declarations(body) != [("animation", "none")]:
            return [f"{REDUCED_MOTION}: only {SIGN_IN_SELECTOR} {{ animation: none }}"]
        return []
    if media is not None:
        return [f"{selector} inside {media!r}"]
    if selector == SIGN_IN_LABEL_SELECTOR:
        return _values_problems(selector, body, SIGN_IN_LABEL_VALUES)
    return _values_problems(selector, body, SIGN_IN_VALUES)


def _keyframe_problems(body: str) -> list[str]:
    """Return how the one @keyframes breaks its rules: percent steps, the gradient and glow only."""
    found = []
    for step, declarations in _blocks(body):
        if not KEYFRAME_SELECTOR.fullmatch(step):
            found.append(f"{KEYFRAMES}: step {step!r} is not a percentage")
        found += _values_problems(f"{KEYFRAMES} {step}", declarations, KEYFRAME_VALUES)
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


def test_the_title_rule_is_the_only_colour_rule():
    """The title's rule exists once, outside @media, with the gradient and fallback from config."""
    rules = [rule for rule in _rules(_css()) if rule[0] == TITLE_SELECTOR]
    assert len(rules) == 1 and rules[0][2] is None
    values = dict(_declarations(rules[0][1]))
    assert HEX.findall(values["background-image"]) == [c.lower() for c in config.TITLE_GRADIENT]
    assert values["color"] == config.TITLE_FALLBACK.lower()
    assert values["-webkit-text-fill-color"] == "transparent"


def _luminance(colour: str) -> float:
    """Return a hex colour's relative luminance (WCAG 2)."""
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    """Return the WCAG contrast ratio of two hex colours."""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("colour", [*config.TITLE_GRADIENT, config.TITLE_FALLBACK])
def test_every_title_colour_is_readable_in_both_modes(mode, colour):
    """Each gradient stop and the fallback reach 3:1 (large text) on the mode's background."""
    theme = tomllib.loads((config.PROJECT_ROOT / ".streamlit" / "config.toml").read_text("utf-8"))
    background = theme["theme"][mode]["backgroundColor"]
    assert _contrast(colour, background) >= MIN_TITLE_CONTRAST


@pytest.mark.parametrize(
    "css",
    [
        ".st-key-app_title h1 { color: #ff0000; }",
        ".st-key-app_title h1 { background-image: linear-gradient(90deg, #127a5f, #ff00ff); }",
        ".st-key-app_title h1 { background-image: url(x.png); }",
        ".st-key-app_title h1 { position: absolute; }",
        ".st-key-app_title h1 { font-size: 99px; }",
        ".st-key-app_title h1 { font-size: 99rem; }",
        ".st-key-other h1 { color: #127a5f; }",
        "@media (max-width: 640px) { .st-key-app_title h1 { font-size: 2rem; } }",
    ],
)
def test_the_check_refuses_anything_else_in_the_title_rule(css):
    """Another colour, a load, another property or unit, another selector or a media rule fail."""
    assert problems(css)


def test_the_menu_rule_sets_only_a_font_size():
    """The page menu's rule exists once and sets only its font size (T9.5, owner's choice)."""
    rules = [rule for rule in _rules(_css()) if rule[0] == NAV_SELECTOR]
    assert len(rules) == 1 and rules[0][2] is None
    assert [prop for prop, _ in _declarations(rules[0][1])] == ["font-size"]


@pytest.mark.parametrize(
    "css",
    [
        f"{NAV_SELECTOR} {{ color: #127a5f; }}",
        f"{NAV_SELECTOR} {{ font-size: 3rem; }}",
        f"{NAV_SELECTOR} {{ font-size: 20px; }}",
        f"{NAV_SELECTOR} {{ display: none; }}",
        '[data-testid="stSidebarNavLink"] { font-size: 1.2rem; }',
        '[data-testid="stMarkdownContainer"] { font-size: 1.2rem; }',
    ],
)
def test_the_check_refuses_anything_else_in_the_menu_rule(css):
    """The menu's rule may set a font size between 1 and 2 rem, nothing else."""
    assert problems(css)


def test_the_title_rule_aims_at_the_header_s_container():
    """The CSS selector names the key views/header.py gives the title, so the gradient applies."""
    from views import header

    assert TITLE_SELECTOR == f".st-key-{header.TITLE_KEY} h1"


def test_the_sign_in_rules_aim_at_the_start_page_s_button():
    """The CSS selector names the key views/account.py gives the sign-in button."""
    from views import account

    assert SIGN_IN_SELECTOR == f".st-key-{account.SIGN_IN_KEY} button"


def test_the_sign_in_button_moves_only_when_motion_is_welcome():
    """The button animates, and the reduced-motion query stops it (T9.5, owner's choice)."""
    rules = {(selector, media): body for selector, body, media in _rules(_css())}
    assert "animation" in dict(_declarations(rules[(SIGN_IN_SELECTOR, None)]))
    assert _declarations(rules[(SIGN_IN_SELECTOR, REDUCED_MOTION)]) == [("animation", "none")]
    assert KEYFRAMES in [prelude for prelude, _ in _blocks(_without_comments(_css()))]


@pytest.mark.parametrize("colour", config.TITLE_GRADIENT)
def test_the_sign_in_label_is_readable_on_every_gradient_stop(colour):
    """White label text reaches 3:1 (large bold text) on each colour the gradient passes."""
    assert _contrast(SIGN_IN_TEXT, colour) >= MIN_TITLE_CONTRAST


@pytest.mark.parametrize(
    "css",
    [
        f"{SIGN_IN_SELECTOR} {{ color: #000000; }}",
        f"{SIGN_IN_SELECTOR} {{ background-image: linear-gradient(90deg, #0f7f8c, #ff00ff); }}",
        f"{SIGN_IN_SELECTOR} {{ position: fixed; }}",
        f"{SIGN_IN_SELECTOR} {{ filter: drop-shadow(0 0 1rem #ff00ff); }}",
        f"{SIGN_IN_SELECTOR} {{ background-image: linear-gradient(100deg, #ffffff, #ffffff); }}",
        f"{SIGN_IN_SELECTOR} {{ filter: drop-shadow(0 0 1rem #ffffff); }}",
        f"{SIGN_IN_SELECTOR} {{ animation: other 6s ease-in-out infinite; }}",
        f"{SIGN_IN_LABEL_SELECTOR} {{ font-size: 0.8rem; }}",
        f"{SIGN_IN_LABEL_SELECTOR} {{ font-weight: 400; }}",
        f"{SIGN_IN_LABEL_SELECTOR} {{ font-size: 25rem; }}",
        "@keyframes other { 0% { background-position: 0% 50%; } }",
        f"{KEYFRAMES} {{ 0% {{ color: #ffffff; }} }}",
        f"{KEYFRAMES} {{ from {{ background-position: 0% 50%; }} }}",
        f"{KEYFRAMES} {{ 50% {{ filter: drop-shadow(0 0 1rem #ff00ff); }} }}",
        f"{KEYFRAMES} {{ 50% {{ filter: drop-shadow(0 0 1rem #ffffff); }} }}",
        f"{REDUCED_MOTION} {{ .st-key-other {{ display: none; }} }}",
        f"{REDUCED_MOTION} {{ {SIGN_IN_SELECTOR} {{ animation: sign-in-glow 1s ease-in-out "
        "infinite; } }",
        f"@media (max-width: {config.PHONE_MAX_WIDTH_PX}px) {{ {SIGN_IN_SELECTOR} "
        "{ border: none; } }",
    ],
)
def test_the_check_refuses_anything_else_in_the_sign_in_rules(css):
    """Another colour, property, step, animation, keyframes name or rule in the query fails."""
    assert problems(css)


def test_the_check_refuses_the_menu_rule_in_a_media_query():
    """The menu's rule holds outside @media only, as the title's does."""
    width = config.PHONE_MAX_WIDTH_PX
    assert problems(f"@media (max-width: {width}px) {{ {NAV_SELECTOR} {{ font-size: 1.2rem; }} }}")
