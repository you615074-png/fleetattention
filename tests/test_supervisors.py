from fleetattention.metrics import PROFILES, aggregate, cost, paired, pareto, summarize, t95
from fleetattention.model import ACTIONS, Answer, Context, Observation, Outcome, PendingQuestion
from fleetattention.supervisors import ABLATIONS, Reference, by_name
from fleetattention.world import Config, Episode


def obs(kind='obstacle', confidence=.99, suggested='proceed', target=(10, 3), attempt=1, human_zone=False,
        incident=0, **details):
    return Observation(incident, kind, 0, 0, (9, 3), target, human_zone, attempt, suggested, confidence, ACTIONS[kind],
                       details or {'motion': False, 'at_goal': False})


def calibrated(kind='obstacle', right=True):
    sup = Reference(audit=0)
    sup.reset(0)
    for _ in range(sup.calibration):
        o = obs(kind, confidence=.9, suggested=ACTIONS[kind][0])
        sup.on_answer(o, Answer(0, ACTIONS[kind][0] if right else ACTIONS[kind][1], o.incident))
    return sup


IDLE = Context(0, (), 0)


def test_reference_asks_while_shadowing_then_acts_when_calibrated():
    fresh = Reference(audit=0)
    fresh.reset(0)
    assert fresh.decide(obs(), IDLE).type == 'ask'
    assert calibrated().decide(obs(), IDLE).action == 'proceed'


def test_reference_keeps_asking_when_the_robot_was_wrong_during_calibration():
    assert calibrated(right=False).decide(obs(), IDLE).type == 'ask'


def test_reference_never_drives_through_an_obstacle_with_motion_or_near_people():
    sup = calibrated()
    assert sup.decide(obs(motion=True), IDLE).type == 'ask'
    assert sup.decide(obs(human_zone=True), IDLE).type == 'ask'


def test_reference_joins_a_pending_question_about_the_same_cause():
    pending = (PendingQuestion(7, 'obstacle', (10, 3), (1,), 0),)
    decision = calibrated().decide(obs(), Context(0, pending, 1))
    assert decision.type == 'join' and decision.question == 7


def test_reference_takes_the_safe_default_when_the_person_is_busy():
    sup = calibrated()
    decision = sup.decide(obs(confidence=.5), Context(0, (), sup.busy_queue))
    assert decision.type == 'act' and decision.action == 'wait'


def test_reference_escalates_the_third_attempt_and_resolves_deadlocks_alone():
    sup = calibrated()
    assert sup.decide(obs(attempt=3), IDLE).type == 'ask'
    assert sup.decide(obs('deadlock', suggested='yield', confidence=.1), IDLE).action == 'yield'


def test_threshold_never_splits_samples_of_equal_confidence():
    sup = Reference()
    sup.reset(0)
    sup.samples['obstacle'] = [(.9, True)] * 3 + [(.9, False)] * 3
    assert sup.threshold('obstacle') == float('inf')
    sup.samples['obstacle'] = [(.95, True)] * 4 + [(.9, False)] * 3
    assert sup.threshold('obstacle') == .95


def test_reference_learns_only_from_its_own_questions_and_verifiable_outcomes():
    sup = Reference()
    sup.reset(0)
    sup.on_answer(obs(incident=5), Answer(0, 'wait', incident=4))     # a joined incident
    sup.on_outcome(obs(suggested='reroute'), Outcome('reroute', None))  # a detour shows nothing
    assert sup.samples['obstacle'] == []
    sup.on_answer(obs(incident=4), Answer(0, 'proceed', incident=4))
    sup.on_outcome(obs(suggested='wait'), Outcome('wait', False))
    assert sup.samples['obstacle'] == [(.99, True), (.99, False)]


def test_by_name():
    assert by_name('threshold@0.8').threshold == .8
    assert by_name('reference').name == 'reference'
    assert by_name('always_safe_reroute').actions['obstacle'] == 'reroute'
    for feature in ABLATIONS:
        assert by_name(f'reference-{feature}').name == f'reference-{feature}'
    assert not by_name('reference-join').join and by_name('reference-busy').busy_queue is None


def test_pareto_front_on_three_axes():
    rows = [
        {'supervisor': 'a', 'interruptions_per_hour': 1, 'harm_per_hour': 10, 'delivered_per_hour': 500},
        {'supervisor': 'b', 'interruptions_per_hour': 5, 'harm_per_hour': 1, 'delivered_per_hour': 500},
        {'supervisor': 'c', 'interruptions_per_hour': 6, 'harm_per_hour': 2, 'delivered_per_hour': 400},
        {'supervisor': 'd', 'interruptions_per_hour': 6, 'harm_per_hour': 2, 'delivered_per_hour': 900},
        {'supervisor': 'd', 'interruptions_per_hour': 6, 'harm_per_hour': 2, 'delivered_per_hour': 900},
    ]
    assert pareto(rows) == {0, 1, 3, 4}  # by row, so two supervisors with one name stay apart


def test_aggregate_means_and_standard_errors():
    rows = [{'supervisor': 's', 'seed': i, 'interruptions_per_hour': v, 'harm_per_hour': 0.0,
             'delivered_per_hour': 2 * v} for i, v in enumerate((1.0, 3.0))]
    out = aggregate(rows)
    assert out['seeds'] == 2 and out['interruptions_per_hour'] == 2.0 and 'seed' not in out
    assert out['interruptions_per_hour_se'] == 1.0 and out['delivered_per_hour_se'] == 2.0


def test_summary_counts_only_the_supervisors_misses_as_harm():
    episode = Episode(by_name('never_ask'), 0, Config(hours=.01, obstacles_per_hour=0))
    episode.run()
    episode.stats['misses'] = [{'severity': s, 'by': by} for s, by in
                               (('critical', 'supervisor'), ('low', 'supervisor'), ('high', 'human'), ('high', 'system'))]
    episode.stats['delivered'], episode.stats['mispicked'] = 5, 2
    row = summarize(episode)
    hours = episode.duration / 3600
    assert row['harm_per_hour'] == (100 + .5) / hours
    assert row['delivered_per_hour'] == 3 / hours


def test_reference_does_not_join_old_or_gated_questions():
    sup = calibrated()
    pending = (PendingQuestion(7, 'obstacle', (10, 3), (1,), 0),)
    assert sup.decide(obs(), Context(sup.join_window, pending, 1)).type != 'join'
    gated = sup.decide(obs(motion=True), Context(5, pending, 1))
    assert gated.type == 'act' and gated.action == 'wait'


def test_one_shared_threshold_without_per_kind_calibration():
    sup = Reference(per_kind=False, shared_target=.9)
    sup.reset(0)
    sup.samples['obstacle'] = [(.9, True)] * 9 + [(.9, False)]
    sup.samples['scan_failure'] = []
    assert sup.threshold('scan_failure') == .9 == sup.threshold('obstacle')


def test_reference_records_why_it_asked():
    fresh = Reference()
    fresh.reset(0)
    fresh.decide(obs(), IDLE)
    assert fresh.reasons == {'shadow': 1} and fresh.report() == {'reason_shadow': 1}


def test_the_patient_baselines_wait_at_the_pick_face_before_giving_up():
    patient = by_name('patient')
    assert patient.decide(obs(at_goal=True, attempt=2), IDLE).action == 'wait'
    assert patient.decide(obs(at_goal=True, attempt=3), IDLE).action == 'reroute'
    assert patient.decide(obs(at_goal=False), IDLE).action == 'reroute'
    assert by_name('patient@0').decide(obs(at_goal=True), IDLE).action == 'reroute'
    motion = by_name('motion_aware')
    assert motion.decide(obs(at_goal=True, motion=True), IDLE).action == 'wait'
    assert motion.decide(obs(at_goal=True, motion=False), IDLE).type == 'ask'


def test_caution_and_attention_trade_off():
    """Neither never asking nor asking where caution is expensive may dominate the other: never asking must cost
    harm, and asking must cost attention. If one dominated, the benchmark would have a trivial answer. And the price
    of attention must decide between them: where it is cheap a supervisor that asks is best, where it is scarce one
    that never asks."""
    config = Config(hours=1)
    never, asking = ('always_safe_reroute', 'patient'), ('cost_aware', 'motion_aware', 'staged')
    rows = {name: aggregate([Episode(by_name(name), seed, config).run() for seed in range(2)])
            for name in never + asking}
    for quiet_one in never:
        for asker in asking:
            assert rows[quiet_one]['harm_per_hour'] > rows[asker]['harm_per_hour']
            assert rows[quiet_one]['interruptions_per_hour'] < rows[asker]['interruptions_per_hour']
    best = lambda profile: min(rows, key=lambda name: cost(rows[name], PROFILES[profile]))
    assert best('attention_cheap') in asking and best('attention_scarce') in never


def test_paired_differences():
    base = [{'seed': i, 'x': v} for i, v in enumerate((1.0, 2.0, 3.0))]
    other = [{'seed': i, 'x': v} for i, v in enumerate((2.0, 4.0, 3.0))]
    mean, se, low, high = paired(other, base, 'x')
    assert mean == 1.0 and abs(se - (1 / 3) ** .5) < 1e-9 and abs(high - (1 + 4.303 * se)) < 1e-3 * se


def test_t_quantiles_match_the_tables():
    for df, value in ((1, 12.706), (4, 2.776), (9, 2.262), (30, 2.042), (31, 2.040), (120, 1.980)):
        assert abs(t95(df) - value) < 1e-3


def test_staged_waits_three_times_rescans_twice_and_charges_first():
    sup, ctx = by_name('staged'), Context(0, (), 0)
    act = lambda o: (lambda d: d.action if d.type == 'act' else d.type)(sup.decide(o, ctx))
    pick_face = {'motion': False, 'at_goal': True}
    assert [act(obs(attempt=a, **pick_face)) for a in (1, 2, 3, 4)] == ['wait', 'wait', 'wait', 'ask']
    assert act(obs()) == 'reroute'
    assert [act(obs('scan_failure', attempt=a)) for a in (1, 2, 3)] == ['rescan', 'rescan', 'ask']
    assert act(obs('low_battery', battery=90.0, estimated_need=4.5)) == 'charge_now'
    assert act(obs('deadlock')) == 'yield'


def test_interruptions_are_questions_plus_recoveries():
    episode = Episode(by_name('never_ask'), 0, Config(hours=.01, obstacles_per_hour=0))
    episode.run()
    episode.stats['questions'], episode.stats['recoveries'] = 3, 2
    assert summarize(episode)['interruptions_per_hour'] == 5 / (episode.duration / 3600)


def test_a_threshold_needs_at_least_three_samples_at_or_above_it():
    sup = Reference()
    sup.reset(0)
    sup.samples['obstacle'] = [(.99, True)] * 2 + [(.5, False)] * 4
    assert sup.threshold('obstacle') == float('inf')
    sup.samples['obstacle'] = [(.99, True)] * 3 + [(.5, False)] * 3
    assert sup.threshold('obstacle') == .99


def test_reference_audits_a_share_of_what_it_would_do_alone():
    for audit, expected in ((0.0, 'act'), (1.0, 'ask')):
        sup = calibrated()
        sup.audit = audit
        assert sup.decide(obs(), IDLE).type == expected
