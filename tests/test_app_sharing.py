"""UI tests for the coach's Clients page and the gymer's Coach and sharing page (T9.12).

AC-20 (a relationship only from a valid code), AC-22 (a revoked scope or an ended relationship
blocks the coach's next read), D15 (a code shown once, stored as a hash, cancellable).
"""

import hashlib
import sqlite3
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import account, config, i18n
from src.store import access, db, invitations, records, users
from tests.test_app_account import PROFILE, USER_ID, button, signed_in, start, store_account, texts
from views import clients, navigation, sharing

pytestmark = pytest.mark.usefixtures("no_env_key")

OTHER_COACH = "coach-kai"
CLIENT_A = "gym-alex"
CLIENT_B = "gym-bo"


def page_text(at: AppTest) -> str:
    """Return the page's texts (test_app_account.texts) and its success and info boxes."""
    boxes = (str(item.value) for item in (*at.success, *at.info))
    return "\n".join((texts(at), *boxes))


def open_page(at: AppTest, url_path: str) -> AppTest:
    """Open a page by its URL path, as a browser would."""
    at._page_hash = calc_hash(url_path)
    return at.run(timeout=30)


def _relationship(coach: str, client: str, scopes=()) -> int:
    """Pair a coach and a gymer in the store with the given scopes on."""
    with db.connect() as conn:
        found = users.start_relationship(conn, coach, client)
        for scope in scopes:
            users.set_consent(conn, client, found, scope, True)
    return found


def _gymer(user_id: str, name: str) -> None:
    """Store a made-up gymer with one weight, so a coach's reads have a row."""
    with db.connect() as conn:
        users.create_user(conn, user_id, "gymer", name)
        records.add_body_measurement(conn, user_id, weight_kg=70.0, measured_on=date(2026, 11, 2))


def _coach(user_id: str = OTHER_COACH, name: str = "Coach Kai") -> None:
    """Store a made-up coach."""
    with db.connect() as conn:
        users.create_user(conn, user_id, "coach", name)


def _code_for(coach: str = OTHER_COACH) -> str:
    """Create a code for a coach in the store and return it."""
    with db.connect() as conn:
        return invitations.create_invitation(conn, coach).code


def _invitation_rows() -> list[dict]:
    """Return every stored invitation row."""
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM invitations")]


def _statuses(client: str = USER_ID) -> list[str]:
    """Return the statuses of a gymer's relationships, oldest first."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT status FROM coach_clients WHERE client_id = ? ORDER BY id", (client,)
        )
        return [row["status"] for row in rows]


def _coach_reads(read, coach: str = OTHER_COACH, client: str = USER_ID) -> bool:
    """Return True if the coach's read of the client's data is allowed now."""
    with db.connect() as conn:
        try:
            read(conn, coach, client)
        except access.NotFound:
            return False
    return True


def _scope_box(at: AppTest, scope: str):
    """Return the checkbox of a scope (its label starts with the scope's bold name)."""
    name = {"nutrition": "Nutrition", "training": "Training", "body": "Body"}[scope]
    (box,) = [item for item in at.checkbox if item.label.startswith(f"**{name}**")]
    return box


# --- The coach's Clients page ---------------------------------------------------------------------


@pytest.fixture
def coach_with_clients():
    """Store the canary user as a coach with a client sharing two scopes and a former client."""
    store_account("coach", name="Coach Sam")
    _gymer(CLIENT_A, "Alex")
    _gymer(CLIENT_B, "Bo")
    _relationship(USER_ID, CLIENT_A, ("nutrition", "body"))
    ended = _relationship(USER_ID, CLIENT_B, ("training",))
    with db.connect() as conn:
        users.end_relationship(conn, CLIENT_B, ended)


def test_the_coach_sees_each_client_with_the_scopes_on(monkeypatch, coach_with_clients):
    """The client list shows the name, active or former, and what is shared (criterion 5)."""
    # Since T9.15 an active client's row holds the week's values, "Not shared" for a scope off,
    # and an ended relationship is listed apart with its name and days.
    at = open_page(start(monkeypatch, user=signed_in()), navigation.CLIENTS)
    active, former = at.dataframe[0].value, at.dataframe[1].value
    assert list(active["Client"]) == ["Alex"]
    assert list(active["Days logged"]) == ["0 of 7 days logged"]  # nutrition shared
    assert list(active["Latest weight"]) == ["70 kg (2026-11-02)"]  # body shared
    assert list(active["Sessions"]) == ["Not shared"]  # training off
    assert list(former["Client"]) == ["Bo"] and former["Ended"][0]


def test_the_client_list_reads_names_through_the_relationship_checked_function(
    monkeypatch, coach_with_clients
):
    """Each name on the page comes from users.display_name_of (criterion 5)."""
    calls = []
    real = users.display_name_of

    def spy(conn, actor, other):
        """Record the call and read the name."""
        calls.append((actor, other))
        return real(conn, actor, other)

    monkeypatch.setattr(users, "display_name_of", spy)
    open_page(start(monkeypatch, user=signed_in()), navigation.CLIENTS)
    assert (USER_ID, CLIENT_A) in calls and (USER_ID, CLIENT_B) in calls


def test_a_coach_with_no_clients_is_told_how_to_invite(monkeypatch):
    """No clients yet: a line says to create an invitation."""
    store_account("coach")
    at = open_page(start(monkeypatch, user=signed_in()), navigation.CLIENTS)
    assert "No clients yet" in page_text(at)
    assert not at.dataframe


def test_a_new_code_is_shown_once_and_stored_only_as_its_hash(monkeypatch):
    """Create shows the code until it is noted; the store holds its hash, never the code."""
    store_account("coach")
    at = open_page(start(monkeypatch, user=signed_in()), navigation.CLIENTS)
    button(at, "Create an invitation").click().run(timeout=30)
    (shown,) = at.code
    code = shown.value
    assert len(code.replace("-", "")) == config.INVITE_CODE_LENGTH
    [row] = _invitation_rows()
    assert row["code_hash"] == hashlib.sha256(code.replace("-", "").encode()).hexdigest()
    assert code not in str(row)
    assert "shown only now" in page_text(at)
    # A rerun keeps it until the coach says it is noted; then it is gone for good.
    at.run(timeout=30)
    assert [item.value for item in at.code] == [code]
    button(at, "I have noted the code").click().run(timeout=30)
    assert not at.code
    assert code not in page_text(at)
    assert list(at.dataframe[0].value["State"]) == ["Open"]


def test_the_coach_cancels_a_code(monkeypatch):
    """Picking the unused code and cancelling it deletes it and hides the shown code."""
    store_account("coach")
    at = open_page(start(monkeypatch, user=signed_in()), navigation.CLIENTS)
    button(at, "Create an invitation").click().run(timeout=30)
    [row] = _invitation_rows()
    at.selectbox(key=clients.CANCEL_KEY).set_value(row["id"]).run(timeout=30)
    button(at, "Cancel this invitation").click().run(timeout=30)
    assert _invitation_rows() == []
    assert not at.code
    assert "No unused codes." in page_text(at)


def test_the_clients_page_in_german(monkeypatch, coach_with_clients):
    """The client list's headers and values follow the language."""
    at = open_page(start(monkeypatch, user=signed_in(), language="de"), navigation.CLIENTS)
    active, former = at.dataframe[0].value, at.dataframe[1].value
    assert list(active["Klient"]) == ["Alex"] and list(former["Klient"]) == ["Bo"]
    assert list(active["Einheiten"]) == ["Nicht geteilt"]
    assert "Einladungen" in page_text(at)


# --- The gymer's Coach and sharing page ----------------------------------------------------------


@pytest.fixture
def gymer_and_coach():
    """Store the canary user as a gymer with a profile, and another coach with a code."""
    store_account("gymer", profile=PROFILE)
    _coach()


def _accept(at: AppTest, code: str, scopes=()) -> AppTest:
    """Type a code, tick the scopes and press Accept."""
    at.text_input(key=sharing.CODE_KEY).input(code)
    for scope in scopes:
        _scope_box(at, scope).check()
    return button(at, "Accept the invitation").click().run(timeout=30)


def test_a_gymer_with_no_coach_sees_the_code_form_with_every_scope_off(
    monkeypatch, gymer_and_coach
):
    """The page asks for a code, every scope starts off, and says qualifications are unchecked."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    assert "You have no coach" in page_text(at)
    assert [_scope_box(at, s).value for s in ("nutrition", "training", "body")] == [False] * 3
    assert "The app does not check a coach's qualifications." in page_text(at)
    assert "Coach Kai" not in page_text(at)  # no coach's name before a code is accepted


def test_a_valid_code_connects_the_gymer_with_the_chosen_scopes(monkeypatch, gymer_and_coach):
    """Accepting shares only the ticked scopes, and the page shows the coach's name (AC-20)."""
    code = _code_for()
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    _accept(at, code.lower().replace("-", " "), ["body"])
    assert _statuses() == ["active"]
    assert "You are now connected with your coach." in page_text(at)
    assert "**Your coach:** Coach Kai" in page_text(at)
    assert _coach_reads(records.list_body_measurements)
    assert not _coach_reads(records.list_meal_items)
    assert [_scope_box(at, s).value for s in ("nutrition", "training", "body")] == [
        False,
        False,
        True,
    ]


def _used(code: str) -> None:
    """Have another gymer accept the code first."""
    _gymer("gym-first", "First")
    with db.connect() as conn:
        invitations.accept_invitation(conn, "gym-first", code, [])


def _cancelled(code: str) -> None:
    """Have the coach cancel the code."""
    with db.connect() as conn:
        [row] = invitations.list_invitations(conn, OTHER_COACH)
        invitations.cancel_invitation(conn, OTHER_COACH, row["id"])


@pytest.mark.parametrize(
    ("case", "prepare"),
    [
        ("wrong", lambda code: None),
        ("used", _used),
        ("cancelled", _cancelled),
        ("expired", None),
    ],
)
def test_every_bad_code_gets_the_one_fixed_message(monkeypatch, gymer_and_coach, case, prepare):
    """A wrong, used, cancelled or expired code gets the same message and starts nothing."""
    code = _code_for()
    if case == "wrong":
        code = "ABCD-EFGH-JKLM"
    elif case == "expired":
        with db.connect() as conn:
            conn.execute("UPDATE invitations SET expires_at = '2026-01-01T00:00:00+00:00'")
    else:
        prepare(code)
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    _accept(at, code, ["body"])
    assert [item.value for item in at.error] == [
        "This code cannot be used. Check it with your coach, or ask them for a new one."
    ]
    assert _statuses() == []


def test_the_daily_limit_holds_across_a_reload(monkeypatch, gymer_and_coach):
    """Tries are counted in the store: a new session (a reload) is refused, even a valid code."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO invite_attempts (user_id, day, count) VALUES (?, ?, ?)",
            (USER_ID, account.today().isoformat(), config.INVITE_MAX_ATTEMPTS),
        )
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    _accept(at, _code_for(), ["body"])
    expected = (
        f"You have tried {config.INVITE_MAX_ATTEMPTS} codes today. Please try again tomorrow."
    )
    assert [item.value for item in at.error] == [expected]
    assert _statuses() == []


@pytest.fixture
def connected_gymer(gymer_and_coach):
    """Store the canary gymer as the other coach's client, sharing every scope."""
    return _relationship(OTHER_COACH, USER_ID, ("nutrition", "training", "body"))


def test_turning_a_scope_off_blocks_the_coachs_next_read(monkeypatch, connected_gymer):
    """Unticking nutrition and saving stops the coach's read of meals, not of weights (AC-22)."""
    assert _coach_reads(records.list_meal_items)
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    _scope_box(at, "nutrition").uncheck()
    button(at, "Save sharing").click().run(timeout=30)
    assert "Your sharing choices are saved." in page_text(at)
    assert not _coach_reads(records.list_meal_items)
    assert _coach_reads(records.list_body_measurements)
    _scope_box(at, "nutrition").check()
    button(at, "Save sharing").click().run(timeout=30)
    assert _coach_reads(records.list_meal_items)


def test_ending_the_relationship_needs_a_tick_and_blocks_every_read(monkeypatch, connected_gymer):
    """End is off until confirmed; then the coach reads nothing and the code form is back."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    assert button(at, "End the relationship").disabled
    at.checkbox(key=sharing.CONFIRM_END_KEY).check().run(timeout=30)
    button(at, "End the relationship").click().run(timeout=30)
    assert _statuses() == ["ended"]
    assert "The relationship has ended." in page_text(at)
    assert "You have no coach" in page_text(at)
    for read in (
        records.list_body_measurements,
        records.list_meal_items,
        records.list_workout_sessions,
    ):
        assert not _coach_reads(read)


def test_a_relationship_ended_by_the_coach_meanwhile_is_shown_as_it_is(
    monkeypatch, connected_gymer
):
    """Saving after the coach ended it writes nothing and shows the code form (no coach now)."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    with db.connect() as conn:
        users.end_relationship(conn, OTHER_COACH, connected_gymer)
    _scope_box(at, "body").uncheck()
    button(at, "Save sharing").click().run(timeout=30)
    assert "You have no coach" in page_text(at)
    assert "Coach Kai" not in page_text(at)
    with db.connect() as conn:
        open_consents = conn.execute(
            "SELECT count(*) FROM consents WHERE relationship_id = ? AND revoked_at IS NULL",
            (connected_gymer,),
        ).fetchone()[0]
    assert open_consents == 0


def test_the_sharing_page_in_german(monkeypatch, connected_gymer):
    """The coach's name line and the end section speak German."""
    at = open_page(start(monkeypatch, user=signed_in(), language="de"), navigation.SHARING)
    page = page_text(at)
    assert "**Ihr Coach:** Coach Kai" in page
    assert "Verbindung beenden" in page
    assert "Die App prüft die Qualifikationen eines Coaches nicht." in page


def test_a_failed_save_shows_the_stored_scopes_again(monkeypatch, connected_gymer):
    """A store failure saves nothing, shows the fixed message and redraws the stored scopes."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)

    def busy(*args):
        """Fail as a store that another session holds too long would."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(users, "set_scopes", busy)
    _scope_box(at, "nutrition").uncheck()
    button(at, "Save sharing").click().run(timeout=30)
    assert [item.value for item in at.error] == [i18n.t("account.store_unavailable", "en")]
    box = _scope_box(at, "nutrition")
    assert box.value is True
    # The stored value is sent to the browser too, so it stops showing the unsaved tick.
    assert box.proto.set_value is True
    assert _coach_reads(records.list_meal_items)
    # The next run (any click) keeps the stored value and sends nothing more.
    at.checkbox(key=sharing.CONFIRM_END_KEY).check().run(timeout=30)
    assert _scope_box(at, "nutrition").value is True
    assert _scope_box(at, "nutrition").proto.set_value is False
    assert not at.error


def test_a_coach_taken_in_another_tab_gets_the_has_coach_message(monkeypatch, gymer_and_coach):
    """A coach accepted elsewhere between the page's read and the accept: the code is refused."""
    code = _code_for()
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    _coach("coach-lee", "Coach Lee")
    real = invitations.accept_invitation

    def other_tab_first(conn, gymer_id, typed, scopes):
        """Accept another coach as a second tab would, then this page's code."""
        users.start_relationship(conn, "coach-lee", gymer_id)
        return real(conn, gymer_id, typed, scopes)

    # A later run reads the store before drawing, so only a change inside the run reaches it.
    monkeypatch.setattr(invitations, "accept_invitation", other_tab_first)
    _accept(at, code, ["body"])
    assert "You have a coach already. End that relationship first." in texts(at)
    assert _statuses() == ["active"]


def test_a_relationship_ended_while_saving_is_an_info_not_a_success(monkeypatch, connected_gymer):
    """An end between the page's read and the save shows the "changed" notice as information."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.SHARING)
    real = users.set_scopes

    def end_first(conn, client_id, relationship_id, wanted):
        """End the relationship as the coach would in another tab, then save."""
        users.end_relationship(conn, OTHER_COACH, relationship_id)
        return real(conn, client_id, relationship_id, wanted)

    monkeypatch.setattr(users, "set_scopes", end_first)
    _scope_box(at, "body").uncheck()
    button(at, "Save sharing").click().run(timeout=30)
    assert [item.value for item in at.info] == [
        "Your coach relationship changed in the meantime; the page shows it as it is now."
    ]
    assert not at.success


@pytest.mark.parametrize(
    ("language", "name_line", "end_line", "ai_line"),
    [
        (
            "en",
            "always sees your display name",
            "still sees your display name and the dates of the relationship",
            "go to an AI model through OpenRouter",
        ),
        (
            "de",
            "sieht immer Ihren Anzeigenamen",
            "weiterhin Ihren Anzeigenamen sowie Beginn und Ende der Verbindung",
            "über OpenRouter an ein KI-Modell",
        ),
    ],
)
def test_the_page_says_what_the_coach_keeps_seeing_and_who_drafts_reviews(
    monkeypatch, connected_gymer, language, name_line, end_line, ai_line
):
    """The texts name the shared display name, what stays after the end, and the AI draft."""
    at = open_page(start(monkeypatch, user=signed_in(), language=language), navigation.SHARING)
    page = page_text(at)
    assert name_line in page
    assert end_line in page
    # The first scope box is nutrition's, in either language.
    assert ai_line in at.checkbox[0].label


@pytest.mark.parametrize(
    ("language", "nutrition", "others"),
    [
        (
            "en",
            "this week's figures (averages and totals, not your name or foods) go to an AI model "
            "through OpenRouter",
            "a weekly review your coach starts also sends this week's",
        ),
        (
            "de",
            "gehen die Zahlen dieser Woche (Durchschnitte und Summen, nicht Ihr Name oder Ihre "
            "Lebensmittel) über OpenRouter an ein KI-Modell",
            "sendet ein Wochenbericht Ihres Coaches auch die",
        ),
    ],
)
def test_each_scope_says_what_a_weekly_review_sends_to_the_model(
    monkeypatch, connected_gymer, language, nutrition, others
):
    """T9.16: Nutrition names the AI model and OpenRouter; Training and Body say theirs go too."""
    at = open_page(start(monkeypatch, user=signed_in(), language=language), navigation.SHARING)
    labels = [box.label for box in at.checkbox]
    assert nutrition in labels[0]
    assert all(others in label for label in labels[1:3])
