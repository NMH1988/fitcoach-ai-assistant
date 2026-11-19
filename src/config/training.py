"""The workout log: muscle groups, the ranges a set keeps, the words a training view may not use."""

# The workout log (T9.14): the exercise list we wrote (EXERCISES_PATH, each exercise in one of the
# muscle groups below) and the ranges a set must keep, in kg (0 kg: a body-weight set with no added
# load; volume is reps x kg, so such a set adds no volume). The store checks them all.
MUSCLE_GROUPS: tuple[str, ...] = ("chest", "back", "legs", "shoulders", "arms", "core")
EXERCISE_NAME_MAX_CHARS = 40
WORKOUT_REPS_RANGE = (1, 100)
WORKOUT_WEIGHT_KG_RANGE = (0.0, 500.0)
WORKOUT_RPE_RANGE = (1.0, 10.0)
WORKOUT_RPE_STEP = 0.5
WORKOUT_MAX_SETS = 40
# The Workouts page's set fields: the reps shown at first, and the weight field's step per unit.
WORKOUT_DEFAULT_REPS = 8
WORKOUT_WEIGHT_STEP: dict[str, float] = {"metric": 2.5, "imperial": 5.0}
# Words that would make a training view give advice; the workout texts (`workouts.`, `muscle.` in
# src/i18n/dashboards.py and the exercise names) must hold none, as the views report facts only
# (T9.14).
# Whole words or phrases, any case; an entry ending in "*" matches any word that starts with it.
TRAINING_ADVICE_WORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "should", "must", "recommend*", "advis*", "advic*", "try to", "aim for", "increase*",
        "decrease*", "reduce*", "too much", "too little", "too heavy", "too light", "better",
        "optimal", "you need", "need to",
    ),
    "de": (
        "soll*", "muss*", "müss*", "empfehl*", "empfiehl*", "empfohlen", "rat*", "rät*", "versuch*",
        "erhöh*", "steiger*", "verringer*", "reduzier*", "zu viel", "zu wenig", "zu schwer",
        "zu leicht", "besser", "optimal", "brauch*",
    ),
}  # fmt: skip
