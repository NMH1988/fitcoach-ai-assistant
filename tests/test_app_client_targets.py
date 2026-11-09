"""UI tests for coach-set targets (T9.17): the coach's form, the gymer's read-only view.

The coach sets a client's targets only while the client shares nutrition, and a write the store
refuses after the page was drawn shows one fixed message. The gymer sees the coach's target on My
profile, marked as set by the coach, with no control to change it; My data lists it as "Your coach"
and offers no delete for it alone, while "Delete everything" still removes it (AC-34).
"""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.store import db, records, users
from src.store.access import NotFound
from tests.test_app_account import PROFILE, USER_ID, button, signed_in, start, store_account
from tests.test_app_dashboards import (  # noqa: F401 (fixtures used by name)
    ALEX,
    BO,
    TODAY,
    _client_week,
    _gymer_with_week,
    _pair,
    coach_world,
    today,
)
from tests.test_app_sharing import open_page
from views import client_week, navigation

pytestmark = pytest.mark.usefixtures("no_env_key")

COACH_TARGET = {"kcal": 2100.0, "protein_g": 170.0, "carbs_g": 200.0, "fat_g": 65.0}
COACH = "coach-kai-t917"


def _page_text(at: AppTest) -> str:
    """Return every caption, Markdown, message and subheader of the page as one text."""
    parts = [
        *at.caption,
        *at.markdown,
        *at.error,
        *at.subheader,
        *at.warning,
        *at.info,
        *at.success,
    ]
    return "\n".join(str(part.value) for part in parts)


def _targets_of(user_id: str) -> list[dict]:
    """Return a user's stored targets, oldest first, read as the user."""
    with db.connect() as conn:
        return records.list_targets(conn, user_id, user_id)


def _audit_actions() -> list[str]:
    """Return every audit row's action, by ID."""
    with db.connect() as conn:
        return [row["action"] for row in conn.execute("SELECT action FROM audit_log ORDER BY id")]


def _fill_and_save(at: AppTest, values: dict[str, float]) -> AppTest:
    """Type the target values into the coach's form and press Set targets."""
    for field, value in values.items():
        at.number_input(key=f"client_targets_{field}").set_value(value)
    [save] = [item for item in at.button if item.label == "Set targets"]
    return save.click().run(timeout=30)


# --- The coach's form on Client week -------------------------------------------------------------


@pytest.mark.usefixtures("coach_world")
def test_a_coach_sets_a_shared_client_s_targets(monkeypatch):
    """The new row is the coach's, from today, with one target_set audit row (criterion 5)."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at = _fill_and_save(at, COACH_TARGET)
    latest = _targets_of(ALEX)[-1]
    assert latest["set_by"] == "coach"
    assert latest["effective_from"] == TODAY.isoformat()
    assert {key: latest[key] for key in COACH_TARGET} == COACH_TARGET
    assert _audit_actions().count("target_set") == 1
    assert "The new targets apply from 2026-10-29." in _page_text(at)


@pytest.mark.usefixtures("coach_world")
def test_the_form_starts_from_the_client_s_target_today(monkeypatch):
    """The fields hold the client's current target, so a small change is one field."""
    at = _client_week(monkeypatch, chosen=ALEX)
    current = _targets_of(ALEX)[-1]
    assert at.number_input(key="client_targets_kcal").value == current["kcal"]
    assert at.number_input(key="client_targets_fat_g").value == current["fat_g"]


@pytest.mark.usefixtures("coach_world")
def test_the_form_starts_from_today_s_target_whatever_the_week(monkeypatch):
    """A past week with another target still fills the form with today's (round 2, owner)."""
    with db.connect() as conn:
        records.add_target(
            conn, ALEX, **COACH_TARGET, set_by="user", effective_from=date(2026, 10, 20)
        )
    today_kcal = _targets_of(ALEX)[-1]["kcal"]  # the profile Save's target, from today
    at = _client_week(monkeypatch, chosen=ALEX)
    at.date_input(key=client_week.WEEK_KEY).set_value(date(2026, 10, 21)).run(timeout=30)
    assert "2026-10-19 to 2026-10-25" in _page_text(at)
    assert at.number_input(key="client_targets_kcal").value == today_kcal != COACH_TARGET["kcal"]


@pytest.mark.usefixtures("coach_world")
def test_another_client_starts_the_form_from_their_target(monkeypatch):
    """Typed values are not carried to the next client sharing nutrition (round 1)."""
    with db.connect() as conn:
        _gymer_with_week(conn, "gym-eve", "Eve")
        records.add_target(conn, "gym-eve", **COACH_TARGET, set_by="user", effective_from=TODAY)
        _pair(conn, USER_ID, "gym-eve", ("nutrition",))
    at = _client_week(monkeypatch, chosen=ALEX)
    at.number_input(key="client_targets_kcal").set_value(3000.0).run(timeout=30)
    at.selectbox(key=client_week.PICK_KEY).set_value("gym-eve").run(timeout=30)
    assert at.number_input(key="client_targets_kcal").value == COACH_TARGET["kcal"]


@pytest.mark.usefixtures("coach_world")
def test_no_form_for_a_client_who_does_not_share_nutrition(monkeypatch):
    """Bo shares training only: no field, and a line says why (criterion 5)."""
    at = _client_week(monkeypatch, chosen=BO)
    assert not [item for item in at.number_input if item.key.startswith("client_targets_")]
    assert "Targets can be set only while the client shares nutrition." in _page_text(at)


@pytest.mark.usefixtures("coach_world")
def test_a_share_revoked_after_the_page_was_drawn_writes_nothing(monkeypatch):
    """The store refuses the write: one fixed message, no target and no audit row of it."""
    at = _client_week(monkeypatch, chosen=ALEX)
    before = len(_targets_of(ALEX))
    with db.connect() as conn:
        [relationship] = [
            row for row in users.list_relationships(conn, ALEX) if row["status"] == "active"
        ]
        users.set_consent(conn, ALEX, relationship["id"], "nutrition", False)
    at = _fill_and_save(at, COACH_TARGET)
    # The click's run reads the week again without nutrition: the form is gone, nothing written.
    assert len(_targets_of(ALEX)) == before
    assert "target_set" not in _audit_actions()
    assert "Targets can be set only while the client shares nutrition." in _page_text(at)


@pytest.mark.usefixtures("coach_world")
def test_a_write_the_store_refuses_shows_one_fixed_message(monkeypatch):
    """A refusal between the page's read and the write (NotFound) names no reason."""
    at = _client_week(monkeypatch, chosen=ALEX)

    def refused(*args, **kwargs):
        """Refuse as the store does for a client who stopped sharing in between."""
        raise NotFound

    monkeypatch.setattr(records, "add_client_target", refused)
    at = _fill_and_save(at, COACH_TARGET)
    assert "The targets were not set: you cannot set targets for this client now." in _page_text(at)


@pytest.mark.usefixtures("coach_world")
def test_a_target_the_store_finds_out_of_range_shows_the_invalid_line(monkeypatch):
    """A kcal under the floor reaches the store's own check: the invalid line, nothing written."""
    at = _client_week(monkeypatch, chosen=ALEX)
    before = len(_targets_of(ALEX))
    real = records.add_client_target

    def below_the_floor(conn, coach_id, client_id, **target):
        """Pass the real store a kcal under the calorie floor, as the form's limits would not."""
        target["kcal"] = config.CALORIE_FLOOR_KCAL - 1.0
        return real(conn, coach_id, client_id, **target)

    monkeypatch.setattr(records, "add_client_target", below_the_floor)
    at = _fill_and_save(at, COACH_TARGET)
    assert "The targets were not set: fill in every field within its range." in _page_text(at)
    assert len(_targets_of(ALEX)) == before
    assert "target_set" not in _audit_actions()


@pytest.mark.usefixtures("coach_world")
def test_the_form_in_german(monkeypatch):
    """The form's heading and labels are German when German is chosen."""
    at = start(monkeypatch, user=signed_in(), language="de")
    at = open_page(at, navigation.CLIENT_WEEK)
    at.selectbox(key="client_week_pick").set_value(ALEX).run(timeout=30)
    assert "Tagesziele" in _page_text(at)
    assert at.number_input(key="client_targets_kcal").label == "Energie (kcal pro Tag)"
    assert [item for item in at.button if item.label == "Ziele setzen"]


# --- The gymer's read-only view ------------------------------------------------------------------


@pytest.fixture
def coached_gymer():
    """Store the canary gymer with a saved profile, a coach sharing nutrition and their target."""
    store_account("gymer", profile=None)
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = users.start_relationship(conn, COACH, USER_ID)
        users.set_consent(conn, USER_ID, relationship, "nutrition", True)
        records.add_target(
            conn,
            USER_ID,
            kcal=2500.0,
            protein_g=150.0,
            carbs_g=280.0,
            fat_g=75.0,
            set_by="system",
            effective_from=date(2026, 10, 20),
        )
        records.add_client_target(conn, COACH, USER_ID, **COACH_TARGET, effective_from=TODAY)


def test_the_gymer_sees_the_coach_s_target_on_my_profile(monkeypatch, coached_gymer):
    """Marked as set by the coach, read-only: no field or button for it (criterion 8)."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.PROFILE)
    [notice] = [item.value for item in at.info if "Your coach set" in item.value]
    assert "from 2026-10-29: 2,100 kcal, 170 g protein, 200 g carbohydrate and 65 g fat" in notice
    assert not [item for item in at.number_input if item.key.startswith("client_targets_")]


def test_the_notice_in_german(monkeypatch, coached_gymer):
    """The gymer's notice is German when German is chosen."""
    at = open_page(start(monkeypatch, user=signed_in(), language="de"), navigation.PROFILE)
    assert [item for item in at.info if "Ihr Coach hat Ihr Tagesziel" in item.value]


def test_no_notice_when_the_active_target_is_the_gymer_s_own(monkeypatch):
    """A gymer without a coach's target sees no notice."""
    store_account("gymer")
    with db.connect() as conn:
        records.add_target(
            conn,
            USER_ID,
            kcal=2500.0,
            protein_g=150.0,
            carbs_g=280.0,
            fat_g=75.0,
            set_by="system",
            effective_from=TODAY,
        )
    at = open_page(start(monkeypatch, user=signed_in()), navigation.PROFILE)
    assert not [item for item in at.info if "Your coach set" in item.value]


def test_my_data_lists_the_coach_s_target_without_a_delete(monkeypatch, coached_gymer):
    """My data shows "Your coach", and the delete picker offers only the gymer's own target."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.MY_DATA)
    table = [frame.value for frame in at.dataframe if "Set by" in frame.value.columns][0]
    assert list(table["Set by"]) == ["The app", "Your coach"]
    # The gymer's own target is the one entry offered (no profile entry or log was stored).
    assert len(at.selectbox(key="my_data_entry").options) == 1
    assert "Delete everything below removes it." in "\n".join(str(c.value) for c in at.caption)


def test_delete_everything_removes_the_coach_s_target(monkeypatch, coached_gymer):
    """AC-34: the gymer's "Delete everything" removes the coach's target with the rest."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.MY_DATA)
    at.checkbox(key="my_data_confirm").check().run(timeout=30)
    [delete] = [item for item in at.button if item.label == "Delete everything"]
    delete.click().run(timeout=30)
    with db.connect() as conn:
        found = "SELECT count(*) FROM nutrition_targets WHERE user_id = ?"
        assert conn.execute(found, (USER_ID,)).fetchone()[0] == 0


@pytest.fixture
def coached_gymer_with_profile():
    """Store the canary gymer with a saved profile and a coach whose target is the active one."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, COACH, "coach", "Coach Kai")
        relationship = users.start_relationship(conn, COACH, USER_ID)
        users.set_consent(conn, USER_ID, relationship, "nutrition", True)
        records.add_client_target(conn, COACH, USER_ID, **COACH_TARGET, effective_from=TODAY)


@pytest.mark.usefixtures("coached_gymer_with_profile")
def test_a_goal_change_keeps_the_coach_s_target_and_says_so(monkeypatch):
    """The sidebar's goal Save writes no target, and a note says the coach's target stays."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.PROFILE)
    at.segmented_control(key="sidebar_goal").set_value("lose_fat").run(timeout=30)
    assert _targets_of(USER_ID)[-1]["set_by"] == "coach"
    notes = [item.value for item in at.sidebar.info]
    assert "Your details are saved. Your daily target stays the one your coach set." in notes


@pytest.mark.usefixtures("coached_gymer_with_profile")
def test_the_sidebar_s_computed_target_says_it_is_not_the_active_one(monkeypatch):
    """The sidebar card's target is labelled as worked out, the coach's being the active one."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.PROFILE)
    captions = "\n".join(str(item.value) for item in at.sidebar.caption)
    assert "Your active target is the one your coach set (My profile)." in captions


@pytest.mark.usefixtures("coached_gymer_with_profile")
def test_a_dialog_save_keeps_the_coach_s_target_and_says_so(monkeypatch):
    """The My profile dialog's Save writes the weight, no target, and the note (round 2)."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.PROFILE)
    button(at, "Edit details").click().run(timeout=30)
    at.number_input(key="profile_form_weight").set_value(75.5)
    button(at, "Save").click().run(timeout=30)
    assert _targets_of(USER_ID)[-1]["set_by"] == "coach"
    notes = [item.value for item in at.sidebar.info]
    assert "Your details are saved. Your daily target stays the one your coach set." in notes


@pytest.mark.parametrize(
    ("language", "unverified"),
    [
        ("en", "The app does not check a coach's qualifications."),
        ("de", "Die App prüft die Qualifikationen eines Coaches nicht."),
    ],
)
@pytest.mark.usefixtures("coached_gymer")
def test_the_coach_s_target_says_qualifications_are_not_checked(monkeypatch, language, unverified):
    """Under the coach's target, the app says it does not check coaches (compliance run 1)."""
    at = open_page(start(monkeypatch, user=signed_in(), language=language), navigation.PROFILE)
    assert unverified in "\n".join(str(item.value) for item in at.caption)


@pytest.mark.parametrize(
    ("language", "phrase"),
    [
        ("en", "cannot change them while they share nutrition with you"),
        ("de", "kann sie nicht ändern, solange er die Ernährung mit Ihnen teilt"),
    ],
)
@pytest.mark.usefixtures("coach_world")
def test_the_form_says_the_client_cannot_change_it_while_sharing(monkeypatch, language, phrase):
    """The form claims no more than the store does (compliance run 1)."""
    at = start(monkeypatch, user=signed_in(), language=language)
    at = open_page(at, navigation.CLIENT_WEEK)
    at.selectbox(key="client_week_pick").set_value(ALEX).run(timeout=30)
    assert phrase in _page_text(at)
