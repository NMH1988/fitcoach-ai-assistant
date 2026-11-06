"""The coach assistant's client tools (T9.17): `list_my_clients` and `get_client_week`.

Offered only in a coach's chat. Both read through `src/dashboard.py`, so they give the numbers the
dashboards and the weekly review show (`src/metrics.py`), and every read of a client's records goes
through the store's checks and audit (`access.authorised_read()`): an active client, and only the
scopes they share. A client's metrics reach the model of the coach's chat only through these
results (PRD guardrails).

The model never gets a client's display name or stored user ID (a keyed hash of the Google
account): `list_my_clients` names each client by an opaque reference for this chat (`client-1`,
...), kept in the coach's session (`ClientRefs`) with the user ID it stands for, and
`get_client_week` maps a reference back through the session only. An unknown reference, a client
whose relationship ended, or anyone else gets the same "not found"; the store still checks access.
The coach's page shows the display name in place of a reference (`name_references()`). No review
text, question or answer is in a result: only the week's metrics.
"""

import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src import config, dashboard, metrics
from src.store.access import NotFound

LIST_TOOL = "list_my_clients"
WEEK_TOOL = "get_client_week"
REFERENCE_PREFIX = "client-"
# The longest reference a call may send; anything longer is refused as invalid.
REFERENCE_MAX_CHARS = 32

LIST_DESCRIPTION = (
    "List the coach's active clients with this week's logging (Monday to Sunday, Europe/Berlin "
    "time): for each client, an opaque reference for this chat (e.g. 'client-1'), the scopes the "
    "client shares with the coach (nutrition, training, body), the days with food logged out of 7 "
    "(null when nutrition is not shared), the workouts this week (null when training is not "
    "shared), and a follow-up flag with its reasons: fewer than "
    f"{config.FOLLOW_UP_MIN_LOGGED_DAYS} logged days, or no workout. Clients' names are never "
    "given: refer to a client only by their reference, exactly as written, and never guess a name. "
    "Takes no arguments."
)
WEEK_DESCRIPTION = (
    "One active client's week from the app's logs, only what the client shares with the coach: "
    "nutrition (each day's totals, or not logged; averages over the logged days only; the active "
    "daily target and the difference from it), body (the latest weight and the change from the "
    "week before) and training (sessions, sets, volume in kg and each exercise's sets, reps, "
    "volume and top weight). A day with nothing logged is 'not logged', never a day without "
    "eating. Takes the client's reference from list_my_clients in this chat and, optionally, "
    "week_of: any day of the week wanted (YYYY-MM-DD, not after today; this week if left out). An "
    "unknown reference, or a client who is no longer active, gives 'not found'."
)
LIST_MESSAGE = (
    "Your active clients this week, by reference. A null value is a scope the client does not "
    "share with you; it is unknown, not zero."
)
WEEK_MESSAGE = (
    "The client's week, by reference. A section that is null is a scope the client does not share "
    "with you; it is unknown, not zero. A day with nothing logged is not logged, not a day without "
    "eating."
)

# A client reference as the model may write it, any case. A preference that holds one is refused
# (src/preferences.py), as a reference names a client and stands for another in the next chat.
REFERENCE = re.compile(r"(?<![\w-])client-([1-9][0-9]*)(?![\w-])", re.IGNORECASE)


@dataclass
class ClientRefs:
    """The chat's client references: client-N to the user ID and display name, session only."""

    # In the order the clients were first listed; kept until "New chat" (clear()).
    by_reference: dict[str, tuple[str, str]] = field(default_factory=dict)

    def reference_for(self, user_id: str, name: str) -> str:
        """Return the client's reference in this chat, giving the next one to a new client."""
        for reference, (known, _) in self.by_reference.items():
            if known == user_id:
                self.by_reference[reference] = (user_id, name)
                return reference
        reference = f"{REFERENCE_PREFIX}{len(self.by_reference) + 1}"
        self.by_reference[reference] = (user_id, name)
        return reference

    def user_id(self, reference: str) -> str | None:
        """Return the user ID a reference stands for in this chat, or None."""
        found = self.by_reference.get(reference.strip().casefold())
        return None if found is None else found[0]

    def names(self) -> dict[str, str]:
        """Return each reference with the display name the coach's page shows for it."""
        return {reference: name for reference, (_, name) in self.by_reference.items()}

    def clear(self) -> None:
        """Forget every reference (a new chat)."""
        self.by_reference.clear()


@dataclass(frozen=True)
class CoachClients:
    """What the client tools need from the coach's session: the coach, the store, the references."""

    coach_id: str
    # Opens the store for one unit of work; the tools run in a worker thread, so each call opens
    # its own connection.
    open_store: Callable[[], AbstractContextManager[sqlite3.Connection]]
    refs: ClientRefs
    today: Callable[[], date] = metrics.berlin_day


class ClientSummary(BaseModel):
    """One active client in list_my_clients: the reference and this week's logging, no name."""

    client: str
    shared_scopes: list[str]
    logged_days: int | None
    days_in_week: int
    workouts: int | None
    follow_up: bool
    follow_up_reasons: list[str]


class ClientListResult(BaseModel):
    """list_my_clients' result: this week's dates and one summary per active client."""

    status: Literal["ok"]
    message: str
    week_start: date
    week_end: date
    follow_up_min_logged_days: int
    clients: list[ClientSummary]


class Nutrients(BaseModel):
    """Energy and macronutrients of a day, an average, a target or a difference (rounded)."""

    kcal: float
    protein_g: float
    carbohydrate_g: float
    fat_g: float


class DayLog(BaseModel):
    """One day of the week: its totals, or None when nothing was logged."""

    day: date
    logged: bool
    totals: Nutrients | None


class TargetOut(BaseModel):
    """The daily target active in the week, who set it and from when."""

    nutrients: Nutrients
    set_by: str
    effective_from: date


class NutritionOut(BaseModel):
    """The week's nutrition: days logged, each day, averages, target and difference."""

    logged_days: int
    days_in_week: int
    days: list[DayLog]
    average_over_logged_days: Nutrients | None
    target: TargetOut | None
    average_minus_target: Nutrients | None


class BodyOut(BaseModel):
    """The week's body figures: the latest weight up to Sunday and the change over the week."""

    latest_weight_kg: float | None
    latest_weight_on: date | None
    weight_change_kg: float | None


class ExerciseOut(BaseModel):
    """One exercise's week: sets, reps, volume (reps x kg) and the top weight of any set."""

    exercise_id: str
    sets: int
    reps: int
    volume_kg: float
    top_weight_kg: float


class TrainingOut(BaseModel):
    """The week's training facts."""

    sessions: int
    sets: int
    volume_kg: float
    exercises: list[ExerciseOut]


class ClientWeekResult(BaseModel):
    """get_client_week's result: one client's week by reference, the scopes shared only."""

    status: Literal["ok"]
    message: str
    client: str
    week_start: date
    week_end: date
    shared_scopes: list[str]
    nutrition: NutritionOut | None
    body: BodyOut | None
    training: TrainingOut | None
    follow_up_reasons: list[str]


class ClientNotice(BaseModel):
    """A client tool's result without values: not found, an invalid call or a failure."""

    status: Literal["not_found", "invalid", "error"]
    message: str


class ClientWeekArgs(BaseModel):
    """get_client_week's arguments: the client's reference and, optionally, a day of the week."""

    model_config = ConfigDict(extra="forbid")

    client: str = Field(min_length=1, max_length=REFERENCE_MAX_CHARS)
    week_of: date | None = None


class _NoArgs(BaseModel):
    """list_my_clients' arguments: none, and any field the model sends is refused."""

    model_config = ConfigDict(extra="forbid")


def invalid_week_message(_: ValidationError) -> str:
    """Return the fixed message for get_client_week arguments that fail the schema."""
    return config.INVALID_CLIENT_WEEK_MESSAGE


def _not_found() -> ClientNotice:
    """Return the one "not found" every refused client gets (AC-21)."""
    return ClientNotice(status="not_found", message=config.CLIENT_NOT_FOUND_MESSAGE)


def _rounded(value: float | None) -> float | None:
    """Round a figure to one decimal for the model (None stays None)."""
    return None if value is None else round(value, 1)


def _nutrients(source: metrics.Intake | metrics.Target) -> Nutrients:
    """Return the energy and macros of an Intake or a Target, rounded."""
    return Nutrients(
        kcal=round(source.kcal, 1),
        protein_g=round(source.protein_g, 1),
        carbohydrate_g=round(source.carbohydrate_g, 1),
        fat_g=round(source.fat_g, 1),
    )


def _nutrition(found: metrics.WeekMetrics) -> NutritionOut:
    """Return the week's nutrition section from its metrics."""
    target = None
    if found.target is not None:
        target = TargetOut(
            nutrients=_nutrients(found.target),
            set_by=found.target.set_by,
            effective_from=found.target.effective_from,
        )
    difference = None
    if found.difference is not None:
        difference = Nutrients(
            **{name: round(value, 1) for name, value in found.difference.items()}
        )
    return NutritionOut(
        logged_days=found.logged_days,
        days_in_week=found.days_in_week,
        days=[
            DayLog(
                day=day,
                logged=totals is not None,
                totals=None if totals is None else _nutrients(totals),
            )
            for day, totals in found.days
        ],
        average_over_logged_days=None if found.average is None else _nutrients(found.average),
        target=target,
        average_minus_target=difference,
    )


def _body(week: dashboard.DashboardWeek) -> BodyOut:
    """Return the week's body section: the latest weight up to Sunday and the week's change."""
    latest = dashboard.latest_weight(week)
    return BodyOut(
        latest_weight_kg=None if latest is None else _rounded(latest[1]),
        latest_weight_on=None if latest is None else latest[0],
        weight_change_kg=_rounded(week.nutrition.weight_change_kg),
    )


def _training(found: metrics.TrainingWeek) -> TrainingOut:
    """Return the week's training section from its facts."""
    return TrainingOut(
        sessions=found.sessions,
        sets=found.sets,
        volume_kg=round(found.volume_kg, 1),
        exercises=[
            ExerciseOut(
                exercise_id=item.exercise_id,
                sets=item.sets,
                reps=item.reps,
                volume_kg=round(item.volume_kg, 1),
                top_weight_kg=round(item.top_weight_kg, 1),
            )
            for item in found.exercises
        ],
    )


def _shared(week: dashboard.DashboardWeek) -> list[str]:
    """Return the scopes read for the week, in the store's order."""
    return [scope for scope in ("nutrition", "training", "body") if scope in week.shared]


def week_result(reference: str, week: dashboard.DashboardWeek) -> ClientWeekResult:
    """Return get_client_week's result for one client's week, the scopes shared only."""
    shared = week.shared
    return ClientWeekResult(
        status="ok",
        message=WEEK_MESSAGE,
        client=reference,
        week_start=week.nutrition.week_start,
        week_end=week.nutrition.week_end,
        shared_scopes=_shared(week),
        nutrition=_nutrition(week.nutrition) if "nutrition" in shared else None,
        body=_body(week) if "body" in shared else None,
        training=None if week.training is None else _training(week.training),
        follow_up_reasons=list(dashboard.follow_up_reasons(week)),
    )


def summary(reference: str, week: dashboard.DashboardWeek) -> ClientSummary:
    """Return one client's line of list_my_clients from their week."""
    reasons = list(dashboard.follow_up_reasons(week))
    return ClientSummary(
        client=reference,
        shared_scopes=_shared(week),
        logged_days=week.nutrition.logged_days if "nutrition" in week.shared else None,
        days_in_week=week.nutrition.days_in_week,
        workouts=None if week.training is None else week.training.sessions,
        follow_up=bool(reasons),
        follow_up_reasons=reasons,
    )


def list_clients(clients: CoachClients) -> ClientListResult:
    """Return this week's summary of each of the coach's active clients, by reference."""
    monday = metrics.week_start(clients.today())
    with clients.open_store() as conn:
        summaries = []
        for relationship in dashboard.active_clients(conn, clients.coach_id):
            week = dashboard.relationship_week(conn, clients.coach_id, relationship, monday)
            reference = clients.refs.reference_for(
                relationship["other_id"], relationship["other_name"]
            )
            summaries.append(summary(reference, week))
    return ClientListResult(
        status="ok",
        message=LIST_MESSAGE,
        week_start=monday,
        week_end=metrics.week_days(monday)[-1],
        follow_up_min_logged_days=config.FOLLOW_UP_MIN_LOGGED_DAYS,
        clients=summaries,
    )


def client_week(
    clients: CoachClients, client: str, week_of: date | None = None
) -> ClientWeekResult | ClientNotice:
    """Return one client's week by reference; the same "not found" for anyone not readable."""
    user_id = clients.refs.user_id(client)
    if user_id is None:
        return _not_found()
    today = clients.today()
    day = today if week_of is None else week_of
    if day > today:
        return ClientNotice(status="invalid", message=config.INVALID_CLIENT_WEEK_MESSAGE)
    try:
        with clients.open_store() as conn:
            week = dashboard.client_week(conn, clients.coach_id, user_id, metrics.week_start(day))
    except NotFound:
        # Ended, never the coach's, or the account gone: the store's one answer (AC-21).
        return _not_found()
    return week_result(client.strip().casefold(), week)


def _not_run(**_: object) -> None:
    """Stand for a tool's function in the ToolNode's definitions: calls run through the registry."""
    raise RuntimeError("The client tools run through registry.run_tool_call().")


def tool_definitions() -> list[StructuredTool]:
    """Return both tools' names, descriptions and schemas, for the ToolNode (no session)."""
    return [
        StructuredTool.from_function(
            func=_not_run, name=LIST_TOOL, description=LIST_DESCRIPTION, args_schema=_NoArgs
        ),
        StructuredTool.from_function(
            func=_not_run, name=WEEK_TOOL, description=WEEK_DESCRIPTION, args_schema=ClientWeekArgs
        ),
    ]


def build_tools(
    clients: CoachClients, no_arguments_message: Callable[[ValidationError], str]
) -> dict[str, StructuredTool]:
    """Return both tools by name, bound to the coach's session; run them through the registry."""

    def list_my_clients() -> ClientListResult:
        """Return the coach's active clients this week, by reference."""
        return list_clients(clients)

    def get_client_week(client: str, week_of: date | None = None):
        """Return one client's week by reference, or "not found"."""
        return client_week(clients, client, week_of)

    return {
        LIST_TOOL: StructuredTool.from_function(
            func=list_my_clients,
            name=LIST_TOOL,
            description=LIST_DESCRIPTION,
            args_schema=_NoArgs,
            handle_validation_error=no_arguments_message,
        ),
        WEEK_TOOL: StructuredTool.from_function(
            func=get_client_week,
            name=WEEK_TOOL,
            description=WEEK_DESCRIPTION,
            args_schema=ClientWeekArgs,
            handle_validation_error=invalid_week_message,
        ),
    }


# A line that holds any of these may hold a link, a URL, an autolink or an e-mail address: every
# reference on it stays as written, so no name can end up in a link's target, whatever its
# Markdown form (inline, angle brackets, reference definitions, bare URLs). One simple rule instead
# of a pattern for each form (code review rounds 1-3; owner's rule for text heuristics). Two slashes
# alone, not "://", so a URL with no scheme (a reference definition's destination on its own line)
# counts too (round 3).
LINK_MARKERS: tuple[str, ...] = ("](", "]:", "<", "//", "www.", "@")


def name_references(text: str, names: Mapping[str, str], quote: Callable[[str], str]) -> str:
    """Return the text with each known reference replaced by the client's quoted name."""
    # Only the coach's page does this; the model and the conversation's memory keep the reference.

    def replace(match: re.Match[str]) -> str:
        """Return the client's quoted name, or the reference as written when it is unknown."""
        name = names.get(match.group(0).casefold())
        return match.group(0) if name is None else quote(name)

    lines = text.splitlines(keepends=True)
    return "".join(
        line
        if any(marker in line.casefold() for marker in LINK_MARKERS)
        else REFERENCE.sub(replace, line)
        for line in lines
    )
