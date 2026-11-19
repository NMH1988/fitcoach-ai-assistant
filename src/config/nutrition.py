"""The energy and macro calculations, the USDA foods table and the FoodData Central API."""

# Written with every target the app computes (set_by = "system"), so a later change to
# calculate_macro_targets can tell old targets apart; bump it when that calculation changes.
TARGET_CALC_VERSION = "macro-targets-1"

# calculate_tdee (docs/ARCHITECTURE.md section 6). Values approved by the owner (O3);
# the numbers in brackets are source IDs in docs/SOURCES.md.
# Mifflin-St Jeor resting energy in kcal/day: 10 x kg + 6.25 x cm - 5 x years, plus 5 for men or
# minus 161 for women [22].
MSJ_KCAL_PER_KG = 10.0
MSJ_KCAL_PER_CM = 6.25
MSJ_KCAL_PER_YEAR = 5.0
MSJ_SEX_CONSTANT_KCAL: dict[str, float] = {"male": 5.0, "female": -161.0}
# Physical activity level that multiplies the resting energy, by how often the user exercises:
# under once a week, 1-3, 4-5, 6-7, and more than 7 times a week with extra heavy workouts [23].
# Keys are src.profile.ActivityLevel.
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "very_active": 1.725,
    "extra_active": 1.9,
}

# calculate_macro_targets; no target is below CALORIE_FLOOR_KCAL (src/config/limits.py).
# Lose fat: a weekly weight loss of 0.5-1.0% of body weight [1], [12]; the target uses the lower,
# slower end, as slower loss better keeps lean mass [9].
FAT_LOSS_PCT_PER_WEEK_RANGE = (0.5, 1.0)
FAT_LOSS_PCT_PER_WEEK = 0.5
# Energy in a pound of pure body fat: approximately 3500 kcal [12]. [12] adds that a deficit gives
# the matching loss only in theory, if all the weight lost is fat, so it is a rough estimate.
KCAL_PER_LB_BODY_FAT = 3500
# Build muscle: about 10-20% above maintenance [11]; the target uses 10%, the lower end, which [11]
# advises advanced lifters to aim for, to limit fat gain.
MUSCLE_GAIN_SURPLUS_PCT_RANGE = (10.0, 20.0)
MUSCLE_GAIN_SURPLUS_PCT = 10.0
# Protein in g per kg of body weight per day: 1.6-2.2 [1], [11]. The top for fat loss, as [1] finds
# that 1.6-2.2 g/kg, or more in lean, resistance-trained people, can best keep lean mass in a
# lasting energy deficit; the middle for the other goals.
PROTEIN_G_PER_KG_RANGE = (1.6, 2.2)
PROTEIN_G_PER_KG: dict[str, float] = {"lose_fat": 2.2, "build_muscle": 1.9, "maintain": 1.9}
# Fat as a share of the kcal target: inside both 20-35% [11] and 15-30% for contest dieting [12],
# i.e. their overlap below.
FAT_PCT_OF_KCAL_RANGE = (20.0, 30.0)
FAT_PCT_OF_KCAL = 25.0
# Carbohydrate gets the kcal left after protein and fat [11]. Energy per gram uses the general
# Atwater factors, the same ones USDA uses for its general-factor energy (docs/ARCHITECTURE.md
# section 6): 4 kcal per g of protein and carbohydrate, 9 per g of fat.
KCAL_PER_G_PROTEIN = 4
KCAL_PER_G_CARBOHYDRATE = 4
KCAL_PER_G_FAT = 9
# The TDEE calculate_macro_targets accepts, in kcal/day. Covers every profile within the ranges
# above (about 467 to 8270 kcal/day; tests/test_energy.py checks it), with room either side.
MACRO_TDEE_KCAL_RANGE = (400, 9000)

# USDA FoodData Central, Foundation Foods (docs/SOURCES.md #21; docs/ARCHITECTURE.md section 6),
# read from USDA_FOODS_PATH. The largest CSV in the 2026-04-30 zip is about 10 MB unpacked; anything
# far bigger is refused.
USDA_MAX_MEMBER_BYTES = 100_000_000
# The credit for the table, used in its "#" lines and in ATTRIBUTION.md. The citation follows the
# format USDA suggests on https://fdc.nal.usda.gov/; {release} is the release date (YYYY-MM-DD).
USDA_CITATION = (
    "U.S. Department of Agriculture, Agricultural Research Service, Beltsville Human Nutrition "
    "Research Center. FoodData Central: Foundation Foods, release {release}. "
    "https://fdc.nal.usda.gov/"
)
USDA_LICENSE = "CC0 1.0 Universal (public domain)"
USDA_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
USDA_CHANGES = (
    "Foundation foods only; values per 100 g: energy (kcal; Atwater specific factors where "
    "reported, else general factors), protein, carbohydrate (by difference), total fat and total "
    "dietary fiber. Foods without energy or a macronutrient are left out; a repeated name is kept "
    "once (latest publication); negative values are set to 0; an empty fiber value means not "
    "reported."
)
# The line under a food lookup's values, in the app and the summary PDF.
USDA_SOURCE_LINE = (
    "Source: USDA FoodData Central, Foundation Foods (CC0). Values per 100 g, scaled."
)
# The line under a meal plan check (T4.5), in the app and the summary PDF.
MEAL_PLAN_SOURCE_LINE = USDA_SOURCE_LINE + " Targets: the daily targets from your details."

# lookup_food_nutrition: argument limits and fuzzy name matching (rapidfuzz scores, 0-100).
# A one-letter name matches by chance ("a" scores 100 on "Eggs, Grade A, ..."), so the name, and
# its longest word once punctuation is dropped, must have at least this many characters.
FOOD_MIN_NAME_CHARS = 2
FOOD_MAX_NAME_CHARS = 100
# Grams per lookup; below 0.1 g every value rounds to zero.
FOOD_MIN_GRAMS = 0.1
FOOD_MAX_GRAMS = 2000
# A food scoring at least this is taken as the match; tried on the real table in T4.3.
FOOD_MATCH_MIN_SCORE = 80
# Foods scoring at least this are offered as alternatives or "did you mean" suggestions.
FOOD_SUGGESTION_MIN_SCORE = 60
FOOD_MAX_ALTERNATIVES = 3
# Decimal places of the scaled values (grams of nutrients); kcal are rounded to whole numbers.
FOOD_DECIMALS = 1

# The USDA FoodData Central API (T9.9; docs/SOURCES.md #21; copyright policy rule 10): the chat's
# food tool asks it only when the Foundation Foods table has no close match, and only when the
# owner's api.data.gov key is set. One search per lookup, with only the food name and the fixed
# fields below in the request body; the key goes in a header, never in the URL; redirects are
# refused, so the key never reaches another host.
FOOD_API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
# The data types USDA makes itself, which its pages say are public domain (CC0 1.0). Branded and
# Experimental foods are left out: USDA's pages do not confirm CC0 for them (copyright policy rule
# 2; checked 2026-11-06).
FOOD_API_DATA_TYPES = ("Foundation", "SR Legacy", "Survey (FNDDS)")
# Foods asked for per search; enough for the fuzzy match to find the plain food among variants.
FOOD_API_PAGE_SIZE = 25
# Each attempt's timeout; a timeout, a connection error or a 5xx answer is tried once more.
FOOD_API_TIMEOUT_SECONDS = 5
FOOD_API_MAX_ATTEMPTS = 2
FOOD_API_RETRY_PAUSE_SECONDS = 0.5
# A 25-food answer is far below this; anything bigger is not a search result.
FOOD_API_MAX_BYTES = 5_000_000
# API searches in one chat turn; the rest use the local table only. Bounds the time a turn waits and
# the key's hourly quota (1,000 requests an hour on api.data.gov).
FOOD_API_MAX_CALLS_PER_TURN = 6
# A food name sent to the API: plain English words (ASCII letters, digits, spaces and , ' % ( ) / -,
# a "." only between digits), at most this many words and digits in all ("85% lean ground beef"
# and "1.5% milk" pass; a phone or card number, spaced or not, does not).
FOOD_API_MAX_WORDS = 10
FOOD_API_MAX_DIGITS = 4
# Longer USDA names from the API are left out (the longest Foundation Foods name is 129 characters).
FOOD_API_MAX_DESCRIPTION_CHARS = 200
# Per-100 g values above these are not a food's and are left out.
FOOD_API_MAX_KCAL = 1000
FOOD_API_MAX_GRAMS_PER_100G = 100.5
# What a food found through the API names as its source, in the tool result the model reads.
FOOD_API_SOURCE = "USDA FoodData Central API, {data_type} (CC0 1.0), https://fdc.nal.usda.gov/"
# What a "not found" names as its source once both the table and the API were searched.
FOOD_API_NO_MATCH_SOURCE = (
    "USDA FoodData Central, Foundation Foods and the FoodData Central API (CC0 1.0), "
    "https://fdc.nal.usda.gov/"
)
# The line under a food lookup's values when they came from the API, in the app and the summary PDF.
FOOD_API_SOURCE_LINE = (
    "Source: USDA FoodData Central API, {data_type} (CC0). Values per 100 g, scaled."
)
# The credit for the API's data, as USDA's API guide suggests it (read 2026-11-06), in
# ATTRIBUTION.md and the summary PDF.
FOOD_API_CITATION = (
    "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, 2019. "
    "fdc.nal.usda.gov."
)
FOOD_API_CHANGES = (
    "Foundation, SR Legacy and Survey (FNDDS) foods, searched by name at the time of a lookup and "
    "not stored; values per 100 g: energy (kcal; Atwater specific factors where reported, else "
    "general factors, else the reported energy), protein, carbohydrate (by difference), total fat "
    "and total dietary fiber, scaled to the amount asked for; negative values are set to 0."
)
