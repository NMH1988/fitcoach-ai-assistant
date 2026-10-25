"""Vega-Lite specs of the macro charts, built from the kcal of each macro in a given language.

Imports no streamlit (T8.1): a function returns the data, the spec and the text alternative, and
views/targets.py draws them, so the specs are unit-tested without AppTest.
"""

from dataclasses import dataclass

from src import config, i18n
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
    """Return the energy split as a donut in the macro colours, the daily kcal in the middle."""
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
                            "range": [config.MACRO_COLORS[n] for n in names],
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
