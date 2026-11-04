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
| always_ask | 91.2 ± 1.6 | 0.0 | 897 ± 15 | 0.0 | 0.0 | 0.0 | 0.0 | 79% | 104 | |
| threshold@0.99 | 85.6 ± 2.1 | 0.6 ± 0.5 | 931 ± 15 | 0.0 | 0.1 | 0.1 | 0.0 | 73% | 92 | |
| threshold@0.95 | 68.2 ± 2.5 | 13.2 ± 1.5 | 951 ± 12 | 0.0 | 2.5 | 1.5 | 0.0 | 66% | 95 | |
| threshold@0.9 | 57.5 ± 1.6 | 45.2 ± 9.2 | 933 ± 20 | 0.2 | 6.7 | 3.4 | 0.1 | 69% | 147 | |
| threshold@0.85 | 46.5 ± 1.4 | 46.6 ± 6.7 | 961 ± 14 | 0.1 | 7.8 | 5.2 | 0.0 | 64% | 124 | |
| threshold@0.8 | 39.5 ± 1.3 | 60.3 ± 9.8 | 946 ± 15 | 0.1 | 10.4 | 6.6 | 0.0 | 70% | 164 | |
| threshold@0.7 | 26.4 ± 0.8 | 101.0 ± 14.9 | 954 ± 11 | 0.6 | 13.0 | 11.9 | 0.1 | 68% | 241 | |
| threshold@0.6 | 19.1 ± 0.7 | 148.9 ± 15.3 | 975 ± 13 | 1.2 | 15.9 | 18.7 | 0.2 | 71% | 241 | |
| never_ask | 8.6 ± 0.6 | 234.2 ± 20.5 | 996 ± 13 | 2.7 | 17.0 | 28.2 | 0.4 | 66% | 0 | |
| always_safe | 0.3 ± 0.1 | 3.5 ± 0.4 | 860 ± 18 | 0.0 | 0.0 | 0.0 | 14.0 | 2% | 0 | * |
| always_safe_reroute | 0.5 ± 0.1 | 5.1 ± 0.5 | 1036 ± 8 | 0.0 | 0.0 | 0.0 | 20.3 | 4% | 0 | * |
| patient | 0.8 ± 0.1 | 4.5 ± 0.5 | 1026 ± 8 | 0.0 | 0.0 | 0.0 | 18.0 | 6% | 0 | * |
| cost_aware | 22.9 ± 0.8 | 0.0 | 1036 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 20% | 34 | * |
| motion_aware | 22.1 ± 0.9 | 0.0 | 1035 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 19% | 32 | * |
| staged | 18.1 ± 0.7 | 0.0 | 1030 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 16% | 34 | * |
| **reference** | 69.2 ± 1.7 | 0.5 ± 0.2 | 975 ± 8 | 0.0 | 0.0 | 1.0 | 0.0 | 65% | 58 | |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors. Interruptions
are questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts
only the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have
avoided (a battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 79% of the time, a question waits almost two
   minutes, and the fleet delivers 10% less than when nobody asks, because robots stand still while their questions
   wait. Following the robot's suggestion without asking (`never_ask`) is far worse: it drives into people, picks
   wrong items and runs batteries flat (234 harm an hour).
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
   the obstacle on the pick face moves, and `staged`, which waits three times first, ask about obstacles 1.5 and 0.7
   times an hour, against 2.2 for `cost_aware`.
4. **Low batteries have no trade-off: charging first is always right.** A robot charges to full either way, so
   charging at the first warning only moves the session earlier; it adds about 2% more docking sessions and costs
   no measurable throughput. Finishing the task first gains nothing and risks a flat battery: on the robot's own
   estimate, which ignores that older robots drain up to 1.8 times faster, `never_ask` runs 8.5 batteries flat an
   hour by its own decision. So this kind tests only whether a supervisor wastes attention on it or takes the
   robot's word, which is a cheap test: `reference` asks about low batteries 29 times an hour, `always_ask` 30
   times (two fifths and a third of their questions), about a decision whose answer never changes. It is also
   frequent (30 to 34 incidents an hour, more than obstacles for most supervisors), so it inflates the
   interruptions of supervisors that ask about it and the harm of those that follow the robot.
5. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the supervisors that ask where caution is expensive are best where attention is
   cheap (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each group the seeds do not tell the best from the runner-up:
   `staged` against `motion_aware` +0.2 [-0.2, +0.5], `always_safe_reroute` against `patient` +0.0 [-0.6, +0.6]
   and +0.4 [-0.6, +1.4] per hour (paired mean and 95% interval). On the secret seeds the same groups win. Never
   asking and asking where caution is expensive do not dominate each other, and the tests check that this stays so.
   The misses that follow the person's wrong answers to the questions are counted as theirs (9 over the 20 hours for
   `cost_aware`, 4 for `staged`).
6. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by `cost_aware`, which ignores the confidence. Harm does not even fall
   steadily as the threshold rises: these 10 seeds give 0.9 and 0.85 the same harm, within the large errors of rare
   misses. Most of the harm of the high thresholds is flat batteries, where the robot's confident suggestion to
   finish is wrong by construction (12.5 of the 13.2 harm an hour at 0.95, 0.5 of 0.55 at 0.99); without that
   kind the thresholds would still be dominated, by a smaller margin.
7. **The reference supervisor is dominated by `cost_aware`, `motion_aware` and `staged`**: 69.2 against 18 to 23
   interruptions an hour, 0.5 against 0 harm, 975 against 1030 to 1036 deliveries. Of its 1367 questions over the 10
   seeds, 64% are about kinds it never learns to trust (scan failures: the scanner is right at most 79% of the time,
   short of the 95% target; and low batteries, where the robot suggests finishing although charging is right), 18%
   about incidents below its learned threshold, 15% come from the shadow phase, and the rest are escalations and
   audits (the `reported_reason_*` columns of the CSV). Calibrating trust costs questions that a cheap cautious
   action makes unnecessary.
8. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. `staged`, three plain rules a reviewer proposed, asks 21% less than
   `cost_aware` (18.1 interruptions an hour, 16.9 questions about scans) for 6 fewer deliveries an hour, and is on
   the front.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 69.2 ± 1.7 | 0.5 ± 0.2 | 975 ± 8 | | | |
| one shared threshold and target instead of one per kind | 72.5 ± 0.9 | 2.6 ± 1.1 | 967 ± 8 | +3.4 [-0.4, +7.2] | +2.1 [-0.6, +4.7] | -8.2 [-25.4, +9.1] |
| no joining of questions about the same cause | 71.7 ± 1.3 | 0.4 ± 0.1 | 983 ± 9 | +2.5 [-1.5, +6.6] | -0.1 [-0.3, +0.1] | +7.8 [-12.0, +27.5] |
| no gate (may drive through motion or the human zone) | 69.5 ± 1.4 | 15.4 ± 10.6 | 983 ± 8 | +0.3 [-3.9, +4.6] | +14.9 [-9.1, +39.0] | +8.0 [-7.1, +23.1] |
| no safe default when the person is busy | 74.5 ± 1.3 | 0.5 ± 0.1 | 950 ± 9 | **+5.4 [+1.7, +9.1]** | -0.1 [-0.3, +0.2] | **-24.6 [-37.7, -11.4]** |
| deadlocks calibrated like other kinds instead of always yielding | 70.9 ± 1.6 | 0.6 ± 0.2 | 972 ± 9 | +1.8 [-1.9, +5.4] | +0.1 [-0.2, +0.4] | -2.8 [-16.1, +10.6] |

- **The safe default when the person is busy** is the one feature with a clear effect in every version of this
  page: without it the reference asks 5.4 more questions an hour, questions wait longer (74 s instead of 58 s), and
  the fleet delivers 25 fewer lines an hour.
- **The gate** shows the largest mean increase in harm without it, from a few critical misses (0.3 an episode);
  the interval includes zero.
- **Per-kind calibration**, **joining questions** and **always yielding in deadlocks** show no effect these seeds
  can tell apart from zero. Joining is rare (39 joins against 1367 questions), and so are deadlocks (about 2 an
  hour).
- Earlier versions of this page found clear effects of the gate on harm, of always yielding on deliveries and of
  per-kind calibration. Changes to the fleet's rules between versions moved them, which shows how roughly 10 seeds
  rank these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors. One such run gave `cost_aware` 26.1 / 0 / 1036 (interrupt/h,
harm/h, delivered/h), `motion_aware` 25.2 / 0 / 1037, `staged` 20.2 / 0 / 1029, `always_safe_reroute`
0.3 / 5.2 / 1036, `patient` 0.4 / 4.7 / 1027 and `reference` 69.6 / 0.9 / 984. The same groups win as on the public
seeds: one of `cost_aware`, `motion_aware` and `staged` where attention is cheap, one of `patient` and
`always_safe_reroute` under the other two profiles. Which member of a group comes first changes from key to key,
since the seeds do not tell them apart. A secret run cannot be repeated exactly; rerunning it draws new seeds.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after eleven rounds of review.** In the first version caution cost nothing; in the
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
  whose obstacle has gone and stopped the no-headway rule cutting detours short; the ninth added docking time to
  charging and made withdrawing a question safe with joined incidents; the tenth made charging first the right
  action on low batteries, as the simulator's costs say it is; the eleventh dropped `staged`'s rule for finishing
  on a full enough battery and counted lines given back before any work apart from dropped ones. (For a while, charging first when the battery would
  have lasted counted as a failed line. That was reverted: the simulator loses no throughput by it, so it was a
  price on nothing.) Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.8 lines an hour
  (0.3 / 0.4 / 1045, against `staged`'s 4.8 / 0 / 1041 and `cost_aware`'s 11.7 / 0 / 1038) and is the best
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
- **Charging is simple.** It runs at a constant 0.5% a second (a full charge in about three minutes) after a
  minute of docking, which lowers every supervisor's deliveries by about 2%. Charge-rate taper, partial charging
  and battery wear are not modelled, and with seven chargers for 24 robots a robot almost never waits for one (at
  36 robots it would). Any of these could give early charging a real cost; the conclusion that low batteries hold
  no trade-off depends on their absence.
- **Some losses may count twice.** A needlessly failed line is a low miss and may also show as fewer deliveries; a
  wrong pick is a medium miss and is not counted as delivered.
- **The "right" action is a label, not an oracle.** It is fixed when an incident is raised, from the truth at that
  moment, and it is the best action as far as the simulator models costs.
- **Supervisors are reset every episode**, so the reference pays its shadow phase every time. Nothing but this rule
  stops a supervisor from keeping state elsewhere (a file, a module global); a fair comparison has to forbid it.
- 10 seeds of two hours each. Critical misses in particular are rare, and the front compares means.
