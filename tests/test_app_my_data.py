"""UI tests for the My data page (AC-34) and demo mode (AC-19, D18) (T9.5)."""

import json
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import config, demo
from src.store import db, records
from tests.test_app_account import (
    APP,
    AUTH,
    PROFILE,
    SECRET,
    USER_ID,
    FakeUser,
    button,
    signed_in,
    start,
    store_account,
    texts,
)
from views import navigation, resources

pytestmark = pytest.mark.usefixtures("no_env_key")


def open_my_data(at: AppTest) -> AppTest:
    """Open the My data page by its URL path."""
    at._page_hash = calc_hash(navigation.MY_DATA)
    return at.run(timeout=30)


def _rows(table: str) -> int:
    """Return how many rows of a table name the canary user."""
    queries = {
        "profile_entries": "SELECT COUNT(*) FROM profile_entries WHERE user_id = ?",
        "body_measurements": "SELECT COUNT(*) FROM body_measurements WHERE user_id = ?",
        "users": "SELECT COUNT(*) FROM users WHERE id = ?",
    }
    with db.connect() as conn:
        return conn.execute(queries[table], (USER_ID,)).fetchone()[0]


@pytest.fixture
def gymer_with_records():
    """Store the canary gymer with a saved profile and one older weight."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        records.add_body_measurement(conn, USER_ID, weight_kg=76.0, measured_on=date(2026, 10, 1))


# --- My data (AC-34) ------------------------------------------------------------------------------


def test_my_data_lists_what_is_stored(monkeypatch, gymer_with_records):
    """The page lists each kind of record with its count and a table of the stored ones."""
    at = open_my_data(start(monkeypatch, user=signed_in()))
    page = texts(at)
    assert "**Profile entries** · 1 stored" in page
    assert "**Weights** · 2 stored" in page
    assert "**Daily targets** · 1 stored" in page
    assert "**Food log** · 0 stored" in page
    assert "**Sam** · Gymer" in page
    assert len(at.dataframe) == 3


def test_my_data_in_german(monkeypatch, gymer_with_records):
    """The page speaks German when German is chosen."""
    at = open_my_data(start(monkeypatch, user=signed_in(), language="de"))
    page = texts(at)
    assert "**Gewichte** · 2 gespeichert" in page
    assert "Alles löschen" in page


def test_the_export_is_built_on_request_and_holds_the_users_rows(monkeypatch, gymer_with_records):
    """Prepare the export builds the JSON of every stored row; then it can be downloaded."""
    at = open_my_data(start(monkeypatch, user=signed_in()))
    assert not at.get("download_button")
    button(at, "Prepare the export").click().run(timeout=30)
    (download,) = at.get("download_button")
    assert download.proto.label == "Download my data (JSON)"
    document = json.loads(at.session_state["my_data_export"])
    assert document["user"]["id"] == USER_ID
    assert len(document["body_measurements"]) == 2
    assert len(document["profile_entries"]) == 1


def test_deleting_one_entry_removes_only_it(monkeypatch, gymer_with_records):
    """Picking the older weight and deleting it leaves the other records."""
    at = open_my_data(start(monkeypatch, user=signed_in()))
    picker = at.selectbox(key="my_data_entry")
    older = next(option for option in picker.options if "2026-10-01" in option)
    picker.set_value(("body_measurements", _older_weight_id())).run(timeout=30)
    assert "Weights" in older
    button(at, "Delete this entry").click().run(timeout=30)
    assert _rows("body_measurements") == 1
    assert _rows("profile_entries") == 1
    assert "**Weights** · 1 stored" in texts(at)


def _older_weight_id() -> int:
    """Return the ID of the canary user's weight of 2026-10-01."""
    with db.connect() as conn:
        weights = records.list_body_measurements(conn, USER_ID, USER_ID)
    return next(row["id"] for row in weights if row["measured_on"] == "2026-10-01")


def test_the_delete_button_needs_a_picked_entry(monkeypatch, gymer_with_records):
    """With no entry picked, Delete this entry is off."""
    at = open_my_data(start(monkeypatch, user=signed_in()))
    assert button(at, "Delete this entry").disabled


def test_delete_everything_needs_the_confirmation_then_signs_out(
    monkeypatch, gymer_with_records, login_calls
):
    """The button is off until confirmed; then every row goes and the user is signed out."""
    at = open_my_data(start(monkeypatch, user=signed_in()))
    assert button(at, "Delete everything").disabled
    at.checkbox(key="my_data_confirm").check().run(timeout=30)
    button(at, "Delete everything").click().run(timeout=30)
    assert login_calls == ["logout"]
    assert _rows("users") == 0
    assert _rows("profile_entries") == 0
    assert _rows("body_measurements") == 0


def test_a_coach_sees_the_account_and_the_export(monkeypatch):
    """A coach keeps no records: the page shows the account, the export and the delete."""
    store_account("coach", name="Alex")
    at = open_my_data(start(monkeypatch, user=signed_in()))
    page = texts(at)
    assert "**Alex** · Coach" in page
    assert "Profile entries" not in page
    button(at, "Prepare the export").click().run(timeout=30)
    assert json.loads(at.session_state["my_data_export"])["user"]["role"] == "coach"


def test_my_data_shows_the_fixed_message_when_the_store_fails_later(monkeypatch):
    """A store that fails after sign-in shows the fixed message, never the error's text."""
    store_account("gymer", profile=PROFILE)
    at = open_my_data(start(monkeypatch, user=signed_in()))

    def failing(path=None):
        """Fail as connect() does for a broken file."""
        raise db.StoreError("C:/private/folder")

    monkeypatch.setattr(db, "connect", failing)
    button(at, "Prepare the export").click().run(timeout=30)
    assert "cannot be opened right now" in texts(at)
    assert "private" not in texts(at)


# --- Demo mode (AC-19, D18) -----------------------------------------------------------------------


@pytest.fixture
def demo_store_is_fresh(monkeypatch):
    """Clear the cached demo database before and after, so each test seeds its own."""
    monkeypatch.delenv(config.DEMO_MODE_NAME, raising=False)
    resources.demo_store.clear()
    yield
    resources.demo_store.clear()


def start_demo(monkeypatch, *, auth=False) -> AppTest:
    """Run app.py with DEMO_MODE on (and an [auth] section if asked)."""
    monkeypatch.setattr("streamlit.user", FakeUser())
    at = AppTest.from_file(str(APP))
    at.secrets["DEMO_MODE"] = True
    if auth:
        at.secrets["auth"] = dict(AUTH)
        at.secrets["account"] = {"user_key_secret": SECRET}
    at.run(timeout=30)
    return at


def test_demo_mode_offers_the_synthetic_users(monkeypatch, demo_store_is_fresh):
    """With DEMO_MODE on and no [auth], the picker lists a guest and the demo users only."""
    at = start_demo(monkeypatch)
    picker = at.selectbox(key="demo_user")
    assert picker.options == ["Guest (nothing stored)", *(u.display_name for u in demo.DEMO_USERS)]
    assert not [item for item in at.button if item.label == "Sign in with Google"]
    assert "Demo mode" in texts(at)


def test_picking_a_demo_gymer_loads_their_profile_from_the_demo_database(
    monkeypatch, demo_store_is_fresh
):
    """Sam's profile comes from the seeded temporary database; the real store file is untouched."""
    at = start_demo(monkeypatch)
    at.selectbox(key="demo_user").set_value(demo.SHARING_GYMER.id).run(timeout=30)
    assert at.session_state["profile"] == demo.PROFILES[demo.SHARING_GYMER.id]
    assert "**Demo gymer Sam** · Gymer" in texts(at)
    assert resources.demo_store() != config.STORE_PATH
    assert not config.STORE_PATH.exists()


def test_a_demo_coach_reaches_my_data(monkeypatch, demo_store_is_fresh):
    """The demo coach has the coach's pages."""
    at = start_demo(monkeypatch)
    at.selectbox(key="demo_user").set_value(demo.COACH.id).run(timeout=30)
    at = open_my_data(at)
    assert "**Demo coach Alex** · Coach" in texts(at)


def test_demo_mode_is_off_by_default(monkeypatch, demo_store_is_fresh):
    """Without DEMO_MODE there is no picker."""
    at = start(monkeypatch, auth=False)
    assert not [box for box in at.selectbox if box.key == "demo_user"]


def test_demo_mode_is_ignored_when_auth_exists(monkeypatch, demo_store_is_fresh):
    """With an [auth] section the picker is gone and sign-in is offered instead (D18)."""
    at = start_demo(monkeypatch, auth=True)
    assert not [box for box in at.selectbox if box.key == "demo_user"]
    assert button(at, "Sign in with Google")
