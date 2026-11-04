# Results: phase 1

Commands, all with 10 seeds of 2 simulated hours, 24 robots, 4 chargers and the default `Config` unless stated:

```sh
python3 -m fleetattention sweep --seeds 10                       # public seeds 0 to 9
python3 -m fleetattention ablate --seeds 10                      # also prints the paired differences below
python3 -m fleetattention sweep --seeds 10 --secret-seeds --out results/keyed
python3 -m fleetattention sweep --seeds 10 --set obstacle_at_pick=0 --set scan_unreadable=0 --out results/sensitivity
python3 -m fleetattention sweep --seeds 10 --set chargers=7 --out results/chargers7
python3 scripts/low_battery_value.py                             # item 4; add --set charge_rate=.25
```

Raw numbers are in `results/` (not committed; rerun to reproduce, except the secret-seed run, whose key is gone).

| supervisor | interrupt/h | harm/h | delivered/h | critical/ep | high/ep | medium/ep | low/ep | person busy | wait s | front |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|
| always_ask | 89.6 ± 1.8 | 0.0 | 873 ± 15 | 0.0 | 0.0 | 0.0 | 0.0 | 79% | 115 |  |
| threshold@0.99 | 84.0 ± 2.3 | 0.0 | 908 ± 11 | 0.0 | 0.0 | 0.0 | 0.0 | 72% | 96 |  |
| threshold@0.95 | 65.9 ± 1.6 | 15.7 ± 3.1 | 912 ± 14 | 0.0 | 3.0 | 1.4 | 0.0 | 70% | 120 |  |
| threshold@0.9 | 56.6 ± 1.9 | 34.2 ± 3.7 | 897 ± 12 | 0.0 | 6.5 | 3.4 | 0.0 | 69% | 142 |  |
| threshold@0.85 | 46.8 ± 1.5 | 55.4 ± 7.0 | 899 ± 21 | 0.2 | 8.6 | 4.7 | 0.0 | 71% | 186 |  |
| threshold@0.8 | 39.5 ± 1.1 | 75.2 ± 7.3 | 916 ± 16 | 0.3 | 11.4 | 6.3 | 0.1 | 72% | 195 |  |
| threshold@0.7 | 26.5 ± 0.7 | 120.1 ± 9.6 | 920 ± 19 | 0.9 | 13.8 | 12.1 | 0.2 | 72% | 295 |  |
| threshold@0.6 | 17.8 ± 0.9 | 213.2 ± 22.6 | 942 ± 16 | 2.6 | 14.8 | 18.3 | 0.4 | 69% | 277 |  |
| never_ask | 9.2 ± 0.4 | 215.1 ± 23.8 | 947 ± 17 | 2.3 | 17.3 | 27.0 | 0.5 | 75% | 0 |  |
| always_safe | 0.6 ± 0.2 | 3.1 ± 0.3 | 844 ± 17 | 0.0 | 0.0 | 0.0 | 12.6 | 5% | 0 | * |
| always_safe_reroute | 0.2 ± 0.1 | 4.7 ± 0.4 | 1005 ± 10 | 0.0 | 0.0 | 0.0 | 18.9 | 2% | 0 | * |
| patient | 0.3 ± 0.1 | 4.3 ± 0.4 | 992 ± 11 | 0.0 | 0.0 | 0.0 | 17.2 | 3% | 0 | * |
| cost_aware | 22.8 ± 0.9 | 0.0 | 1005 ± 10 | 0.0 | 0.0 | 0.0 | 0.0 | 23% | 42 |  |
| motion_aware | 21.9 ± 0.8 | 0.0 | 1005 ± 10 | 0.0 | 0.0 | 0.0 | 0.0 | 22% | 43 | * |
| staged | 17.9 ± 0.7 | 0.0 | 1000 ± 10 | 0.0 | 0.0 | 0.0 | 0.0 | 19% | 41 | * |
| **reference** | 65.8 ± 1.6 | 5.3 ± 5.0 | 965 ± 13 | 0.1 | 0.0 | 0.6 | 0.1 | 60% | 54 |  |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors. Interruptions
are questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts
only the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have
avoided (a battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 79% of the time, a question waits almost two
   minutes, and the fleet delivers 8% less than when nobody asks, because robots stand still while their questions
   wait. Following the robot's suggestion without asking (`never_ask`) is far worse: it drives into people, picks
   wrong items and runs batteries flat (215 harm an hour).
2. **The trade-off is mostly about scan failures.** `always_safe_reroute` drives around every obstacle, rescans
   until the fleet gives the item up, and charges at the first battery warning. It interrupts less than once an
   hour, never drives into anything, and delivers as much as any supervisor. Its price is 9.5 order lines an hour
   that fail needlessly: 7.8 are items the fleet skipped after three rescans although the scanner's guess was right,
   and 1.7 are pick faces it gave up although a person was about to leave or a ghost only seemed to block them
   (`supervisor_low_*` columns). `cost_aware` asks about a label that one rescan could not read and about an
   obstacle on the pick face, 22.0 questions an hour (19.9 of them about scans), and fails no line by its own
   decision. So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both
   numbers follow from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many
   failures are damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   cuts the lines lost to obstacles by more than half (0.8 an hour instead of 1.7). Waiting at every obstacle
   (`always_safe`) loses none, but costs 16% of the deliveries. `motion_aware`, which waits instead of asking when
   the obstacle on the pick face moves, and `staged`, which waits three times first, ask about obstacles 1.4 and
   1.1 times an hour, against 2.1 for `cost_aware`.
4. **Low batteries hold a small trade-off.** A robot charges to full either way, so while a charger is free
   charging first costs nothing. With 4 chargers for 24 robots, a robot sent to charge often finds every charger
   taken and waits its turn; finishing the task first instead uses that time, so it is labelled right when every
   charger is taken and the battery covers the task at the robot's true drain. That is the label at 27% of the
   battery warnings. A copy of `staged` that reads the label and always takes it (a measurement, not a supervisor:
   `scripts/low_battery_value.py`) delivers 10.8 ± 3.6 more lines an hour than one that always charges first
   (paired over the 10 seeds, ± a standard error): about 1.2 lines per right call (0.8 to 1.7 within one standard
   error). At half the charge rate it is 13.7 ± 3.7, or 0.9 lines per right call, since finishing first is then
   right twice as often. `staged`'s own rule, finish only when no charger is free and the battery has a wide margin,
   gets about half of that (6.0 ± 3.1; 7.0 ± 2.5 at half the charge rate) without a flat battery. Getting it wrong
   the other way is expensive: on the robot's own estimate, which ignores that older robots drain up to 1.8 times
   faster, `never_ask` runs 8.7 batteries flat an hour by its own decision. So asking about low batteries does not
   pay (11 lines an hour are worth about 0.5 an hour under every profile, the price of a few questions at most), and the
   kind mostly tests whether a supervisor wastes attention on it: `reference` asks about it 28 times an hour and
   `always_ask` 29 times, two fifths and a third of their questions. It is also frequent (28 to 33 incidents an
   hour, more than obstacles for the supervisors that rarely ask), so it inflates the interruptions of supervisors
   that ask about it and the harm of those that follow the robot. Compared with 7 chargers (the fifth command
   above), 4 chargers lower deliveries by 1 to 5%, about 3% for the supervisors on the front, and change no
   conclusion on this page.
5. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the supervisors that ask where caution is expensive are best where attention is
   cheap (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each group the seeds do not tell the best from the runner-up:
   `staged` against `motion_aware` +0.1 [-0.4, +0.7], `always_safe_reroute` against `patient` +0.3 [-0.4, +0.9]
   and +0.5 [-0.4, +1.4] per hour (paired mean and 95% interval). On the secret seeds and with 7 chargers the same
   groups win. Never asking and asking where caution is expensive do not dominate each other, and the tests check
   that this stays so and that the price of attention picks between them. The misses that follow the person's
   wrong answers to the questions are counted as theirs (10 over the 20 hours for `cost_aware`, 5 for `staged`).
6. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by `cost_aware` (at 0.6, by `always_safe_reroute`), which ignore the confidence. Most of
   the harm of the high thresholds is flat batteries, where the robot confidently suggests finishing although that
   is right only about a quarter of the time (15.0 of the 15.7 harm an hour at 0.95); without that kind the
   thresholds would still be dominated, by a smaller margin.
7. **The reference supervisor is dominated by `cost_aware`, `motion_aware` and `staged`**: 65.8 against 18 to 23
   interruptions an hour, 5.3 against 0 harm (one critical miss in the 20 hours), 965 against 1000 to 1005
   deliveries. Of its
   1304 questions over the 10 seeds, 60% are about kinds it never learns to trust (scan failures: the scanner is
   right at most 79% of the time, short of the 95% target; and low batteries, where the robot's suggestion to
   finish is mostly wrong), 21% about incidents below its learned threshold, 16% come from the shadow phase, and
   the rest are escalations and audits (the `reported_reason_*` columns of the CSV). Calibrating trust costs
   questions that a cheap cautious action makes unnecessary.
8. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. `staged`, three plain rules a reviewer proposed and one for batteries, asks
   21% less than `cost_aware` (17.9 interruptions an hour, 15.9 questions about scans) for 5 fewer deliveries an
   hour, and is on the front.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 65.8 ± 1.6 | 5.3 ± 5.0 | 965 ± 13 | | | |
| one shared threshold and target instead of one per kind | 69.3 ± 2.1 | 3.0 ± 1.5 | 935 ± 9 | +3.5 [-3.1, +10.1] | -2.3 [-10.7, +6.1] | **-29.9 [-58.2, -1.7]** |
| no joining of questions about the same cause | 70.0 ± 1.0 | 0.4 ± 0.2 | 953 ± 10 | **+4.2 [+1.8, +6.6]** | -5.0 [-16.2, +6.3] | -11.9 [-25.4, +1.5] |
| no gate (may drive through motion or the human zone) | 66.1 ± 1.1 | 15.6 ± 7.6 | 953 ± 12 | +0.2 [-3.4, +3.9] | +10.2 [-4.7, +25.2] | -11.9 [-32.6, +8.8] |
| no safe default when the person is busy | 71.0 ± 1.8 | 0.5 ± 0.2 | 926 ± 14 | **+5.1 [+2.1, +8.1]** | -4.8 [-16.1, +6.4] | **-39.0 [-57.9, -20.2]** |
| deadlocks calibrated like other kinds instead of always yielding | 66.2 ± 1.6 | 0.5 ± 0.2 | 940 ± 14 | +0.4 [-2.6, +3.4] | -4.8 [-16.1, +6.4] | **-24.6 [-39.5, -9.6]** |

- **The safe default when the person is busy** saves questions and deliveries: without it the reference asks
  about 5 more questions an hour, questions wait longer (82 s instead of 54 s), and the fleet delivers 39 fewer
  lines an hour.
- **Always yielding in deadlocks** and **per-kind calibration** each save over 20 deliveries an hour; **joining
  questions** saves about 4 questions an hour, more than the joins themselves explain (32 against 1304 questions,
  1.6 an hour); these seeds do not show where the rest comes from.
- **The gate**: without it there are more critical misses (0.3 an episode) and the largest mean increase in harm,
  but the interval includes zero. The reference itself drove into a person once in the 20 hours, which is why the
  other variants show less harm than it.
- Each change to the simulator has moved which of these effects stand out, which shows how roughly 10 seeds rank
  these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors. One such run gave `cost_aware` 24.8 / 0 / 1015 (interrupt/h,
harm/h, delivered/h), `motion_aware` 24.6 / 0 / 1013, `staged` 19.9 / 0 / 1003, `always_safe_reroute`
0.7 / 4.5 / 1015, `patient` 0.5 / 4.1 / 1007 and `reference` 66.5 / 5.7 / 979 (one critical miss). The same groups win as on the
public seeds: one of `cost_aware`, `motion_aware` and `staged` where attention is cheap, one of `patient` and
`always_safe_reroute` under the other two profiles. Which member of a group comes first changes from key to key,
since the seeds do not tell them apart. A secret run cannot be repeated exactly; rerunning it draws new seeds.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after fifteen rounds of review.** In the first version caution cost nothing; in the
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
  action on low batteries, as the simulator's costs say it is; the eleventh counted lines given back before any work
  apart from dropped ones; the twelfth made chargers scarce (4 for 24 robots instead of 7), so that finishing a task
  first is sometimes right, and gave `staged` a rule for it; the thirteenth sent robots waiting for a charger out
  of the station bays they blocked and served them first come, first served; the fourteenth parked every waiting
  robot off pick faces, bay entrances and the one-lane aisle, and stopped counting a charger as free while a robot
  still stands in it; the fifteenth made the label leave a free charger to the robots already waiting for it.
  (For a while, charging first when the battery would
  have lasted counted as a failed line. That was reverted: the simulator loses no throughput by it, so it was a
  price on nothing.) Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.9 lines an hour
  (0.5 / 0.4 / 1010, against `staged`'s 5.1 / 0 / 1008 and `cost_aware`'s 11.7 / 0 / 1008), and it or `patient`,
  which scores almost the same because its rule then hardly applies, is the best supervisor under all three cost
  profiles.
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
  and battery wear are not modelled. The only cost of charging early is robot time spent waiting for a charger,
  about 1.2 order lines per right call (0.9 at half the charge rate); the conclusion that low batteries hold only a
  small trade-off depends on that. The label looks only at whether a charger is free when the warning comes, not at how soon one
  will be or whether the robot will wait again after the task. A robot waiting for a charger parks in the nearest
  free cell off pick faces, bay entrances and the one-lane top aisle. Battery warnings come just after a drop, so
  nearly all waiting robots park beside the stations, far from the chargers, where they are in the way of drop
  traffic and take about 45 s to reach a charger once it is theirs. Parking near the chargers would shorten waits
  and so lower the value of finishing first.
- **Some losses may count twice.** A needlessly failed line is a low miss and may also show as fewer deliveries; a
  wrong pick is a medium miss and is not counted as delivered.
- **The "right" action is a label, not an oracle.** It is fixed when an incident is raised, from the truth at that
  moment, and it is the best action as far as the simulator models costs.
- **Supervisors are reset every episode**, so the reference pays its shadow phase every time. Nothing but this rule
  stops a supervisor from keeping state elsewhere (a file, a module global); a fair comparison has to forbid it.
- 10 seeds of two hours each. Critical misses in particular are rare, and the front compares means.
