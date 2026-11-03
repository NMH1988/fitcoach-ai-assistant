"""Demo mode's synthetic users and the records they start with (T9.5, D18).

A fixture we wrote ourselves: made-up names and numbers, no real person's data. Demo mode seeds them
into a temporary database when the app starts (only with DEMO_MODE on and no [auth] section), so a
reviewer can try the coach and gymer pages without a Google client. Later tickets add their own
records here (meals, an invitation); Sam's workouts come from T9.14.
"""

import sqlite3
from dataclasses import dataclass
from datetime import timedelta

from src import account
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
# Sam's made-up workouts (T9.14), by how many days before today they were done, each a list of
# (exercise, reps, kg, RPE). Sam does not share training, so the coach cannot read them.
WORKOUTS = (
    (2, (("squat", 5, 100.0, 8.0), ("squat", 5, 100.0, 8.5), ("bench_press", 8, 70.0, None))),
    (0, (("deadlift", 5, 140.0, 8.0), ("pull_up", 8, 0.0, None), ("pull_up", 6, 0.0, 9.0))),
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
    for days_back, sets in WORKOUTS:
        records.add_workout_session(
            conn,
            SHARING_GYMER.id,
            performed_on=account.today() - timedelta(days=days_back),
            sets=[
                records.ExerciseSet(exercise_id, number, reps, kg, rpe)
                for number, (exercise_id, reps, kg, rpe) in enumerate(sets, start=1)
            ],
        )
