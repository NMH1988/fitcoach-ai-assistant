"""What the pages start with and how they look: defaults, time zone, sizes, layout, colours."""

# The time zone of the days a user records (D21): a saved weight is dated today in Berlin.
TIME_ZONE = "Europe/Berlin"
# The dashboards (T9.15): the weight trend shows the weights of this many weeks, ending with the
# chosen week's Sunday; each chart is this tall, its axes and legend included.
WEIGHT_TREND_WEEKS = 8
DASHBOARD_CHART_HEIGHT_PX = 240
# Authors named on a source card before "et al." (the full list is in ATTRIBUTION.md).
CARD_AUTHORS_SHOWN = 3
# Characters of the question shown on the sidebar's "Last answer" card before "…" (T3.2).
CARD_QUESTION_CHARS = 60
# Height of the scrolling message area in the Ask tab; tall enough to read a whole answer on a
# desktop screen (owner's requests, 2026-10-20: 520, then 650, then 750 to fill a tall window).
# On a short window the page scrolls to the chat input.
CHAT_HEIGHT_PX = 750
# Most words of the streamed answer shown per second. The real model sends its answer in fast
# bursts, which looked as if it appeared all at once (owner's request, 2026-10-20). 20 read too
# slowly in the owner's check; at 30 a 200-word answer takes about 7 s. 0 shows the text as it
# arrives.
ANSWER_WORDS_PER_SECOND = 30
# The page uses the wide layout with the content in the middle column: these are the relative
# widths of the left margin, the content and the right margin. The content takes about three
# quarters of a large screen, without lines too long to read.
PAGE_COLUMN_WEIGHTS = (1, 6, 1)
# The units the profile form and the sidebar start in; the user can switch to imperial.
DEFAULT_UNIT_SYSTEM = "metric"
# The language a session starts in (owner's choice, 2026-11-02: English for everyone; from T7.1 to
# T9.5 it followed the browser's locale); the user can switch to German.
DEFAULT_LANGUAGE = "en"
# The app's title (T9.5, owner's choices of 2026-11-02: the start page's, then every page's): the
# one rule of app.css that may set
# colour, a teal-to-green gradient around the theme's greens, every stop at least 3:1 (large text)
# on both modes' backgrounds, with a solid fallback (tests/test_stylesheet.py checks both).
TITLE_GRADIENT = ("#0F7F8C", "#1D9E75", "#4E9A28")
TITLE_FALLBACK = "#168563"
# The widest screen the stylesheet treats as a phone: each @media (max-width: Npx) in it uses this
# value (tests/test_stylesheet.py). Streamlit 1.66 stacks st.columns below 640 px; a tablet (about
# 820 px) keeps the desktop layout. T9.15's client cards use it.
PHONE_MAX_WIDTH_PX = 640
# Height of the macro chart in "Tool results", its axis and legend included: at 140 px the bar was a
# hairline in the browser, at 220 px it is drawn clearly (checked with a fake model, T4.4).
MACRO_CHART_HEIGHT_PX = 220
# The donut of the energy split in the sidebar's My targets card (T4.7): its height with the legend,
# the hole for the daily kcal, and the gap between the parts (radians).
MACRO_DONUT_HEIGHT_PX = 150
MACRO_DONUT_INNER_RADIUS_PX = 46
MACRO_DONUT_PAD_ANGLE = 0.03
# The amount the Food lookup tab starts with, and its +/- step, in grams (T4.7).
FOOD_LOOKUP_DEFAULT_GRAMS = 100.0
FOOD_LOOKUP_STEP_GRAMS = 10.0
# Macro colours in charts (docs/UI_DESIGN.md), in the order the macros are listed. One palette for
# both modes: each has at least 3:1 contrast on the main and sidebar backgrounds of the light and
# the dark theme (WCAG 1.4.11; tests/test_theme.py), so they differ by hue, not lightness (T4.7).
MACRO_COLORS: dict[str, str] = {
    "Protein": "#168A6C",
    "Carbohydrate": "#7A6FD0",
    "Fat": "#B87318",
}
# The sidebar donut's macro colours (T9.23, owner's choice, 2026-10-31): the palette above cannot
# keep 3:1 on the deep green sidebar (protein is 2.1:1 on its light-mode secondary background), so
# the donut uses the dark theme's green, violet and orange, which keep it on both sidebar
# backgrounds in both modes (tests/test_theme.py). The same hue per macro as MACRO_COLORS.
SIDEBAR_MACRO_COLORS: dict[str, str] = {
    "Protein": "#5DCAA5",
    "Carbohydrate": "#AFA9EC",
    "Fat": "#EF9F27",
}
