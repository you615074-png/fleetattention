"""What a supervisor sees and returns. Everything here is visible to supervisors; ground truth stays in the simulator."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .layout import Cell

KINDS = ('obstacle', 'low_battery', 'scan_failure', 'deadlock')

# The autonomous actions a supervisor may choose per incident kind. Asking a person is always possible.
ACTIONS: dict[str, tuple[str, ...]] = {
    'obstacle': ('proceed', 'reroute', 'wait'),
    'low_battery': ('finish_task', 'charge_now'),
    'scan_failure': ('pick_anyway', 'rescan', 'skip'),
    'deadlock': ('yield', 'wait'),
}

SEVERITIES = ('critical', 'high', 'medium', 'low')


class Details(dict):
    """A read-only dict: what a supervisor is shown cannot be changed by it."""

    def _read_only(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError('observation details are read-only')

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _read_only  # type: ignore

    def __reduce__(self):
        return Details, (dict(self),)


@dataclass(frozen=True)
class Observation:
    """One incident as the robot reports it.

    `suggested` and `confidence` come from the robot's onboard model; how well the confidence is calibrated
    differs per kind, and learning that is part of the supervisor's job.
    `target` is the cell the incident is about: the obstacle's cell, the blocking robot's cell, or the robot's own
    cell. Incidents with the same kind and target usually share one cause.
    For obstacles, `details` has the classifier's `predicted` class, whether `motion` was detected, and `at_goal`:
    the obstacle stands on the pick face the robot is heading to, so it cannot be driven around.
    """
    incident: int
    kind: str
    time: int
    robot: int
    cell: Cell
    target: Cell
    human_zone: bool
    attempt: int
    suggested: str
    confidence: float
    actions: tuple[str, ...]
    details: Details = field(default_factory=Details)


@dataclass(frozen=True)
class Decision:
    type: Literal['act', 'ask', 'join']
    action: str | None = None
    question: int | None = None

    @staticmethod
    def act(action: str) -> Decision:
        return Decision('act', action=action)

    @staticmethod
    def ask() -> Decision:
        """Ask a person one question about this incident; the robot waits for the answer."""
        return Decision('ask')

    @staticmethod
    def join(question: int) -> Decision:
        """Attach this incident to a pending question of the same kind; the answer is applied to both."""
        return Decision('join', question=question)


@dataclass(frozen=True)
class PendingQuestion:
    id: int
    kind: str
    target: Cell
    incidents: tuple[int, ...]
    asked_at: int


@dataclass(frozen=True)
class Context:
    time: int
    pending: tuple[PendingQuestion, ...]
    human_queue: int
    """Questions and recoveries waiting for the person, including the one in progress."""


@dataclass(frozen=True)
class Answer:
    """What the person said: the autonomous action that was right for the question's incident.

    The person is right with the configured accuracy, so an answer can be wrong. `incident` is the incident the
    question was asked about; incidents joined to it get the same answer, which fits them only if they share its cause.
    """
    question: int
    correct_action: str
    incident: int


@dataclass(frozen=True)
class Outcome:
    """What became observable after an autonomous action.

    `ok` is True when the outcome confirmed the action (driving past what turned out to be a ghost, the item
    delivered was the right one), False when it showed the action was wrong, and None when nothing observable says
    either way (waiting, a detour, a charge, a task cancelled before it finished). `severity` is set for a miss.
    """
    action: str
    ok: bool | None
    severity: str | None = None
