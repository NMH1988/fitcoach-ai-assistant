"""UI tests for sign-in, roles, pages per role, the privacy note and the store's errors (T9.5)."""

import io
import logging
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import account, config, observability
from src.profile import UserProfile
from src.store import db, records, users
from views import navigation

APP = Path(__file__).resolve().parent.parent / "app.py"
SECRET = "k" * config.USER_KEY_SECRET_MIN_CHARS
AUTH = {
    "redirect_uri": "http://localhost:8501/oauth2callback",
    "cookie_secret": "c" * 40,
    "client_id": "test-client.apps.googleusercontent.com",
    "client_secret": "test-not-a-real-secret",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}
ISSUER = "https://accounts.google.com"
SUBJECT = "canary-sub-424242"
# What Google sends besides the ID: never stored, logged or shown (D14).
EMAIL = "canary.person@example.com"
NAME = "Canary Googlename"
PICTURE = "https://example.com/canary-picture.png"
USER_ID = account.user_key(ISSUER, SUBJECT, SECRET)
PROFILE = UserProfile(
    weight_kg=74.6, height_cm=171, age=41, sex="male", activity="light", goal="maintain"
)

pytestmark = pytest.mark.usefixtures("no_env_key")


class FakeUser(dict):
    """Stands in for st.user: a mapping of the ID token's claims plus is_logged_in."""


def signed_in() -> FakeUser:
    """Return st.user as Streamlit fills it after a Google sign-in, with canary values."""
    return FakeUser(
        is_logged_in=True, iss=ISSUER, sub=SUBJECT, email=EMAIL, name=NAME, picture=PICTURE
    )


@pytest.fixture
def calls(monkeypatch):
    """Replace st.login and st.logout with recorders and return the list of calls."""
    made = []
    monkeypatch.setattr(st, "login", lambda *args: made.append("login"))
    monkeypatch.setattr(st, "logout", lambda: made.append("logout"))
    return made


def start(monkeypatch, *, user=None, auth=True, language="en") -> AppTest:
    """Run app.py once with sign-in set up (or not) and st.user faked, and return the handle."""
    monkeypatch.setattr(st, "user", user if user is not None else FakeUser())
    at = AppTest.from_file(str(APP))
    at.secrets["UNRELATED"] = "x"
    if auth:
        at.secrets["auth"] = dict(AUTH)
        at.secrets["account"] = {"user_key_secret": SECRET}
    at.session_state["language"] = language
    at.run(timeout=30)
    return at


def store_account(role: str, name: str = "Sam", profile: UserProfile | None = None) -> None:
    """Store the canary user's account (and a saved profile for a gymer) before the app runs."""
    with db.connect() as conn:
        users.create_user(conn, USER_ID, role, name)
        if profile is not None:
            account.save_profile(conn, USER_ID, profile, with_weight=True)


def button(at: AppTest, label: str):
    """Return the one button with this label; the sidebar's when the My targets tab has one too."""
    found = [item for item in at.button if item.label == label]
    if len(found) > 1:
        found = [item for item in at.sidebar.button if item.label == label]
    (item,) = found
    return item


def texts(at: AppTest) -> str:
    """Return every caption, Markdown, error and subheader of the page as one text."""
    parts = [*at.caption, *at.markdown, *at.error, *at.subheader, *at.warning]
    return "\n".join(str(part.value) for part in parts)


def page_links(at: AppTest) -> list[str]:
    """Return the labels of the page's page links."""
    return [link.proto.label for link in at.get("page_link")]


# --- The guest and the sign-in button -------------------------------------------------------------


def test_without_auth_the_button_is_hidden_and_a_note_says_why(monkeypatch):
    """No [auth] section: no sign-in button, the note, and today's chat tabs (AC-19)."""
    at = start(monkeypatch, auth=False)
    assert not [item for item in at.button if item.label == "Sign in with Google"]
    assert "Sign-in is off" in texts(at)
    assert len(at.tabs) == 4


def test_with_auth_a_guest_sees_the_sign_in_button(monkeypatch, calls):
    """With sign-in set up, a guest gets "Sign in with Google", which starts st.login."""
    at = start(monkeypatch)
    button(at, "Sign in with Google").click().run(timeout=30)
    assert calls == ["login"]
    assert len(at.tabs) == 4


def test_the_sign_in_button_is_not_primary(monkeypatch):
    """White text on the sidebar's primary is 2.0:1, so the button is secondary (T9.23)."""
    at = start(monkeypatch)
    assert button(at, "Sign in with Google").proto.type != "primary"


def test_with_example_placeholders_sign_in_is_not_offered(monkeypatch):
    """An [auth] section with the example's cookie secret shows the not-set-up note instead."""
    monkeypatch.setattr(st, "user", FakeUser())
    at = AppTest.from_file(str(APP))
    at.secrets["auth"] = {**AUTH, "cookie_secret": config.COOKIE_SECRET_PLACEHOLDER}
    at.secrets["account"] = {"user_key_secret": SECRET}
    at.run(timeout=30)
    assert not [item for item in at.button if item.label == "Sign in with Google"]
    assert "not fully set up" in texts(at)


def test_a_guest_writes_nothing_to_disk(monkeypatch):
    """A guest who saves a profile and opens the app's pages never creates the store file."""
    at = start(monkeypatch)
    button(at, "Add your details").click().run(timeout=30)
    at.number_input(key="profile_form_weight").set_value(80.0)
    at.number_input(key="profile_form_height_cm").set_value(180)
    at.number_input(key="profile_form_age").set_value(30)
    at.segmented_control(key="profile_form_sex").set_value("male")
    at.selectbox(key="profile_form_activity").set_value("moderate")
    at.segmented_control(key="profile_form_goal").set_value("build_muscle")
    button(at, "Save").click().run(timeout=30)
    assert at.session_state["profile"].weight_kg == 80.0
    assert "Kept for this session only" in texts(at)
    assert not config.STORE_PATH.exists()
    assert not config.STORE_DIR.exists()


# --- The first sign-in (AC-18) --------------------------------------------------------------------


def test_the_first_sign_in_shows_only_the_welcome_page(monkeypatch):
    """Signed in with Google but no account yet: the welcome form, not the chat."""
    at = start(monkeypatch, user=signed_in())
    assert "Set up your account" in texts(at)
    assert not at.tabs
    assert at.radio(key="account_role").value is None
    assert button(at, "Sign out")


def _create(at: AppTest, role: str, name: str) -> AppTest:
    """Fill the welcome form and press Create account."""
    at.radio(key="account_role").set_value(role)
    at.text_input(key="account_name").input(name)
    return button(at, "Create account").click().run(timeout=30)


def test_creating_a_gymer_account_stores_the_keyed_id_role_and_name(monkeypatch):
    """The account is stored under the keyed hash with the role and name, and the chat follows."""
    at = _create(start(monkeypatch, user=signed_in()), "gymer", "  Sam  ")
    with db.connect() as conn:
        assert users.find_user(conn, USER_ID)["role"] == "gymer"
        assert users.find_user(conn, USER_ID)["display_name"] == "Sam"
    assert len(at.tabs) == 4
    assert "**Sam** · Gymer" in texts(at)


def test_a_bad_display_name_is_refused_and_nothing_is_stored(monkeypatch):
    """A refused name shows its reason and stores no account."""
    at = _create(start(monkeypatch, user=signed_in()), "coach", "**Boss**")
    assert "Use only letters" in texts(at)
    with db.connect() as conn:
        assert users.find_user(conn, USER_ID) is None


def test_no_role_is_refused(monkeypatch):
    """The role must be chosen."""
    at = start(monkeypatch, user=signed_in())
    at.text_input(key="account_name").input("Sam")
    button(at, "Create account").click().run(timeout=30)
    assert "Choose a role." in texts(at)


def test_the_google_name_email_and_picture_are_never_stored_shown_or_logged(monkeypatch):
    """The canary claims reach no stored byte, no element of the page and no log line (D14)."""
    stream = io.StringIO()
    configure = observability.configure_logging
    monkeypatch.setattr(
        observability,
        "configure_logging",
        lambda: configure(level=logging.DEBUG, stream=stream),
    )
    at = _create(start(monkeypatch, user=signed_in()), "gymer", "Sam")
    page = texts(at) + "".join(str(item.value) for item in at.text_input)
    stored = config.STORE_PATH.read_bytes()
    for canary in (EMAIL, NAME, PICTURE, SUBJECT, "canary"):
        assert canary.encode() not in stored
        assert canary not in page
        assert canary not in stream.getvalue()


def test_sign_out_clears_the_session_and_calls_st_logout(monkeypatch, calls):
    """Sign out forgets the profile and the chat, then signs out of Google."""
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in())
    at.session_state["messages"] = [{"role": "user", "text": "canary question"}]
    at.session_state["my_data_export"] = '{"canary": 1}'
    button(at, "Sign out").click().run(timeout=30)
    assert calls == ["logout"]
    # The fake st.user is still signed in after the rerun (a real sign-out starts a new session),
    # so the profile is loaded again; what the session held besides it is gone.
    assert at.session_state["messages"] == []
    assert "my_data_export" not in at.session_state


# --- Pages per role (D20) -------------------------------------------------------------------------


def _role_user(role):
    """Store an account for a role (none for a guest or a first sign-in) and return st.user."""
    if role in ("coach", "gymer"):
        store_account(role)
    return None if role is None else signed_in()


@pytest.mark.parametrize("role", list(navigation.PAGES_BY_ROLE))
def test_a_page_of_another_role_cannot_be_reached_by_its_url(monkeypatch, role):
    """Requesting any url_path the role does not have shows the role's home instead."""
    at = start(monkeypatch, user=_role_user(role))
    home = navigation.PAGES_BY_ROLE[role][0]
    others = {path for paths in navigation.PAGES_BY_ROLE.values() for path in paths}
    for url_path in sorted(others - set(navigation.PAGES_BY_ROLE[role])):
        # What a browser sends for /<url_path>: the page hash Streamlit derives from it. AppTest
        # has no public way to request a callable page by URL, so its page hash is set directly.
        at._page_hash = calc_hash(url_path)
        at.run(timeout=30)
        if home == navigation.CHAT:
            assert len(at.tabs) == 4, url_path
        else:
            assert "Set up your account" in texts(at), url_path
        assert "Delete everything" not in texts(at), url_path


@pytest.mark.parametrize("role", ["coach", "gymer"])
def test_a_signed_in_user_reaches_my_data(monkeypatch, role):
    """My data is registered for both roles and opens by its URL."""
    store_account(role)
    at = start(monkeypatch, user=signed_in())
    at._page_hash = calc_hash(navigation.MY_DATA)
    at.run(timeout=30)
    assert "Delete everything" in texts(at)


# --- The store's errors ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "message"),
    [("en", "cannot be opened right now"), ("de", "können gerade nicht geöffnet werden")],
)
def test_a_store_that_cannot_be_opened_shows_one_fixed_message(monkeypatch, language, message):
    """connect() raising shows the fixed message in the language, not its text; nothing written."""

    def failing(path=None):
        """Fail as connect() does for a folder it cannot make."""
        raise db.StoreError("C:/private/folder could not be made")

    monkeypatch.setattr(db, "connect", failing)
    at = start(monkeypatch, user=signed_in(), language=language)
    page = texts(at)
    assert message in page
    assert "private" not in page
    assert len(at.tabs) == 4  # the session runs as a guest's
    assert not config.STORE_PATH.exists()


# --- The gymer's profile and the privacy note -----------------------------------------------------


def test_signing_in_loads_the_latest_profile(monkeypatch):
    """A gymer's saved profile is in the session after sign-in."""
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in())
    assert at.session_state["profile"] == PROFILE


def _fill(at: AppTest, weight: float = 80.0) -> AppTest:
    """Fill the open profile form in metric units."""
    at.number_input(key="profile_form_weight").set_value(weight)
    at.number_input(key="profile_form_height_cm").set_value(180)
    at.number_input(key="profile_form_age").set_value(30)
    at.segmented_control(key="profile_form_sex").set_value("male")
    at.selectbox(key="profile_form_activity").set_value("moderate")
    at.segmented_control(key="profile_form_goal").set_value("build_muscle")
    return at


def _counts() -> tuple[int, int, int]:
    """Return how many profile entries, weights and targets the canary user has."""
    with db.connect() as conn:
        return (
            len(records.list_profile_entries(conn, USER_ID, USER_ID)),
            len(records.list_body_measurements(conn, USER_ID, USER_ID)),
            len(records.list_targets(conn, USER_ID, USER_ID)),
        )


def test_the_first_save_needs_the_opt_in(monkeypatch):
    """Without the box ticked nothing is saved; ticked, Save stores entry, weight and target."""
    store_account("gymer")
    at = start(monkeypatch, user=signed_in())
    button(at, "Add your details").click().run(timeout=30)
    _fill(at)
    button(at, "Save").click().run(timeout=30)
    assert "Tick the box above" in texts(at)
    assert _counts() == (0, 0, 0)
    assert at.session_state["profile"] is None
    at.checkbox(key="profile_form_opt_in").check()
    button(at, "Save").click().run(timeout=30)
    assert _counts() == (1, 1, 1)
    assert at.session_state["profile"].weight_kg == 80.0


def test_a_gymer_with_a_saved_profile_saves_without_the_box(monkeypatch):
    """A gymer who saved before is not asked again; each Save adds an entry, weight and target."""
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in())
    button(at, "Edit details").click().run(timeout=30)
    assert not [box for box in at.checkbox if box.key == "profile_form_opt_in"]
    at.number_input(key="profile_form_weight").set_value(75.5)
    button(at, "Save").click().run(timeout=30)
    assert _counts() == (2, 2, 2)


def test_a_goal_change_is_saved_for_a_gymer(monkeypatch):
    """The sidebar's goal control adds an entry and a target, no weight."""
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in())
    at.segmented_control(key="sidebar_goal").set_value("lose_fat").run(timeout=30)
    assert _counts() == (2, 1, 2)
    with db.connect() as conn:
        assert account.load_profile(conn, USER_ID).goal == "lose_fat"


def test_a_coach_profile_stays_in_the_session(monkeypatch):
    """A coach's profile form keeps the details for the session and writes no record."""
    store_account("coach")
    at = start(monkeypatch, user=signed_in())
    button(at, "Add your details").click().run(timeout=30)
    _fill(at)
    assert not [box for box in at.checkbox if box.key == "profile_form_opt_in"]
    button(at, "Save").click().run(timeout=30)
    assert at.session_state["profile"].weight_kg == 80.0
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM profile_entries").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("language", "guest", "gymer", "coach", "link"),
    [
        (
            "en",
            "Kept for this session only",
            "Saved for your account",
            "a coach's details are not stored",
            "See, export or delete it in My data",
        ),
        (
            "de",
            "Nur für diese Sitzung",
            "Für Ihr Konto gespeichert",
            "Die Angaben eines Coachs werden nicht gespeichert",
            "Unter Meine Daten ansehen, exportieren oder löschen",
        ),
    ],
)
def test_the_privacy_note_per_user(monkeypatch, language, guest, gymer, coach, link):
    """A guest keeps today's text; a gymer and a coach get theirs, a My data link and the ask."""
    at = start(monkeypatch, language=language)
    at.session_state["profile"] = PROFILE
    at.run(timeout=30)
    assert guest in texts(at)
    assert gymer not in texts(at)
    assert link not in page_links(at)
    store_account("gymer", profile=PROFILE)
    at = start(monkeypatch, user=signed_in(), language=language)
    assert gymer in texts(at)
    assert link in page_links(at)
    real = "do not enter real health data" if language == "en" else "keine echten Gesundheitsdaten"
    assert real in texts(at)
    chat = "earlier questions and answers" if language == "en" else "früheren Fragen und Antworten"
    assert chat in texts(at)
    _reset_store()
    store_account("coach")
    at = start(monkeypatch, user=signed_in(), language=language)
    assert coach in texts(at)
    assert real in texts(at)
    assert link in page_links(at)


def _reset_store() -> None:
    """Delete the canary user's rows, so a test can store them again under another role."""
    from src.store import my_data

    with db.connect() as conn:
        my_data.delete_user_data(conn, USER_ID)
