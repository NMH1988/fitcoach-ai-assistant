"""Invitations, accepting a code and the daily limit on tries (T9.12, D15, AC-20, AC-22)."""

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from src import config
from src.store import db, invitations, records, users
from src.store.access import NotFound
from src.store.values import StoreValueError
from tests import store_world as world

# A fixed moment, so expiry and the day in Berlin are known: 2026-11-03 10:00 UTC.
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
NEWCOMER = "gym-new"  # a gymer with no coach


@pytest.fixture
def clock(monkeypatch):
    """Fix the store's clock at NOW and return a list whose one item a test may move."""
    moment = [NOW]
    monkeypatch.setattr(invitations, "_now", lambda: moment[0])
    return moment


@pytest.fixture
def relationships(store_conn, clock):
    """Build the made-up world, add a gymer with no coach, and return the relationship IDs."""
    found = world.build(store_conn)
    users.create_user(store_conn, NEWCOMER, "gymer", "Newcomer")
    return found


def _relationships(conn, gymer):
    """Return a gymer's relationships as (coach, status) pairs."""
    rows = conn.execute(
        "SELECT coach_id, status FROM coach_clients WHERE client_id = ? ORDER BY id", (gymer,)
    )
    return [(row["coach_id"], row["status"]) for row in rows]


def _attempts(conn, gymer):
    """Return the gymer's counted tries by day."""
    rows = conn.execute("SELECT day, count FROM invite_attempts WHERE user_id = ?", (gymer,))
    return {row["day"]: row["count"] for row in rows}


# --- Creating and cancelling (D15) ------------------------------------------------------------


def test_a_code_is_random_shown_once_and_stored_only_as_its_hash(store_conn, relationships):
    """The code has the configured length and alphabet; only its SHA-256 hash is in the file."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    code = new.code.replace("-", "")
    assert len(code) == config.INVITE_CODE_LENGTH
    assert set(code) <= set(config.INVITE_CODE_ALPHABET)
    assert new.code.count("-") == config.INVITE_CODE_LENGTH // config.INVITE_CODE_GROUP - 1
    [row] = [dict(r) for r in store_conn.execute("SELECT * FROM invitations")]
    assert row["code_hash"] == hashlib.sha256(code.encode()).hexdigest()
    assert code not in str(row) and new.code not in str(row)
    # The listing never holds the code either.
    assert new.code not in str(invitations.list_invitations(store_conn, world.COACH_A))


def test_the_code_comes_from_the_secrets_module(store_conn, relationships, monkeypatch):
    """Every character is drawn with secrets.choice, never with the random module."""
    calls = []

    def choice(alphabet):
        """Record the call and return the alphabet's first character."""
        calls.append(alphabet)
        return alphabet[0]

    monkeypatch.setattr(invitations.secrets, "choice", choice)
    new = invitations.create_invitation(store_conn, world.COACH_A)
    assert calls == [config.INVITE_CODE_ALPHABET] * config.INVITE_CODE_LENGTH
    assert new.code.replace("-", "") == "A" * config.INVITE_CODE_LENGTH


def test_two_codes_differ(store_conn, relationships):
    """Each invitation gets its own code."""
    first = invitations.create_invitation(store_conn, world.COACH_A)
    second = invitations.create_invitation(store_conn, world.COACH_A)
    assert first.code != second.code


def test_a_code_expires_after_the_configured_days(store_conn, relationships):
    """The expiry is creation time plus INVITE_TTL_DAYS, in UTC."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    expected = NOW + timedelta(days=config.INVITE_TTL_DAYS)
    assert datetime.fromisoformat(new.expires_at) == expected
    [listed] = invitations.list_invitations(store_conn, world.COACH_A)
    assert listed["expires_at"] == new.expires_at
    assert listed["expired"] is False


@pytest.mark.parametrize("actor", [world.SHARED, world.MISSING])
def test_only_a_coach_creates_or_lists_codes(store_conn, relationships, actor):
    """A gymer or a missing user gets NotFound and nothing is written."""
    with pytest.raises(NotFound):
        invitations.create_invitation(store_conn, actor)
    with pytest.raises(NotFound):
        invitations.list_invitations(store_conn, actor)
    assert store_conn.execute("SELECT count(*) FROM invitations").fetchone()[0] == 0


def test_a_coach_lists_only_their_own_unused_codes(store_conn, relationships):
    """Coach B's codes and a used code are not in coach A's list."""
    mine = invitations.create_invitation(store_conn, world.COACH_A)
    used = invitations.create_invitation(store_conn, world.COACH_A)
    invitations.create_invitation(store_conn, world.COACH_B)
    invitations.accept_invitation(store_conn, NEWCOMER, used.code, [])
    assert [row["id"] for row in invitations.list_invitations(store_conn, world.COACH_A)] == [
        mine.id
    ]


def test_the_coach_cancels_a_code_and_it_can_no_longer_be_accepted(store_conn, relationships):
    """A cancelled code is deleted; entering it gets the one refusal."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    invitations.cancel_invitation(store_conn, world.COACH_A, new.id)
    assert invitations.list_invitations(store_conn, world.COACH_A) == []
    with pytest.raises(invitations.InvitationRefused) as refused:
        invitations.accept_invitation(store_conn, NEWCOMER, new.code, [])
    assert refused.value.reason == "not_valid"


def test_only_the_owner_cancels_an_unused_code(store_conn, relationships):
    """Another coach, a gymer, a missing ID and a used code all give NotFound."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    for actor in (world.COACH_B, NEWCOMER, world.MISSING):
        with pytest.raises(NotFound):
            invitations.cancel_invitation(store_conn, actor, new.id)
    for missing in (999, None, "1", True, 0):
        with pytest.raises(NotFound):
            invitations.cancel_invitation(store_conn, world.COACH_A, missing)
    invitations.accept_invitation(store_conn, NEWCOMER, new.code, [])
    with pytest.raises(NotFound):
        invitations.cancel_invitation(store_conn, world.COACH_A, new.id)


# --- Accepting (AC-20) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scopes", [(), ("body",), ("nutrition", "training"), ("nutrition", "training", "body")]
)
def test_a_valid_code_starts_an_active_relationship_with_the_chosen_scopes(
    store_conn, relationships, scopes
):
    """The gymer's choice decides what is shared; the code is marked used."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    relationship = invitations.accept_invitation(store_conn, NEWCOMER, new.code, scopes)
    assert _relationships(store_conn, NEWCOMER) == [(world.COACH_A, "active")]
    [mine] = users.list_relationships(store_conn, NEWCOMER)
    assert mine["id"] == relationship
    assert set(mine["scopes"]) == set(scopes)
    used_at = store_conn.execute("SELECT used_at FROM invitations").fetchone()[0]
    assert used_at == NOW.isoformat()
    # The coach reads a shared scope at once, and an unshared one is refused (D16).
    if "body" in scopes:
        assert records.list_body_measurements(store_conn, world.COACH_A, NEWCOMER) == []
    else:
        with pytest.raises(NotFound):
            records.list_body_measurements(store_conn, world.COACH_A, NEWCOMER)


@pytest.mark.parametrize(
    "typed",
    [
        lambda code: code,
        lambda code: code.lower(),
        lambda code: code.replace("-", ""),
        lambda code: " " + code.replace("-", " ") + " ",
    ],
)
def test_a_code_is_accepted_with_or_without_hyphens_and_in_either_case(
    store_conn, relationships, typed
):
    """Hyphens, spaces and lower case do not matter."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    invitations.accept_invitation(store_conn, NEWCOMER, typed(new.code), ["body"])
    assert _relationships(store_conn, NEWCOMER) == [(world.COACH_A, "active")]


def _expired(conn, clock):
    """Return a code whose expiry has passed."""
    new = invitations.create_invitation(conn, world.COACH_A)
    clock[0] = NOW + timedelta(days=config.INVITE_TTL_DAYS, seconds=1)
    return new.code


def _used(conn, clock):
    """Return a code another gymer has accepted."""
    new = invitations.create_invitation(conn, world.COACH_A)
    users.create_user(conn, "gym-first", "gymer", "First")
    invitations.accept_invitation(conn, "gym-first", new.code, [])
    return new.code


def _cancelled(conn, clock):
    """Return a code the coach cancelled."""
    new = invitations.create_invitation(conn, world.COACH_A)
    invitations.cancel_invitation(conn, world.COACH_A, new.id)
    return new.code


def _wrong(conn, clock):
    """Return a well-formed code that was never created."""
    invitations.create_invitation(conn, world.COACH_A)
    return "ABCD-EFGH-JKLM"


REFUSED_CODES = {
    "expired": _expired,
    "used": _used,
    "cancelled": _cancelled,
    "never created": _wrong,
    "malformed": lambda conn, clock: "not a code",
    "too long": lambda conn, clock: "A" * (config.INVITE_CODE_INPUT_MAX_CHARS + 1),
    "not text": lambda conn, clock: 123,
}


@pytest.mark.parametrize("case", REFUSED_CODES)
def test_an_invalid_used_or_expired_code_gets_one_refusal(store_conn, relationships, clock, case):
    """Every bad code gives the same refusal, with the same message, and starts nothing."""
    code = REFUSED_CODES[case](store_conn, clock)
    with pytest.raises(invitations.InvitationRefused) as refused:
        invitations.accept_invitation(store_conn, NEWCOMER, code, ["body"])
    assert refused.value.reason == "not_valid"
    assert str(refused.value) == "not_valid"
    assert _relationships(store_conn, NEWCOMER) == []


def test_a_code_is_still_valid_until_its_expiry(store_conn, relationships, clock):
    """One second before the expiry the code works."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    clock[0] = NOW + timedelta(days=config.INVITE_TTL_DAYS, seconds=-1)
    invitations.accept_invitation(store_conn, NEWCOMER, new.code, [])
    assert _relationships(store_conn, NEWCOMER) == [(world.COACH_A, "active")]


def test_a_gymer_with_a_coach_cannot_accept_another_code(store_conn, relationships):
    """One coach at a time: the code stays unused and the gymer keeps their coach."""
    new = invitations.create_invitation(store_conn, world.COACH_B)
    with pytest.raises(invitations.InvitationRefused) as refused:
        invitations.accept_invitation(store_conn, world.SHARED, new.code, ["body"])
    assert refused.value.reason == "has_coach"
    assert _relationships(store_conn, world.SHARED) == [(world.COACH_A, "active")]
    assert [row["id"] for row in invitations.list_invitations(store_conn, world.COACH_B)] == [
        new.id
    ]


def test_after_ending_a_relationship_the_gymer_accepts_a_new_coach(store_conn, relationships):
    """The ended client of coach A takes coach B's code."""
    new = invitations.create_invitation(store_conn, world.COACH_B)
    invitations.accept_invitation(store_conn, world.ENDED, new.code, ["nutrition"])
    assert _relationships(store_conn, world.ENDED) == [
        (world.COACH_A, "ended"),
        (world.COACH_B, "active"),
    ]


@pytest.mark.parametrize("actor", [world.COACH_B, world.MISSING])
def test_only_a_gymer_accepts_a_code(store_conn, relationships, actor):
    """A coach or a missing user gets NotFound; nothing is counted or started."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    with pytest.raises(NotFound):
        invitations.accept_invitation(store_conn, actor, new.code, [])
    assert store_conn.execute("SELECT count(*) FROM invite_attempts").fetchone()[0] == 0


@pytest.mark.parametrize("scopes", [["preferences"], ["body", "everything"], [None]])
def test_an_unknown_scope_is_refused_before_anything_is_written(store_conn, relationships, scopes):
    """A scope outside the three is refused, and the try is not even counted."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    with pytest.raises(StoreValueError):
        invitations.accept_invitation(store_conn, NEWCOMER, new.code, scopes)
    assert _attempts(store_conn, NEWCOMER) == {}
    assert _relationships(store_conn, NEWCOMER) == []


def test_users_start_relationship_keeps_one_coach_per_gymer(store_conn, relationships):
    """The low-level step refuses a second coach and the same pair twice."""
    for coach in (world.COACH_B, world.COACH_A):
        with pytest.raises(StoreValueError, match="the gymer has a coach already"):
            users.start_relationship(store_conn, coach, world.SHARED)


# --- The daily limit on tries -------------------------------------------------------------------


def test_every_try_counts_and_the_limit_refuses_even_a_valid_code(store_conn, relationships):
    """After INVITE_MAX_ATTEMPTS tries in a day, a valid code is refused with "limit"."""
    for _ in range(config.INVITE_MAX_ATTEMPTS):
        with pytest.raises(invitations.InvitationRefused):
            invitations.accept_invitation(store_conn, NEWCOMER, "ABCD-EFGH-JKLM", [])
    good = invitations.create_invitation(store_conn, world.COACH_A)
    with pytest.raises(invitations.InvitationRefused) as refused:
        invitations.accept_invitation(store_conn, NEWCOMER, good.code, [])
    assert refused.value.reason == "limit"
    assert _relationships(store_conn, NEWCOMER) == []
    assert _attempts(store_conn, NEWCOMER) == {"2026-11-03": config.INVITE_MAX_ATTEMPTS}


def test_a_valid_try_counts_too(store_conn, relationships):
    """An accepted code is one of the day's tries."""
    new = invitations.create_invitation(store_conn, world.COACH_A)
    invitations.accept_invitation(store_conn, NEWCOMER, new.code, [])
    assert _attempts(store_conn, NEWCOMER) == {"2026-11-03": 1}


def test_the_count_survives_a_new_connection(relationships, store_conn):
    """The tries are in the store, so a reload (a new connection, a new session) keeps them."""
    for _ in range(config.INVITE_MAX_ATTEMPTS):
        with pytest.raises(invitations.InvitationRefused):
            invitations.accept_invitation(store_conn, NEWCOMER, "ABCD-EFGH-JKLM", [])
    with db.connect() as fresh:
        with pytest.raises(invitations.InvitationRefused) as refused:
            invitations.accept_invitation(fresh, NEWCOMER, "ABCD-EFGH-JKLM", [])
    assert refused.value.reason == "limit"


def test_the_limit_is_per_gymer_and_per_day_in_berlin(store_conn, relationships, clock):
    """Another gymer still has tries; the gymer gets new ones at midnight in Berlin."""
    for _ in range(config.INVITE_MAX_ATTEMPTS):
        with pytest.raises(invitations.InvitationRefused):
            invitations.accept_invitation(store_conn, NEWCOMER, "ABCD-EFGH-JKLM", [])
    with pytest.raises(invitations.InvitationRefused) as other:
        invitations.accept_invitation(store_conn, world.UNSHARED, "ABCD-EFGH-JKLM", [])
    assert other.value.reason == "has_coach"  # counted and checked, not limited
    # 22:59 UTC on 3 November is 23:59 in Berlin: still the same day.
    clock[0] = datetime(2026, 11, 3, 22, 59, tzinfo=UTC)
    with pytest.raises(invitations.InvitationRefused) as same_day:
        invitations.accept_invitation(store_conn, NEWCOMER, "ABCD-EFGH-JKLM", [])
    assert same_day.value.reason == "limit"
    # 23:00 UTC is midnight in Berlin: a new day.
    clock[0] = datetime(2026, 11, 3, 23, 0, tzinfo=UTC)
    new = invitations.create_invitation(store_conn, world.COACH_A)
    invitations.accept_invitation(store_conn, NEWCOMER, new.code, [])
    assert _attempts(store_conn, NEWCOMER) == {
        "2026-11-03": config.INVITE_MAX_ATTEMPTS,
        "2026-11-04": 1,
    }


def test_a_failed_accept_rolls_back_but_keeps_the_count(store_conn, relationships, monkeypatch):
    """An error after the code check starts nothing and leaves the code unused; the try counts."""
    new = invitations.create_invitation(store_conn, world.COACH_A)

    def broken(*args):
        """Fail like a full disk while the scope is granted."""
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(users, "_grant", broken)
    with pytest.raises(sqlite3.OperationalError):
        invitations.accept_invitation(store_conn, NEWCOMER, new.code, ["body"])
    assert _relationships(store_conn, NEWCOMER) == []
    assert len(invitations.list_invitations(store_conn, world.COACH_A)) == 1
    assert _attempts(store_conn, NEWCOMER) == {"2026-11-03": 1}
