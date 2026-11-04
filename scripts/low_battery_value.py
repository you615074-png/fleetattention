"""How much a low-battery decision is worth: `staged`, an oracle copy of it that takes the labelled action on every
low battery (it reads the label, so it is a measurement, not a supervisor), and a copy that always charges first.

    uv run python scripts/low_battery_value.py [--seeds 10] [--set name=value ...]

Prints the paired difference in deliveries an hour to the always-charging copy (mean ± standard error over seeds),
and how often finishing first is the labelled action.
"""
from __future__ import annotations

import argparse
import statistics
from dataclasses import replace
from multiprocessing import Pool

from fleetattention.cli import setting
from fleetattention.model import Decision
from fleetattention.supervisors import Staged
from fleetattention.world import Config, Episode


class ChargeFirst(Staged):
    name = 'staged_charge_first'

    def decide(self, obs, ctx):
        return Decision.act('charge_now') if obs.kind == 'low_battery' else super().decide(obs, ctx)


class Oracle(Staged):
    name = 'staged_oracle'
    episode: Episode | None = None

    def decide(self, obs, ctx):
        if obs.kind == 'low_battery':
            return Decision.act(self.episode.incidents[obs.incident].correct)
        return super().decide(obs, ctx)


def run(job: tuple[str, int, Config]) -> tuple[str, int, float, float, int, int]:
    name, seed, config = job
    sup = {'staged': Staged, 'charge_first': ChargeFirst, 'oracle': Oracle}[name]()
    episode = Episode(sup, seed, config)
    sup.episode = episode
    row = episode.run()
    warnings = [i for i in episode.incidents.values() if i.obs.kind == 'low_battery']
    return name, seed, row['delivered_per_hour'], row['harm_per_hour'], len(warnings), \
        sum(i.correct == 'finish_task' for i in warnings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--seeds', type=int, default=10)
    parser.add_argument('--set', type=setting, action='append', default=[], metavar='NAME=VALUE')
    args = parser.parse_args()
    config = replace(Config(), **dict(args.set))
    jobs = [(name, seed, config) for name in ('staged', 'charge_first', 'oracle') for seed in range(args.seeds)]
    with Pool() as pool:
        results = {(name, seed): rest for name, seed, *rest in pool.map(run, jobs)}
    for name in ('staged', 'oracle'):
        diffs = [results[name, s][0] - results['charge_first', s][0] for s in range(args.seeds)]
        harm = statistics.fmean(results[name, s][1] for s in range(args.seeds))
        print(f'{name:8s} delivered/h vs charging first: {statistics.fmean(diffs):+.1f} '
              f'± {statistics.stdev(diffs) / len(diffs) ** .5:.1f}   harm/h {harm:.2f}')
    warnings = sum(results['staged', s][2] for s in range(args.seeds))
    finish = sum(results['staged', s][3] for s in range(args.seeds))
    hours = args.seeds * config.hours
    print(f'low-battery warnings {warnings / hours:.1f} an hour; finishing first labelled right at {finish / warnings:.0%}')


if __name__ == '__main__':
    main()
