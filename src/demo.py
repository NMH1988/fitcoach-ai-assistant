"""Demo mode's synthetic users and the records they start with (T9.5, D18).

A fixture we wrote ourselves: made-up names and numbers, no real person's data. Demo mode seeds them
into a temporary database when the app starts (only with DEMO_MODE on and no [auth] section), so a
reviewer can try the coach and gymer pages without a Google client. Later tickets add their own
records here (an invitation); T9.13 added Sam's meals, T9.14 Sam's workouts, and T9.27 a full
week before this one, so a coach can draft a weekly review of a finished week on any day.
"""

import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from src import account, config, diary
from src.profile import UserProfile
from src.store import records, users
from src.tools import registry


@dataclass(frozen=True)
class DemoUser:
    """A synthetic user: a fixed ID, the role and the display name shown in the picker."""

    id: str
    role: users.Role
    display_name: str


COACH = DemoUser("demo-coach", "coach", "Demo coach Alex")
SHARING_GYMER = DemoUser("demo-gymer-sam", "gymer", "Demo gymer Sam")
OTHER_GYMER = DemoUser("demo-gymer-kim", "gymer", "Demo gymer Kim")
DEMO_USERS = (COACH, SHARING_GYMER, OTHER_GYMER)
USER_IDS = frozenset(user.id for user in DEMO_USERS)

# Made-up profiles. Sam is the coach's client and shares body and nutrition; Kim has no coach.
PROFILES = {
    SHARING_GYMER.id: UserProfile(
        weight_kg=78.4, height_cm=176, age=29, sex="male", activity="moderate", goal="build_muscle"
    ),
    OTHER_GYMER.id: UserProfile(
        weight_kg=64.0, height_cm=168, age=34, sex="female", activity="light", goal="lose_fat"
    ),
}
# Sam's weight a week before the profile's, so the history has more than one entry.
EARLIER_WEIGHT_KG = 77.9
SHARED_SCOPES = ("body", "nutrition")
# Sam's made-up food diary (T9.13): (days before today, meal, a USDA table name, grams), so the
# Today page and the week's metrics have something to show; today and two earlier days, only those
# within this week (T9.27).
MEALS = (
    (0, "breakfast", "Oats, whole grain, rolled, old fashioned", 80.0),
    (0, "breakfast", "Milk, whole, 3.25% milkfat, with added vitamin D", 250.0),
    (0, "lunch", "Chicken, breast, boneless, skinless, raw", 180.0),
    (0, "lunch", "Rice, white, long grain, unenriched, raw", 90.0),
    (1, "breakfast", "Yogurt, Greek, plain, nonfat", 200.0),
    (1, "snack", "Bananas, ripe and slightly ripe, raw", 120.0),
    (1, "dinner", "Eggs, Grade A, Large, egg whole", 150.0),
    (2, "lunch", "Chicken, breast, boneless, skinless, raw", 200.0),
)
# Sam's made-up workouts (T9.14), by how many days before today they were done, each a list of
# (exercise, reps, kg, RPE). Sam does not share training, so the coach cannot read them.
WORKOUTS = (
    (2, (("squat", 5, 100.0, 8.0), ("squat", 5, 100.0, 8.5), ("bench_press", 8, 70.0, None))),
    (0, (("deadlift", 5, 140.0, 8.0), ("pull_up", 8, 0.0, None), ("pull_up", 6, 0.0, 9.0))),
)
# The whole week before this one (T9.27), so the coach can draft a weekly review of a finished week
# on any day and the README images show a full week: two made-up day plans of (meal, USDA table
# name, grams), about 2,500 kcal each, a little under Sam's target, alternated over six of the
# seven days (Thursday has no log, as a real week often has a gap).
DAY_PLANS = (
    (
        ("breakfast", "Oats, whole grain, rolled, old fashioned", 110.0),
        ("breakfast", "Milk, whole, 3.25% milkfat, with added vitamin D", 300.0),
        ("breakfast", "Bananas, ripe and slightly ripe, raw", 120.0),
        ("lunch", "Chicken, breast, boneless, skinless, raw", 200.0),
        ("lunch", "Rice, white, long grain, unenriched, raw", 140.0),
        ("lunch", "Broccoli, raw", 150.0),
        ("snack", "Yogurt, Greek, plain, nonfat", 250.0),
        ("snack", "Peanut butter, creamy", 40.0),
        ("dinner", "Fish, salmon, Atlantic, farm raised, raw", 180.0),
        ("dinner", "Potatoes, russet, without skin, raw", 400.0),
    ),
    (
        ("breakfast", "Eggs, Grade A, Large, egg whole", 150.0),
        ("breakfast", "Bread, whole-wheat, commercially prepared", 100.0),
        ("breakfast", "Apples, gala, with skin, raw", 180.0),
        ("lunch", "Turkey, ground, 93% lean/ 7% fat, raw", 200.0),
        ("lunch", "Rice, white, long grain, unenriched, raw", 130.0),
        ("snack", "Yogurt, Greek, plain, nonfat", 200.0),
        ("snack", "Oats, whole grain, rolled, old fashioned", 60.0),
        ("dinner", "Beef, ground, 90% lean meat / 10% fat, raw", 180.0),
        ("dinner", "Sweet potatoes, orange flesh, without skin, raw", 350.0),
        ("dinner", "Cheese, cheddar", 40.0),
    ),
)
# Last week's logged days (0 is Monday) and Sam's workouts on three of them.
LAST_WEEK_DAYS = (0, 1, 2, 4, 5, 6)
LAST_WEEK_WORKOUTS = (
    (0, (("squat", 5, 97.5, 8.0), ("squat", 5, 97.5, 8.0), ("bench_press", 8, 67.5, 8.0))),
    (2, (("deadlift", 5, 137.5, 8.0), ("pull_up", 8, 0.0, 8.5), ("pull_up", 7, 0.0, 9.0))),
    (5, (("squat", 5, 100.0, 8.5), ("bench_press", 8, 70.0, 8.5), ("bench_press", 7, 70.0, 9.0))),
)


def seed(conn: sqlite3.Connection) -> None:
    """Write the demo users, Sam's relationship with the coach and each gymer's records."""
    for user in DEMO_USERS:
        users.create_user(conn, user.id, user.role, user.display_name)
    relationship = users.start_relationship(conn, COACH.id, SHARING_GYMER.id)
    for scope in SHARED_SCOPES:
        users.set_consent(conn, SHARING_GYMER.id, relationship, scope, True)
    records.add_body_measurement(
        conn,
        SHARING_GYMER.id,
        weight_kg=EARLIER_WEIGHT_KG,
        measured_on=account.today() - timedelta(days=7),
    )
    today = account.today()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    # Sam's daily target from two weeks back (T9.27), so the finished week the coach reviews has a
    # target to compare with; the profile saved below adds today's, with the same values.
    sam_targets = registry.macro_targets(PROFILES[SHARING_GYMER.id]).targets
    records.add_target(
        conn,
        SHARING_GYMER.id,
        kcal=sam_targets.kcal_target,
        protein_g=sam_targets.protein.grams,
        carbs_g=sam_targets.carbohydrate.grams,
        fat_g=sam_targets.fat.grams,
        set_by="system",
        effective_from=last_monday - timedelta(days=7),
        calc_version=config.TARGET_CALC_VERSION,
    )
    for user_id, profile in PROFILES.items():
        account.save_profile(conn, user_id, profile, with_weight=True)
    # The recent records only within this week (T9.27): on a Monday or Tuesday their earlier days
    # would fall in last week, which the day plans below fill, and leave it uneven.
    meals = [
        (day, meal, food, grams)
        for days_back, meal, food, grams in MEALS
        if (day := today - timedelta(days=days_back)) >= this_monday
    ]
    workouts = [
        (day, sets)
        for days_back, sets in WORKOUTS
        if (day := today - timedelta(days=days_back)) >= this_monday
    ]
    for index, weekday in enumerate(LAST_WEEK_DAYS):
        plan = DAY_PLANS[index % len(DAY_PLANS)]
        day = last_monday + timedelta(days=weekday)
        meals += [(day, meal, food, grams) for meal, food, grams in plan]
    workouts += [
        (last_monday + timedelta(days=weekday), sets) for weekday, sets in LAST_WEEK_WORKOUTS
    ]
    for day, meal, food_name, grams in meals:
        diary.log_food(conn, SHARING_GYMER.id, food_name=food_name, grams=grams, meal=meal, day=day)
    for day, sets in workouts:
        records.add_workout_session(
            conn,
            SHARING_GYMER.id,
            performed_on=day,
            sets=[
                records.ExerciseSet(exercise_id, number, reps, kg, rpe)
                for number, (exercise_id, reps, kg, rpe) in enumerate(sets, start=1)
            ],
        )
