"""Unit tests for src/profile.py: profile validation, messages and form values (AC-5, AC-8)."""

import math
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from src import config, profile, units
from src.profile import ProfileError, UserProfile, build_profile

VALID_METRIC = {
    "units_system": "metric",
    "weight": 80.0,
    "height_cm": 180,
    "age": 30,
    "sex": "male",
    "activity": "moderate",
    "goal": "build_muscle",
}
VALID_IMPERIAL = {
    "units_system": "imperial",
    "weight": 176.4,
    "height_ft": 5,
    "height_in": 11,
    "age": 30,
    "sex": "female",
    "activity": "light",
    "goal": "lose_fat",
}


def _messages(**changes) -> list[str]:
    """Build a metric profile with some fields changed and return the error messages."""
    with pytest.raises(ProfileError) as caught:
        build_profile(**{**VALID_METRIC, **changes})
    return caught.value.messages


def _imperial_messages(**changes) -> list[str]:
    """Build an imperial profile with some fields changed and return the error messages."""
    with pytest.raises(ProfileError) as caught:
        build_profile(**{**VALID_IMPERIAL, **changes})
    return caught.value.messages


def test_valid_metric_profile_is_kept_in_kg_and_cm():
    """A valid metric entry gives a profile with the same kg and cm values."""
    built = build_profile(**VALID_METRIC)
    assert built == UserProfile(
        weight_kg=80.0,
        height_cm=180.0,
        age=30,
        sex="male",
        activity="moderate",
        goal="build_muscle",
    )


def test_valid_imperial_profile_is_converted_to_kg_and_cm():
    """An imperial entry is stored in kg and cm (AC-5: values accepted in the chosen units)."""
    built = build_profile(**VALID_IMPERIAL)
    assert built.weight_kg == pytest.approx(units.lb_to_kg(176.4))
    assert built.height_cm == pytest.approx(180.34)
    assert (built.sex, built.activity, built.goal) == ("female", "light", "lose_fat")


def test_config_ranges_are_the_documented_ones():
    """The accepted ranges are the owner-approved ones (30-300 kg, 120-230 cm, 18-100 years)."""
    assert config.PROFILE_WEIGHT_KG_RANGE == (30.0, 300.0)
    assert config.PROFILE_HEIGHT_CM_RANGE == (120.0, 230.0)
    assert config.PROFILE_AGE_RANGE == (18, 100)


@pytest.mark.parametrize("weight", [30.0, 30, 300.0])
def test_metric_weight_at_the_bounds_passes(weight):
    """The weight bounds are inclusive."""
    assert build_profile(**{**VALID_METRIC, "weight": weight}).weight_kg == weight


@pytest.mark.parametrize("weight", [29.9, 300.1, 0, -80.0, 1e9])
def test_metric_weight_out_of_range_is_rejected(weight):
    """A weight outside 30-300 kg is rejected with the range in kg."""
    assert _messages(weight=weight) == ["Weight must be between 30 and 300 kg."]


@pytest.mark.parametrize("height", [120, 230, 165.5])
def test_metric_height_in_range_passes(height):
    """Heights from 120 to 230 cm pass, bounds included."""
    assert build_profile(**{**VALID_METRIC, "height_cm": height}).height_cm == height


@pytest.mark.parametrize("height", [119.9, 230.1, 0, -1])
def test_metric_height_out_of_range_is_rejected(height):
    """A height outside 120-230 cm is rejected with the range in cm."""
    assert _messages(height_cm=height) == ["Height must be between 120 and 230 cm."]


@pytest.mark.parametrize("weight", [66.0, 661.5])
def test_imperial_weight_out_of_range_is_rejected_in_lb(weight):
    """An imperial weight outside the range gets the range in lb, not in kg."""
    assert _imperial_messages(weight=weight) == ["Weight must be between 66.1 and 661.4 lb."]


@pytest.mark.parametrize(("feet", "inches"), [(3, 10), (7, 8), (0, 0)])
def test_imperial_height_out_of_range_is_rejected_in_ft_in(feet, inches):
    """An imperial height outside the range gets the range in feet and inches."""
    assert _imperial_messages(height_ft=feet, height_in=inches) == [
        "Height must be between 3 ft 11 in and 7 ft 7 in."
    ]


@pytest.mark.parametrize(("feet", "inches"), [(5, 12), (5, -1), (-1, 6), (5.5, 0)])
def test_imperial_height_with_bad_parts_is_rejected(feet, inches):
    """Inches must be 0 to 11 and feet a whole number, not negative."""
    assert _imperial_messages(height_ft=feet, height_in=inches) == [
        "Enter the height as whole feet and 0 to 11 inches."
    ]


@pytest.mark.parametrize(
    ("kg", "cm"), [(30.0, 120.0), (300.0, 230.0), (30.0, 230.0), (300.0, 120.0)]
)
def test_a_profile_at_the_bounds_survives_a_switch_to_imperial(kg, cm):
    """Profiles at the bounds still pass when shown and saved in imperial, and stay in range."""
    start = UserProfile(
        weight_kg=kg, height_cm=cm, age=30, sex="male", activity="moderate", goal="maintain"
    )
    values = profile.form_values(start, "imperial")
    saved = build_profile(units_system="imperial", **values)
    assert saved.weight_kg == pytest.approx(kg, abs=units.lb_to_kg(0.05))
    assert saved.height_cm == pytest.approx(cm, abs=units.CM_PER_INCH / 2)
    assert profile.WEIGHT_MIN_KG <= saved.weight_kg <= profile.WEIGHT_MAX_KG
    assert profile.HEIGHT_MIN_CM <= saved.height_cm <= profile.HEIGHT_MAX_CM


@pytest.mark.parametrize("age", [18, 50, 100])
def test_age_in_range_passes(age):
    """Ages from 18 to 100 pass, bounds included."""
    assert build_profile(**{**VALID_METRIC, "age": age}).age == age


@pytest.mark.parametrize("age", [17, 12, 0])
def test_under_18_is_rejected_with_an_adults_only_message(age):
    """Users under 18 are told the app is for adults (PRD scope, AC-5)."""
    assert _messages(age=age) == [
        "This app is for adults aged 18 and over, so it cannot give personal targets for "
        "younger users."
    ]


def test_age_over_100_is_rejected():
    """An age over 100 is rejected with the range."""
    assert _messages(age=101) == ["Age must be between 18 and 100."]


@pytest.mark.parametrize("age", [30.5, "30", None, True, math.nan])
def test_age_must_be_a_whole_number(age):
    """Fractional, text, empty, boolean and NaN ages are rejected."""
    assert _messages(age=age) == ["Enter your age in whole years."]


@pytest.mark.parametrize("weight", [None, "80", math.nan, math.inf, False, 10**400])
def test_weight_must_be_a_finite_number(weight):
    """Empty, text, NaN, infinite, boolean and too-large weights are rejected, not a crash."""
    assert _messages(weight=weight) == ["Enter your weight in kg."]


def test_missing_imperial_height_is_rejected():
    """An imperial entry needs both feet and inches."""
    assert _imperial_messages(height_in=None) == ["Enter your height in feet and inches."]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sex", None, "Choose the sex for the energy equation."),
        ("sex", "other", "Choose the sex for the energy equation."),
        ("activity", "athlete", "Choose your activity level."),
        ("goal", "bulk", "Choose your goal."),
    ],
)
def test_choices_must_be_one_of_the_options(field, value, message):
    """Sex, activity and goal must be one of the listed options."""
    assert _messages(**{field: value}) == [message]


def test_every_problem_is_reported_at_once():
    """All fields to fix are listed together, in form order."""
    messages = _messages(weight=10, height_cm=None, age=16, goal=None)
    assert messages == [
        "Weight must be between 30 and 300 kg.",
        "Enter your height in cm.",
        "This app is for adults aged 18 and over, so it cannot give personal targets for "
        "younger users.",
        "Choose your goal.",
    ]


def test_unknown_unit_system_is_rejected():
    """Only metric and imperial are accepted."""
    with pytest.raises(ProfileError) as caught:
        build_profile(**{**VALID_METRIC, "units_system": "stone"})
    assert caught.value.messages == ["Choose metric or imperial units."]


@pytest.mark.parametrize(
    "changes", [{"weight_kg": 20.0}, {"age": 17}, {"height_cm": math.inf}, {"sex": "x"}]
)
def test_user_profile_model_enforces_the_ranges_too(changes):
    """The model itself rejects out-of-range values, as a second line of defence for the tools."""
    fields = {
        "weight_kg": 80.0,
        "height_cm": 180.0,
        "age": 30,
        "sex": "male",
        "activity": "moderate",
        "goal": "maintain",
    }
    with pytest.raises(ValidationError):
        UserProfile(**{**fields, **changes})


def test_user_profile_is_frozen():
    """A built profile cannot be changed in place."""
    built = build_profile(**VALID_METRIC)
    with pytest.raises(ValidationError):
        built.weight_kg = 90.0


def test_every_option_has_a_label():
    """Each sex, activity level and goal has a label for the form."""
    assert set(profile.SEX_LABELS) == set(get_args(profile.Sex))
    assert set(profile.ACTIVITY_LABELS) == set(get_args(profile.ActivityLevel))
    assert set(profile.ACTIVITY_SHORT_LABELS) == set(get_args(profile.ActivityLevel))
    assert set(profile.GOAL_LABELS) == set(get_args(profile.Goal))


def test_form_values_without_a_profile_are_empty():
    """With no profile the form starts empty."""
    assert all(value is None for value in profile.form_values(None, "metric").values())


def test_form_values_show_the_profile_in_each_unit_system():
    """The form starts with the profile in the chosen units."""
    built = build_profile(**VALID_METRIC)
    metric = profile.form_values(built, "metric")
    imperial = profile.form_values(built, "imperial")
    assert (metric["weight"], metric["height_cm"]) == (80.0, 180)
    assert (imperial["weight"], imperial["height_ft"], imperial["height_in"]) == (176.4, 5, 11)
    assert metric["age"] == imperial["age"] == 30


def _typed_metric(weight: float, height_cm: int) -> dict:
    """Return metric form values with this weight and height and the other fields filled in."""
    return {
        **profile.form_values(build_profile(**VALID_METRIC), "metric"),
        "weight": weight,
        "height_cm": height_cm,
    }


def test_convert_form_values_moves_weight_and_height_only():
    """Converting fills the imperial fields, empties the metric ones and keeps the rest."""
    typed = _typed_metric(80.0, 180)
    there = profile.convert_form_values(typed, "metric", "imperial")
    assert (there["weight"], there["height_ft"], there["height_in"]) == (176.4, 5, 11)
    assert there["height_cm"] is None
    assert {k: there[k] for k in ("age", "sex", "activity", "goal")} == {
        k: typed[k] for k in ("age", "sex", "activity", "goal")
    }


@pytest.mark.parametrize(
    ("weight", "height_cm"), [(80.0, 179), (80.1, 181), (91.3, 182), (55.5, 184), (120.0, 230)]
)
def test_convert_form_values_there_and_back_is_within_rounding(weight, height_cm):
    """Plain conversion there and back moves values by at most the rounding (AC-8)."""
    typed = _typed_metric(weight, height_cm)
    back = profile.convert_form_values(
        profile.convert_form_values(typed, "metric", "imperial"), "imperial", "metric"
    )
    assert abs(back["weight"] - weight) <= 0.1 + 1e-9
    assert abs(back["height_cm"] - height_cm) <= units.CM_PER_INCH / 2


@pytest.mark.parametrize(
    ("weight", "height_cm"), [(80.0, 179), (80.1, 181), (91.3, 182), (55.5, 184), (120.0, 230)]
)
def test_switching_units_and_back_without_editing_restores_the_typed_values(weight, height_cm):
    """A switch back with nothing edited in between gives exactly what was typed (AC-8)."""
    typed = _typed_metric(weight, height_cm)
    there, memory = profile.switch_form_units(typed, "metric", "imperial", None)
    back, memory = profile.switch_form_units(there, "imperial", "metric", memory)
    assert back == typed
    again, _ = profile.switch_form_units(back, "metric", "imperial", memory)
    assert again == there


def test_switching_back_after_an_edit_converts_the_edit():
    """When a value was edited after the switch, switching back converts the edited values."""
    there, memory = profile.switch_form_units(_typed_metric(80.0, 179), "metric", "imperial", None)
    edited = {**there, "weight": 200.0}
    back, _ = profile.switch_form_units(edited, "imperial", "metric", memory)
    assert back["weight"] == pytest.approx(90.7)
    assert abs(back["height_cm"] - 179) <= units.CM_PER_INCH / 2


def test_saving_unchanged_values_keeps_the_stored_profile():
    """Saving the form as shown (e.g. after a units switch only) does not round the profile."""
    stored = UserProfile(
        weight_kg=80.04, height_cm=190.5, age=30, sex="male", activity="moderate", goal="maintain"
    )
    for system in units.UNIT_SYSTEMS:
        shown = profile.form_values(stored, system)
        assert profile.save_profile(shown, system, stored) is stored


def test_saving_changed_values_builds_a_new_profile():
    """Saving edited values checks them and returns the new profile."""
    stored = build_profile(**VALID_METRIC)
    edited = {**profile.form_values(stored, "metric"), "weight": 82.5}
    assert profile.save_profile(edited, "metric", stored).weight_kg == 82.5
    with pytest.raises(ProfileError):
        profile.save_profile({**edited, "age": 17}, "metric", stored)
    assert profile.save_profile(edited, "metric", None).weight_kg == 82.5


def test_convert_form_values_keeps_empty_and_out_of_range_fields():
    """Empty fields stay empty and out-of-range numbers are converted, not dropped."""
    values = {**profile.form_values(None, "metric"), "weight": 500.0, "age": 40}
    converted = profile.convert_form_values(values, "metric", "imperial")
    assert converted["weight"] == pytest.approx(1102.3)
    assert converted["height_ft"] is None and converted["height_in"] is None
    assert converted["age"] == 40


def test_convert_form_values_to_the_same_system_changes_nothing():
    """Converting to the system already in use returns the same values."""
    typed = profile.form_values(build_profile(**VALID_METRIC), "metric")
    assert profile.convert_form_values(typed, "metric", "metric") == typed


def test_profile_module_never_logs_or_prints():
    """The profile module has no logging or printing (the profile is never logged)."""
    source = (Path(profile.__file__)).read_text(encoding="utf-8")
    assert "logging" not in source and "print(" not in source
