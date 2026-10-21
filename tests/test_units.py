"""Unit tests for src/units.py: kg/lb and cm/ft-in conversion and display."""

import pytest

from src import i18n, units


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
    assert {f"units.{system}" for system in units.UNIT_SYSTEMS} <= set(i18n.TEXT["en"])


@pytest.mark.parametrize(
    ("g_per_kg", "system", "expected"),
    [
        (1.9, "metric", "1.9 g/kg"),
        (2.0, "metric", "2 g/kg"),
        (1.9, "imperial", "0.86 g/lb"),
        (2.2, "imperial", "1 g/lb"),
        (1.1, "imperial", "0.5 g/lb"),
    ],
)
def test_format_per_body_weight(g_per_kg, system, expected):
    """Grams per body weight show per kg in metric and per lb (to 0.01 g) in imperial."""
    assert units.format_per_body_weight(g_per_kg, system) == expected


def test_per_lb_and_back_gives_the_per_kg_value():
    """A per-lb value converted back to per kg is the per-kg value, within the rounding."""
    per_lb = float(units.format_per_body_weight(1.9, "imperial").split()[0])
    assert per_lb / units.KG_PER_LB == pytest.approx(1.9, abs=0.01 / units.KG_PER_LB)


@pytest.mark.parametrize(
    ("g_per_kg", "system", "value", "shown"),
    [
        (1.9, "metric", 1.9, "1.9 g/kg"),
        (2.0, "metric", 2.0, "2 g/kg"),
        # 1.9 g/kg x 0.45359237 kg/lb = 0.8618 g/lb.
        (1.9, "imperial", 0.86, "0.86 g/lb"),
        (2.2, "imperial", 1.0, "1 g/lb"),
        (1.6, "imperial", 0.73, "0.73 g/lb"),
    ],
)
def test_grams_per_body_weight_follow_the_unit_system(g_per_kg, system, value, shown):
    """Grams per kg are shown as g/kg in metric and converted to g/lb in imperial (T4.7)."""
    assert units.per_body_weight(g_per_kg, system) == value
    assert units.format_per_body_weight(g_per_kg, system) == shown


def test_grams_per_lb_convert_back_to_grams_per_kg_within_rounding():
    """g/lb converted back to g/kg gives the g/kg value within the shown rounding (AC-8)."""
    for tenths in range(10, 31):
        g_per_kg = tenths / 10
        back = units.per_body_weight(g_per_kg, "imperial") / units.KG_PER_LB
        assert back == pytest.approx(g_per_kg, abs=0.005 / units.KG_PER_LB)


@pytest.mark.parametrize(
    ("grams", "weight_kg", "metric", "imperial"),
    [
        # 42 / 40.1 = 1.047 g/kg: rounded twice (1.05, then 1.1) it showed 1.1 (PR #53 review).
        (42, 40.1, "1 g/kg", "0.48 g/lb"),
        # 50 / 60 = 0.833 g/kg = 0.378 g/lb; from a g/kg rounded to 0.8 it showed 0.36 g/lb.
        (50, 60, "0.8 g/kg", "0.38 g/lb"),
        (51, 80, "0.6 g/kg", "0.29 g/lb"),
        (52, 70, "0.7 g/kg", "0.34 g/lb"),
        (152, 80, "1.9 g/kg", "0.86 g/lb"),
        (418, 80, "5.2 g/kg", "2.37 g/lb"),
        (84, 80, "1.1 g/kg", "0.48 g/lb"),
    ],
)
def test_grams_per_body_weight_are_rounded_once_from_the_grams(grams, weight_kg, metric, imperial):
    """Grams per body weight are grams over the weight, rounded once, in each unit system."""
    assert units.format_grams_per_body_weight(grams, weight_kg, "metric") == metric
    assert units.format_grams_per_body_weight(grams, weight_kg, "imperial") == imperial


def test_grams_per_body_weight_match_a_single_rounding_across_profiles():
    """Over many weights and grams, the shown value is the single rounding of grams / weight."""
    for weight_tenths in range(400, 2000, 7):
        weight_kg = weight_tenths / 10
        for grams in range(20, 400, 3):
            per_kg = grams / weight_kg
            assert units.format_grams_per_body_weight(grams, weight_kg, "metric") == (
                f"{round(per_kg, 1):g} g/kg"
            )
            assert units.format_grams_per_body_weight(grams, weight_kg, "imperial") == (
                f"{round(per_kg * units.KG_PER_LB, 2):g} g/lb"
            )
