"""UI tests for the dashboards (T9.15): the coach's Clients and Client week, the gymer's My week.

AC-21 (no other coach's or former client by any query parameter), AC-26 ("3 of 7 days logged"),
AC-41 (an approved review is labelled as an AI draft the coach approved), and the phone cards
holding the same values as the table (the owner's decision of 2026-10-30).
"""

from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from src import account, metrics
from src.store import db, records, reviews, users
from tests.test_app_account import PROFILE, USER_ID, signed_in, start, store_account, texts
from tests.test_app_sharing import open_page
from views import client_week, clients, my_week, navigation, tables

pytestmark = pytest.mark.usefixtures("no_env_key")

TODAY = date(2026, 10, 29)  # a Thursday: the week of 2026-10-26 is in progress
MONDAY = date(2026, 10, 26)
ALEX, BO, CY, DEE = "gym-alex", "gym-bo", "gym-cy", "gym-dee"
OTHER_COACH = "coach-kai"


@pytest.fixture(autouse=True)
def today(monkeypatch):
    """Fix today in Berlin to Thursday 2026-10-29, for the app and for the records written."""
    monkeypatch.setattr(metrics, "berlin_day", lambda moment=None: TODAY)


def _meal(conn, user_id: str, day: date, kcal: float) -> None:
    """Log a made-up food of the given kcal on a day."""
    records.add_meal_item(
        conn,
        user_id,
        consumed_on=day,
        meal="lunch",
        fdc_id=1,
        food_name="Made-up food",
        grams=100.0,
        kcal=kcal,
        protein_g=30.0,
        carbohydrate_g=50.0,
        fat_g=10.0,
        fiber_g=5.0,
    )


def _gymer_with_week(conn, user_id: str, name: str) -> None:
    """Store a made-up gymer with a profile, target and weight today, and three logged days."""
    users.create_user(conn, user_id, "gymer", name)
    records.add_body_measurement(conn, user_id, weight_kg=80.0, measured_on=MONDAY - timedelta(7))
    account.save_profile(conn, user_id, PROFILE, with_weight=True)
    for offset, kcal in ((0, 2000.0), (1, 2200.0), (3, 2400.0)):
        _meal(conn, user_id, MONDAY + timedelta(offset), kcal)
    records.add_workout_session(
        conn,
        user_id,
        performed_on=MONDAY + timedelta(1),
        sets=[records.ExerciseSet("squat", 1, 5, 100.0)],
    )


def _pair(conn, coach: str, client: str, scopes=()) -> int:
    """Start a relationship with the given scopes on; return its ID."""
    found = users.start_relationship(conn, coach, client)
    for scope in scopes:
        users.set_consent(conn, client, found, scope, True)
    return found


@pytest.fixture
def coach_world():
    """Store the canary coach with Alex (nutrition, body), Bo (training), Cy (ended), and Dee."""
    store_account("coach", name="Coach Sam")
    with db.connect() as conn:
        for user_id, name in ((ALEX, "Alex"), (BO, "Bo"), (CY, "Cy"), (DEE, "Dee")):
            _gymer_with_week(conn, user_id, name)
        users.create_user(conn, OTHER_COACH, "coach", "Coach Kai")
        _pair(conn, USER_ID, ALEX, ("nutrition", "body"))
        _pair(conn, USER_ID, BO, ("training",))
        ended = _pair(conn, USER_ID, CY, ("nutrition", "body", "training"))
        users.end_relationship(conn, CY, ended)
        _pair(conn, OTHER_COACH, DEE, ("nutrition", "body", "training"))


def _audit_subjects() -> set[str]:
    """Return every user an audit row is about."""
    with db.connect() as conn:
        return {row["subject_id"] for row in conn.execute("SELECT subject_id FROM audit_log")}


def _clients(monkeypatch, language: str = "en") -> AppTest:
    """Open the Clients page as the canary coach."""
    return open_page(start(monkeypatch, user=signed_in(), language=language), navigation.CLIENTS)


# --- The Clients page: criteria 1, 2 and 7 -------------------------------------------------------


def test_one_row_per_active_client_with_this_week_s_values(monkeypatch, coach_world):
    """Criterion 1: name, days logged, kcal against target, sessions, weight, review; not shared."""
    at = _clients(monkeypatch)
    table = at.get_by_key(clients.TABLE_KEY).dataframe[0].value
    assert list(table["Client"]) == ["Alex", "Bo"]  # never Cy (ended) or Dee (another coach's)
    assert list(table["Days logged"]) == ["3 of 7 days logged", "Not shared"]
    assert table["Avg kcal / target"][0].startswith("2,200 / ")
    assert list(table["Sessions"]) == ["Not shared", "1"]
    assert list(table["Latest weight"]) == [f"{PROFILE.weight_kg:g} kg (2026-10-29)", "Not shared"]
    assert list(table["Weekly review"]) == ["None", "Not shared"]
    assert "This week, 2026-10-26 to 2026-11-01." in texts(at)


def test_the_cards_hold_the_same_clients_and_values_as_the_table(monkeypatch, coach_world):
    """Criterion 2: both containers are drawn, a card per table row with the row's values."""
    at = _clients(monkeypatch)
    table = at.get_by_key(clients.TABLE_KEY).dataframe[0].value
    cards = [item.value for item in at.get_by_key(clients.CARDS_KEY).markdown]
    rows = [dict(zip(tables.CLIENT_COLUMNS, row, strict=True)) for row in table.values.tolist()]
    assert cards == [tables.client_card(row, "en") for row in rows]
    assert "**Sessions:** Not shared" in cards[0] and "**Days logged:** Not shared" in cards[1]


def test_a_former_client_shows_the_name_and_days_only(monkeypatch, coach_world):
    """An ended relationship is listed apart, with no value of the client's data."""
    at = _clients(monkeypatch)
    former = at.dataframe[1].value
    assert list(former.columns) == ["Client", "Since", "Ended"]
    assert list(former["Client"]) == ["Cy"]


def test_the_list_reads_no_former_or_foreign_client(monkeypatch, coach_world):
    """The coach's reads (audited) are about the active clients only."""
    _clients(monkeypatch)
    assert _audit_subjects() == {ALEX, BO}


def test_a_review_s_status_shows_in_the_list(monkeypatch, coach_world):
    """The latest review the coach wrote about a client shows its status and week."""
    with db.connect() as conn:
        _review(conn, USER_ID, ALEX, MONDAY - timedelta(7))
    table = _clients(monkeypatch).get_by_key(clients.TABLE_KEY).dataframe[0].value
    assert table["Weekly review"][0] == "Pending · week of 2026-10-19"


@pytest.mark.parametrize(
    ("language", "note"),
    [
        ("en", "The app does not check coaches' qualifications"),
        ("de", "Die App prüft die Qualifikationen von Coaches nicht"),
    ],
)
@pytest.mark.parametrize("page", [navigation.CLIENTS, navigation.CLIENT_WEEK])
def test_the_coach_s_pages_say_qualifications_are_not_checked(
    monkeypatch, coach_world, language, note, page
):
    """Criterion 7: Clients and Client week say the app does not check qualifications."""
    at = open_page(start(monkeypatch, user=signed_in(), language=language), page)
    assert note in texts(at)


def test_the_clients_page_in_german(monkeypatch, coach_world):
    """The list's headers and values follow the language."""
    table = _clients(monkeypatch, "de").get_by_key(clients.TABLE_KEY).dataframe[0].value
    assert list(table["Erfasste Tage"]) == ["3 von 7 Tagen erfasst", "Nicht geteilt"]


def test_a_client_picked_on_clients_opens_on_the_client_week_page(monkeypatch, coach_world):
    """Picking a client keeps the pick; the link goes to Client week, which shows their week."""
    at = _clients(monkeypatch)
    at.selectbox(key=clients.OPEN_KEY).set_value(ALEX).run(timeout=30)
    [link] = [item for item in at.get("page_link") if item.proto.label == "Open the week"]
    assert link.proto.page_script_hash == calc_hash(navigation.CLIENT_WEEK)
    # AppTest cannot click a link; opening the page is what the link does.
    at = open_page(at, navigation.CLIENT_WEEK)
    assert at.selectbox(key=client_week.PICK_KEY).value == ALEX
    assert "3 of 7 days logged" in texts(at)


def test_the_clients_picker_shows_the_client_the_link_opens(monkeypatch, coach_world):
    """Back on Clients, the picker shows the client picked on Client week (round 1)."""
    at = open_page(start(monkeypatch, user=signed_in()), navigation.CLIENT_WEEK)
    at.selectbox(key=client_week.PICK_KEY).set_value(BO).run(timeout=30)
    at = open_page(at, navigation.CLIENTS)
    assert at.selectbox(key=clients.OPEN_KEY).value == BO
    # Streamlit's "default value and Session State" warning (the header's box is a warning too).
    assert not [item for item in at.warning if "Session State" in str(item.value)]


# --- The Client week page: criteria 3 and 6 ------------------------------------------------------


def _client_week(monkeypatch, chosen: str | None = None, params: dict | None = None) -> AppTest:
    """Open the Client week page with query parameters, and pick a client if one is given."""
    at = start(monkeypatch, user=signed_in())
    for name, value in (params or {}).items():
        at.query_params[name] = value
    at = open_page(at, navigation.CLIENT_WEEK)
    if chosen is not None:
        at.selectbox(key=client_week.PICK_KEY).set_value(chosen).run(timeout=30)
    return at


def test_the_picker_offers_the_active_clients_only(monkeypatch, coach_world):
    """Criterion 6: the picker lists Alex and Bo, never the former or another coach's client."""
    at = _client_week(monkeypatch)
    assert at.selectbox(key=client_week.PICK_KEY).options == ["Alex", "Bo"]
    assert at.selectbox(key=client_week.PICK_KEY).value is None


@pytest.mark.parametrize("other", [CY, DEE, OTHER_COACH, "no-such-user"])
@pytest.mark.parametrize("name", ["client", "client_id", "id", "user", "subject", "pick"])
def test_no_query_parameter_opens_someone_else_s_week(monkeypatch, coach_world, name, other):
    """AC-21: a URL naming a former, foreign or unknown user shows nobody's data and reads none."""
    at = _client_week(monkeypatch, params={name: other})
    assert at.selectbox(key=client_week.PICK_KEY).value is None
    assert "days logged" not in texts(at)
    assert not at.get("vega_lite_chart")
    assert _audit_subjects() == set()


@pytest.mark.parametrize("other", [CY, DEE])
def test_a_forged_pick_in_the_session_is_dropped(monkeypatch, coach_world, other):
    """AC-21: a kept pick that is not an active client is dropped before anything is read."""
    at = start(monkeypatch, user=signed_in())
    at.session_state[client_week.CLIENT_KEY] = other
    at = open_page(at, navigation.CLIENT_WEEK)
    assert at.selectbox(key=client_week.PICK_KEY).value is None
    assert _audit_subjects() == set()


def test_a_client_s_week_has_the_charts_of_what_they_share(monkeypatch, coach_world):
    """Criterion 3: kcal per day, macros and the weight trend; training says not shared."""
    at = _client_week(monkeypatch, chosen=ALEX)
    page = texts(at)
    assert "3 of 7 days logged" in page
    assert "Not shared with you." in page  # training
    charts = at.get("vega_lite_chart")
    assert len(charts) == 3
    assert "Wed 28 not logged" in charts[0].proto.alt
    assert _audit_subjects() == {ALEX}


def test_a_training_client_s_week_has_the_volume_chart(monkeypatch, coach_world):
    """Training shared: the week's facts, the volume per day and the exercise table."""
    at = _client_week(monkeypatch, chosen=BO)
    assert "Sessions: 1" in texts(at)
    [volume] = at.get("vega_lite_chart")
    assert "Tue 27 500 kg" in volume.proto.alt
    assert texts(at).count("Not shared with you.") == 2


def test_the_week_picker_moves_the_charts_to_that_week(monkeypatch, coach_world):
    """Criterion 3: a day of another week shows that week, Monday to Sunday."""
    at = _client_week(monkeypatch, chosen=ALEX)
    at.date_input(key=client_week.WEEK_KEY).set_value(date(2026, 10, 21)).run(timeout=30)
    page = texts(at)
    assert "2026-10-19 to 2026-10-25" in page
    assert "0 of 7 days logged" in page


def test_a_relationship_ended_after_the_pick_shows_nothing(monkeypatch, coach_world):
    """AC-21: once the client ends the relationship, the next run reads nothing of theirs."""
    at = _client_week(monkeypatch, chosen=ALEX)
    with db.connect() as conn:
        [relationship] = [
            row for row in users.list_relationships(conn, ALEX) if row["status"] == "active"
        ]
        users.end_relationship(conn, ALEX, relationship["id"])
        conn.execute("DELETE FROM audit_log")
    at.run(timeout=30)
    assert at.selectbox(key=client_week.PICK_KEY).options == ["Bo"]
    assert "days logged" not in texts(at)
    assert _audit_subjects() == set()


def test_a_coach_with_no_active_client_is_told_how_to_get_one(monkeypatch):
    """No active client: a line points to the Clients page, and nothing else is drawn."""
    store_account("coach")
    at = open_page(start(monkeypatch, user=signed_in()), navigation.CLIENT_WEEK)
    assert "You have no active clients" in texts(at)
    assert not at.selectbox


# --- The gymer's My week: criteria 4 and 5 -------------------------------------------------------


def _review(conn, coach: str, client: str, monday: date, decision=None, final=None) -> int:
    """Save a made-up review and decide it as asked (None leaves it pending)."""
    found = reviews.save_review(
        conn,
        coach,
        client,
        period_start=monday,
        metrics={"logged_days": 3},
        data_quality={"logged_days": 3},
        draft={"observations": [f"Draft of {monday.isoformat()}."]},
        model_version="test-model",
    )
    if decision is not None:
        reviews.decide_review(conn, coach, found, decision, final)
    return found


@pytest.fixture
def gymer_world():
    """Store the canary gymer with a week of records, a coach and reviews of every status."""
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        for offset, kcal in ((0, 2000.0), (2, 2100.0)):
            _meal(conn, USER_ID, MONDAY + timedelta(offset), kcal)
        users.create_user(conn, OTHER_COACH, "coach", "Coach Kai")
        _pair(conn, OTHER_COACH, USER_ID, ("nutrition",))
        _review(conn, OTHER_COACH, USER_ID, date(2026, 10, 5), "approve")
        _review(
            conn,
            OTHER_COACH,
            USER_ID,
            date(2026, 10, 12),
            "edit",
            {"observations": ["Edited by the coach."]},
        )
        _review(conn, OTHER_COACH, USER_ID, date(2026, 10, 19), "reject")
        _review(conn, OTHER_COACH, USER_ID, MONDAY)  # pending


def _my_week(monkeypatch, language: str = "en") -> AppTest:
    """Open My week as the canary gymer."""
    return open_page(start(monkeypatch, user=signed_in(), language=language), navigation.MY_WEEK)


def test_my_week_shows_the_gymer_s_own_week(monkeypatch, gymer_world):
    """Criterion 4: the same views of the gymer's own data, every scope."""
    at = _my_week(monkeypatch)
    page = texts(at)
    assert "2 of 7 days logged" in page
    assert "worked out from the profile" in page
    assert "Not shared with you." not in page
    assert len(at.get("vega_lite_chart")) == 3  # kcal, macros, weight; no workout this week


def test_only_approved_reviews_show_each_labelled_as_an_ai_draft(monkeypatch, gymer_world):
    """AC-41: the approved and edited reviews show with their label; pending or rejected never."""
    at = _my_week(monkeypatch)
    page = texts(at)
    assert "Week of 2026-10-12" in page and "Week of 2026-10-05" in page
    assert "Week of 2026-10-19" not in page and "Week of 2026-10-26" not in page
    assert "Edited by the coach." in page
    assert "Draft of 2026-10-12" not in page  # the model's text the coach replaced
    captions = [item.value for item in at.caption]
    assert any("AI draft, edited and approved by the coach" in text for text in captions)
    assert any(text.endswith("AI draft, approved by the coach") for text in captions)


def test_the_review_label_in_german(monkeypatch, gymer_world):
    """AC-41 in German."""
    at = _my_week(monkeypatch, "de")
    assert any("KI-Entwurf, vom Coach freigegeben" in item.value for item in at.caption)


@pytest.mark.parametrize(("language", "yours"), [("en", "your coach"), ("de", "hr Coach")])
def test_a_former_coach_s_review_is_not_credited_to_the_new_coach(monkeypatch, language, yours):
    """A review approved by a coach the gymer has left reads "the coach", not "your coach"."""
    # Compliance run 1, finding 1 (code review round 2: the whole page, the intro included): the
    # gymer's approved reviews include a former coach's. "hr Coach" is "Ihr"/"Ihrem Coach".
    store_account("gymer", profile=PROFILE)
    with db.connect() as conn:
        users.create_user(conn, OTHER_COACH, "coach", "Coach Kai")
        users.create_user(conn, "coach-lee", "coach", "Coach Lee")
        former = _pair(conn, OTHER_COACH, USER_ID, ("nutrition",))
        _review(conn, OTHER_COACH, USER_ID, date(2026, 10, 12), "approve")
        users.end_relationship(conn, USER_ID, former)
        _pair(conn, "coach-lee", USER_ID, ("nutrition",))
    at = _my_week(monkeypatch, language)
    label = {"en": "AI draft, approved by the coach", "de": "KI-Entwurf, vom Coach freigegeben"}
    assert {"en": "Weekly reviews", "de": "Wochenberichte"}[language] in [
        item.value for item in at.subheader
    ]
    assert "2026-10-12" in texts(at)
    assert any(item.value.endswith(label[language]) for item in at.caption)
    assert yours not in texts(at)


def test_my_week_has_no_chat_and_no_control_but_the_week(monkeypatch, gymer_world):
    """Criterion 4: no chat, and no button, field or box to edit, decide or delete anything."""
    at = _my_week(monkeypatch)
    main = at.main
    assert not at.chat_input
    assert [item.key for item in main.date_input] == [my_week.WEEK_KEY]
    for kind in (
        "button",
        "checkbox",
        "text_input",
        "text_area",
        "number_input",
        "selectbox",
        "radio",
        "toggle",
        "segmented_control",
        "download_button",
        "form",
    ):
        assert not main.get(kind), kind


def test_a_gymer_with_no_approved_review_is_told_so(monkeypatch):
    """No approved review yet: a line says so."""
    store_account("gymer", profile=PROFILE)
    at = _my_week(monkeypatch)
    assert "No approved weekly review yet." in texts(at)


# --- T9.17: the follow-up flag in the client list ----------------------------------------------


def test_the_list_flags_a_client_for_follow_up(monkeypatch, coach_world):
    """Alex logged 3 days (fewer than 4): flagged; Bo shares training only and trained: not."""
    at = _clients(monkeypatch)
    table = at.get_by_key(clients.TABLE_KEY).dataframe[0].value
    assert list(table["Follow up"]) == ["Yes: few days logged", "No"]
    cards = [item.value for item in at.get_by_key(clients.CARDS_KEY).markdown]
    assert r"**Follow up:** Yes\: few days logged" in cards[0]


def test_the_follow_up_flag_in_german(monkeypatch, coach_world):
    """The column and its values are German when German is chosen."""
    at = _clients(monkeypatch, language="de")
    table = at.get_by_key(clients.TABLE_KEY).dataframe[0].value
    assert list(table["Nachfassen"]) == ["Ja: wenige Tage erfasst", "Nein"]
