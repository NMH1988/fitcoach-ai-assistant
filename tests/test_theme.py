"""Tests for the light and dark themes, the brand sidebar (T9.23) and the toolbar setting (T7.3)."""

import re
import tomllib
from pathlib import Path

import pytest

from src import config

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".streamlit" / "config.toml"
UI_DESIGN = ROOT / "docs" / "UI_DESIGN.md"

MODES = ("light", "dark")
CORE_COLOURS = ("primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor")
HEX_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}")
# WCAG 2.x level AA for body text.
MIN_TEXT_CONTRAST = 4.5
# Streamlit 1.66 draws st.caption in the text colour at this opacity (checked in the browser, T7.3).
CAPTION_OPACITY = 0.6
# White text on the primary button: AA in light mode; in dark mode the owner kept #1D9E75 at 3.4:1
# (WCAG's 3:1 for interface parts), as a darker green fails AA for the accent text instead (T7.3).
MIN_BUTTON_TEXT_CONTRAST = {"light": MIN_TEXT_CONTRAST, "dark": 3.0}
# WCAG 2.x 1.4.11 (non-text contrast) for the parts of a chart (T4.7).
MIN_GRAPHIC_CONTRAST = 3.0


def _config() -> dict:
    """Parse the app's Streamlit config file."""
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def _documented_theme() -> dict:
    """Parse the TOML block under "## Theme" in docs/UI_DESIGN.md."""
    doc = UI_DESIGN.read_text(encoding="utf-8")
    section = doc.split("## Theme", 1)[1]
    block = re.search(r"```toml\n(.*?)```", section, re.DOTALL)
    assert block, "docs/UI_DESIGN.md has no TOML block under '## Theme'"
    return tomllib.loads(block.group(1))


def _luminance(colour: str) -> float:
    """Return the WCAG relative luminance of a #RRGGBB colour."""
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    """Return the WCAG contrast ratio of two #RRGGBB colours."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _blend(colour: str, background: str, opacity: float) -> str:
    """Return the #RRGGBB colour seen when a colour at this opacity covers the background."""
    channels = [
        round(int(colour[i : i + 2], 16) * opacity + int(background[i : i + 2], 16) * (1 - opacity))
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02X}" for c in channels)


def test_the_contrast_helper_matches_known_ratios():
    """Black on white is 21:1 and a colour on itself is 1:1, as WCAG defines them."""
    assert _contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert _contrast("#0F6E56", "#0F6E56") == pytest.approx(1.0)


def test_the_blend_helper_mixes_colours_by_opacity():
    """Full opacity keeps the colour, zero keeps the background, half is the midpoint."""
    assert _blend("#000000", "#FFFFFF", 1.0) == "#000000"
    assert _blend("#000000", "#FFFFFF", 0.0) == "#FFFFFF"
    assert _blend("#000000", "#FFFFFF", 0.5) == "#808080"


def test_the_config_defines_both_modes():
    """The config has a light and a dark theme section, so the menu offers Light, Dark, System."""
    theme = _config()["theme"]
    for mode in MODES:
        assert mode in theme, f"[theme.{mode}] is missing"


def test_the_themes_match_the_ui_design_doc():
    """Every theme value in the config is the one docs/UI_DESIGN.md documents, and no more."""
    assert _config()["theme"] == _documented_theme()["theme"]


@pytest.mark.parametrize("mode", MODES)
def test_each_mode_sets_the_core_colours_as_hex(mode):
    """Each mode sets the accent, both backgrounds and the text colour as #RRGGBB."""
    colours = _config()["theme"][mode]
    for name in CORE_COLOURS:
        assert HEX_COLOUR.fullmatch(colours[name]), f"theme.{mode}.{name} = {colours.get(name)!r}"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", ["backgroundColor", "secondaryBackgroundColor"])
def test_text_is_readable_on_both_backgrounds(mode, background):
    """Body text meets WCAG AA contrast on the main and the sidebar background in each mode."""
    colours = _config()["theme"][mode]
    assert _contrast(colours["textColor"], colours[background]) >= MIN_TEXT_CONTRAST


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", ["backgroundColor", "secondaryBackgroundColor"])
def test_captions_are_readable_on_both_backgrounds(mode, background):
    """Captions (text colour at 60% opacity) meet WCAG AA on both backgrounds in each mode."""
    colours = _config()["theme"][mode]
    caption = _blend(colours["textColor"], colours[background], CAPTION_OPACITY)
    assert _contrast(caption, colours[background]) >= MIN_TEXT_CONTRAST


@pytest.mark.parametrize("mode", MODES)
def test_white_button_text_is_readable_on_the_primary_colour(mode):
    """White text on the primary button meets AA in light mode and the documented 3:1 in dark."""
    primary = _config()["theme"][mode]["primaryColor"]
    assert _contrast("#FFFFFF", primary) >= MIN_BUTTON_TEXT_CONTRAST[mode]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", ["backgroundColor", "secondaryBackgroundColor"])
def test_accent_text_is_readable_on_both_backgrounds(mode, background):
    """Text in the primary colour (a selected option) meets AA on both backgrounds in each mode."""
    colours = _config()["theme"][mode]
    assert _contrast(colours["primaryColor"], colours[background]) >= MIN_TEXT_CONTRAST


def test_the_toolbar_keeps_the_theme_switch():
    """toolbarMode keeps the theme switch and hides developer options from remote visitors."""
    # "minimal" hides the switch; "developer" would show Rerun and Clear cache (which drops the
    # cached index and clients for everyone) to every visitor of a deployed app.
    assert _config()["client"]["toolbarMode"] in {"auto", "viewer"}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", ["backgroundColor", "secondaryBackgroundColor"])
@pytest.mark.parametrize("macro", list(config.MACRO_COLORS))
def test_macro_colours_stand_out_on_both_backgrounds(mode, background, macro):
    """Each macro colour has 3:1 against both main backgrounds in each mode (T4.7)."""
    # One palette for both modes: the charts cannot follow a theme switch reliably in Streamlit
    # 1.66 (st.context.theme can be wrong right after one), so each colour works on all four.
    colours = _config()["theme"][mode]
    colour = config.MACRO_COLORS[macro]
    assert HEX_COLOUR.fullmatch(colour)
    assert _contrast(colour, colours[background]) >= MIN_GRAPHIC_CONTRAST


def test_the_macro_colours_match_the_ui_design_doc():
    """docs/UI_DESIGN.md names the macro colours the charts use."""
    doc = UI_DESIGN.read_text(encoding="utf-8")
    line = next(line for line in doc.splitlines() if line.startswith("Macro colours"))
    for macro, colour in config.MACRO_COLORS.items():
        assert f"{macro.lower()} `{colour}`" in line


# --- The brand sidebar (T9.23) -----------------------------------------------------------------

SIDEBAR_BACKGROUNDS = ["backgroundColor", "secondaryBackgroundColor"]
SIDEBAR_COLOURS = (
    "primaryColor",
    *SIDEBAR_BACKGROUNDS,
    "textColor",
    "borderColor",
    "blueColor",
    "blueTextColor",
)


def _sidebar(mode: str) -> dict:
    """Return the sidebar's colours in this mode."""
    return _config()["theme"][mode]["sidebar"]


@pytest.mark.parametrize("mode", MODES)
def test_each_mode_sets_the_sidebar_colours_as_hex(mode):
    """Both modes set the sidebar's accent, backgrounds, text, border and blues as #RRGGBB."""
    colours = _sidebar(mode)
    for name in SIDEBAR_COLOURS:
        assert HEX_COLOUR.fullmatch(colours[name]), f"theme.{mode}.sidebar.{name}"


@pytest.mark.parametrize("mode", MODES)
def test_the_sidebar_is_deep_green_with_light_text(mode):
    """A dark green background (green the strongest channel) under a light text colour."""
    colours = _sidebar(mode)
    red, green, blue = (int(colours["backgroundColor"][i : i + 2], 16) for i in (1, 3, 5))
    assert green > max(red, blue)
    assert _luminance(colours["backgroundColor"]) < 0.05 < 0.8 < _luminance(colours["textColor"])


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", SIDEBAR_BACKGROUNDS)
def test_sidebar_text_is_readable_on_both_sidebar_backgrounds(mode, background):
    """Sidebar text meets WCAG AA on the sidebar's background and its widgets' background."""
    colours = _sidebar(mode)
    assert _contrast(colours["textColor"], colours[background]) >= MIN_TEXT_CONTRAST


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", SIDEBAR_BACKGROUNDS)
def test_sidebar_captions_are_readable_on_both_sidebar_backgrounds(mode, background):
    """Sidebar captions (its text at 60% opacity) meet WCAG AA on both sidebar backgrounds."""
    colours = _sidebar(mode)
    caption = _blend(colours["textColor"], colours[background], CAPTION_OPACITY)
    assert _contrast(caption, colours[background]) >= MIN_TEXT_CONTRAST


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", SIDEBAR_BACKGROUNDS)
def test_sidebar_accent_text_is_readable_on_both_sidebar_backgrounds(mode, background):
    """The sidebar's primary as text (the goal's and the language's selected option) meets AA."""
    colours = _sidebar(mode)
    assert _contrast(colours["primaryColor"], colours[background]) >= MIN_TEXT_CONTRAST


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("background", SIDEBAR_BACKGROUNDS)
@pytest.mark.parametrize("macro", list(config.SIDEBAR_MACRO_COLORS))
def test_sidebar_macro_colours_stand_out_on_both_sidebar_backgrounds(mode, background, macro):
    """Each colour of the sidebar's donut has 3:1 on both sidebar backgrounds in each mode."""
    colour = config.SIDEBAR_MACRO_COLORS[macro]
    assert HEX_COLOUR.fullmatch(colour)
    assert _contrast(colour, _sidebar(mode)[background]) >= MIN_GRAPHIC_CONTRAST


# Streamlit 1.66 fills a badge in the sidebar with its colour at this opacity, in both modes, as it
# treats the deep green sidebar as dark (measured in the browser, T9.23).
BADGE_FILL_OPACITY = 0.2


@pytest.mark.parametrize("mode", MODES)
def test_sidebar_blue_badges_are_readable(mode):
    """The last answer's filter badges: blue text meets AA on its blue fill in the sidebar."""
    colours = _sidebar(mode)
    fill = _blend(colours["blueColor"], colours["backgroundColor"], BADGE_FILL_OPACITY)
    assert _contrast(colours["blueTextColor"], fill) >= MIN_TEXT_CONTRAST


@pytest.mark.parametrize("mode", MODES)
def test_the_selected_option_is_readable_on_its_tint(mode):
    """A selected option is the primary on the primary at 10% over the sidebar (browser, T9.23)."""
    colours = _sidebar(mode)
    tint = _blend(colours["primaryColor"], colours["backgroundColor"], 0.1)
    assert _contrast(colours["primaryColor"], tint) >= MIN_TEXT_CONTRAST


def test_the_sidebar_palette_names_the_same_macros_in_the_same_order():
    """The donut's palette covers exactly the macros of the main palette, in its order."""
    assert list(config.SIDEBAR_MACRO_COLORS) == list(config.MACRO_COLORS)


def test_the_main_palette_cannot_keep_3_to_1_on_the_sidebar():
    """Why the donut has its own palette: protein fails 3:1 on the light sidebar (T9.23)."""
    light = _sidebar("light")
    assert _contrast(config.MACRO_COLORS["Protein"], light["secondaryBackgroundColor"]) < 3.0


def test_the_sidebar_macro_colours_match_the_ui_design_doc():
    """docs/UI_DESIGN.md names the sidebar donut's colours."""
    doc = UI_DESIGN.read_text(encoding="utf-8")
    line = next(line for line in doc.splitlines() if line.startswith("Sidebar donut colours"))
    for macro, colour in config.SIDEBAR_MACRO_COLORS.items():
        assert f"{macro.lower()} `{colour}`" in line
