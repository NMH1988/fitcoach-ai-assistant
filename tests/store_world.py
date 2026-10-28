"""A small made-up world for the store tests: two coaches, four gymers, each with some records."""

from datetime import date

from src.store import records, users

COACH_A = "coach-a"
COACH_B = "coach-b"
SHARED = "gym-shared"  # coach A's client, every scope on
UNSHARED = "gym-unshared"  # coach A's client, no scope on
ENDED = "gym-ended"  # was coach A's client with every scope on; the relationship ended
OTHERS = "gym-others"  # coach B's client, every scope on
MISSING = "no-such-user"
GYMERS = (SHARED, UNSHARED, ENDED, OTHERS)
DAY = date(2026, 10, 26)
# Recognisable numbers, so a test can look for them where they must not be (an audit row, a log).
WEIGHT = 87.3
HEIGHT = 181.7


def add_records(conn, user_id):
    """Give a gymer one record of every kind."""
    records.add_profile_entry(
        conn, user_id, height_cm=HEIGHT, age=37, sex="male", activity="moderate", goal="lose_fat"
    )
    records.add_body_measurement(conn, user_id, weight_kg=WEIGHT, measured_on=DAY)
    records.add_target(
        conn,
        user_id,
        kcal=2345.0,
        protein_g=160.0,
        carbs_g=250.0,
        fat_g=70.0,
        set_by="system",
        effective_from=DAY,
        calc_version="t9.5",
    )
    records.add_meal_item(
        conn,
        user_id,
        consumed_on=DAY,
        meal="breakfast",
        fdc_id=123,
        food_name="Oats, rolled",
        grams=150.0,
        kcal=571.5,
        protein_g=19.95,
        carbohydrate_g=101.4,
        fat_g=9.75,
        fiber_g=15.0,
    )
    records.add_workout_session(
        conn,
        user_id,
        performed_on=DAY,
        sets=[
            records.ExerciseSet("squat", 1, 5, 100.0, 8.0),
            records.ExerciseSet("squat", 2, 5, 100.0),
        ],
    )
    records.add_preference(conn, user_id, "vegetarian")


def build(conn):
    """Create the users, relationships, scopes and records; return the relationship IDs by gymer."""
    users.create_user(conn, COACH_A, "coach", "Coach A")
    users.create_user(conn, COACH_B, "coach", "Coach B")
    for gymer in GYMERS:
        users.create_user(conn, gymer, "gymer", gymer)
        add_records(conn, gymer)
    relationships = {
        SHARED: users.start_relationship(conn, COACH_A, SHARED),
        UNSHARED: users.start_relationship(conn, COACH_A, UNSHARED),
        ENDED: users.start_relationship(conn, COACH_A, ENDED),
        OTHERS: users.start_relationship(conn, COACH_B, OTHERS),
    }
    for gymer in (SHARED, ENDED, OTHERS):
        for scope in ("nutrition", "training", "body"):
            users.set_consent(conn, gymer, relationships[gymer], scope, True)
    users.end_relationship(conn, ENDED, relationships[ENDED])
    return relationships
