# FleetAttention

An open benchmark for robot-fleet supervisors: **how often do they interrupt a person, how many risks do they miss,
and how much work gets done?**

One person supervises a fleet of warehouse robots. Robots run into things they cannot settle alone: an unknown
obstacle, a battery that may not last another task, an item the scanner is unsure about, two robots blocking each
other. For each incident a supervisor either acts on its own or asks the person. Asking hands the decision to the
person, who is usually but not always right; it costs attention, and a busy person answers slowly, which stalls the
fleet. Acting alone is fast but sometimes wrong. Always taking
the cautious action is safe too, but robots then wait, detour and give up work.

The benchmark measures that three-way trade-off. It reports a front, not a single score: different sites put
different prices on an interruption, a miss and an hour of lost throughput.

> Status: phase 1 (simulation, metrics, rule baselines). Everything here is **simulated**; incident rates,
> sensor accuracies, durations and costs are assumptions, open to challenge. Rates, accuracies and durations are in
> `Config`, harm weights and cost profiles in `metrics`; the shapes of a few distributions are fixed in the code.

## Quick start

Python 3.11+, no dependencies.

```sh
python3 -m fleetattention sweep --seeds 10           # baselines and the reference supervisor
python3 -m fleetattention ablate --seeds 10          # the reference supervisor without one feature at a time
python3 -m fleetattention run reference --seeds 10   # one supervisor
python3 -m fleetattention run never_ask --seeds 1 --events results/events.jsonl
python3 -m fleetattention sweep --set obstacle_at_pick=0 --set scan_unreadable=0   # other assumptions
python3 -m fleetattention run mymodule:Mine --isolate  # your own supervisor, in a process of its own
python3 -m fleetattention sweep --secret-seeds       # secret seeds, every supervisor isolated
uv run pytest                                         # tests
```

Results go to `results/` as per-episode and summary CSV files.

The sweep also prints which supervisor is best under each cost profile in `metrics.PROFILES`.

**Comparing supervisors fairly.** The simulator is public and deterministic, so a supervisor that knows the episode
seed can simulate the episode itself and read the ground truth. In the simulator's process it can also read the
truth directly (through the call stack, for example).

- Seeds 0, 1, 2, ... are public and fine for development, but a supervisor can recognise them. Scores meant for
  comparison should use `--secret-seeds`: the seeds come from a random key that exists only in the memory of the
  process running the benchmark and is never written anywhere. The output shows a hash of the key, not the key.
  `--seed-key-file` repeats a secret run from a key you keep yourself; keep that file away from the supervisor.
- Both turn on `--isolate`: every episode runs the supervisor in a fresh process with its own command line, an
  empty environment and an empty temporary working directory, talking JSON over a pipe, one reply per request.
  Each call has a time limit, sending included, and each reply a size limit. A supervisor that hangs, crashes,
  replies out of turn, reports anything but plain names and numbers, or makes an illegal decision is killed,
  together with the processes it started that stayed in its process group, and left out. Results name it by the
  spec you gave, not by the name it gives itself. Without `--isolate` a supervisor runs in the benchmark's own
  process and could also name itself after a baseline.
- This is not a sandbox. The supervisor's process runs as your user and can read and write what you can, so it
  could, for example, keep notes on disk from one episode to the next. For code you do not trust, run the
  benchmark inside an OS sandbox (a container, or a user without access to the key or the results).

## The simulation

- A 32 x 21 grid warehouse: double shelf rows with two-cell aisles between them and a one-lane aisle along the top
  wall, drop stations on the left (where people work), chargers on the right; stations and chargers are
  dead-end bays. 24 robots pick items and bring them to stations; one tick is one second; an episode is two
  hours. A fifth of the pick faces get four fifths of the orders.
- The fleet manager handles traffic with simple rules of its own: short local detours; head-on rules (one robot
  steps aside, and keeps giving way to the same robot until it reaches its goal, so the two settle who backs out of
  the one-lane aisle); queueing outside a full bay and stepping aside for robots coming out, and waiting inside a
  bay while a robot that is not moving stands in its way out; after a minute stuck behind another robot, a way
  around the robots standing still however long, or else a new goal; a new goal when one cannot be reached, a robot
  stays on it, or a robot has made no headway towards it for a minute and a half; giving an item up after three
  failed rescans. A head-on standoff these rules cannot settle reaches the supervisor, as a deadlock. The rules are
  deliberately plain, and traffic still costs throughput: robots queue, detour and sometimes give an order line up.
- A simulated person answers one question at a time: about 20 seconds per answer, 10 seconds more when questions
  arrive back to back, right 97% of the time. Recovering a robot whose battery ran out takes five minutes of their
  time and counts as an interruption.

### Incidents

| Kind | Actions | What makes it hard |
| --- | --- | --- |
| `obstacle` | `proceed`, `reroute`, `wait` | A box, a person or a sensor ghost. Driving into a person is a **critical** miss, into a box a medium one. Several robots meet the same obstacle. In an aisle, driving around is cheap and right for anything but a ghost; on the pick face the robot is heading to (`at_goal`), rerouting gives the order line up, which is a **low** miss unless it was a box. Waiting for a ghost or a box can take many minutes. |
| `low_battery` | `finish_task`, `charge_now` | The robot estimates with its nominal drain, but older robots drain up to 1.8x faster. `charge_now` is always right: a robot charges to full either way, so finishing first gains nothing, and running out after it is a **high** miss. Reaching a charger after finishing first gives the supervisor no verdict. Every charging session starts with a minute of docking, whenever it happens. |
| `scan_failure` | `pick_anyway`, `rescan`, `skip` | The scanner is overconfident: its guess is right about 20 points less often than it claims. Half the failures are damaged labels that no rescan will read; after three failed rescans the fleet skips the line. A wrong pick is a **medium** miss; skipping a line whose guess was right, or that a rescan could have read, is a **low** one. A person can identify any item. |
| `deadlock` | `yield`, `wait` | Never harmful whatever is chosen; asking about it only wastes attention and time. Rare (one to five an hour), since the fleet settles most standoffs itself; it tests interruptions and throughput, not harm. |

With the default settings, most of the trade-off comes from scan failures: about 20 questions an hour, or about 8
order lines an hour lost by never asking. Obstacles add a smaller part, and on low batteries caution costs almost
nothing (see RESULTS.md).

Each observation carries the robot's suggested action and confidence. How well that confidence can be trusted differs
per kind, and finding out is part of the job.

## Writing a supervisor

```python
from fleetattention.model import Decision
from fleetattention.supervisors import Supervisor

class Mine(Supervisor):
    name = 'mine'

    def decide(self, obs, ctx):
        # obs: kind, suggested, confidence, attempt, target, human_zone, details ...
        # ctx: time, pending questions, how many jobs the person has waiting
        if obs.confidence > .9:
            return Decision.act(obs.suggested)
        return Decision.ask()          # or Decision.join(question_id) to share a pending question

    def on_answer(self, obs, answer): ...     # what the person said was right (answer.incident: what was asked)
    def on_outcome(self, obs, outcome): ...   # after acting alone: ok True, False, or None when nothing showed
```

Supervisors see only copies of observations (with read-only `details`), answers and visible outcomes; ground truth
stays in the simulator. An optional `report()` returning a dict of numbers adds `reported_*` columns to the CSV.
Run your own as `module:Class`, with `--secret-seeds` for scores you want to compare.

## Metrics

- `interrupt/h`: questions plus forced recoveries per hour.
- `harm/h`: the supervisor's own misses per hour, weighted critical 100, high 10, medium 1, low 0.5. A miss is an
  action other than the right one that led to harm; misses of the person (wrong answers) and of the system are
  counted apart. A person's answer applied to an incident the supervisor joined to the question is the person's
  only if it was about the same cause (the same obstacle, say); otherwise any miss it leads to is the supervisor's,
  which chose to apply an answer about something else. The weights are a profile, not a truth; the per-severity counts are reported too.
- `delivered/h`: correct deliveries per hour. This is where caution shows its cost.
- Also reported: how busy the person is, how long questions wait, and order lines dropped for any reason, including
  lines the fleet manager gives up when it sends a robot to another goal (`replanned`). Orders are an endless
  stream, so a robot that drops a line simply takes the next one; only the needless failures above count as harm,
  and lines dropped by the traffic rules are no one's miss. Lines a robot gives back before starting on them, when
  it goes to charge at the battery warning that comes with a new task, are counted apart (`returned`).
- `withdrawn`: questions the fleet took back because the obstacle they were about went away before anyone
  answered. A withdrawn question still counts in `interrupt/h`: it was raised, and the person may have read it.
- The Pareto front marks the supervisors no other one beats on all three axes. It compares means; check the
  standard errors before reading much into a close call. Cost profiles in `metrics.PROFILES` turn the three axes into
  one cost for a few example sites.

## Supervisors included

- `always_ask`, `never_ask`, and `threshold@t`: follow the robot when its confidence reaches `t`, otherwise ask.
- `always_safe` and `always_safe_reroute`: never ask, always take the cautious action (waiting at, or driving around,
  every obstacle). `patient` does the same but waits twice at an obstacle on the pick face before giving the line up.
  These are strong baselines: see RESULTS.md for how they compare under the three cost profiles.
- `cost_aware`: ask only where the cautious action is expensive (an obstacle on the pick face, a label one rescan
  could not read), otherwise take it. `motion_aware` waits instead of asking when that obstacle moves. `staged`,
  proposed by a reviewer, asks later still: after three waits at the pick face and two failed rescans.
- `reference`: built on the principle of DeepSeek's open-source
  [dsh-superagent](https://github.com/deepseek-ai/dsh-superagent-prototype) design, *take as little human
  attention as possible*: hard safety rules in code, one question per cause, a shadow phase that calibrates trust
  per incident kind, audits, and a safe default when the person is busy. It is a baseline to beat, not an answer,
  and `cost_aware`, `motion_aware` and `staged` beat it on every axis. `reference-<feature>` runs it without one feature.

## Results

See [RESULTS.md](RESULTS.md).
