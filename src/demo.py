"""Demo mode's synthetic users and the records they start with (T9.5, D18).

A fixture we wrote ourselves: made-up names and numbers, no real person's data. Demo mode seeds them
into a temporary database when the app starts (only with DEMO_MODE on and no [auth] section), so a
reviewer can try the coach and gymer pages without a Google client. Later tickets add their own
records here (workouts, an invitation); T9.13 added Sam's meals.
"""

import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from src import account, diary
from src.profile import UserProfile
from src.store import records, users


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
# Today page and the week's metrics have something to show; today and two earlier days.
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
    for user_id, profile in PROFILES.items():
        account.save_profile(conn, user_id, profile, with_weight=True)
    for days_back, meal, food_name, grams in MEALS:
        diary.log_food(
            conn,
            SHARING_GYMER.id,
            food_name=food_name,
            grams=grams,
            meal=meal,
            day=account.today() - timedelta(days=days_back),
        )
