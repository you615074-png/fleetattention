"""The simulator: robots, obstacles, the person, incidents and their ground truth.

One tick is one second. Each tick the person finishes answers, every robot takes one step, and the supervisor
decides on the incidents raised in that step. Ground truth (what an obstacle really is, how fast a battery really
drains, whether a scan guess is right) never leaves this module except through answers and observable outcomes.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field, fields, replace
from typing import Any, Protocol

from .layout import Cell, Layout, warehouse
from .model import ACTIONS, Answer, Context, Decision, Details, Observation, Outcome, PendingQuestion


class DecisionError(ValueError):
    """A supervisor returned a decision the rules do not allow."""


class Supervisor(Protocol):
    name: str

    def reset(self, seed: int) -> None: ...
    def decide(self, obs: Observation, ctx: Context) -> Decision: ...
    def on_answer(self, obs: Observation, answer: Answer) -> None: ...
    def on_outcome(self, obs: Observation, outcome: Outcome) -> None: ...


@dataclass(frozen=True)
class Config:
    """The rates, accuracies and durations of the simulation. The harm weights and cost profiles are in `metrics`; the
    shapes of the classifier's confidence distributions are fixed in `_raise_obstacle`."""
    robots: int = 24
    hours: float = 2.0
    hot_picks: float = .2
    hot_share: float = .8
    """A `hot_picks` share of the pick faces gets a `hot_share` share of the orders, as in velocity slotting."""
    obstacles_per_hour: float = 20.0
    obstacle_mix: tuple[tuple[str, float], ...] = (('box', .2), ('person', .55), ('ghost', .25))
    person_in_human_zone: float = .6
    obstacle_at_pick: float = .5
    """Of the obstacles not placed in the human zone, the share that appears on a pick face, chosen as often as
    orders are: a dropped case, a person restocking, a reflection off the shelf. Robots heading to that pick cannot
    drive around them. The others appear in aisle cells that are not pick faces."""
    obstacle_lifetime: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        'box': (300, 1200), 'person': (30, 300), 'ghost': (120, 900)})
    """Seconds an obstacle stays, drawn uniformly. The ranges overlap, so how long a cell has been blocked does not
    tell what blocks it."""
    classifier_accuracy: dict[str, float] = field(default_factory=lambda: {'box': .8, 'person': .75, 'ghost': .7})
    motion_detected: dict[str, float] = field(default_factory=lambda: {'box': .03, 'person': .85, 'ghost': .1})
    scan_failure: float = .03
    scan_overconfidence: float = .2
    """A scan guess with stated confidence c is right with probability c minus this."""
    scan_unreadable: float = .5
    """Share of failed scans whose label is damaged: rescanning them never works."""
    rescan_success: float = .6
    """Chance that a rescan of a readable label works."""
    max_rescans: int = 3
    """After this many failed rescans of one item the fleet skips the order line on its own."""
    drain: float = .05
    """Nominal battery percent per cell; the true drain is this times the robot's hidden age."""
    age_range: tuple[float, float] = (.8, 1.8)
    charge_at: float = 4.5
    """An idle robot at or below this battery goes to charge without asking."""
    low_battery_at: float = 9.0
    """An idle robot below this battery raises an incident before its next task: one more task, or charge now?"""
    charge_rate: float = .5
    chargers: int = 4
    """Charger bays in use, spread evenly along the right edge (the layout has room for 7). With 4 for 24 robots a
    robot often finds every charger taken, which is what makes finishing a task first sometimes right."""
    finish_margin: float = 1.25
    """Finishing the task first is labelled right only if the battery covers this many times the task's true need."""
    docking_time: int = 60
    """Seconds of every charging session spent docking and undocking, whatever the battery. A fixed cost per session:
    charging at the first warning adds only a few per cent more sessions."""
    human_accuracy: float = .97
    human_median: float = 20.0
    """Median seconds for the person to answer a question; answer times are log-normal."""
    human_spread: float = .5
    """Standard deviation of the log of the answer time."""
    human_min: int = 3
    """No answer takes less than this many seconds."""
    human_switch_penalty: float = 10.0
    """Extra seconds when the person's previous question ended less than `human_switch_window` seconds ago."""
    human_switch_window: int = 60
    recovery_time: int = 300
    """Seconds of the person's time to recover a robot whose battery ran out."""
    recovery_battery: float = 30.0
    """Battery after a recovery (a swapped pack); the robot then goes to charge."""
    deadlock_after: int = 15
    """Seconds stuck behind a robot, or without a path, before the fleet escalates or replans."""
    pick_time: int = 5
    drop_time: int = 3
    rescan_time: int = 15
    wait_timeout: int = 120
    """A robot told to wait at an obstacle raises it again after this many seconds."""
    suspect_time: int = 300
    """Seconds the fleet plans around a cell after a robot rerouted away from it."""
    stop_after_box: int = 30
    stop_after_person: int = 60
    yield_time: int = 30
    """Seconds a robot that yielded in a deadlock plans around the other robot's cell."""
    deadlock_wait: int = 20
    max_sidesteps: int = 12
    """Head-on side-steps a robot makes between goals before it stops giving way and the standoff is escalated."""
    replan_avoid: int = 60
    """Seconds a robot avoids a goal it could not reach."""
    no_headway_after: int = 90
    """Seconds a moving robot may go without getting closer to its goal than it has been before the fleet manager
    gives it another goal (two robots shuffling around each other, say)."""

    def __post_init__(self) -> None:
        """Check every setting and bring sequences to the shapes of the defaults (a list from `--set` becomes a
        tuple), so that a bad setting fails here and not in the middle of an episode."""
        def check(ok: bool, message: str) -> None:
            if not ok:
                raise ValueError(message)

        def number(name: str, value: Any, whole: bool = False) -> float:
            check(type(value) is int if whole else type(value) in (int, float),
                  f'{name} must be a whole number' if whole else f'{name} must be a number')
            check(math.isfinite(value) and value >= 0, f'{name} must be finite and not negative')
            return value if whole else float(value)

        def pair(name: str, value: Any, whole: bool = False) -> tuple[float, float]:
            check(type(value) in (tuple, list) and len(value) == 2, f'{name} needs a (low, high) pair')
            low, high = (number(name, v, whole) for v in value)
            check(low <= high, f'{name} needs low <= high')
            return low, high

        def table(name: str, value: Any) -> dict[str, Any]:
            check(type(value) is dict and all(type(k) is str for k in value), f'{name} must map class names to values')
            return value

        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == 'age_range':
                value = pair(f.name, value)
            elif f.name == 'obstacle_mix':
                check(type(value) in (tuple, list) and all(
                    type(v) in (tuple, list) and len(v) == 2 and type(v[0]) is str for v in value),
                    'obstacle_mix needs (class, weight) pairs')
                value = tuple((cls, number(f.name, weight)) for cls, weight in value)
            elif f.name == 'obstacle_lifetime':
                value = {cls: pair(f.name, v, whole=True) for cls, v in table(f.name, value).items()}
            elif f.name in ('classifier_accuracy', 'motion_detected'):
                value = {cls: number(f.name, v) for cls, v in table(f.name, value).items()}
                check(set(value) == set(OBSTACLE_CLASSES), f'{f.name} needs exactly the classes {OBSTACLE_CLASSES}')
                check(all(p <= 1 for p in value.values()), f'{f.name} holds probabilities between 0 and 1')
            else:
                value = number(f.name, value, whole=f.type == 'int')
            object.__setattr__(self, f.name, value)
        for name in ('hot_picks', 'hot_share', 'person_in_human_zone', 'obstacle_at_pick', 'scan_failure',
                     'scan_unreadable', 'rescan_success', 'human_accuracy'):
            check(getattr(self, name) <= 1, f'{name} is a probability and must be between 0 and 1')
        mix = dict(self.obstacle_mix)
        check(len(mix) == len(self.obstacle_mix), 'obstacle_mix names each class once')
        check(set(mix) <= set(OBSTACLE_CLASSES) and sum(mix.values()) > 0,
              f'obstacle_mix needs positive weights for classes among {OBSTACLE_CLASSES}')
        check(set(self.obstacle_lifetime) >= set(mix), 'obstacle_lifetime needs a (low, high) range per class')
        check(self.robots >= 1, 'an episode needs at least one robot')
        check(self.chargers >= 1, 'an episode needs at least one charger')
        check(self.hours * 3600 >= 1, 'an episode must last at least one second')
        check(self.max_rescans >= 1 and self.charge_rate > 0 and self.human_median > 0,
              'max_rescans, charge_rate and human_median must be positive')


OBSTACLE_CLASSES = ('box', 'person', 'ghost')


def right_action(cls: str, at_goal: bool) -> str:
    """The best action for an obstacle class. Rerouting costs nothing in an aisle, so it is right for a person there;
    on the pick face it gives the order line up, so there the robot should wait for a person to leave."""
    if cls == 'ghost':
        return 'proceed'
    return 'wait' if cls == 'person' and at_goal else 'reroute'


@dataclass
class Obstacle:
    id: int
    """Its index in the schedule, so the same obstacle has the same id whatever the supervisor does."""
    cell: Cell
    cls: str
    until: int
    revealed: bool = False
    """The fleet knows what it is: a revealed box is planned around, a revealed ghost is ignored."""


@dataclass
class Robot:
    id: int
    cell: Cell
    battery: float
    age: float
    state: str = 'idle'
    """idle, moving, working, charging, incident, waiting, stopped or dead."""
    purpose: str = ''
    goal: Cell | None = None
    path: list[Cell] = field(default_factory=list)
    timer: int = 0
    on_timer: str = ''
    tasks: int = 0
    pick: Cell | None = None
    drop: Cell | None = None
    charger: Cell | None = None
    mispick: tuple[str, int] | None = None
    pick_incident: int | None = None
    finish_incident: int | None = None
    incident: int | None = None
    passing: int | None = None
    wait_obstacle: int | None = None
    blocked: int = 0
    sidesteps: int = 0
    """Head-on side-steps since the robot last reached a goal. Past `max_sidesteps` it stops giving way and the
    standoff is escalated as a deadlock."""
    yields_to: int | None = None
    """The robot this one gave way to on its way to the current goal. It keeps giving way to it, so two robots in a
    one-lane aisle settle who backs out once instead of taking turns forever."""
    no_path: int = 0
    closest: int = 0
    """The robot's smallest distance to its goal so far, and when it got there (time spent stopped excluded)."""
    closest_at: int = 0
    deadlock_cooldown: int = 0
    low_raised: bool = False
    must_charge: bool = False
    avoid: dict[Cell, int] = field(default_factory=dict)
    attempts: dict[Any, int] = field(default_factory=dict)


@dataclass
class Incident:
    obs: Observation
    correct: str
    data: dict[str, Any]
    decision: str = ''
    action: str = ''
    by: str = ''
    question: int | None = None
    open: bool = True


@dataclass
class Question:
    id: int
    kind: str
    target: Cell
    incidents: list[int]
    asked_at: int


@dataclass
class Job:
    type: str
    """question or recovery"""
    ref: int


def supervisor_seed(seed: int | str) -> int:
    """The seed a supervisor gets: derived one way from the episode seed, so it does not reveal the episode."""
    return random.Random(f'{seed}:supervisor').getrandbits(63)


class Episode:
    def __init__(self, supervisor: Supervisor, seed: int | str = 0, config: Config = Config(),
                 layout: Layout | None = None, record: bool = False) -> None:
        self.sup, self.seed, self.cfg = supervisor, seed, config
        self.layout = layout or warehouse(chargers=config.chargers)
        self.duration = int(config.hours * 3600)
        self.record = record
        if config.robots > len(self.layout.aisles):
            raise ValueError(f'{config.robots} robots do not fit in {len(self.layout.aisles)} aisle cells')
        # Streams that the supervisor cannot influence. Draws that depend on what happens in the episode are keyed
        # by the entity they are about (see `_rng`), so two supervisors meeting the same obstacle with the same
        # robot see the same sensor reading.
        self.rng = {name: random.Random(f'{seed}:{name}') for name in ('setup', 'slotting', 'obstacles', 'traffic', 'human')}
        self.time = 0
        self.robots: list[Robot] = []
        self.occupied: dict[Cell, int] = {}
        setup = self.rng['setup']
        for i, cell in enumerate(setup.sample(list(self.layout.aisles), config.robots)):
            self.robots.append(Robot(i, cell, setup.uniform(40, 100), setup.uniform(*config.age_range)))
            self.occupied[cell] = i
        self.bays = frozenset(self.layout.stations) | frozenset(self.layout.chargers)
        """Dead ends, entered from one side: robots never step aside into one and queue outside a full one."""
        self.pick_weight = self._slotting()
        self.schedule = self._obstacle_schedule()
        self.next_obstacle = 0
        self.obstacles: dict[int, Obstacle] = {}
        self.obstacle_cells: dict[Cell, Obstacle] = {}
        self.suspected: dict[Cell, int] = {}
        self.reserved_picks: dict[Cell, int] = {}
        self.reserved_chargers: dict[Cell, int] = {}
        self.incidents: dict[int, Incident] = {}
        self.new: list[int] = []
        self.questions: dict[int, Question] = {}
        self.queue: deque[Job] = deque()
        self.current: Job | None = None
        self.current_end = 0
        self.last_answer_end: int | None = None
        self.events: list[dict[str, Any]] = []
        self.stats: dict[str, Any] = {
            'questions': 0, 'answered': 0, 'answer_latency': 0, 'recoveries': 0, 'human_busy': 0,
            'delivered': 0, 'mispicked': 0, 'skipped': 0, 'abandoned': 0, 'returned': 0, 'replanned': 0, 'withdrawn': 0, 'spawned_obstacles': 0,
            'misses': [], 'incidents': {}, 'decisions': {},
        }
        supervisor.reset(supervisor_seed(seed))

    def _shown(self, incident: Incident) -> Observation:
        """A copy of the observation for the supervisor, details included, so nothing it does to it reaches the
        simulator."""
        return replace(incident.obs, details=Details(incident.obs.details))

    def _rng(self, *key: Any) -> random.Random:
        return random.Random(':'.join(map(str, (self.seed, *key))))

    # ---- running

    def run(self) -> dict[str, Any]:
        while self.time < self.duration:
            self.tick()
        from .metrics import summarize
        return summarize(self)

    def tick(self) -> None:
        self._obstacles_step()
        self._human_step()
        for robot in self.robots:
            self._robot_step(robot)
        self._decide_new()
        self.time += 1

    def _log(self, type_: str, **data: Any) -> None:
        if self.record:
            self.events.append({'t': self.time, 'type': type_, **data})

    # ---- orders and obstacles

    def _slotting(self) -> dict[Cell, float]:
        picks = list(self.layout.picks)
        self.rng['slotting'].shuffle(picks)
        hot = max(1, round(len(picks) * self.cfg.hot_picks))
        cold = len(picks) - hot
        weight = {cell: self.cfg.hot_share / hot for cell in picks[:hot]}
        weight.update({cell: (1 - self.cfg.hot_share) / cold for cell in picks[hot:]} if cold else {})
        return weight

    def _obstacle_schedule(self) -> list[tuple[int, Cell, str, int]]:
        rng, cfg = self.rng['obstacles'], self.cfg
        if cfg.obstacles_per_hour == 0:
            return []
        # Nothing is left in a bay's entrance, the only way out of it.
        entrances = {c for bay in self.bays for c in self.layout.neighbors(bay)}
        aisles = [cell for cell in self.layout.aisles if cell not in entrances]
        human = [cell for cell in aisles if self.layout.in_human_zone(cell)]
        elsewhere = [cell for cell in aisles if cell not in self.pick_weight]
        picks, weights = zip(*self.pick_weight.items())
        classes, mix = zip(*cfg.obstacle_mix)
        schedule, t = [], 0.0
        while True:
            t += rng.expovariate(cfg.obstacles_per_hour / 3600)
            if t >= self.duration:
                return schedule
            cls = rng.choices(classes, mix)[0]
            if cls == 'person' and rng.random() < cfg.person_in_human_zone:
                cell = rng.choice(human)
            elif rng.random() < cfg.obstacle_at_pick:
                cell = rng.choices(picks, weights if sum(weights) > 0 else None)[0]
            else:
                cell = rng.choice(elsewhere)
            schedule.append((int(t), cell, cls, rng.randint(*cfg.obstacle_lifetime[cls])))

    def _obstacles_step(self) -> None:
        while self.next_obstacle < len(self.schedule) and self.schedule[self.next_obstacle][0] <= self.time:
            index, (_, cell, cls, lifetime) = self.next_obstacle, self.schedule[self.next_obstacle]
            self.next_obstacle += 1
            if cell in self.occupied or cell in self.obstacle_cells:
                continue
            obstacle = Obstacle(index, cell, cls, self.time + lifetime)
            self.stats['spawned_obstacles'] += 1
            self.obstacles[obstacle.id] = obstacle
            self.obstacle_cells[cell] = obstacle
            self._log('obstacle', id=obstacle.id, cell=cell, cls=cls)
        gone = [o for o in self.obstacles.values() if o.until <= self.time]
        for obstacle in gone:
            del self.obstacles[obstacle.id]
            del self.obstacle_cells[obstacle.cell]
        if gone:
            ids = {o.id for o in gone}
            for question in list(self.questions.values()):
                for incident_id in list(question.incidents):
                    incident = self.incidents[incident_id]
                    if incident_id in question.incidents and incident.obs.kind == 'obstacle' \
                            and incident.data['obstacle'].id in ids:
                        self._withdraw(question, incident)

    def _withdraw(self, question: Question, incident: Incident) -> None:
        """The obstacle a waiting question is about has gone: the fleet takes the incident back from the question and
        the robot moves on. When it is the incident the question was asked about, the whole question goes, joined
        incidents included (their robots raise their obstacles again if those are still there): a joined incident
        never becomes what the person is asked about. A question the person is already answering stays. A withdrawn
        question still counts as asked, and simply disappears from the supervisor's pending questions."""
        if self.current is not None and self.current.type == 'question' and self.current.ref == question.id:
            return
        taken = list(question.incidents) if question.incidents[0] == incident.obs.incident else [incident.obs.incident]
        for incident_id in taken:
            question.incidents.remove(incident_id)
            withdrawn = self.incidents[incident_id]
            withdrawn.question = None
            self._close(withdrawn, None)
            robot = self.robots[withdrawn.obs.robot]
            robot.state, robot.path = 'moving', []
        if not question.incidents:
            del self.questions[question.id]
            self.queue = deque(j for j in self.queue if not (j.type == 'question' and j.ref == question.id))
            self.stats['withdrawn'] += 1

    def _known_box(self, cell: Cell) -> bool:
        obstacle = self.obstacle_cells.get(cell)
        return obstacle is not None and obstacle.revealed and obstacle.cls == 'box'

    def _blocked_for(self, robot: Robot, own_avoid: bool = True):
        """Cells the robot plans around. Its own avoid list (cells it yielded or goals it gave up) is a preference:
        `_plan` drops it when it leaves no way out."""
        def blocked(cell: Cell) -> bool:
            if self.suspected.get(cell, -1) > self.time or (own_avoid and robot.avoid.get(cell, -1) > self.time):
                return True
            occupant = self.occupied.get(cell)
            if occupant is not None and self.robots[occupant].state == 'dead':
                return True
            return self._known_box(cell)
        return blocked

    # ---- the person

    def _enqueue(self, job: Job) -> None:
        self.queue.append(job)
        if self.current is None:
            self._start_next()

    def _start_next(self) -> None:
        if not self.queue:
            return
        job = self.queue.popleft()
        if job.type == 'recovery':
            duration = self.cfg.recovery_time
        else:
            rng = self.rng['human']
            duration = self.cfg.human_median * math.exp(self.cfg.human_spread * rng.gauss(0, 1))
            if self.last_answer_end is not None and self.time - self.last_answer_end < self.cfg.human_switch_window:
                duration += self.cfg.human_switch_penalty
            duration = max(self.cfg.human_min, round(duration))
        self.current, self.current_end = job, self.time + duration

    def _human_step(self) -> None:
        if self.current is not None:
            self.stats['human_busy'] += 1
        while self.current is not None and self.time >= self.current_end:
            job, self.current = self.current, None
            self.last_answer_end = self.time
            if job.type == 'question':
                self._answer(self.questions.pop(job.ref))
            else:
                self._recovered(self.robots[job.ref])
            self._start_next()

    def _answer(self, question: Question) -> None:
        primary = self.incidents[question.incidents[0]]
        rng = self.rng['human']
        right = rng.random() < self.cfg.human_accuracy
        said = primary.correct if right else rng.choice([a for a in ACTIONS[question.kind] if a != primary.correct])
        answer = Answer(question.id, said, primary.obs.incident)
        self.stats['answered'] += 1
        self.stats['answer_latency'] += self.time - question.asked_at
        self._log('answer', question=question.id, action=said, right=right)
        for index, incident_id in enumerate(question.incidents):
            incident = self.incidents[incident_id]
            self.sup.on_answer(self._shown(incident), answer)
            same = index == 0 or (incident.obs.kind == 'obstacle'
                                  and incident.data['obstacle'] is primary.data['obstacle'])
            if right and said == incident.correct:
                if same:
                    self._resolve_by_person(incident)
                else:
                    # The person looked at the question's incident only: a joined incident with another cause gets
                    # the action, not what the person learned about the first (which item it is, what an obstacle is).
                    self._apply(incident, said, 'human')
            else:
                # A wrong answer is the person's miss on what they looked at. Anything else that goes wrong is the
                # supervisor's, which joined the incident: the answer was about another one, or about another place.
                self._apply(incident, said, 'human' if same and not right else 'supervisor')

    def _resolve_by_person(self, incident: Incident) -> None:
        """A right answer: the person also tells the fleet what an obstacle is, and identifies a scanned item."""
        incident.by = 'human'
        if incident.obs.kind == 'obstacle':
            obstacle = incident.data['obstacle']
            if obstacle.id in self.obstacles and obstacle.cls in ('box', 'ghost'):
                obstacle.revealed = True
        if incident.obs.kind == 'scan_failure':
            robot = self.robots[incident.obs.robot]
            incident.action = 'identify'
            self._close(incident, True)
            self._go(robot, robot.drop, 'drop')
            return
        self._apply(incident, incident.correct, 'human')

    # ---- robots

    def _robot_step(self, robot: Robot) -> None:
        state = robot.state
        if state != 'moving':
            robot.closest_at = self.time  # time spent stopped is not lost headway
        if state == 'idle':
            self._assign(robot)
        elif state == 'moving':
            self._move(robot)
        elif state == 'charging' and self.time >= robot.timer:
            robot.battery = min(100.0, robot.battery + self.cfg.charge_rate)
            if robot.battery >= 100:
                robot.low_raised = robot.must_charge = False
                self._release_charger(robot)
                robot.state = 'idle'
        elif state == 'waiting' and robot.wait_obstacle is not None and robot.wait_obstacle not in self.obstacles:
            # The obstacle is gone. That does not show waiting was right: a box or a ghost may just have expired.
            incident = self.incidents[robot.incident]
            robot.wait_obstacle = None
            self._close(incident, None)
            robot.state, robot.path = 'moving', []
        elif state in ('working', 'waiting', 'stopped') and self.time >= robot.timer:
            self._timer_done(robot)

    def _assign(self, robot: Robot) -> None:
        if robot.battery <= self.cfg.charge_at or robot.must_charge:
            self._go_charge(robot)
            return
        available = [p for p in self.layout.picks if p not in self.reserved_picks and robot.avoid.get(p, -1) <= self.time
                     and self.suspected.get(p, -1) <= self.time and not self._known_box(p)]
        if not available:
            return  # every pick face is taken; try again next tick
        rng = self._rng('task', robot.id, robot.tasks)
        robot.tasks += 1
        weights = [self.pick_weight[p] for p in available]
        # With every hot pick face taken and the rest weightless (hot_share = 1), any free face will do.
        pick = rng.choices(available, weights if sum(weights) > 0 else None)[0]
        self.reserved_picks[pick] = robot.id
        robot.pick, robot.drop = pick, self._station(robot, rng)
        if robot.battery < self.cfg.low_battery_at and not robot.low_raised:
            robot.low_raised = True
            robot.goal, robot.purpose = pick, 'pick'
            self._raise_low_battery(robot)
            return
        self._go(robot, pick, 'pick')

    def _station(self, robot: Robot, rng: random.Random) -> Cell:
        """The station with the fewest robots already headed there, among those the robot can reach."""
        load = {s: 0 for s in self.layout.stations if robot.avoid.get(s, -1) <= self.time} or \
            {s: 0 for s in self.layout.stations}
        for other in self.robots:
            if other.drop in load:
                load[other.drop] += 1
        least = min(load.values())
        return rng.choice([s for s, n in load.items() if n == least])

    def _go(self, robot: Robot, goal: Cell, purpose: str) -> None:
        robot.goal, robot.purpose, robot.state, robot.no_path = goal, purpose, 'moving', 0
        robot.yields_to, robot.closest, robot.closest_at = None, self._manhattan(robot.cell, goal), self.time
        robot.path = self._plan(robot, goal) or []

    @staticmethod
    def _manhattan(a: Cell, b: Cell) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _plan(self, robot: Robot, goal: Cell) -> list[Cell] | None:
        path = self.layout.path(robot.cell, goal, self._blocked_for(robot))
        if path is None:
            # A robot that yielded inside a dead-end bay would otherwise avoid its only way out.
            path = self.layout.path(robot.cell, goal, self._blocked_for(robot, own_avoid=False))
        return path

    def _go_charge(self, robot: Robot) -> None:
        robot.must_charge = True
        free = [c for c in self.layout.chargers if c not in self.reserved_chargers and robot.avoid.get(c, -1) <= self.time]
        if not free:
            robot.state = 'idle'  # every charger is taken; try again next tick
            return
        charger = min(free, key=lambda c: abs(c[0] - robot.cell[0]) + abs(c[1] - robot.cell[1]))
        self.reserved_chargers[charger] = robot.id
        robot.charger = charger
        self._go(robot, charger, 'charge')

    def _release_pick(self, robot: Robot) -> None:
        if robot.pick is not None and self.reserved_picks.get(robot.pick) == robot.id:
            del self.reserved_picks[robot.pick]

    def _release_charger(self, robot: Robot) -> None:
        if robot.charger is not None and self.reserved_chargers.get(robot.charger) == robot.id:
            del self.reserved_chargers[robot.charger]
        robot.charger = None

    def _abandon_task(self, robot: Robot, started: bool = True) -> None:
        """Drop the current order line. A pending scan decision is cancelled before anything showed whether it was
        right. A pending finish-task decision stays open: the robot still has to reach a charger on that battery.
        A line given back before the robot started on it (`started=False`) counts as returned, not dropped."""
        if robot.pick is not None:
            self.stats['abandoned' if started else 'returned'] += 1
        self._release_pick(robot)
        if robot.pick_incident is not None:
            self._close(self.incidents[robot.pick_incident], None)
            robot.pick_incident = None
        robot.pick = robot.drop = robot.mispick = None
        self._forget_obstacles(robot)

    def _forget_obstacles(self, robot: Robot) -> None:
        """A new task, or the way through: obstacle encounters count from one again."""
        for key in [k for k in robot.attempts if isinstance(k, tuple) and k[0] == 'obstacle']:
            del robot.attempts[key]

    def _give_up_pick(self, robot: Robot) -> None:
        """The pick face cannot be reached: the order line goes back and the robot takes another task."""
        self._abandon_task(robot)
        robot.state, robot.path = 'idle', []

    def _replan(self, robot: Robot) -> None:
        """No path to the goal for a while: the fleet manager gives the robot another goal."""
        self.stats['replanned'] += 1
        robot.avoid[robot.goal] = self.time + self.cfg.replan_avoid
        robot.no_path = 0
        if robot.purpose == 'pick':
            self._abandon_task(robot)
            robot.state = 'idle'
        elif robot.purpose == 'drop':
            robot.drop = self._station(robot, self._rng('replan', robot.id, self.time))
            self._go(robot, robot.drop, 'drop')
        else:
            self._release_charger(robot)
            self._go_charge(robot)

    def _move(self, robot: Robot) -> None:
        if robot.cell == robot.goal:
            self._arrive(robot)
            return
        if robot.purpose == 'pick' and self._known_box(robot.goal):
            self._give_up_pick(robot)
            return
        if robot.cell in self.bays:
            # A bay has one way out. While a robot that is not moving (one waiting for an answer, or out of battery)
            # stands in it, the robot inside waits, its task kept, and asks no one to make way.
            exit_cell = next(iter(self.layout.neighbors(robot.cell)))
            occupant = self.occupied.get(exit_cell)
            if occupant is not None and self.robots[occupant].state != 'moving':
                robot.path, robot.blocked, robot.no_path, robot.closest_at = [], 0, 0, self.time
                return
        distance = self._manhattan(robot.cell, robot.goal)
        if distance < robot.closest:
            robot.closest, robot.closest_at = distance, self.time
        elif self.time - robot.closest_at >= self.cfg.no_headway_after:
            # No headway for a long while, though moving: two robots that both stopped giving way shuffle around
            # each other, say, or a robot keeps stepping aside for others. The fleet manager gives it another goal.
            robot.blocked = 0
            self._replan(robot)
            return
        blocked = self._blocked_for(robot)
        if not robot.path or blocked(robot.path[0]):
            path = self._plan(robot, robot.goal)
            if not path:
                robot.no_path += 1
                if robot.no_path >= self.cfg.deadlock_after:
                    self._replan(robot)
                return
            robot.path, robot.no_path = path, 0
        nxt = robot.path[0]
        if robot.path[1:] == [robot.goal] and robot.goal in self.bays and self.occupied.get(robot.goal) is not None:
            # Queue outside a dead-end bay until the robot in it has come out, but not in the way of a robot that
            # wants this cell (the one coming out, say): step aside for it, or else let the head-on rules settle it.
            if not any(other.state == 'moving' and other.path and other.path[0] == robot.cell
                       for other in self.robots if other is not robot):
                robot.blocked += 1
                if self.robots[self.occupied[robot.goal]].state not in ('moving', 'working') and \
                        robot.blocked >= self.cfg.deadlock_after:
                    # The robot in the bay is staying (waiting for an answer, or out of battery): go elsewhere.
                    robot.blocked = 0
                    self._replan(robot)
                return
            side = self._side_cells(robot, nxt)
            if side:
                self._step_to(robot, self.rng['traffic'].choice(side))
                robot.path = []
                return
        obstacle = self.obstacle_cells.get(nxt)
        if obstacle and robot.passing != obstacle.id and not (obstacle.revealed and obstacle.cls == 'ghost'):
            self._raise_obstacle(robot, obstacle)
            return
        other = self.occupied.get(nxt)
        if other is not None:
            blocker = self.robots[other]
            head_on = blocker.state == 'moving' and bool(blocker.path) and blocker.path[0] == robot.cell
            robot.blocked += 1
            if nxt == robot.goal and blocker.state != 'moving' and robot.blocked >= self.cfg.deadlock_after:
                # A robot that stays on the goal (waiting at an obstacle, say) is not a standoff to settle: the
                # fleet manager gives this robot another goal.
                robot.blocked = 0
                self._replan(robot)
                return
            if head_on and robot.blocked >= 2:
                # Head-on: fleet traffic rules settle it without anyone (see `_gives_way`).
                side = self._side_cells(robot, nxt)
                if side and self._gives_way(robot, blocker):
                    self._step_to(robot, self.rng['traffic'].choice(side))
                    robot.path, robot.blocked = [], 0
                    robot.sidesteps += 1
                    robot.yields_to = blocker.id
                    if blocker.yields_to == robot.id:
                        blocker.yields_to = None
                    return
            if robot.blocked >= 3:
                # Local avoidance: plan around the cells other robots stand on, if the detour is short and really
                # avoids the blocked cell (it cannot when the blocker stands on the goal).
                detour = self.layout.path(robot.cell, robot.goal,
                                          lambda c: blocked(c) or (c in self.occupied and c != robot.goal))
                if detour and detour[0] != nxt and len(detour) <= len(robot.path) + 8:
                    robot.path = detour
                    return
            if robot.blocked >= 4 * self.cfg.deadlock_after:
                # Stuck behind a robot that does not move off (waiting for an answer, say), or in a standoff nobody
                # settled: the fleet manager routes this robot around the robots that are standing still, however
                # long the way, or else gives it another goal.
                robot.blocked = 0
                around = self.layout.path(robot.cell, robot.goal, lambda c: blocked(c) or (
                    c in self.occupied and c != robot.goal and self.robots[self.occupied[c]].state != 'moving'))
                if around and around[0] != nxt:
                    robot.path, robot.closest_at = around, self.time  # the detour gets its own time to make headway
                else:
                    self._replan(robot)
                return
            if head_on and robot.blocked >= self.cfg.deadlock_after and self.time >= robot.deadlock_cooldown:
                # Only a standoff the traffic rules could not settle is escalated. A robot queued behind one that
                # has stopped waits: the stopped robot's own incident is what the supervisor needs to settle.
                self._raise_deadlock(robot, blocker)
            return
        robot.path.pop(0)
        self._step_to(robot, nxt)
        robot.attempts.pop(('obstacle', nxt), None)
        robot.blocked = 0
        robot.attempts.pop('deadlock', None)

    def _side_cells(self, robot: Robot, ahead: Cell) -> list[Cell]:
        blocked = self._blocked_for(robot)
        return [c for c in self.layout.neighbors(robot.cell)
                if c != ahead and c not in self.occupied and c not in self.obstacle_cells and not blocked(c)
                and c not in self.bays]

    def _gives_way(self, robot: Robot, blocker: Robot) -> bool:
        """Whether `robot` steps aside for `blocker`, which wants its cell. A robot that has stepped aside
        `max_sidesteps` times since reaching a goal no longer does. A robot that cannot step aside (in a dead-end bay,
        or shut in at the end of an aisle) never does, so the other one must. Otherwise a robot keeps giving way to
        the one it already gave way to; failing that, the robot entering its goal steps aside, else the one with the
        higher id."""
        if robot.sidesteps >= self.cfg.max_sidesteps:
            return False
        if not self._side_cells(blocker, robot.cell):
            return True
        if robot.yields_to == blocker.id or blocker.yields_to == robot.id:
            return robot.yields_to == blocker.id
        entering = lambda r: r.path[0] == r.goal
        return entering(robot) or (not entering(blocker) and robot.id > blocker.id)

    def _step_to(self, robot: Robot, cell: Cell) -> None:
        """Move one cell, draining the battery by the robot's true rate."""
        del self.occupied[robot.cell]
        robot.cell = cell
        self.occupied[cell] = robot.id
        robot.battery -= self.cfg.drain * robot.age
        if robot.battery <= 0:
            self._die(robot)

    def _arrive(self, robot: Robot) -> None:
        robot.sidesteps, robot.yields_to = 0, None
        self._forget_obstacles(robot)
        if robot.purpose == 'pick':
            robot.state, robot.timer, robot.on_timer = 'working', self.time + self.cfg.pick_time, 'picked'
        elif robot.purpose == 'drop':
            robot.state, robot.timer, robot.on_timer = 'working', self.time + self.cfg.drop_time, 'dropped'
        else:
            robot.state, robot.timer = 'charging', self.time + self.cfg.docking_time
            if robot.finish_incident is not None:
                # Reaching the charger shows only that the battery lasted, not that finishing first was right.
                self._close(self.incidents[robot.finish_incident], None)
                robot.finish_incident = None

    def _timer_done(self, robot: Robot) -> None:
        event = robot.on_timer
        if event == 'picked':
            self._release_pick(robot)
            if self._rng('scan', robot.id, robot.tasks).random() < self.cfg.scan_failure:
                self._raise_scan(robot, 1)
            else:
                self._go(robot, robot.drop, 'drop')
        elif event == 'dropped':
            self._deliver(robot)
        elif event == 'rescanned':
            attempt = robot.attempts.get('scan', 1)
            last = self.incidents[robot.attempts['scan_incident']]
            if not last.data['unreadable'] and \
                    self._rng('rescan', robot.id, robot.tasks, attempt).random() < self.cfg.rescan_success:
                self._go(robot, robot.drop, 'drop')
            elif attempt >= self.cfg.max_rescans:
                # The fleet gives the item up on its own. That fails the line needlessly unless skipping was right;
                # when rescanning was right and the rescans failed by chance, it is nobody's misjudgement.
                if last.correct != 'skip':
                    self._miss('low', 'system' if last.correct == 'rescan' else last.by, last)
                self.stats['skipped'] += 1
                self._abandon_task(robot)
                robot.state = 'idle'
            else:
                self._raise_scan(robot, attempt + 1)
        elif event == 'wait_timeout':
            incident = self.incidents[robot.incident]
            obstacle = incident.data['obstacle']
            robot.wait_obstacle = None
            self._close(incident, None)  # a person may simply still be there
            if obstacle.id in self.obstacles and not obstacle.revealed:
                self._raise_obstacle(robot, obstacle)
            elif obstacle.id in self.obstacles and obstacle.cls == 'ghost':
                robot.passing = obstacle.id  # someone found out while the robot waited
                robot.state, robot.path = 'moving', []
            else:
                # Gone, or a known box: the robot plans around it, and gives the line up if it is on the pick face.
                robot.state, robot.path = 'moving', []
                if obstacle.id in self.obstacles and robot.purpose == 'pick' and obstacle.cell == robot.goal:
                    self._give_up_pick(robot)
        else:
            robot.state, robot.path = 'moving', []

    def _deliver(self, robot: Robot) -> None:
        self.stats['delivered'] += 1
        if robot.pick_incident is not None:
            incident = self.incidents[robot.pick_incident]
            if robot.mispick:
                self._miss('medium', robot.mispick[0], incident)
            self._close(incident, robot.mispick is None, 'medium' if robot.mispick else None)
        if robot.mispick:
            self.stats['mispicked'] += 1
        robot.pick = robot.drop = robot.mispick = robot.pick_incident = None
        robot.state = 'idle'

    def _die(self, robot: Robot) -> None:
        if robot.finish_incident is not None:
            incident = self.incidents[robot.finish_incident]
            # Running out after finishing the task is the miss of whoever chose to finish, unless finishing was labelled
            # right (never by default: see `_raise_low_battery`), when it is nobody's misjudgement.
            self._miss('high', incident.by if incident.correct == 'charge_now' else 'system', incident)
            self._close(incident, False, 'high')
            robot.finish_incident = None
        else:
            self._miss('high', 'system', None)
        self._abandon_task(robot)
        self._release_charger(robot)
        robot.state, robot.battery = 'dead', 0.0
        self.stats['recoveries'] += 1
        self._log('dead', robot=robot.id, cell=robot.cell)
        self._enqueue(Job('recovery', robot.id))

    def _recovered(self, robot: Robot) -> None:
        robot.state, robot.path, robot.battery = 'idle', [], self.cfg.recovery_battery
        robot.low_raised, robot.must_charge = False, True

    def _stop(self, robot: Robot, seconds: int) -> None:
        robot.state, robot.timer, robot.on_timer = 'stopped', self.time + seconds, 'resume'

    # ---- incidents

    def _raise(self, robot: Robot, kind: str, target: Cell, attempt: int, suggested: str, confidence: float,
               correct: str, details: dict[str, Any], data: dict[str, Any] | None = None) -> None:
        incident_id = len(self.incidents)
        obs = Observation(
            incident_id, kind, self.time, robot.id, robot.cell, target, self.layout.in_human_zone(target), attempt,
            suggested, round(confidence, 3), ACTIONS[kind], Details(details))
        self.incidents[incident_id] = Incident(obs, correct, data or {})
        self.stats['incidents'][kind] = self.stats['incidents'].get(kind, 0) + 1
        robot.state, robot.incident = 'incident', incident_id
        self.new.append(incident_id)
        self._log('incident', id=incident_id, kind=kind, robot=robot.id, cell=robot.cell, target=target, attempt=attempt)

    def _raise_obstacle(self, robot: Robot, obstacle: Obstacle) -> None:
        # Counted by cell, from the robot's last arrival or its way through that cell: the robot cannot tell one
        # obstacle from the next one in the same place.
        key = ('obstacle', obstacle.cell)
        robot.attempts[key] = attempt = robot.attempts.get(key, 0) + 1
        rng, cls, cfg = self._rng('sense', obstacle.id, robot.id, attempt), obstacle.cls, self.cfg
        predicted = cls if rng.random() < cfg.classifier_accuracy[cls] else rng.choice([c for c in ('box', 'person', 'ghost') if c != cls])
        confidence = rng.betavariate(8, 2) if predicted == cls else rng.betavariate(5, 3)
        at_goal = obstacle.cell == robot.goal
        details = {'predicted': predicted, 'motion': rng.random() < cfg.motion_detected[cls], 'at_goal': at_goal}
        self._raise(robot, 'obstacle', obstacle.cell, attempt, right_action(predicted, at_goal), confidence,
                    right_action(cls, at_goal), details, {'obstacle': obstacle, 'at_goal': at_goal})

    def _distance(self, robot: Robot, start: Cell, goal: Cell) -> int:
        path = self.layout.path(start, goal, self._blocked_for(robot))
        return len(path) if path is not None else 10_000

    def _raise_low_battery(self, robot: Robot) -> None:
        need = self._distance(robot, robot.cell, robot.pick) + self._distance(robot, robot.pick, robot.drop)
        need += min(self._distance(robot, robot.drop, charger) for charger in self.layout.chargers)
        estimated = need * self.cfg.drain
        margin = robot.battery - estimated
        free = sum(c not in self.reserved_chargers for c in self.layout.chargers)
        # A robot charges to full either way, so charging first costs nothing while a charger is free. With every
        # charger taken it stands idle until one frees up: then finishing the task first is right if the battery
        # covers it at the robot's true drain, with a margin for detours. Labelled on what is known now.
        enough = robot.battery > self.cfg.finish_margin * need * self.cfg.drain * robot.age
        self._raise(robot, 'low_battery', robot.cell, 1, 'finish_task' if margin > 0 else 'charge_now',
                    .5 + .5 * math.tanh(abs(margin) / 2), 'finish_task' if free == 0 and enough else 'charge_now',
                    {'battery': round(robot.battery, 2), 'estimated_need': round(estimated, 2),
                     'free_chargers': free})

    def _raise_scan(self, robot: Robot, attempt: int) -> None:
        robot.attempts['scan'] = attempt
        # The label and the scanner's best guess belong to the item, so they stay the same over rescans.
        unreadable = self._rng('label', robot.id, robot.tasks).random() < self.cfg.scan_unreadable
        rng = self._rng('scanner', robot.id, robot.tasks)
        stated = rng.uniform(.5, .99)
        # The scanner is overconfident: its guess is right less often than it claims.
        guess_correct = rng.random() < max(.05, stated - self.cfg.scan_overconfidence)
        # The right action: take a right guess; otherwise rescan, unless the label is damaged, when the only
        # autonomous way to avoid a wrong pick is to skip the line. A person can always identify the item.
        correct = 'pick_anyway' if guess_correct else 'skip' if unreadable else 'rescan'
        self._raise(robot, 'scan_failure', robot.cell, attempt, 'pick_anyway', stated, correct, {},
                    {'guess_correct': guess_correct, 'unreadable': unreadable})
        robot.attempts['scan_incident'] = len(self.incidents) - 1

    def _raise_deadlock(self, robot: Robot, blocker: Robot) -> None:
        robot.attempts['deadlock'] = attempt = robot.attempts.get('deadlock', 0) + 1
        robot.deadlock_cooldown = self.time + self.cfg.yield_time
        self._raise(robot, 'deadlock', blocker.cell, attempt, 'yield',
                    self._rng('deadlock', robot.id, self.time).uniform(.85, .99), 'yield',
                    {'blocker': blocker.id}, {'blocker': blocker.id})

    def _context(self) -> Context:
        pending = tuple(PendingQuestion(q.id, q.kind, q.target, tuple(q.incidents), q.asked_at)
                        for q in self.questions.values())
        return Context(self.time, pending, len(self.queue) + (self.current is not None))

    def _decide_new(self) -> None:
        for incident_id in self.new:
            incident = self.incidents[incident_id]
            decision = self.sup.decide(self._shown(incident), self._context())
            self._check(decision, incident)
            incident.decision = decision.type
            key = f'{incident.obs.kind}:{decision.type}'
            self.stats['decisions'][key] = self.stats['decisions'].get(key, 0) + 1
            self._log('decision', id=incident_id, decision=decision.type, action=decision.action, question=decision.question)
            if decision.type == 'act':
                self._apply(incident, decision.action, 'supervisor')
            elif decision.type == 'ask':
                question = Question(self.stats['questions'], incident.obs.kind,
                                    incident.obs.target, [incident_id], self.time)
                self.stats['questions'] += 1
                self.questions[question.id] = question
                incident.question = question.id
                self._enqueue(Job('question', question.id))
            else:
                question = self.questions[decision.question]
                question.incidents.append(incident_id)
                incident.question = question.id
        self.new.clear()

    def _check(self, decision: Decision, incident: Incident) -> None:
        if not isinstance(decision, Decision):
            raise DecisionError(f'{self.sup.name} returned {decision!r}, not a Decision')
        if decision.type == 'act':
            if decision.action not in incident.obs.actions:
                raise DecisionError(f'{self.sup.name} chose {decision.action!r} for a {incident.obs.kind} incident')
        elif decision.type == 'join':
            question = self.questions.get(decision.question) if type(decision.question) is int else None
            if question is None or question.kind != incident.obs.kind:
                raise DecisionError(f'{self.sup.name} joined a {incident.obs.kind} incident to question '
                                    f'{decision.question!r}')
        elif decision.type != 'ask':
            raise DecisionError(f'{self.sup.name} returned an unknown decision {decision.type!r}')

    def _apply(self, incident: Incident, action: str, by: str) -> None:
        robot = self.robots[incident.obs.robot]
        incident.action, incident.by = action, by
        kind = incident.obs.kind
        if kind == 'obstacle':
            obstacle = incident.data['obstacle']
            active = obstacle.id in self.obstacles
            if action == 'proceed':
                if not active or obstacle.cls == 'ghost':
                    if active:
                        obstacle.revealed = True
                    robot.passing = obstacle.id
                    self._close(incident, True)
                    robot.state = 'moving'
                elif obstacle.cls == 'box':
                    obstacle.revealed = True
                    self._miss('medium', by, incident)
                    self._close(incident, False, 'medium')
                    self._stop(robot, self.cfg.stop_after_box)
                else:
                    self._miss('critical', by, incident)
                    self._close(incident, False, 'critical')
                    self._stop(robot, self.cfg.stop_after_person)
            elif action == 'reroute':
                self.suspected[obstacle.cell] = max(self.suspected.get(obstacle.cell, 0), self.time + self.cfg.suspect_time)
                if incident.data['at_goal'] and robot.purpose == 'pick':
                    # There is no way around an obstacle on the pick face: rerouting gives the order line up. That is
                    # right for a box, and a needless failed order for a person who would have left or a ghost.
                    wrong = incident.correct != 'reroute'
                    if wrong:
                        self._miss('low', by, incident)
                    self._close(incident, None)
                    self._give_up_pick(robot)
                else:
                    self._close(incident, None)
                    robot.state, robot.path = 'moving', []
            else:
                robot.state, robot.wait_obstacle = 'waiting', obstacle.id
                robot.timer, robot.on_timer = self.time + self.cfg.wait_timeout, 'wait_timeout'
        elif kind == 'low_battery':
            if action == 'finish_task':
                robot.finish_incident = incident.obs.incident
                robot.incident, robot.must_charge = None, True
                self._go(robot, robot.pick, 'pick')
            else:
                # Charging first is never a miss, and costs next to nothing: the robot charges to full either way.
                # The battery warning comes with a new task, so the line goes back before any work was done on it.
                self._close(incident, None)
                self._abandon_task(robot, started=False)
                self._go_charge(robot)
        elif kind == 'scan_failure':
            if action == 'pick_anyway':
                if not incident.data['guess_correct']:
                    robot.mispick = (by, incident.obs.incident)
                robot.pick_incident = incident.obs.incident
                robot.incident = None
                self._go(robot, robot.drop, 'drop')
            elif action == 'rescan':
                self._close(incident, None)
                robot.state, robot.timer, robot.on_timer = 'working', self.time + self.cfg.rescan_time, 'rescanned'
            else:
                # Skipping fails the order line: needlessly unless the label was damaged and the guess wrong.
                wrong = incident.correct != 'skip'
                if wrong:
                    self._miss('low', by, incident)
                self._close(incident, None)
                self.stats['skipped'] += 1
                self._abandon_task(robot)
                robot.state = 'idle'
        else:
            self._close(incident, None)
            if action == 'yield':
                blocker_cell = self.robots[incident.data['blocker']].cell
                robot.avoid[blocker_cell] = self.time + self.cfg.yield_time
                side = self._side_cells(robot, blocker_cell)
                robot.state, robot.path, robot.blocked = 'moving', [], 0
                if side:
                    self._step_to(robot, self.rng['traffic'].choice(side))
            else:
                robot.state, robot.timer, robot.on_timer, robot.blocked = 'waiting', self.time + self.cfg.deadlock_wait, 'resume', 0

    def _close(self, incident: Incident, ok: bool | None, severity: str | None = None) -> None:
        if not incident.open:
            return
        incident.open = False
        robot = self.robots[incident.obs.robot]
        if robot.incident == incident.obs.incident:
            robot.incident = None
        if incident.decision == 'act':
            # A miss is visible only when something visibly went wrong; whether a detour or a skipped line was
            # needless is never shown.
            self.sup.on_outcome(self._shown(incident), Outcome(incident.action, ok, severity if ok is False else None))

    def _miss(self, severity: str, by: str, incident: Incident | None) -> None:
        self.stats['misses'].append({
            't': self.time, 'severity': severity, 'by': by,
            'kind': incident.obs.kind if incident else None,
            'incident': incident.obs.incident if incident else None,
        })
        self._log('miss', severity=severity, by=by, incident=incident.obs.incident if incident else None)
