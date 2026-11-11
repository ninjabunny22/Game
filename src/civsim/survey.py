"""Plays whole games at full speed and counts what the rules about ships and large buildings
are meant to guarantee, so the numbers can be had again after a change:

    .venv/bin/python -m civsim.survey                       # eight seeds, 6000 ticks each
    .venv/bin/python -m civsim.survey --seeds 7 42 --ticks 3000

Per game it reports
- ships: army-ticks spent on open water and how many of those were aboard ship (all of them,
  by the crossing rule), how often an army put out and whether it did so from land near a
  working harbour, and villager-ticks on open water;
- armies with nowhere to go: army-ticks spent with no route to their goal;
- buildings: how many stand at the end and how many are larger than one tile, how many tiles
  lie under more than one building or buildings stand on a castle's ground (none, by the
  placement rule), and how much of the civs' land is built on.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor

from .config import MAP_SIZES, SimConfig, game_config
from .economy import castle_ground, footprint, ports
from .simulation import Simulation
from .strategy import make_brain

DEFAULT_SEEDS = (1, 2, 3, 7, 42, 101, 2024, 31337)


def survey(seed: int, ticks: int, brain_name: str = "utility", size: str | None = None) -> dict:
    """Play one game and return its counts: on one of the chosen maps of `size`, or with no
    size on the map the seed itself makes."""
    sim = Simulation(game_config(size, seed=seed, end_tick=0) if size else SimConfig(seed=seed))
    brain = make_brain(brain_name)
    world = sim.world
    counts = dict.fromkeys((
        "army_ticks_afloat", "army_ticks_aboard", "embarkations", "embarkations_from_port",
        "villager_ticks_afloat", "army_ticks_no_route", "wars_declared", "alliances_formed",
    ), 0)
    first_harbour = None
    was_at: dict[int, int] = {}  # army id -> tile last tick
    for _ in range(ticks):
        harbour_land = {civ.id: ports(civ, world) for civ in sim.civs}  # as it stood when armies moved
        for event in sim.step_with(brain):
            counts["wars_declared"] += "declares war" in event.get("text", "")
            counts["alliances_formed"] += "form an alliance" in event.get("text", "")
        for civ in sim.civs:
            if first_harbour is None and any(b.type == "harbour" and b.complete for b in civ.buildings):
                first_harbour = sim.tick
            counts["villager_ticks_afloat"] += sum(world.is_open_water(v.tile) for v in civ.villagers)
            for army in civ.armies:
                before = was_at.get(army.id, army.tile)
                was_at[army.id] = army.tile
                counts["army_ticks_no_route"] += army.no_route is not None
                if not world.is_open_water(army.tile):
                    continue
                counts["army_ticks_afloat"] += 1
                counts["army_ticks_aboard"] += army.boat
                if not world.is_open_water(before):
                    counts["embarkations"] += 1
                    # An army moves up to a few tiles a tick: it put out from the last land on its way.
                    counts["embarkations_from_port"] += any(
                        tile in harbour_land[civ.id] for tile in [before, *world.neighbors(army.tile)])

    # Every building stands on its own square of tiles: count the tiles under more than one
    # building, the buildings on a castle's ground, and how full the civs' land is.
    under: dict[int, int] = {}
    large = {"buildings": 0, "multi_tile": 0, "harbour": 0, "stables": 0, "overlapping_tiles": 0,
             "on_castle_ground": 0, "land_tiles": 0, "built_tiles": 0}
    for civ in sim.civs:
        large["land_tiles"] += len(civ.territory)
        for building in civ.buildings:
            ground = footprint(world, building.type, building.tile)
            large["buildings"] += 1
            large["multi_tile"] += len(ground) > 1
            if building.type in large:
                large[building.type] += 1
            large["on_castle_ground"] += any(castle_ground(world, tile) for tile in ground)
            for tile in ground:
                under[tile] = under.get(tile, 0) + 1
    large["built_tiles"] = len(under)
    large["overlapping_tiles"] = sum(1 for count in under.values() if count > 1)
    return {"seed": seed, "ticks": ticks, "first_harbour_tick": first_harbour, **counts, "large": large,
            "alive": sum(civ.alive for civ in sim.civs), "population": round(sum(c.population for c in sim.civs))}


def report(results: list[dict]) -> str:
    lines = ["seed    harbour@  afloat  aboard  put-out  from-port  villagers-afloat  no-route  wars  alliances  alive  population"]
    for r in results:
        lines.append(f"{r['seed']:<7d} {r['first_harbour_tick'] or '-':>8}  {r['army_ticks_afloat']:6d}  "
                     f"{r['army_ticks_aboard']:6d}  {r['embarkations']:7d}  {r['embarkations_from_port']:9d}  "
                     f"{r['villager_ticks_afloat']:16d}  {r['army_ticks_no_route']:8d}  {r['wars_declared']:4d}  "
                     f"{r['alliances_formed']:9d}  {r['alive']:5d}  {r['population']:10d}")
    total = {key: sum(r[key] for r in results) for key in
             ("army_ticks_afloat", "army_ticks_aboard", "embarkations", "embarkations_from_port")}
    with_ships = sum(1 for r in results if r["army_ticks_aboard"])
    lines += ["", f"games with a ship seen: {with_ships} of {len(results)}",
              f"army-ticks on open water: {total['army_ticks_afloat']}, aboard ship: {total['army_ticks_aboard']}",
              f"times an army put out: {total['embarkations']}, from land near a working harbour: "
              f"{total['embarkations_from_port']}", "",
              "seed    buildings  multi-tile  harbours  stables  overlapping-tiles  on-castle-ground  land-built"]
    for r in results:
        large = r["large"]
        share = 100 * large["built_tiles"] / max(1, large["land_tiles"])
        lines.append(f"{r['seed']:<7d} {large['buildings']:9d}  {large['multi_tile']:10d}  {large['harbour']:8d}  "
                     f"{large['stables']:7d}  {large['overlapping_tiles']:17d}  {large['on_castle_ground']:16d}  "
                     f"{share:9.0f}%")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim.survey", description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--ticks", type=int, default=6000, help="ticks per game")
    parser.add_argument("--brain", default="utility", help='who plays the civs: "utility" (default) or "rules"')
    parser.add_argument("--size", choices=list(MAP_SIZES), help="play on the chosen maps of this size "
                        "(the seed picks which, and where the civs start) instead of one made from the seed")
    args = parser.parse_args(argv)
    n = len(args.seeds)
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(survey, args.seeds, [args.ticks] * n, [args.brain] * n, [args.size] * n))
    print(report(results))


if __name__ == "__main__":
    main()
