"""Unit conversion: kg/lb and cm/ft-in, and how weights and heights are shown.

The app works in kg and cm everywhere; other units exist only at input and display.
"""

from typing import Literal

UnitSystem = Literal["metric", "imperial"]
UNIT_SYSTEMS: tuple[UnitSystem, ...] = ("metric", "imperial")
UNIT_SYSTEM_LABELS: dict[UnitSystem, str] = {
    "metric": "Metric (kg, cm)",
    "imperial": "Imperial (lb, ft/in)",
}

# Exact by definition (the international yard and pound, 1959).
KG_PER_LB = 0.45359237
CM_PER_INCH = 2.54
INCHES_PER_FOOT = 12

# Weights are shown to 0.1 kg or lb; heights to the whole cm or inch.
WEIGHT_DECIMALS = 1


def kg_to_lb(kg: float) -> float:
    """Convert kilograms to pounds."""
    return kg / KG_PER_LB


def lb_to_kg(lb: float) -> float:
    """Convert pounds to kilograms."""
    return lb * KG_PER_LB


def ft_in_to_cm(feet: float, inches: float) -> float:
    """Convert a height in feet and inches to centimetres."""
    return (feet * INCHES_PER_FOOT + inches) * CM_PER_INCH


def cm_to_ft_in(cm: float) -> tuple[int, int]:
    """Convert centimetres to whole feet and inches, rounded to the nearest inch."""
    feet, inches = divmod(round(cm / CM_PER_INCH), INCHES_PER_FOOT)
    return int(feet), int(inches)


def weight_to_kg(value: float, units: UnitSystem) -> float:
    """Convert a weight given in a unit system to kilograms."""
    return value if units == "metric" else lb_to_kg(value)


def weight_in(kg: float, units: UnitSystem) -> float:
    """Return a weight in the given unit system, rounded as it is shown."""
    value = kg if units == "metric" else kg_to_lb(kg)
    return round(value, WEIGHT_DECIMALS)


def weight_unit(units: UnitSystem) -> str:
    """Return the weight unit symbol of a unit system."""
    return "kg" if units == "metric" else "lb"


def format_weight(kg: float, units: UnitSystem) -> str:
    """Show a weight in the given unit system, e.g. "80.5 kg" or "177.5 lb"."""
    return f"{weight_in(kg, units):g} {weight_unit(units)}"


def format_height(cm: float, units: UnitSystem) -> str:
    """Show a height in the given unit system, e.g. "180 cm" or "5 ft 11 in"."""
    if units == "metric":
        return f"{round(cm)} cm"
    feet, inches = cm_to_ft_in(cm)
    return f"{feet} ft {inches} in"
