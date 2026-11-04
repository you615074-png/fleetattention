import signal

import pytest

from fleetattention.model import Decision
from fleetattention.supervisors import AlwaysAsk, NeverAsk, Reference, Supervisor, by_name
from fleetattention.world import Config, Episode, Obstacle, supervisor_seed

SHORT = Config(hours=.25)


class Fixed(Supervisor):
    """Takes the same action for every incident of a kind, asks otherwise; records outcomes."""
    name = 'fixed'

    def __init__(self, **actions):
        self.actions, self.outcomes, self.seed = actions, [], None

    def reset(self, seed):
        self.seed = seed

    def decide(self, obs, ctx):
        return Decision.act(self.actions[obs.kind]) if obs.kind in self.actions else Decision.ask()

    def on_outcome(self, obs, outcome):
        self.outcomes.append((obs, outcome))


def quiet(**overrides):
    """An episode without scheduled obstacles, for setting up situations by hand."""
    return Config(obstacles_per_hour=0, **overrides)


def place(episode, robot, cell):
    del episode.occupied[robot.cell]
    robot.cell = cell
    episode.occupied[cell] = robot.id


def test_same_seed_gives_the_same_episode():
    assert Episode(Reference(), 3, SHORT).run() == Episode(Reference(), 3, SHORT).run()


def test_obstacle_schedule_does_not_depend_on_the_supervisor():
    assert Episode(NeverAsk(), 5, SHORT).schedule == Episode(AlwaysAsk(), 5, SHORT).schedule


@pytest.mark.parametrize('name, seed', [('never_ask', 1), ('cost_aware', 2), ('reference', 3), ('patient', 4)])
def test_robots_never_share_a_cell_and_reservations_have_one_owner(name, seed):
    episode = Episode(by_name(name), seed, Config(hours=.15))
    for _ in range(episode.duration):
        episode.tick()
        cells = [robot.cell for robot in episode.robots]
        assert len(cells) == len(set(cells))
        assert episode.occupied == {robot.cell: robot.id for robot in episode.robots}
        for cell, owner in episode.reserved_picks.items():
            assert episode.robots[owner].pick == cell
        for cell, owner in episode.reserved_chargers.items():
            assert episode.robots[owner].charger == cell
        holders = [r.charger for r in episode.robots if r.charger is not None]
        assert len(holders) == len(set(holders))
        for robot in episode.robots:
            if robot.state in ('incident', 'waiting') and robot.incident is not None:
                assert episode.incidents[robot.incident].open


def test_the_supervisor_cannot_rebuild_the_episode_from_its_seed():
    sup = Fixed()
    episode = Episode(sup, 7, SHORT)
    assert sup.seed == supervisor_seed(7) != 7
    assert Episode(NeverAsk(), sup.seed, SHORT).schedule != episode.schedule


def test_sensor_readings_do_not_depend_on_what_else_the_fleet_did():
    """Common random numbers: the same robot meeting the same obstacle sees the same reading, even after traffic
    (driven by the supervisor) consumed random draws in one episode and not the other."""
    readings = []
    for extra_traffic in (0, 5):
        episode = Episode(NeverAsk(), 4, quiet())
        for _ in range(extra_traffic):
            episode.rng['traffic'].random()
        robot = episode.robots[0]
        episode._raise_obstacle(robot, Obstacle(3, (10, 3), 'box', 600))
        obs = episode.incidents[0].obs
        readings.append((obs.suggested, obs.confidence, obs.details))
    assert readings[0] == readings[1]


def test_more_robots_than_pick_faces_waits_instead_of_hanging():
    def alarm(*_):
        raise TimeoutError('tick did not return')
    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(5)
    try:
        episode = Episode(NeverAsk(), 0, Config(robots=201, hours=.01))
        episode.tick()
    finally:
        signal.alarm(0)
    assert len(episode.reserved_picks) == len(episode.layout.picks)
    assert sum(robot.pick is None and robot.state == 'idle' for robot in episode.robots) >= 1


def test_zero_obstacles_is_a_valid_config_and_negative_is_not():
    assert Episode(NeverAsk(), 0, quiet(hours=.01)).schedule == []
    with pytest.raises(ValueError):
        Config(obstacles_per_hour=-1)


def test_chargers_are_never_double_booked():
    episode = Episode(NeverAsk(), 0, quiet(robots=12))
    for robot in episode.robots:
        episode._go_charge(robot)
    booked = [r for r in episode.robots if r.charger is not None]
    assert len(booked) == len(episode.layout.chargers)
    assert all(r.state == 'idle' for r in episode.robots if r.charger is None)


def test_a_known_box_on_the_pick_face_gives_the_order_line_back_once():
    episode = Episode(NeverAsk(), 0, quiet(robots=1))
    robot = episode.robots[0]
    episode._assign(robot)
    box = Obstacle(0, robot.pick, 'box', 10_000, revealed=True)
    episode.obstacles[0], episode.obstacle_cells[robot.pick] = box, box
    pick = robot.pick
    for _ in range(50):
        episode.tick()
    assert episode.stats['abandoned'] == 1
    assert sum(episode.stats['incidents'].values()) == 0
    assert robot.pick != pick


@pytest.mark.parametrize('cls, low_misses', [('person', 1), ('ghost', 1), ('box', 0)])
def test_rerouting_away_from_the_pick_face_fails_the_order_unless_it_is_a_box(cls, low_misses):
    episode = Episode(Fixed(obstacle='reroute'), 0, quiet(robots=1))
    robot = episode.robots[0]
    episode._assign(robot)
    obstacle = Obstacle(0, robot.pick, cls, 10_000)
    episode.obstacles[0], episode.obstacle_cells[robot.pick] = obstacle, obstacle
    while not episode.stats['abandoned']:
        episode.tick()
    assert episode.incidents[0].obs.details['at_goal']
    assert sum(m['severity'] == 'low' and m['by'] == 'supervisor' for m in episode.stats['misses']) == low_misses


def test_a_robot_staying_on_the_goal_makes_the_fleet_choose_another_goal():
    episode = Episode(Fixed(deadlock='wait'), 0, quiet(robots=2))
    mover, blocker = episode.robots
    place(episode, mover, (1, 1))
    place(episode, blocker, (0, 1))
    blocker.state = 'incident'
    mover.drop = (0, 1)
    episode._go(mover, (0, 1), 'drop')
    for _ in range(40):
        episode._move(mover)
        episode.time += 1
    assert episode.stats['replanned'] == 1 and mover.goal != (0, 1)
    assert 'deadlock' not in episode.stats['incidents']


def test_no_path_makes_the_fleet_replan_instead_of_waiting_forever():
    episode = Episode(NeverAsk(), 0, quiet(robots=1))
    robot = episode.robots[0]
    station = episode.layout.stations[0]
    entrance = (station[0] + 1, station[1])
    box = Obstacle(0, entrance, 'box', 10_000, revealed=True)
    episode.obstacles[0], episode.obstacle_cells[entrance] = box, box
    place(episode, robot, (3, 5))
    episode._go(robot, station, 'drop')
    for _ in range(episode.cfg.deadlock_after + 1):
        episode._move(robot)
    assert episode.stats['replanned'] == 1
    assert robot.goal != station


def test_running_out_after_a_right_finish_task_is_nobodys_miss():
    episode = Episode(Fixed(low_battery='finish_task'), 0, quiet(robots=1))
    robot = episode.robots[0]
    robot.battery = 8.0
    episode._assign(robot)
    episode._decide_new()
    episode.incidents[0].correct = 'finish_task'
    episode._die(robot)
    assert [m['by'] for m in episode.stats['misses']] == ['system']


def test_running_out_after_a_wrong_finish_task_is_the_deciders_miss():
    episode = Episode(Fixed(low_battery='finish_task'), 0, quiet(robots=1))
    robot = episode.robots[0]
    robot.battery = 8.0
    episode._assign(robot)
    episode._decide_new()
    episode.incidents[0].correct = 'charge_now'
    episode._die(robot)
    assert [m['by'] for m in episode.stats['misses']] == ['supervisor']


def test_a_scan_decision_cancelled_by_a_dead_battery_is_not_reported_as_right():
    sup = Fixed(scan_failure='pick_anyway')
    episode = Episode(sup, 0, quiet(robots=1))
    robot = episode.robots[0]
    episode._assign(robot)
    episode._raise_scan(robot, 1)
    episode._decide_new()
    episode._die(robot)
    assert [outcome.ok for _, outcome in sup.outcomes] == [None]


def test_a_damaged_label_never_rescans_and_the_fleet_gives_up_after_the_cap():
    episode = Episode(Fixed(scan_failure='rescan'), 0, quiet(robots=1, scan_unreadable=1.0))
    robot = episode.robots[0]
    episode._assign(robot)
    episode._raise_scan(robot, 1)
    for _ in range(10):
        episode._decide_new()
        if robot.state == 'idle':
            break
        robot.timer = episode.time
        episode._timer_done(robot)
    assert len(episode.incidents) == episode.cfg.max_rescans
    assert episode.stats['skipped'] == 1 and robot.state == 'idle'
    # The guess belongs to the item: every attempt has the same right action.
    assert len({i.correct for i in episode.incidents.values()}) == 1
    low = [m for m in episode.stats['misses'] if m['severity'] == 'low']
    assert len(low) == (episode.incidents[0].correct != 'skip')


def test_never_ask_asks_nothing_and_always_ask_decides_nothing_alone():
    never = Episode(NeverAsk(), 2, SHORT).run()
    always = Episode(AlwaysAsk(), 2, SHORT).run()
    assert never['questions'] == 0
    assert never['incidents'] > 0
    assert not any(k.endswith(':act') for k in always if k.startswith('decisions_'))
    assert sum(always[f'supervisor_{s}'] for s in ('critical', 'high', 'medium', 'low')) == 0


def test_an_action_outside_the_incident_kind_is_refused():
    class Wrong(Supervisor):
        name = 'wrong'

        def decide(self, obs, ctx):
            return Decision.act('teleport')

    with pytest.raises(ValueError, match='teleport'):
        Episode(Wrong(), 0, SHORT).run()


def test_joining_a_question_of_another_kind_is_refused():
    class BadJoin(Supervisor):
        name = 'bad_join'

        def decide(self, obs, ctx):
            others = [q for q in ctx.pending if q.kind != obs.kind]
            return Decision.join(others[0].id) if others else Decision.ask()

    with pytest.raises(ValueError, match='joined'):
        Episode(BadJoin(), 0, Config(hours=1)).run()


def test_the_supervisor_gets_copies_it_cannot_change():
    class Mutate(Supervisor):
        name = 'mutate'

        def decide(self, obs, ctx):
            with pytest.raises(TypeError):
                obs.details['at_goal'] = False
            dict.__setitem__(obs.details, 'at_goal', False)
            object.__setattr__(obs, 'robot', 99)
            return Decision.act('reroute')

    episode = Episode(Mutate(), 0, quiet(robots=1))
    robot = episode.robots[0]
    episode._assign(robot)
    ghost = Obstacle(0, robot.pick, 'ghost', 10_000)
    episode.obstacles[0], episode.obstacle_cells[robot.pick] = ghost, ghost
    for _ in range(200):
        episode.tick()
        if episode.stats['abandoned']:
            break
    assert episode.incidents[0].obs.robot == 0 and episode.incidents[0].obs.details['at_goal']
    assert [m['severity'] for m in episode.stats['misses']] == ['low']


def test_outcomes_do_not_reveal_what_was_not_observable():
    for cls in ('person', 'box'):
        sup = Fixed(obstacle='reroute')
        episode = Episode(sup, 0, quiet(robots=1))
        robot = episode.robots[0]
        episode._assign(robot)
        obstacle = Obstacle(0, robot.pick, cls, 10_000)
        episode.obstacles[0], episode.obstacle_cells[robot.pick] = obstacle, obstacle
        while not sup.outcomes:
            episode.tick()
        assert [(o.ok, o.severity) for _, o in sup.outcomes] == [(None, None)]


def test_waiting_gives_no_verdict_on_the_obstacle():
    sup = Fixed(obstacle='wait')
    episode = Episode(sup, 0, quiet(robots=1, wait_timeout=10))
    robot = episode.robots[0]
    episode._assign(robot)
    obstacle = Obstacle(0, robot.pick, 'person', 10_000)
    episode.obstacles[0], episode.obstacle_cells[robot.pick] = obstacle, obstacle
    while len(sup.outcomes) < 2:
        episode.tick()
    assert {o.ok for _, o in sup.outcomes} == {None}


def test_right_actions_are_the_best_ones():
    from fleetattention.world import right_action
    assert right_action('person', at_goal=False) == 'reroute'  # driving around costs nothing in an aisle
    assert right_action('person', at_goal=True) == 'wait'
    assert right_action('box', at_goal=True) == 'reroute' and right_action('ghost', at_goal=False) == 'proceed'


@pytest.mark.parametrize('enough', [True, False])
def test_a_finish_task_decision_still_counts_when_the_line_is_dropped(enough):
    sup = Fixed(low_battery='finish_task')
    episode = Episode(sup, 0, quiet(robots=1))
    robot = episode.robots[0]
    robot.battery = 8.0
    episode._assign(robot)
    episode._decide_new()
    incident = episode.incidents[0]
    incident.correct = 'finish_task' if enough else 'charge_now'
    episode._give_up_pick(robot)
    assert episode.stats['abandoned'] == 1 and robot.finish_incident == 0 and not sup.outcomes
    episode._die(robot)  # on the way to the charger
    assert [o.ok for _, o in sup.outcomes] == [False]
    assert [m['by'] for m in episode.stats['misses']] == ['system' if enough else 'supervisor']


def test_replanning_a_drop_updates_the_task_and_picks_avoid_unreachable_goals():
    episode = Episode(NeverAsk(), 0, quiet(robots=1))
    robot = episode.robots[0]
    episode._assign(robot)
    old = robot.drop
    episode._go(robot, old, 'drop')
    episode._replan(robot)
    assert robot.drop == robot.goal != old
    robot.purpose, robot.goal = 'pick', robot.pick
    pick = robot.pick
    episode._replan(robot)
    for _ in range(20):
        episode._assign(robot)
        assert robot.pick != pick
        episode._abandon_task(robot)


def test_a_robot_queued_behind_a_working_robot_goes_elsewhere():
    episode = Episode(Fixed(deadlock='wait'), 0, quiet(robots=2))
    mover, worker = episode.robots
    place(episode, mover, (1, 1))
    place(episode, worker, (0, 1))
    worker.state, worker.timer = 'working', 10_000
    episode._go(mover, (0, 1), 'drop')
    for _ in range(40):
        episode._move(mover)
        episode.time += 1
    assert episode.stats['replanned'] == 1 and mover.goal != (0, 1)


def test_episodes_shorter_than_a_tick_are_refused():
    with pytest.raises(ValueError):
        Config(hours=0)


def test_rescans_that_were_right_but_failed_by_chance_are_nobodys_miss():
    config = quiet(robots=1, scan_unreadable=0.0, rescan_success=0.0, scan_overconfidence=1.0)
    episode = Episode(Fixed(scan_failure='rescan'), 0, config)
    robot = episode.robots[0]
    episode._assign(robot)
    episode._raise_scan(robot, 1)
    assert episode.incidents[0].correct == 'rescan'
    for _ in range(10):
        episode._decide_new()
        if robot.state == 'idle':
            break
        robot.timer = episode.time
        episode._timer_done(robot)
    assert episode.stats['skipped'] == 1
    assert [(m['severity'], m['by']) for m in episode.stats['misses']] == [('low', 'system')]


def test_a_joined_scan_question_gets_the_answer_but_not_the_identification():
    class AskThenJoin(Supervisor):
        name = 'ask_then_join'

        def decide(self, obs, ctx):
            return Decision.join(ctx.pending[0].id) if ctx.pending else Decision.ask()

    episode = Episode(AskThenJoin(), 0, quiet(robots=2, human_accuracy=1.0))
    for robot in episode.robots:
        episode._assign(robot)
        episode._raise_scan(robot, 1)
    for incident in episode.incidents.values():
        incident.correct, incident.data['guess_correct'], incident.data['unreadable'] = 'skip', False, True
    episode._decide_new()
    while episode.questions:
        episode.tick()
    assert [i.action for i in episode.incidents.values()] == ['identify', 'skip']
    assert episode.stats['skipped'] == 1 and not episode.stats['misses']


@pytest.mark.parametrize('cls', ['ghost', 'box'])
def test_a_robot_does_not_ask_again_about_an_obstacle_found_out_while_it_waited(cls):
    episode = Episode(Fixed(obstacle='wait'), 0, quiet(robots=1, wait_timeout=5))
    robot = episode.robots[0]
    episode._assign(robot)
    obstacle = Obstacle(0, robot.pick, cls, 10_000)
    episode.obstacles[0], episode.obstacle_cells[robot.pick] = obstacle, obstacle
    while robot.state != 'waiting':
        episode.tick()
    obstacle.revealed = True
    for _ in range(10):
        episode.tick()
    assert len(episode.incidents) == 1
    if cls == 'ghost':
        assert robot.passing == 0
    else:
        assert episode.stats['abandoned'] == 1


def test_without_pick_face_obstacles_none_lands_on_a_pick_face():
    for seed in range(4):
        episode = Episode(NeverAsk(), seed, Config(obstacle_at_pick=0.0))
        assert episode.schedule and not [cell for _, cell, _, _ in episode.schedule if cell in episode.pick_weight]


@pytest.mark.parametrize('field, value', [
    ('hours', float('inf')), ('obstacles_per_hour', float('nan')), ('human_accuracy', 1.5), ('scan_failure', -.1),
    ('classifier_accuracy', {'box': float('nan'), 'person': .5, 'ghost': .5}),
    ('motion_detected', {'box': 2, 'person': .5, 'ghost': .5}), ('age_range', (2.0, 1.0)),
    ('obstacle_lifetime', {'box': (10, 5), 'person': (1, 2), 'ghost': (1, 2)}), ('max_rescans', 0)])
def test_impossible_settings_are_refused(field, value):
    with pytest.raises(ValueError, match=field):
        Config(**{field: value})


def test_two_robots_meeting_head_on_in_a_one_lane_aisle_both_get_through():
    """Row 0 is a single lane between cross aisles at x = 7 and 14: one robot has to back out."""
    episode = Episode(Fixed(deadlock='yield'), 0, quiet(robots=2))
    a, b = episode.robots
    place(episode, a, (8, 0))
    place(episode, b, (13, 0))
    episode._go(a, (20, 0), 'charge')
    episode._go(b, (1, 0), 'charge')
    reached = set()
    for _ in range(300):
        episode.tick()
        reached |= {r.id for r in (a, b) if r.cell == r.goal}
        if reached == {0, 1}:
            break
    assert reached == {0, 1}


@pytest.mark.parametrize('name, seed', [('always_safe_reroute', 2), ('motion_aware', 5)])
def test_no_robot_shuffles_between_two_cells_for_two_minutes(name, seed):
    """Seeds on which robots used to trap each other at station bays and in one-lane aisles."""
    from collections import deque
    episode = Episode(by_name(name), seed, Config(hours=.15))
    recent = {robot.id: deque(maxlen=120) for robot in episode.robots}
    for _ in range(episode.duration):
        episode.tick()
        for robot in episode.robots:
            recent[robot.id].append((robot.cell, robot.state))
            window = recent[robot.id]
            assert not (len(window) == 120 and all(state == 'moving' for _, state in window)
                        and len({cell for cell, _ in window}) <= 2), (robot.id, episode.time)


def test_obstacle_attempts_count_again_after_the_robot_got_through():
    episode = Episode(Fixed(obstacle='wait'), 0, quiet(robots=1))
    robot = episode.robots[0]
    episode._assign(robot)
    cell = robot.pick
    for index in range(3):
        obstacle = Obstacle(index, cell, 'person', 10_000)
        episode.obstacles[index], episode.obstacle_cells[cell] = obstacle, obstacle
        episode._raise_obstacle(robot, obstacle)
        del episode.obstacles[index], episode.obstacle_cells[cell]
    assert [i.obs.attempt for i in episode.incidents.values()] == [1, 2, 3]
    episode._arrive(robot)
    obstacle = Obstacle(3, cell, 'person', 10_000)
    episode._raise_obstacle(robot, obstacle)
    assert episode.incidents[3].obs.attempt == 1


@pytest.mark.parametrize('overrides', [
    {'hot_share': 1.0, 'hot_picks': .01}, {'scan_failure': 1.0, 'scan_unreadable': 1.0}, {'human_accuracy': 0.0},
    {'obstacle_at_pick': 1.0, 'person_in_human_zone': 0.0}, {'rescan_success': 1.0, 'scan_failure': 1.0}])
def test_extreme_but_legal_settings_run(overrides):
    Episode(by_name('reference'), 0, Config(hours=.05, **overrides)).run()


GOLDEN = {  # seed 0, half an hour: (questions, recoveries, delivered/h, supervisor low misses, incidents)
    'cost_aware': (17, 1, 988.0, 0, 68),
    'always_safe_reroute': (0, 0, 990.0, 5, 89),
    'reference': (37, 1, 896.0, 0, 73),
}


@pytest.mark.parametrize('name', GOLDEN)
def test_golden_numbers(name):
    """Pins the simulation. If a change moves these on purpose, update them and rerun everything in RESULTS.md."""
    row = Episode(by_name(name), 0, Config(hours=.5)).run()
    assert (row['questions'], row['recoveries'], row['delivered_per_hour'], row['supervisor_low'],
            row['incidents']) == GOLDEN[name]


def test_a_robot_queued_outside_a_full_bay_gives_way():
    # The station (0, 1) opens onto (1, 1), and (1, 0) and (1, 2) are taken: the robots at (1, 1) and in the station
    # can only leave past the robot queued at (2, 1) for the station.
    episode = Episode(Fixed(deadlock='wait'), 0, quiet(robots=5))
    entrance, queued, inside, *walls = episode.robots
    for robot, cell in zip(episode.robots, [(1, 1), (2, 1), (0, 1), (1, 0), (1, 2)]):
        place(episode, robot, cell)
    episode._go(entrance, (4, 2), 'drop')
    episode._go(inside, (4, 0), 'drop')
    episode._go(queued, (0, 1), 'drop')
    for _ in range(120):
        for robot in (entrance, queued, inside):
            if robot.state == 'moving':
                episode._move(robot)
            elif robot.state == 'waiting' and episode.time >= robot.timer:
                episode._timer_done(robot)
        episode._decide_new()
        episode.time += 1
    assert entrance.cell == (4, 2) and inside.cell == (4, 0)


def test_yielding_in_a_deadlock_never_steps_into_a_bay():
    # The only free cell next to the robot is the station (0, 1).
    episode = Episode(Fixed(deadlock='yield'), 0, quiet(robots=4))
    robot, blocker, *walls = episode.robots
    for r, cell in zip(episode.robots, [(1, 1), (2, 1), (1, 0), (1, 2)]):
        place(episode, r, cell)
    episode._go(robot, (4, 1), 'drop')
    episode._raise_deadlock(robot, blocker)
    episode._decide_new()
    assert episode.stats['incidents']['deadlock'] == 1
    assert robot.cell not in episode.bays


def test_wrong_types_and_shapes_in_the_settings_are_refused():
    for bad in ({'robots': 1.5}, {'max_rescans': 1.5}, {'robots': 0}, {'hours': True}, {'age_range': [-1, -1]},
                {'obstacle_lifetime': {'box': [-1, 2], 'person': (1, 2), 'ghost': (1, 2)}},
                {'obstacle_mix': (('box', 'x'),)}, {'obstacle_mix': (('box', 0), ('box', 1))},
                {'classifier_accuracy': {'box': .5}}):
        with pytest.raises(ValueError):
            Config(**bad)
    assert Config(age_range=[1, 2]).age_range == (1.0, 2.0)


def test_every_pick_face_weightless_still_places_obstacles_and_orders():
    Episode(NeverAsk(), 0, Config(hours=.1, hot_picks=1.0, hot_share=0.0, obstacles_per_hour=200.0)).run()


def held_in_bay(episode, robot):
    """In a bay whose way out is taken by a robot that is not moving: waiting there is right, not a jam."""
    if robot.cell not in episode.bays:
        return False
    occupant = episode.occupied.get(next(iter(episode.layout.neighbors(robot.cell))))
    return occupant is not None and episode.robots[occupant].state != 'moving'


def longest_freeze(name, seed):
    """The longest time any robot spent moving without leaving its cell in a two-hour episode, not counting robots
    held in a bay."""
    episode = Episode(by_name(name), seed)
    since, longest = {r.id: (r.cell, 0) for r in episode.robots}, 0
    while episode.time < episode.duration:
        episode.tick()
        for r in episode.robots:
            if r.state != 'moving' or r.cell != since[r.id][0] or held_in_bay(episode, r):
                since[r.id] = (r.cell, episode.time)
            longest = max(longest, episode.time - since[r.id][1])
    return longest


@pytest.mark.parametrize('name, seed', [('reference', 3), ('reference', 4), ('never_ask', 13), ('always_ask', 6),
                                        ('always_safe', 0), ('always_safe', 20), ('threshold@0.8', 3)])
def test_no_robot_is_stuck_for_long_in_episodes_that_once_jammed(name, seed):
    # Robots queued outside a full bay, or behind robots that stayed put, once froze for ten minutes to an hour or
    # more on these seeds.
    assert longest_freeze(name, seed) < 600


def reaches(episode, robot, cell, seconds):
    """Whether the robot gets to the cell within the given seconds (it takes another task once there)."""
    for _ in range(seconds):
        episode.tick()
        if robot.cell == cell:
            return True
    return False


def test_two_robots_in_a_one_lane_aisle_settle_who_backs_out():
    # A dead robot shuts the west end of the one-lane aisle in row 0: the robot at (10, 0) can only leave eastwards,
    # through the robot that wants its cell. They once took turns stepping back for ever.
    episode = Episode(Fixed(), 0, quiet(robots=3))
    other, shut_in, dead = episode.robots
    place(episode, dead, (9, 0)); dead.state = 'dead'
    place(episode, shut_in, (10, 0)); place(episode, other, (12, 0))
    episode._go(shut_in, (0, 11), 'drop')
    episode._go(other, (10, 0), 'drop')
    assert reaches(episode, other, (10, 0), 120)
    assert not episode.incidents and shut_in.cell[1] > 0


def test_a_standoff_the_traffic_rules_cannot_settle_is_escalated():
    # Dead robots shut both ends of the aisle: neither robot can step aside.
    episode = Episode(Fixed(), 0, quiet(robots=4))
    a, b, *dead = episode.robots
    for robot, cell in zip(dead, [(9, 0), (12, 0)]):
        place(episode, robot, cell); robot.state = 'dead'
    place(episode, a, (10, 0)); place(episode, b, (11, 0))
    episode._go(a, (11, 0), 'drop')
    episode._go(b, (10, 0), 'drop')
    for _ in range(episode.cfg.deadlock_after + 2):
        episode.tick()
    assert episode.stats['incidents'] == {'deadlock': 1}


def test_a_robot_behind_one_waiting_for_an_answer_waits_then_goes_around_without_asking():
    # The robot at (10, 0) waits for the person; the one behind it in the one-lane aisle has to go the long way.
    episode = Episode(Fixed(), 0, quiet(robots=2, human_median=10_000, human_spread=0))
    stuck, behind = episode.robots
    place(episode, stuck, (10, 0)); place(episode, behind, (11, 0))
    episode._go(stuck, (8, 0), 'drop')
    episode._raise(stuck, 'deadlock', (9, 0), 1, 'yield', .9, 'yield', {})
    episode._go(behind, (8, 0), 'drop')
    for _ in range(4 * episode.cfg.deadlock_after - 1):
        episode.tick()
    assert behind.cell == (11, 0)
    assert reaches(episode, behind, (8, 0), 60) and len(episode.incidents) == 1


def test_no_obstacle_is_left_in_a_bay_entrance():
    episode = Episode(NeverAsk(), 0, Config(obstacles_per_hour=2000, hours=.5))
    entrances = {c for bay in episode.bays for c in episode.layout.neighbors(bay)}
    assert episode.schedule and not entrances & {cell for _, cell, _, _ in episode.schedule}


def test_a_wrong_answer_on_a_joined_incident_with_another_cause_is_the_supervisors_miss():
    class AskThenJoin(Supervisor):
        name = 'ask_then_join'

        def decide(self, obs, ctx):
            return Decision.join(ctx.pending[0].id) if ctx.pending else Decision.ask()

    class Wrong:
        """The person gets it wrong and says 'proceed'."""
        def random(self):
            return 1.0

        def choice(self, options):
            return 'proceed'

    episode = Episode(AskThenJoin(), 0, quiet(robots=2))
    for robot, cell in zip(episode.robots, [(10, 3), (20, 3)]):
        box = Obstacle(robot.id, (cell[0] + 1, cell[1]), 'box', 10_000)
        episode.obstacles[box.id], episode.obstacle_cells[box.cell] = box, box
        place(episode, robot, cell)
        episode._go(robot, (cell[0] + 3, cell[1]), 'drop')
        episode._raise_obstacle(robot, box)
    episode._decide_new()
    episode.rng['human'] = Wrong()
    episode._answer(episode.questions.pop(0))
    assert [(m['severity'], m['by']) for m in episode.stats['misses']] == [('medium', 'human'), ('medium', 'supervisor')]


@pytest.mark.parametrize('name', ['cost_aware', 'always_ask'])
def test_a_robot_shut_in_beside_an_obstacle_does_not_raise_it_over_and_over(name):
    # A known box behind it and a person ahead in the one-lane aisle: rerouting leaves no way out. Planning once went
    # straight back through the suspected cell, raising the obstacle every second.
    episode = Episode(by_name(name), 1, quiet(robots=1))
    robot = episode.robots[0]
    place(episode, robot, (25, 0))
    for obstacle in (Obstacle(0, (23, 0), 'box', 10_000, revealed=True), Obstacle(1, (26, 0), 'person', 10_000)):
        episode.obstacles[obstacle.id], episode.obstacle_cells[obstacle.cell] = obstacle, obstacle
    episode._go(robot, (0, 1), 'drop')
    for _ in range(1800):
        episode.tick()
    assert episode.stats['incidents']['obstacle'] <= 10


def test_a_robot_in_a_bay_behind_a_dead_robot_waits_and_keeps_its_task():
    episode = Episode(NeverAsk(), 0, quiet(robots=2, recovery_time=10_000))
    inside, dead = episode.robots
    station = episode.layout.stations[0]
    place(episode, inside, station)
    place(episode, dead, (station[0] + 1, station[1])); episode._die(dead)
    episode._assign(inside)
    pick = inside.pick
    for _ in range(600):
        episode.tick()
    assert inside.cell == station and inside.pick == pick and not episode.stats['replanned']


def longest_shuffle(name, seed):
    """The most times in a row any robot moved back to the cell it had just left."""
    episode = Episode(by_name(name), seed)
    trail = {r.id: [r.cell] for r in episode.robots}
    run, longest = dict.fromkeys(trail, 0), 0
    while episode.time < episode.duration:
        episode.tick()
        for r in episode.robots:
            cells = trail[r.id]
            if cells[-1] != r.cell:
                cells.append(r.cell)
                run[r.id] = run[r.id] + 1 if len(cells) >= 3 and cells[-3] == r.cell else 0
                longest = max(longest, run[r.id])
    return longest


@pytest.mark.parametrize('name, seed', [('always_safe_reroute', 8), ('threshold@0.6', 19)])
def test_robots_do_not_shuffle_back_and_forth_for_long(name, seed):
    # Two robots that had both stopped giving way once shuffled around each other for ten minutes on seed 8; a
    # robot queued outside a bay stepped aside and back for five minutes on seed 19.
    assert longest_shuffle(name, seed) < 60


def test_a_robot_in_a_bay_behind_one_waiting_for_an_answer_waits_and_keeps_its_task():
    episode = Episode(Fixed(), 0, quiet(robots=2, human_median=10_000, human_spread=0))
    inside, asking = episode.robots
    station = episode.layout.stations[0]
    place(episode, inside, station)
    place(episode, asking, (station[0] + 1, station[1]))
    episode._go(asking, (4, 4), 'drop')
    episode._raise(asking, 'deadlock', (2, 1), 1, 'yield', .9, 'yield', {})
    episode._decide_new()
    episode._assign(inside)
    pick = inside.pick
    for _ in range(600):
        episode.tick()
    assert inside.cell == station and inside.pick == pick and not episode.stats['replanned']


def test_a_detour_around_a_robot_that_stays_put_is_not_cut_short():
    # The robot at (10, 0) waits for the person; the one behind it in the one-lane aisle is sent the long way round,
    # which first leads away from its goal. The no-headway rule once gave the line up halfway.
    episode = Episode(Fixed(), 0, quiet(robots=2, human_median=10_000, human_spread=0, no_headway_after=70))
    stuck, behind = episode.robots
    place(episode, stuck, (10, 0)); place(episode, behind, (11, 0))
    episode._raise(stuck, 'deadlock', (9, 0), 1, 'yield', .9, 'yield', {})
    episode._go(behind, (8, 0), 'drop')
    assert reaches(episode, behind, (8, 0), 4 * episode.cfg.deadlock_after + 40)
    assert not episode.stats['replanned']


def test_charging_first_is_never_a_miss():
    episode = Episode(Fixed(low_battery='charge_now'), 0, quiet(robots=1))
    robot = episode.robots[0]
    robot.battery = 8.0
    episode._assign(robot)
    episode.incidents[0].correct = 'finish_task'
    episode._decide_new()
    assert episode.stats['abandoned'] == 1 and not episode.stats['misses'] and robot.purpose == 'charge'


def test_every_charging_session_starts_with_docking():
    episode = Episode(NeverAsk(), 0, quiet(robots=1))
    robot = episode.robots[0]
    robot.battery = 99.0
    place(episode, robot, episode.layout.chargers[0])
    episode._go(robot, robot.cell, 'charge')
    episode.tick()
    assert robot.state == 'charging'
    for _ in range(episode.cfg.docking_time - 1):
        episode.tick()
    assert robot.battery == 99.0
    for _ in range(3):
        episode.tick()
    assert robot.battery == 100.0 and robot.state != 'charging'

def test_a_question_about_an_obstacle_that_has_gone_is_taken_back():
    episode = Episode(Fixed(), 0, quiet(robots=2, human_median=10_000, human_spread=0))
    for robot, cell in zip(episode.robots, [(10, 3), (20, 3)]):
        obstacle = Obstacle(robot.id, (cell[0] + 1, cell[1]), 'person', 5 + robot.id)
        episode.obstacles[obstacle.id], episode.obstacle_cells[obstacle.cell] = obstacle, obstacle
        place(episode, robot, cell)
        episode._go(robot, (cell[0] + 3, cell[1]), 'drop')
        episode._raise_obstacle(robot, obstacle)
    episode._decide_new()
    for _ in range(10):
        episode.tick()
    # The person is still on the first question; the second, queued, is taken back and its robot moves on.
    assert list(episode.questions) == [0] and not episode.queue
    assert episode.robots[0].state == 'incident' and episode.robots[1].state != 'incident'
    assert episode.stats['questions'] == 2


def test_when_the_asked_about_obstacle_goes_the_joined_incidents_go_with_the_question():
    class AskThenJoin(Supervisor):
        name = 'ask_then_join'

        def decide(self, obs, ctx):
            return Decision.join(ctx.pending[-1].id) if len(ctx.pending) > 1 else Decision.ask()

    episode = Episode(AskThenJoin(), 0, quiet(robots=3, human_median=10_000, human_spread=0))
    # The first question keeps the person busy; the second is about A, and B (elsewhere, staying) joins it.
    for robot, cell, until in zip(episode.robots, [(4, 3), (10, 3), (20, 3)], [10_000, 5, 10_000]):
        obstacle = Obstacle(robot.id, (cell[0] + 1, cell[1]), 'person', until)
        episode.obstacles[obstacle.id], episode.obstacle_cells[obstacle.cell] = obstacle, obstacle
        place(episode, robot, cell)
        episode._go(robot, (cell[0] + 3, cell[1]), 'drop')
        episode._raise_obstacle(robot, obstacle)
        episode._decide_new()
    assert episode.questions[1].incidents == [1, 2]
    for _ in range(6):
        episode.tick()
    # B's robot raises its obstacle again, which makes a question of its own about it.
    assert 1 not in episode.questions and episode.stats['withdrawn'] == 1
    assert not episode.incidents[1].open and not episode.incidents[2].open and episode.incidents[2].question is None
    assert [i.obs.target for i in episode.incidents.values() if i.open and i.obs.robot == 2] == [(21, 3)]


def test_two_robots_asking_about_one_obstacle_that_goes_lose_the_question_together():
    class AskThenJoin(Supervisor):
        name = 'ask_then_join'

        def decide(self, obs, ctx):
            return Decision.join(ctx.pending[-1].id) if len(ctx.pending) > 1 else Decision.ask()

    episode = Episode(AskThenJoin(), 0, quiet(robots=3, human_median=10_000, human_spread=0))
    busy, a, b = episode.robots
    stays = Obstacle(0, (5, 3), 'person', 10_000)
    goes = Obstacle(1, (11, 3), 'person', 5)
    for obstacle in (stays, goes):
        episode.obstacles[obstacle.id], episode.obstacle_cells[obstacle.cell] = obstacle, obstacle
    # The first question keeps the person busy; a and b, on either side of one obstacle, share the second.
    for robot, cell, obstacle in ((busy, (4, 3), stays), (a, (10, 3), goes), (b, (12, 3), goes)):
        place(episode, robot, cell)
        episode._go(robot, (cell[0] + 2 if robot is not b else cell[0] - 2, cell[1]), 'drop')
        episode._raise_obstacle(robot, obstacle)
        episode._decide_new()
    assert episode.questions[1].incidents == [1, 2]
    for _ in range(6):
        episode.tick()
    assert list(episode.questions) == [0] and episode.stats['withdrawn'] == 1
    assert a.state != 'incident' and b.state != 'incident'
