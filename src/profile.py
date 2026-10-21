"""The user's profile: the allowed values, validation with clear messages, and form values.

The profile is personal data: it lives in `st.session_state` for the session only and is never
logged, stored or indexed (`.claude/rules/security-privacy.md`). Nothing in this module logs.
"""

import math
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from src import config, i18n, units
from src.units import UnitSystem

Sex = Literal["male", "female"]
# The energy equation (Mifflin-St Jeor, src/tools/energy.py) has a male and a female form.
SEX_LABELS: dict[Sex, str] = {"male": "Male", "female": "Female"}

ActivityLevel = Literal["sedentary", "light", "moderate", "very_active", "extra_active"]
# The activity frequencies the activity factors belong to in their source (docs/SOURCES.md #23;
# factors in config.ACTIVITY_FACTORS).
ACTIVITY_LABELS: dict[ActivityLevel, str] = {
    "sedentary": "Sedentary · exercise less than once a week",
    "light": "Light · exercise 1-3 times a week",
    "moderate": "Moderate · exercise 4-5 times a week",
    "very_active": "Very active · exercise 6-7 times a week",
    "extra_active": "Extra active · exercise more than 7 times a week, extra heavy workouts",
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


# One thing to fix: its key in src/i18n.py and the values in its text (T7.1).
Problem = tuple[str, dict[str, Any]]


class ProfileError(ValueError):
    """Raised when the entered profile is not valid; one problem per field that needs fixing."""

    def __init__(self, problems: list[Problem]):
        """Keep the problems and their English messages (`messages`), one per field."""
        self.problems = problems
        self.messages = [i18n.t(code, "en", **params) for code, params in problems]
        super().__init__(" ".join(self.messages))

    def messages_in(self, lang: i18n.Language) -> list[str]:
        """Return the messages in a language, one per field that needs fixing."""
        return [i18n.t(code, lang, **params) for code, params in self.problems]


def _is_number(value: Any) -> bool:
    """Return True for a finite int or float (not a bool)."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large for a float
        return False


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


def _weight_kg(system: UnitSystem, weight: Any) -> tuple[float | None, Problem | None]:
    """Return the entered weight in kg, or None and the problem saying what is wrong."""
    unit = units.weight_unit(system)
    if not _is_number(weight):
        return None, ("profile.err.weight_missing", {"unit": unit})
    if system == "metric":
        if not WEIGHT_MIN_KG <= weight <= WEIGHT_MAX_KG:
            limits = {"low": WEIGHT_MIN_KG, "high": WEIGHT_MAX_KG, "unit": unit}
            return None, ("profile.err.weight_range", limits)
        return float(weight), None
    low, high = IMPERIAL_WEIGHT_RANGE_LB
    if not low <= weight <= high:
        return None, ("profile.err.weight_range", {"low": low, "high": high, "unit": unit})
    return _clamp(units.lb_to_kg(weight), WEIGHT_MIN_KG, WEIGHT_MAX_KG), None


def _height_cm(
    system: UnitSystem, height_cm: Any, height_ft: Any, height_in: Any
) -> tuple[float | None, Problem | None]:
    """Return the entered height in cm, or None and the problem saying what is wrong."""
    if system == "metric":
        if not _is_number(height_cm):
            return None, ("profile.err.height_cm_missing", {})
        if not HEIGHT_MIN_CM <= height_cm <= HEIGHT_MAX_CM:
            limits = {"low": HEIGHT_MIN_CM, "high": HEIGHT_MAX_CM}
            return None, ("profile.err.height_cm_range", limits)
        return float(height_cm), None
    if not _is_number(height_ft) or not _is_number(height_in):
        return None, ("profile.err.height_ft_missing", {})
    if height_ft < 0 or height_ft != int(height_ft) or not 0 <= height_in < units.INCHES_PER_FOOT:
        return None, ("profile.err.height_ft_format", {})
    low, high = IMPERIAL_HEIGHT_RANGE_IN
    if not low <= height_ft * units.INCHES_PER_FOOT + height_in <= high:
        limits = {"low": _feet_inches_text(low), "high": _feet_inches_text(high)}
        return None, ("profile.err.height_ft_range", limits)
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
    """Check the typed values; return the profile in kg and cm, or raise ProfileError."""
    # ProfileError carries one problem per field to fix, in the user's units.
    if units_system not in units.UNIT_SYSTEMS:
        raise ProfileError([("profile.err.units", {})])
    problems: list[Problem] = []

    weight_kg, weight_problem = _weight_kg(units_system, weight)
    cm, height_problem = _height_cm(units_system, height_cm, height_ft, height_in)
    problems += [problem for problem in (weight_problem, height_problem) if problem]

    if not _is_number(age) or age != int(age):
        problems.append(("profile.err.age_missing", {}))
    elif age < AGE_MIN:
        problems.append(("profile.err.age_minor", {"min": AGE_MIN}))
    elif age > AGE_MAX:
        problems.append(("profile.err.age_range", {"min": AGE_MIN, "max": AGE_MAX}))

    if sex not in get_args(Sex):
        problems.append(("profile.err.sex", {}))
    if activity not in get_args(ActivityLevel):
        problems.append(("profile.err.activity", {}))
    if goal not in get_args(Goal):
        problems.append(("profile.err.goal", {}))

    if problems:
        raise ProfileError(problems)
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
    """Return the form values with weight and height moved to another unit system."""
    # Fields that are empty or not numbers stay empty; the other fields are unchanged.
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


# The form fields that depend on the unit system; the others never change on a units switch.
WEIGHT_FIELDS = ("weight",)
HEIGHT_FIELDS = ("height_cm", "height_ft", "height_in")
UNIT_FIELDS = WEIGHT_FIELDS + HEIGHT_FIELDS

# What the last units switch did: the system switched from, the weight and height there, and
# the converted weight and height it showed. Lets a switch back restore exactly what was there.
FormMemory = tuple[UnitSystem, dict[str, Any], dict[str, Any]]


def _unit_fields(values: dict[str, Any]) -> dict[str, Any]:
    """Return only the weight and height fields of the form values."""
    return {field: values.get(field) for field in UNIT_FIELDS}


def initial_form_memory(current: UserProfile | None, system: UnitSystem) -> FormMemory | None:
    """Return a new form's memory, so a first unedited switch shows the stored profile."""
    # Without it, the first switch would convert the rounded values on screen, which can land
    # 0.1 lb away from the stored weight shown in the other system.
    if current is None:
        return None
    other: UnitSystem = "imperial" if system == "metric" else "metric"
    return (
        other,
        _unit_fields(form_values(current, other)),
        _unit_fields(form_values(current, system)),
    )


def switch_form_units(
    values: dict[str, Any],
    from_system: UnitSystem,
    to_system: UnitSystem,
    memory: FormMemory | None,
) -> tuple[dict[str, Any], FormMemory]:
    """Convert the form to another unit system; switching back unedited restores what was typed."""
    # The weight and the height are restored separately, each only if it was not edited since
    # the last switch; an edited one, and every other field, comes from the current values.
    shown = _unit_fields(values)
    result = convert_form_values(values, from_system, to_system)
    if memory is not None and memory[0] == to_system:
        for group in (WEIGHT_FIELDS, HEIGHT_FIELDS):
            if all(memory[2][field] == shown[field] for field in group):
                result.update({field: memory[1][field] for field in group})
    return result, (from_system, shown, _unit_fields(result))


def save_profile(
    values: dict[str, Any], system: UnitSystem, current: UserProfile | None
) -> UserProfile:
    """Return the saved form's profile, keeping the stored weight and height where unchanged."""
    # The form shows the stored profile rounded (0.1 kg or lb, whole cm or inch). A weight or
    # height saved as shown, e.g. after a units switch (see initial_form_memory) or with only
    # another field edited, keeps its stored value instead of the rounded one.
    built = build_profile(units_system=system, **values)
    if current is None:
        return built
    shown = form_values(current, system)
    kept = {}
    if values.get("weight") == shown["weight"]:
        kept["weight_kg"] = current.weight_kg
    if all(values.get(field) == shown[field] for field in HEIGHT_FIELDS):
        kept["height_cm"] = current.height_cm
    if not kept:
        return built
    restored = UserProfile(**{**built.model_dump(), **kept})
    return current if restored == current else restored


def with_goal(current: UserProfile, goal: Goal) -> UserProfile:
    """Return the profile with another goal; an unknown goal raises pydantic's ValidationError."""
    return UserProfile(**{**current.model_dump(), "goal": goal})
