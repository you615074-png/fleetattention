# Changelog

Every round below came out of a review of the previous version. Each changed the simulator, so the numbers in
RESULTS.md come from the latest version only.

1. Caution cost nothing in the first version; throughput became an axis.
2. Robots rescanned damaged labels forever and queued behind them, which made caution look far more expensive than
   it is; the fleet now skips an item after a limit of rescans.
3. Fixed how misses are attributed and how the fleet treats an obstacle it already knows.
4. Fixed robots trapping each other at station bays and in the one-lane top aisle, which had cost every supervisor
   deliveries and dead batteries.
5. Fixed robots queued outside a full station that never gave way, which froze clusters of robots for an hour or
   more in some episodes.
6. Fixed two robots in the one-lane aisle stepping back and forth for each other for ever; robots queued behind a
   robot waiting for the person's answer raising deadlocks of their own (most of `always_ask`'s questions, which
   had cut its deliveries to a third); and robots shut in a bay by an obstacle in its entrance.
7. Fixed a robot raising the same obstacle every second when rerouting left it no way out, two robots shuffling
   around each other for minutes, and robots shut in a bay giving their order line up every 15 seconds.
8. The fleet takes back a question whose obstacle has gone; the no-headway rule no longer cuts detours short.
9. Added docking time to charging; withdrawing a question is safe with joined incidents. (For a while, charging
   first when the battery would have lasted counted as a failed line. That was reverted: the simulator lost no
   throughput by it, so it was a price on nothing.)
10. Charging first became the right action on low batteries, as the simulator's costs then said it was.
11. Lines given back before any work are counted apart from dropped ones.
12. Chargers became scarce (4 for 24 robots instead of 7), so that finishing a task first is sometimes right;
    `staged` got a rule for it.
13. Robots waiting for a charger leave the station bays they blocked and are served first come, first served.
14. Every waiting robot parks off pick faces, bay entrances and the one-lane aisle; a charger is not free while a
    robot still stands in it.
15. The low-battery label leaves a free charger to the robots already waiting for it.
16. Tests for twelve core rules that only the golden numbers protected; an obstacle counts as on the pick face only
    for a robot heading there to pick.
