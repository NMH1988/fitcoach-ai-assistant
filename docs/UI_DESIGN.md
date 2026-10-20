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
textColor = "#1F2328"
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

Macro colours (charts, set in the Altair spec): protein `#0F6E56`, carbohydrate `#5DCAA5`, fat `#EF9F27`.

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
| Daily target | `st.metric("Daily target", "3,010 kcal", border=True)` | Always visible, whatever tab is open; added with the targets (T4.4) |
| My targets (summary card) | `st.container(border=True)`: a donut of the energy split (protein, carbohydrate, fat; Altair `mark_arc` with an inner radius, about 120-140 px) with the daily kcal in the middle, and each macro's grams and % as text beside it | The full view stays in the My targets tab. One donut, not one circle per value: the three macros are parts of the kcal total, and kcal is the total, not a fourth part. Text values carry the numbers, as angles are harder to compare than lengths and colour is never the only signal. Owner's choice, 2026-10-20 (T4.4) |
| Details, last answer (summary card) | `st.container(border=True)`: the number of rewrites and the filters as badges (T3.2), the answer's tokens and cost and the session total (T5.1) | The full view stays in the Details tab. Owner's choice, 2026-10-20 |
| Privacy note | `st.caption(":material/lock: Kept for this session only")` | |
| About the answers | `st.divider`, `st.header(":material/menu_book: About the answers")`, three bullets (article count by tier and licence from the manifest, how answers cite passages, the answer model) and a "Sources and credits" expander listing every source with its first three authors, title, year, journal, licence and article link, then the change made and the no-endorsement note (the same text as `ATTRIBUTION.md`) | Fills the empty sidebar and credits the sources (copyright policy rule 6); beyond the brief (owner's request, 2026-10-20) |

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
- **Safety:** the input guard and the domain guardrails get German patterns and German test strings in T7.1, together with the German UI, so a German injection or a German high-risk request is caught like an English one even if T7.2 is cut.

### Light and dark mode (T7.3, extra)

- Both `[theme.light]` and `[theme.dark]` are defined (see "Theme"; T3.1 writes them, T7.3 adds the config test, the toolbar check and the hint), so Streamlit's own menu (top right -> Settings) offers Light, Dark and System. The choice is remembered by the browser.
- Streamlit 1.66 cannot change the theme from the script, and a custom CSS toggle would break the "native first" principle and break on upgrades, so there is no separate header icon (owner's decision, 2026-10-20).
- A sidebar caption under the privacy note says where to switch: ":material/dark_mode: Light or dark mode: menu at the top right -> Settings".
- Charts and badges are checked in both modes; chart colours come from the palette above, which reads on both backgrounds.

### Tabs

`st.tabs([":material/chat: Ask", ":material/target: My targets", ":material/search: Food lookup", ":material/list: Details"])`. Tab bodies are cheap to render; LLM and embedding calls run only when a prompt is submitted, never because a tab is drawn.

#### Ask

- Messages in `st.container(height=...)` so the input stays in view; `st.chat_input("Ask about nutrition for your training")` directly below it, inside the tab (inline, not pinned).
- User messages: `st.chat_message("user")`.
- Assistant messages: `st.chat_message("assistant", avatar=":material/nutrition:")`, containing in order:
  1. **Progress** while the turn runs: `st.status(":shimmer[Searching sources]", type="compact")` with `type="step"` children (check input, rewrite question, search sources, answer, tools). Collapses to a static label when done (core 5). Each step holds a one-line caption on what it does: in Streamlit 1.66 a step without content ends the timeline and hides the steps after it (found in T3.1). Past turns show the same collapsed status.
  2. **Answer** as Markdown with `[S#]` citations (no `unsafe_allow_html`), streamed in under the status box as the model writes it, revealed word by word at most `ANSWER_WORDS_PER_SECOND` (30) so it reads at a steady pace even when the model sends it in bursts, then replaced by the full result (owner's requests in T3.1).
  3. **Sources:** one `st.container(border=True)` per cited source: bold title, a caption with the first three authors and "et al." (owner's choice in T3.1, for the CC BY credit), `st.badge` for the evidence tier (green "ISSN position stand", violet "Peer-reviewed review"), caption with journal, year and licence, and a link "Open article" (AC-1).
  4. **Tool result:** a compact expander labelled with the headline result (e.g. ":material/calculate: Protein target: 160 g") that opens to the result table (AC-6, T4.4).
- **Empty chat:** a one-line invitation and three suggested questions as `st.pills` in an `st.empty()` placeholder, sent through the same handler as typed input; hidden once the chat has a message.
- **Errors:** a short `st.error` inside the assistant message saying what happened and what to do; the history stays (AC-13).

#### My targets

- Four `st.metric(border=True)` in one row: daily kcal (with the surplus or deficit as delta), protein, carbohydrate, fat (grams; % and g/kg in the help text).
- A thin horizontal stacked bar (Altair) of the macro split, with `alt=`.
- Caption: maintenance kcal and how it was calculated, with the sources used.
- Without a profile: an invitation and the "Add your details" button.

#### Food lookup

- `st.text_input` for the food and `st.number_input` for grams, side by side with `vertical_alignment="bottom"`, and a "Look up" button.
- Result: the matched USDA name, four small metrics (kcal, protein, carbohydrate, fat) and fibre in a caption; "Source: USDA FoodData Central".
- Not found: a short message and close matches as `st.pills`.

#### Details (for the last answer)

- **How this answer was found:** the query rewrites as a short list and the filters as `st.badge`s (AC-3).
- **Usage:** this answer's tokens and cost, and the session totals, in one compact line or small metrics (AC-10, Medium 5).

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
| Sidebar daily target, My targets summary card with the macro donut | T4.4 (core) |
| Sidebar Details summary card | T3.2 (rewrites and filters), T5.1 (usage) |
| Sidebar "About the answers" block | T3.1 (beyond the brief, owner's request); folded into an expander once the summary cards arrive, so the sidebar does not grow too long (owner's choice, 2026-10-20) |
| Chat messages, progress steps, source cards | T3.1 (core) |
| Details tab: rewrites and filters | T3.2 (core) |
| Tool result expander, My targets tab, macro bar | T4.4 (core) |
| Food lookup tab | T4.3 / T4.4 (core) |
| Details tab: usage | T5.1 (extra) |
| Light and dark mode hint, both themes checked | T7.3 (extra) |
| Language control, German UI text, German guard and guardrail patterns | T7.1 (extra) |
| German answers, English rewrites for retrieval | T7.2 (extra) |
| Empty-state suggestions, colour tuning, final polish | UI polish ticket (extra, beyond the brief, owner's request) |

## Open questions

- Height of the message container: `CHAT_HEIGHT_PX` = 750 (owner's requests, 2026-10-20: 650, then 750 to fill a tall window), which keeps the input in view in a 1200 px window (checked: the input ends at 1030 px); on a shorter window the page scrolls to the input. Streamlit has no height relative to the window, and it advises at most 500 px for phones: revisit in the UI polish ticket.
- Whether `baseFontSize = 17` and the wide layout read well on a phone: check during the UI polish ticket. At 17 px the sidebar goal control wraps "Maintain" onto a second line (checked 2026-10-20).
