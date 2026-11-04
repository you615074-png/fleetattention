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
| always_ask | 89.0 ± 1.5 | 0.0 | 901 ± 16 | 0.0 | 0.0 | 0.0 | 0.0 | 77% | 108 | |
| threshold@0.99 | 84.1 ± 2.0 | 0.0 | 928 ± 18 | 0.0 | 0.0 | 0.0 | 0.0 | 73% | 96 | |
| threshold@0.95 | 65.8 ± 2.0 | 8.8 ± 1.9 | 959 ± 14 | 0.0 | 1.6 | 1.5 | 0.0 | 62% | 92 | |
| threshold@0.9 | 56.2 ± 1.8 | 46.2 ± 8.5 | 927 ± 16 | 0.2 | 6.9 | 3.4 | 0.1 | 70% | 158 | |
| threshold@0.85 | 46.0 ± 0.9 | 38.1 ± 3.7 | 964 ± 15 | 0.0 | 7.1 | 5.2 | 0.0 | 64% | 122 | |
| threshold@0.8 | 39.6 ± 1.3 | 60.3 ± 9.4 | 942 ± 13 | 0.1 | 10.4 | 6.6 | 0.0 | 71% | 174 | |
| threshold@0.7 | 26.4 ± 0.8 | 98.5 ± 14.9 | 954 ± 11 | 0.6 | 12.5 | 11.9 | 0.1 | 68% | 241 | |
| threshold@0.6 | 19.1 ± 0.7 | 146.9 ± 14.9 | 975 ± 13 | 1.2 | 15.5 | 18.7 | 0.2 | 71% | 241 | |
| never_ask | 8.6 ± 0.6 | 233.2 ± 20.3 | 996 ± 13 | 2.7 | 16.8 | 28.2 | 0.4 | 66% | 0 | |
| always_safe | 0.3 ± 0.1 | 3.5 ± 0.4 | 860 ± 18 | 0.0 | 0.0 | 0.0 | 14.0 | 2% | 0 | * |
| always_safe_reroute | 0.5 ± 0.1 | 5.1 ± 0.5 | 1036 ± 8 | 0.0 | 0.0 | 0.0 | 20.3 | 4% | 0 | * |
| patient | 0.8 ± 0.1 | 4.5 ± 0.5 | 1026 ± 8 | 0.0 | 0.0 | 0.0 | 18.0 | 6% | 0 | * |
| cost_aware | 22.9 ± 0.8 | 0.0 | 1036 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 20% | 34 | * |
| motion_aware | 22.1 ± 0.9 | 0.0 | 1035 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 19% | 32 | * |
| staged | 18.1 ± 0.6 | 0.0 | 1029 ± 7 | 0.0 | 0.0 | 0.0 | 0.0 | 16% | 33 | * |
| **reference** | 62.5 ± 2.7 | 2.5 ± 0.8 | 992 ± 7 | 0.0 | 0.4 | 1.0 | 0.2 | 57% | 52 | |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors. Interruptions
are questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts
only the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have
avoided (a battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 77% of the time, a question waits almost two
   minutes, and the fleet delivers 10% less than when nobody asks, because robots stand still while their questions
   wait. Following the robot's suggestion without asking (`never_ask`) is far worse: it drives into people, picks
   wrong items and runs batteries flat (233 harm an hour).
2. **The trade-off is mostly about scan failures.** `always_safe_reroute` drives around every obstacle, rescans
   until the fleet gives the item up, and charges at the first battery warning. It interrupts less than once an
   hour, never drives into anything, and delivers as much as any supervisor. Its price is 10.2 order lines an hour
   that fail needlessly: 8.4 are items the fleet skipped after three rescans although the scanner's guess was right,
   and 1.8 are pick faces it gave up although a person was about to leave or a ghost only seemed to block them
   (`supervisor_low_*` columns). `cost_aware` asks about a label that one rescan could not read and about an
   obstacle on the pick face, 22.5 questions an hour (20.3 of them about scans), and fails no line by its own
   decision. So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both
   numbers follow from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many
   failures are damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   more than halves the lines lost to obstacles (0.7 an hour instead of 1.8). Waiting at every obstacle
   (`always_safe`) loses none, but costs 17% of the deliveries. `motion_aware`, which waits instead of asking when
   the obstacle on the pick face moves, and `staged`, which waits three times first, ask about obstacles 1.4 and 0.9
   times an hour, against 2.2 for `cost_aware`.
4. **On low batteries, caution costs almost nothing.** Every charging session includes a minute of docking, but a
   robot charges to full either way, so charging at the first warning only moves the session earlier: the
   supervisors that always do so deliver as much as any. Finishing the task on the robot's own estimate
   (`never_ask`) runs a battery flat 8.4 times an hour, because older robots drain up to 1.8 times faster than the
   estimate assumes. This kind therefore tests only whether a supervisor wastes attention or takes needless risks
   on it: `reference` asks about low batteries 21 times an hour.
5. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the supervisors that ask where caution is expensive are best where attention is
   cheap (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each group the seeds do not tell the best from the runner-up:
   `staged` against `motion_aware` +0.1 [-0.3, +0.6], `always_safe_reroute` against `patient` +0.0 [-0.6, +0.6]
   and +0.4 [-0.6, +1.4] per hour (paired mean and 95% interval). On the secret seeds the same groups win. Never
   asking and asking where caution is expensive do not dominate each other, and the tests check that this stays so.
   The misses that follow the person's wrong answers to the questions are counted as theirs (9 over the 20 hours for
   `cost_aware`, 5 for `staged`).
6. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by `cost_aware`, which ignores the confidence. Harm does not even fall
   steadily as the threshold rises: these 10 seeds put 0.85 below 0.9, within the large errors of rare misses.
7. **The reference supervisor is dominated by `cost_aware`, `motion_aware` and `staged`**: 62.5 against 18 to 23
   interruptions an hour, 2.5 against 0 harm, 992 against 1029 to 1036 deliveries. Of its 1238 questions over the 10
   seeds, 42% are about kinds it never learns to trust (scan failures, for example: the scanner is right at most 79%
   of the time, short of the 95% target), 39% about incidents below its learned threshold, 17% come from the shadow
   phase, and the rest are escalations and audits (the `reported_reason_*` columns of the CSV). Calibrating trust
   costs questions that a cheap cautious action makes unnecessary.
8. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. `staged`, three plain rules a reviewer proposed, asks 21% less than
   `cost_aware` (18.1 interruptions an hour, 16.8 questions about scans) for 7 fewer deliveries an hour, and is on
   the front.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 62.5 ± 2.7 | 2.5 ± 0.8 | 992 ± 7 | | | |
| one shared threshold and target instead of one per kind | 63.8 ± 1.3 | 4.8 ± 1.8 | 971 ± 9 | +1.4 [-5.0, +7.7] | +2.3 [-3.1, +7.7] | **-20.6 [-34.7, -6.5]** |
| no joining of questions about the same cause | 61.2 ± 2.1 | 5.0 ± 1.3 | 983 ± 9 | -1.2 [-8.1, +5.7] | +2.5 [-1.7, +6.6] | -9.3 [-22.8, +4.2] |
| no gate (may drive through motion or the human zone) | 59.3 ± 1.5 | 14.1 ± 6.2 | 991 ± 9 | -3.1 [-8.4, +2.1] | +11.6 [-2.3, +25.5] | -0.7 [-10.3, +9.0] |
| no safe default when the person is busy | 66.3 ± 2.5 | 2.6 ± 1.0 | 973 ± 10 | **+3.9 [+1.5, +6.3]** | +0.1 [-2.4, +2.5] | **-19.4 [-32.8, -5.9]** |
| deadlocks calibrated like other kinds instead of always yielding | 62.3 ± 2.2 | 10.0 ± 5.7 | 985 ± 9 | -0.1 [-3.2, +2.9] | +7.5 [-6.4, +21.3] | -6.9 [-16.0, +2.2] |

- **The safe default when the person is busy** is the one feature with a clear effect in every version of this
  page: without it the reference asks 3.9 more questions an hour, questions wait longer (67 s instead of 52 s), and
  the fleet delivers 19 fewer lines an hour.
- **Per-kind calibration** keeps 21 deliveries an hour.
- **The gate** shows the largest mean increase in harm without it, from a few critical misses (0.2 an episode);
  the interval includes zero.
- **Joining questions** and **always yielding in deadlocks** show no effect these seeds can tell apart from zero.
  Joining is rare (46 joins against 1238 questions), and so are deadlocks (about 2 an hour).
- Earlier versions of this page found clear effects of the gate on harm and of always yielding on deliveries.
  Changes to the fleet's rules between versions moved them, which shows how roughly 10 seeds rank these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors: `cost_aware` 26.4 / 0 / 1060 (interrupt/h, harm/h, delivered/h),
`motion_aware` 26.1 / 0 / 1058, `staged` 21.0 / 0 / 1042, `always_safe_reroute` 0.3 / 5.8 / 1060, `patient`
0.3 / 5.3 / 1050, `reference` 64.2 / 1.5 / 1004. The front is `always_safe`, `always_safe_reroute`, `patient`,
`cost_aware`, `motion_aware` and `staged`. The best under the three profiles are `cost_aware` (ahead of
`motion_aware` by +0.1 [-0.2, +0.3]), `patient` and `patient` (ahead of `always_safe_reroute` by +0.0 [-0.4, +0.4]
and +0.0 [-0.5, +0.5]).
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
  robots shut in a bay giving their order line up every 15 seconds; the eighth let the fleet take back a question
  whose obstacle has gone, stopped the no-headway rule cutting detours short, and added docking time to charging.
  (For a while, charging first when the battery would have lasted counted as a failed line. That was reverted:
  the simulator loses no throughput by it, so it was a price on nothing.) Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.8 lines an hour
  (0.3 / 0.4 / 1045, against `staged`'s 4.8 / 0 / 1042 and `cost_aware`'s 11.7 / 0 / 1038) and is the best
  supervisor under all three cost profiles; `patient` scores exactly the same, because its rule then never
  applies.
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
