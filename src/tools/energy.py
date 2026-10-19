"""calculate_tdee and calculate_macro_targets: daily energy needs and macro targets for a profile.

Every number comes from an approved source (docs/SOURCES.md; values and source IDs in
`src/config.py`): the Mifflin-St Jeor equation [22], the activity factors [23], and the goal
adjustments, macro ranges and calorie floor [1], [9], [11], [12]. The arguments are personal data:
nothing here logs, prints or stores them. Invalid arguments give a result with status "invalid" and
a fixed message, never an exception and never an echo of what was sent.
"""

import math
from typing import Literal, NamedTuple, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src import config, units
from src.profile import (
    AGE_MAX,
    AGE_MIN,
    HEIGHT_MAX_CM,
    HEIGHT_MIN_CM,
    WEIGHT_MAX_KG,
    WEIGHT_MIN_KG,
    ActivityLevel,
    Goal,
    Sex,
)

TDEE_MIN_KCAL, TDEE_MAX_KCAL = config.MACRO_TDEE_KCAL_RANGE
# Energy in a kg of body fat, from the "about 3500 kcal per lb" estimate in [12].
KCAL_PER_KG_BODY_FAT = config.KCAL_PER_LB_BODY_FAT / units.KG_PER_LB
DAYS_PER_WEEK = 7


class FormulaSource(NamedTuple):
    """An article the tools take a formula or factors from (credited in ATTRIBUTION.md)."""

    id: str
    authors: tuple[str, ...]
    title: str
    journal: str
    year: int
    doi: str
    copyright_notice: str
    license: str
    license_url: str
    used_for: str


# The articles behind calculate_tdee (docs/SOURCES.md #22 and #23). Only the numbers are used;
# none of their text is reproduced.
FORMULA_SOURCES: tuple[FormulaSource, ...] = (
    FormulaSource(
        id="22",
        authors=("Ciara Cooney", "Ed Daly", "Maria McDonagh", "Lisa Ryan"),
        title=(
            "Evaluation of Measured Resting Metabolic Rate for Dietary Prescription in Ageing "
            "Adults with Overweight and Adiposity-Based Chronic Disease"
        ),
        journal="Nutrients 13(4):1229",
        year=2021,
        doi="10.3390/nu13041229",
        copyright_notice="© 2021 by the authors. Licensee MDPI, Basel, Switzerland.",
        license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        used_for="the coefficients of the Mifflin-St Jeor equation in calculate_tdee",
    ),
    FormulaSource(
        id="23",
        authors=(
            "Rita Ostan",
            "Giulia Guidarelli",
            "Enrico Giampieri",
            "Catia Lanzarini",
            "Agnes A. M. Berendsen",
            "Olga Januszko",
            "Amy Jennings",
            "Noëlle Lyon",
            "Elodie Caumon",
            "Rachel Gillings",
            "Ewa Sicinska",
            "Nathalie Meunier",
            "Edith J. M. Feskens",
            "Barbara Pietruszka",
            "Lisette C. P. G. M. de Groot",
            "Susan Fairweather-Tait",
            "Miriam Capri",
            "Claudio Franceschi",
            "Aurelia Santoro",
        ),
        title=(
            "Cross-Sectional Analysis of the Correlation Between Daily Nutrient Intake Assessed by "
            "7-Day Food Records and Biomarkers of Dietary Intake Among Participants of the NU-AGE "
            "Study"
        ),
        journal="Frontiers in Physiology 9:1359",
        year=2018,
        doi="10.3389/fphys.2018.01359",
        copyright_notice=(
            "© 2018 Ostan, Guidarelli, Giampieri, Lanzarini, Berendsen, Januszko, Jennings, Lyon, "
            "Caumon, Gillings, Sicinska, Meunier, Feskens, Pietruszka, de Groot, "
            "Fairweather-Tait, Capri, Franceschi and Santoro."
        ),
        license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        used_for="the activity factors and their activity levels in calculate_tdee",
    ),
)

TDEE_METHOD = (
    "Resting energy from the Mifflin-St Jeor equation, multiplied by an activity factor. A "
    "prediction: real needs can differ, so adjust by how body weight changes over a few weeks."
)
TDEE_SOURCES: tuple[str, ...] = (
    "Mifflin-St Jeor equation as given in Cooney et al. 2021, Nutrients (CC BY 4.0), "
    "https://doi.org/10.3390/nu13041229",
    "Activity factors from Ostan et al. 2018, Frontiers in Physiology (CC BY 4.0), "
    "https://doi.org/10.3389/fphys.2018.01359",
)
MACRO_SOURCES: tuple[str, ...] = (
    "Aragon et al. 2026, ISSN position stand: diets for body weight reduction (CC BY 4.0), "
    "https://doi.org/10.1080/15502783.2026.2740266",
    "Aragon et al. 2017, ISSN position stand: diets and body composition (CC BY 4.0), "
    "https://doi.org/10.1186/s12970-017-0174-y",
    "Iraki et al. 2019, Nutrition recommendations for bodybuilders in the off-season "
    "(CC BY 4.0), https://doi.org/10.3390/sports7070154",
    "Helms et al. 2014, Evidence-based recommendations for natural bodybuilding contest "
    "preparation (CC BY 2.0), https://doi.org/10.1186/1550-2783-11-20",
)


class TdeeArgs(BaseModel):
    """calculate_tdee's arguments; checked before anything is computed."""

    model_config = ConfigDict(extra="forbid")

    # Strict: JSON numbers only (no strings or booleans); an int is accepted for a float.
    weight_kg: float = Field(
        ge=WEIGHT_MIN_KG,
        le=WEIGHT_MAX_KG,
        strict=True,
        allow_inf_nan=False,
        description="Body weight in kg.",
    )
    height_cm: float = Field(
        ge=HEIGHT_MIN_CM,
        le=HEIGHT_MAX_CM,
        strict=True,
        allow_inf_nan=False,
        description="Height in cm.",
    )
    age: int = Field(ge=AGE_MIN, le=AGE_MAX, strict=True, description="Age in whole years.")
    sex: Sex = Field(description="'male' or 'female': the equation has one form for each.")
    activity: ActivityLevel = Field(description="Activity level from the user's profile.")


class TdeeResult(BaseModel):
    """What calculate_tdee returns: resting and daily energy in kcal/day, or why there are none."""

    status: Literal["ok", "invalid"]
    message: str
    bmr_kcal: int | None = None
    tdee_kcal: int | None = None
    activity_factor: float | None = None
    method: str = TDEE_METHOD
    sources: list[str] = Field(default_factory=lambda: list(TDEE_SOURCES))


class MacroArgs(BaseModel):
    """calculate_macro_targets' arguments; checked before anything is computed."""

    model_config = ConfigDict(extra="forbid")

    weight_kg: float = Field(
        ge=WEIGHT_MIN_KG,
        le=WEIGHT_MAX_KG,
        strict=True,
        allow_inf_nan=False,
        description="Body weight in kg.",
    )
    goal: Goal = Field(description="The user's goal: 'build_muscle', 'lose_fat' or 'maintain'.")
    tdee_kcal: float = Field(
        ge=TDEE_MIN_KCAL,
        le=TDEE_MAX_KCAL,
        strict=True,
        allow_inf_nan=False,
        description="Daily energy needs in kcal/day, from calculate_tdee.",
    )


class Macro(BaseModel):
    """One macronutrient's daily target."""

    grams: int
    # Share of the kcal target, in whole percent.
    percent: int
    g_per_kg: float


class MacroTargetsResult(BaseModel):
    """What calculate_macro_targets returns: the daily targets, or why there are none."""

    status: Literal["ok", "invalid"]
    message: str
    goal: Goal | None = None
    kcal_target: int | None = None
    # The kcal the sources' range for the goal gives (lowest, highest), floor applied.
    kcal_range: tuple[int, int] | None = None
    calorie_floor_kcal: int = config.CALORIE_FLOOR_KCAL
    # True when the goal's estimate was below the floor and the target was raised to it.
    floor_applied: bool = False
    protein: Macro | None = None
    carbohydrate: Macro | None = None
    fat: Macro | None = None
    # Protein for the sources' 1.6-2.2 g/kg range at this body weight, in g/day.
    protein_g_range: tuple[int, int] | None = None
    notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=lambda: list(MACRO_SOURCES))


def _fields(error: ValidationError) -> set[str]:
    """Return the names of the arguments that failed validation (or were not expected)."""
    return {str(e["loc"][0]) for e in error.errors() if e["loc"]}


WEIGHT_RULE = f"weight_kg must be a number from {WEIGHT_MIN_KG:g} to {WEIGHT_MAX_KG:g}"


def _tdee_invalid_message(error: ValidationError) -> str:
    """Explain which calculate_tdee arguments are wrong, without repeating what was sent."""
    fields = _fields(error)
    parts = []
    if "weight_kg" in fields:
        parts.append(WEIGHT_RULE)
    if "height_cm" in fields:
        parts.append(f"height_cm must be a number from {HEIGHT_MIN_CM:g} to {HEIGHT_MAX_CM:g}")
    if "age" in fields:
        parts.append(f"age must be a whole number of years from {AGE_MIN} to {AGE_MAX}")
    if "sex" in fields:
        parts.append(f"sex must be one of {', '.join(get_args(Sex))}")
    if "activity" in fields:
        parts.append(f"activity must be one of {', '.join(get_args(ActivityLevel))}")
    return "Invalid energy calculation: " + ("; ".join(parts) or "check the arguments") + "."


def _macro_invalid_message(error: ValidationError) -> str:
    """Explain which macro arguments are wrong, without repeating what was sent."""
    fields = _fields(error)
    parts = []
    if "weight_kg" in fields:
        parts.append(WEIGHT_RULE)
    if "goal" in fields:
        parts.append(f"goal must be one of {', '.join(get_args(Goal))}")
    if "tdee_kcal" in fields:
        parts.append(f"tdee_kcal must be a number from {TDEE_MIN_KCAL} to {TDEE_MAX_KCAL}")
    return "Invalid macro calculation: " + ("; ".join(parts) or "check the arguments") + "."


def resting_energy_kcal(weight_kg: float, height_cm: float, age: int, sex: Sex) -> float:
    """Return resting energy in kcal/day from the Mifflin-St Jeor equation, unrounded."""
    return (
        config.MSJ_KCAL_PER_KG * weight_kg
        + config.MSJ_KCAL_PER_CM * height_cm
        - config.MSJ_KCAL_PER_YEAR * age
        + config.MSJ_SEX_CONSTANT_KCAL[sex]
    )


def calculate_tdee(
    weight_kg: float, height_cm: float, age: int, sex: Sex, activity: ActivityLevel
) -> TdeeResult:
    """Return resting energy (BMR) and daily energy needs (TDEE) in kcal/day, or why not."""
    try:
        args = TdeeArgs(
            weight_kg=weight_kg, height_cm=height_cm, age=age, sex=sex, activity=activity
        )
    except ValidationError as exc:
        return TdeeResult(status="invalid", message=_tdee_invalid_message(exc))
    bmr = resting_energy_kcal(args.weight_kg, args.height_cm, args.age, args.sex)
    factor = config.ACTIVITY_FACTORS[args.activity]
    bmr_kcal, tdee_kcal = round(bmr), round(bmr * factor)
    return TdeeResult(
        status="ok",
        message=(
            f"Resting energy about {bmr_kcal} kcal/day; with the activity factor {factor:g}, daily "
            f"energy needs about {tdee_kcal} kcal/day."
        ),
        bmr_kcal=bmr_kcal,
        tdee_kcal=tdee_kcal,
        activity_factor=factor,
    )


def _goal_kcal(weight_kg: float, goal: Goal, tdee_kcal: float, rate: float) -> float:
    """Return the unrounded kcal for a goal: a weekly loss of rate% or a surplus of rate%."""
    # `rate` is ignored for "maintain".
    if goal == "lose_fat":
        weekly_kg = weight_kg * rate / 100
        return tdee_kcal - weekly_kg * KCAL_PER_KG_BODY_FAT / DAYS_PER_WEEK
    if goal == "build_muscle":
        return tdee_kcal * (1 + rate / 100)
    return tdee_kcal


def _goal_rates(goal: Goal) -> tuple[float, tuple[float, float]]:
    """Return the goal's target rate and the sources' range of rates (in %)."""
    if goal == "lose_fat":
        return config.FAT_LOSS_PCT_PER_WEEK, config.FAT_LOSS_PCT_PER_WEEK_RANGE
    if goal == "build_muscle":
        return config.MUSCLE_GAIN_SURPLUS_PCT, config.MUSCLE_GAIN_SURPLUS_PCT_RANGE
    return 0.0, (0.0, 0.0)


def _floored(kcal: float) -> int:
    """Return the kcal rounded to a whole number and never below the calorie floor."""
    return max(round(kcal), config.CALORIE_FLOOR_KCAL)


def _macro(grams: int, kcal_per_g: int, kcal_target: int, weight_kg: float) -> Macro:
    """Return a macro's grams with its share of the kcal target and its grams per kg."""
    return Macro(
        grams=grams,
        percent=round(grams * kcal_per_g / kcal_target * 100),
        g_per_kg=round(grams / weight_kg, 1),
    )


def _goal_message(goal: Goal, kcal_target: int, floor_applied: bool) -> str:
    """Return the result message: the target and how it was set for the goal."""
    if floor_applied:
        how = (
            f"raised to the calorie floor of {config.CALORIE_FLOOR_KCAL} kcal/day, as the goal's "
            "estimate was lower (see the notes)"
        )
    elif goal == "lose_fat":
        how = (
            f"set for a weekly loss of about {config.FAT_LOSS_PCT_PER_WEEK:g}% of body weight, "
            f"counting about {config.KCAL_PER_LB_BODY_FAT} kcal per lb of body fat (a rough "
            "estimate)"
        )
    elif goal == "build_muscle":
        how = f"set {config.MUSCLE_GAIN_SURPLUS_PCT:g}% above daily energy needs"
    else:
        how = "set at daily energy needs"
    return (
        f"Daily target about {kcal_target} kcal, {how}. Protein by body weight, fat at "
        f"{config.FAT_PCT_OF_KCAL:g}% of the kcal, carbohydrate the rest. Adjust by how body "
        "weight changes over a few weeks."
    )


def calculate_macro_targets(weight_kg: float, goal: Goal, tdee_kcal: float) -> MacroTargetsResult:
    """Return the daily kcal, protein, carbohydrate and fat targets for a goal, or why not."""
    # The kcal target is never below config.CALORIE_FLOOR_KCAL (AC-7), and the macros' kcal add up
    # to at least the target: grams of carbohydrate (or protein, when it is lowered) round up.
    try:
        args = MacroArgs(weight_kg=weight_kg, goal=goal, tdee_kcal=tdee_kcal)
    except ValidationError as exc:
        return MacroTargetsResult(status="invalid", message=_macro_invalid_message(exc))
    weight, floor = args.weight_kg, config.CALORIE_FLOOR_KCAL
    rate, (low_rate, high_rate) = _goal_rates(args.goal)
    estimate = round(_goal_kcal(weight, args.goal, args.tdee_kcal, rate))
    kcal_target = max(estimate, floor)
    ends = sorted(
        _floored(_goal_kcal(weight, args.goal, args.tdee_kcal, r)) for r in (low_rate, high_rate)
    )
    floor_applied = estimate < floor
    notes = []
    if floor_applied:
        notes.append(
            f"The goal's estimate was below the calorie floor of {floor} kcal/day, so the target "
            "is set to the floor."
        )
        if kcal_target > args.tdee_kcal:
            # Small, older or less active profiles: the floor is above the estimated needs.
            effect = ", so it will not lead to fat loss" if args.goal == "lose_fat" else ""
            notes.append(
                f"This target is above the estimated daily energy needs of about "
                f"{round(args.tdee_kcal)} kcal/day{effect}. The app does not set targets below the "
                "floor; ask a registered dietitian for personal targets."
            )
        elif args.goal == "lose_fat":
            notes.append("At the floor, the deficit is smaller than the goal's weekly rate.")

    protein_g = round(weight * config.PROTEIN_G_PER_KG[args.goal])
    fat_g = round(kcal_target * config.FAT_PCT_OF_KCAL / 100 / config.KCAL_PER_G_FAT)
    fat_kcal = fat_g * config.KCAL_PER_G_FAT
    carb_kcal = kcal_target - protein_g * config.KCAL_PER_G_PROTEIN - fat_kcal
    if carb_kcal < 0:
        # Only for a very heavy body with a low kcal target: protein by body weight and fat would
        # exceed the target, so protein gets what fat leaves and carbohydrate none.
        protein_g = math.ceil((kcal_target - fat_kcal) / config.KCAL_PER_G_PROTEIN)
        carb_g = 0
        notes.append(
            f"Protein at {config.PROTEIN_G_PER_KG[args.goal]:g} g/kg and fat at "
            f"{config.FAT_PCT_OF_KCAL:g}% would exceed the kcal target, so protein was lowered to "
            "fit and carbohydrate set to 0. Ask a registered dietitian for targets at this body "
            "weight."
        )
    else:
        carb_g = math.ceil(carb_kcal / config.KCAL_PER_G_CARBOHYDRATE)

    protein_low, protein_high = config.PROTEIN_G_PER_KG_RANGE
    return MacroTargetsResult(
        status="ok",
        message=_goal_message(args.goal, kcal_target, floor_applied),
        goal=args.goal,
        kcal_target=kcal_target,
        kcal_range=(ends[0], ends[1]),
        floor_applied=floor_applied,
        protein=_macro(protein_g, config.KCAL_PER_G_PROTEIN, kcal_target, weight),
        carbohydrate=_macro(carb_g, config.KCAL_PER_G_CARBOHYDRATE, kcal_target, weight),
        fat=_macro(fat_g, config.KCAL_PER_G_FAT, kcal_target, weight),
        protein_g_range=(round(weight * protein_low), round(weight * protein_high)),
        notes=notes,
    )
