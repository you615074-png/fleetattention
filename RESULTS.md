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
| always_ask | 88.6 ± 1.8 | 0.0 | 878 ± 14 | 0.0 | 0.0 | 0.0 | 0.0 | 77% | 110 |  |
| threshold@0.99 | 86.6 ± 2.0 | 0.5 ± 0.5 | 904 ± 18 | 0.0 | 0.1 | 0.0 | 0.0 | 75% | 95 |  |
| threshold@0.95 | 68.5 ± 1.9 | 15.3 ± 3.1 | 918 ± 17 | 0.0 | 2.9 | 1.6 | 0.0 | 69% | 111 |  |
| threshold@0.9 | 57.2 ± 1.9 | 31.8 ± 3.3 | 906 ± 13 | 0.0 | 6.0 | 3.5 | 0.0 | 72% | 142 |  |
| threshold@0.85 | 46.0 ± 1.0 | 61.5 ± 7.6 | 897 ± 19 | 0.2 | 9.8 | 4.9 | 0.0 | 71% | 215 |  |
| threshold@0.8 | 40.4 ± 0.7 | 84.3 ± 13.6 | 907 ± 16 | 0.5 | 11.2 | 6.6 | 0.0 | 72% | 223 |  |
| threshold@0.7 | 28.4 ± 0.7 | 154.8 ± 19.7 | 897 ± 15 | 1.5 | 14.8 | 11.5 | 0.1 | 76% | 356 |  |
| threshold@0.6 | 18.8 ± 0.8 | 160.4 ± 16.2 | 930 ± 17 | 1.4 | 16.2 | 18.7 | 0.1 | 74% | 359 |  |
| never_ask | 9.3 ± 0.6 | 234.7 ± 31.1 | 960 ± 11 | 2.7 | 17.2 | 27.2 | 0.5 | 73% | 0 |  |
| always_safe | 0.6 ± 0.2 | 3.2 ± 0.3 | 845 ± 16 | 0.0 | 0.0 | 0.0 | 13.0 | 5% | 0 | * |
| always_safe_reroute | 0.6 ± 0.2 | 4.7 ± 0.5 | 1002 ± 10 | 0.0 | 0.0 | 0.0 | 18.6 | 5% | 0 | * |
| patient | 0.3 ± 0.1 | 4.2 ± 0.5 | 998 ± 11 | 0.0 | 0.0 | 0.0 | 16.8 | 3% | 0 | * |
| cost_aware | 22.7 ± 0.6 | 0.0 | 997 ± 11 | 0.0 | 0.0 | 0.0 | 0.0 | 24% | 46 |  |
| motion_aware | 22.4 ± 0.8 | 0.0 | 1002 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 22% | 46 | * |
| staged | 17.7 ± 0.6 | 0.0 | 995 ± 10 | 0.0 | 0.0 | 0.0 | 0.0 | 19% | 38 | * |
| **reference** | 65.5 ± 1.3 | 0.4 ± 0.2 | 957 ± 13 | 0.0 | 0.0 | 0.8 | 0.1 | 63% | 58 |  |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors. Interruptions
are questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts
only the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have
avoided (a battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 77% of the time, a question waits almost two
   minutes, and the fleet delivers 9% less than when nobody asks, because robots stand still while their questions
   wait. Following the robot's suggestion without asking (`never_ask`) is far worse: it drives into people, picks
   wrong items and runs batteries flat (235 harm an hour).
2. **The trade-off is mostly about scan failures.** `always_safe_reroute` drives around every obstacle, rescans
   until the fleet gives the item up, and charges at the first battery warning. It interrupts less than once an
   hour, never drives into anything, and delivers as much as any supervisor. Its price is 9.3 order lines an hour
   that fail needlessly: 7.8 are items the fleet skipped after three rescans although the scanner's guess was right,
   and 1.6 are pick faces it gave up although a person was about to leave or a ghost only seemed to block them
   (`supervisor_low_*` columns). `cost_aware` asks about a label that one rescan could not read and about an
   obstacle on the pick face, 21.7 questions an hour (19.4 of them about scans), and fails no line by its own
   decision. So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both
   numbers follow from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many
   failures are damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   cuts the lines lost to obstacles by more than half (0.6 an hour instead of 1.6). Waiting at every obstacle
   (`always_safe`) loses none, but costs 16% of the deliveries. `staged`, which waits three times at the pick face
   before asking, asks about obstacles 0.6 times an hour, against 2.3 for `cost_aware` and `motion_aware`.
4. **Low batteries hold a small trade-off.** A robot charges to full either way, so while a charger is free
   charging first costs nothing. With 4 chargers for 24 robots, a robot sent to charge often finds every charger
   taken and stands idle until one frees up; finishing the task first instead uses that time, so it is labelled
   right when every charger is taken and the battery covers the task at the robot's true drain. That is the label
   at 26% of the battery warnings. Getting it right is worth little: a copy of `staged` that reads the label and
   always takes it (a measurement, not a supervisor: `scripts/low_battery_value.py`) delivers 7.0 ± 2.0 more lines
   an hour than one that always charges first (paired over the 10 seeds, ± a standard error), about 0.8 lines per
   right call; at half the charge rate, 8.2 ± 4.2. A robot that finishes first may still wait for a charger
   afterwards, so a right call saves robot idle time, on average less than one order line. `staged`'s own rule,
   finish only when no charger is free and the battery has a wide margin, gains nothing measurable (-3.9 ± 3.8).
   Getting it wrong the other way is expensive: on the robot's own estimate, which ignores that older robots drain
   up to 1.8 times faster, `never_ask` runs 8.6 batteries flat an hour by its own decision. So asking about low
   batteries never pays (7 lines an hour are worth 0.35 an hour under every profile, the price of a few questions at
   most), and the kind mostly tests whether a supervisor wastes attention on it: `reference` asks about it 27 times
   an hour and `always_ask` 29 times, two fifths and a third of their questions. It is also frequent (28 to 33
   incidents an hour, more than obstacles for the supervisors that rarely ask), so it inflates the interruptions of
   supervisors that ask about it and the harm of those that follow the robot. Compared with 7 chargers (the fifth
   command above), 4 chargers lower deliveries by 2 to 6%, about 3.5% for the supervisors on the front, and change
   no conclusion on this page.
5. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the supervisors that ask where caution is expensive are best where attention is
   cheap (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each group the seeds do not tell the best from the runner-up:
   `staged` against `motion_aware` +0.1 [-0.5, +0.7], `patient` against `always_safe_reroute` +0.3 [-0.2, +0.9]
   and +0.7 [-0.1, +1.4] per hour (paired mean and 95% interval). On the secret seeds and with 7 chargers the same
   groups win. Never asking and asking where caution is expensive do not dominate each other, and the tests check
   that this stays so and that the price of attention picks between them. The misses that follow the person's
   wrong answers to the questions are counted as theirs (9 over the 20 hours for `cost_aware`, 6 for `staged`).
6. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by `cost_aware` (at 0.6, by `staged`), which ignore the confidence. Harm
   does not even fall steadily as the confidence needed rises: these 10 seeds give 0.7 and 0.6 about the same harm,
   within the large errors of rare misses. Most of the harm of the high thresholds is flat batteries, where the
   robot confidently suggests finishing although that is right only about a quarter of the time (14.5 of the 15.3
   harm an hour at 0.95, all of the 0.5 at 0.99); without that kind the thresholds would still be dominated, by a
   smaller margin.
7. **The reference supervisor is dominated by `cost_aware`, `motion_aware` and `staged`**: 65.5 against 18 to 23
   interruptions an hour, 0.4 against 0 harm, 957 against 995 to 1002 deliveries. Of its 1288 questions over the 10
   seeds, 62% are about kinds it never learns to trust (scan failures: the scanner is right at most 79% of the time,
   short of the 95% target; and low batteries, where the robot's suggestion to finish is mostly wrong), 20% about
   incidents below its learned threshold, 16% come from the shadow phase, and the rest are escalations and audits
   (the `reported_reason_*` columns of the CSV). Calibrating trust costs questions that a cheap cautious action
   makes unnecessary.
8. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. `staged`, three plain rules a reviewer proposed, asks 22% less than
   `cost_aware` (17.7 interruptions an hour, 16.1 questions about scans) for 2 fewer deliveries an hour, and is on
   the front.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 65.5 ± 1.3 | 0.4 ± 0.2 | 957 ± 13 | | | |
| one shared threshold and target instead of one per kind | 68.7 ± 1.3 | 2.5 ± 1.1 | 938 ± 9 | **+3.2 [+0.1, +6.4]** | +2.1 [-0.5, +4.8] | -18.8 [-39.4, +1.8] |
| no joining of questions about the same cause | 70.5 ± 1.5 | 0.4 ± 0.1 | 952 ± 12 | **+5.0 [+2.0, +8.0]** | -0.1 [-0.5, +0.4] | -4.5 [-17.8, +8.9] |
| no gate (may drive through motion or the human zone) | 64.1 ± 1.3 | 10.6 ± 6.7 | 945 ± 14 | -1.4 [-4.2, +1.5] | +10.2 [-4.9, +25.2] | -12.3 [-34.6, +10.0] |
| no safe default when the person is busy | 68.9 ± 1.2 | 0.5 ± 0.2 | 941 ± 13 | **+3.5 [+1.8, +5.1]** | +0.1 [-0.1, +0.3] | **-15.8 [-30.5, -1.0]** |
| deadlocks calibrated like other kinds instead of always yielding | 67.7 ± 2.0 | 0.6 ± 0.2 | 946 ± 15 | +2.2 [-0.7, +5.2] | +0.1 [-0.1, +0.3] | -10.9 [-26.2, +4.3] |

- **The safe default when the person is busy** saves questions and deliveries: without it the reference asks 3.5
  more questions an hour, questions wait longer (76 s instead of 58 s), and the fleet delivers 16 fewer lines an
  hour.
- **Joining questions** and **per-kind calibration** each save a few questions an hour (5.0 and 3.2), with
  intervals that just exclude zero. Joins are rare (34 against 1288 questions, 1.7 an hour), so a saving of 5
  questions an hour is more than the joins themselves explain; these seeds do not show where the rest comes from.
- **The gate** shows the largest mean increase in harm without it, from a few critical misses (0.2 an episode);
  the interval includes zero. **Always yielding in deadlocks** shows no effect these seeds can tell apart from zero;
  deadlocks are rare (about 2 an hour).
- Each change to the simulator has moved which of these effects stand out, which shows how roughly 10 seeds rank
  these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors. One such run gave `cost_aware` 26.4 / 0 / 1006 (interrupt/h,
harm/h, delivered/h), `motion_aware` 24.4 / 0 / 1011, `staged` 18.6 / 0 / 1004, `always_safe_reroute`
0.8 / 5.0 / 1011, `patient` 0.5 / 4.3 / 996 and `reference` 66.2 / 5.7 / 973 (its harm from one critical miss in the
20 hours). The same groups win as on the public seeds: one of `cost_aware`, `motion_aware` and `staged` where
attention is cheap, one of `patient` and `always_safe_reroute` under the other two profiles. Which member of a
group comes first changes from key to key, since the seeds do not tell them apart. A secret run cannot be repeated
exactly; rerunning it draws new seeds.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after thirteen rounds of review.** In the first version caution cost nothing; in the
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
  of the station bays they blocked and served them first come, first served. (For a while, charging first when the battery would
  have lasted counted as a failed line. That was reverted: the simulator loses no throughput by it, so it was a
  price on nothing.) Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.9 lines an hour
  (0.7 / 0.4 / 1014, against `staged`'s 5.0 / 0 / 1008 and `cost_aware`'s 11.7 / 0 / 1008), and it or `patient`,
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
  on average less than one order line per decision; the conclusion that low batteries hold only a small trade-off
  depends on that. The label looks only at whether a charger is free when the warning comes, not at how soon one
  will be or whether the robot will wait again after the task. A robot waiting for a charger parks in the nearest
  free aisle cell, where it can still be in other robots' way.
- **Some losses may count twice.** A needlessly failed line is a low miss and may also show as fewer deliveries; a
  wrong pick is a medium miss and is not counted as delivered.
- **The "right" action is a label, not an oracle.** It is fixed when an incident is raised, from the truth at that
  moment, and it is the best action as far as the simulator models costs.
- **Supervisors are reset every episode**, so the reference pays its shadow phase every time. Nothing but this rule
  stops a supervisor from keeping state elsewhere (a file, a module global); a fair comparison has to forbid it.
- 10 seeds of two hours each. Critical misses in particular are rare, and the front compares means.
