"""Streamlit entry point: page layout only; the logic lives in src/."""

import re
from collections.abc import Callable
from datetime import date
from typing import get_args

import streamlit as st

from src import chat, config, export_pdf, guard, i18n, llm, profile, units, usage
from src.rag import hybrid, store
from src.tools import meal_plan, registry
from src.tools.energy import Macro, MacroTargetsResult, TdeeResult, protein_lowered_note
from src.tools.food import FoodLookupResult, food_names
from src.tools.meal_plan import MealPlanResult

# The language: the browser's at the start of a session, then the user's choice from the header
# (T7.1). Written once, before the control is drawn, so it is kept for the session.
if i18n.SESSION_KEY not in st.session_state:
    st.session_state[i18n.SESSION_KEY] = i18n.language_for_locale(i18n.browser_locale())

st.set_page_config(
    page_title=i18n.t("app.title", st.session_state[i18n.SESSION_KEY]),
    page_icon=":material/nutrition:",
    layout="wide",
)

# Session state: "profile" holds the UserProfile (kg and cm), "units" the unit system the user
# chose, "language" the UI language (T7.1) and "messages" the chat history (questions, and
# TurnResults with their priced TurnUsage under "usage", T5.1); "food_result" the Food lookup
# tab's last result (USDA data only), with its inputs under "food_query" and "food_grams". All
# live for the session only and are never logged (docs/SECURITY.md).
st.session_state.setdefault("units", config.DEFAULT_UNIT_SYSTEM)
st.session_state.setdefault("messages", [])

FORM_FIELDS = tuple(profile.form_values(None, "metric"))
GOAL_ICONS = {
    "build_muscle": ":material/fitness_center:",
    "lose_fat": ":material/local_fire_department:",
    "maintain": ":material/balance:",
}
ASSISTANT_AVATAR = ":material/nutrition:"
# The icon before each tool result's heading; None is a refused call.
TOOL_ICONS = {
    registry.TDEE_TOOL: ":material/local_fire_department:",
    registry.MACRO_TOOL: ":material/target:",
    registry.FOOD_TOOL: ":material/restaurant:",
    registry.MEAL_PLAN_TOOL: ":material/fact_check:",
    None: ":material/block:",
}
TIER_COLORS = {1: "green", 2: "violet"}
# The start of a line Markdown would read as a block: "#", "-", "+", "=" or "1." / "1)". A ">"
# (quote) is not here: chat.escape_markdown() escapes it first, so keep both in step.
_LINE_START = re.compile(r"^(\d*)([#+=.)-])")
USAGE_ICON = ":material/data_usage:"
# The columns of the Details tab's table of a turn's calls (T5.1), as keys in src/i18n.py.
USAGE_COLUMNS = ("step", "model", "input", "cached", "output", "reasoning", "cost")
# A call of the answer step is named with its round ("Answer, round 2"), read back for the UI.
_ANSWER_STEP = re.compile(
    re.escape(config.USAGE_STEP_ANSWER).replace(re.escape("{round}"), r"(\d+)")
)


def _lang() -> i18n.Language:
    """Return the session's UI language."""
    return st.session_state[i18n.SESSION_KEY]


def _t(key: str, **params: object) -> str:
    """Return a UI text in the session's language."""
    return i18n.t(key, _lang(), **params)


def _n(value: float) -> str:
    """Show a number with thousands marks in the session's language ("2,500" or "2.500")."""
    return i18n.number(value, _lang())


def _plain(value: float) -> str:
    """Show a number with no thousands marks in the session's language ("1.5" or "1,5")."""
    return i18n.plain(value, _lang())


def _percent(value: int) -> str:
    """Show a percentage as the language writes it: "20%" or "20 %"."""
    return i18n.percent(value, _lang())


def _label_of(prefix: str) -> Callable[[str], str]:
    """Return a widget's format_func: a value's label under a key prefix, in today's language."""
    # The language is bound now: Streamlit (and AppTest) may call format_func outside the run.
    lang = _lang()
    return lambda value: i18n.t(f"{prefix}.{value}", lang)


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


def _profile_form() -> None:
    """Show the profile form; Save checks it and keeps the profile for this session."""
    # Drawn only while the dialog is open: a style-only st.html takes no space (T4.6).
    st.html(config.PROFILE_DIALOG_CSS)
    st.caption(f":material/info: {_t('profile.form_hint')}")
    st.segmented_control(
        _t("profile.units"),
        units.UNIT_SYSTEMS,
        format_func=_label_of("units"),
        required=True,
        key="profile_form_units",
        on_change=_switch_form_units,
        width="stretch",
    )
    system = st.session_state["profile_form_units"]
    st.segmented_control(
        _t("profile.goal"),
        get_args(profile.Goal),
        format_func=_label_of("goal"),
        key=_form_key("goal"),
        width="stretch",
    )
    left, right = st.columns(2)
    with left:
        st.number_input(
            _t("profile.weight_unit", unit=units.weight_unit(system)),
            min_value=0.0,
            step=10**-units.WEIGHT_DECIMALS,
            format=f"%.{units.WEIGHT_DECIMALS}f",
            key=_form_key("weight"),
        )
    with right:
        st.number_input(_t("profile.age_years"), min_value=0, step=1, key=_form_key("age"))
    if system == "metric":
        st.number_input(_t("profile.height_cm"), min_value=0, step=1, key=_form_key("height_cm"))
    else:
        feet, inches = st.columns(2)
        with feet:
            st.number_input(
                _t("profile.height_ft"), min_value=0, step=1, key=_form_key("height_ft")
            )
        with inches:
            st.number_input(
                _t("profile.height_in"),
                min_value=0,
                max_value=units.INCHES_PER_FOOT - 1,
                step=1,
                key=_form_key("height_in"),
            )
    st.segmented_control(
        _t("profile.sex"),
        get_args(profile.Sex),
        format_func=_label_of("sex"),
        key=_form_key("sex"),
        help=_t("profile.sex_help"),
        width="stretch",
    )
    st.selectbox(
        _t("profile.activity"),
        get_args(profile.ActivityLevel),
        index=None,
        format_func=_label_of("activity"),
        placeholder=_t("profile.activity_placeholder"),
        key=_form_key("activity"),
    )
    if st.button(_t("profile.save"), type="primary", icon=":material/check:", width="stretch"):
        values = {field: st.session_state.get(_form_key(field)) for field in FORM_FIELDS}
        try:
            saved = profile.save_profile(values, system, st.session_state.get("profile"))
        except profile.ProfileError as error:
            messages = error.messages_in(_lang())
            st.error(
                "\n".join(f"- {message}" for message in messages), title=_t("profile.check_these")
            )
        else:
            st.session_state["profile"] = saved
            st.session_state["units"] = system
            st.session_state["profile_form_open"] = False
            st.rerun()
    st.caption(f":material/lock: {_t('profile.kept_never_stored')}")


def _profile_sidebar() -> None:
    """Show the profile in the sidebar, in the chosen units, with a button to edit it."""
    st.header(f":material/person: {_t('profile.your_profile')}")
    current = st.session_state.get("profile")
    if current is None:
        st.caption(_t("profile.add_caption"))
        st.button(
            _t("profile.add"),
            icon=":material/person_add:",
            width="stretch",
            on_click=_open_profile_form,
        )
        return
    system = st.session_state["units"]
    st.session_state["sidebar_goal"] = current.goal
    goal_label = _label_of("goal")
    st.segmented_control(
        _t("profile.goal"),
        get_args(profile.Goal),
        format_func=lambda goal: f"{GOAL_ICONS[goal]} {goal_label(goal)}",
        required=True,
        key="sidebar_goal",
        on_change=_change_goal,
        label_visibility="collapsed",
        width="stretch",
    )
    left, right = st.columns(2)
    weight = units.format_weight(current.weight_kg, system, _lang())
    left.metric(_t("profile.weight"), weight, border=True)
    right.metric(_t("profile.height"), units.format_height(current.height_cm, system), border=True)
    left.metric(_t("profile.age"), current.age, border=True)
    right.metric(_t("profile.sex"), _t(f"sex.{current.sex}"), border=True)
    st.metric(
        _t("profile.activity"),
        _t(f"activity_short.{current.activity}"),
        help=_t(f"activity.{current.activity}"),
        border=True,
    )
    st.button(
        _t("profile.edit"), icon=":material/edit:", width="stretch", on_click=_open_profile_form
    )
    _targets_sidebar(system)
    st.caption(f":material/lock: {_t('profile.kept')}")


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
        return _t("status.answer_uncited")
    return _t(f"status.{result.kind}")


def _final_state(result: chat.TurnResult) -> str:
    """Return the status state that ends a turn: error if rejected or failed, else complete."""
    # A guardrail redirect ends "complete": the app did what it should, nothing went wrong.
    return "error" if result.kind in ("rejected", "error") else "complete"


def _step_label(step: chat.Step) -> str:
    """Return the name of a turn's step in the session's language."""
    return _t(f"step.{step.name.lower()}")


def _step_box(step: chat.Step, state: str):
    """Show one step of a turn with a line on what it does, and return its status box."""
    box = st.status(_step_label(step), type="step", state=state)
    # A step without content ends Streamlit's timeline and hides the steps after it.
    box.caption(_t(f"step.{step.name.lower()}.detail"))
    return box


def _show_steps(result: chat.TurnResult) -> None:
    """Show the steps of a past turn as a collapsed status, as they ended."""
    state = _final_state(result)
    with st.status(_status_label(result), type="compact", state=state):
        for number, step in enumerate(result.steps, start=1):
            _step_box(step, state if number == len(result.steps) else "complete")


def _run_turn(question: str, turn: int) -> None:
    """Run one chat turn: steps in a status box, the answer as it streams in, then the result."""
    status = st.status(f":shimmer[{_step_label(chat.Step.CHECK)}]", type="compact")
    # Below the status: the answer while it streams, replaced by the full result at the end.
    answer_slot = st.empty()
    # Under the answer: the turn's tokens and cost, once it is priced (T5.1).
    usage_slot = st.empty()
    boxes = []

    def on_step(step: chat.Step) -> None:
        """Close the previous step and show the one starting now (core 5, AC-10)."""
        if boxes:
            boxes[-1].update(state="complete")
        with status:
            boxes.append(_step_box(step, "running"))
        status.update(label=f":shimmer[{_step_label(step)}]")

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
        # The answer is written in the language chosen in the header when the question is asked
        # (T7.2); the question's own language does not change it.
        language=_lang(),
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
    # In the history before the price read: a click during that network call reruns the script,
    # which would otherwise drop the answer from the chat.
    message = {"role": "assistant", "result": result, "usage": None}
    st.session_state["messages"].append(message)
    # Priced once, after the answer is shown, when the turn ends: a rerun shows the stored cost
    # and makes no network call. Its own slot, as a slot drawn twice in one run keeps stale parts.
    message["usage"] = _price(result)
    with usage_slot.container():
        _usage_caption(message["usage"])


def _price(result: chat.TurnResult) -> usage.TurnUsage:
    """Price a turn's calls with OpenRouter's prices; a turn with no call needs no prices."""
    return usage.price_turn(result.usage, usage.PRICES.get() if result.usage else None)


def _usage_caption(turn_usage: usage.TurnUsage | None) -> None:
    """Show a turn's tokens and cost under its answer, if it made any model call (AC-10)."""
    if turn_usage is not None and turn_usage.calls:
        st.caption(f"{USAGE_ICON} {_dollars(usage.format_turn(turn_usage, _lang()))}")


def _dollars(text: str) -> str:
    """Escape the dollar signs of a cost line, so Markdown never reads two as LaTeX."""
    return text.replace("$", r"\$")


def _tier_label(tier: int) -> str:
    """Return the name of an evidence tier, or "Review" for a tier the app does not know."""
    return _t(f"tier.{tier}") if tier in config.EVIDENCE_TIERS else _t("tier.unknown")


def _source_card(card: chat.SourceCard) -> None:
    """Show one cited article: title, authors, tier, journal, year, licence and link (AC-1)."""
    with st.container(border=True):
        # Titles, journals, authors and licence names stay as the articles give them (English).
        st.markdown(f"**{chat.escape_markdown(card.title)}**")
        if card.authors:
            # Credits the authors on the card itself (CC BY; copyright policy rule 6).
            st.caption(chat.escape_markdown(chat.format_authors(card.authors)))
        st.badge(_tier_label(card.evidence_tier), color=TIER_COLORS.get(card.evidence_tier, "gray"))
        meta = [chat.escape_markdown(card.journal)] if card.journal else []
        meta += [
            str(card.year),
            f"[{card.license}]({chat.markdown_url(card.license_url)})",
            _t("card.cited_as", labels=", ".join(card.labels)),
        ]
        st.caption(" · ".join(meta))
        open_article = _t("card.open_article")
        st.markdown(f"[:material/open_in_new: {open_article}]({chat.markdown_url(card.url)})")
        for correction in card.corrections:
            relation = _t(f"correction.{correction.relation}")
            st.caption(
                f":material/edit_note: {relation}: "
                f"[{chat.escape_markdown(correction.title)}]({chat.markdown_url(correction.url)})"
            )


def _table(rows: dict[str, str]) -> None:
    """Show label and value pairs as a two-column table of plain text (AC-6)."""
    # st.dataframe shows cells as plain text; st.table would read Markdown in them, so a USDA name
    # could add a link or an image (docs/SECURITY.md).
    st.dataframe(
        {_t("table.item"): list(rows), _t("table.value"): list(rows.values())},
        hide_index=True,
        width="stretch",
    )


def _show_tdee(result: TdeeResult) -> None:
    """Show calculate_tdee's result: resting energy, activity factor and daily needs."""
    per_day = _t("unit.kcal_per_day")
    _table(
        {
            _t("tdee.bmr"): f"{_n(result.bmr_kcal)} {per_day}",
            _t("tdee.factor"): _plain(result.activity_factor),
            _t("tdee.tdee"): f"{_n(result.tdee_kcal)} {per_day}",
        }
    )
    # The method is the tool's own text, the same the model received (English).
    st.caption(result.method)


def _macro_label(name: str) -> str:
    """Return a macro's name ("Protein", "Carbohydrate", "Fat") in the session's language."""
    return _t(f"macro.{name.lower()}")


def _kcal_encoding() -> dict:
    """Return the tooltip field of a chart's kcal: a formatted number, as the language writes it."""
    # Vega formats numbers the English way; German gets the text the app formatted itself.
    if _lang() == "de":
        return {"field": "kcal_text", "type": "nominal", "title": "kcal"}
    return {"field": "kcal", "type": "quantitative", "format": ","}


def _macro_bar(kcal: dict[str, int]) -> None:
    """Draw the kcal of each macro as one horizontal stacked bar, in the macro colours."""
    names = list(kcal)
    labels = [_macro_label(name) for name in names]
    # A Vega-Lite spec rather than st.bar_chart, so the value axis starts at 0 (st.bar_chart's
    # started at -500 in a narrow window). `alt` is the chart's text alternative.
    alt = _t(
        "chart.bar_alt",
        parts=", ".join(
            f"{label} {_n(value)} kcal" for label, value in zip(labels, kcal.values(), strict=True)
        ),
    )
    x = {
        "field": "kcal",
        "type": "quantitative",
        "stack": "zero",
        # From 0 to the next round value, so the bar never ends at the chart's edge.
        "scale": {"domainMin": 0, "nice": True},
        "title": _t("chart.kcal_per_day"),
    }
    if _lang() == "de":
        # German thousands marks on the axis ("2.000").
        x["axis"] = {"labelExpr": "replace(format(datum.value, ','), /,/g, '.')"}
    spec = {
        "mark": {"type": "bar"},
        "encoding": {
            "x": x,
            "y": {"field": "split", "type": "nominal", "title": None},
            "color": {
                "field": "macro",
                "type": "nominal",
                "sort": labels,
                "scale": {"domain": labels, "range": [config.MACRO_COLORS[n] for n in names]},
                "legend": {"orient": "bottom", "title": None},
            },
            # Typed as numbers: an untyped field is nominal, and a nominal kcal ignores the format.
            "order": {"field": "position", "type": "quantitative"},
            "tooltip": [{"field": "macro", "type": "nominal"}, _kcal_encoding()],
        },
    }
    data = {
        "macro": labels,
        "kcal": list(kcal.values()),
        "kcal_text": [_n(value) for value in kcal.values()],
        "split": [_t("chart.energy")] * len(names),
        "position": list(range(len(names))),
    }
    st.vega_lite_chart(data, spec, width="stretch", height=config.MACRO_CHART_HEIGHT_PX, alt=alt)


def _per_body_weight(macro: Macro, targets: MacroTargetsResult, system: units.UnitSystem) -> str:
    """Show a macro's grams per body weight in the user's units, rounded once."""
    # From the grams and the weight, not Macro.g_per_kg, which is already rounded to 0.1: rounding
    # it again showed 1.1 g/kg for 42 g at 40.1 kg (1.047; code review on PR #53).
    return units.format_grams_per_body_weight(macro.grams, targets.weight_kg or 0, system, _lang())


def _macro_cells(macro: Macro, targets: MacroTargetsResult, system: units.UnitSystem) -> list[str]:
    """Return one macro's grams, share of the kcal and grams per body weight, as table cells."""
    return [
        f"{_n(macro.grams)} g",
        _percent(macro.percent),
        _per_body_weight(macro, targets, system),
    ]


def _macro_parts(targets: MacroTargetsResult) -> dict[str, tuple[Macro, int]]:
    """Return each macro's target and its kcal per gram, by name, in the macro colours' order."""
    parts = {
        "Protein": (targets.protein, config.KCAL_PER_G_PROTEIN),
        "Carbohydrate": (targets.carbohydrate, config.KCAL_PER_G_CARBOHYDRATE),
        "Fat": (targets.fat, config.KCAL_PER_G_FAT),
    }
    return {name: (macro, kcal) for name, (macro, kcal) in parts.items() if macro is not None}


def _macro_kcal(targets: MacroTargetsResult) -> dict[str, int]:
    """Return the kcal a day each macro's target gives, by name."""
    return {name: macro.grams * kcal for name, (macro, kcal) in _macro_parts(targets).items()}


def _has_targets(result: object) -> bool:
    """Return whether a result holds complete daily targets to show."""
    return (
        isinstance(result, registry.MacroToolResult)
        and result.status == "ok"
        and result.targets.kcal_target is not None
        and bool(result.targets.weight_kg)
        and result.energy_needs.tdee_kcal is not None
        and len(_macro_parts(result.targets)) == len(config.MACRO_COLORS)
    )


def _session_targets() -> registry.MacroToolResult | None:
    """Return the daily targets for the session's profile, or None without a profile."""
    # Computed from the profile on every run (no model call), so they follow the goal and details.
    current = st.session_state.get("profile")
    if current is None:
        return None
    result = registry.macro_targets(current)
    if isinstance(result, registry.MacroToolResult) and _has_targets(result):
        return result
    return None


def _protein_range(targets: MacroTargetsResult, system: units.UnitSystem) -> str:
    """Return the sources' protein range for this body weight, in grams and per body weight."""
    # Always set with status "ok"; the fallback only satisfies the type.
    low, high = targets.protein_g_range or (0, 0)
    per_low, per_high = (
        units.format_per_body_weight(value, system, _lang())
        for value in config.PROTEIN_G_PER_KG_RANGE
    )
    return _t(
        "targets.protein_range", low=_n(low), high=_n(high), per_low=per_low, per_high=per_high
    )


def _show_macros(result: registry.MacroToolResult) -> None:
    """Show the daily targets as a table and the energy split as a stacked bar (AC-6)."""
    targets = result.targets
    # The second test only narrows the type: _has_targets() already checked it.
    if not _has_targets(result) or targets.kcal_target is None:
        st.caption(result.message)
        return
    system = st.session_state["units"]
    low, high = targets.kcal_range or (targets.kcal_target, targets.kcal_target)
    protein_low, protein_high = targets.protein_g_range or (0, 0)
    _table(
        {
            _t("targets.daily_target"): f"{_n(targets.kcal_target)} kcal",
            _t("macros.range"): f"{_n(low)}-{_n(high)} kcal",
            _t("macros.needs"): f"{_n(result.energy_needs.tdee_kcal)} kcal",
            _t("macros.protein_range"): f"{_n(protein_low)}-{_n(protein_high)} g",
        }
    )
    macros = _macro_parts(targets)
    # Per body weight in the units the user chose now (g/kg or g/lb; AC-8).
    cells = [_macro_cells(macro, targets, system) for macro, _ in macros.values()]
    st.dataframe(
        {
            _t("macros.macro"): [_macro_label(name) for name in macros],
            _t("macros.per_day"): [row[0] for row in cells],
            _t("macros.share"): [row[1] for row in cells],
            _t("macros.per_weight", unit=units.weight_unit(system)): [row[2] for row in cells],
        },
        hide_index=True,
        width="stretch",
    )
    # The energy split as one stacked bar; the numbers are in the table above, so colour is never
    # the only signal (docs/UI_DESIGN.md, Accessibility).
    _macro_bar(_macro_kcal(targets))
    # The tool's own message and notes, the same the model received (English).
    st.caption(result.message)
    for note in targets.notes:
        st.caption(f":material/info: {note}")


def _macro_donut(kcal: dict[str, int], total: int) -> None:
    """Draw the energy split as a donut in the macro colours, with the daily kcal in the middle."""
    names = list(kcal)
    labels = [_macro_label(name) for name in names]
    parts = ", ".join(
        f"{label} {_n(value)} kcal" for label, value in zip(labels, kcal.values(), strict=True)
    )
    alt = _t("chart.donut_alt", total=_n(total), parts=parts)
    # One text mark per line in the middle, each with its own one-row data, so it is drawn once.
    # Streamlit's chart theme colours axes and legends but not text marks (black in dark mode), so
    # the text takes the page's text colour through the SVG's currentColor.
    centre = [
        {
            "data": {"values": [{"line": line}]},
            "mark": {
                "type": "text",
                "fontSize": size,
                "fontWeight": weight,
                "dy": dy,
                "color": "currentColor",
            },
            "encoding": {"text": {"field": "line", "type": "nominal"}},
        }
        for line, size, weight, dy in ((_n(total), 17, "bold", -7), ("kcal", 12, "normal", 11))
    ]
    spec = {
        "layer": [
            {
                "mark": {
                    "type": "arc",
                    "innerRadius": config.MACRO_DONUT_INNER_RADIUS_PX,
                    # Gaps between the parts, so neighbouring colours never touch.
                    "padAngle": config.MACRO_DONUT_PAD_ANGLE,
                },
                "encoding": {
                    "theta": {"field": "kcal", "type": "quantitative", "stack": True},
                    "color": {
                        "field": "macro",
                        "type": "nominal",
                        "sort": labels,
                        "scale": {
                            "domain": labels,
                            "range": [config.MACRO_COLORS[n] for n in names],
                        },
                        "legend": {"orient": "right", "title": None},
                    },
                    "order": {"field": "position", "type": "quantitative"},
                    "tooltip": [{"field": "macro", "type": "nominal"}, _kcal_encoding()],
                },
            },
            *centre,
        ]
    }
    data = {
        "macro": labels,
        "kcal": list(kcal.values()),
        "kcal_text": [_n(value) for value in kcal.values()],
        "position": list(range(len(names))),
    }
    st.vega_lite_chart(data, spec, width="stretch", height=config.MACRO_DONUT_HEIGHT_PX, alt=alt)


def _targets_sidebar(system: units.UnitSystem) -> None:
    """Show the daily target and a summary card of the energy split in the sidebar (T4.7)."""
    result = _session_targets()
    if result is None:
        return
    targets = result.targets
    st.metric(_t("targets.daily_target"), f"{_n(targets.kcal_target)} kcal", border=True)
    with st.container(border=True):
        st.markdown(f"**:material/target: {_t('targets.my_targets')}**")
        _macro_donut(_macro_kcal(targets), targets.kcal_target or 0)
        # The values as text, so the colours are never the only signal.
        for name, (macro, _) in _macro_parts(targets).items():
            per_weight = _per_body_weight(macro, targets, system)
            share = _percent(macro.percent)
            st.caption(f"**{_macro_label(name)}** {_n(macro.grams)} g · {share} · {per_weight}")
        if targets.protein_lowered:
            st.caption(f":material/warning: {_t('targets.protein_lowered')}")
        st.caption(_t("targets.more"))


def _kcal_delta(difference: int) -> str | None:
    """Return the daily target's surplus or deficit against daily energy needs, or None."""
    # Short, as a longer delta is cut off in a quarter of the tab; the caption below says more.
    if difference == 0:
        return None
    return f"{'+' if difference > 0 else '-'}{_n(abs(difference))} kcal"


def _goal_line(goal: profile.Goal, difference: int) -> str:
    """Say the goal and how far the daily target is from daily energy needs."""
    name = _t(f"goal.{goal}")
    if difference == 0:
        return _t("targets.at_maintenance", goal=name)
    key = "targets.above_maintenance" if difference > 0 else "targets.below_maintenance"
    return _t(key, goal=name, kcal=_n(abs(difference)))


def _targets_tab() -> None:
    """Show the daily targets: four metrics, the energy split and how they were set (T4.7)."""
    st.subheader(f":material/target: {_t('targets.my_targets')}")
    result = _session_targets()
    if result is None:
        st.caption(_t("targets.empty"))
        st.button(
            _t("profile.add"),
            icon=":material/person_add:",
            key="targets_add_details",
            on_click=_open_profile_form,
        )
        return
    system = st.session_state["units"]
    targets, needs = result.targets, result.energy_needs
    difference = (targets.kcal_target or 0) - (needs.tdee_kcal or 0)
    kcal_column, *macro_columns = st.columns(1 + len(config.MACRO_COLORS))
    kcal_column.metric(
        _t("targets.daily_target"),
        f"{_n(targets.kcal_target)} kcal",
        # Grey with its sign: a deficit for fat loss is the plan, not a warning.
        delta=_kcal_delta(difference),
        delta_color="off",
        border=True,
    )
    if targets.goal is not None:
        kcal_column.caption(_goal_line(targets.goal, difference))
    macros = _macro_parts(targets).items()
    for column, (name, (macro, _)) in zip(macro_columns, macros, strict=True):
        column.metric(_macro_label(name), f"{_n(macro.grams)} g", border=True)
        per_weight = _per_body_weight(macro, targets, system)
        column.caption(_t("targets.share", percent=macro.percent, per_weight=per_weight))
    lowered = protein_lowered_note(targets.goal) if targets.goal is not None else None
    if targets.protein_lowered and lowered:
        st.warning(
            _t("targets.protein_warning", note=lowered, range=_protein_range(targets, system)),
            icon=":material/warning:",
        )
    _macro_bar(_macro_kcal(targets))
    maintenance = _t("targets.maintenance", kcal=_n(needs.tdee_kcal), method=needs.method)
    st.caption(f":material/local_fire_department: {maintenance}")
    # The tool's own message, notes and sources, the same the model received (English).
    st.caption(result.message)
    for note in targets.notes:
        if note != lowered:
            st.caption(f":material/info: {note}")
    sources = "\n".join(f"- {source}" for source in [*needs.sources, *targets.sources])
    st.caption(f":material/menu_book: {_t('targets.sources')}\n{sources}")


def _fiber_text(fiber_g: float | None) -> str:
    """Return a food's fiber in grams, or "not reported" when USDA gives no value."""
    return _t("food.not_reported") if fiber_g is None else f"{_plain(fiber_g)} g"


def _food_tab_message(result: registry.ToolResult) -> str:
    """Return why a Food lookup tab lookup gave no result, in the session's language."""
    # The tab calls no model, so its messages follow the language (owner's choice in the review
    # of PR #74); English keeps the lookup's own fixed text. The dropdown and the grams widget
    # keep both in range, so an invalid lookup is not expected; a food is never "not found".
    if _lang() == "en":
        return result.message
    return _t("food.tab.invalid" if result.status == "invalid" else "food.tab.error")


def _food_result(result: registry.ToolResult) -> None:
    """Show a lookup from the Food lookup tab: the food and its nutrients, or why not."""
    # Every message is fixed text that never repeats the input.
    if result.status == "invalid":
        st.warning(_food_tab_message(result), icon=":material/edit:")
        return
    if not isinstance(result, FoodLookupResult) or result.nutrients is None:
        # The foods table is missing or broken.
        st.error(_food_tab_message(result), icon=":material/error:")
        return
    nutrients = result.nutrients
    st.caption(_t("food.matched", grams=result.grams))
    # Plain text: a USDA name is never read as Markdown (docs/SECURITY.md). USDA names stay English.
    st.text(result.matched_name or "")
    energy, protein, carbohydrate, fat = st.columns(4)
    energy.metric(_t("nutrient.energy"), f"{_n(nutrients.kcal)} kcal", border=True)
    protein.metric(_t("nutrient.protein"), f"{_plain(nutrients.protein_g)} g", border=True)
    carbohydrate.metric(
        _t("nutrient.carbohydrate"), f"{_plain(nutrients.carbohydrate_g)} g", border=True
    )
    fat.metric(_t("nutrient.fat"), f"{_plain(nutrients.fat_g)} g", border=True)
    st.caption(_t("food.fiber_line", fiber=_fiber_text(nutrients.fiber_g)))
    st.caption(_t("usda.source_line"))


def _food_tab() -> None:
    """Look up the nutrients of a food and amount in the USDA table, with no model call (T4.7)."""
    st.subheader(f":material/search: {_t('food.title')}")
    # The dropdown lists the table's own foods, so a visitor sees what can be looked up (T4.8).
    try:
        names = food_names()
    except Exception:
        # A missing or broken table (FoodTableError) or one that cannot be read at all (e.g. not
        # UTF-8): the fixed message, never the exception's text, and the rest of the page still
        # draws (the Details tab and the sidebar come after this tab).
        names = ()
        st.error(_t("food.tab.error"), icon=":material/error:")
    food_column, grams_column, button_column = st.columns([4, 1, 1], vertical_alignment="bottom")
    food = food_column.selectbox(
        _t("food.food"),
        names,
        index=None,
        key="food_query",
        placeholder=_t("food.placeholder"),
        disabled=not names,
    )
    grams = grams_column.number_input(
        _t("food.grams"),
        min_value=config.FOOD_MIN_GRAMS,
        max_value=float(config.FOOD_MAX_GRAMS),
        value=config.FOOD_LOOKUP_DEFAULT_GRAMS,
        step=config.FOOD_LOOKUP_STEP_GRAMS,
        format="%.1f",
        key="food_grams",
    )
    if button_column.button(
        _t("food.look_up"),
        icon=":material/search:",
        key="food_lookup",
        type="primary",
        width="stretch",
        disabled=food is None,
    ):
        # Kept for the session, so the result stays while other widgets rerun the page.
        st.session_state["food_result"] = registry.run_chosen_food_lookup(food, grams)
    # The caption also says the food names are English: the USDA table has English names only.
    st.caption(_t("food.caption"))
    result = st.session_state.get("food_result")
    if result is not None:
        _food_result(result)


def _show_food(result: FoodLookupResult) -> None:
    """Show a food lookup: the matched USDA food and its nutrients, or the suggestions."""
    if result.status != "found" or result.nutrients is None:
        st.caption(result.message)
        if result.alternatives:
            # USDA names as table cells: plain text, never Markdown.
            st.dataframe(
                {_t("food.did_you_mean"): result.alternatives}, hide_index=True, width="stretch"
            )
        return
    nutrients = result.nutrients
    rows = {
        _t("food.usda_food"): result.matched_name or "",
        _t("food.amount"): f"{_plain(result.grams)} g",
        _t("nutrient.energy"): f"{_n(nutrients.kcal)} kcal",
        _t("nutrient.protein"): f"{_plain(nutrients.protein_g)} g",
        _t("nutrient.carbohydrate"): f"{_plain(nutrients.carbohydrate_g)} g",
        _t("nutrient.fat"): f"{_plain(nutrients.fat_g)} g",
        _t("nutrient.fiber"): _fiber_text(nutrients.fiber_g),
    }
    if result.alternatives:
        rows[_t("food.close_alternatives")] = "; ".join(result.alternatives)
    _table(rows)
    st.caption(_t("usda.source_line"))


def _columns(names: tuple[str, ...], rows: list[list[str]]) -> dict[str, list[str]]:
    """Return rows of cells as columns by name, for st.dataframe."""
    return {name: [row[i] for row in rows] for i, name in enumerate(names)}


def _show_meal_plan(result: MealPlanResult) -> None:
    """Show a meal plan check: each food, then the totals against the daily targets (T4.5)."""
    lang = _lang()
    # The names asked for and the USDA names as table cells: plain text, never Markdown.
    columns = meal_plan.food_columns(lang)
    foods = _columns(columns, [meal_plan.food_row(item, lang) for item in result.items])
    other_names = _t("meal.other_names")
    foods[other_names] = ["; ".join(item.alternatives) for item in result.items]
    # A long name would take the whole width and push the values out of view; a capped column
    # cuts it and shows it in full on hover.
    names = {
        column: st.column_config.TextColumn(width="medium")
        for column in (columns[0], columns[1], other_names)
    }
    st.dataframe(foods, hide_index=True, width="stretch", column_config=names)
    comparison = meal_plan.comparison_rows(result, lang)
    if comparison:
        st.dataframe(
            _columns(meal_plan.comparison_columns(lang), comparison),
            hide_index=True,
            width="stretch",
        )
    # The tool's own message and notes, the same the model received (English).
    st.caption(result.message)
    for note in result.notes:
        st.caption(f":material/info: {note}")
    st.caption(_t("meal.source_line"))


def _show_tool_run(run: registry.ToolRun, key: str) -> None:
    """Show one tool result under its heading; without a profile, a button opens the form."""
    name = run.name if run.name in registry.TOOL_TITLES else None
    st.markdown(f"**{TOOL_ICONS[name]} {_t(f'tool.title.{name or "none"}')}**")
    result = run.result
    if run.status == "profile_needed":
        st.info(_t("tool.profile_needed"), icon=":material/person_add:")
        st.button(
            _t("profile.add"), icon=":material/person_add:", key=key, on_click=_open_profile_form
        )
    elif isinstance(result, TdeeResult) and result.status == "ok":
        _show_tdee(result)
    elif isinstance(result, registry.MacroToolResult) and result.status == "ok":
        _show_macros(result)
    elif isinstance(result, FoodLookupResult) and result.status != "invalid":
        _show_food(result)
    elif isinstance(result, MealPlanResult) and result.status != "invalid":
        _show_meal_plan(result)
    else:
        # A refused or failed call: the fixed message the model got, never what it sent.
        st.caption(result.message)


def _show_tool_runs(runs: tuple[registry.ToolRun, ...], turn: int) -> None:
    """Show each tool result of a turn in one "Tool results" expander (AC-6)."""
    # Open when a result needs the profile, so the "Add your details" button is in view.
    needs_profile = any(run.status == "profile_needed" for run in runs)
    with st.expander(
        _t("tool.results", count=len(runs)), icon=":material/calculate:", expanded=needs_profile
    ):
        for number, run in enumerate(runs):
            if number:
                st.divider()
            _show_tool_run(run, key=f"tool_profile_{turn}_{number}")


def _fixed_text(result: chat.TurnResult) -> str:
    """Return a turn's fixed message in the language chosen now, or the model's own answer."""
    # Past turns follow the language too; the answer stays in the language it was written in.
    return chat.fixed_text(result, _lang())


def _show_result(result: chat.TurnResult, turn: int) -> None:
    """Show a turn's answer with its sources and tool results, or its fixed message."""
    if result.kind == "rejected":
        st.warning(_fixed_text(result), icon=":material/block:")
    elif result.kind == "guardrail":
        # A refusal or a pointer to a professional (AC-12), not an error.
        st.info(_fixed_text(result), icon=":material/health_and_safety:")
    elif result.kind == "error":
        st.error(_fixed_text(result), icon=":material/error:")
    else:
        # Model output as Markdown, never with unsafe_allow_html (docs/SECURITY.md).
        st.markdown(_fixed_text(result))
        if result.sources:
            with st.expander(
                _t("sources.count", count=len(result.sources)), icon=":material/menu_book:"
            ):
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
        _usage_caption(message.get("usage"))


def _last_searched() -> dict | None:
    """Return the message of the latest turn that reached the search, or None before any."""
    for message in reversed(st.session_state["messages"]):
        if message["role"] == "assistant" and message["result"].search is not None:
            return message
    return None


def _session_usage() -> usage.SessionUsage:
    """Add up the tokens and the known cost of every turn of the session (AC-10)."""
    turns = [m["usage"] for m in st.session_state["messages"] if m.get("usage") is not None]
    return usage.session_usage(turns)


def _usage_step(step: str) -> str:
    """Return the name of a call's step in the session's language."""
    if step == config.USAGE_STEP_REWRITE:
        return _t("usage.step.rewrite")
    if step == config.USAGE_STEP_SEARCH:
        return _t("usage.step.search")
    answer = _ANSWER_STEP.fullmatch(step)
    return _t("usage.step.answer", round=int(answer[1])) if answer else step


def _usage_rows(turn_usage: usage.TurnUsage) -> dict[str, list]:
    """Return a turn's calls as table columns: step, model, the token counts and the cost."""
    rows = [
        [
            _usage_step(call.step),
            call.model,
            call.input_tokens,
            call.cached_tokens,
            call.output_tokens,
            call.reasoning_tokens,
            usage.format_cost(cost, _lang()),
        ]
        for call, cost in zip(turn_usage.calls, turn_usage.costs, strict=True)
    ]
    names = [_t(f"usage.col.{column}") for column in USAGE_COLUMNS]
    return {name: [row[i] for row in rows] for i, name in enumerate(names)}


def _usage_section(turn_usage: usage.TurnUsage | None) -> None:
    """Show the tokens and cost of each call of the last answer, and the session totals."""
    lang = _lang()
    st.subheader(f"{USAGE_ICON} {_t('usage.title')}")
    if turn_usage is not None and turn_usage.calls:
        st.dataframe(_usage_rows(turn_usage), hide_index=True)
        this_answer = _dollars(usage.format_turn(turn_usage, lang))
        st.markdown(_bold_label(_t("usage.this_answer", usage=this_answer)))
    else:
        st.caption(_t("usage.no_calls"))
    session = _dollars(usage.format_session(_session_usage(), lang))
    st.markdown(_bold_label(_t("usage.this_session", usage=session)))
    st.caption(_t("usage.explain"))


def _bold_label(line: str) -> str:
    """Return "Label: value" with the label in bold: "**This answer:** 1,234 tokens"."""
    label, value = line.split(": ", 1)
    return f"**{label}:** {value}"


def _one_line(text: str) -> str:
    """Return text on one line, escaped, so it adds no formatting, image or link to a list."""
    # GFM still links a bare "www." or e-mail address (no scheme, nothing to escape); it is shown,
    # never loaded, and no raw HTML gets through.
    line = chat.escape_markdown(" ".join(text.split()))
    # A line start Markdown reads as a heading, quote, list or rule ("# Big", "> x", "1. x").
    return _LINE_START.sub(r"\1\\\2", line)


def _topic_label(topic: str) -> str:
    """Return a topic filter's name, or the topic itself if the app does not know it."""
    return _t(f"topic.{topic}") if topic in config.TOPICS else topic


def _filter_badges(details: chat.SearchDetails) -> None:
    """Show the filters the rewrite step chose as badges, or say there were none."""
    if not details.has_filters:
        st.badge(_t("filter.none"), icon=":material/filter_alt_off:", color="gray")
        return
    with st.container(horizontal=True, gap="small"):
        for topic in details.topics:
            st.badge(_topic_label(topic), icon=":material/sell:", color="blue")
        if details.min_year is not None:
            year = _t("filter.from_year", year=str(details.min_year))
            st.badge(year, icon=":material/calendar_month:", color="blue")
        if details.evidence_tier is not None:
            tier = details.evidence_tier
            label = (
                _t(f"tier_filter.{tier}") if tier in config.EVIDENCE_TIERS else _tier_label(tier)
            )
            st.badge(label, icon=":material/verified:", color="blue")


def _routing_badges(result: chat.TurnResult) -> None:
    """Show whether the rewrite step expected a tool, and whether <profile> was sent (T3.5)."""
    if result.search is None or result.search.needs_tool is None:
        # No usable plan: the note from _search_notes() says what happened instead.
        return
    st.markdown(f"**{_t('routing.title')}**")
    with st.container(horizontal=True, gap="small"):
        if result.search.needs_tool:
            st.badge(_t("routing.tool"), icon=":material/build:", color="blue")
        else:
            st.badge(_t("routing.no_tool"), icon=":material/build:", color="gray")
        # What the answer model really got: no block when no answer call was made, even if
        # the plan asked for one. Tool results can still name some values (docs/SECURITY.md).
        if result.profile_sent:
            st.badge(_t("routing.profile_sent"), icon=":material/person:", color="blue")
        else:
            st.badge(_t("routing.profile_not_sent"), icon=":material/person_off:", color="gray")


def _search_notes(details: chat.SearchDetails) -> None:
    """Say when the rewrite step gave nothing usable or the filters were dropped."""
    if details.fell_back:
        st.caption(f":material/info: {_t('search.fell_back')}")
    if details.filter_dropped:
        st.caption(f":material/filter_alt_off: {_t('search.filter_dropped')}")


def _details_tab() -> None:
    """Show how the last answer was found: what was searched and the filters used (AC-3)."""
    message = _last_searched()
    st.subheader(f":material/manage_search: {_t('details.title')}")
    if message is None:
        st.caption(_t("details.empty"))
        return
    details = message["result"].search
    st.markdown(f"**{_t('details.searched_for')}**")
    # The question is the user's text and the rewrites the model's: both shown escaped.
    lines = [f"1. {_one_line(details.question)} *{_t('details.your_question')}*"]
    lines += [
        f"{number}. {_one_line(rewrite)}" for number, rewrite in enumerate(details.rewrites, 2)
    ]
    st.markdown("\n".join(lines))
    st.markdown(f"**{_t('details.filters')}**")
    _filter_badges(details)
    _routing_badges(message["result"])
    _search_notes(details)
    _usage_section(message.get("usage"))


def _last_answer_card() -> None:
    """Show a short summary of how the last answer was found, and its cost, in the sidebar."""
    lang = _lang()
    message = _last_searched()
    if message is None:
        # No turn has searched yet, but one may have spent tokens before failing (AC-10).
        session = _session_usage()
        if session.tokens:
            line = _t("usage.session", usage=_dollars(usage.format_session(session, lang)))
            st.caption(f"{USAGE_ICON} {line}")
        return
    details = message["result"].search
    with st.container(border=True):
        st.markdown(f"**:material/manage_search: {_t('card.last_answer')}**")
        # Names the question, as a rejected or failed turn leaves an earlier search here.
        question = _one_line(details.question)
        if len(question) > config.CARD_QUESTION_CHARS:
            question = question[: config.CARD_QUESTION_CHARS].rstrip("\\ ") + "…"
        st.caption(_t("card.for", question=question))
        if details.rewrites:
            rewrites = len(details.rewrites)
            key = "card.searched_one" if rewrites == 1 else "card.searched_many"
            st.caption(_t(key, queries=len(details.queries), rewrites=rewrites))
        else:
            st.caption(_t("card.question_only"))
        _filter_badges(details)
        if details.filter_dropped:
            st.caption(_t("card.filters_dropped"))
        turn_usage = message.get("usage")
        if turn_usage is not None and turn_usage.calls:
            this_answer = _dollars(usage.format_turn(turn_usage, lang))
            st.caption(f"{USAGE_ICON} {_t('usage.this_answer', usage=this_answer)}")
        session = _dollars(usage.format_session(_session_usage(), lang))
        st.caption(f"{USAGE_ICON} {_t('usage.session', usage=session)}")
        st.caption(_t("card.more"))


def _ask_tab() -> None:
    """Show the chat: the history, then the input; a new question runs one turn."""
    history = st.session_state["messages"]
    box = st.container(height=config.CHAT_HEIGHT_PX)
    with box:
        invitation = st.empty()
        if not history:
            invitation.caption(_t("ask.invitation"))
        for turn, message in enumerate(history):
            _show_message(message, turn)
    question = st.chat_input(_t("ask.placeholder"), key="chat_input")
    if not question:
        return
    invitation.empty()
    history.append({"role": "user", "text": question})
    with box:
        _show_message(history[-1], len(history) - 1)
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            _run_turn(question, len(history))


def _about_content(manifest) -> None:
    """Say what the answers are based on and credit every source (the About dialog's body)."""
    summary = chat.knowledge_base_summary(manifest)
    articles = _t(
        "about.articles",
        articles=summary.articles,
        stands=summary.position_stands,
        reviews=summary.reviews,
        licenses=_t("about.and").join(summary.licenses),
    )
    models = _t(
        "about.models",
        rewrite_model=config.QUERY_TRANSLATION_MODEL,
        answer_model=config.DEFAULT_ANSWER_MODEL,
    )
    st.markdown(f"- {articles}\n- {_t('about.method')}\n- {models}")
    # Credits every source (copyright policy rule 6): authors, title, journal, licence, link,
    # and the change made with the no-endorsement note, as in ATTRIBUTION.md. The credits
    # themselves stay as the articles give them.
    st.markdown(f"**:material/license: {_t('about.credits')}**")
    article = _t("about.article")
    for source in manifest.values():
        st.markdown(
            f"**{source.id}.** {chat.escape_markdown(chat.format_authors(source.authors))}. "
            f"{chat.escape_markdown(source.title)} ({source.year}). "
            f"{chat.escape_markdown(source.journal)}. "
            f"[{source.license}]({chat.markdown_url(source.license_url)}) · "
            f"[{article}]({chat.markdown_url(source.url)})"
        )
    st.caption(f"{_t('about.changes')} {_t('about.full_credits')}")


@st.fragment
def _about_button(manifest) -> None:
    """Draw the button that opens the About dialog; a press reruns only this fragment."""
    # A fragment, so a press while an answer streams does not rerun the script and stop that
    # turn: Streamlit runs the fragment once the turn ends, and the dialog opens then (T3.9).
    opened = st.button(
        _t("about.title"), icon=":material/menu_book:", width="stretch", key="about_open"
    )
    # Streamlit allows one dialog per run: with the profile form open, a press changes nothing.
    if opened and not st.session_state.get("profile_form_open"):
        # Built in the run of the press, so the dialog's title is in the language chosen now.
        st.dialog(_t("about.title"), width="large")(_about_content)(manifest)


def _about_sidebar() -> None:
    """Put a button in the sidebar that opens the About dialog."""
    manifest = _manifest()
    if not manifest:
        return
    st.divider()
    # A dialog, not an expander: the 20 credits are long and the sidebar is narrow (T3.9). The
    # content is static, so it needs no session state to stay open; a click draws it in that run.
    _about_button(manifest)


def _summary_download() -> None:
    """Offer the session summary as a PDF, built in memory only when clicked (AC-9)."""
    # Drawn after the main area, so the turn that just ran is in it. The PDF is built from this
    # run's snapshot when the user clicks; Streamlit keeps the bytes in memory, never on disk. It
    # is in the language chosen now (T7.2), bound here: the click may build it outside the run.
    turns = export_pdf.session_turns(st.session_state["messages"])
    user = st.session_state.get("profile")
    system = st.session_state["units"]
    manifest = _manifest()
    lang = _lang()
    # One date for the file name and the PDF, even if the click comes after midnight.
    today = date.today()

    def build() -> bytes:
        """Build the PDF from this run's session, in this run's language."""
        return export_pdf.build_summary_pdf(turns, user, system, manifest, today, lang)

    empty = user is None and not turns
    st.download_button(
        _t("pdf.label"),
        data=build,
        file_name=config.PDF_FILE_NAME.format(date=today.isoformat()),
        mime="application/pdf",
        icon=":material/download:",
        # The download needs no rerun of the app.
        on_click="ignore",
        disabled=empty,
        help=_t("pdf.empty_help") if empty else _t("pdf.help"),
        key="summary_pdf",
        width="stretch",
    )


def _language_control() -> None:
    """Show the EN | DE switch: an icon and a segmented control whose label is collapsed."""
    with st.container(horizontal=True, gap="small", vertical_alignment="center", width="content"):
        st.markdown(":material/translate:")
        # required=True: a click on the chosen language cannot deselect it to None. The value is
        # the session's language, written before the control is drawn (no default here).
        st.segmented_control(
            _t("language.label"),
            i18n.LANGUAGES,
            format_func=i18n.LANGUAGE_LABELS.get,
            required=True,
            key=i18n.SESSION_KEY,
            label_visibility="collapsed",
        )


def _main_area() -> None:
    """Show the header, the disclaimer and the four tabs."""
    with st.container(
        horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"
    ):
        st.title(_t("app.title"))
        with st.container(
            horizontal=True, gap="medium", vertical_alignment="center", width="content"
        ):
            st.badge(
                _t("app.not_medical_advice"),
                icon=":material/info:",
                color="orange",
                help=_t("app.disclaimer"),
            )
            _language_control()
    st.markdown(_t("app.intro"))
    # Shown on every page state (AC-12), large enough to notice (owner's request, 2026-10-20).
    st.warning(
        f"**{_t('app.not_medical_advice')}.** {_t('app.disclaimer')}", icon=":material/info:"
    )

    ask, targets, food, details = st.tabs(
        [
            f":material/chat: **{_t('tab.ask')}**",
            f":material/target: **{_t('tab.targets')}**",
            f":material/search: **{_t('tab.food')}**",
            f":material/list: **{_t('tab.details')}**",
        ]
    )
    with ask:
        _ask_tab()
    with targets:
        _targets_tab()
    with food:
        _food_tab()
    with details:
        _details_tab()


with st.sidebar:
    _profile_sidebar()
    st.caption(_t("theme.hint"))
    # Both slots are filled after the main area, so they hold the turn that just ran (the PDF too);
    # until then the page keeps the previous run's card. Drawn once per run: a slot drawn twice in
    # one run keeps the first draw's extra elements (e.g. a badge the new turn does not have).
    download_slot = st.empty()
    last_answer_slot = st.empty()
    _about_sidebar()
if st.session_state.get("profile_form_open"):
    # Built on each run, so the dialog's title is in the language chosen now.
    st.dialog(_t("profile.dialog_title"), on_dismiss=_close_profile_form)(_profile_form)()


# The content sits in the middle column of the wide layout (config.PAGE_COLUMN_WEIGHTS).
_, main, _ = st.columns(config.PAGE_COLUMN_WEIGHTS)
with main:
    _main_area()
with download_slot.container():
    _summary_download()
with last_answer_slot.container():
    _last_answer_card()
