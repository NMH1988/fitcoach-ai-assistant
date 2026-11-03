"""UI tests for a gymer's Workouts page (T9.14, AC-24): log, edit, delete and the week's facts."""

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import account, units
from src.store import db, my_data, records
from tests.test_app_account import (
    PROFILE,
    USER_ID,
    button,
    signed_in,
    start,
    store_account,
    texts,
)
from views import account as views_account
from views import navigation, workouts

pytestmark = pytest.mark.usefixtures("no_env_key")


def open_workouts(at: AppTest) -> AppTest:
    """Open the Workouts page by its URL path."""
    at._page_hash = calc_hash(navigation.WORKOUTS)
    return at.run(timeout=30)


def _stored() -> list[dict]:
    """Return the canary gymer's stored workouts."""
    with db.connect() as conn:
        return records.list_workout_sessions(conn, USER_ID, USER_ID)


def _add_set(at: AppTest, exercise: str, reps: int, weight: float, rpe: float | None) -> None:
    """Type one set into the fields and press Add set."""
    at.selectbox(key="workout_exercise").set_value(exercise)
    at.number_input(key="workout_reps").set_value(reps)
    at.number_input(key="workout_weight").set_value(weight)
    at.number_input(key="workout_rpe").set_value(rpe)
    button(at, "Add set").click().run(timeout=30)


@pytest.fixture
def gymer(monkeypatch) -> AppTest:
    """Store the canary gymer and open their Workouts page."""
    store_account("gymer", profile=PROFILE)
    return open_workouts(start(monkeypatch, user=signed_in()))


def _stored_workout(*sets: records.ExerciseSet, day: date | None = None) -> int:
    """Store a workout for the canary gymer (today by default); return its ID."""
    with db.connect() as conn:
        return records.add_workout_session(
            conn, USER_ID, performed_on=day or account.today(), sets=list(sets)
        )


def test_a_gymer_s_menu_has_workouts_and_the_page_opens(gymer):
    """Workouts is one of a gymer's pages (not the home), with its note on what is stored."""
    assert navigation.PAGES_BY_ROLE["gymer"] == (
        navigation.PROFILE,
        navigation.WORKOUTS,
        navigation.MY_DATA,
    )
    page = texts(gymer)
    assert "Workouts" in page
    assert "your workouts are stored in this app's data file" in page
    assert "No sets yet" in page
    assert "No workout logged in this week." in page


def test_save_is_off_until_a_set_is_added(gymer):
    """With no set in the draft, Save and Remove are disabled."""
    assert button(gymer, "Save workout").disabled
    assert button(gymer, "Remove the last set").disabled


def test_a_logged_workout_is_stored_and_shown_with_its_volume(gymer):
    """Two sets saved: the store holds them, and the page shows 2 sets and 1,000 kg (AC-24)."""
    _add_set(gymer, "squat", 5, 100.0, 8.0)
    _add_set(gymer, "squat", 5, 100.0, None)
    assert len(gymer.dataframe) == 1  # the draft's sets
    button(gymer, "Save workout").click().run(timeout=30)
    [session] = _stored()
    assert session["performed_on"] == account.today().isoformat()
    assert session["sets"] == [
        {"exercise_id": "squat", "set_no": 1, "reps": 5, "weight_kg": 100.0, "rpe": 8.0},
        {"exercise_id": "squat", "set_no": 2, "reps": 5, "weight_kg": 100.0, "rpe": None},
    ]
    page = texts(gymer)
    assert "Workout saved." in [item.value for item in gymer.success]
    assert "Sessions: 1 · Sets: 2 · Volume: 1,000 kg" in page
    assert f"**{account.today().isoformat()}** · Sets: 2 · Volume: 1,000 kg" in page
    week = gymer.dataframe[0].value
    assert list(week["Exercise"]) == ["Squat · Legs"]
    assert list(week["Volume"]) == ["1,000 kg"]
    assert list(week["Top weight"]) == ["100 kg"]
    assert "No sets yet" in page  # the draft is empty again


def test_a_body_weight_set_adds_no_volume(gymer):
    """Pull-ups at 0 kg are kept with their reps and count 0 kg of volume."""
    _add_set(gymer, "pull_up", 10, 0.0, None)
    button(gymer, "Save workout").click().run(timeout=30)
    assert _stored()[0]["sets"][0]["weight_kg"] == 0.0
    assert "Sets: 1 · Volume: 0 kg" in texts(gymer)


def test_weights_typed_in_pounds_are_stored_in_kg(monkeypatch):
    """With imperial units, 225 lb is stored as its kg value and shown again as 225 lb."""
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in())
    at.session_state["units"] = "imperial"
    at = open_workouts(at)
    assert at.number_input(key="workout_weight").label == "Weight (lb)"
    _add_set(at, "bench_press", 5, 225.0, None)
    button(at, "Save workout").click().run(timeout=30)
    assert _stored()[0]["sets"][0]["weight_kg"] == pytest.approx(units.lb_to_kg(225.0))
    assert "Volume: 1,125 lb" in texts(at)


def test_remove_the_last_set_drops_it_from_the_draft(gymer):
    """Remove the last set takes the latest set off the draft, before anything is saved."""
    _add_set(gymer, "squat", 5, 100.0, None)
    _add_set(gymer, "deadlift", 3, 140.0, None)
    button(gymer, "Remove the last set").click().run(timeout=30)
    assert list(gymer.dataframe[0].value["Exercise"]) == ["Squat · Legs"]
    assert _stored() == []


def test_editing_a_workout_replaces_it(gymer):
    """Edit loads a workout's sets; Save changes stores the edited one in its place."""
    _stored_workout(
        records.ExerciseSet("squat", 1, 5, 100.0), records.ExerciseSet("squat", 2, 5, 100.0)
    )
    gymer.run(timeout=30)
    button(gymer, "Edit").click().run(timeout=30)
    assert any("Edit the workout of" in item.value for item in gymer.subheader)
    button(gymer, "Remove the last set").click().run(timeout=30)
    _add_set(gymer, "squat", 3, 110.0, 9.0)
    button(gymer, "Save changes").click().run(timeout=30)
    [session] = _stored()  # the old workout is gone: only the edited one is stored
    assert [(s["reps"], s["weight_kg"], s["rpe"]) for s in session["sets"]] == [
        (5, 100.0, None),
        (3, 110.0, 9.0),
    ]
    assert "Sets: 2 · Volume: 830 kg" in texts(gymer)
    assert not [item for item in gymer.button if item.label == "Cancel editing"]


def test_cancel_editing_keeps_the_stored_workout(gymer):
    """Cancel editing empties the draft and leaves the stored workout as it was."""
    _stored_workout(records.ExerciseSet("squat", 1, 5, 100.0))
    gymer.run(timeout=30)
    before = _stored()
    button(gymer, "Edit").click().run(timeout=30)
    button(gymer, "Cancel editing").click().run(timeout=30)
    assert _stored() == before
    assert "No sets yet" in texts(gymer)


def test_deleting_a_workout_removes_it_and_its_sets(gymer):
    """Delete removes the workout from the store and from the week."""
    _stored_workout(records.ExerciseSet("squat", 1, 5, 100.0))
    gymer.run(timeout=30)
    button(gymer, "Delete").click().run(timeout=30)
    assert _stored() == []
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM exercise_sets").fetchone()[0] == 0
    assert "No workout logged in this week." in texts(gymer)


def test_the_week_picker_shows_only_that_week(gymer):
    """A workout is counted in its own week only: the week before shows none, its week shows it."""
    _stored_workout(records.ExerciseSet("squat", 1, 5, 100.0), day=date(2026, 10, 27))
    gymer.date_input(key="workout_week").set_value(date(2026, 10, 25)).run(timeout=30)
    page = texts(gymer)
    assert "2026-10-19 to 2026-10-25 · Sessions: 0 · Sets: 0 · Volume: 0 kg" in page
    assert "No workout logged in this week." in page
    gymer.date_input(key="workout_week").set_value(date(2026, 10, 30)).run(timeout=30)
    page = texts(gymer)
    assert "2026-10-26 to 2026-11-01 · Sessions: 1 · Sets: 1 · Volume: 500 kg" in page


def test_the_page_in_german(monkeypatch):
    """The page speaks German, with German numbers and exercise names."""
    store_account("gymer", profile=PROFILE)
    _stored_workout(records.ExerciseSet("squat", 1, 5, 102.5))
    at = open_workouts(start(monkeypatch, user=signed_in(), language="de"))
    page = texts(at)
    assert "Trainingseinheit erfassen" in page
    assert "Einheiten: 1 · Sätze: 1 · Volumen: 512 kg" in page
    assert list(at.dataframe[0].value["Übung"]) == ["Kniebeuge · Beine"]
    assert list(at.dataframe[0].value["Höchstes Gewicht"]) == ["102,5 kg"]


def test_a_store_error_on_save_shows_one_fixed_message_and_keeps_the_draft(gymer, monkeypatch):
    """A store that fails while saving shows the store's fixed message; the sets stay drafted."""

    def failing(*args, **kwargs):
        """Fail as SQLite does on a locked file."""
        raise sqlite3.OperationalError("C:/private/file is locked")

    _add_set(gymer, "squat", 5, 100.0, None)
    monkeypatch.setattr(records, "add_workout_session", failing)
    button(gymer, "Save workout").click().run(timeout=30)
    page = texts(gymer)
    assert "cannot be opened right now" in page
    assert "private" not in page
    assert len(gymer.dataframe) == 1  # the draft is kept


def test_a_coach_has_no_workouts_page(monkeypatch):
    """A coach keeps no records, so the Workouts URL shows the coach's home, the chat."""
    store_account("coach")
    at = open_workouts(start(monkeypatch, user=signed_in()))
    assert "Log a workout" not in texts(at)
    assert len(at.tabs) == 4


def test_an_edit_keeps_its_day_when_the_user_opens_another_page_and_comes_back(gymer):
    """The day of a workout being edited survives a visit to My data (code review round 1)."""
    _stored_workout(records.ExerciseSet("squat", 1, 5, 100.0), day=date(2026, 10, 27))
    gymer.date_input(key="workout_week").set_value(date(2026, 10, 27)).run(timeout=30)
    button(gymer, "Edit").click().run(timeout=30)
    gymer._page_hash = calc_hash(navigation.MY_DATA)
    gymer.run(timeout=30)
    open_workouts(gymer)
    assert any("Edit the workout of 2026-10-27" in item.value for item in gymer.subheader)
    button(gymer, "Save changes").click().run(timeout=30)
    assert [session["performed_on"] for session in _stored()] == ["2026-10-27"]


def test_an_rpe_off_the_scale_s_steps_is_put_on_the_nearest_step(gymer):
    """A typed RPE of 7.3 is drafted and saved as 7.5, so Save never fails on it (round 1)."""
    _add_set(gymer, "squat", 5, 100.0, 7.3)
    assert list(gymer.dataframe[0].value["RPE"]) == ["7.5"]
    button(gymer, "Save workout").click().run(timeout=30)
    assert _stored()[0]["sets"][0]["rpe"] == 7.5


def test_the_day_field_takes_no_day_after_today(gymer):
    """The day field's latest day is today, so the page offers no future day."""
    field = gymer.date_input(key="workout_day")
    assert field.max == account.today()
    assert field.value == account.today()


def test_a_past_day_picked_in_the_field_is_saved(gymer):
    """A day picked in the field is the day the workout is stored on (round 2)."""
    past = account.today() - timedelta(days=3)
    gymer.date_input(key="workout_day").set_value(past).run(timeout=30)
    _add_set(gymer, "squat", 5, 100.0, None)
    assert gymer.date_input(key="workout_day").value == past  # kept while sets are added
    button(gymer, "Save workout").click().run(timeout=30)
    assert [session["performed_on"] for session in _stored()] == [past.isoformat()]


def test_an_edit_can_move_a_workout_to_another_day(gymer):
    """Changing the day while editing stores the workout on the new day (round 2)."""
    old_day = account.today() - timedelta(days=2)
    new_day = account.today() - timedelta(days=1)
    _stored_workout(records.ExerciseSet("squat", 1, 5, 100.0), day=old_day)
    gymer.date_input(key="workout_week").set_value(old_day).run(timeout=30)
    button(gymer, "Edit").click().run(timeout=30)
    gymer.date_input(key="workout_day").set_value(new_day).run(timeout=30)
    assert any(f"Edit the workout of {new_day}" in item.value for item in gymer.subheader)
    button(gymer, "Save changes").click().run(timeout=30)
    assert [session["performed_on"] for session in _stored()] == [new_day.isoformat()]


def test_edit_waits_until_the_draft_is_saved_or_discarded(gymer):
    """With unsaved sets, Edit is off, so the draft is never replaced; Discard clears it."""
    _stored_workout(records.ExerciseSet("squat", 1, 5, 100.0))
    gymer.run(timeout=30)
    _add_set(gymer, "deadlift", 3, 140.0, None)
    assert button(gymer, "Edit").disabled
    button(gymer, "Discard the draft").click().run(timeout=30)
    assert not button(gymer, "Edit").disabled
    assert "No sets yet" in texts(gymer)
    assert len(_stored()) == 1


def test_an_emptied_day_field_keeps_the_last_day(gymer):
    """A day field cleared in the browser keeps the day picked before, never an empty one."""
    past = account.today() - timedelta(days=1)
    gymer.date_input(key="workout_day").set_value(past).run(timeout=30)
    gymer.date_input(key="workout_day").set_value(None).run(timeout=30)
    _add_set(gymer, "squat", 5, 100.0, None)
    button(gymer, "Save workout").click().run(timeout=30)
    assert [session["performed_on"] for session in _stored()] == [past.isoformat()]


def test_a_gymer_with_no_saved_profile_cannot_save_a_workout(monkeypatch):
    """Without a saved profile (no first-save tick yet), Save is off and nothing is stored."""
    store_account("gymer")  # an account, no profile entry
    at = open_workouts(start(monkeypatch, user=signed_in()))
    assert "save them in My profile first" in " ".join(item.value for item in at.info)
    assert _link_hash(at, "Go to My profile") == calc_hash(navigation.PROFILE)
    _add_set(at, "squat", 5, 100.0, None)
    assert button(at, "Save workout").disabled
    assert _stored() == []


def test_a_profile_deleted_in_another_tab_stops_the_save(gymer):
    """Save checks the saved profile again at the write, so nothing is stored without it."""
    _add_set(gymer, "squat", 5, 100.0, None)
    with db.connect() as conn:
        for entry in records.list_profile_entries(conn, USER_ID, USER_ID):
            records.delete_record(conn, USER_ID, "profile_entries", entry["id"])
    button(gymer, "Save workout").click().run(timeout=30)
    assert _stored() == []
    # Said once, by the note on saving the profile first, not again as an error (round 4).
    assert any("save them in My profile first" in item.value for item in gymer.info)
    assert not gymer.error


def test_the_stored_note_links_to_my_data(gymer):
    """Under the note on what is stored, a link leads to My data (compliance run 1)."""
    link = "See, export or delete them in My data"
    assert _link_hash(gymer, link) == calc_hash(navigation.MY_DATA)


def _link_hash(at: AppTest, label: str) -> str:
    """Return the page hash of the one page link with this label (where a click goes)."""
    (link,) = [item for item in at.get("page_link") if item.proto.label == label]
    return link.proto.page_script_hash


def test_an_account_deleted_in_another_tab_stops_the_save(gymer):
    """Save after the account was deleted elsewhere stores nothing and says the account is gone."""
    _add_set(gymer, "squat", 5, 100.0, None)
    with db.connect() as conn:
        my_data.delete_user_data(conn, USER_ID)
    # The click's callback runs before the page works out that the account is gone.
    button(gymer, "Save workout").click().run(timeout=30)
    assert not gymer.exception
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM workout_sessions").fetchone()[0] == 0
    # The welcome page says why it is shown (round 5: the page's own notice would be dropped).
    assert "no longer exists" in texts(gymer)


def test_a_deleted_account_s_draft_leaves_the_session(gymer):
    """Once the account is gone, no workout key of the old account stays in the session."""
    _add_set(gymer, "squat", 5, 100.0, None)
    assert gymer.session_state["workout_draft"]
    with db.connect() as conn:
        my_data.delete_user_data(conn, USER_ID)
    gymer.run(timeout=30)
    keys = (workouts.DRAFT_KEY, workouts.EDITING_KEY, workouts.KEPT_DAY_KEY, workouts.NOTICE_KEY)
    for key in keys:
        assert key not in gymer.session_state


def test_every_workouts_session_key_has_the_prefix_the_account_drops():
    """Each session key of the page starts with WORKOUT_KEY_PREFIX, so none outlives an account."""
    source = Path(workouts.__file__).read_text(encoding="utf-8")
    keys = {
        value
        for name, value in vars(workouts).items()
        if name.endswith("_KEY") and isinstance(value, str)
    }
    # The widget keys are written in the calls (key="..."), so they are read from the source.
    keys |= set(re.findall(r'key="([^"]+)"', source))
    keys |= set(re.findall(r'key=f"([^"{]+)', source))
    assert len(keys) >= 10
    assert all(key.startswith(views_account.WORKOUT_KEY_PREFIX) for key in keys), keys
