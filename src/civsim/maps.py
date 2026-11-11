"""Finds good maps. The game is played on a small set of chosen maps rather than a new random
one each time (see config.MAPS); this is the tool that chose them, kept so more can be found:

    .venv/bin/python -m civsim.maps --size medium --seeds 300      # score seeds 1..300
    .venv/bin/python -m civsim.maps --size large --seeds 300 --play 8   # and play the best 8

A map is scored on what makes a game on it good: a sensible share of land, most of it one
landmass so the civs can get at each other, regions of similar size and enough of them, water
and deposits spread through the regions, and a mix of terrain without too much waste.
`--play` then plays short games on the best and reports how the civs fared.
"""

import argparse
import math
from concurrent.futures import ProcessPoolExecutor

from .config import MAP_SIZES, SimConfig
from .map import Biome, generate_map

WEIGHTS = {"land": 1.0, "mainland": 2.0, "fairness": 1.5, "water": 1.5, "deposits": 1.0, "variety": 1.0, "waste": 1.0}


def measure(seed: int, side: int, max_civs: int) -> dict:
    world = generate_map(seed, side, side)
    size = side * side
    land = [t for t in range(size) if not world.is_water(t)]
    walkable = [t for t in range(size) if not world.is_open_water(t)]
    # The largest stretch an army can walk without ships.
    seen: set[int] = set()
    largest = 0
    for start in walkable:
        if start in seen:
            continue
        seen.add(start)
        stack, count = [start], 0
        while stack:
            tile = stack.pop()
            count += 1
            for n in world.neighbors(tile):
                if n not in seen and not world.is_open_water(n):
                    seen.add(n)
                    stack.append(n)
        largest = max(largest, count)
    sizes = [sum(1 for t in region.tiles if not world.is_water(t)) for region in world.regions]
    wet = dry_deposit = 0
    for region in world.regions:
        tiles = set(region.tiles)
        wet += any(t in world.rivers or any(world.biomes[n] == Biome.LAKE for n in world.neighbors(t)) for t in tiles)
        dry_deposit += any(t in world.deposits for t in tiles)
    counts: dict[Biome, int] = {}
    for tile in land:
        counts[world.biomes[tile]] = counts.get(world.biomes[tile], 0) + 1
    shares = [c / max(1, len(land)) for c in counts.values()]
    entropy = -sum(s * math.log(s) for s in shares if s > 0) / math.log(6)
    waste = (counts.get(Biome.DESERT, 0) + counts.get(Biome.TUNDRA, 0) + counts.get(Biome.MOUNTAIN, 0)) / max(1, len(land))
    share = len(land) / size
    parts = {
        "land": max(0.0, 1 - abs(share - 0.5) / 0.25),
        "mainland": largest / max(1, len(walkable)),
        "fairness": min(sizes) / max(1, max(sizes)) if sizes else 0.0,
        "water": wet / max(1, len(world.regions)),
        "deposits": dry_deposit / max(1, len(world.regions)),
        "variety": min(1.0, entropy),
        "waste": max(0.0, 1 - waste / 0.4),
    }
    score = sum(WEIGHTS[k] * v for k, v in parts.items()) / sum(WEIGHTS.values())
    if len(world.regions) < 2 * max_civs + 2:
        score *= 0.5  # too few regions for every civ to start with two and still have room
    return {"seed": seed, "score": round(score, 3), "land_share": round(share, 2), "regions": len(world.regions),
            **{k: round(v, 2) for k, v in parts.items()}}


def play(seed: int, size: str, ticks: int) -> dict:
    """Two short games on the map with different starts: how evenly the civs did, and whether they met."""
    from .simulation import Simulation
    from .strategy import make_brain
    spec = MAP_SIZES[size]
    spread, wars, alive, harbours = [], 0, 0, 0
    for game in (11, 23):
        sim = Simulation(SimConfig(seed=game, map_seed=seed, width=spec["side"], height=spec["side"],
                                   num_civs=spec["civs"], end_tick=0))
        brain = make_brain("utility")
        for _ in range(ticks):
            for event in sim.step_with(brain):
                wars += "declares war" in event.get("text", "")
        people = [civ.population for civ in sim.civs]
        spread.append(min(people) / max(1.0, max(people)))
        alive += sum(civ.alive for civ in sim.civs)
        harbours += sum(1 for civ in sim.civs for b in civ.buildings if b.type == "harbour")
    return {"seed": seed, "evenness": round(sum(spread) / len(spread), 2), "wars": wars,
            "alive": alive, "of": 2 * spec["civs"], "harbours": harbours}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim.maps", description=__doc__.split("\n\n")[0])
    parser.add_argument("--size", choices=list(MAP_SIZES), default="medium")
    parser.add_argument("--seeds", type=int, default=200, help="score seeds 1..N")
    parser.add_argument("--play", type=int, default=0, help="play short games on the best N")
    parser.add_argument("--ticks", type=int, default=2500)
    args = parser.parse_args(argv)
    spec = MAP_SIZES[args.size]
    seeds = range(1, args.seeds + 1)
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(measure, seeds, [spec["side"]] * len(seeds), [spec["max_civs"]] * len(seeds), chunksize=4))
        rows.sort(key=lambda r: -r["score"])
        best = rows[:max(12, args.play)]
        keys = list(best[0])
        print("  ".join(f"{k:>9}" for k in keys))
        for row in best:
            print("  ".join(f"{row[k]:>9}" for k in keys))
        if args.play:
            print()
            top = [r["seed"] for r in rows[:args.play]]
            for result in pool.map(play, top, [args.size] * len(top), [args.ticks] * len(top)):
                print(result)


if __name__ == "__main__":
    main()
