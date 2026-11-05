"""views/charts.py: the Vega-Lite specs, built without Streamlit (T8.1; the week's, T9.15)."""

from datetime import date

import pytest

from src import config, metrics
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


def test_the_donut_uses_the_sidebar_colours_and_the_german_total():
    """The sidebar's macro colours (T9.23), the legend on the right, German writes a point."""
    chart = charts.macro_donut(KCAL, 2950, "de")
    arc = chart.spec["layer"][0]["encoding"]
    assert arc["color"]["scale"]["range"] == [config.SIDEBAR_MACRO_COLORS[name] for name in KCAL]
    assert arc["color"]["legend"]["orient"] == "right"
    assert chart.spec["layer"][1]["data"]["values"] == [{"line": "2.950"}]
    assert "2.950" in chart.alt


def test_a_chart_is_a_value_that_cannot_be_changed():
    """The chart is frozen, so a view cannot alter a spec another view built."""
    chart = charts.macro_bar(KCAL, "en")
    with pytest.raises(AttributeError):
        chart.alt = "changed"  # type: ignore[misc]


# --- The dashboards' week (T9.15) -----------------------------------------------------------------

MONDAY = date(2026, 10, 26)
TARGET = {
    "id": 1,
    "effective_from": "2026-10-01",
    "kcal": 2400.0,
    "protein_g": 150.0,
    "carbs_g": 250.0,
    "fat_g": 70.0,
    "set_by": "system",
}


def _meal(day: str, kcal: float) -> dict:
    """Return a stored meal item row of one day."""
    return {
        "consumed_on": day,
        "kcal": kcal,
        "protein_g": 120.0,
        "carbohydrate_g": 210.0,
        "fat_g": 60.0,
        "fiber_g": 10.0,
    }


def _week(targets=(TARGET,)) -> metrics.WeekMetrics:
    """Return a week logged on Monday, Tuesday and Thursday, with or without a target."""
    meals = [_meal("2026-10-26", 2000), _meal("2026-10-27", 2250.4), _meal("2026-10-29", 2300)]
    return metrics.week_metrics(meals, [], list(targets), MONDAY)


def _layer(chart: charts.Chart, mark: str) -> dict:
    """Return the one layer of a chart with this mark type."""
    (found,) = [layer for layer in chart.spec["layer"] if layer["mark"]["type"] == mark]
    return found


def _week_charts(lang: str) -> list[charts.Chart]:
    """Return the four week charts built from the test week."""
    points = ((date(2026, 10, 20), 80.0),)
    sessions = [{"id": 1, "performed_on": "2026-10-27", "sets": [{"reps": 5, "weight_kg": 100.0}]}]
    return [
        charts.kcal_per_day(_week(), lang),
        charts.macros_vs_target(_week(), lang),
        charts.weight_trend(points, "metric", lang),
        charts.volume_per_day(metrics.volume_by_day(sessions, MONDAY), "metric", lang),
    ]


def _tooltips(spec: dict) -> list[dict]:
    """Return every tooltip entry of a spec, in its layers too."""
    found = []
    for part in (spec, *spec.get("layer", ())):
        found += part.get("encoding", {}).get("tooltip", [])
    return found


@pytest.mark.parametrize("lang", ["en", "de"])
def test_every_week_tooltip_has_a_translated_title(lang):
    """Round 3: no tooltip shows a column name ("kcal_text"); each has the language's title."""
    for chart in _week_charts(lang):
        tooltips = _tooltips(chart.spec)
        assert tooltips
        for entry in tooltips:
            assert entry.get("title"), entry
            assert entry["title"] != entry["field"]
            # Round 4: the value shows the unit, so the title does not ("kcal: 2,000 kcal").
            assert not {"kcal", "kg", "lb", "g"} & set(entry["title"].replace("(", " ").split())
    titles = [[entry["title"] for entry in _tooltips(chart.spec)] for chart in _week_charts(lang)]
    assert (
        titles
        == {
            "en": [
                ["Day", "Energy"] * 2,  # the bars and the "not logged" marks
                ["Macro", "Average or target", "Per day"],
                ["Day", "Weight"],
                ["Day", "Volume"],
            ],
            "de": [
                ["Tag", "Energie"] * 2,
                ["Makronährstoff", "Durchschnitt oder Ziel", "Pro Tag"],
                ["Tag", "Gewicht"],
                ["Tag", "Volumen"],
            ],
        }[lang]
    )


@pytest.mark.parametrize(("lang", "monday"), [("en", "Mon 26"), ("de", "Mo 26")])
def test_the_days_are_labelled_by_weekday_and_day(lang, monday):
    """The axis shows each of the seven days, Monday first, in the language."""
    chart = charts.kcal_per_day(_week(), lang)
    assert chart.data["day"][0] == monday and len(chart.data["day"]) == 7
    assert _layer(chart, "bar")["encoding"]["x"]["scale"]["domain"] == chart.data["day"]


def test_a_day_not_logged_is_marked_never_drawn_as_zero_eaten():
    """AC-26: the bars show logged days only; the others get a "not logged" text mark."""
    chart = charts.kcal_per_day(_week(), "en")
    assert chart.data["logged"] == [True, True, False, True, False, False, False]
    assert chart.data["kcal_text"][:3] == ["2,000 kcal", "2,250 kcal", "not logged"]
    assert _layer(chart, "bar")["transform"] == [{"filter": "datum.logged"}]
    text = _layer(chart, "text")
    assert text["transform"] == [{"filter": "!datum.logged"}]
    assert text["encoding"]["text"]["field"] == "kcal_text"
    assert "Wed 28 not logged" in chart.alt


def test_the_target_is_a_dashed_rule_only_when_there_is_one():
    """The target is drawn as a dashed line and named in the alt text; no target, no line."""
    chart = charts.kcal_per_day(_week(), "de")
    rule = _layer(chart, "rule")
    assert rule["data"]["values"] == [{"target": 2400}]
    assert rule["mark"]["strokeDash"]
    assert chart.alt.endswith("Ziel 2.400 kcal")
    without = charts.kcal_per_day(_week(targets=()), "en")
    assert [layer["mark"]["type"] for layer in without.spec["layer"]] == ["bar", "text"]


def test_the_macros_chart_puts_the_average_beside_the_target():
    """Each macro has an average bar and a lighter target bar, in the macro colours."""
    chart = charts.macros_vs_target(_week(), "en")
    assert chart.data["macro"] == ["Protein", "Carbohydrate", "Fat"] * 2
    assert chart.data["series"] == ["Average"] * 3 + ["Target"] * 3
    assert chart.data["grams"] == [120, 210, 60, 150, 250, 70]
    colour = chart.spec["encoding"]["color"]["scale"]
    assert colour["range"] == list(config.MACRO_COLORS.values())
    assert chart.spec["encoding"]["xOffset"]["field"] == "series"
    # The average is solid and the target light, whatever order the words sort in (round 2).
    assert chart.spec["encoding"]["opacity"]["sort"] == ["Average", "Target"]
    assert "Protein Target 150 g" in chart.alt


def test_no_macros_chart_without_a_logged_day_and_no_target_bars_without_a_target():
    """Nothing logged gives no chart; no target gives the averages only."""
    assert charts.macros_vs_target(metrics.week_metrics([], [], [], MONDAY), "en") is None
    chart = charts.macros_vs_target(_week(targets=()), "de")
    assert chart.data["series"] == ["Durchschnitt"] * 3


def test_the_weight_trend_is_in_the_user_s_units():
    """The weights are converted for the chart and written in the user's units in the alt text."""
    points = ((date(2026, 10, 20), 80.0), (date(2026, 10, 28), 79.4))
    chart = charts.weight_trend(points, "imperial", "en")
    assert chart.data["day"] == ["2026-10-20", "2026-10-28"]
    assert chart.data["weight"] == [176.4, 175.0]  # units.weight_in() rounds to 0.1
    assert chart.spec["encoding"]["y"]["title"] == "Weight (lb)"
    assert chart.spec["encoding"]["y"]["scale"] == {"zero": False}
    # The days stay in UTC, as Vega reads an ISO day: no time zone moves a point (round 2).
    x = chart.spec["encoding"]["x"]
    assert x["scale"] == {"type": "utc"}
    # The labels are ISO days in UTC, in any language (the owner's screenshots of 2026-11-05).
    assert x["axis"]["labelExpr"] == "utcFormat(datum.value, '%Y-%m-%d')"
    assert "format" not in x["axis"] and "formatType" not in x["axis"]
    assert chart.spec["encoding"]["tooltip"][0] == {
        "field": "day_text",
        "type": "nominal",
        "title": "Day",
    }
    assert chart.data["day_text"] == ["2026-10-20", "2026-10-28"]
    assert chart.alt == "Weights: 2026-10-20 176.4 lb, 2026-10-28 175 lb"


def test_the_volume_has_bars_on_training_days_only():
    """A day with no workout has no bar and says so in the alt text; volume in the user's units."""
    sessions = [
        {"id": 1, "performed_on": "2026-10-27", "sets": [{"reps": 5, "weight_kg": 100.0}]},
    ]
    chart = charts.volume_per_day(metrics.volume_by_day(sessions, MONDAY), "metric", "de")
    assert chart.data["trained"] == [False, True, False, False, False, False, False]
    assert chart.data["volume"][1] == 500
    assert chart.spec["transform"] == [{"filter": "datum.trained"}]
    assert chart.spec["encoding"]["y"]["title"] == "Volumen (kg)"
    assert "Di 27 500 kg" in chart.alt and "Mo 26 kein Training" in chart.alt
