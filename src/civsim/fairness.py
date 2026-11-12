"""How fair a drawn map's starts are, by geography alone (no game played): for each number of
civs and each slot it uses, what the slot starts with and what lies open to it.

    .venv/bin/python -m civsim.fairness [map ...]

Per slot:
- land, points: land tiles and region points of its two starting regions;
- riches: their yields (food, wood, stone, ore, gold; mines counted as gold) against an
  average region's;
- room: the neutral regions nearer it than any other slot (route length over the region
  graph, a sea crossing counted three times), and their points;
- rival: route length to the nearest other slot's home region;
- prize: route length to the nearest region drawn as a prize;
- ways in: walkable borders of its two regions with any region not its own.

A figure more than TOLERANCE from the average of the slots in the same game is marked "!".
Gameplay balance is a separate question, for played games (civsim.balance).
"""

import argparse
import math

from .map.designs import DESIGNS
from .map.saved import load_map
from .strategy.geography import RESOURCES, SEA_DETOUR, Geography

TOLERANCE = 0.15


def slot_figures(world, geo: Geography, slots: list[str]) -> dict[str, dict]:
    homes = {s: world.starts[s] for s in slots}
    taken = {r for pair in homes.values() for r in pair}
    dist = {s: geo._dijkstra(set(pair), lambda a, b, sea: True, SEA_DETOUR)[0] for s, pair in homes.items()}
    prizes = [r.id for r in world.regions if "prize" in r.tags]
    room = {s: [] for s in slots}
    for region in world.regions:
        if region.id in taken:
            continue
        ranked = sorted(slots, key=lambda s: (dist[s].get(region.id, math.inf), s))
        best = ranked[0]
        if len(ranked) > 1 and dist[ranked[1]].get(region.id, math.inf) - dist[best].get(region.id, math.inf) < 1.5:
            continue  # about equally near two: nobody's
        room[best].append(region.id)
    figures = {}
    for s, pair in homes.items():
        riches = sum(min(3.0, geo.potential[r][res] / geo.mean[res]) for r in pair for res in RESOURCES)
        riches += sum(geo.mines[r] for r in pair)
        others = [o for o in slots if o != s]
        figures[s] = {
            "land": sum(sum(1 for t in world.regions[r].tiles if not world.is_water(t)) for r in pair),
            "points": sum(world.regions[r].points for r in pair),
            "riches": round(riches, 1),
            "room": len(room[s]),
            "room_points": sum(world.regions[r].points for r in room[s]),
            "rival": round(min(dist[s].get(r, math.inf) for o in others for r in homes[o]), 0) if others else 0,
            "prize": round(min((dist[s].get(r, math.inf) for r in prizes), default=0), 0),
            "ways_in": sum(1 for r in pair for b, (_, sea) in geo.neighbours[r].items() if not sea and b not in pair),
        }
    return figures


def report(map_id: str) -> list[str]:
    world = load_map(map_id)
    geo = Geography(world, [], None)
    lines = [f"{map_id}"]
    for count, options in sorted(world.start_sets.items()):
        for slots in options:
            figures = slot_figures(world, geo, slots)
            keys = list(next(iter(figures.values())))
            mean = {k: sum(f[k] for f in figures.values()) / len(figures) for k in keys}
            lines.append(f"  {count} civs   " + "  ".join(f"{k:>11}" for k in keys))
            for slot, f in figures.items():
                cells = []
                for k in keys:
                    off = mean[k] and abs(f[k] - mean[k]) / mean[k] > TOLERANCE
                    cells.append(f"{f[k]:>10}{'!' if off else ' '}")
                lines.append(f"    {slot:<6} " + " ".join(cells))
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim.fairness")
    parser.add_argument("maps", nargs="*")
    args = parser.parse_args(argv)
    for map_id in args.maps or DESIGNS:
        print("\n".join(report(map_id)))


if __name__ == "__main__":
    main()
