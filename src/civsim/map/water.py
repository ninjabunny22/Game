"""Fresh water: lakes and rivers, placed from the map seed."""

import random

from .biomes import Biome
from .world import WorldMap

LAKES = 6  # typical count on a 96x96 map; the seed varies it
MAX_LAKE_TILES = 14  # hard cap, so no lake can dominate the map
MIN_LAKE_TILES = 3
LAKE_SPACING = 7

RIVERS = 8  # typical count on a 96x96 map; the seed varies it
MAX_RIVER_LENGTH = 70
MIN_RIVER_LENGTH = 4
RIVER_SOURCE_SPACING = 7
TILES_PER_SIZE_STEP = 10  # a river widens by one size every this many tiles from its source
MAX_RIVER_SIZE = 3

_LAKE_BED = (Biome.PLAINS, Biome.FOREST, Biome.TUNDRA, Biome.DESERT, Biome.HILLS)
_SEA = (Biome.OCEAN, Biome.SHALLOWS)


def add_lakes(world: WorldMap, rng: random.Random) -> None:
    """Inland lakes: seed a centre away from the sea, then grow it to a random size up to the cap."""
    def inland(i: int) -> bool:
        # Clear of the sea, and of lakes placed earlier, so two lakes never merge past the size cap.
        return world.biomes[i] in _LAKE_BED and not any(
            world.biomes[n] in _SEA or world.biomes[n] == Biome.LAKE for n in world.neighbors(i, diagonal=True))

    def well_inland(i: int) -> bool:
        return inland(i) and all(inland(n) for n in world.neighbors(i, diagonal=True))

    candidates = [i for i in range(len(world.biomes)) if well_inland(i)]
    centres: list[int] = []
    for _ in range(_count(world, rng, LAKES)):
        centre = _spaced_pick(world, rng, candidates, centres, LAKE_SPACING)
        if centre is None:
            break
        centres.append(centre)
        lake = [centre]
        frontier = [centre]
        size = rng.randint(MIN_LAKE_TILES, MAX_LAKE_TILES)
        while len(lake) < size and frontier:
            tile = rng.choice(frontier)
            options = [n for n in world.neighbors(tile) if n not in lake and inland(n)]
            if not options:
                frontier.remove(tile)
                continue
            new = rng.choice(options)
            lake.append(new)
            frontier.append(new)
        level = min(world.heights[t] for t in lake)  # a lake surface is flat
        for tile in lake:
            world.biomes[tile] = Biome.LAKE
            world.heights[tile] = level


def add_rivers(world: WorldMap, rng: random.Random) -> None:
    """Rivers rise in the high ground and run downhill until they reach the sea, a lake or another river.

    Length falls out of the terrain, so it differs from river to river and seed
    to seed; a river grows in size the further it is from its source.
    """
    highland = [i for i, b in enumerate(world.biomes) if b in (Biome.MOUNTAIN, Biome.HILLS)]
    sources: list[int] = []
    for _ in range(_count(world, rng, RIVERS)):
        source = _spaced_pick(world, rng, highland, sources, RIVER_SOURCE_SPACING)
        if source is None:
            break
        sources.append(source)
        path: list[int] = []
        visited = {source}
        tile = source
        arrived = False
        while len(path) < MAX_RIVER_LENGTH:
            if world.is_water(tile) or tile in world.rivers:
                arrived = True
                break
            path.append(tile)
            options = [n for n in world.neighbors(tile) if n not in visited]
            if not options:
                break
            # Steepest way down, with a little noise so rivers meander across flat ground.
            tile = min(options, key=lambda n: world.heights[n] + 0.01 * rng.random())
            visited.add(tile)
        if arrived and len(path) >= MIN_RIVER_LENGTH:
            for distance, river_tile in enumerate(path):
                size = min(MAX_RIVER_SIZE, 1 + distance // TILES_PER_SIZE_STEP)
                world.rivers[river_tile] = max(world.rivers.get(river_tile, 0), size)


def _count(world: WorldMap, rng: random.Random, typical: int) -> int:
    area_scale = (world.width * world.height) / (96 * 96)
    return max(1, round(typical * area_scale * rng.uniform(0.6, 1.4)))


def _spaced_pick(world: WorldMap, rng: random.Random, candidates: list[int], taken: list[int],
                 spacing: int) -> int | None:
    if not candidates:
        return None
    for _ in range(40):
        tile = rng.choice(candidates)
        x, y = world.xy(tile)
        if all(abs(x - tx) + abs(y - ty) >= spacing for tx, ty in map(world.xy, taken)):
            return tile
    return None
