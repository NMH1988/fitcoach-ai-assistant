"""UI tests for the profile sidebar and the "Your details" dialog (T4.1, AC-5, AC-8)."""

import logging
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.profile import UserProfile

APP = Path(__file__).resolve().parent.parent / "app.py"

pytestmark = pytest.mark.usefixtures("no_env_key")


def _key(field: str) -> str:
    """Return the session state key of a profile form field, as app.py names it."""
    return f"profile_form_{field}"


def _start() -> AppTest:
    """Run app.py once with no API key and return the test handle."""
    at = AppTest.from_file(str(APP))
    at.secrets["UNRELATED"] = "x"
    at.run(timeout=30)
    return at


def _button(at: AppTest, label: str):
    """Return the one button with this label."""
    (found,) = [button for button in at.button if button.label == label]
    return found


def _metric(at: AppTest, label: str) -> str:
    """Return the value of the sidebar metric with this label."""
    (found,) = [metric for metric in at.sidebar.metric if metric.label == label]
    return found.value


def _fill_metric(at: AppTest, *, weight=80.0, height_cm=180, age=30) -> AppTest:
    """Fill every field of the open form in metric units."""
    at.number_input(key=_key("weight")).set_value(weight)
    at.number_input(key=_key("height_cm")).set_value(height_cm)
    at.number_input(key=_key("age")).set_value(age)
    at.segmented_control(key=_key("sex")).set_value("male")
    at.selectbox(key=_key("activity")).set_value("moderate")
    at.segmented_control(key=_key("goal")).set_value("build_muscle")
    return at


def _save(at: AppTest) -> AppTest:
    """Press Save in the dialog."""
    return _button(at, "Save").click().run(timeout=30)


def _add_metric_profile(**values) -> AppTest:
    """Open the dialog, fill it in metric units, save it and return the test handle."""
    at = _start()
    _button(at, "Add your details").click().run(timeout=30)
    return _save(_fill_metric(at, **values))


def test_without_a_profile_the_sidebar_invites_to_add_one():
    """Before a profile exists, the sidebar shows an invitation and no tiles."""
    at = _start()
    assert not at.exception
    assert _button(at, "Add your details")
    assert not at.sidebar.metric
    assert "profile" not in at.session_state


def test_the_form_opens_in_metric_units_by_default():
    """The dialog starts empty, in kg and cm, with a units switch."""
    at = _start()
    _button(at, "Add your details").click().run(timeout=30)
    assert at.segmented_control(key="profile_form_units").value == "metric"
    assert at.number_input(key=_key("weight")).label == "Weight (kg)"
    assert at.number_input(key=_key("height_cm")).value is None


def test_a_valid_metric_profile_is_saved_and_shown():
    """Saving a valid profile keeps it in session state and shows it as sidebar tiles."""
    at = _add_metric_profile()
    assert not at.exception and not at.error
    assert at.session_state["profile"] == UserProfile(
        weight_kg=80.0,
        height_cm=180.0,
        age=30,
        sex="male",
        activity="moderate",
        goal="build_muscle",
    )
    assert _metric(at, "Weight") == "80 kg"
    assert _metric(at, "Height") == "180 cm"
    assert _metric(at, "Age") == "30"
    assert _metric(at, "Sex") == "Male"
    assert _metric(at, "Activity") == "Moderate · 4-5 times"
    assert at.sidebar.segmented_control(key="sidebar_goal").value == "build_muscle"
    assert "Save" not in [button.label for button in at.button]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"age": 17}, "This app is for adults aged 18 and over"),
        ({"weight": 25.0}, "Weight must be between 30 and 300 kg."),
        ({"height_cm": 250}, "Height must be between 120 and 230 cm."),
    ],
)
def test_invalid_values_show_a_clear_message_and_nothing_is_saved(values, message):
    """Out-of-range values and ages under 18 are rejected in the dialog (AC-5)."""
    at = _add_metric_profile(**values)
    assert not at.exception
    assert message in at.error[0].value
    assert "profile" not in at.session_state
    assert _button(at, "Save")


def test_switching_units_converts_the_typed_values():
    """Switching to imperial in the dialog changes the inputs and keeps the values (AC-8)."""
    at = _start()
    _button(at, "Add your details").click().run(timeout=30)
    _fill_metric(at).run(timeout=30)
    at.segmented_control(key="profile_form_units").set_value("imperial").run(timeout=30)
    assert at.number_input(key=_key("weight")).label == "Weight (lb)"
    assert at.number_input(key=_key("weight")).value == pytest.approx(176.4)
    assert at.number_input(key=_key("height_ft")).value == 5
    assert at.number_input(key=_key("height_in")).value == 11
    assert not [field for field in at.number_input if field.key == _key("height_cm")]

    at.segmented_control(key="profile_form_units").set_value("metric").run(timeout=30)
    assert at.number_input(key=_key("weight")).value == pytest.approx(80.0)
    assert at.number_input(key=_key("height_cm")).value == 180


def test_saving_in_imperial_changes_the_displayed_values_and_back():
    """The sidebar shows the chosen units; switching back shows the first values (AC-8)."""
    at = _add_metric_profile()
    _button(at, "Edit details").click().run(timeout=30)
    assert at.number_input(key=_key("weight")).value == pytest.approx(80.0)
    at.segmented_control(key="profile_form_units").set_value("imperial").run(timeout=30)
    _save(at)
    assert at.session_state["units"] == "imperial"
    assert _metric(at, "Weight") == "176.4 lb"
    assert _metric(at, "Height") == "5 ft 11 in"

    _button(at, "Edit details").click().run(timeout=30)
    assert at.segmented_control(key="profile_form_units").value == "imperial"
    at.segmented_control(key="profile_form_units").set_value("metric").run(timeout=30)
    _save(at)
    assert _metric(at, "Weight") == "80 kg"
    assert _metric(at, "Height") == "180 cm"
    # Only the units changed, so the stored kg and cm are kept as they were, not re-rounded.
    assert at.session_state["profile"].weight_kg == 80.0
    assert at.session_state["profile"].height_cm == 180.0


def test_saving_after_units_switches_only_keeps_the_weight_typed_in_lb():
    """176.5 lb saved, then saved in metric and back in imperial unedited, still shows 176.5 lb."""
    at = _start()
    _button(at, "Add your details").click().run(timeout=30)
    at.segmented_control(key="profile_form_units").set_value("imperial").run(timeout=30)
    at.number_input(key=_key("weight")).set_value(176.5)
    at.number_input(key=_key("height_ft")).set_value(5)
    at.number_input(key=_key("height_in")).set_value(11)
    at.number_input(key=_key("age")).set_value(30)
    at.segmented_control(key=_key("sex")).set_value("male")
    at.selectbox(key=_key("activity")).set_value("moderate")
    at.segmented_control(key=_key("goal")).set_value("maintain")
    _save(at)
    stored = at.session_state["profile"]
    for system in ("metric", "imperial"):
        _button(at, "Edit details").click().run(timeout=30)
        at.segmented_control(key="profile_form_units").set_value(system).run(timeout=30)
        _save(at)
    assert at.session_state["profile"] == stored
    assert _metric(at, "Weight") == "176.5 lb"


def test_switching_units_twice_gives_back_exactly_what_was_typed():
    """Flipping to imperial and back without editing restores the typed metric values."""
    at = _start()
    _button(at, "Add your details").click().run(timeout=30)
    _fill_metric(at, weight=80.1, height_cm=179).run(timeout=30)
    at.segmented_control(key="profile_form_units").set_value("imperial").run(timeout=30)
    at.segmented_control(key="profile_form_units").set_value("metric").run(timeout=30)
    assert at.number_input(key=_key("weight")).value == pytest.approx(80.1)
    assert at.number_input(key=_key("height_cm")).value == 179


def test_an_imperial_profile_is_stored_in_kg_and_cm():
    """Values typed in lb and ft/in are stored in kg and cm."""
    at = _start()
    _button(at, "Add your details").click().run(timeout=30)
    at.segmented_control(key="profile_form_units").set_value("imperial").run(timeout=30)
    at.number_input(key=_key("weight")).set_value(150.0)
    at.number_input(key=_key("height_ft")).set_value(5)
    at.number_input(key=_key("height_in")).set_value(6)
    at.number_input(key=_key("age")).set_value(40)
    at.segmented_control(key=_key("sex")).set_value("female")
    at.selectbox(key=_key("activity")).set_value("light")
    at.segmented_control(key=_key("goal")).set_value("lose_fat")
    _save(at)
    saved = at.session_state["profile"]
    assert saved.weight_kg == pytest.approx(68.04, abs=0.01)
    assert saved.height_cm == pytest.approx(167.64)
    assert _metric(at, "Weight") == "150 lb"
    assert _metric(at, "Height") == "5 ft 6 in"


def test_the_sidebar_goal_changes_the_profile():
    """Picking another goal in the sidebar updates the saved profile."""
    at = _add_metric_profile()
    at.sidebar.segmented_control(key="sidebar_goal").set_value("lose_fat").run(timeout=30)
    assert at.session_state["profile"].goal == "lose_fat"
    assert at.session_state["profile"].weight_kg == 80.0


def test_closing_the_dialog_keeps_the_saved_profile():
    """Editing and dismissing the dialog without saving changes nothing."""
    at = _add_metric_profile()
    _button(at, "Edit details").click().run(timeout=30)
    at.number_input(key=_key("weight")).set_value(95.0).run(timeout=30)
    at.session_state["profile_form_open"] = False  # what the dialog's on_dismiss callback does
    at.run(timeout=30)
    assert at.session_state["profile"].weight_kg == 80.0
    assert _metric(at, "Weight") == "80 kg"


def test_the_profile_stays_in_the_session_and_out_of_logs_and_the_url(caplog, capsys):
    """The profile lives only in session state: no log record, output or URL holds its values."""
    # Streamlit's loggers do not propagate to the root and set their own levels, so capture
    # them directly, at DEBUG, and restore them afterwards.
    names = ["streamlit"] + [
        name for name in logging.root.manager.loggerDict if name.startswith("streamlit.")
    ]
    loggers = [logging.getLogger(name) for name in names]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.DEBUG)
    logging.getLogger("streamlit").addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG):
            at = _add_metric_profile(weight=87.3, height_cm=193, age=47)
    finally:
        logging.getLogger("streamlit").removeHandler(caplog.handler)
        for logger, level in zip(loggers, levels, strict=True):
            logger.setLevel(level)
    assert at.session_state["profile"].weight_kg == 87.3
    output = capsys.readouterr()
    for value in ("87.3", "193", "47"):
        assert value not in caplog.text
        assert value not in output.out + output.err
    assert not dict(at.query_params)


def test_disclaimer_stays_visible_with_a_profile():
    """The disclaimer is still shown once a profile exists."""
    at = _add_metric_profile()
    assert any("Not medical advice" in box.value for box in at.warning)


# --- T4.6: a hint instead of "Press Enter to apply" --------------------------------------------


def _open_dialog() -> AppTest:
    """Run the app and open the "Your details" dialog."""
    at = _start()
    return _button(at, "Add your details").click().run(timeout=30)


def _first_element(block):
    """Return the first element (not container) drawn inside a block."""
    node = block
    while getattr(node, "children", None):
        node = next(iter(node.children.values()))
    return node


def test_the_hint_is_the_first_line_of_the_dialog():
    """The dialog opens with the hint on how values are applied and saved (T4.6)."""
    [dialog] = _open_dialog().get("dialog")
    first = _first_element(dialog)
    assert first.type == "caption"
    assert first.value == f":material/info: {config.PROFILE_FORM_HINT}"
    # The exact sentence the owner approved for T4.6.
    assert config.PROFILE_FORM_HINT == (
        "Type your values, then press Save. Values are checked when you save."
    )


def test_the_css_is_drawn_only_while_the_dialog_is_open():
    """The style rule exists with the dialog open, not before it opens or after Save closes it."""
    at = _start()
    assert [h.value for h in at.html] == []
    _button(at, "Add your details").click().run(timeout=30)
    assert [h.value for h in at.html] == [config.PROFILE_DIALOG_CSS]
    at = _save(_fill_metric(at))
    assert "profile" in at.session_state
    assert [h.value for h in at.html] == []


def test_the_dialog_css_is_one_fixed_rule_scoped_to_the_dialog():
    """The CSS hides only the input instructions inside the dialog and holds nothing else."""
    css = config.PROFILE_DIALOG_CSS
    assert css == (
        '<style>[data-testid="stDialog"] [data-testid="InputInstructions"] '
        "{ display: none; }</style>"
    )
    assert css.count("{") == css.count("}") == 1
    for unsafe in ("<script", "javascript:", "@import", "url(", "{{"):
        assert unsafe not in css.lower()


def test_st_html_is_used_only_with_the_fixed_dialog_css():
    """The app calls st.html once, with the constant: never with user or model text."""
    files = [APP, *sorted((APP.parent / "src").rglob("*.py"))]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert source.count("st.html(") == 1
    assert "st.html(config.PROFILE_DIALOG_CSS)" in source
    assert "unsafe_allow_javascript" not in source
