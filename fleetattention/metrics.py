"""Episode metrics, aggregation over seeds, and the Pareto front.

The three headline axes are interruptions per hour (questions plus forced recoveries), harm per hour from the
supervisor's own misses, and correct deliveries per hour. Harm is a weighted count; the weights are a profile, not a
truth. Throughput is an axis of its own so that caution is not free: waiting, detours and charging show up
there. The trade-off surface is the result, not any single score.
"""
from __future__ import annotations

import functools
import math
import statistics
from typing import TYPE_CHECKING, Any

from .model import SEVERITIES

if TYPE_CHECKING:
    from .world import Episode

HARM_WEIGHTS = {'critical': 100.0, 'high': 10.0, 'medium': 1.0, 'low': .5}
"""critical: drove into a person. high: a battery ran out. medium: drove into a box, or a wrong item delivered.
low: an order line failed needlessly (rerouted away from a pick face a person or a ghost was on, or skipped a scan)."""
AXES = (('interruptions_per_hour', 'min'), ('harm_per_hour', 'min'), ('delivered_per_hour', 'max'))

# Prices that turn the three axes into one cost per hour, in harm units (a medium miss is 1). They are examples of
# sites, not truths: the front is the result, a profile only ranks the supervisors on it for one kind of site.
PROFILES: dict[str, dict[str, Any]] = {
    'attention_cheap': {'interruption': .1, 'delivery': .05, 'note': 'a dedicated operator; 10 questions = 1 mispick'},
    'balanced': {'interruption': .5, 'delivery': .05, 'note': '2 questions = 1 mispick, 20 deliveries = 1 mispick'},
    'attention_scarce': {'interruption': 2, 'delivery': .05, 'note': 'a shift lead with other work; 1 question = 2 mispicks'},
}


def cost(row: dict[str, Any], prices: dict[str, Any]) -> float:
    """Cost per hour of a summary row under a profile: interruptions and harm, minus the value of deliveries."""
    return (prices['interruption'] * row['interruptions_per_hour'] + row['harm_per_hour']
            - prices['delivery'] * row['delivered_per_hour'])


def summarize(episode: Episode) -> dict[str, Any]:
    stats, hours = episode.stats, episode.duration / 3600
    misses = stats['misses']
    row: dict[str, Any] = {
        'supervisor': episode.sup.name,
        'seed': episode.seed,
        'hours': hours,
        'questions': stats['questions'],
        'recoveries': stats['recoveries'],
        'interruptions_per_hour': (stats['questions'] + stats['recoveries']) / hours,
        'human_utilization': stats['human_busy'] / episode.duration,
        'mean_answer_latency': stats['answer_latency'] / stats['answered'] if stats['answered'] else 0.0,
        'unanswered': len(episode.questions),
        'delivered_per_hour': (stats['delivered'] - stats['mispicked']) / hours,
        'skipped': stats['skipped'],
        'abandoned': stats['abandoned'],
        'returned': stats['returned'],
        'replanned': stats['replanned'],
        'withdrawn': stats['withdrawn'],
        'incidents': sum(stats['incidents'].values()),
    }
    for by in ('supervisor', 'human', 'system'):
        for severity in SEVERITIES:
            row[f'{by}_{severity}'] = sum(1 for m in misses if m['by'] == by and m['severity'] == severity)
    for kind in ('obstacle', 'low_battery', 'scan_failure'):
        # Where the supervisor's needless failed lines come from.
        row[f'supervisor_low_{kind}'] = sum(1 for m in misses if m['by'] == 'supervisor' and m['severity'] == 'low'
                                            and m.get('kind') == kind)
    row['harm_per_hour'] = sum(HARM_WEIGHTS[s] * row[f'supervisor_{s}'] for s in SEVERITIES) / hours
    for kind, count in stats['incidents'].items():
        row[f'incidents_{kind}'] = count
    for key, count in stats['decisions'].items():
        row[f'decisions_{key}'] = count
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean of each numeric column over seeds, plus the standard error of the headline axes."""
    keys = sorted({k for row in rows for k in row if isinstance(row[k], (int, float)) and k != 'seed'})
    out: dict[str, Any] = {'supervisor': rows[0]['supervisor'], 'seeds': len(rows)}
    for key in keys:
        out[key] = statistics.fmean(row.get(key, 0) for row in rows)
    for key, _ in AXES:
        values = [row[key] for row in rows]
        out[f'{key}_se'] = statistics.stdev(values) / len(values) ** .5 if len(values) > 1 else 0.0
    return out


def pareto(rows: list[dict[str, Any]], axes: tuple[tuple[str, str], ...] = AXES) -> set[int]:
    """Indexes of the rows no other row matches or beats on every axis and beats on one.

    It compares means; differences within the standard errors are not significant."""
    def better(a: dict[str, Any], b: dict[str, Any], key: str, sense: str) -> bool:
        return a[key] < b[key] if sense == 'min' else a[key] > b[key]

    front = set()
    for index, row in enumerate(rows):
        dominated = any(
            all(not better(row, other, key, sense) for key, sense in axes)
            and any(better(other, row, key, sense) for key, sense in axes)
            for other in rows if other is not row)
        if not dominated:
            front.add(index)
    return front


@functools.lru_cache
def t95(df: int) -> float:
    """The two-sided 95% quantile of Student's t with `df` degrees of freedom: where the density, integrated from 0
    by Simpson's rule, reaches .475."""
    c = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(df * math.pi)
    density = lambda x: c * (1 + x * x / df) ** (-(df + 1) / 2)

    def mass(x: float, n: int = 2000) -> float:
        h = x / n
        return h / 3 * (density(0) + density(x) + sum((4 if i % 2 else 2) * density(i * h) for i in range(1, n)))

    low, high = 0.0, 20.0
    for _ in range(50):
        middle = (low + high) / 2
        low, high = (middle, high) if mass(middle) < .475 else (low, middle)
    return (low + high) / 2


def paired(rows: list[dict[str, Any]], baseline: list[dict[str, Any]], key: str) -> tuple[float, float, float, float]:
    """Mean difference of `key` between two supervisors run on the same seeds, its standard error, and a 95%
    interval (t distribution)."""
    base = {row['seed']: row[key] for row in baseline}
    diffs = [row[key] - base[row['seed']] for row in rows if row['seed'] in base]
    mean = statistics.fmean(diffs)
    if len(diffs) < 2:
        return mean, 0.0, mean, mean
    se = statistics.stdev(diffs) / len(diffs) ** .5
    t = t95(len(diffs) - 1)
    return mean, se, mean - t * se, mean + t * se
