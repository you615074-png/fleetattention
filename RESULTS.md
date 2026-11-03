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
| always_ask | 112.2 ± 2.1 | 0.0 | 352 ± 38 | 0.0 | 0.0 | 0.0 | 0.0 | 94% | 521 | |
| threshold@0.99 | 111.8 ± 1.7 | 0.0 | 370 ± 35 | 0.0 | 0.0 | 0.0 | 0.0 | 94% | 509 | |
| threshold@0.95 | 99.2 ± 2.1 | 7.0 ± 1.4 | 496 ± 40 | 0.0 | 1.3 | 0.9 | 0.0 | 89% | 463 | |
| threshold@0.9 | 78.8 ± 3.8 | 27.2 ± 5.7 | 702 ± 60 | 0.1 | 4.2 | 2.5 | 0.0 | 83% | 342 | |
| threshold@0.85 | 46.1 ± 1.0 | 68.6 ± 15.3 | 923 ± 27 | 0.5 | 8.2 | 5.1 | 0.1 | 72% | 206 | |
| threshold@0.8 | 38.9 ± 1.1 | 83.4 ± 14.1 | 914 ± 19 | 0.7 | 9.0 | 6.7 | 0.1 | 71% | 261 | |
| threshold@0.7 | 27.5 ± 0.8 | 109.5 ± 15.2 | 949 ± 18 | 0.9 | 11.6 | 12.9 | 0.0 | 72% | 282 | |
| threshold@0.6 | 18.6 ± 0.7 | 124.8 ± 16.5 | 961 ± 22 | 0.9 | 14.1 | 18.3 | 0.4 | 69% | 342 | |
| never_ask | 7.5 ± 0.5 | 195.3 ± 11.2 | 1019 ± 13 | 2.2 | 14.2 | 28.4 | 0.4 | 61% | 0 | |
| always_safe | 0.7 ± 0.3 | 3.6 ± 0.4 | 894 ± 13 | 0.0 | 0.0 | 0.0 | 14.3 | 6% | 0 | * |
| always_safe_reroute | 0.2 ± 0.1 | 4.8 ± 0.5 | 1049 ± 9 | 0.0 | 0.0 | 0.0 | 19.4 | 2% | 0 | * |
| patient | 0.4 ± 0.1 | 4.4 ± 0.5 | 1045 ± 9 | 0.0 | 0.0 | 0.0 | 17.6 | 3% | 0 | * |
| cost_aware | 22.9 ± 0.9 | 0.0 | 1050 ± 8 | 0.0 | 0.0 | 0.0 | 0.0 | 21% | 40 | |
| motion_aware | 22.4 ± 0.9 | 0.0 | 1050 ± 8 | 0.0 | 0.0 | 0.0 | 0.0 | 20% | 38 | * |
| **reference** | 59.9 ± 1.7 | 4.0 ± 2.0 | 988 ± 11 | 0.0 | 0.7 | 0.9 | 0.0 | 62% | 72 | |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors, and a
supervisor just off it (`cost_aware`, a hair behind `motion_aware`) is not clearly worse. Interruptions are
questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts only
the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have avoided (a
battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 94% of the time, a question waits almost nine
   minutes, and the fleet delivers 65% less than when nobody asks.
2. **The trade-off is mostly about scan failures.** Of the incidents where the cautious action has a real price,
   scan failures dominate in the default settings:
   - `always_safe_reroute` drives around every obstacle, rescans until the fleet gives the item up, and charges at
     the first warning. It interrupts less than once an hour, never drives into anything, and delivers as much as
     any supervisor. Its price is 9.7 order lines an hour that fail needlessly: 8.4 are items the fleet skipped
     after three rescans although the scanner's guess was right, and 1.4 are pick faces it gave up although a
     person was about to leave or a ghost only seemed to block them (`supervisor_low_*` columns).
   - `cost_aware` asks about an obstacle on the pick face the robot is heading to and about a label that one
     rescan could not read, and takes the cautious action everywhere else. It asks 22.4 questions an hour, 20.6 of
     them about scans, and fails no line by its own decision.
   So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both numbers follow
   from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many failures are
   damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   halves the lines lost to obstacles (0.6 an hour instead of 1.4). Waiting at every obstacle (`always_safe`) loses
   none, but costs 15% of the deliveries. `motion_aware` waits instead of asking when the obstacle on the pick face
   moves, and saves a few obstacle questions over `cost_aware` (1.3 instead of 1.8 an hour); the two are level
   within the errors.
4. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the two that ask where caution is expensive are best where attention is cheap
   (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where a
   question costs half a wrong pick or more. Within each pair the seeds do not tell the two apart: the runner-up
   costs +0.1 [-0.3, +0.5], +0.2 [-0.4, +0.8] and +0.1 [-0.9, +1.0] more per hour (paired mean and 95% interval).
   On the secret seeds the same pairs win. Never asking and asking where caution is expensive do not dominate each
   other, and the tests check that this stays so. The harm of `cost_aware` is zero by construction in the default
   settings (with `max_rescans=1`, for example, its first rescan could already end in a skipped line); the misses
   that follow the person's wrong answers to its questions, 8 over the 20 hours, are counted as theirs.
5. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is beaten on all three axes
   by a baseline that ignores the confidence (`always_safe_reroute`, or `cost_aware` for 0.99). Going from 0.9 to
   0.85 cuts the interruptions by 41% and raises harm two and a half times.
6. **The reference supervisor is beaten on every axis by `cost_aware` and `motion_aware`**: 59.9 vs 22.4
   interruptions an hour, 4.0 vs 0 harm, 988 vs 1050 deliveries. Of its 1168 questions over the 10 seeds, 44% are
   about incidents below its learned threshold, 34% about kinds it never learns to trust (scan failures, for
   example: the scanner is right at most 79% of the time, short of the 95% target), 19% come from the shadow phase,
   and the rest are escalations and audits (the `reported_reason_*` columns of the CSV). It also asks about low
   batteries, 20 times an hour, where the others simply charge. Calibrating trust costs questions that a cheap
   cautious action makes unnecessary.
7. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than `cost_aware`. Simple rules already move along the front: a supervisor that waits twice at a pick
   face before asking, and asks about a label only after two failed rescans, gets 18.9 / 0 / 1047 (not included as
   a baseline; it was written by a reviewer).

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 59.9 ± 1.7 | 4.0 ± 2.0 | 988 ± 11 | | | |
| one shared threshold and target instead of one per kind | 62.1 ± 2.2 | 6.4 ± 3.0 | 988 ± 8 | +2.2 [-2.1, +6.6] | +2.5 [-4.9, +9.8] | -0.8 [-26.6, +24.9] |
| no joining of questions about the same cause | 61.1 ± 2.8 | 3.0 ± 1.3 | 1005 ± 9 | +1.2 [-3.1, +5.6] | -1.0 [-4.1, +2.1] | +16.6 [-10.7, +43.8] |
| no gate (may drive through motion or the human zone) | 57.9 ± 2.1 | 17.8 ± 8.1 | 1004 ± 6 | -1.9 [-5.5, +1.6] | +13.8 [-5.4, +33.1] | +15.4 [-15.8, +46.7] |
| no safe default when the person is busy | 62.5 ± 1.4 | 4.6 ± 1.3 | 950 ± 16 | **+2.6 [+0.6, +4.7]** | +0.7 [-2.8, +4.1] | **-38.1 [-61.9, -14.4]** |
| deadlocks calibrated like other kinds instead of always yielding | 61.9 ± 1.8 | 8.0 ± 4.9 | 985 ± 10 | +2.0 [-1.1, +5.2] | +4.0 [-8.4, +16.5] | -3.4 [-19.0, +12.3] |

- **The safe default when the person is busy** is the only feature with a clear effect at 10 seeds: without it
  the reference asks 2.6 more questions an hour, questions wait longer (109 s instead of 72 s), and the fleet
  delivers 38 fewer lines an hour.
- **The gate** shows the largest mean increase in harm without it (four times as much), from a few critical
  misses; the interval includes zero.
- **Per-kind calibration**, **joining questions** and **always yielding in deadlocks** show no difference these
  seeds can detect. Joining is rare: 39 joins against 1168 questions.
- Earlier versions of this page reported a clear effect of always yielding in deadlocks (about 12 questions an
  hour). It came from robots jamming outside full stations, which a review found and the fifth round of fixes
  removed; the jam hit the reference supervisor far more often than its variants. With intervals this wide, these
  10 seeds rank the features only roughly.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors: `cost_aware` 24.9 / 0 / 1066 (interrupt/h, harm/h, delivered/h),
`motion_aware` 24.2 / 0 / 1059, `always_safe_reroute` 0.3 / 5.3 / 1061, `patient` 0.5 / 4.7 / 1056, `reference`
58.7 / 5.2 / 1002. The front is `always_safe`, `always_safe_reroute`, `patient`, `cost_aware` and `motion_aware`.
The best under the three profiles are `cost_aware`, `patient` and `always_safe_reroute`, each with the other
member of its pair as runner-up; only `cost_aware`'s lead over `motion_aware` (+0.3 [+0.0, +0.6]) is at the edge
of what these seeds can tell.
Since the key is gone, this run cannot be repeated exactly; rerunning it draws new seeds and should give the same
picture.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after five rounds of review.** In the first version caution cost nothing; in the
  second, robots rescanned damaged labels forever and queued behind them, which made caution look far more
  expensive than it is; the third fixed how misses are attributed and how the fleet treats an obstacle it already
  knows; the fourth fixed robots trapping each other at station bays and in the one-lane top aisle, which had cost
  every supervisor deliveries and dead batteries; the fifth fixed robots queued outside a full station that never
  gave way, which froze clusters of robots for an hour or more in some episodes. Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.85 lines an hour
  (0.2 / 0.4 / 1063 against `cost_aware`'s 12.2 / 0 / 1061) and is the best supervisor under all three cost
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
