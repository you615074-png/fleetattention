# Results: phase 1

Commands, all with 10 seeds of 2 simulated hours, 24 robots and the default `Config` unless stated:

```sh
python3 -m fleetattention sweep --seeds 10                       # public seeds 0 to 9
python3 -m fleetattention ablate --seeds 10                      # also prints the paired differences below
python3 -m fleetattention sweep --seeds 10 --secret-seeds --out results/keyed
python3 -m fleetattention sweep --seeds 10 --set obstacle_at_pick=0 --set scan_unreadable=0 --out results/sensitivity
```

Raw numbers are in `results/` (not committed; rerun to reproduce, except the secret-seed run, whose key is gone).

| supervisor | interrupt/h | harm/h | delivered/h | critical/ep | high/ep | medium/ep | low/ep | person busy | wait s | front |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|
| always_ask | 93.3 ± 2.3 | 0.0 | 923 ± 10 | 0.0 | 0.0 | 0.0 | 0.0 | 78% | 100 | * |
| threshold@0.99 | 85.2 ± 1.9 | 0.1 ± 0.0 | 948 ± 11 | 0.0 | 0.0 | 0.1 | 0.0 | 75% | 94 | * |
| threshold@0.95 | 69.8 ± 2.6 | 11.3 ± 2.8 | 970 ± 13 | 0.0 | 2.1 | 1.6 | 0.0 | 65% | 90 | |
| threshold@0.9 | 58.4 ± 2.0 | 32.8 ± 3.3 | 951 ± 12 | 0.0 | 6.2 | 3.5 | 0.0 | 68% | 135 | |
| threshold@0.85 | 47.4 ± 1.8 | 52.1 ± 7.5 | 948 ± 15 | 0.1 | 8.9 | 5.2 | 0.0 | 73% | 183 | |
| threshold@0.8 | 40.9 ± 1.5 | 70.2 ± 10.0 | 950 ± 16 | 0.3 | 10.4 | 6.4 | 0.0 | 69% | 191 | |
| threshold@0.7 | 27.1 ± 0.9 | 104.7 ± 14.1 | 971 ± 18 | 0.7 | 12.7 | 12.4 | 0.0 | 70% | 236 | |
| threshold@0.6 | 19.6 ± 0.5 | 168.8 ± 19.6 | 984 ± 14 | 1.6 | 15.8 | 19.3 | 0.4 | 73% | 243 | |
| never_ask | 8.2 ± 0.6 | 197.6 ± 22.9 | 1023 ± 9 | 2.1 | 15.6 | 29.0 | 0.5 | 64% | 0 | |
| always_safe | 0.6 ± 0.1 | 11.8 ± 0.6 | 867 ± 18 | 0.0 | 0.0 | 0.0 | 47.1 | 5% | 0 | * |
| always_safe_reroute | 0.3 ± 0.1 | 15.2 ± 0.7 | 1057 ± 8 | 0.0 | 0.0 | 0.0 | 60.9 | 3% | 0 | * |
| patient | 0.3 ± 0.1 | 14.8 ± 0.5 | 1051 ± 9 | 0.0 | 0.0 | 0.0 | 59.1 | 3% | 0 | * |
| cost_aware | 23.4 ± 1.0 | 10.2 ± 0.3 | 1056 ± 9 | 0.0 | 0.0 | 0.0 | 41.0 | 21% | 38 | * |
| motion_aware | 22.9 ± 0.9 | 10.3 ± 0.3 | 1058 ± 9 | 0.0 | 0.0 | 0.0 | 41.3 | 19% | 34 | * |
| staged | 18.1 ± 0.9 | 5.9 ± 0.4 | 1049 ± 8 | 0.0 | 0.0 | 0.0 | 23.7 | 16% | 35 | * |
| **reference** | 62.2 ± 1.3 | 4.8 ± 1.2 | 1003 ± 9 | 0.0 | 0.7 | 1.0 | 3.2 | 61% | 58 | * |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors. With three
axes the front is wide: most supervisors that are best at something are on it, and the cost profiles below are
what ranks them. Interruptions are questions plus recoveries of robots whose battery ran out, which is why no
supervisor is at zero. Harm counts only the supervisor's own misses; misses that follow the person's wrong answers
and misses nobody could have avoided (a battery that ran out after a right call, rescans that were right but failed
by chance) are counted apart (`human_*`, `system_*` in the CSV). Each low miss is one order line failed
needlessly, so low/ep divided by 2 is lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 78% of the time, a question waits more than a
   minute and a half, and the fleet delivers 10% less than when nobody asks, because robots stand still while their
   questions wait. Following the robot's suggestion without asking (`never_ask`) is far worse: it drives into
   people, picks wrong items and runs batteries flat (197.6 harm an hour).
2. **Every cautious default has a price, and three incident kinds set it.** `always_safe_reroute` drives around
   every obstacle, rescans until the fleet gives the item up, and charges at the first battery warning. It
   interrupts less than once an hour, never drives into anything, and delivers as much as any supervisor. Its price
   is 30 order lines an hour that fail needlessly (`supervisor_low_*` columns):
   - 20.7 from charging first although the battery would have lasted the task (about three in five low-battery
     warnings);
   - 8.5 from items the fleet skipped after three rescans although the scanner's guess was right;
   - 1.4 from pick faces given up although a person was about to leave or a ghost only seemed to block them.
   These follow from assumptions, among them how much older robots drain (`age_range`), how often scans fail and how
   many failures are damaged labels (`scan_failure`, `scan_unreadable`); see the caveats.
3. **Batteries can be settled without asking.** The robot's own estimate uses the nominal drain, so following it
   (`never_ask`) runs out of battery 7.8 times an hour. `staged` finishes the task only when the battery covers the
   estimate at the oldest robots' drain with the fleet's margin (2.25 times the estimate): that halves the lines
   lost to charging (11.9 an hour) with no flat battery. `reference` asks about low batteries instead, 21 times an
   hour, and loses 1.6 lines and runs 0.35 batteries flat an hour.
4. **Scan failures are where asking pays.** `cost_aware` asks about a label that one rescan could not read, 20.8
   times an hour, and fails no line on scans. `staged` asks only after two failed rescans, 16.9 times an hour, also
   failing none. Never asking fails 8.5.
5. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   more than halves the lines lost to obstacles (0.55 an hour instead of 1.35). Waiting at every obstacle
   (`always_safe`) loses none, but costs 18% of the deliveries. `cost_aware` asks about an obstacle on the pick face
   (2.0 times an hour) and loses none; `motion_aware`, which waits instead when the obstacle moves, and `staged`,
   which waits three times first, ask 1.9 and 0.8 times.
6. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, `staged` is best where attention is cheap (a dedicated operator), clearly ahead
   of the runner-up `motion_aware` (+4.4 [+3.2, +5.7] per hour, paired mean and 95% interval). Under the balanced
   and scarce profiles, where a question costs half a wrong pick or more, `patient` is best, but the seeds do not
   tell it from the runner-ups `staged` (+0.1 [-1.2, +1.3]) and `always_safe_reroute` (+0.1 [-0.8, +1.1]). On the
   secret seeds the same supervisors win. The misses that follow the person's wrong answers are counted as theirs
   (6 over the 20 hours for `cost_aware`, 5 for `staged`).
7. **Trusting the robot's confidence does not pay here.** Every threshold from 0.95 down is dominated, no better
   on any axis and worse on at least one, by `cost_aware`. Only 0.99, which asks almost always, reaches the front,
   just beside `always_ask`. Going from 0.9 to 0.85 cuts the interruptions by a fifth and raises harm by 60%.
8. **The reference supervisor is on the front but is beaten under every cost profile.** It has the lowest harm of
   the supervisors that deliver 1000 lines an hour (4.8 an hour), mostly because it asks about low batteries. But it
   asks 62.2 questions an hour, more than three times as many as `staged`, and delivers 46 lines an hour less. Of
   its 1222 questions over the 10 seeds, 40% are about incidents below its learned threshold, 40% about kinds it
   never learns to trust (scan failures, for example: the scanner is right at most 79% of the time, short of the 95%
   target), 17% come from the shadow phase, and the rest are escalations and audits (the `reported_reason_*`
   columns of the CSV).
9. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. `staged`, which a reviewer proposed and which is three simple rules, shows how
   far plain rules already get.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 62.2 ± 1.3 | 4.8 ± 1.2 | 1003 ± 9 | | | |
| one shared threshold and target instead of one per kind | 67.3 ± 1.6 | 5.5 ± 1.2 | 989 ± 9 | **+5.1 [+0.9, +9.3]** | +0.8 [-2.8, +4.3] | -14.3 [-31.2, +2.5] |
| no joining of questions about the same cause | 60.8 ± 1.4 | 3.9 ± 1.0 | 1005 ± 6 | -1.4 [-4.1, +1.3] | -0.9 [-5.0, +3.3] | +2.3 [-11.1, +15.7] |
| no gate (may drive through motion or the human zone) | 59.9 ± 1.1 | 13.0 ± 6.5 | 1007 ± 9 | -2.4 [-5.4, +0.7] | +8.2 [-6.9, +23.2] | +3.8 [-8.4, +16.0] |
| no safe default when the person is busy | 67.3 ± 1.5 | 8.9 ± 4.8 | 974 ± 11 | **+5.1 [+2.8, +7.4]** | +4.1 [-7.5, +15.7] | **-28.6 [-45.8, -11.4]** |
| deadlocks calibrated like other kinds instead of always yielding | 62.0 ± 2.8 | 4.2 ± 0.9 | 1001 ± 10 | -0.1 [-5.3, +5.0] | -0.6 [-4.2, +2.9] | -1.8 [-17.6, +14.0] |

- **The safe default when the person is busy** is the one feature with a clear effect in every version of this
  page: without it the reference asks 5.1 more questions an hour, questions wait longer (82 s instead of 58 s), and
  the fleet delivers 29 fewer lines an hour.
- **Per-kind calibration** saves 5.1 questions an hour.
- **The gate** shows the largest mean increase in harm without it, from a few critical misses (0.2 an episode);
  the interval includes zero.
- **Joining questions** and **always yielding in deadlocks** show no effect these seeds can tell apart from zero.
  Joining is rare (47 joins against 1222 questions), and so are deadlocks (about 2 an hour).
- Earlier versions of this page found clear effects of the gate on harm and of always yielding on deliveries.
  Changes to the fleet's rules between versions moved them, which shows how roughly 10 seeds rank these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors: `staged` 20.4 / 6.9 / 1059 (interrupt/h, harm/h, delivered/h),
`cost_aware` 26.2 / 11.0 / 1064, `motion_aware` 25.9 / 10.9 / 1065, `patient` 0.5 / 16.0 / 1055,
`always_safe_reroute` 0.3 / 16.8 / 1062, `reference` 62.0 / 6.4 / 994. The best under the three profiles are
`staged` (ahead of `motion_aware` by +4.2 [+3.2, +5.2]), `patient` and `patient` (ahead of `always_safe_reroute`
by +0.3 [-0.5, +1.2] and +0.1 [-1.3, +1.5]).
Since the key is gone, this run cannot be repeated exactly; rerunning it draws new seeds and should give the same
picture.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after eight rounds of review.** In the first version caution cost nothing; in the
  second, robots rescanned damaged labels forever and queued behind them, which made caution look far more
  expensive than it is; the third fixed how misses are attributed and how the fleet treats an obstacle it already
  knows; the fourth fixed robots trapping each other at station bays and in the one-lane top aisle, which had cost
  every supervisor deliveries and dead batteries; the fifth fixed robots queued outside a full station that never
  gave way, which froze clusters of robots for an hour or more in some episodes; the sixth fixed two robots in the
  one-lane aisle stepping back and forth for each other for ever, robots queued behind a robot waiting for the
  person's answer raising deadlocks of their own (most of `always_ask`'s questions, which had cut its deliveries to
  a third), and robots shut in a bay by an obstacle in its entrance; the seventh fixed a robot raising the same
  obstacle every second when rerouting left it no way out, two robots shuffling around each other for minutes, and
  robots shut in a bay giving their order line up every 15 seconds; the eighth priced charging first like the other
  ways of giving a line up (until then caution cost nothing on low batteries), let the fleet take back a question
  whose obstacle has gone, and stopped the no-headway rule cutting detours short. Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), caution costs almost only the charging: `staged`
  (4.7 / 6.0 / 1068) is best under the cheap and balanced profiles and dominates `cost_aware` (12.1 / 10.1 / 1061),
  and `always_safe_reroute` (0.3 / 11.2 / 1066) is best where attention is scarce; `patient` scores exactly the same,
  because its rule then never applies.
- **The same author wrote the simulator and almost every supervisor**, including `cost_aware`, `patient` and
  `motion_aware`, which were written after seeing where caution is cheap in this simulator; `staged` came from a
  reviewer who had seen the same. Independent supervisors
  and scenarios are the real test.
- **Isolation is not a sandbox.** It stops a supervisor from reading the simulator or the key through the protocol,
  its command line, its environment or its working directory, and from stalling the run or breaking it with what
  it sends back; code that sets out to cheat could still read the user's files, keep notes on disk between
  episodes, or start processes that leave its process group and outlive it. Scores from untrusted
  code need an OS sandbox around the run. On public seeds a supervisor can recognise the seed and simulate the
  episode itself (a reviewer's attempt cut interruptions by 28%), which is why comparisons use secret seeds.
- **Some losses count twice.** A needlessly failed line is a low miss and also a delivery that did not happen; a
  wrong pick is a medium miss and is not counted as delivered.
- **The "right" action is a label, not an oracle.** It is fixed when an incident is raised, from the truth at that
  moment, and it is the best action as far as the simulator models costs.
- **Supervisors are reset every episode**, so the reference pays its shadow phase every time. Nothing but this rule
  stops a supervisor from keeping state elsewhere (a file, a module global); a fair comparison has to forbid it.
- 10 seeds of two hours each. Critical misses in particular are rare, and the front compares means.
