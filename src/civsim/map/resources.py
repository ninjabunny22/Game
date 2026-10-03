"""Resource deposits: bonus yields placed in clusters on suitable biomes."""

import random
from dataclasses import dataclass

from .biomes import BIOME_INFO, Biome
from .world import WorldMap


@dataclass(frozen=True)
class DepositType:
    name: str
    color: str
    biomes: tuple[Biome, ...]
    bonus: dict[str, int]
    clusters: int  # cluster count on a 96x96 map; scaled by map area
    size: tuple[int, int]  # min/max tiles per cluster
    spacing: int  # min distance between cluster centres of this type


DEPOSIT_TYPES: dict[str, DepositType] = {
    "fertile_soil": DepositType("Fertile Soil", "#d7e84a", (Biome.PLAINS,), {"food": 2}, 12, (4, 9), 9),
    "fish": DepositType("Fish", "#9fe3f0", (Biome.SHALLOWS,), {"food": 2}, 10, (3, 6), 8),
    "game": DepositType("Game", "#b5763a", (Biome.FOREST,), {"food": 1}, 8, (3, 6), 9),
    "stone": DepositType("Stone", "#e3e3e3", (Biome.HILLS,), {"stone": 2}, 8, (3, 6), 9),
    "iron": DepositType("Iron", "#b0492f", (Biome.HILLS, Biome.MOUNTAIN), {"ore": 3}, 9, (2, 5), 10),
    "gold": DepositType("Gold", "#ffd21f", (Biome.MOUNTAIN, Biome.HILLS, Biome.DESERT), {"gold": 2}, 6, (2, 4), 12),
}


def place_deposits(world: WorldMap, rng: random.Random) -> None:
    """Seed cluster centres on eligible biomes, then grow each into a contiguous vein."""
    area_scale = (world.width * world.height) / (96 * 96)
    for type_id, dtype in DEPOSIT_TYPES.items():
        eligible = [i for i, b in enumerate(world.biomes) if b in dtype.biomes and i not in world.deposits]
        if not eligible:
            continue
        centres: list[int] = []
        for _ in range(max(1, round(dtype.clusters * area_scale))):
            centre = _pick_centre(world, rng, eligible, centres, dtype.spacing)
            if centre is None:
                break
            centres.append(centre)
            _grow_cluster(world, rng, centre, type_id, dtype, rng.randint(*dtype.size))


def compute_yields(world: WorldMap) -> None:
    for i, biome in enumerate(world.biomes):
        yields = dict(BIOME_INFO[biome].yields)
        deposit = world.deposits.get(i)
        if deposit:
            for res, amount in DEPOSIT_TYPES[deposit].bonus.items():
                yields[res] = yields.get(res, 0) + amount
        world.yields[i] = yields


def _pick_centre(world, rng, eligible, centres, spacing) -> int | None:
    for _ in range(40):
        i = rng.choice(eligible)
        if i in world.deposits:
            continue
        x, y = world.xy(i)
        if all(abs(x - cx) + abs(y - cy) >= spacing for cx, cy in map(world.xy, centres)):
            return i
    return None


def _grow_cluster(world, rng, centre, type_id, dtype, size) -> None:
    world.deposits[centre] = type_id
    frontier = [centre]
    placed = 1
    while placed < size and frontier:
        tile = rng.choice(frontier)
        options = [
            n for n in world.neighbors(tile, diagonal=True)
            if n not in world.deposits and world.biomes[n] in dtype.biomes
        ]
        if not options:
            frontier.remove(tile)
            continue
        new = rng.choice(options)
        world.deposits[new] = type_id
        frontier.append(new)
        placed += 1
