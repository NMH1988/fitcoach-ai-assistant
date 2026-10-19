"""The user's profile: the allowed values, validation with clear messages, and form values.

The profile is personal data: it lives in `st.session_state` for the session only and is never
logged, stored or indexed (`.claude/rules/security-privacy.md`). Nothing in this module logs.
"""

import math
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from src import config, units
from src.units import UnitSystem

Sex = Literal["male", "female"]
# The energy equation planned for T4.2 (Mifflin-St Jeor) has a male and a female form.
SEX_LABELS: dict[Sex, str] = {"male": "Male", "female": "Female"}

ActivityLevel = Literal["sedentary", "light", "moderate", "very_active", "extra_active"]
# Working labels; T4.2 checks them against the source of the activity factors.
ACTIVITY_LABELS: dict[ActivityLevel, str] = {
    "sedentary": "Sedentary · little or no exercise",
    "light": "Light · 1-3 days a week",
    "moderate": "Moderate · 3-5 days a week",
    "very_active": "Very active · 6-7 days a week",
    "extra_active": "Extra active · hard daily training or a physical job",
}

Goal = Literal["build_muscle", "lose_fat", "maintain"]
GOAL_LABELS: dict[Goal, str] = {
    "build_muscle": "Build muscle",
    "lose_fat": "Lose fat",
    "maintain": "Maintain",
}

WEIGHT_MIN_KG, WEIGHT_MAX_KG = config.PROFILE_WEIGHT_KG_RANGE
HEIGHT_MIN_CM, HEIGHT_MAX_CM = config.PROFILE_HEIGHT_CM_RANGE
AGE_MIN, AGE_MAX = config.PROFILE_AGE_RANGE


class UserProfile(BaseModel):
    """A validated profile, always in kg and cm."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    weight_kg: float = Field(ge=WEIGHT_MIN_KG, le=WEIGHT_MAX_KG)
    height_cm: float = Field(ge=HEIGHT_MIN_CM, le=HEIGHT_MAX_CM)
    age: int = Field(ge=AGE_MIN, le=AGE_MAX, strict=True)
    sex: Sex
    activity: ActivityLevel
    goal: Goal


class ProfileError(ValueError):
    """Raised when the entered profile is not valid; `messages` says what to fix, one per field."""

    def __init__(self, messages: list[str]):
        """Keep the messages, one per field that needs fixing."""
        super().__init__(" ".join(messages))
        self.messages = messages


def _is_number(value: Any) -> bool:
    """Return True for a finite int or float (not a bool)."""
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


# In imperial units the bounds are the kg and cm bounds rounded as the form shows them (0.1 lb,
# whole inches), so a profile at a bound still passes after a switch of units. A value accepted
# that way is moved onto the nearest bound, which changes it by less than the rounding.
IMPERIAL_WEIGHT_RANGE_LB = (
    units.weight_in(WEIGHT_MIN_KG, "imperial"),
    units.weight_in(WEIGHT_MAX_KG, "imperial"),
)
IMPERIAL_HEIGHT_RANGE_IN = (
    round(HEIGHT_MIN_CM / units.CM_PER_INCH),
    round(HEIGHT_MAX_CM / units.CM_PER_INCH),
)


def _feet_inches_text(total_inches: int) -> str:
    """Show a whole number of inches as feet and inches, e.g. "5 ft 11 in"."""
    feet, inches = divmod(total_inches, units.INCHES_PER_FOOT)
    return f"{feet} ft {inches} in"


def _clamp(value: float, low: float, high: float) -> float:
    """Return the value moved into [low, high]."""
    return min(max(value, low), high)


def _weight_kg(system: UnitSystem, weight: Any) -> tuple[float | None, str | None]:
    """Return the entered weight in kg, or None and a message saying what is wrong."""
    if not _is_number(weight):
        return None, f"Enter your weight in {units.weight_unit(system)}."
    if system == "metric":
        if not WEIGHT_MIN_KG <= weight <= WEIGHT_MAX_KG:
            return None, f"Weight must be between {WEIGHT_MIN_KG:g} and {WEIGHT_MAX_KG:g} kg."
        return float(weight), None
    low, high = IMPERIAL_WEIGHT_RANGE_LB
    if not low <= weight <= high:
        return None, f"Weight must be between {low:g} and {high:g} lb."
    return _clamp(units.lb_to_kg(weight), WEIGHT_MIN_KG, WEIGHT_MAX_KG), None


def _height_cm(
    system: UnitSystem, height_cm: Any, height_ft: Any, height_in: Any
) -> tuple[float | None, str | None]:
    """Return the entered height in cm, or None and a message saying what is wrong."""
    if system == "metric":
        if not _is_number(height_cm):
            return None, "Enter your height in cm."
        if not HEIGHT_MIN_CM <= height_cm <= HEIGHT_MAX_CM:
            return None, f"Height must be between {HEIGHT_MIN_CM:g} and {HEIGHT_MAX_CM:g} cm."
        return float(height_cm), None
    if not _is_number(height_ft) or not _is_number(height_in):
        return None, "Enter your height in feet and inches."
    if height_ft < 0 or not 0 <= height_in < units.INCHES_PER_FOOT:
        return None, "Enter the height as whole feet and 0 to 11 inches."
    low, high = IMPERIAL_HEIGHT_RANGE_IN
    if not low <= height_ft * units.INCHES_PER_FOOT + height_in <= high:
        return (
            None,
            f"Height must be between {_feet_inches_text(low)} and {_feet_inches_text(high)}.",
        )
    cm = units.ft_in_to_cm(height_ft, height_in)
    return _clamp(cm, HEIGHT_MIN_CM, HEIGHT_MAX_CM), None


def build_profile(
    *,
    units_system: UnitSystem,
    weight: Any,
    height_cm: Any = None,
    height_ft: Any = None,
    height_in: Any = None,
    age: Any,
    sex: Any,
    activity: Any,
    goal: Any,
) -> UserProfile:
    """Check the values entered in `units_system` and return the profile in kg and cm.

    Raises `ProfileError` with one message per field to fix, in the user's units.
    """
    if units_system not in units.UNIT_SYSTEMS:
        raise ProfileError(["Choose metric or imperial units."])
    messages: list[str] = []

    weight_kg, weight_message = _weight_kg(units_system, weight)
    cm, height_message = _height_cm(units_system, height_cm, height_ft, height_in)
    messages += [message for message in (weight_message, height_message) if message]

    if not _is_number(age) or age != int(age):
        messages.append("Enter your age in whole years.")
    elif age < AGE_MIN:
        messages.append(
            f"This app is for adults aged {AGE_MIN} and over, so it cannot give personal "
            "targets for younger users."
        )
    elif age > AGE_MAX:
        messages.append(f"Age must be between {AGE_MIN} and {AGE_MAX}.")

    if sex not in get_args(Sex):
        messages.append("Choose the sex for the energy equation.")
    if activity not in get_args(ActivityLevel):
        messages.append("Choose your activity level.")
    if goal not in get_args(Goal):
        messages.append("Choose your goal.")

    if messages:
        raise ProfileError(messages)
    return UserProfile(
        weight_kg=weight_kg, height_cm=cm, age=int(age), sex=sex, activity=activity, goal=goal
    )


def form_values(profile: UserProfile | None, system: UnitSystem) -> dict[str, Any]:
    """Return the profile form's starting values in a unit system (empty fields with no profile)."""
    if profile is None:
        return {
            "weight": None,
            "height_cm": None,
            "height_ft": None,
            "height_in": None,
            "age": None,
            "sex": None,
            "activity": None,
            "goal": None,
        }
    values = {
        "weight": units.weight_in(profile.weight_kg, system),
        "height_cm": None,
        "height_ft": None,
        "height_in": None,
        "age": profile.age,
        "sex": profile.sex,
        "activity": profile.activity,
        "goal": profile.goal,
    }
    if system == "metric":
        values["height_cm"] = round(profile.height_cm)
    else:
        values["height_ft"], values["height_in"] = units.cm_to_ft_in(profile.height_cm)
    return values


def _entered_cm(system: UnitSystem, height_cm: Any, height_ft: Any, height_in: Any) -> float | None:
    """Return the entered height in cm whatever its range, or None if it is not filled in."""
    if system == "metric":
        return float(height_cm) if _is_number(height_cm) else None
    if _is_number(height_ft) and _is_number(height_in):
        return units.ft_in_to_cm(height_ft, height_in)
    return None


def convert_form_values(
    values: dict[str, Any], from_system: UnitSystem, to_system: UnitSystem
) -> dict[str, Any]:
    """Return the form values with weight and height moved to another unit system.

    Fields that are empty or not numbers stay empty; the other fields are unchanged.
    """
    converted = dict(values)
    if from_system == to_system:
        return converted
    weight = values.get("weight")
    converted["weight"] = (
        units.weight_in(units.weight_to_kg(float(weight), from_system), to_system)
        if _is_number(weight)
        else None
    )
    cm = _entered_cm(
        from_system, values.get("height_cm"), values.get("height_ft"), values.get("height_in")
    )
    converted["height_cm"] = converted["height_ft"] = converted["height_in"] = None
    if cm is not None:
        if to_system == "metric":
            converted["height_cm"] = round(cm)
        else:
            converted["height_ft"], converted["height_in"] = units.cm_to_ft_in(cm)
    return converted
