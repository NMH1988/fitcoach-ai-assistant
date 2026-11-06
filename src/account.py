"""Signed-in users' accounts: the user ID, the display name, the profile they save (T9.5, D14).

The user ID is a keyed hash (HMAC-SHA256) of the Google account's issuer and `sub`, with a secret
from secrets.toml, so the store never holds the Google ID itself; the Google name, email and
picture are never read into it. The acting user always comes from the signed-in session (or a demo
user picked from a closed list, `src/demo.py`), never from a form, a URL or a model argument
(docs/SECURITY.md, known limits). `open_store()` is the only way the app opens the store: an error
there becomes `StoreUnavailable`, which the page shows as one fixed message, and a log line with the
error's class name only.
"""

import hashlib
import hmac
import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from src import config, guard, metrics
from src.profile import UserProfile
from src.store import db, records, users
from src.store.access import NotFound
from src.tools import registry

logger = logging.getLogger(__name__)

_NAME_PATTERN = re.compile(config.DISPLAY_NAME_PATTERN)


class AccountError(ValueError):
    """A display name or account that cannot be used; `code` is the i18n key of its message."""

    def __init__(self, code: str) -> None:
        """Keep the message's key (the message never holds the value)."""
        super().__init__(code)
        self.code = code


class StoreUnavailable(RuntimeError):
    """Raised when the store cannot be opened or used; the page shows one fixed message."""

    def __init__(self) -> None:
        """Give every case the one fixed text: an error's own text may name the file's path."""
        super().__init__("store unavailable")


def user_key(issuer: str, subject: str, secret: str) -> str:
    """Return the user ID: HMAC-SHA256 of the issuer and subject under the secret, in hex."""
    if not (isinstance(issuer, str) and issuer and isinstance(subject, str) and subject):
        raise AccountError("account.no_identity")
    if not isinstance(secret, str) or len(secret) < config.USER_KEY_SECRET_MIN_CHARS:
        raise AccountError("account.no_identity")
    # A newline cannot appear in an issuer URL, so ("a", "b\nc") and ("a\nb", "c") never collide.
    message = "\n".join((issuer, subject)).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def check_display_name(text: object) -> str:
    """Return the cleaned display name, or raise AccountError with the reason's i18n key."""
    if not isinstance(text, str):
        raise AccountError("account.name_length")
    # The input guard's cleaning (NFC, control and invisible characters removed, trimmed), then
    # one space between words, so a name cannot hide anything the pattern would not show.
    name = " ".join(guard.clean_input(text).split())
    low, high = config.DISPLAY_NAME_CHARS
    if not low <= len(name) <= high:
        raise AccountError("account.name_length")
    if not _NAME_PATTERN.fullmatch(name):
        raise AccountError("account.name_characters")
    if any(guard.looks_like_injection(view) for view in guard.detection_views(name)):
        raise AccountError("account.name_refused")
    return name


@contextmanager
def open_store(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the store for one unit of work; StoreUnavailable if it cannot be opened or used."""
    try:
        with db.connect(path) as conn:
            yield conn
    except (db.StoreError, sqlite3.Error) as exc:
        # The class name only: an error's text may name the file's path (T9.6).
        logger.warning("store_unavailable", extra={"code": type(exc).__name__})
        raise StoreUnavailable from None


def find_account(conn: sqlite3.Connection, user_id: str) -> dict | None:
    """Return the signed-in user's account (ID, role, display name); None at the first sign-in."""
    return users.find_user(conn, user_id)


def create_account(conn: sqlite3.Connection, user_id: str, role: str, display_name: str) -> None:
    """Store the account with its one role and a checked display name (AC-18)."""
    if role not in users.ROLES:
        raise AccountError("account.role_needed")
    name = check_display_name(display_name)
    if users.find_user(conn, user_id) is not None:
        # The role is chosen once: a second form (another tab) never changes it.
        raise AccountError("account.exists")
    try:
        users.create_user(conn, user_id, role, name)
    except sqlite3.IntegrityError:
        # Another tab created it between the check and the write: the same answer.
        raise AccountError("account.exists") from None


def today() -> date:
    """Return today's date in the app's time zone (D21), as the diary and metrics see it."""
    return metrics.berlin_day()


def has_profile_entries(conn: sqlite3.Connection, user_id: str) -> bool:
    """Return True if the gymer has saved a profile before (so they agreed to storing it then)."""
    try:
        return bool(records.list_profile_entries(conn, user_id, user_id))
    except NotFound:
        # The account was deleted in another tab since this session's last run.
        raise AccountError("account.gone") from None


def load_profile(conn: sqlite3.Connection, user_id: str) -> UserProfile | None:
    """Return a gymer's latest saved profile with their latest weight, or None if incomplete."""
    entries = records.list_profile_entries(conn, user_id, user_id)
    weights = records.list_body_measurements(conn, user_id, user_id)
    if not entries or not weights:
        return None
    entry, weight = entries[-1], weights[-1]
    return UserProfile(
        weight_kg=weight["weight_kg"],
        height_cm=entry["height_cm"],
        age=entry["age"],
        sex=entry["sex"],
        activity=entry["activity"],
        goal=entry["goal"],
    )


def save_profile(
    conn: sqlite3.Connection, user_id: str, profile: UserProfile, *, with_weight: bool
) -> bool:
    """Save a gymer's profile, weight (if asked) and new target; False: the coach's target kept."""
    # While the gymer shares nutrition with a coach and the latest target is a coach's, the store
    # writes no new target (T9.17, owner's choices, 2026-11-06), so the page can say it stays.
    # The target is worked out before anything is written, so a profile that gives no target
    # writes nothing; the three rows are one store transaction (T9.13), so a profile entry never
    # stays without its target.
    result = registry.macro_targets(profile)
    if not isinstance(result, registry.MacroToolResult) or result.status != "ok":
        raise AccountError("account.no_target")
    targets = result.targets
    try:
        return records.add_profile_with_target(
            conn,
            user_id,
            height_cm=profile.height_cm,
            age=profile.age,
            sex=profile.sex,
            activity=profile.activity,
            goal=profile.goal,
            weight_kg=profile.weight_kg if with_weight else None,
            kcal=targets.kcal_target,
            protein_g=targets.protein.grams,
            carbs_g=targets.carbohydrate.grams,
            fat_g=targets.fat.grams,
            set_by="system",
            calc_version=config.TARGET_CALC_VERSION,
            day=today(),
        )
    except NotFound:
        # The account was deleted in another tab since this session's last run (the store's
        # NotFound for a coach is not reached: the views save only a gymer's profile).
        raise AccountError("account.gone") from None
