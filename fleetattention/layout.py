"""The warehouse grid: shelves, aisles, drop stations, chargers and the human zone."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

Cell = tuple[int, int]
STEPS: tuple[Cell, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    shelves: frozenset[Cell]
    stations: tuple[Cell, ...]
    chargers: tuple[Cell, ...]
    picks: tuple[Cell, ...]
    aisles: tuple[Cell, ...]
    human_zone_width: int

    def free(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height and cell not in self.shelves

    def neighbors(self, cell: Cell) -> Iterable[Cell]:
        x, y = cell
        for dx, dy in STEPS:
            nxt = (x + dx, y + dy)
            if self.free(nxt):
                yield nxt

    def in_human_zone(self, cell: Cell) -> bool:
        """People work at the drop stations, so the columns next to them are shared with people."""
        return cell[0] < self.human_zone_width

    def path(self, start: Cell, goal: Cell, blocked: Callable[[Cell], bool] = lambda _: False) -> list[Cell] | None:
        """Shortest path from start to goal, excluding start; None when goal is unreachable."""
        if start == goal:
            return []
        parents: dict[Cell, Cell] = {start: start}
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            for nxt in self.neighbors(cell):
                if nxt in parents or (nxt != goal and blocked(nxt)):
                    continue
                parents[nxt] = cell
                if nxt == goal:
                    route = [goal]
                    while parents[route[-1]] != start:
                        route.append(parents[route[-1]])
                    return route[::-1]
                queue.append(nxt)
        return None


def warehouse(width: int = 32, height: int = 21, human_zone_width: int = 5, chargers: int | None = None) -> Layout:
    """Double shelf rows with two-cell aisles between them, cross aisles every seventh column,
    drop stations on the left edge and chargers on the right edge.

    Stations and chargers are dead-end bays entered from the side: the edge cells between them are walls, so robots
    never use an edge column as a corridor. `chargers` keeps that many of the charger bays, spread evenly; the
    others are walled off."""
    racks = {
        (x, y)
        for x in range(human_zone_width, width - 4)
        for y in range(height)
        if y % 4 in (1, 2) and x % 7 != 0 and 0 < y < height - 1
    }
    stations = tuple((0, y) for y in range(1, height - 1, 2))
    bays = [(width - 1, y) for y in range(1, height - 1, 3)]
    if chargers is not None:
        if not 1 <= chargers <= len(bays):
            raise ValueError(f'the layout has room for 1 to {len(bays)} chargers')
        if chargers == 1:
            bays = [bays[len(bays) // 2]]
        else:
            bays = [bays[round(i * (len(bays) - 1) / (chargers - 1))] for i in range(chargers)]
    chargers = tuple(bays)
    walls = {(x, y) for x in (0, width - 1) for y in range(height)} - set(stations) - set(chargers)
    shelves = frozenset(racks | walls)
    special = set(stations) | set(chargers)
    picks = tuple(sorted(
        (x, y)
        for x in range(width)
        for y in range(height)
        if (x, y) not in shelves and ((x, y - 1) in racks or (x, y + 1) in racks)
    ))
    aisles = tuple(sorted(
        (x, y) for x in range(width) for y in range(height) if (x, y) not in shelves and (x, y) not in special
    ))
    return Layout(width, height, shelves, stations, chargers, picks, aisles, human_zone_width)
