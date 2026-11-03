"""Baseline supervisors and the reference supervisor.

A supervisor is any object with `name`, `reset`, `decide`, `on_answer` and `on_outcome`; subclass `Supervisor`
for no-op callbacks. It is reset at the start of every episode and learns only within that episode.
"""
from __future__ import annotations

import importlib
import math
import random

from .model import Answer, Context, Decision, Observation, Outcome

# The action that does no harm when unsure, per kind.
SAFE_DEFAULT = {'obstacle': 'wait', 'low_battery': 'charge_now', 'scan_failure': 'rescan', 'deadlock': 'yield'}


class Supervisor:
    name = 'supervisor'

    def reset(self, seed: int) -> None:
        pass

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        raise NotImplementedError

    def on_answer(self, obs: Observation, answer: Answer) -> None:
        pass

    def on_outcome(self, obs: Observation, outcome: Outcome) -> None:
        pass


class Threshold(Supervisor):
    """Follows the robot's suggestion when its confidence reaches `threshold`, otherwise asks."""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.name = f'threshold@{threshold:g}'

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        return Decision.act(obs.suggested) if obs.confidence >= self.threshold else Decision.ask()


class AlwaysAsk(Threshold):
    name = 'always_ask'

    def __init__(self) -> None:
        super().__init__(math.inf)
        self.name = 'always_ask'


class NeverAsk(Threshold):
    name = 'never_ask'

    def __init__(self) -> None:
        super().__init__(0.0)
        self.name = 'never_ask'


class AlwaysSafe(Supervisor):
    """Never asks and always takes the cautious action. With `obstacle='reroute'` it drives around every obstacle
    instead of waiting. A benchmark where this wins is one where caution costs nothing."""

    def __init__(self, obstacle: str = 'wait') -> None:
        self.actions = {**SAFE_DEFAULT, 'obstacle': obstacle}
        self.name = 'always_safe' if obstacle == 'wait' else f'always_safe_{obstacle}'

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        return Decision.act(self.actions[obs.kind])


class Patient(Supervisor):
    """Never asks. Like `always_safe_reroute`, but at an obstacle on the pick face it is heading to it waits `waits`
    times before giving the line up: people on a pick face usually leave."""

    def __init__(self, waits: int = 2) -> None:
        self.waits = waits
        self.name = 'patient' if waits == 2 else f'patient@{waits}'

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        if obs.kind == 'obstacle':
            return Decision.act('wait' if obs.details.get('at_goal') and obs.attempt <= self.waits else 'reroute')
        return Decision.act(SAFE_DEFAULT[obs.kind])


class CostAware(Supervisor):
    """A rule that asks only where caution is expensive: it drives around obstacles in the aisles and rescans once,
    but asks about an obstacle on the pick face and about a label that a rescan could not read. It charges early and
    resolves deadlocks alone."""
    name = 'cost_aware'

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        if obs.kind == 'obstacle':
            return Decision.ask() if obs.details.get('at_goal') else Decision.act('reroute')
        if obs.kind == 'scan_failure':
            return Decision.ask() if obs.attempt >= 2 else Decision.act('rescan')
        return Decision.act(SAFE_DEFAULT[obs.kind])


class MotionAware(CostAware):
    """`cost_aware`, but at an obstacle on the pick face with motion seen it waits (twice) instead of asking: what
    moves is most likely a person, who will leave."""
    name = 'motion_aware'

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        if obs.kind == 'obstacle' and obs.details.get('at_goal') and obs.details.get('motion') and obs.attempt <= 2:
            return Decision.act('wait')
        return super().decide(obs, ctx)


class Reference(Supervisor):
    """A supervisor built on the dsh-superagent principle: take as little human attention as possible.

    - Gate in code, not judgement (`gate`): an obstacle with motion or in the zone shared with people is never driven
      through, whatever the robot suggests; and (`auto_deadlock`) deadlocks are always resolved by yielding.
    - One question per cause (`join`): an incident with the same kind and target as a question asked less than
      `join_window` seconds ago joins it. The answer to a joined question is applied as given, so an obstacle the gate
      covers does not join (the answer could be `proceed`); it waits for the pending answer instead.
    - Shadow mode first: each kind is asked about until `calibration` answers show how far the robot's confidence can
      be trusted for that kind, then the supervisor acts alone above the learned threshold. With `per_kind` off, all
      kinds share one pool of samples and one target, `shared_target`. It learns only from the person's answers to its own questions and from outcomes
      that confirm or refute an action, never from joined answers or unverifiable outcomes.
    - Audits: a share `audit` of the incidents it would act on alone is treated as unsure instead, so a drifting
      calibration is noticed.
    - Escalation: an incident raised for the third time is asked about.
    - Attention budget (`busy_queue`): when the person already has that many jobs waiting, an unsure incident, audits
      included, takes the safe default instead of another question. None disables it.
    """
    name = 'reference'

    def __init__(self, calibration: int = 6, audit: float = .05, busy_queue: int | None = 3,
                 targets: dict[str, float] | None = None, per_kind: bool = True, shared_target: float = .95,
                 join: bool = True, join_window: int = 60, gate: bool = True, auto_deadlock: bool = True) -> None:
        self.calibration, self.audit, self.busy_queue = calibration, audit, busy_queue
        self.targets = targets or {'obstacle': .97, 'low_battery': .95, 'scan_failure': .95, 'deadlock': .9}
        self.per_kind, self.shared_target = per_kind, shared_target
        self.join, self.join_window, self.gate, self.auto_deadlock = join, join_window, gate, auto_deadlock

    def reset(self, seed: int) -> None:
        self.rng = random.Random(f'{seed}:reference')
        self.samples: dict[str, list[tuple[float, bool]]] = {kind: [] for kind in self.targets}
        self.reasons: dict[str, int] = {}
        """Why each question was asked or each safe default taken: for analysing the supervisor, not used by it."""

    def report(self) -> dict[str, int]:
        """Counters for the results: why it asked or fell back to the safe default."""
        return {f'reason_{reason}': count for reason, count in self.reasons.items()}

    def _note(self, reason: str, decision: Decision) -> Decision:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1
        return decision

    def decide(self, obs: Observation, ctx: Context) -> Decision:
        if self.auto_deadlock and obs.kind == 'deadlock':
            return Decision.act('yield')
        allowed = set(obs.actions)
        gated = self.gate and obs.kind == 'obstacle' and bool(obs.details.get('motion') or obs.human_zone)
        if gated:
            allowed.discard('proceed')
        if self.join:
            for question in ctx.pending:
                if question.kind == obs.kind and question.target == obs.target \
                        and ctx.time - question.asked_at < self.join_window:
                    return Decision.act('wait') if gated else self._note('joined', Decision.join(question.id))
        if obs.attempt >= 3:
            return self._note('escalation', Decision.ask())
        threshold = self.threshold(obs.kind)
        if threshold is None:
            return self._note('shadow', Decision.ask())
        if obs.confidence >= threshold and obs.suggested in allowed:
            if self.rng.random() >= self.audit:
                return Decision.act(obs.suggested)
            reason = 'audit'
        else:
            reason = 'never_trusted' if threshold == math.inf else 'below_threshold'
        if self.busy_queue is not None and ctx.human_queue >= self.busy_queue:
            return self._note(f'busy_default:{reason}', Decision.act(SAFE_DEFAULT[obs.kind]))
        return self._note(reason, Decision.ask())

    def _samples(self, kind: str) -> list[tuple[float, bool]]:
        return self.samples[kind] if self.per_kind else [s for samples in self.samples.values() for s in samples]

    def threshold(self, kind: str) -> float | None:
        """The lowest confidence at and above which the robot's suggestion met the target accuracy, or None while
        shadowing. Samples with equal confidence are taken together, so a cut never splits them."""
        samples = self._samples(kind)
        if len(samples) < self.calibration:
            return None
        ranked = sorted(samples, key=lambda s: -s[0])
        best, right = math.inf, 0
        for count, (confidence, correct) in enumerate(ranked, 1):
            right += correct
            last_of_group = count == len(ranked) or ranked[count][0] != confidence
            target = self.targets[kind] if self.per_kind else self.shared_target
            if last_of_group and count >= 3 and right / count >= target:
                best = confidence
        return best

    def on_answer(self, obs: Observation, answer: Answer) -> None:
        if answer.incident == obs.incident:
            self.samples[obs.kind].append((obs.confidence, obs.suggested == answer.correct_action))

    def on_outcome(self, obs: Observation, outcome: Outcome) -> None:
        if outcome.action == obs.suggested and outcome.ok is not None:
            self.samples[obs.kind].append((obs.confidence, outcome.ok))


ABLATIONS = {
    'per_kind': {'per_kind': False}, 'join': {'join': False}, 'gate': {'gate': False},
    'busy': {'busy_queue': None}, 'deadlock': {'auto_deadlock': False},
}


def by_name(name: str) -> Supervisor:
    """always_ask, never_ask, always_safe, always_safe_reroute, patient, cost_aware, motion_aware, threshold@<value>,
    patient@<waits>, reference,
    reference-<feature> for the reference supervisor without one feature (see ABLATIONS), or module:Class for a
    supervisor of your own."""
    if ':' in name:
        module, cls = name.split(':', 1)
        return getattr(importlib.import_module(module), cls)()
    if name.startswith('threshold@'):
        return Threshold(float(name.split('@', 1)[1]))
    if name.startswith('patient@'):
        return Patient(int(name.split('@', 1)[1]))
    if name.startswith('reference-') and name.split('-', 1)[1] in ABLATIONS:
        sup = Reference(**ABLATIONS[name.split('-', 1)[1]])
        sup.name = name
        return sup
    known = {'always_ask': AlwaysAsk, 'never_ask': NeverAsk, 'always_safe': AlwaysSafe,
             'always_safe_reroute': lambda: AlwaysSafe('reroute'), 'patient': Patient, 'cost_aware': CostAware,
             'motion_aware': MotionAware, 'reference': Reference}
    if name not in known:
        raise ValueError(f'unknown supervisor {name!r}; use {", ".join(known)}, threshold@<value>, patient@<waits>, '
                         f'reference-<{"|".join(ABLATIONS)}> or module:Class')
    return known[name]()
