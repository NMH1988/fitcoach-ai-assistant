"""views/charts.py: the macro charts' Vega-Lite specs, built without Streamlit (T8.1)."""

import pytest

from src import config
from views import charts

KCAL = {"Protein": 640, "Carbohydrate": 1500, "Fat": 810}


def test_the_english_tooltip_formats_kcal_with_vega():
    """English leaves the number to Vega's own thousands format."""
    assert charts.kcal_encoding("en") == {"field": "kcal", "type": "quantitative", "format": ","}


def test_the_german_tooltip_shows_the_text_the_app_formatted():
    """German gets the preformatted text, as Vega formats numbers the English way."""
    assert charts.kcal_encoding("de") == {"field": "kcal_text", "type": "nominal", "title": "kcal"}


@pytest.mark.parametrize("lang", ["en", "de"])
def test_the_bar_has_one_part_per_macro_in_the_macro_colours(lang):
    """The data has a row per macro; the colour scale follows the macro colours."""
    chart = charts.macro_bar(KCAL, lang)
    assert chart.data["kcal"] == [640, 1500, 810]
    assert chart.data["position"] == [0, 1, 2]
    colour = chart.spec["encoding"]["color"]["scale"]
    assert colour["domain"] == chart.data["macro"]
    assert colour["range"] == [config.MACRO_COLORS[name] for name in KCAL]


def test_the_bar_starts_at_zero_and_stacks():
    """The value axis starts at 0 and the parts are stacked from zero, in order."""
    spec = charts.macro_bar(KCAL, "en").spec
    x = spec["encoding"]["x"]
    assert x["scale"] == {"domainMin": 0, "nice": True}
    assert x["stack"] == "zero"
    # Typed as numbers: an untyped field is nominal and ignores the format.
    assert spec["encoding"]["order"]["type"] == "quantitative"


def test_the_german_bar_writes_thousands_with_a_point_on_its_axis():
    """Only the German axis has a label expression, replacing the comma with a point."""
    assert "axis" not in charts.macro_bar(KCAL, "en").spec["encoding"]["x"]
    assert "replace" in charts.macro_bar(KCAL, "de").spec["encoding"]["x"]["axis"]["labelExpr"]


def test_the_bar_names_the_macros_and_numbers_in_the_language():
    """The text alternative lists each macro with its kcal as the language writes it."""
    english = charts.macro_bar(KCAL, "en")
    german = charts.macro_bar(KCAL, "de")
    assert "Protein 640 kcal" in english.alt
    assert "1,500 kcal" in english.alt
    assert "1.500 kcal" in german.alt
    assert german.data["macro"] != english.data["macro"]
    assert german.data["kcal_text"] == ["640", "1.500", "810"]


def test_the_donut_has_the_arc_and_two_lines_of_text_in_the_middle():
    """One arc layer, then the total and "kcal" as text marks in the page's text colour."""
    chart = charts.macro_donut(KCAL, 2950, "en")
    arc, total, unit = chart.spec["layer"]
    assert arc["mark"]["innerRadius"] == config.MACRO_DONUT_INNER_RADIUS_PX
    assert arc["mark"]["padAngle"] == config.MACRO_DONUT_PAD_ANGLE
    assert total["data"]["values"] == [{"line": "2,950"}]
    assert unit["data"]["values"] == [{"line": "kcal"}]
    assert total["mark"]["color"] == unit["mark"]["color"] == "currentColor"


def test_the_donut_keeps_the_macro_colours_and_the_german_total():
    """The legend sits on the right; German writes the total with a point."""
    chart = charts.macro_donut(KCAL, 2950, "de")
    arc = chart.spec["layer"][0]["encoding"]
    assert arc["color"]["scale"]["range"] == [config.MACRO_COLORS[name] for name in KCAL]
    assert arc["color"]["legend"]["orient"] == "right"
    assert chart.spec["layer"][1]["data"]["values"] == [{"line": "2.950"}]
    assert "2.950" in chart.alt


def test_a_chart_is_a_value_that_cannot_be_changed():
    """The chart is frozen, so a view cannot alter a spec another view built."""
    chart = charts.macro_bar(KCAL, "en")
    with pytest.raises(AttributeError):
        chart.alt = "changed"  # type: ignore[misc]
