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
| always_ask | 87.7 ± 1.4 | 0.0 | 854 ± 17 | 0.0 | 0.0 | 0.0 | 0.0 | 83% | 147 | |
| threshold@0.99 | 85.8 ± 2.7 | 0.0 | 856 ± 36 | 0.0 | 0.0 | 0.0 | 0.0 | 81% | 154 | |
| threshold@0.95 | 67.4 ± 1.8 | 14.2 ± 3.3 | 930 ± 15 | 0.0 | 2.7 | 1.5 | 0.0 | 71% | 141 | |
| threshold@0.9 | 55.9 ± 1.8 | 25.1 ± 1.8 | 919 ± 18 | 0.0 | 4.7 | 3.1 | 0.0 | 70% | 178 | |
| threshold@0.85 | 44.9 ± 1.5 | 57.9 ± 12.7 | 914 ± 21 | 0.3 | 8.1 | 4.7 | 0.0 | 72% | 240 | |
| threshold@0.8 | 39.5 ± 0.8 | 87.5 ± 16.2 | 904 ± 20 | 0.6 | 10.8 | 7.0 | 0.0 | 75% | 292 | |
| threshold@0.7 | 27.1 ± 1.0 | 112.9 ± 18.9 | 931 ± 24 | 0.8 | 13.4 | 11.8 | 0.1 | 74% | 344 | |
| threshold@0.6 | 18.9 ± 0.8 | 185.0 ± 28.4 | 979 ± 18 | 2.1 | 14.1 | 18.9 | 0.1 | 70% | 265 | |
| never_ask | 8.2 ± 0.6 | 203.0 ± 22.3 | 1022 ± 9 | 2.2 | 15.7 | 28.7 | 0.5 | 64% | 0 | |
| always_safe | 0.3 ± 0.2 | 3.5 ± 0.3 | 876 ± 17 | 0.0 | 0.0 | 0.0 | 14.0 | 2% | 0 | * |
| always_safe_reroute | 0.4 ± 0.1 | 4.9 ± 0.4 | 1056 ± 8 | 0.0 | 0.0 | 0.0 | 19.5 | 3% | 0 | * |
| patient | 0.5 ± 0.2 | 4.6 ± 0.5 | 1050 ± 9 | 0.0 | 0.0 | 0.0 | 18.5 | 4% | 0 | * |
| cost_aware | 23.2 ± 0.9 | 0.0 | 1055 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 22% | 40 | |
| motion_aware | 22.8 ± 0.9 | 0.0 | 1056 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 19% | 34 | * |
| **reference** | 64.5 ± 1.2 | 1.9 ± 0.8 | 1002 ± 10 | 0.0 | 0.3 | 0.7 | 0.0 | 61% | 57 | |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors, and a
supervisor just off it (`cost_aware`, a hair behind `motion_aware`) is not clearly worse. Interruptions are
questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts only
the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have avoided (a
battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 83% of the time, a question waits about two and
   a half minutes, and the fleet delivers 16% less than when nobody asks, because robots stand still while their
   questions wait.
2. **The trade-off is mostly about scan failures.** Of the incidents where the cautious action has a real price,
   scan failures dominate in the default settings:
   - `always_safe_reroute` drives around every obstacle, rescans until the fleet gives the item up, and charges at
     the first warning. It interrupts less than once an hour, never drives into anything, and delivers as much as
     any supervisor. Its price is 9.8 order lines an hour that fail needlessly: 8.5 are items the fleet skipped
     after three rescans although the scanner's guess was right, and 1.3 are pick faces it gave up although a
     person was about to leave or a ghost only seemed to block them (`supervisor_low_*` columns).
   - `cost_aware` asks about an obstacle on the pick face the robot is heading to and about a label that one
     rescan could not read, and takes the cautious action everywhere else. It asks 22.7 questions an hour, 20.8 of
     them about scans, and fails no line by its own decision.
   So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both numbers follow
   from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many failures are
   damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   halves the lines lost to obstacles (0.65 an hour instead of 1.3). Waiting at every obstacle (`always_safe`) loses
   none, but costs 17% of the deliveries. `motion_aware` waits instead of asking when the obstacle on the pick face
   moves; it asks about as often as `cost_aware` about obstacles (1.8 against 1.9 an hour), and the two are level
   within the errors.
4. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the two that ask where caution is expensive are best where attention is cheap
   (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each pair the seeds do not tell the two apart: the runner-up
   costs +0.1 [-0.2, +0.4], +0.1 [-0.4, +0.6] and +0.2 [-0.9, +1.4] more per hour (paired mean and 95% interval).
   On the secret seeds the same pairs win. Never asking and asking where caution is expensive do not dominate each
   other, and the tests check that this stays so. The harm of `cost_aware` is zero by construction in the default
   settings (with `max_rescans=1`, for example, its first rescan could already end in a skipped line); the misses
   that follow the person's wrong answers to its questions, 8 over the 20 hours, are counted as theirs.
5. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by a baseline that ignores the confidence (`always_safe_reroute`, or
   `cost_aware` for 0.99). Going from 0.9 to 0.85 cuts the interruptions by a fifth and more than doubles the harm.
6. **The reference supervisor is dominated by `cost_aware` and `motion_aware`**: 64.5 against 23.2 and 22.8
   interruptions an hour, 1.9 against 0 harm, 1002 against 1055 deliveries. Of its 1273 questions over the 10
   seeds, 42% are about kinds it never learns to trust (scan failures, for example: the scanner is right at most
   79% of the time, short of the 95% target), 39% about incidents below its learned threshold, 16% come from the
   shadow phase, and the rest are escalations and audits (the `reported_reason_*` columns of the CSV). It also asks
   about low batteries, 21 times an hour, where the others simply charge. Calibrating trust costs questions that a
   cheap cautious action makes unnecessary.
7. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than `cost_aware`. Simple rules already move along the front: a supervisor that waits up to three
   times at a pick face before asking, and asks about a label only after two failed rescans, gets 18.1 / 0 / 1049
   (not included as a baseline; it was written by a reviewer).

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 64.5 ± 1.2 | 1.9 ± 0.8 | 1002 ± 10 | | | |
| one shared threshold and target instead of one per kind | 64.2 ± 1.5 | 6.9 ± 2.0 | 980 ± 8 | -0.3 [-3.9, +3.3] | **+5.0 [+0.3, +9.7]** | **-22.3 [-35.0, -9.6]** |
| no joining of questions about the same cause | 64.1 ± 2.0 | 2.9 ± 0.8 | 998 ± 8 | -0.4 [-4.0, +3.2] | +1.1 [-0.4, +2.6] | -4.8 [-24.9, +15.3] |
| no gate (may drive through motion or the human zone) | 60.2 ± 0.8 | 16.5 ± 7.5 | 1000 ± 8 | **-4.3 [-8.4, -0.2]** | +14.7 [-3.0, +32.3] | -2.5 [-17.7, +12.8] |
| no safe default when the person is busy | 67.2 ± 1.9 | 2.9 ± 1.0 | 973 ± 13 | **+2.6 [+0.3, +5.0]** | +1.1 [-1.1, +3.3] | **-29.2 [-54.2, -4.3]** |
| deadlocks calibrated like other kinds instead of always yielding | 62.2 ± 2.8 | 4.4 ± 1.6 | 985 ± 11 | -2.2 [-7.1, +2.6] | +2.5 [-0.9, +6.0] | **-17.4 [-31.2, -3.5]** |

- **The safe default when the person is busy** helps on two axes: without it the reference asks 2.6 more
  questions an hour, questions wait longer (81 s instead of 57 s), and the fleet delivers 29 fewer lines an hour.
- **Per-kind calibration** shows up now: with one shared threshold the reference misses more (mostly low
  batteries) and delivers 22 fewer lines an hour.
- **Always yielding in deadlocks** keeps 17 deliveries an hour. Deadlocks are rare now (about 2 an hour), but a
  robot in a standoff that waits for an answer probably holds up the robots behind it as well.
- **The gate** shows the largest mean increase in harm without it, from a few critical misses; the interval
  includes zero. Without it the reference asks 4.3 fewer questions an hour.
- **Joining questions** shows no difference these seeds can detect; it is rare (55 joins against 1273 questions).
- Earlier versions of this page drew other conclusions about these features. The sixth round of fixes changed the
  fleet's traffic rules (see the caveats), and with intervals this wide, these 10 seeds rank the features only
  roughly.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors: `cost_aware` 24.9 / 0 / 1080 (interrupt/h, harm/h, delivered/h),
`motion_aware` 24.3 / 0 / 1078, `always_safe_reroute` 0.5 / 5.4 / 1078, `patient` 0.3 / 4.9 / 1074, `reference`
58.2 / 5.2 / 1032. The front is `always_safe`, `always_safe_reroute`, `patient`, `cost_aware` and `motion_aware`.
The best under the three profiles are `cost_aware`, `patient` and `patient`, each with the other member of its
pair as runner-up and an interval that holds zero (+0.0 [-0.3, +0.4], +0.4 [-0.1, +0.9], +0.6 [-0.2, +1.4]).
Since the key is gone, this run cannot be repeated exactly; rerunning it draws new seeds and should give the same
picture.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after six rounds of review.** In the first version caution cost nothing; in the
  second, robots rescanned damaged labels forever and queued behind them, which made caution look far more
  expensive than it is; the third fixed how misses are attributed and how the fleet treats an obstacle it already
  knows; the fourth fixed robots trapping each other at station bays and in the one-lane top aisle, which had cost
  every supervisor deliveries and dead batteries; the fifth fixed robots queued outside a full station that never
  gave way, which froze clusters of robots for an hour or more in some episodes; the sixth fixed two robots in the
  one-lane aisle stepping back and forth for each other for ever, robots queued behind a robot waiting for the
  person's answer raising deadlocks of their own (most of `always_ask`'s questions, which had cut its deliveries to
  a third), and robots shut in a bay by an obstacle in its entrance. Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.85 lines an hour
  (0.4 / 0.4 / 1066 against `cost_aware`'s 12.1 / 0 / 1061) and is the best supervisor under all three cost
  profiles; `patient` scores exactly the same, because its rule then never applies.
- **The same author wrote the simulator and every supervisor**, including `cost_aware`, `patient` and
  `motion_aware`, which were written after seeing where caution is cheap in this simulator. Independent supervisors
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
