"""Command line: `run` one supervisor over seeds, `sweep` the baselines and the reference supervisor, or `ablate`
the reference supervisor one feature at a time."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import hmac
import json
import secrets
import sys
from contextlib import nullcontext
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from .isolate import Isolated, SupervisorError
from .layout import warehouse
from .metrics import AXES, PROFILES, aggregate, cost, paired, pareto
from .supervisors import ABLATIONS, by_name
from .world import Config, DecisionError, Episode

SWEEP = ['always_ask', *(f'threshold@{t:g}' for t in (.99, .95, .9, .85, .8, .7, .6)), 'never_ask',
         'always_safe', 'always_safe_reroute', 'patient', 'cost_aware', 'motion_aware', 'staged', 'reference']
ABLATE = ['reference', *(f'reference-{feature}' for feature in ABLATIONS)]
COLUMNS = [
    ('supervisor', 'supervisor', '{}'),
    ('interrupt/h', 'interruptions_per_hour', '{:.1f}'),
    ('harm/h', 'harm_per_hour', '{:.2f}'),
    ('critical/ep', 'supervisor_critical', '{:.2f}'),
    ('high/ep', 'supervisor_high', '{:.2f}'),
    ('medium/ep', 'supervisor_medium', '{:.2f}'),
    ('low/ep', 'supervisor_low', '{:.2f}'),
    ('human busy', 'human_utilization', '{:.0%}'),
    ('wait s', 'mean_answer_latency', '{:.0f}'),
    ('delivered/h', 'delivered_per_hour', '{:.0f}'),
    ('lines dropped/ep', 'abandoned', '{:.1f}'),
]


def episode_seed(index: int, key: str | None) -> int | str:
    """Seed `index`, or with a key a seed derived from it that nobody without the key can guess. Public seeds are for
    development: a supervisor can recognise them by simulating them itself. Results never contain the key or the
    derived seeds."""
    return index if key is None else hmac.new(key.encode(), str(index).encode(), hashlib.sha256).hexdigest()


def run_seeds(name: str, seeds: int, config: Config, events: Path | None = None, key: str | None = None,
              isolate: bool = False) -> list[dict[str, Any]]:
    """Run supervisor `name` over seeds. With `isolate`, each episode runs it in a process of its own."""
    rows = []
    for index in range(seeds):
        with Isolated(name) if isolate else nullcontext(by_name(name)) as supervisor:
            episode = Episode(supervisor, episode_seed(index, key), config, record=events is not None and index == 0)
            row = episode.run()
            report = getattr(supervisor, 'report', None)
            row.update({f'reported_{k}': v for k, v in (report() if report else {}).items()})
        row['seed'] = index if key is None else f'keyed:{index}'
        rows.append(row)
        if episode.record:
            events.parent.mkdir(parents=True, exist_ok=True)
            events.write_text(''.join(json.dumps(e) + '\n' for e in episode.events))
    return rows


def table(rows: list[dict[str, Any]], front: set[int] = frozenset()) -> str:
    """`front` holds the indexes of the rows on the Pareto front."""
    cells = [[header for header, _, _ in COLUMNS] + ['pareto']]
    for index, row in enumerate(rows):
        cells.append([fmt.format(row.get(key, 0)) for _, key, fmt in COLUMNS] + ['*' if index in front else ''])
    widths = [max(len(r[i]) for r in cells) for i in range(len(cells[0]))]
    return '\n'.join('  '.join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))) for r in cells)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, keys)
        writer.writeheader()
        writer.writerows(rows)


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return value


def positive_float(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError('must be positive')
    return value


def setting(text: str) -> tuple[str, Any]:
    """`name=value` for a `Config` field; the value is a Python literal (`0`, `.5`, `{'box': .9, ...}`)."""
    name, sep, value = text.partition('=')
    if not sep or name not in Config.__dataclass_fields__:
        raise argparse.ArgumentTypeError(f'expected name=value with a Config field name, got {text!r}')
    try:
        return name, ast.literal_eval(value)
    except (ValueError, SyntaxError):
        raise argparse.ArgumentTypeError(f'{value!r} is not a Python literal') from None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='fleetattention')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('run', 'sweep', 'ablate'):
        p = sub.add_parser(command)
        p.add_argument('--seeds', type=positive, default=10)
        p.add_argument('--hours', type=positive_float, help=f'episode length (default {Config.hours:g})')
        p.add_argument('--robots', type=positive, help=f'fleet size (default {Config.robots})')
        p.add_argument('--out', type=Path, default=Path('results'))
        p.add_argument('--set', type=setting, action='append', default=[], metavar='NAME=VALUE',
                       help='change one Config setting, e.g. --set obstacle_at_pick=0; may be repeated')
        keys = p.add_mutually_exclusive_group()
        keys.add_argument('--secret-seeds', action='store_true',
                          help='derive episode seeds from a random key that only this process ever holds; implies --isolate')
        keys.add_argument('--seed-key-file', type=Path,
                          help='derive episode seeds from the key in this file, to repeat a secret run; implies --isolate')
        p.add_argument('--isolate', action='store_true', help='run each supervisor in a process of its own')
        if command == 'run':
            p.add_argument('supervisor', help='a name from the sweep, threshold@<value>, reference-<feature> or module:Class')
            p.add_argument('--events', type=Path, help='write the event log of seed 0 as JSON lines')
    args = parser.parse_args(argv)
    changes = dict(args.set)
    for name in ('hours', 'robots'):
        if getattr(args, name) is not None:
            if name in changes:
                parser.error(f'--{name} and --set {name}= both given')
            changes[name] = getattr(args, name)
    try:
        config = replace(Config(), **changes)
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    room = len(warehouse().aisles)
    if config.robots > room:
        parser.error(f'{config.robots} robots do not fit in the {room} aisle cells of the warehouse')
    names = {'run': [getattr(args, 'supervisor', '')], 'sweep': SWEEP, 'ablate': ABLATE}[args.command]
    # The key never goes on a command line or into the environment, where the supervisor's process could find it.
    key = secrets.token_hex(32) if args.secret_seeds else \
        args.seed_key_file.read_text().strip() if args.seed_key_file else None
    if key is not None:
        print(f'Secret seeds: sha256 of the key {hashlib.sha256(key.encode()).hexdigest()[:16]}')
    episodes, summary, by_supervisor = [], [], {}
    for name in names:
        try:
            rows = run_seeds(name, args.seeds, config, getattr(args, 'events', None), key,
                             args.isolate or key is not None)
        except (SupervisorError, DecisionError) as error:
            print(f'{name}: {error}; left out', file=sys.stderr)
            continue
        episodes += rows
        by_supervisor[name] = rows
        summary.append(aggregate(rows))
    if not summary:
        raise SystemExit('no supervisor finished')
    front = pareto(summary)
    print(table(summary, front))
    print(f'\n{args.seeds} seeds x {config.hours:g} h, {config.robots} robots. harm/h weights critical 100, high 10, medium 1, '
          'low 0.5; misses counted are the supervisor\'s own. * marks the Pareto front on interrupt/h, harm/h and '
          'delivered/h.')
    changed = [(f.name, getattr(config, f.name)) for f in fields(Config)
               if f.name not in ('hours', 'robots') and getattr(config, f.name) != getattr(Config(), f.name)]
    if changed:
        print('Settings changed from the defaults: ' + ', '.join(f'{k}={v!r}' for k, v in changed))
    print('\nBest under each cost profile (cost per hour, lower is better), and how much more the runner-up costs on '
          'the same seeds: mean [95% interval]; an interval that holds 0 does not tell the two apart:')
    for profile, prices in PROFILES.items():
        best, *rest = sorted(summary, key=lambda row: cost(row, prices))
        line = f'  {profile:18s} {best["supervisor"]:22s} {cost(best, prices):8.1f}'
        if rest and args.seeds > 1:
            costs = lambda row: [{'seed': r['seed'], 'cost': cost(r, prices)} for r in by_supervisor[row['supervisor']]]
            mean, _, low, high = paired(costs(rest[0]), costs(best), 'cost')
            line += f'   runner-up {rest[0]["supervisor"]} {mean:+.1f} [{low:+.1f}, {high:+.1f}]'
        print(f'{line}   ({prices["note"]})')
    if args.command == 'ablate' and 'reference' in by_supervisor and args.seeds > 1:
        print('\nDifference to reference on the same seeds: mean [95% interval]')
        for name, rows in by_supervisor.items():
            if name != 'reference':
                cells = []
                for key, _ in AXES:
                    mean, _, low, high = paired(rows, by_supervisor['reference'], key)
                    cells.append(f'{key.split("_")[0]} {mean:+.1f} [{low:+.1f}, {high:+.1f}]')
                print(f'  {name:20s} ' + '   '.join(cells))
    write_csv(args.out / f'{args.command}-episodes.csv', episodes)
    write_csv(args.out / f'{args.command}-summary.csv', summary)
    print(f'Wrote {args.out}/{args.command}-episodes.csv and {args.out}/{args.command}-summary.csv')
