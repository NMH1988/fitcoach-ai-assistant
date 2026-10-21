# UI design

How the Streamlit app looks and where each piece of information lives. Accepted by the owner on 2026-10-19 as the working design (mockup v5, `docs/ui/mockup-v5.html`); it may change later. Built with Streamlit 1.66 native elements and `.streamlit/config.toml`, not custom CSS.

**Serves:** core 5 (intuitive UI that shows sources, tool results and progress), Medium 5 and 6, AC-1, AC-3, AC-6, AC-10. Colours, the empty-state suggestions and other visual polish are beyond the brief (owner's request) and belong to the extras group in `docs/IMPLEMENTATION_PLAN.md`.

## Principles

- **The chat comes first.** The Ask tab shows only what a user needs to read an answer: the answer, its sources and its tool result. Everything else is one tab away.
- **One accent colour** (teal-green) on a neutral base; one primary button per view.
- **Readable text:** body 17 px (Streamlit's default is 16 px); captions for labels and meta lines. The owner found 14 px too small to read in the chat (2026-10-20, T3.1).
- **Native first:** `st.chat_message`, `st.metric`, `st.badge`, `st.tabs`, `st.status`, `st.dialog`. No `unsafe_allow_html`, no `st.html` styling. If a detail of the mockup needs CSS, the native look wins.
  - **One exception (owner's approval, T4.6, 2026-10-20):** inside the "Your details" dialog, `st.html(config.PROFILE_DIALOG_CSS)` hides Streamlit's in-field "Press Enter to apply" (`[data-testid="InputInstructions"]`, scoped to `[data-testid="stDialog"]`), and the dialog's first line is the hint `config.PROFILE_FORM_HINT` ("Type your values, then press Save. Values are checked when you save."). Why: the text inside the field looked wrong; Streamlit 1.66 hides it only inside `st.form(enter_to_submit=False)`, and the dialog is not a form so the units switch can convert typed values. A typed number is applied when the field loses focus, so Save right after typing keeps it (checked in the browser, metric and imperial). The style is drawn only while the dialog is open (a style-only `st.html` goes to Streamlit's event container and takes no space). Risk: a later Streamlit may rename the test id; the text would then come back and nothing would break. No other custom CSS.
- **Sentence case**, Material Symbols icons (`:material/name:`), no emoji in the UI.

## Theme (`.streamlit/config.toml`)

```toml
[theme]
font = "sans-serif"          # system font; no Google Fonts request (visitors' IPs are not sent to Google)
baseFontSize = 17
baseRadius = "0.5rem"
buttonRadius = "0.5rem"
showWidgetBorder = true
showSidebarBorder = true
metricValueFontSize = "1.25rem"
linkUnderline = false

[theme.light]
primaryColor = "#0F6E56"     # teal-green, dark enough for white button text (WCAG AA)
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F4F6F5"
textColor = "#14171B"        # dark enough that captions (60% opacity) meet WCAG AA (T7.3)
borderColor = "#D8DEDB"
greenColor = "#0F6E56"
orangeColor = "#BA7517"
violetColor = "#534AB7"

[theme.dark]
primaryColor = "#1D9E75"
backgroundColor = "#0F1412"
secondaryBackgroundColor = "#18201D"
textColor = "#E6EDEA"
borderColor = "#2C3633"
greenColor = "#5DCAA5"
orangeColor = "#EF9F27"
violetColor = "#AFA9EC"
```

Both `[theme.light]` and `[theme.dark]` are set, so users keep the light/dark toggle. Exact hex values may be tuned when the theme is built; check contrast in both modes.

Macro colours (charts, set in the Vega-Lite spec): protein `#168A6C`, carbohydrate `#7A6FD0`, fat `#B87318`. One palette for both modes (owner's choice in T4.7, 2026-10-20): each colour has at least 3:1 contrast against the main and the sidebar background in light and dark mode (WCAG 1.4.11 for graphics; `tests/test_theme.py`), so they differ by hue, not lightness. The charts cannot follow a theme switch reliably (`st.context.theme` may be wrong right after one in Streamlit 1.66), so no per-theme shades. The values are always also shown as text. Neighbouring colours differ by hue, not lightness (about 1.1:1 between them), so the donut has gaps between its parts; in the stacked bars the parts touch, and the legend and the values in text tell them apart. The first palette (protein `#0F6E56`, carbohydrate `#5DCAA5`, fat `#EF9F27`) fell to 2.0:1 (carbohydrate) and 2.2:1 (fat) on the light background (T4.4).

## Page layout

`st.set_page_config(page_title="Nutrition AI Assistant", page_icon=":material/nutrition:", layout="wide")`, with the header and tabs in the middle of three columns weighted `PAGE_COLUMN_WEIGHTS` = (1, 6, 1). The content takes about three quarters of the main area (about 1,050 px on a 1920 px screen with the sidebar open, instead of about 700 px with the centered layout) without lines too long to read; on a laptop it is about as wide as before (owner's request, 2026-10-20, T3.1).

### Sidebar: the profile

| Element | Streamlit | Notes |
|---|---|---|
| "Your profile" heading | `st.header` with `:material/person:` | Larger than `st.subheader` (owner's request, 2026-10-20) |
| Goal | `st.segmented_control` (Build muscle / Lose fat / Maintain, with icons), `width="stretch"` | Changing it recalculates the targets |
| Weight, height, age, sex | `st.columns(2)` of `st.metric(..., border=True)` | Values large, labels small; shown in the chosen units |
| Activity | `st.metric(..., border=True)` full width | e.g. "Moderate · 4-5 times" |
| Edit details | `st.button("Edit details", icon=":material/edit:", width="stretch")` | Opens the profile form in an `st.dialog` (owner's choice in T4.1): a Metric / Imperial switch, then plain inputs and a Save button, not an `st.form`, so switching units converts the values already typed. Validation messages come from `src/profile.py` |
| Daily target | `st.metric("Daily target", "3,035 kcal", border=True)`, after Edit details | Always visible, whatever tab is open; built in T4.7 (split from T4.4 by the owner on 2026-10-20). Computed on every run from the session profile with `registry.macro_targets()`, the same function the macro tool uses, so it follows the goal control at once and makes no model call |
| My targets (summary card) | `st.container(border=True)`: "My targets", a donut of the energy split (`st.vega_lite_chart`, an `arc` mark with `innerRadius`, gaps between the parts, `MACRO_DONUT_HEIGHT_PX` = 150 with the legend on its right) with the daily kcal in the middle, then one caption per macro ("**Protein** 152 g · 20% · 1.9 g/kg", g/lb in imperial), a warning line when protein was lowered, and "More in the My targets tab." | The full view stays in the My targets tab. One donut, not one circle per value: the three macros are parts of the kcal total, and kcal is the total, not a fourth part. Text values carry the numbers, as angles are harder to compare than lengths and colour is never the only signal. Owner's choice, 2026-10-20 (built in T4.7). The lines sit under the donut, not beside it: the sidebar is too narrow for both. Streamlit's chart theme colours axes and legends but leaves text marks black (unreadable in dark mode), so the kcal in the middle uses `currentColor`, which follows the page's text colour, even right after a theme switch (checked in the browser) |
| Privacy note | `st.caption(":material/lock: Kept for this session only")` | |
| Light or dark mode hint | `st.caption(config.THEME_HINT)` | Right after the privacy note (T7.3; its tests check the order) |
| Download summary (PDF) | `st.download_button(config.PDF_BUTTON_LABEL, icon=":material/download:", width="stretch", on_click="ignore")` with `data` as a function | After the theme hint, before the last answer card (owner's choice in T5.2, 2026-10-20: always in view, whatever tab is open). Off, with the help "Add your details or ask a question first.", until the session has a profile or a question. The PDF is built only on a click, from the session as it stands after the turn that just ran (its `st.empty()` slot is filled after the main area, like the card's); file name `nutrition-summary-YYYY-MM-DD.pdf`. Screenshot (fake model): `docs/ui/t5.2-download-button.jpg`; the PDF itself: `docs/ui/t5.2-summary-pdf.jpg` |
| Details, last answer (summary card) | `st.container(border=True)`: "Last answer", how many ways the question was searched ("Searched 4 ways: your question and 3 rewrites.") and the filters as badges, a note when they were dropped (T3.2); the answer's tokens and cost and the session total as two captions with `:material/data_usage:` ("This answer: 3,700 tokens · $0.0074", "Session: 7,400 tokens · $0.0148", with "+ price unknown" when some turn could not be priced; T5.1). Before any turn has searched (e.g. the first one failed after the rewrite) the session line is shown alone, without the card | The full view stays in the Details tab. Owner's choice, 2026-10-20. Shown once a turn has searched. Its `st.empty()` slot is filled once per run, after the main area, so it shows the turn that just ran: a slot filled twice in one run kept the first draw's extra badges in the browser (AppTest does not show this; found in T3.2's browser check) |
| About the answers | `st.divider`, then `st.expander("About the answers", icon=":material/menu_book:")` (folded since T3.2, when the summary card arrived): three bullets (article count by tier and licence from the manifest, how questions are rephrased and answers cite passages, the rewrite and answer models) and a bold "Sources and credits" heading (Streamlit cannot nest expanders) listing every source with its first three authors, title, year, journal, licence and article link, then the change made and the no-endorsement note (the same text as `ATTRIBUTION.md`) | Fills the empty sidebar and credits the sources (copyright policy rule 6); beyond the brief (owner's request, 2026-10-20) |

Before a profile exists, the sidebar shows a short invitation and the "Add your details" button (same dialog) instead of the tiles.

### Header

App name with icon on the left; `st.badge("Not medical advice", icon=":material/info:", color="orange")` on the right (`st.container(horizontal=True)`). Below it the intro as plain text and the full disclaimer in `st.warning`, starting with a bold "Not medical advice.", so it is large and easy to notice (owner's request, 2026-10-20; a badge's text size is fixed in Streamlit 1.66). Always visible (AC-12). Tab labels are bold; their size is fixed too. Once T7.1 lands, the language control sits at the far right of the badge row (see "Language").

### Language (T7.1, T7.2, extra)

- **Control:** at the right end of the header row, a small `:material/translate:` icon (`st.markdown`) followed by `st.segmented_control(label="Language", options=["EN", "DE"], key="language", required=True, label_visibility="collapsed")`, both in the header's `st.container(horizontal=True)`. `required=True` stops a click on the selected option from deselecting it (the value would become `None`). The collapsed label should keep "Language" as the accessible name (to check in the browser's accessibility tree in T7.1).
- **Default:** from the browser (`st.context.locale`): `de*` gives German, anything else (including `None`, as under AppTest) English. It is written to `st.session_state["language"]` once, before the widget is drawn (no `default=` together with the key); after that the user's choice is kept for the session; nothing is stored. T7.1 checks in the browser that `st.context.locale` is already set on a new session's first run.
- **What changes:** every UI string (from `src/i18n.py`, English and German), the disclaimer, error messages, the empty-state suggestions and the answer language. What stays English: source titles, journal names, licence names, USDA food names and the knowledge base itself.
- **Food lookup in German:** a caption under the food input says to enter the food name in English (USDA names are English). In the chat the food tool's description tells the model to pass English names (checked in T7.2).
- **Messages from `src/`** (guard, LLM errors, missing index, profile validation) come back as keys or codes and the UI translates them. Tool notes stay English, so what the UI shows matches what the model received.
- **Answers in German:** the language is passed to the answer step as a fixed value (`en`/`de`), never read from user text. The question is rewritten into English for retrieval (T3.2), so both vector and keyword search match the English chunks. Source passages are summarised, never shown as translated quotes.
- **Safety:** the input guard and the domain guardrails got German patterns and German test strings in T7.4 (split from T7.1, owner's decision, 2026-10-21), merged before the German UI, so a German injection or a German high-risk request is caught like an English one even if T7.2 is cut. Their messages stay English until T7.1.

### Light and dark mode (T7.3, extra)

- Both `[theme.light]` and `[theme.dark]` are defined (see "Theme"; T3.1 writes them, T7.3 adds the config test, the toolbar check and the hint), so Streamlit's own menu (⋮, top right) offers System, Light and Dark at its top. Streamlit 1.66 has no separate Settings entry (seen in the browser, T7.3). The choice is remembered by the browser.
- `[client] toolbarMode = "auto"` in `.streamlit/config.toml`: the switch stays for every visitor; the developer options (Rerun, Clear cache, Deploy) show only on localhost. "minimal" would hide the switch.
- Streamlit 1.66 cannot change the theme from the script, and a custom CSS toggle would break the "native first" principle and break on upgrades, so there is no separate header icon (owner's decision, 2026-10-20).
- A sidebar caption says where to switch: `config.THEME_HINT`, ":material/dark_mode: Light or dark mode: menu :material/more_vert: at the top right" (the icon is the menu's own ⋮). It sits under the privacy note with a profile, and under the "Add your details" button before one exists.
- Badges, source cards, the sidebar and the profile dialog are checked in both modes (T7.3, results in `docs/TESTING.md`); the charts and the tool result table are checked in T4.4. Chart colours come from the palette above, which reads on both backgrounds. `tests/test_theme.py` checks that body text and captions (drawn at 60% opacity) meet WCAG AA on both backgrounds in both modes; that is why the light text colour is #14171B. It also checks white text on the primary button and the primary colour as text on both backgrounds. The 60% caption opacity was measured on Streamlit 1.66: recheck it in the browser after a Streamlit upgrade (`CAPTION_OPACITY` in the test). Known limit (owner's choice): white text on the dark-mode primary button is 3.4:1, as a darker green would make the accent text on the dark background fall under AA instead.

### Session summary PDF (T5.2, extra)

- **Layout** (A4, DejaVu Sans, black on white whatever the app's theme): the title and the date; the disclaimer with a bold "Not medical advice."; "Your profile" as a two-column table in the chosen units; "Your daily targets" from the profile (the same tables as "Tool results", grams per kg or per lb of body weight by the unit system, then the message, the notes and the method); "Questions and answers", numbered, each with its answer, a "Sources" list (labels, title, year, tier, licence, URL, and under a source its correction notice, as on the app's card) and its tool results, or the label and fixed message of a turn with no answer (owner's choice: every turn, as in the chat); "Credits". Every page's footer: the app's name, "Not medical advice" and the page number.
- **Answers as plain text** (owner's choice, 2026-10-20): headings, emphasis and code marks are dropped, list items become bullets (indented by level), a table row becomes its cells joined by " · " (the separator row dropped), a link becomes its text and its URL; code and URLs are kept as written; the `[S#]` labels stay. Nothing in the PDF is a link.
- **Text:** every heading and label is in `export_pdf.TEXT`, `config.STATUS_LABELS` and `registry.TOOL_TITLES` (the last two shared with the app), so T7.2 can add the German version.
- **Credits** end with a "Font" section: DejaVu Sans 2.37 and its licence (the Bitstream Vera and Arev parts of `assets/fonts/LICENSE`) word for word, in small print (owner's choices in the review of PR #54).

### Tabs

`st.tabs([":material/chat: Ask", ":material/target: My targets", ":material/search: Food lookup", ":material/list: Details"])`. Tab bodies are cheap to render; LLM and embedding calls run only when a prompt is submitted, never because a tab is drawn.

#### Ask

- Messages in `st.container(height=...)` so the input stays in view; `st.chat_input("Ask about nutrition for your training")` directly below it, inside the tab (inline, not pinned).
- User messages: `st.chat_message("user")`.
- Assistant messages: `st.chat_message("assistant", avatar=":material/nutrition:")`, containing in order:
  1. **Progress** while the turn runs: `st.status(":shimmer[Searching sources]", type="compact")` with `type="step"` children (check input, rewrite question, search sources, answer, tools). Collapses to a static label when done (core 5). Each step holds a one-line caption on what it does: in Streamlit 1.66 a step without content ends the timeline and hides the steps after it (found in T3.1). Past turns show the same collapsed status.
  2. **Answer** as Markdown with `[S#]` citations (no `unsafe_allow_html`), streamed in under the status box as the model writes it, revealed word by word at most `ANSWER_WORDS_PER_SECOND` (30) so it reads at a steady pace even when the model sends it in bursts, then replaced by the full result (owner's requests in T3.1).
  3. **Sources:** one `st.container(border=True)` per cited source: bold title, a caption with the first three authors and "et al." (owner's choice in T3.1, for the CC BY credit), `st.badge` for the evidence tier (green "ISSN position stand", violet "Peer-reviewed review"), caption with journal, year and licence, and a link "Open article" (AC-1).
  4. **Tool results:** one expander "Tool results (n)" with `:material/calculate:`, like "Sources (n)" (owner's choice in T4.4, 2026-10-20, instead of one expander per result labelled with its headline). Inside, each result under a bold heading (Daily energy needs, Daily targets, Food lookup, Meal plan check, or "Tool call not run") with its values in `st.dataframe` tables (AC-6); macro targets also as a horizontal stacked bar of the kcal from each macro (`st.vega_lite_chart` with a spec, so the value axis starts at 0; macro colours; `alt=` text naming every value; the values are also in the table above it), and a food lookup with "Source: USDA FoodData Central". Tables use `st.dataframe`, never `st.table`, which reads Markdown in its cells in Streamlit 1.66, so a USDA name stays plain text. Without a profile, an energy result says the details are needed (`st.info`) with an "Add your details" button that opens the profile dialog. Tool messages are the English text the model got. Screenshot (fake model, sample values): `docs/ui/t4.4-tool-results.jpg`. **Meal plan check (T4.5):** two `st.dataframe` tables, no chart (owner's choice): the foods (name asked for, USDA match or "Not found", amount, kcal, protein, carbohydrate, fat, fiber, other close USDA names; the name columns capped at "medium" width, full text on hover, so a long name does not push the values out of view) and the plan against the daily targets (plan total, daily target, the difference in words, "Below/Within/Above" the sources' range for kcal and protein; fiber with "No target"); then the result message, the notes (`:material/info:`) and the USDA source line. Screenshot (fake model, sample values): `docs/ui/t4.5-meal-plan-check.jpg`.
  5. **Usage (T5.1, AC-10):** one `st.caption` with `:material/data_usage:`, the turn's tokens and cost over all its calls ("3,700 tokens · $0.0074"; "<$0.0001" below a hundredth of a cent; "price unknown" when OpenRouter's prices could not be read). It has its own `st.empty()` slot under the answer, filled once the turn is priced, after the answer is shown. Also under an error that came after a model call (what it spent); none for a question the guard stopped. Screenshot (fake models, live prices): `docs/ui/t5.1-answer-and-card.jpg`.
- **Empty chat:** a one-line invitation and three suggested questions as `st.pills` in an `st.empty()` placeholder, sent through the same handler as typed input; hidden once the chat has a message.
- **Errors:** a short `st.error` inside the assistant message saying what happened and what to do; the history stays (AC-13).
- **Guard rejections:** `st.warning` with `:material/block:`; the status ends as an error, "Question not accepted".
- **Domain guardrails (T5.3, AC-12):** a refused or redirected question gets its fixed message in `st.info` with `:material/health_and_safety:` and no answer; the status ends complete, "Not something this assistant can advise on", since nothing went wrong.

#### My targets

Built in T4.7. Screenshots (fake model, sample profile): `docs/ui/t4.7-my-targets-light.jpg`, `docs/ui/t4.7-my-targets-dark.jpg`.

- Four `st.metric(border=True)` in one row: daily kcal, with the surplus or deficit as a short grey delta ("+276 kcal", `delta_color="off"`: a deficit for fat loss is the plan, not a warning; a longer delta was cut off in a quarter of the tab), and protein, carbohydrate and fat in grams. Under each, a caption: the goal and the distance from maintenance ("Build muscle: 276 kcal above maintenance"), or the macro's % of the kcal and its grams per body weight (g/kg, or g/lb in imperial). Visible captions rather than help text, so the values are always on screen.
- When protein was lowered to fit the target (very heavy body, low target), an `st.warning` right under the metrics with the note and the sources' protein range for this weight ("480-660 g a day (1.6 g/kg to 2.2 g/kg)").
- The horizontal stacked bar of the macro split, the same chart as in "Tool results" (`_macro_bar()`), with `alt=`.
- Captions: maintenance kcal with how it was calculated, the target's message, any other note (e.g. the calorie floor), and the sources as a list.
- Without a profile: an invitation and the "Add your details" button (the same dialog).

#### Food lookup

Built in T4.7. Screenshot: `docs/ui/t4.7-food-lookup.jpg`.

- `st.text_input` for the food (at most `FOOD_MAX_NAME_CHARS`) and `st.number_input` for grams (`FOOD_MIN_GRAMS` to `FOOD_MAX_GRAMS`, 100 to start), side by side with `vertical_alignment="bottom"`, and a "Look up" button (the tab's primary button). A caption says the table holds single, unprocessed foods named in English.
- The lookup is `registry.run_food_lookup()`: the tool's own schema check and fixed messages, with no model and no API call, so it does not go through the input guard or count in the rate limit. The last result is kept in the session, so it stays while other widgets rerun the page.
- Result: "Matched USDA food, 80 g:", the USDA name with `st.text` (plain text), four metrics (energy, protein, carbohydrate, fat), fibre in a caption ("not reported" when USDA has no value), close alternatives in a plain-text table, and "Source: USDA FoodData Central, Foundation Foods (CC0)".
- Not found: the fixed message in `st.info` and the close names in a "Did you mean" `st.dataframe`, not `st.pills` as first planned: pill labels read Markdown, and USDA names stay out of labels (owner's choice in T4.7). Invalid input gives the fixed message in `st.warning`; a missing foods table the fixed error.

#### Details (for the last answer)

- **How this answer was found:** for the last turn that searched, "Searched for" as a numbered list (the question, marked "your question", then the rewrites; both escaped, on one line each) and "Filters" as blue `st.badge`s ("Protein", "From 2021", "ISSN position stands only"), or a grey "No filters" badge; a caption when only the question was searched (the rewrite step gave nothing usable) or when the filters were dropped (nothing close enough passed them). Before any question, an invitation (AC-3, T3.2).
- **Tokens and cost** (T5.1, AC-10, Medium 5): a subheader with `:material/data_usage:`, then an `st.dataframe` with one row per call of the last answer that searched (step, model, input tokens, cached input, output tokens, reasoning, cost: "Rewrite the question", "Embed the searches", "Answer, round 1"...), then "**This answer:**" and "**This session:**" lines and a caption: costs are priced on the input and output tokens with OpenRouter's prices, read once a day; reasoning is shown as reported, not priced again, and can be higher than the output count; what "price unknown" means. A table rather than metrics: up to six calls with five numbers each. Screenshot: `docs/ui/t5.1-details-usage.jpg`.

## Text

- App text is English, sentence case, no "please", no exclamation marks. After T7.1 every string also has a German version in `src/i18n.py`; German text uses the formal "Sie".
- Errors say what happened and what to do next ("Your API key is missing. Add it to `.streamlit/secrets.toml`.").
- Empty states invite an action ("Add your details to get personal targets").

## Accessibility

- `alt=` on every chart and table.
- Colour is never the only signal: badges carry text, deltas carry a sign.
- Contrast checked in light and dark mode.

## Built in which ticket

| Piece | Ticket |
|---|---|
| Theme file, page config, header, tabs skeleton | T3.1 (core); T4.1 already sets `metricValueFontSize`, which the sidebar tiles need |
| Sidebar goal control, profile tiles, Edit details dialog, units | T4.1 (core) |
| Sidebar daily target, My targets summary card with the macro donut | T4.7 (core; split from T4.4), done |
| Sidebar Details summary card | T3.2 (rewrites and filters), T5.1 (usage) |
| Sidebar "About the answers" block | T3.1 (beyond the brief, owner's request); folded into an expander once the summary cards arrive, so the sidebar does not grow too long (owner's choice, 2026-10-20) |
| Chat messages, progress steps, source cards | T3.1 (core) |
| Details tab: rewrites and filters | T3.2 (core) |
| Tool results expander in the chat, with tables and the macro bar | T4.4 (core) |
| Meal plan check in the Tool results expander | T4.5 (extra tool) |
| My targets tab | T4.7 (core; split from T4.4), done |
| Food lookup tab | T4.7 (core; split from T4.4), done |
| Details tab: usage | T5.1 (extra) |
| Sidebar "Download summary (PDF)" button and the PDF's layout | T5.2 (extra) |
| Light and dark mode hint, both themes checked | T7.3 (extra) |
| German guard and guardrail patterns | T7.4 (extra) |
| Language control, German UI text | T7.1 (extra) |
| German answers, English rewrites for retrieval | T7.2 (extra) |
| Empty-state suggestions, colour tuning, final polish | UI polish ticket (extra, beyond the brief, owner's request) |

## Open questions

- Height of the message container: `CHAT_HEIGHT_PX` = 750 (owner's requests, 2026-10-20: 650, then 750 to fill a tall window), which keeps the input in view in a 1200 px window (checked: the input ends at 1030 px); on a shorter window the page scrolls to the input. Streamlit has no height relative to the window, and it advises at most 500 px for phones: revisit in the UI polish ticket.
- Whether `baseFontSize = 17` and the wide layout read well on a phone: check during the UI polish ticket. At 17 px the sidebar goal control wraps "Maintain" onto a second line (checked 2026-10-20).
