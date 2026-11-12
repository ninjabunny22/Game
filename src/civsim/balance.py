"""Gameplay balance of the drawn maps: many games per map and number of civs, reported per start
slot. Geography alone is civsim.fairness; this is what happens when the civs play.

    .venv/bin/python -m civsim.balance gilded_isle --civs 4 --games 20 [--jobs 8]

The seed varies from game to game, so each slot is played by different civs and personalities.
Per slot: wins (with a 90% interval), regions on days 1,000 and 3,000 and at the end, first
war, eliminations, and which slot took each prize (a region drawn as a prize or a stronghold)
first and when. Games run to a victory or the last day.
"""

import argparse
import math
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from .config import MAPS, game_config

SNAPSHOTS = (1000, 3000)


def _size_of(map_id: str) -> str:
    return next(size for size, pool in MAPS.items() if any(m["id"] == map_id for m in pool))


def play(map_id: str, civs: int, seed: int) -> dict:
    from .simulation import Simulation
    from .strategy import make_brain
    sim = Simulation(game_config(_size_of(map_id), civs, seed=seed, map=map_id))
    brain, world = make_brain("utility"), sim.world
    slot_of = {}
    for civ in sim.civs:
        home = world.region_of[civ.capital.tile]
        slot_of[civ.id] = next(s for s, (h, _) in world.starts.items() if h == home)
    prizes = {r.id: None for r in world.regions if "prize" in r.tags or r.strength > 1}
    held = lambda: {slot_of[c.id]: sum(1 for r in world.regions if r.owner == c.id) for c in sim.civs}  # noqa: E731
    first_war, snaps = None, {}
    while not sim.victory and sim.tick <= sim.config.end_tick:
        for event in sim.step_with(brain):
            if first_war is None and "declares war" in event.get("text", ""):
                first_war = sim.tick
        for r in prizes:
            if prizes[r] is None and world.regions[r].owner is not None:
                prizes[r] = (slot_of[world.regions[r].owner], sim.tick)
        if sim.tick in SNAPSHOTS:
            snaps[sim.tick] = held()
    victory = sim.victory or {}
    return {"seed": seed, "winner": slot_of.get(victory.get("civ")), "kind": victory.get("kind"),
            "day": victory.get("tick", sim.tick), "first_war": first_war, "snaps": snaps, "end": held(),
            "dead": [slot_of[c.id] for c in sim.civs if not c.alive],
            "prizes": {world.regions[r].name: p for r, p in prizes.items()}}


def interval(wins: int, n: int, z: float = 1.645) -> tuple[float, float]:
    """Wilson 90% interval for a win rate."""
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def summarise(map_id: str, civs: int, games: list[dict]) -> list[str]:
    n = len(games)
    expected = 1 / civs
    slots = sorted({s for g in games for s in g["end"]})
    lines = [f"{map_id}, {civs} civs, {n} games: "
             + ", ".join(f"{k} {sum(1 for g in games if g['kind'] == k)}" for k in ("conquest", "domination", "score"))
             + f", undecided {sum(1 for g in games if g['kind'] is None)}; median end day "
             + str(sorted(g["day"] for g in games)[n // 2])
             + f"; first war median day {sorted(g['first_war'] or 10**9 for g in games)[n // 2]}"]
    lines.append(f"  {'slot':<12}{'wins':>6}{'90% interval':>16}{'d1000':>7}{'d3000':>7}{'end':>6}{'fallen':>8}  flag")
    for slot in slots:
        wins = sum(1 for g in games if g["winner"] == slot)
        lo, hi = interval(wins, n)
        mean = lambda key: sum(g["snaps"].get(key, {}).get(slot, 0) for g in games) / n  # noqa: E731
        end = sum(g["end"].get(slot, 0) for g in games) / n
        fallen = sum(1 for g in games if slot in g["dead"])
        flag = ""
        if abs(wins / n - expected) > 0.15 and not lo <= expected <= hi:
            flag = "win rate"
        if fallen / n > 0.4:
            flag = (flag + ", " if flag else "") + "often falls"
        lines.append(f"  {slot:<12}{wins:>6}{f'{lo:.0%}-{hi:.0%}':>16}{mean(1000):>7.1f}{mean(3000):>7.1f}{end:>6.1f}"
                     f"{fallen:>8}  {flag}")
    taken = defaultdict(list)
    for g in games:
        for name, got in g["prizes"].items():
            if got:
                taken[name].append(got)
    for name in sorted({name for g in games for name in g["prizes"]}):
        got = taken[name]
        by = defaultdict(int)
        for slot, _ in got:
            by[slot] += 1
        days = sorted(day for _, day in got)
        lines.append(f"  prize {name}: taken in {len(got)}/{n} games"
                     + (f", median day {days[len(days) // 2]}, first by " + ", ".join(f"{s} {c}" for s, c in sorted(by.items()))
                        if got else ""))
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim.balance")
    parser.add_argument("map")
    parser.add_argument("--civs", type=int, required=True)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    seeds = range(args.first_seed, args.first_seed + args.games)
    with ProcessPoolExecutor(args.jobs) as pool:
        games = list(pool.map(play, [args.map] * args.games, [args.civs] * args.games, seeds))
    print("\n".join(summarise(args.map, args.civs, games)))


if __name__ == "__main__":
    main()
