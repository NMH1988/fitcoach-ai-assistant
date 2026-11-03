"""Vega-Lite specs of the app's charts: the macro charts and, since T9.15, the dashboards' week.

Imports no streamlit (T8.1): a function returns the data, the spec and the text alternative, and
views/targets.py and views/week_view.py draw them, so the specs are unit-tested without AppTest.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from src import config, i18n, metrics, units
from src.i18n import Language
from views import tables


@dataclass(frozen=True)
class Chart:
    """What st.vega_lite_chart needs: the data columns, the Vega-Lite spec and the alt text."""

    data: dict
    spec: dict
    alt: str


def kcal_encoding(lang: Language) -> dict:
    """Return the tooltip field of a chart's kcal: a formatted number, as the language writes it."""
    # Vega formats numbers the English way; German gets the text the app formatted itself.
    if lang == "de":
        return {"field": "kcal_text", "type": "nominal", "title": "kcal"}
    return {"field": "kcal", "type": "quantitative", "format": ","}


def macro_bar(kcal: dict[str, int], lang: Language) -> Chart:
    """Return the kcal of each macro as one horizontal stacked bar, in the macro colours."""
    names = list(kcal)
    labels = [tables.macro_label(name, lang) for name in names]
    # A Vega-Lite spec rather than st.bar_chart, so the value axis starts at 0 (st.bar_chart's
    # started at -500 in a narrow window). `alt` is the chart's text alternative.
    alt = i18n.t(
        "chart.bar_alt",
        lang,
        parts=", ".join(
            f"{label} {i18n.number(value, lang)} kcal"
            for label, value in zip(labels, kcal.values(), strict=True)
        ),
    )
    x = {
        "field": "kcal",
        "type": "quantitative",
        "stack": "zero",
        # From 0 to the next round value, so the bar never ends at the chart's edge.
        "scale": {"domainMin": 0, "nice": True},
        "title": i18n.t("chart.kcal_per_day", lang),
    }
    if lang == "de":
        # German thousands marks on the axis ("2.000").
        x["axis"] = {"labelExpr": "replace(format(datum.value, ','), /,/g, '.')"}
    spec = {
        "mark": {"type": "bar"},
        "encoding": {
            "x": x,
            "y": {"field": "split", "type": "nominal", "title": None},
            "color": {
                "field": "macro",
                "type": "nominal",
                "sort": labels,
                "scale": {"domain": labels, "range": [config.MACRO_COLORS[n] for n in names]},
                "legend": {"orient": "bottom", "title": None},
            },
            # Typed as numbers: an untyped field is nominal, and a nominal kcal ignores the format.
            "order": {"field": "position", "type": "quantitative"},
            "tooltip": [{"field": "macro", "type": "nominal"}, kcal_encoding(lang)],
        },
    }
    data = {
        "macro": labels,
        "kcal": list(kcal.values()),
        "kcal_text": [i18n.number(value, lang) for value in kcal.values()],
        "split": [i18n.t("chart.energy", lang)] * len(names),
        "position": list(range(len(names))),
    }
    return Chart(data, spec, alt)


def macro_donut(kcal: dict[str, int], total: int, lang: Language) -> Chart:
    """Return the energy split as a donut in the sidebar's macro colours, the kcal in the middle."""
    names = list(kcal)
    labels = [tables.macro_label(name, lang) for name in names]
    parts = ", ".join(
        f"{label} {i18n.number(value, lang)} kcal"
        for label, value in zip(labels, kcal.values(), strict=True)
    )
    alt = i18n.t("chart.donut_alt", lang, total=i18n.number(total, lang), parts=parts)
    # One text mark per line in the middle, each with its own one-row data, so it is drawn once.
    # Streamlit's chart theme colours axes and legends but not text marks (black in dark mode), so
    # the text takes the page's text colour through the SVG's currentColor.
    centre = [
        {
            "data": {"values": [{"line": line}]},
            "mark": {
                "type": "text",
                "fontSize": size,
                "fontWeight": weight,
                "dy": dy,
                "color": "currentColor",
            },
            "encoding": {"text": {"field": "line", "type": "nominal"}},
        }
        for line, size, weight, dy in (
            (i18n.number(total, lang), 17, "bold", -7),
            ("kcal", 12, "normal", 11),
        )
    ]
    spec = {
        "layer": [
            {
                "mark": {
                    "type": "arc",
                    "innerRadius": config.MACRO_DONUT_INNER_RADIUS_PX,
                    # Gaps between the parts, so neighbouring colours never touch.
                    "padAngle": config.MACRO_DONUT_PAD_ANGLE,
                },
                "encoding": {
                    "theta": {"field": "kcal", "type": "quantitative", "stack": True},
                    "color": {
                        "field": "macro",
                        "type": "nominal",
                        "sort": labels,
                        "scale": {
                            "domain": labels,
                            # Drawn only in the deep green sidebar (T9.23).
                            "range": [config.SIDEBAR_MACRO_COLORS[n] for n in names],
                        },
                        "legend": {"orient": "right", "title": None},
                    },
                    "order": {"field": "position", "type": "quantitative"},
                    "tooltip": [{"field": "macro", "type": "nominal"}, kcal_encoding(lang)],
                },
            },
            *centre,
        ]
    }
    data = {
        "macro": labels,
        "kcal": list(kcal.values()),
        "kcal_text": [i18n.number(value, lang) for value in kcal.values()],
        "position": list(range(len(names))),
    }
    return Chart(data, spec, alt)


# The dashboards' charts (T9.15): a week's kcal per day, its macros against the target, the weight
# trend and the training volume per day. Each tooltip shows text the app formatted, so German gets
# its own number marks; the page also shows the values as text.
# The macros of a WeekMetrics average and target, by MACRO_COLORS name.
WEEK_MACROS = {"Protein": "protein_g", "Carbohydrate": "carbohydrate_g", "Fat": "fat_g"}


def _tip(field: str, title: str) -> dict:
    """Return a tooltip entry with a translated title, so no column name shows (round 3)."""
    return {"field": field, "type": "nominal", "title": title}


def day_label(day: date, lang: Language) -> str:
    """Return a day as a chart's axis shows it: the weekday and the day of the month ("Mon 26")."""
    return f"{i18n.t('week.weekdays', lang).split(',')[day.weekday()]} {day.day}"


def _days_axis(days: list[str]) -> dict:
    """Return the x encoding of a week's days, Monday first, every day on the axis."""
    return {
        "field": "day",
        "type": "ordinal",
        "sort": days,
        "scale": {"domain": days},
        "title": None,
        "axis": {"labelAngle": 0},
    }


def kcal_per_day(week: metrics.WeekMetrics, lang: Language) -> Chart:
    """Return the kcal per day as bars, "not logged" on a day with nothing, the target dashed."""
    days = [day_label(day, lang) for day, _ in week.days]
    not_logged = i18n.t("chart.not_logged", lang)
    kcal = [None if totals is None else round(totals.kcal) for _, totals in week.days]
    texts = [not_logged if value is None else f"{i18n.number(value, lang)} kcal" for value in kcal]
    parts = ", ".join(f"{day} {text}" for day, text in zip(days, texts, strict=True))
    alt = i18n.t("chart.kcal_days_alt", lang, parts=parts)
    tooltip = [_tip("day", i18n.t("chart.day", lang)), _tip("kcal_text", "kcal")]
    layers = [
        {
            "transform": [{"filter": "datum.logged"}],
            "mark": {"type": "bar"},
            "encoding": {
                "x": _days_axis(days),
                "y": {
                    "field": "kcal",
                    "type": "quantitative",
                    "scale": {"domainMin": 0, "nice": True},
                    "title": i18n.t("chart.kcal_per_day", lang),
                },
                "tooltip": tooltip,
            },
        },
        {
            # A day with nothing logged is marked as such, never drawn as zero eaten (AC-26).
            # Streamlit's chart theme does not colour text marks, so they take the page's colour.
            "transform": [{"filter": "!datum.logged"}],
            "mark": {
                "type": "text",
                "angle": -90,
                "align": "left",
                "dx": 4,
                "color": "currentColor",
            },
            "encoding": {
                "x": _days_axis(days),
                "y": {"datum": 0, "type": "quantitative"},
                "text": {"field": "kcal_text", "type": "nominal"},
                "tooltip": tooltip,
            },
        },
    ]
    if week.target is not None:
        target = round(week.target.kcal)
        alt += "; " + i18n.t("chart.target_alt", lang, target=i18n.number(target, lang))
        layers.append(
            {
                "data": {"values": [{"target": target}]},
                "mark": {"type": "rule", "strokeDash": [6, 4], "color": "currentColor"},
                "encoding": {"y": {"field": "target", "type": "quantitative"}},
            }
        )
    data = {
        "day": days,
        "kcal": [value or 0 for value in kcal],
        "kcal_text": texts,
        "logged": [value is not None for value in kcal],
    }
    return Chart(data, {"layer": layers}, alt)


def macros_vs_target(week: metrics.WeekMetrics, lang: Language) -> Chart | None:
    """Return the average grams per logged day beside the target's, per macro; None if none."""
    if week.average is None:
        return None
    names = list(WEEK_MACROS)
    labels = [tables.macro_label(name, lang) for name in names]
    series = [("average", week.average)]
    if week.target is not None:
        series.append(("target", week.target))
    rows = [
        (label, i18n.t(f"chart.{kind}", lang), round(getattr(source, field)))
        for kind, source in series
        for label, field in zip(labels, WEEK_MACROS.values(), strict=True)
    ]
    parts = ", ".join(f"{label} {kind} {i18n.number(grams, lang)} g" for label, kind, grams in rows)
    spec = {
        "mark": {"type": "bar"},
        "encoding": {
            "x": {
                "field": "macro",
                "type": "nominal",
                "sort": labels,
                "title": None,
                "axis": {"labelAngle": 0},
            },
            "xOffset": {"field": "series", "type": "nominal"},
            "y": {
                "field": "grams",
                "type": "quantitative",
                "title": i18n.t("chart.grams_per_day", lang),
            },
            "color": {
                "field": "macro",
                "type": "nominal",
                "sort": labels,
                "scale": {"domain": labels, "range": [config.MACRO_COLORS[n] for n in names]},
                "legend": None,
            },
            # The target's bars are lighter; the legend names the two. Its symbols take protein's
            # colour, as Vega's default black would not show in dark mode.
            "opacity": {
                "field": "series",
                "type": "nominal",
                # Average first, whatever the translations' alphabetical order.
                "sort": [i18n.t("chart.average", lang), i18n.t("chart.target", lang)],
                "scale": {"range": [1, 0.45]},
                "legend": {
                    "orient": "bottom",
                    "title": None,
                    "symbolType": "square",
                    "symbolFillColor": config.MACRO_COLORS["Protein"],
                    "symbolStrokeColor": config.MACRO_COLORS["Protein"],
                },
            },
            "tooltip": [
                _tip("macro", i18n.t("chart.macro", lang)),
                _tip("series", i18n.t("chart.series", lang)),
                _tip("grams_text", i18n.t("chart.grams_per_day", lang)),
            ],
        },
    }
    data = {
        "macro": [label for label, _, _ in rows],
        "series": [kind for _, kind, _ in rows],
        "grams": [grams for _, _, grams in rows],
        "grams_text": [f"{i18n.number(grams, lang)} g" for _, _, grams in rows],
    }
    return Chart(data, spec, i18n.t("chart.macros_alt", lang, parts=parts))


def weight_trend(
    points: Sequence[tuple[date, float]], system: units.UnitSystem, lang: Language
) -> Chart:
    """Return the weights over the trend's weeks as a line with points, in the user's units."""
    shown = [units.format_weight(kg, system, lang) for _, kg in points]
    parts = ", ".join(
        f"{day.isoformat()} {text}" for (day, _), text in zip(points, shown, strict=True)
    )
    spec = {
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {
                "field": "day",
                "type": "temporal",
                "title": None,
                # Vega reads "2026-10-29" as UTC midnight, so the scale and labels stay in UTC: in
                # local time a browser west of UTC would show the day before (code review round 2).
                "scale": {"type": "utc"},
                # At most one tick a day: with fewer days than ticks, Vega labelled each day twice.
                "axis": {"format": "%Y-%m-%d", "formatType": "utc", "tickMinStep": 86_400_000},
            },
            "y": {
                "field": "weight",
                "type": "quantitative",
                "scale": {"zero": False},
                "title": i18n.t("chart.weight_axis", lang, unit=units.weight_unit(system)),
            },
            # The day as the app wrote it, so no time zone can move it.
            "tooltip": [
                _tip("day_text", i18n.t("chart.day", lang)),
                _tip(
                    "weight_text", i18n.t("chart.weight_axis", lang, unit=units.weight_unit(system))
                ),
            ],
        },
    }
    data = {
        "day": [day.isoformat() for day, _ in points],
        "day_text": [day.isoformat() for day, _ in points],
        "weight": [units.weight_in(kg, system) for _, kg in points],
        "weight_text": shown,
    }
    return Chart(data, spec, i18n.t("chart.weight_alt", lang, parts=parts))


def volume_per_day(
    by_day: Sequence[tuple[date, float | None]], system: units.UnitSystem, lang: Language
) -> Chart:
    """Return the week's training volume per day as bars; a day with no workout has none."""
    days = [day_label(day, lang) for day, _ in by_day]
    texts = [
        i18n.t("chart.no_workout", lang) if kg is None else tables.volume_text(kg, system, lang)
        for _, kg in by_day
    ]
    parts = ", ".join(f"{day} {text}" for day, text in zip(days, texts, strict=True))
    spec = {
        "transform": [{"filter": "datum.trained"}],
        "mark": {"type": "bar"},
        "encoding": {
            "x": _days_axis(days),
            "y": {
                "field": "volume",
                "type": "quantitative",
                "scale": {"domainMin": 0, "nice": True},
                "title": i18n.t("chart.volume_axis", lang, unit=units.weight_unit(system)),
            },
            "tooltip": [
                _tip("day", i18n.t("chart.day", lang)),
                _tip(
                    "volume_text", i18n.t("chart.volume_axis", lang, unit=units.weight_unit(system))
                ),
            ],
        },
    }
    data = {
        "day": days,
        "volume": [0 if kg is None else round(units.weight_in(kg, system)) for _, kg in by_day],
        "volume_text": texts,
        "trained": [kg is not None for _, kg in by_day],
    }
    return Chart(data, spec, i18n.t("chart.volume_alt", lang, parts=parts))
