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
| always_ask | 89.0 ± 1.4 | 0.0 | 844 ± 25 | 0.0 | 0.0 | 0.0 | 0.0 | 84% | 151 | |
| threshold@0.99 | 83.5 ± 1.6 | 0.0 | 895 ± 19 | 0.0 | 0.0 | 0.0 | 0.0 | 80% | 128 | |
| threshold@0.95 | 68.3 ± 1.8 | 14.8 ± 2.6 | 927 ± 22 | 0.0 | 2.8 | 1.5 | 0.0 | 72% | 141 | |
| threshold@0.9 | 55.9 ± 1.9 | 26.1 ± 2.8 | 937 ± 22 | 0.0 | 4.9 | 3.2 | 0.0 | 70% | 157 | |
| threshold@0.85 | 45.5 ± 1.5 | 52.9 ± 7.7 | 925 ± 13 | 0.2 | 8.1 | 4.8 | 0.0 | 72% | 219 | |
| threshold@0.8 | 40.2 ± 0.7 | 87.3 ± 9.8 | 896 ± 22 | 0.6 | 10.8 | 6.6 | 0.0 | 75% | 289 | |
| threshold@0.7 | 26.9 ± 0.8 | 121.5 ± 18.5 | 929 ± 28 | 0.9 | 14.1 | 12.1 | 0.0 | 74% | 347 | |
| threshold@0.6 | 17.9 ± 0.5 | 177.2 ± 26.7 | 984 ± 17 | 2.0 | 13.5 | 19.2 | 0.3 | 70% | 287 | |
| never_ask | 8.2 ± 0.6 | 197.6 ± 22.9 | 1023 ± 9 | 2.1 | 15.6 | 29.0 | 0.5 | 64% | 0 | |
| always_safe | 0.5 ± 0.2 | 3.4 ± 0.4 | 880 ± 18 | 0.0 | 0.0 | 0.0 | 13.4 | 4% | 0 | * |
| always_safe_reroute | 0.3 ± 0.1 | 4.9 ± 0.4 | 1057 ± 8 | 0.0 | 0.0 | 0.0 | 19.6 | 3% | 0 | * |
| patient | 0.6 ± 0.2 | 4.6 ± 0.4 | 1051 ± 9 | 0.0 | 0.0 | 0.0 | 18.3 | 5% | 0 | * |
| cost_aware | 23.4 ± 0.9 | 0.0 | 1057 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 22% | 40 | |
| motion_aware | 22.9 ± 0.9 | 0.0 | 1058 ± 9 | 0.0 | 0.0 | 0.0 | 0.0 | 19% | 34 | * |
| staged | 18.2 ± 0.8 | 0.0 | 1049 ± 8 | 0.0 | 0.0 | 0.0 | 0.0 | 17% | 36 | * |
| **reference** | 64.8 ± 1.5 | 1.9 ± 0.7 | 1002 ± 9 | 0.0 | 0.3 | 0.7 | 0.1 | 61% | 56 | |

± is the standard error over seeds. *front* marks the Pareto front on all three axes (fewer interruptions, less
harm, more deliveries), compared on means; neighbours on it often differ by less than their errors, and a
supervisor just off it (`cost_aware`, a hair behind `motion_aware`) is not clearly worse. Interruptions are
questions plus recoveries of robots whose battery ran out, which is why no supervisor is at zero. Harm counts only
the supervisor's own misses; misses that follow the person's wrong answers and misses nobody could have avoided (a
battery that ran out after a right call, rescans that were right but failed by chance) are counted apart
(`human_*`, `system_*` in the CSV). Each low miss is one order line failed needlessly, so low/ep divided by 2 is
lines per hour.

## What it shows

1. **Asking about everything does not work.** The person is busy 84% of the time, a question waits about two and
   a half minutes, and the fleet delivers 18% less than when nobody asks, because robots stand still while their
   questions wait.
2. **The trade-off is mostly about scan failures.** Of the incidents where the cautious action has a real price,
   scan failures dominate in the default settings:
   - `always_safe_reroute` drives around every obstacle, rescans until the fleet gives the item up, and charges at
     the first warning. It interrupts less than once an hour, never drives into anything, and delivers as much as
     any supervisor. Its price is 9.8 order lines an hour that fail needlessly: 8.5 are items the fleet skipped
     after three rescans although the scanner's guess was right, and 1.4 are pick faces it gave up although a
     person was about to leave or a ghost only seemed to block them (`supervisor_low_*` columns).
   - `cost_aware` asks about an obstacle on the pick face the robot is heading to and about a label that one
     rescan could not read, and takes the cautious action everywhere else. It asks 22.9 questions an hour, 20.8 of
     them about scans, and fails no line by its own decision.
   So the main choice is between asking about some 20 scans an hour and failing about 8 lines. Both numbers follow
   from two assumptions the reviews added, how often scans fail (`scan_failure`, 3%) and how many failures are
   damaged labels (`scan_unreadable`, 50%); see the caveats for what happens without them.
3. **Obstacles add a smaller trade-off of their own.** Waiting twice at a pick face before giving it up (`patient`)
   more than halves the lines lost to obstacles (0.6 an hour instead of 1.4). Waiting at every obstacle
   (`always_safe`) loses none, but costs 17% of the deliveries. `motion_aware` waits instead of asking when the
   obstacle on the pick face moves; it asks about obstacles a little less often than `cost_aware` (1.9 against 2.1
   times an hour), and the two are level within the errors.
4. **So the answer depends on the price of attention, which is the point of the benchmark.** Under the cost
   profiles in `metrics.PROFILES`, the supervisors that ask where caution is expensive are best where attention is
   cheap (a dedicated operator), and the two that never ask are best under the balanced and scarce profiles, where
   a question costs half a wrong pick or more. Within each group the seeds do not tell the best from the runner-up:
   `motion_aware` against `staged` +0.0 [-0.4, +0.4], `always_safe_reroute` against `patient` +0.1 [-0.2, +0.4]
   and +0.4 [-0.4, +1.2] per hour (paired mean and 95% interval). On the secret seeds the same groups win. Never
   asking and asking where caution is expensive do not dominate each other, and the tests check that this stays so.
   The harm of `cost_aware` is zero by construction in the default settings (with `max_rescans=1`, for example, its
   first rescan could already end in a skipped line); the misses that follow the person's wrong answers to its
   questions, 8 over the 20 hours, are counted as theirs.
5. **Trusting the robot's confidence does not pay here.** Every threshold in the grid is dominated, no better on
   any axis and worse on at least one, by a baseline that ignores the confidence (`always_safe_reroute`, or
   `cost_aware` for 0.99). Going from 0.9 to 0.85 cuts the interruptions by a fifth and doubles the harm.
6. **The reference supervisor is dominated by `cost_aware`, `motion_aware` and `staged`**: 64.8 against 18 to 23
   interruptions an hour, 1.9 against 0 harm, 1002 against 1049 to 1058 deliveries. Of its 1279 questions over the
   10 seeds, 42% are about incidents below its learned threshold, 39% about kinds it never learns to trust (scan
   failures, for example: the scanner is right at most 79% of the time, short of the 95% target), 16% come from the
   shadow phase, and the rest are escalations and audits (the `reported_reason_*` columns of the CSV). It also asks
   about low batteries, 22 times an hour, where the others simply charge. Calibrating trust costs questions that a
   cheap cautious action makes unnecessary.
7. **There is room.** The open challenge is to fail fewer lines than the never-asking supervisors with fewer
   questions than the ones that ask. Simple rules already move along the front: `staged`, which a reviewer proposed,
   waits three times at a pick face before asking and asks about a label only after two failed rescans. It asks 22%
   less than `cost_aware` (18.2 questions an hour, 16.9 of them about scans) for 8 fewer deliveries an hour, and is
   on the front.

## Which parts of the reference supervisor matter

`ablate` runs the reference supervisor without one feature at a time and prints, for each variant, the mean
difference to `reference` on the same seeds with a 95% interval (t distribution, 9 degrees of freedom).

| variant | interrupt/h | harm/h | delivered/h | Δ interrupt/h | Δ harm/h | Δ delivered/h |
|---|---:|---:|---:|---:|---:|---:|
| reference | 64.8 ± 1.5 | 1.9 ± 0.7 | 1002 ± 9 | | | |
| one shared threshold and target instead of one per kind | 64.5 ± 1.6 | 6.8 ± 2.0 | 986 ± 9 | -0.2 [-4.1, +3.6] | +5.0 [+0.0, +9.9] | **-16.9 [-31.7, -2.1]** |
| no joining of questions about the same cause | 64.3 ± 2.1 | 5.0 ± 2.0 | 997 ± 7 | -0.4 [-5.5, +4.7] | +3.1 [-1.0, +7.2] | -5.8 [-27.3, +15.7] |
| no gate (may drive through motion or the human zone) | 62.7 ± 1.4 | 21.1 ± 8.0 | 1003 ± 8 | -2.0 [-5.4, +1.3] | **+19.2 [+1.7, +36.7]** | +0.8 [-7.5, +9.1] |
| no safe default when the person is busy | 67.5 ± 1.4 | 2.4 ± 1.0 | 952 ± 23 | **+2.8 [+0.6, +5.0]** | +0.6 [-1.4, +2.5] | **-50.0 [-96.1, -4.0]** |
| deadlocks calibrated like other kinds instead of always yielding | 61.0 ± 2.7 | 3.4 ± 1.5 | 998 ± 9 | -3.8 [-7.5, -0.0] | +1.5 [-2.3, +5.3] | -4.1 [-15.7, +7.5] |

- **The safe default when the person is busy** helps on two axes: without it the reference asks 2.8 more
  questions an hour, questions wait longer (92 s instead of 56 s), and the fleet delivers 50 fewer lines an hour.
- **The gate** prevents harm: without it the reference drives into people (0.4 critical misses an episode) and
  harm rises tenfold.
- **Per-kind calibration** keeps 17 deliveries an hour; with one shared threshold the reference also misses more
  low batteries (the harm interval just reaches zero).
- **Joining questions** and **always yielding in deadlocks** show no effect these seeds can tell apart from zero.
  Joining is rare (48 joins against 1279 questions), and so are deadlocks (about 2 an hour).
- The previous version of this page found a clear effect of always yielding in deadlocks on deliveries, and none
  of the gate on harm. Small changes to the fleet's traffic rules between the two versions moved both, which shows
  how roughly 10 seeds rank these features.

These are differences in this simulator with these settings, not general effects.

## On secret seeds, with every supervisor isolated

`--secret-seeds` runs each supervisor in its own process on seeds derived from a random key that was never written
down. The picture is the same within the errors: `cost_aware` 26.4 / 0 / 1062 (interrupt/h, harm/h, delivered/h),
`motion_aware` 25.6 / 0 / 1063, `staged` 20.1 / 0 / 1056, `always_safe_reroute` 0.6 / 5.7 / 1059, `patient`
0.4 / 5.4 / 1052, `reference` 63.7 / 3.0 / 996. The front is `always_safe`, `always_safe_reroute`, `patient`,
`motion_aware` and `staged`. The best under the three profiles are `staged`, `patient` and `patient`, each with a
member of its group as runner-up and an interval that holds zero (`motion_aware` +0.2 [-0.4, +0.8],
`always_safe_reroute` +0.1 [-0.7, +0.8] and +0.4 [-0.8, +1.6]).
Since the key is gone, this run cannot be repeated exactly; rerunning it draws new seeds and should give the same
picture.

## Caveats

- **Everything is simulated.** Every rate, accuracy, duration and cost is an assumption, in `Config` and `metrics`.
  Different assumptions move every number.
- **The benchmark was changed after seven rounds of review.** In the first version caution cost nothing; in the
  second, robots rescanned damaged labels forever and queued behind them, which made caution look far more
  expensive than it is; the third fixed how misses are attributed and how the fleet treats an obstacle it already
  knows; the fourth fixed robots trapping each other at station bays and in the one-lane top aisle, which had cost
  every supervisor deliveries and dead batteries; the fifth fixed robots queued outside a full station that never
  gave way, which froze clusters of robots for an hour or more in some episodes; the sixth fixed two robots in the
  one-lane aisle stepping back and forth for each other for ever, robots queued behind a robot waiting for the
  person's answer raising deadlocks of their own (most of `always_ask`'s questions, which had cut its deliveries to
  a third), and robots shut in a bay by an obstacle in its entrance; the seventh fixed a robot raising the same
  obstacle every second when rerouting left it no way out, two robots shuffling around each other for minutes, and
  robots shut in a bay giving their order line up every 15 seconds. Obstacles on pick faces, damaged labels, a fleet limit on rescans
  and throughput as an axis came out of those reviews. They are plausible features of real warehouses, but they
  were chosen knowing what they would change, and the conclusions above depend on them. With no obstacles on pick
  faces and no damaged labels (the fourth command above), `always_safe_reroute` fails 0.85 lines an hour
  (0.3 / 0.4 / 1066 against `cost_aware`'s 12.1 / 0 / 1061) and is the best supervisor under the balanced and
  scarce profiles; `patient` scores exactly the same, because its rule then never applies. `staged` (4.7 / 0 /
  1068) is best where attention is cheap and dominates `cost_aware`.
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
