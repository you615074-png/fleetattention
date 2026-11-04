# Results: phase 1

Commands, all with 10 seeds of 2 simulated hours, 24 robots, 4 chargers and the default `Config` unless stated:

```sh
python3 -m fleetattention sweep --seeds 10                       # public seeds 0 to 9
python3 -m fleetattention ablate --seeds 10                      # also prints the paired differences below
python3 -m fleetattention sweep --seeds 10 --secret-seeds --out results/keyed
python3 -m fleetattention sweep --seeds 10 --set obstacle_at_pick=0 --set scan_unreadable=0 --out results/sensitivity
python3 -m fleetattention sweep --seeds 10 --set chargers=7 --out results/chargers7
```

Raw numbers are in `results/` (not committed; rerun to reproduce, except the secret-seed run, whose key is gone).

| supervisor | interrupt/h | harm/h | delivered/h | critical/ep | high/ep | medium/ep | low/ep | person busy | wait s | front |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:-:|
| always_ask | 89.3 ± 1.5 | 0.0 | 871 ± 17 | 0.0 | 0.0 | 0.0 | 0.0 | 78% | 116 |  |
| threshold@0.99 | 82.1 ± 2.0 | 0.5 ± 0.5 | 905 ± 16 | 0.0 | 0.1 | 0.0 | 0.0 | 72% | 97 |  |
| threshold@0.95 | 70.2 ± 2.0 | 21.2 ± 3.4 | 873 ± 14 | 0.0 | 4.1 | 1.4 | 0.0 | 73% | 144 |  |
| threshold@0.9 | 56.7 ± 1.5 | 42.7 ± 6.7 | 902 ± 16 | 0.1 | 7.2 | 3.3 | 0.1 | 71% | 145 |  |
| threshold@0.85 | 47.6 ± 1.4 | 51.9 ± 7.0 | 893 ± 16 | 0.1 | 8.9 | 4.8 | 0.0 | 72% | 195 |  |
| threshold@0.8 | 40.8 ± 0.8 | 64.9 ± 4.4 | 900 ± 18 | 0.1 | 11.3 | 6.7 | 0.2 | 76% | 223 |  |
| threshold@0.7 | 27.9 ± 1.0 | 137.6 ± 16.4 | 903 ± 21 | 1.1 | 15.4 | 11.1 | 0.2 | 78% | 352 |  |
| threshold@0.6 | 18.1 ± 0.7 | 206.9 ± 23.2 | 927 ± 20 | 2.3 | 16.5 | 18.8 | 0.0 | 75% | 362 |  |
| never_ask | 8.9 ± 0.6 | 194.2 ± 28.5 | 960 ± 14 | 1.9 | 17.1 | 27.2 | 0.6 | 72% | 0 |  |
| always_safe | 0.5 ± 0.1 | 3.2 ± 0.4 | 843 ± 16 | 0.0 | 0.0 | 0.0 | 12.9 | 4% | 0 | * |
| always_safe_reroute | 0.3 ± 0.1 | 4.5 ± 0.5 | 991 ± 11 | 0.0 | 0.0 | 0.0 | 18.0 | 2% | 0 | * |
| patient | 0.3 ± 0.1 | 4.2 ± 0.4 | 993 ± 11 | 0.0 | 0.0 | 0.0 | 16.6 | 3% | 0 | * |
| cost_aware | 22.4 ± 0.9 | 0.0 | 996 ± 12 | 0.0 | 0.0 | 0.0 | 0.0 | 21% | 38 | * |
| motion_aware | 21.8 ± 1.0 | 0.0 | 992 ± 11 | 0.0 | 0.0 | 0.0 | 0.0 | 22% | 38 | * |
| staged | 17.7 ± 0.8 | 0.0 | 989 ± 10 | 0.0 | 0.0 | 0.0 | 0.0 | 17% | 36 | * |
| **reference** | 64.7 ± 1.2 | 1.0 ± 0.6 | 946 ± 10 | 0.0 | 0.1 | 0.9 | 0.2 | 64% | 64 |  |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors. Interruptions
are questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts
only the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have
avoided (a battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 78% of the time, a question waits about two
   minutes, and the fleet delivers 9% less than when nobody asks, because robots stand still while their questions
   wait. Following the robot's suggestion without asking (`never_ask`) is far worse: it drives into people, picks
   wrong items and runs batteries flat (194 harm an hour).
2. **The trade-off is mostly about scan failures.** `always_safe_reroute` drives around every obstacle, rescans
   until the fleet gives the item up, and charges at the first battery warning. It interrupts less than once an
   hour, never drives into anything, and delivers about as much as any supervisor. Its price is 9.0 order lines an
   hour that fail needlessly: 7.8 are items the fleet skipped after three rescans although the scanner's guess was
   right, and 1.3 are pick faces it gave up although a person was about to leave or a ghost only seemed to block
   them (`supervisor_low_*` columns). `cost_aware` asks about a label that one rescan could not read and about an
   obstacle on the pick face, 21.8 questions an hour (19.4 of them about scans), and fails no line by its own
   decision. So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both
   numbers follow from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many
   failures are damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   halves the lines lost to obstacles (0.6 an hour instead of 1.3). Waiting at every obstacle (`always_safe`) loses
   none, but costs 15% of the deliveries. `motion_aware`, which waits instead of asking when the obstacle on the
   pick face moves, and `staged`, which waits three times first, ask about obstacles 1.9 and 0.8 times an hour,
   against 2.4 for `cost_aware`.
4. **Low batteries hold a real but small trade-off.** A robot charges to full either way, so while a charger is
   free charging first costs nothing. With 4 chargers for 24 robots, a robot that goes to charge often finds every
   charger taken and stands idle until one frees up; then finishing the task first is right, if the battery lasts.
   That is the label at 27% of the battery warnings. But getting it right is worth little: a supervisor that
   (for measurement only) reads the label and always takes it delivers 7.0 ± 4.6 more lines an hour than the same
   supervisor charging every time (paired over the 10 seeds, ± a standard error); `staged`'s rule for it, finish
   only when no charger is free and the battery has a wide margin, gains 1.8 ± 2.5. A right call saves at most
   the one order line the robot would otherwise give back, so even halving the charge rate raises the oracle's gain
   only to about 12 an hour. Getting it wrong the other way is expensive: on the robot's own estimate, which ignores
   that older robots drain up to 1.8 times faster, `never_ask` runs 8.6 batteries flat an hour by its own decision.
   So asking about low batteries never pays (7 lines an hour are worth 0.35 an hour under every profile, the price
   of a few questions at most), and the kind mostly tests whether a supervisor wastes attention on it: `reference`
   asks about it 26 times an hour and `always_ask` 29 times, two fifths and a third of their questions. It is also
   frequent (28 to 33 incidents an hour, more than obstacles for the supervisors that rarely ask), so it inflates the
   interruptions of supervisors that ask about it and the harm of those that follow the robot. Compared with 7
   chargers (the last command above), 4 chargers lower every supervisor's deliveries by about 4% and change no
   conclusion on this page.
5. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the supervisors that ask where caution is expensive are best where attention is
   cheap (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each group the seeds do not tell the best from the runner-up:
   `staged` against `cost_aware` +0.1 [-0.4, +0.7], `patient` against `always_safe_reroute` +0.4 [-0.0, +0.8]
   and +0.3 [-0.2, +0.9] per hour (paired mean and 95% interval). On the secret seeds and with 7 chargers the same
   groups win. Never asking and asking where caution is expensive do not dominate each other, and the tests check
   that this stays so and that the price of attention picks between them. The misses that follow the person's
   wrong answers to the questions are counted as theirs (12 over the 20 hours for `cost_aware`, 6 for `staged`).
6. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by `cost_aware` (at 0.6, by `staged`), which ignore the confidence. Harm
   does not even fall steadily as the confidence needed falls: these 10 seeds give `threshold@0.6` more harm than
   `never_ask`, within the large errors of rare misses. Most of the harm of the high thresholds is flat batteries,
   where the robot confidently suggests finishing although that is right only about a quarter of the time (20.5 of
   the 21.2 harm an hour at 0.95, all of the 0.5 at 0.99); without that kind the thresholds would still be
   dominated, by a smaller margin.
7. **The reference supervisor is dominated by `cost_aware`, `motion_aware` and `staged`**: 64.7 against 18 to 22
   interruptions an hour, 1.0 against 0 harm, 946 against 989 to 996 deliveries. Of its 1268 questions over the 10
   seeds, 53% are about kinds it never learns to trust (scan failures: the scanner is right at most 79% of the time,
   short of the 95% target; and low batteries, where the robot's suggestion to finish is mostly wrong), 26% about
   incidents below its learned threshold, 17% come from the shadow phase, and the rest are escalations and audits
   (the `reported_reason_*` columns of the CSV). Calibrating trust costs questions that a cheap cautious action
   makes unnecessary.
8. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. `staged`, three plain rules a reviewer proposed, asks 21% less than
   `cost_aware` (17.7 interruptions an hour, 16.2 questions about scans) for 7 fewer deliveries an hour, and is on
   the front.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 64.7 ± 1.2 | 1.0 ± 0.6 | 946 ± 10 | | | |
| one shared threshold and target instead of one per kind | 68.9 ± 1.9 | 3.1 ± 1.5 | 928 ± 10 | +4.2 [-1.7, +10.1] | +2.0 [-2.0, +6.1] | -18.2 [-41.3, +4.9] |
| no joining of questions about the same cause | 69.3 ± 1.6 | 0.5 ± 0.2 | 944 ± 10 | +4.6 [-0.2, +9.4] | -0.6 [-1.9, +0.8] | -2.5 [-12.9, +8.0] |
| no gate (may drive through motion or the human zone) | 66.0 ± 1.2 | 35.6 ± 15.0 | 943 ± 13 | +1.3 [-1.9, +4.5] | **+34.6 [+0.8, +68.4]** | -3.6 [-17.7, +10.5] |
| no safe default when the person is busy | 69.3 ± 1.7 | 0.8 ± 0.5 | 940 ± 14 | **+4.7 [+1.0, +8.3]** | -0.2 [-2.0, +1.6] | -6.3 [-19.9, +7.3] |
| deadlocks calibrated like other kinds instead of always yielding | 67.1 ± 1.8 | 0.5 ± 0.2 | 946 ± 12 | +2.4 [-0.7, +5.5] | -0.5 [-1.7, +0.6] | -1.0 [-10.7, +8.7] |

- **The safe default when the person is busy** saves questions: without it the reference asks 4.7 more an hour
  and questions wait longer (77 s instead of 64 s). Its effect on deliveries, clear in earlier versions of this
  page, is within the errors here.
- **The gate** keeps the reference from driving into people: without it there are 0.7 critical misses an episode,
  and the interval of the harm difference just excludes zero.
- **Per-kind calibration**, **joining questions** and **always yielding in deadlocks** show no effect these seeds
  can tell apart from zero. Joining is rare (44 joins against 1268 questions), and so are deadlocks (about 2 an
  hour).
- Each change to the simulator has moved which of these effects stand out, which shows how roughly 10 seeds rank
  these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors. One such run gave `cost_aware` 23.5 / 0 / 997 (interrupt/h,
harm/h, delivered/h), `motion_aware` 23.1 / 0 / 1002, `staged` 18.4 / 0 / 994, `always_safe_reroute`
0.7 / 5.1 / 998, `patient` 0.5 / 4.6 / 991 and `reference` 66.5 / 5.6 / 957 (its harm from one critical miss in the
20 hours). The same groups win as on the public seeds: one of `cost_aware`, `motion_aware` and `staged` where
attention is cheap, one of `patient` and `always_safe_reroute` under the other two profiles. Which member of a
group comes first changes from key to key, since the seeds do not tell them apart. A secret run cannot be repeated
exactly; rerunning it draws new seeds.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after twelve rounds of review.** In the first version caution cost nothing; in the
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
  first is sometimes right, and gave `staged` a rule for it. (For a while, charging first when the battery would
  have lasted counted as a failed line. That was reverted: the simulator loses no throughput by it, so it was a
  price on nothing.) Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.9 lines an hour
  (0.6 / 0.4 / 1003, against `staged`'s 4.7 / 0 / 1004 and `cost_aware`'s 11.8 / 0 / 1002) and is the best
  supervisor under the balanced and scarce profiles; where attention is cheap `staged` is best, with
  `always_safe_reroute` +0.1 [-0.4, +0.5] behind it. `patient` scores exactly the same as `always_safe_reroute`, because its rule then never applies.
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
  and battery wear are not modelled. The only cost of charging early is waiting for a charger, so a low-battery
  decision is worth at most the one order line it can save; the conclusion that low batteries hold only a small
  trade-off depends on that. The label looks only at whether a charger is free when the warning comes, not at
  how soon one will be.
- **Some losses may count twice.** A needlessly failed line is a low miss and may also show as fewer deliveries; a
  wrong pick is a medium miss and is not counted as delivered.
- **The "right" action is a label, not an oracle.** It is fixed when an incident is raised, from the truth at that
  moment, and it is the best action as far as the simulator models costs.
- **Supervisors are reset every episode**, so the reference pays its shadow phase every time. Nothing but this rule
  stops a supervisor from keeping state elsewhere (a file, a module global); a fair comparison has to forbid it.
- 10 seeds of two hours each. Critical misses in particular are rare, and the front compares means.
