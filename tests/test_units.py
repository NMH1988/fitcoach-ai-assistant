"""Unit tests for src/units.py: kg/lb and cm/ft-in conversion and display."""

import pytest

from src import units


@pytest.mark.parametrize(
    ("kg", "lb"),
    [(1.0, 2.2046226218), (0.45359237, 1.0), (80.0, 176.3698097), (30.0, 66.1386787)],
)
def test_kg_and_lb_known_values(kg, lb):
    """Kilograms and pounds convert both ways at the defined 0.45359237 kg per lb."""
    assert units.kg_to_lb(kg) == pytest.approx(lb)
    assert units.lb_to_kg(lb) == pytest.approx(kg)


@pytest.mark.parametrize(
    ("feet", "inches", "cm"),
    [(1, 0, 30.48), (0, 1, 2.54), (5, 11, 180.34), (6, 0, 182.88)],
)
def test_ft_in_to_cm_known_values(feet, inches, cm):
    """Feet and inches convert to centimetres at 2.54 cm per inch."""
    assert units.ft_in_to_cm(feet, inches) == pytest.approx(cm)


@pytest.mark.parametrize(
    ("cm", "expected"),
    [(180.0, (5, 11)), (182.88, (6, 0)), (152.4, (5, 0)), (120.0, (3, 11))],
)
def test_cm_to_ft_in_known_values(cm, expected):
    """Centimetres convert to whole feet and inches."""
    assert units.cm_to_ft_in(cm) == expected


def test_cm_to_ft_in_carries_twelve_inches_into_a_foot():
    """A height that rounds up to 12 inches shows as the next foot, never as "5 ft 12 in"."""
    assert units.cm_to_ft_in(units.ft_in_to_cm(5, 11.6)) == (6, 0)


@pytest.mark.parametrize("kg", [30.0, 55.3, 80.0, 123.45, 300.0])
def test_weight_round_trip_is_exact(kg):
    """kg -> lb -> kg returns the same value (no rounding inside the app)."""
    assert units.lb_to_kg(units.kg_to_lb(kg)) == pytest.approx(kg, abs=1e-9)


@pytest.mark.parametrize("cm", [120.0, 165.5, 180.0, 199.9, 230.0])
def test_height_round_trip_is_exact(cm):
    """cm -> inches -> cm returns the same value when the inches are not rounded."""
    inches = cm / units.CM_PER_INCH
    assert units.ft_in_to_cm(0, inches) == pytest.approx(cm, abs=1e-9)


@pytest.mark.parametrize("kg", [30.0, 55.3, 80.0, 123.45, 300.0])
def test_weight_round_trip_through_display_is_within_rounding(kg):
    """kg -> shown lb -> kg stays within half the shown step of 0.1 lb (AC-8)."""
    shown_lb = units.weight_in(kg, "imperial")
    assert abs(units.lb_to_kg(shown_lb) - kg) <= units.lb_to_kg(0.05) + 1e-9
    assert units.weight_in(units.lb_to_kg(shown_lb), "metric") == pytest.approx(round(kg, 1))


@pytest.mark.parametrize("cm", [120.0, 165.5, 180.0, 199.9, 230.0])
def test_height_round_trip_through_display_is_within_rounding(cm):
    """cm -> shown ft/in -> cm stays within half an inch (AC-8)."""
    feet, inches = units.cm_to_ft_in(cm)
    assert abs(units.ft_in_to_cm(feet, inches) - cm) <= units.CM_PER_INCH / 2 + 1e-9


@pytest.mark.parametrize(
    ("kg", "system", "expected"),
    [
        (80.0, "metric", "80 kg"),
        (80.46, "metric", "80.5 kg"),
        (80.0, "imperial", "176.4 lb"),
        (300.0, "metric", "300 kg"),
    ],
)
def test_format_weight(kg, system, expected):
    """Weights are shown to 0.1 in the chosen unit, without a trailing ".0"."""
    assert units.format_weight(kg, system) == expected


@pytest.mark.parametrize(
    ("cm", "system", "expected"),
    [(180.0, "metric", "180 cm"), (180.4, "metric", "180 cm"), (180.0, "imperial", "5 ft 11 in")],
)
def test_format_height(cm, system, expected):
    """Heights are shown as whole cm, or whole feet and inches."""
    assert units.format_height(cm, system) == expected


def test_every_unit_system_has_a_label():
    """Each unit system has a label for the units switch."""
    assert set(units.UNIT_SYSTEM_LABELS) == set(units.UNIT_SYSTEMS)
