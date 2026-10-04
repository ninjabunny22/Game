"""Plays whole games at full speed and counts what the rules about ships and large buildings
are meant to guarantee, so the numbers can be had again after a change:

    .venv/bin/python -m civsim.survey                       # eight seeds, 6000 ticks each
    .venv/bin/python -m civsim.survey --seeds 7 42 --ticks 3000

Per game it reports
- ships: army-ticks spent on open water and how many of those were aboard ship (all of them,
  by the crossing rule), how often an army put out and whether it did so from land near a
  working harbour, and villager-ticks on open water;
- armies with nowhere to go: army-ticks spent with no route to their goal;
- large buildings (harbour, stables): how many stand at the end, how many share their tile or
  stand on a capital's tile (none, by the placement rule), and how many have another building
  or a capital on one of the eight tiles around them, which their models overhang.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor

from .config import SimConfig
from .economy import EXCLUSIVE, ports
from .simulation import Simulation
from .strategy import make_brain

DEFAULT_SEEDS = (1, 2, 3, 7, 42, 101, 2024, 31337)


def survey(seed: int, ticks: int) -> dict:
    """Play one game with the built-in rules brain and return its counts."""
    sim = Simulation(SimConfig(seed=seed))
    brain = make_brain("rules")
    world = sim.world
    counts = dict.fromkeys((
        "army_ticks_afloat", "army_ticks_aboard", "embarkations", "embarkations_from_port",
        "villager_ticks_afloat", "army_ticks_no_route",
    ), 0)
    first_harbour = None
    was_at: dict[int, int] = {}  # army id -> tile last tick
    for _ in range(ticks):
        harbour_land = {civ.id: ports(civ, world) for civ in sim.civs}  # as it stood when armies moved
        sim.step_with(brain)
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

    capitals = set(world.capital_tiles) | {s.tile for civ in sim.civs for s in civ.settlements}
    built = {tile for civ in sim.civs for tile in civ.buildings_by_tile()}
    large = {"harbour": 0, "stables": 0, "sharing_tile": 0, "on_capital": 0,
             "building_alongside": 0, "capital_alongside": 0}
    for civ in sim.civs:
        on_tile = civ.buildings_by_tile()
        for building in civ.buildings:
            if building.type not in EXCLUSIVE:
                continue
            large[building.type] += 1
            large["sharing_tile"] += len(on_tile[building.tile]) > 1
            large["on_capital"] += building.tile in capitals
            around = set(world.neighbors(building.tile, diagonal=True))
            large["building_alongside"] += bool(around & built)
            large["capital_alongside"] += bool(around & capitals)
    return {"seed": seed, "ticks": ticks, "first_harbour_tick": first_harbour, **counts, "large": large}


def report(results: list[dict]) -> str:
    lines = ["seed    harbour@  afloat  aboard  put-out  from-port  villagers-afloat  no-route"]
    for r in results:
        lines.append(f"{r['seed']:<7d} {r['first_harbour_tick'] or '-':>8}  {r['army_ticks_afloat']:6d}  "
                     f"{r['army_ticks_aboard']:6d}  {r['embarkations']:7d}  {r['embarkations_from_port']:9d}  "
                     f"{r['villager_ticks_afloat']:16d}  {r['army_ticks_no_route']:8d}")
    total = {key: sum(r[key] for r in results) for key in
             ("army_ticks_afloat", "army_ticks_aboard", "embarkations", "embarkations_from_port")}
    with_ships = sum(1 for r in results if r["army_ticks_aboard"])
    lines += ["", f"games with a ship seen: {with_ships} of {len(results)}",
              f"army-ticks on open water: {total['army_ticks_afloat']}, aboard ship: {total['army_ticks_aboard']}",
              f"times an army put out: {total['embarkations']}, from land near a working harbour: "
              f"{total['embarkations_from_port']}", "",
              "seed    harbours  stables  sharing-tile  on-capital  building-alongside  capital-alongside"]
    for r in results:
        large = r["large"]
        lines.append(f"{r['seed']:<7d} {large['harbour']:8d}  {large['stables']:7d}  {large['sharing_tile']:12d}  "
                     f"{large['on_capital']:10d}  {large['building_alongside']:18d}  {large['capital_alongside']:17d}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim.survey", description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--ticks", type=int, default=6000, help="ticks per game")
    args = parser.parse_args(argv)
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(survey, args.seeds, [args.ticks] * len(args.seeds)))
    print(report(results))


if __name__ == "__main__":
    main()
