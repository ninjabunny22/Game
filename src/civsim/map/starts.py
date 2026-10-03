"""Pick starting tiles: productive land, spread far apart, on a shared landmass if possible."""

import math
import random

from .biomes import BIOME_INFO, Biome
from .world import WorldMap

EDGE_MARGIN = 4
SCAN_RADIUS = 3


def find_start_positions(world: WorldMap, count: int, rng: random.Random) -> list[int]:
    def startable(i: int) -> bool:
        x, y = world.xy(i)
        return (
            world.biomes[i] in (Biome.PLAINS, Biome.FOREST)
            and EDGE_MARGIN <= x < world.width - EDGE_MARGIN
            and EDGE_MARGIN <= y < world.height - EDGE_MARGIN
        )

    candidates = [i for i in _largest_landmass(world) if startable(i)]
    if len(candidates) < count * 10:
        candidates = [i for i in range(len(world.biomes)) if startable(i)]
    if len(candidates) < count:
        candidates = [i for i, b in enumerate(world.biomes) if BIOME_INFO[b].buildable]
    if len(candidates) < count:
        raise ValueError("map has too little land for the requested number of civilizations")

    scores = {i: _site_score(world, i) for i in candidates}
    ranked = sorted(candidates, key=lambda i: (-scores[i], i))
    good = ranked[: max(count, len(ranked) // 2)]
    best_score = scores[good[0]] or 1.0

    chosen = [rng.choice(good[: max(1, len(good) // 10)])]
    while len(chosen) < count:
        def spread(i: int) -> float:
            x, y = world.xy(i)
            nearest = min(math.hypot(x - cx, y - cy) for cx, cy in map(world.xy, chosen))
            return nearest * (0.7 + 0.3 * scores[i] / best_score)

        chosen.append(max((i for i in good if i not in chosen), key=spread))
    rng.shuffle(chosen)
    return chosen


def _site_score(world: WorldMap, i: int) -> float:
    x, y = world.xy(i)
    total = 0.0
    for dy in range(-SCAN_RADIUS, SCAN_RADIUS + 1):
        for dx in range(-SCAN_RADIUS, SCAN_RADIUS + 1):
            if world.in_bounds(x + dx, y + dy):
                yields = world.yields[world.idx(x + dx, y + dy)]
                total += (
                    1.5 * yields.get("food", 0)
                    + yields.get("wood", 0)
                    + yields.get("stone", 0)
                    + 0.5 * yields.get("ore", 0)
                )
    return total


def _largest_landmass(world: WorldMap) -> list[int]:
    seen: set[int] = set()
    largest: list[int] = []
    for start in range(len(world.biomes)):
        if start in seen or world.is_water(start):
            continue
        component = [start]
        seen.add(start)
        for tile in component:
            for n in world.neighbors(tile):
                if n not in seen and not world.is_water(n):
                    seen.add(n)
                    component.append(n)
        if len(component) > len(largest):
            largest = component
    return sorted(largest)
