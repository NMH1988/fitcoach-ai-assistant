"""Tests for src/i18n.py: both languages complete, the locale mapping, numbers, message codes."""

import re
import string
from decimal import Decimal

import pytest

from src import chat, config, guard, guardrails, i18n, llm, profile, units, usage
from src.rag import sources, store
from src.tools import meal_plan, registry

# --- Every key in both languages (AC 1) -----------------------------------------------------------


def _placeholders(text: str) -> set[str]:
    """Return the names of a text's {placeholders}."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_key_exists_in_both_languages():
    """A key in one language but not the other fails the test."""
    assert set(i18n.TEXT["en"]) == set(i18n.TEXT["de"])


@pytest.mark.parametrize("key", sorted(i18n.TEXT["en"]))
def test_each_text_is_filled_and_has_the_same_placeholders_in_both_languages(key):
    """No text is empty, and both languages fill the same {placeholders}."""
    english, german = i18n.TEXT["en"][key], i18n.TEXT["de"][key]
    assert english.strip() and german.strip()
    assert _placeholders(english) == _placeholders(german), key


def test_the_german_texts_use_the_formal_sie():
    """German speaks to the user as "Sie", never "du" (docs/UI_DESIGN.md)."""
    informal = re.compile(r"\b(?:du|dich|dir|dein\w*)\b", re.IGNORECASE)
    assert not [key for key, text in i18n.TEXT["de"].items() if informal.search(text)]


# --- The browser's language (AC 3) ----------------------------------------------------------------


@pytest.mark.parametrize("locale", ["de", "de-DE", "de-AT", "de-CH", "DE-de"])
def test_a_german_browser_locale_gives_german(locale):
    """Any de* locale starts the session in German."""
    assert i18n.language_for_locale(locale) == "de"


@pytest.mark.parametrize("locale", [None, "", "en-US", "en-GB", "fr-FR", "nl-NL", "dk", "es"])
def test_any_other_locale_or_none_gives_english(locale):
    """Every other locale, and none at all (as under AppTest), starts in English."""
    assert i18n.language_for_locale(locale) == "en"


# --- Numbers (owner's choice: German marks in German) ---------------------------------------------


@pytest.mark.parametrize(
    ("value", "english", "german"),
    [
        (2500, "2,500", "2.500"),
        (1234567, "1,234,567", "1.234.567"),
        (55.6, "55.6", "55,6"),
        (3035.0, "3,035", "3.035"),
        (0, "0", "0"),
    ],
)
def test_numbers_get_the_language_s_thousands_and_decimal_marks(value, english, german):
    """English writes 2,500.5, German 2.500,5."""
    assert i18n.number(value, "en") == english
    assert i18n.number(value, "de") == german


def test_plain_numbers_have_no_thousands_marks():
    """Limits and ages are written without marks; German uses the decimal comma."""
    assert i18n.plain(2000, "en") == i18n.plain(2000, "de") == "2000"
    assert (i18n.plain(1.9, "en"), i18n.plain(1.9, "de")) == ("1.9", "1,9")


def test_t_fills_numbers_in_the_language_s_style():
    """Numbers passed to t() are shown with the language's decimal mark."""
    assert i18n.t("food.matched", "en", grams=12.5) == "Matched USDA food, 12.5 g:"
    assert i18n.t("food.matched", "de", grams=12.5) == "Gefundenes USDA-Lebensmittel, 12,5 g:"


def test_the_units_show_german_decimals_and_keep_english_by_default():
    """Weights and grams per body weight use the decimal comma in German only."""
    assert units.format_weight(80.5, "metric") == "80.5 kg"
    assert units.format_weight(80.5, "metric", "de") == "80,5 kg"
    assert units.format_per_body_weight(1.94, "metric", "de") == "1,9 g/kg"


# --- English is the same as the modules' own texts (model, PDF, guard) ----------------------------


def test_the_english_labels_are_the_ones_the_model_and_the_pdf_get():
    """Profile, unit, status, tier, topic and tool labels match their modules."""
    labels = [
        ("goal", profile.GOAL_LABELS),
        ("sex", profile.SEX_LABELS),
        ("activity", profile.ACTIVITY_LABELS),
        ("activity_short", profile.ACTIVITY_SHORT_LABELS),
        ("units", units.UNIT_SYSTEM_LABELS),
        ("status", config.STATUS_LABELS),
        ("tier", config.EVIDENCE_TIER_LABELS),
        ("correction", config.CORRECTION_LABELS),
        ("topic", config.TOPIC_LABELS),
    ]
    for prefix, mapping in labels:
        for value, label in mapping.items():
            assert i18n.t(f"{prefix}.{value}", "en") == label, (prefix, value)
    assert i18n.t("tier.unknown", "en") == config.UNKNOWN_TIER_LABEL
    for name, title in registry.TOOL_TITLES.items():
        assert i18n.t(f"tool.title.{name or 'none'}", "en") == title
    for step in chat.Step:
        assert i18n.t(f"step.{step.name.lower()}", "en") == step.value
    assert i18n.t("about.changes", "en") == sources.ARTICLE_CHANGES_NOTE


def test_the_english_guard_and_guardrail_messages_match_the_guard():
    """Each guard code gives the guard's own English message."""
    assert i18n.t("guard.empty", "en") == guard.EMPTY_MESSAGE
    assert i18n.t("guard.too_long", "en") == guard.TOO_LONG_MESSAGE
    assert i18n.t("guard.injection", "en") == guard.INJECTION_MESSAGE
    assert i18n.t("guard.rate_window", "en", seconds=7) == guard.RATE_WINDOW_MESSAGE.format(
        seconds=7
    )
    assert i18n.t("guard.rate_session", "en", limit=50) == guard.RATE_SESSION_MESSAGE.format(
        limit=50
    )
    for concern, message in guardrails.MESSAGES.items():
        assert i18n.t(f"guardrail.{concern.value}", "en") == message


def _subclasses(cls: type) -> list[type]:
    """Return a class and all its subclasses."""
    return [cls, *(sub for child in cls.__subclasses__() for sub in _subclasses(child))]


def test_every_model_error_has_a_code_with_its_english_message():
    """Each LLMError (ToolLoopError too) names a key whose English is its user message."""
    for error in _subclasses(llm.LLMError):
        assert i18n.t(error.code, "en") == error.user_message, error.__name__
        assert error.code in i18n.TEXT["de"]


@pytest.mark.parametrize(
    "reason", [store._MISSING, store.UNREADABLE, store._EMPTY, store._OTHER_MODEL]
)
def test_every_index_error_has_a_code_with_its_english_message(reason):
    """A missing, unreadable, empty or other-model index names a key with the same English."""
    error = store.IndexNotReadyError(reason)
    assert i18n.t(error.code, "en") == str(error)


def test_the_other_fixed_messages_match_their_english():
    """The "not covered", key and prompt messages are the ones in config."""
    assert i18n.t("answer.no_sources", "en") == config.NO_SOURCES_MESSAGE
    assert i18n.t("key.missing", "en") == config.MISSING_KEY_MESSAGE
    assert i18n.t("key.secrets_file", "en") == config.SECRETS_FILE_MESSAGE
    assert i18n.t("prompt.answer_missing", "en") == config.PROMPT_MISSING_MESSAGE
    assert i18n.t("prompt.query_missing", "en") == config.QUERY_PROMPT_MISSING_MESSAGE


def test_every_guard_rejection_has_a_code_in_both_languages():
    """The guard's codes (one per rejection, one per guardrail) all have a text."""
    codes = {f"guard.{reason.value}" for reason in guard.Rejection} - {"guard.guardrail"}
    codes |= {f"guardrail.{concern.value}" for concern in guardrails.Concern}
    for lang in i18n.LANGUAGES:
        assert codes <= set(i18n.TEXT[lang])


def test_a_rejection_carries_its_code_and_numbers():
    """A rate-limited message keeps the seconds to wait for the UI's own language."""
    limiter = guard.RateLimiter(per_window=1, clock=lambda: 0.0)
    assert guard.check_message("Protein per day?", limiter).allowed
    result = guard.check_message("Protein per day?", limiter)
    assert result.code == "guard.rate_window"
    assert i18n.t(result.code, "de", **result.params).startswith("Sie senden Fragen zu schnell.")
    redirect = guard.check_message("Ich bin schwanger, wie viel Protein?", limiter)
    assert redirect.code == "guardrail.pregnancy"


def test_profile_problems_have_their_english_and_german_messages():
    """ProfileError keeps the English messages and gives them in German too."""
    with pytest.raises(profile.ProfileError) as caught:
        profile.build_profile(
            units_system="metric",
            weight=10,
            height_cm=None,
            age=12,
            sex=None,
            activity=None,
            goal=None,
        )
    error = caught.value
    assert error.messages[0] == "Weight must be between 30 and 300 kg."
    german = error.messages_in("de")
    assert german[0] == "Das Gewicht muss zwischen 30 und 300 kg liegen."
    # Weight, height, age, sex, activity and goal: one problem each.
    assert len(german) == len(error.messages) == 6


# --- German formats of costs, tokens and the meal plan (owner's choice) ---------------------------


@pytest.mark.parametrize(
    ("cost", "english", "german"),
    [
        (None, "price unknown", "Preis unbekannt"),
        (Decimal("0"), "$0", "0 $"),
        (Decimal("0.00004"), "<$0.0001", "<0,0001 $"),
        (Decimal("0.0012"), "$0.0012", "0,0012 $"),
        (Decimal("12.34567"), "$12.3457", "12,3457 $"),
    ],
)
def test_costs_are_written_the_language_s_way(cost, english, german):
    """English puts the dollar first with a decimal point, German last with a decimal comma."""
    assert usage.format_cost(cost) == english
    assert usage.format_cost(cost, "de") == german


def test_token_counts_and_the_session_line_in_german():
    """Thousands marks, the noun and the unknown part of a session's cost are German."""
    assert usage.format_tokens(1234, "de") == "1.234 Token"
    assert usage.format_tokens(1, "en") == "1 token"
    session = usage.SessionUsage(tokens=3700, cost=Decimal("0.0074"), partial=True)
    assert usage.format_session(session, "de") == "3.700 Token · 0,0074 $ + Preis unbekannt"


def _check(**fields) -> meal_plan.NutrientCheck:
    """Return a meal plan's check of one nutrient with these fields."""
    base = {"nutrient": "kcal", "unit": "kcal", "plan_total": 1800, "target": 2000, "gap": 200}
    return meal_plan.NutrientCheck(**(base | fields))


def test_the_meal_plan_cells_in_german():
    """The plan's differences, ranges and food rows use German words and marks."""
    assert meal_plan.difference_text(_check(), "de") == "200 kcal unter dem Ziel"
    assert meal_plan.difference_text(_check(gap=-1250), "de") == "1.250 kcal über dem Ziel"
    within = _check(target_range=(1600, 2000), range_position="within")
    assert meal_plan.range_text(within, "de") == "Im Bereich 1.600-2.000 kcal"
    assert meal_plan.range_text(within) == "Within 1,600-2,000 kcal"
    item = meal_plan.MealItem(requested="Haferflocken", grams=80.5, status="not_found")
    assert meal_plan.food_row(item, "de")[1:3] == ["Nicht gefunden", "80,5 g"]
    assert meal_plan.food_columns("de")[0] == "Angefragtes Lebensmittel"
    assert meal_plan.FOOD_COLUMNS[0] == "Food asked"
