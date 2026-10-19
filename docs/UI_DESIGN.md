# UI design

How the Streamlit app looks and where each piece of information lives. Accepted by the owner on 2026-10-19 as the working design (mockup v5, `docs/ui/mockup-v5.html`); it may change later. Built with Streamlit 1.66 native elements and `.streamlit/config.toml`, not custom CSS.

**Serves:** core 5 (intuitive UI that shows sources, tool results and progress), Medium 5 and 6, AC-1, AC-3, AC-6, AC-10. Colours, the empty-state suggestions and other visual polish are beyond the brief (owner's request) and belong to the extras group in `docs/IMPLEMENTATION_PLAN.md`.

## Principles

- **The chat comes first.** The Ask tab shows only what a user needs to read an answer: the answer, its sources and its tool result. Everything else is one tab away.
- **One accent colour** (teal-green) on a neutral base; one primary button per view.
- **Compact text:** body 14 px (Streamlit's default is 16 px); captions for labels and meta lines.
- **Native first:** `st.chat_message`, `st.metric`, `st.badge`, `st.tabs`, `st.status`, `st.dialog`. No `unsafe_allow_html`, no `st.html` styling. If a detail of the mockup needs CSS, the native look wins.
- **Sentence case**, Material Symbols icons (`:material/name:`), no emoji in the UI.

## Theme (`.streamlit/config.toml`)

```toml
[theme]
font = "sans-serif"          # system font; no Google Fonts request (visitors' IPs are not sent to Google)
baseFontSize = 14
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

`st.set_page_config(page_title="Gym nutrition assistant", page_icon=":material/nutrition:", layout="centered")`.

### Sidebar: the profile

| Element | Streamlit | Notes |
|---|---|---|
| "Your profile" heading | `st.subheader` with `:material/person:` | |
| Goal | `st.segmented_control` (Build muscle / Lose fat / Maintain, with icons), `width="stretch"` | Changing it recalculates the targets |
| Weight, height, age, sex | `st.columns(2)` of `st.metric(..., border=True)` | Values large, labels small; shown in the chosen units |
| Activity | `st.metric(..., border=True)` full width | e.g. "Moderate · 4-5 times" |
| Edit details | `st.button("Edit details", icon=":material/edit:", width="stretch")` | Opens the profile form in an `st.dialog` (owner's choice in T4.1): a Metric / Imperial switch, then plain inputs and a Save button, not an `st.form`, so switching units converts the values already typed. Validation messages come from `src/profile.py` |
| Daily target | `st.metric("Daily target", "3,010 kcal", border=True)` | Always visible, whatever tab is open; added with the targets (T4.4) |
| Privacy note | `st.caption(":material/lock: Kept for this session only")` | |

Before a profile exists, the sidebar shows a short invitation and the "Add your details" button (same dialog) instead of the tiles.

### Header

App name with icon on the left; `st.badge("Not medical advice", icon=":material/info:", color="orange")` on the right (`st.container(horizontal=True)`). Always visible (AC-12).

### Tabs

`st.tabs([":material/chat: Ask", ":material/target: My targets", ":material/search: Food lookup", ":material/list: Details"])`. Tab bodies are cheap to render; LLM and embedding calls run only when a prompt is submitted, never because a tab is drawn.

#### Ask

- Messages in `st.container(height=...)` so the input stays in view; `st.chat_input("Ask about nutrition for your training")` directly below it, inside the tab (inline, not pinned).
- User messages: `st.chat_message("user")`.
- Assistant messages: `st.chat_message("assistant", avatar=":material/nutrition:")`, containing in order:
  1. **Progress** while the turn runs: `st.status(":shimmer[Searching sources]", type="compact")` with `type="step"` children (check input, rewrite question, search sources, answer, tools). Collapses to a static label when done (core 5).
  2. **Answer** as Markdown with `[S#]` citations (no `unsafe_allow_html`).
  3. **Sources:** one `st.container(border=True)` per cited source: bold title, `st.badge` for the evidence tier (green "ISSN position stand", violet "Peer-reviewed review"), caption with journal, year and licence, and a link "Open article" (AC-1).
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

- App text is English, sentence case, no "please", no exclamation marks.
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
| Sidebar daily target | T4.4 (core) |
| Chat messages, progress steps, source cards | T3.1 (core) |
| Details tab: rewrites and filters | T3.2 (core) |
| Tool result expander, My targets tab, macro bar | T4.4 (core) |
| Food lookup tab | T4.3 / T4.4 (core) |
| Details tab: usage | T5.1 (extra) |
| Empty-state suggestions, colour tuning, final polish | UI polish ticket (extra, beyond the brief, owner's request) |

## Open questions

- Height of the message container on small screens: check during T3.1.
- Whether `baseFontSize = 14` reads well on a phone: check during the UI polish ticket.
