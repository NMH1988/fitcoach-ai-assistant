"""Streamlit entry point: page layout only; the logic lives in src/."""

import re
from datetime import date
from typing import get_args

import streamlit as st

from src import chat, config, export_pdf, guard, llm, profile, units
from src.rag import hybrid, store
from src.rag.sources import ARTICLE_CHANGES_NOTE
from src.tools import registry
from src.tools.energy import Macro, TdeeResult
from src.tools.food import FoodLookupResult

st.set_page_config(page_title=config.APP_TITLE, page_icon=":material/nutrition:", layout="wide")

# Session state: "profile" holds the UserProfile (kg and cm), "units" the unit system the user
# chose and "messages" the chat history (questions and TurnResults). All live for the session
# only and are never logged (docs/SECURITY.md).
st.session_state.setdefault("units", config.DEFAULT_UNIT_SYSTEM)
st.session_state.setdefault("messages", [])

FORM_FIELDS = tuple(profile.form_values(None, "metric"))
GOAL_ICONS = {
    "build_muscle": ":material/fitness_center:",
    "lose_fat": ":material/local_fire_department:",
    "maintain": ":material/balance:",
}
ASSISTANT_AVATAR = ":material/nutrition:"
# What each step of a turn does, shown under it in the status box.
STEP_DETAILS = {
    chat.Step.CHECK: "Length, prompt-injection patterns, safety topics and the question limit.",
    chat.Step.REWRITE: (
        f"A small model rephrases the question {config.QUERY_REWRITES} ways and picks filters."
    ),
    chat.Step.SEARCH: (
        "Search by meaning and by keyword over the approved research for the question and each "
        "rewrite, merged into one ranking."
    ),
    chat.Step.ANSWER: "The model answers from the passages found and cites them.",
    chat.Step.TOOLS: "Calculations from your profile and the USDA food table.",
}
# The icon before each tool result's heading (registry.TOOL_TITLES); None is a refused call.
TOOL_ICONS = {
    registry.TDEE_TOOL: ":material/local_fire_department:",
    registry.MACRO_TOOL: ":material/target:",
    registry.FOOD_TOOL: ":material/restaurant:",
    None: ":material/block:",
}
TIER_COLORS = {1: "green", 2: "violet"}
# The start of a line Markdown would read as a block: "#", "-", "+", "=" or "1." / "1)". A ">"
# (quote) is not here: chat.escape_markdown() escapes it first, so keep both in step.
_LINE_START = re.compile(r"^(\d*)([#+=.)-])")
# How an evidence tier filter is named in "How this answer was found".
TIER_FILTER_LABELS = {1: "ISSN position stands only", 2: "Peer-reviewed reviews only"}


def _form_key(field: str) -> str:
    """Return the session state key of a profile form field."""
    return f"profile_form_{field}"


def _open_profile_form() -> None:
    """Fill the form with the current profile in the chosen units and open the dialog."""
    system = st.session_state["units"]
    values = profile.form_values(st.session_state.get("profile"), system)
    for field, value in values.items():
        st.session_state[_form_key(field)] = value
    st.session_state["profile_form_units"] = system
    st.session_state["profile_form_units_shown"] = system
    st.session_state["profile_form_memory"] = profile.initial_form_memory(
        st.session_state.get("profile"), system
    )
    st.session_state["profile_form_open"] = True


def _close_profile_form() -> None:
    """Close the dialog without saving."""
    st.session_state["profile_form_open"] = False


def _switch_form_units() -> None:
    """Convert the weight and height typed so far into the unit system just chosen."""
    old = st.session_state["profile_form_units_shown"]
    new = st.session_state["profile_form_units"]
    values = {field: st.session_state.get(_form_key(field)) for field in FORM_FIELDS}
    converted, memory = profile.switch_form_units(
        values, old, new, st.session_state.get("profile_form_memory")
    )
    for field, value in converted.items():
        st.session_state[_form_key(field)] = value
    st.session_state["profile_form_memory"] = memory
    st.session_state["profile_form_units_shown"] = new


def _change_goal() -> None:
    """Save the goal picked in the sidebar into the profile."""
    goal = st.session_state["sidebar_goal"]
    current = st.session_state.get("profile")
    if current is not None and goal in get_args(profile.Goal):
        st.session_state["profile"] = profile.with_goal(current, goal)


@st.dialog("Your details", on_dismiss=_close_profile_form)
def _profile_form() -> None:
    """Show the profile form; Save checks it and keeps the profile for this session."""
    # Drawn only while the dialog is open: a style-only st.html takes no space (T4.6).
    st.html(config.PROFILE_DIALOG_CSS)
    st.caption(f":material/info: {config.PROFILE_FORM_HINT}")
    st.segmented_control(
        "Units",
        units.UNIT_SYSTEMS,
        format_func=units.UNIT_SYSTEM_LABELS.get,
        required=True,
        key="profile_form_units",
        on_change=_switch_form_units,
        width="stretch",
    )
    system = st.session_state["profile_form_units"]
    st.segmented_control(
        "Goal",
        get_args(profile.Goal),
        format_func=profile.GOAL_LABELS.get,
        key=_form_key("goal"),
        width="stretch",
    )
    left, right = st.columns(2)
    with left:
        st.number_input(
            f"Weight ({units.weight_unit(system)})",
            min_value=0.0,
            step=10**-units.WEIGHT_DECIMALS,
            format=f"%.{units.WEIGHT_DECIMALS}f",
            key=_form_key("weight"),
        )
    with right:
        st.number_input("Age (years)", min_value=0, step=1, key=_form_key("age"))
    if system == "metric":
        st.number_input("Height (cm)", min_value=0, step=1, key=_form_key("height_cm"))
    else:
        feet, inches = st.columns(2)
        with feet:
            st.number_input("Height (ft)", min_value=0, step=1, key=_form_key("height_ft"))
        with inches:
            st.number_input(
                "Height (in)",
                min_value=0,
                max_value=units.INCHES_PER_FOOT - 1,
                step=1,
                key=_form_key("height_in"),
            )
    st.segmented_control(
        "Sex",
        get_args(profile.Sex),
        format_func=profile.SEX_LABELS.get,
        key=_form_key("sex"),
        help="Used by the energy equation, which has a male and a female form.",
        width="stretch",
    )
    st.selectbox(
        "Activity",
        get_args(profile.ActivityLevel),
        index=None,
        format_func=profile.ACTIVITY_LABELS.get,
        placeholder="Choose your activity level",
        key=_form_key("activity"),
    )
    if st.button("Save", type="primary", icon=":material/check:", width="stretch"):
        values = {field: st.session_state.get(_form_key(field)) for field in FORM_FIELDS}
        try:
            saved = profile.save_profile(values, system, st.session_state.get("profile"))
        except profile.ProfileError as error:
            st.error("\n".join(f"- {message}" for message in error.messages), title="Check these")
        else:
            st.session_state["profile"] = saved
            st.session_state["units"] = system
            st.session_state["profile_form_open"] = False
            st.rerun()
    st.caption(":material/lock: Kept for this session only, never stored.")


def _profile_sidebar() -> None:
    """Show the profile in the sidebar, in the chosen units, with a button to edit it."""
    st.header(":material/person: Your profile")
    current = st.session_state.get("profile")
    if current is None:
        st.caption("Add your details to get personal targets.")
        st.button(
            "Add your details",
            icon=":material/person_add:",
            width="stretch",
            on_click=_open_profile_form,
        )
        return
    system = st.session_state["units"]
    st.session_state["sidebar_goal"] = current.goal
    st.segmented_control(
        "Goal",
        get_args(profile.Goal),
        format_func=lambda goal: f"{GOAL_ICONS[goal]} {profile.GOAL_LABELS[goal]}",
        required=True,
        key="sidebar_goal",
        on_change=_change_goal,
        label_visibility="collapsed",
        width="stretch",
    )
    left, right = st.columns(2)
    left.metric("Weight", units.format_weight(current.weight_kg, system), border=True)
    right.metric("Height", units.format_height(current.height_cm, system), border=True)
    left.metric("Age", current.age, border=True)
    right.metric("Sex", profile.SEX_LABELS[current.sex], border=True)
    st.metric(
        "Activity",
        profile.ACTIVITY_SHORT_LABELS[current.activity],
        help=profile.ACTIVITY_LABELS[current.activity],
        border=True,
    )
    st.button("Edit details", icon=":material/edit:", width="stretch", on_click=_open_profile_form)
    st.caption(":material/lock: Kept for this session only")


@st.cache_resource(show_spinner=False)
def _index():
    """Open the knowledge base index once per app process; restart the app after a rebuild."""
    return store.open_index()


@st.cache_resource(show_spinner=False)
def _keyword_index(_chroma):
    """Build the BM25 index of the knowledge base once per app process (T3.3)."""
    # The leading underscore keeps Streamlit from hashing the Chroma object; the cache is cleared
    # together with _index, so it always matches the index the app holds.
    return hybrid.build_keyword_index(_chroma)


@st.cache_resource(show_spinner=False)
def _chat_model():
    """Build the answer model's client once per app process."""
    return llm.build_chat_model()


@st.cache_resource(show_spinner=False)
def _translation_model():
    """Build the query translation model's client once per app process."""
    return llm.build_chat_model(config.QUERY_TRANSLATION_MODEL, config.QUERY_TRANSLATION_MAX_TOKENS)


@st.cache_resource(show_spinner=False)
def _manifest():
    """Read the approved sources once, for the journal and corrections on the source cards."""
    return chat.manifest_by_id()


def _status_label(result: chat.TurnResult) -> str:
    """Return the label a turn's status box ends with."""
    if result.kind == "answer" and not result.sources:
        return config.STATUS_LABELS["answer_uncited"]
    return config.STATUS_LABELS[result.kind]


def _final_state(result: chat.TurnResult) -> str:
    """Return the status state that ends a turn: error if rejected or failed, else complete."""
    # A guardrail redirect ends "complete": the app did what it should, nothing went wrong.
    return "error" if result.kind in ("rejected", "error") else "complete"


def _step_box(step: chat.Step, state: str):
    """Show one step of a turn with a line on what it does, and return its status box."""
    box = st.status(step.value, type="step", state=state)
    # A step without content ends Streamlit's timeline and hides the steps after it.
    box.caption(STEP_DETAILS[step])
    return box


def _show_steps(result: chat.TurnResult) -> None:
    """Show the steps of a past turn as a collapsed status, as they ended."""
    state = _final_state(result)
    with st.status(_status_label(result), type="compact", state=state):
        for number, step in enumerate(result.steps, start=1):
            _step_box(step, state if number == len(result.steps) else "complete")


def _run_turn(question: str, turn: int) -> None:
    """Run one chat turn: steps in a status box, the answer as it streams in, then the result."""
    status = st.status(f":shimmer[{chat.Step.CHECK.value}]", type="compact")
    # Below the status: the answer while it streams, replaced by the full result at the end.
    answer_slot = st.empty()
    boxes = []

    def on_step(step: chat.Step) -> None:
        """Close the previous step and show the one starting now (core 5, AC-10)."""
        if boxes:
            boxes[-1].update(state="complete")
        with status:
            boxes.append(_step_box(step, "running"))
        status.update(label=f":shimmer[{step.value}]")

    def show_text(text: str) -> None:
        """Show the answer so far, so the user reads it while the model is still writing."""
        # Model output as Markdown, never with unsafe_allow_html (docs/SECURITY.md).
        answer_slot.markdown(text)

    # The model sends its answer in fast bursts; reveal it at a steady, readable pace.
    on_text = chat.PacedWriter(show_text, config.ANSWER_WORDS_PER_SECOND)

    result = chat.run_turn(
        question,
        guard.session_limiter(st.session_state),
        open_index=_index,
        chat_model=_chat_model,
        translation_model=_translation_model,
        manifest=_manifest(),
        on_step=on_step,
        on_text=on_text,
        # The energy tools read the session's profile; the model cannot change it.
        user=st.session_state.get("profile"),
        keyword_index=_keyword_index,
    )
    if result.index_not_ready:
        # Open the index again on the next turn, e.g. once the owner has rebuilt it.
        _index.clear()
        _keyword_index.clear()
    state = _final_state(result)
    if boxes:
        boxes[-1].update(state=state)
    status.update(label=_status_label(result), state=state)
    with answer_slot.container():
        _show_result(result, turn)
    st.session_state["messages"].append({"role": "assistant", "result": result})


def _source_card(card: chat.SourceCard) -> None:
    """Show one cited article: title, authors, tier, journal, year, licence and link (AC-1)."""
    with st.container(border=True):
        st.markdown(f"**{chat.escape_markdown(card.title)}**")
        if card.authors:
            # Credits the authors on the card itself (CC BY; copyright policy rule 6).
            st.caption(chat.escape_markdown(chat.format_authors(card.authors)))
        st.badge(
            config.EVIDENCE_TIER_LABELS.get(card.evidence_tier, config.UNKNOWN_TIER_LABEL),
            color=TIER_COLORS.get(card.evidence_tier, "gray"),
        )
        meta = [chat.escape_markdown(card.journal)] if card.journal else []
        meta += [
            str(card.year),
            f"[{card.license}]({chat.markdown_url(card.license_url)})",
            f"cited as {', '.join(card.labels)}",
        ]
        st.caption(" · ".join(meta))
        st.markdown(f"[:material/open_in_new: Open article]({chat.markdown_url(card.url)})")
        for correction in card.corrections:
            relation = config.CORRECTION_LABELS[correction.relation]
            st.caption(
                f":material/edit_note: {relation}: "
                f"[{chat.escape_markdown(correction.title)}]({chat.markdown_url(correction.url)})"
            )


def _table(rows: dict[str, str]) -> None:
    """Show label and value pairs as a two-column table of plain text (AC-6)."""
    # st.dataframe shows cells as plain text; st.table would read Markdown in them, so a USDA name
    # could add a link or an image (docs/SECURITY.md).
    st.dataframe(
        {"Item": list(rows), "Value": list(rows.values())}, hide_index=True, width="stretch"
    )


def _show_tdee(result: TdeeResult) -> None:
    """Show calculate_tdee's result: resting energy, activity factor and daily needs."""
    _table(
        {
            "Resting energy (BMR)": f"{result.bmr_kcal:,} kcal/day",
            "Activity factor": f"{result.activity_factor:g}",
            "Daily energy needs (TDEE)": f"{result.tdee_kcal:,} kcal/day",
        }
    )
    st.caption(result.method)


def _macro_bar(kcal: dict[str, int]) -> None:
    """Draw the kcal of each macro as one horizontal stacked bar, in the macro colours."""
    names = list(kcal)
    # A Vega-Lite spec rather than st.bar_chart, so the value axis starts at 0 (st.bar_chart's
    # started at -500 in a narrow window). `alt` is the chart's text alternative.
    alt = "Energy split per day: " + ", ".join(
        f"{name} {value:,} kcal" for name, value in kcal.items()
    )
    spec = {
        "mark": {"type": "bar"},
        "encoding": {
            "x": {
                "field": "kcal",
                "type": "quantitative",
                "stack": "zero",
                # From 0 to the next round value, so the bar never ends at the chart's edge.
                "scale": {"domainMin": 0, "nice": True},
                "title": "kcal per day",
            },
            "y": {"field": "split", "type": "nominal", "title": None},
            "color": {
                "field": "macro",
                "type": "nominal",
                "sort": names,
                "scale": {"domain": names, "range": [config.MACRO_COLORS[n] for n in names]},
                "legend": {"orient": "bottom", "title": None},
            },
            # Typed as numbers: an untyped field is nominal, and a nominal kcal ignores the format.
            "order": {"field": "position", "type": "quantitative"},
            "tooltip": [
                {"field": "macro", "type": "nominal"},
                {"field": "kcal", "type": "quantitative", "format": ","},
            ],
        },
    }
    data = {
        "macro": names,
        "kcal": list(kcal.values()),
        "split": ["Energy"] * len(names),
        "position": list(range(len(names))),
    }
    st.vega_lite_chart(data, spec, width="stretch", height=config.MACRO_CHART_HEIGHT_PX, alt=alt)


def _macro_cells(macro: Macro) -> list[str]:
    """Return one macro's grams, share of the kcal and grams per kg, as table cells."""
    return [f"{macro.grams:,} g", f"{macro.percent}%", f"{macro.g_per_kg:g} g/kg"]


def _show_macros(result: registry.MacroToolResult) -> None:
    """Show the daily targets as a table and the energy split as a stacked bar (AC-6)."""
    targets = result.targets
    if targets.kcal_target is None or not (
        targets.protein and targets.carbohydrate and targets.fat
    ):
        st.caption(result.message)
        return
    low, high = targets.kcal_range or (targets.kcal_target, targets.kcal_target)
    protein_low, protein_high = targets.protein_g_range or (0, 0)
    _table(
        {
            "Daily target": f"{targets.kcal_target:,} kcal",
            "Range for the goal": f"{low:,}-{high:,} kcal",
            "Daily energy needs": f"{result.energy_needs.tdee_kcal:,} kcal",
            "Protein range": f"{protein_low:,}-{protein_high:,} g",
        }
    )
    macros = {
        "Protein": (targets.protein, config.KCAL_PER_G_PROTEIN),
        "Carbohydrate": (targets.carbohydrate, config.KCAL_PER_G_CARBOHYDRATE),
        "Fat": (targets.fat, config.KCAL_PER_G_FAT),
    }
    cells = [_macro_cells(macro) for macro, _ in macros.values()]
    st.dataframe(
        {
            "Macro": list(macros),
            "Per day": [row[0] for row in cells],
            "Share of kcal": [row[1] for row in cells],
            "Per kg of body weight": [row[2] for row in cells],
        },
        hide_index=True,
        width="stretch",
    )
    # The energy split as one stacked bar; the numbers are in the table above, so colour is never
    # the only signal (docs/UI_DESIGN.md, Accessibility).
    _macro_bar({name: macro.grams * kcal_per_g for name, (macro, kcal_per_g) in macros.items()})
    st.caption(result.message)
    for note in targets.notes:
        st.caption(f":material/info: {note}")


def _show_food(result: FoodLookupResult) -> None:
    """Show a food lookup: the matched USDA food and its nutrients, or the suggestions."""
    if result.status != "found" or result.nutrients is None:
        st.caption(result.message)
        if result.alternatives:
            # USDA names as table cells: plain text, never Markdown.
            st.dataframe({"Did you mean": result.alternatives}, hide_index=True, width="stretch")
        return
    nutrients = result.nutrients
    fiber = "not reported" if nutrients.fiber_g is None else f"{nutrients.fiber_g:g} g"
    rows = {
        "USDA food": result.matched_name or "",
        "Amount": f"{result.grams:g} g",
        "Energy": f"{nutrients.kcal:,} kcal",
        "Protein": f"{nutrients.protein_g:g} g",
        "Carbohydrate": f"{nutrients.carbohydrate_g:g} g",
        "Fat": f"{nutrients.fat_g:g} g",
        "Fiber": fiber,
    }
    if result.alternatives:
        rows["Close alternatives"] = "; ".join(result.alternatives)
    _table(rows)
    st.caption(config.USDA_SOURCE_LINE)


def _show_tool_run(run: registry.ToolRun, key: str) -> None:
    """Show one tool result under its heading; without a profile, a button opens the form."""
    name = run.name if run.name in registry.TOOL_TITLES else None
    st.markdown(f"**{TOOL_ICONS[name]} {registry.TOOL_TITLES[name]}**")
    result = run.result
    if run.status == "profile_needed":
        st.info(config.PROFILE_NEEDED_HINT, icon=":material/person_add:")
        st.button(
            "Add your details", icon=":material/person_add:", key=key, on_click=_open_profile_form
        )
    elif isinstance(result, TdeeResult) and result.status == "ok":
        _show_tdee(result)
    elif isinstance(result, registry.MacroToolResult) and result.status == "ok":
        _show_macros(result)
    elif isinstance(result, FoodLookupResult) and result.status != "invalid":
        _show_food(result)
    else:
        # A refused or failed call: the fixed message the model got, never what it sent.
        st.caption(result.message)


def _show_tool_runs(runs: tuple[registry.ToolRun, ...], turn: int) -> None:
    """Show each tool result of a turn in one "Tool results" expander (AC-6)."""
    # Open when a result needs the profile, so the "Add your details" button is in view.
    needs_profile = any(run.status == "profile_needed" for run in runs)
    with st.expander(
        f"Tool results ({len(runs)})", icon=":material/calculate:", expanded=needs_profile
    ):
        for number, run in enumerate(runs):
            if number:
                st.divider()
            _show_tool_run(run, key=f"tool_profile_{turn}_{number}")


def _show_result(result: chat.TurnResult, turn: int) -> None:
    """Show a turn's answer with its sources and tool results, or its fixed message."""
    if result.kind == "rejected":
        st.warning(result.text, icon=":material/block:")
    elif result.kind == "guardrail":
        # A refusal or a pointer to a professional (AC-12), not an error.
        st.info(result.text, icon=":material/health_and_safety:")
    elif result.kind == "error":
        st.error(result.text, icon=":material/error:")
    else:
        # Model output as Markdown, never with unsafe_allow_html (docs/SECURITY.md).
        st.markdown(result.text)
        if result.sources:
            with st.expander(f"Sources ({len(result.sources)})", icon=":material/menu_book:"):
                for card in result.sources:
                    _source_card(card)
        if result.tool_runs:
            _show_tool_runs(result.tool_runs, turn)


def _show_message(message: dict, turn: int) -> None:
    """Show one message of the chat history; `turn` is its place, for unique widget keys."""
    if message["role"] == "user":
        with st.chat_message("user"):
            # Plain text: the user's own words are shown as typed, not read as Markdown.
            st.text(message["text"])
        return
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        _show_steps(message["result"])
        _show_result(message["result"], turn)


def _last_search() -> chat.SearchDetails | None:
    """Return how the latest turn that reached the search searched, or None before any."""
    for message in reversed(st.session_state["messages"]):
        if message["role"] == "assistant" and message["result"].search is not None:
            return message["result"].search
    return None


def _one_line(text: str) -> str:
    """Return text on one line, escaped, so it adds no formatting, image or link to a list."""
    # GFM still links a bare "www." or e-mail address (no scheme, nothing to escape); it is shown,
    # never loaded, and no raw HTML gets through.
    line = chat.escape_markdown(" ".join(text.split()))
    # A line start Markdown reads as a heading, quote, list or rule ("# Big", "> x", "1. x").
    return _LINE_START.sub(r"\1\\\2", line)


def _filter_badges(details: chat.SearchDetails) -> None:
    """Show the filters the rewrite step chose as badges, or say there were none."""
    if not details.has_filters:
        st.badge("No filters", icon=":material/filter_alt_off:", color="gray")
        return
    with st.container(horizontal=True, gap="small"):
        for topic in details.topics:
            st.badge(config.TOPIC_LABELS.get(topic, topic), icon=":material/sell:", color="blue")
        if details.min_year is not None:
            st.badge(f"From {details.min_year}", icon=":material/calendar_month:", color="blue")
        if details.evidence_tier is not None:
            label = TIER_FILTER_LABELS.get(details.evidence_tier, config.UNKNOWN_TIER_LABEL)
            st.badge(label, icon=":material/verified:", color="blue")


def _search_notes(details: chat.SearchDetails) -> None:
    """Say when the rewrite step gave nothing usable or the filters were dropped."""
    if details.fell_back:
        st.caption(
            ":material/info: The rewrite step gave no usable result, so only your question "
            "was searched, with no filters."
        )
    if details.filter_dropped:
        st.caption(
            ":material/filter_alt_off: No passage close enough matched these filters, so the "
            "search ran again without them."
        )


def _details_tab() -> None:
    """Show how the last answer was found: what was searched and the filters used (AC-3)."""
    details = _last_search()
    st.subheader(":material/manage_search: How this answer was found")
    if details is None:
        st.caption(
            "Ask a question in the Ask tab to see how its answer was found: the searches run "
            "and the filters used."
        )
        return
    st.markdown("**Searched for**")
    # The question is the user's text and the rewrites the model's: both shown escaped.
    lines = [f"1. {_one_line(details.question)} *(your question)*"]
    lines += [
        f"{number}. {_one_line(rewrite)}" for number, rewrite in enumerate(details.rewrites, 2)
    ]
    st.markdown("\n".join(lines))
    st.markdown("**Filters**")
    _filter_badges(details)
    _search_notes(details)


def _last_answer_card() -> None:
    """Show a short summary of how the last answer was found in the sidebar."""
    details = _last_search()
    if details is None:
        return
    with st.container(border=True):
        st.markdown("**:material/manage_search: Last answer**")
        # Names the question, as a rejected or failed turn leaves an earlier search here.
        question = _one_line(details.question)
        if len(question) > config.CARD_QUESTION_CHARS:
            question = question[: config.CARD_QUESTION_CHARS].rstrip("\\ ") + "…"
        st.caption(f"For: {question}")
        if details.rewrites:
            rewrites = len(details.rewrites)
            st.caption(
                f"Searched {len(details.queries)} ways: your question and {rewrites} "
                f"{'rewrite' if rewrites == 1 else 'rewrites'}."
            )
        else:
            st.caption("Searched for your question only.")
        _filter_badges(details)
        if details.filter_dropped:
            st.caption("No match with these filters, so they were dropped.")
        st.caption("More in the Details tab.")


def _ask_tab() -> None:
    """Show the chat: the history, then the input; a new question runs one turn."""
    history = st.session_state["messages"]
    box = st.container(height=config.CHAT_HEIGHT_PX)
    with box:
        invitation = st.empty()
        if not history:
            invitation.caption(
                "Ask a question about nutrition for strength training. "
                "Answers cite the research they use."
            )
        for turn, message in enumerate(history):
            _show_message(message, turn)
    question = st.chat_input("Ask about nutrition for your training", key="chat_input")
    if not question:
        return
    invitation.empty()
    history.append({"role": "user", "text": question})
    with box:
        _show_message(history[-1], len(history) - 1)
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            _run_turn(question, len(history))


def _about_sidebar() -> None:
    """Say in the sidebar what the answers are based on, and credit every source."""
    manifest = _manifest()
    if not manifest:
        return
    summary = chat.knowledge_base_summary(manifest)
    st.divider()
    # An expander since the last answer's card sits above it (docs/UI_DESIGN.md); Streamlit cannot
    # nest expanders, so the credits are a section inside it.
    with st.expander("About the answers", icon=":material/menu_book:"):
        st.markdown(
            f"- **{summary.articles} open-access research articles**: "
            f"{summary.position_stands} ISSN position stands and {summary.reviews} peer-reviewed "
            f"reviews ({' and '.join(summary.licenses)}).\n"
            f"- Each question is rephrased {config.QUERY_REWRITES} ways, passages are found by "
            "meaning and by keyword and ranked together, and the answer cites them as "
            "[S1], [S2]...\n"
            f"- Rephrased by `{config.QUERY_TRANSLATION_MODEL}` and written by "
            f"`{config.DEFAULT_ANSWER_MODEL}` through OpenRouter."
        )
        # Credits every source (copyright policy rule 6): authors, title, journal, licence, link,
        # and the change made with the no-endorsement note, as in ATTRIBUTION.md.
        st.markdown("**:material/license: Sources and credits**")
        for source in manifest.values():
            st.markdown(
                f"**{source.id}.** {chat.escape_markdown(chat.format_authors(source.authors))}. "
                f"{chat.escape_markdown(source.title)} ({source.year}). "
                f"{chat.escape_markdown(source.journal)}. "
                f"[{source.license}]({chat.markdown_url(source.license_url)}) · "
                f"[Article]({chat.markdown_url(source.url)})"
            )
        st.caption(
            f"{ARTICLE_CHANGES_NOTE} Full credits, with each article's copyright notice, are in "
            "ATTRIBUTION.md in the repository."
        )


def _summary_download() -> None:
    """Offer the session summary as a PDF, built in memory only when clicked (AC-9)."""
    # Drawn after the main area, so the turn that just ran is in it. The PDF is built from this
    # run's snapshot when the user clicks; Streamlit keeps the bytes in memory, never on disk.
    turns = export_pdf.session_turns(st.session_state["messages"])
    user = st.session_state.get("profile")
    system = st.session_state["units"]
    manifest = _manifest()
    # One date for the file name and the PDF, even if the click comes after midnight.
    today = date.today()

    def build() -> bytes:
        """Build the PDF from this run's session."""
        return export_pdf.build_summary_pdf(turns, user, system, manifest, today)

    empty = user is None and not turns
    st.download_button(
        config.PDF_BUTTON_LABEL,
        data=build,
        file_name=config.PDF_FILE_NAME.format(date=today.isoformat()),
        mime="application/pdf",
        icon=":material/download:",
        # The download needs no rerun of the app.
        on_click="ignore",
        disabled=empty,
        help=config.PDF_BUTTON_EMPTY_HELP if empty else config.PDF_BUTTON_HELP,
        key="summary_pdf",
        width="stretch",
    )


def _main_area() -> None:
    """Show the header, the disclaimer and the four tabs."""
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"
    ):
        st.title(config.APP_TITLE)
        st.badge(
            "Not medical advice", icon=":material/info:", color="orange", help=config.DISCLAIMER
        )
    st.markdown(config.APP_INTRO)
    # Shown on every page state (AC-12), large enough to notice (owner's request, 2026-10-20).
    st.warning(f"**Not medical advice.** {config.DISCLAIMER}", icon=":material/info:")

    ask, targets, food, details = st.tabs(
        [
            ":material/chat: **Ask**",
            ":material/target: **My targets**",
            ":material/search: **Food lookup**",
            ":material/list: **Details**",
        ]
    )
    with ask:
        _ask_tab()
    with targets:
        st.caption("Your daily energy and macro targets will appear here in a later version.")
    with food:
        st.caption("Looking up the nutrients of a food will be possible here in a later version.")
    with details:
        _details_tab()


with st.sidebar:
    _profile_sidebar()
    st.caption(config.THEME_HINT)
    # Both slots are filled after the main area, so they hold the turn that just ran (the PDF too);
    # until then the page keeps the previous run's card. Drawn once per run: a slot drawn twice in
    # one run keeps the first draw's extra elements (e.g. a badge the new turn does not have).
    download_slot = st.empty()
    last_answer_slot = st.empty()
    _about_sidebar()
if st.session_state.get("profile_form_open"):
    _profile_form()


# The content sits in the middle column of the wide layout (config.PAGE_COLUMN_WEIGHTS).
_, main, _ = st.columns(config.PAGE_COLUMN_WEIGHTS)
with main:
    _main_area()
with download_slot.container():
    _summary_download()
with last_answer_slot.container():
    _last_answer_card()
