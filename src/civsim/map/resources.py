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


RIVERSIDE_FARMLAND = (Biome.PLAINS, Biome.FOREST, Biome.DESERT)  # a river makes these more fertile


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
            if type_id == "gold":
                world.mines.append(centre)  # no dice thrown: the map is the same as before


RICH_YIELD = 3  # a rich node's tiles yield this many times their deposit's bonus
RICH_SHARE = 1 / 3  # about this share of the regions that start neutral hold a rich node
RICH_REACH = 2  # tiles of the same deposit within this many steps of the centre belong to the node
RICH_NAMES = {
    "iron": ["the Great Iron Vein", "the Deep Iron Vein", "the Red Iron Hills"],
    "gold": ["the Golden Seam", "the King's Gold", "the Sunlit Seam"],
    "stone": ["the White Quarries", "the Marble Shelf", "the Giant's Steps"],
    "fertile_soil": ["the Black Earth", "the Golden Fields", "the Garden of Plenty"],
    "fish": ["the Silver Shoals", "the Teeming Banks", "the Herring Run"],
    "game": ["the Royal Forest", "the Great Hunt", "the Stag Woods"],
}


RICH_WORTH = {"gold": 2.0, "iron": 1.6, "stone": 1.2, "fertile_soil": 1.0, "fish": 0.9, "game": 0.8}


def choose_rich_nodes(world: WorldMap, start_regions: set[int], rng) -> None:
    """Rich nodes in about RICH_SHARE of the regions that are not a start region (at least
    one a map). In each, the best of its deposits (the most tiles near one spot, weighted by
    how scarce the resource is, and against kinds already chosen, for variety), at the tile
    nearest that spot, with the deposit's tiles within RICH_REACH. Start regions never get
    one, so starts stay fair."""
    world.rich, world.rich_tiles = {}, set()
    candidates = [r for r in world.regions if r.id not in start_regions and any(t in world.deposits for t in r.tiles)]
    rng.shuffle(candidates)
    used: dict[str, int] = {}
    for region in candidates[:max(1, round(RICH_SHARE * len(candidates)))]:
        best = None
        for kind in sorted({world.deposits[t] for t in region.tiles if t in world.deposits}):
            tiles = [t for t in region.tiles if world.deposits.get(t) == kind]
            mx = sum(world.xy(t)[0] for t in tiles) / len(tiles)
            my = sum(world.xy(t)[1] for t in tiles) / len(tiles)
            centre = min(tiles, key=lambda t: ((world.xy(t)[0] - mx) ** 2 + (world.xy(t)[1] - my) ** 2, t))
            cx, cy = world.xy(centre)
            node = [t for t in tiles if max(abs(world.xy(t)[0] - cx), abs(world.xy(t)[1] - cy)) <= RICH_REACH]
            bonus = sum(DEPOSIT_TYPES[kind].bonus.values())
            score = len(node) * bonus * RICH_WORTH.get(kind, 1.0) * 0.5 ** used.get(kind, 0)
            if best is None or score > best[0]:
                best = (score, kind, centre, node)
        _, kind, centre, node = best
        names = RICH_NAMES[kind]
        world.rich[centre] = names[used.get(kind, 0) % len(names)]
        used[kind] = used.get(kind, 0) + 1
        world.rich_tiles |= set(node)


def compute_yields(world: WorldMap) -> None:
    for i, biome in enumerate(world.biomes):
        yields = dict(BIOME_INFO[biome].yields)
        deposit = world.deposits.get(i)
        if deposit:
            rich = RICH_YIELD if i in world.rich_tiles else 1
            for res, amount in DEPOSIT_TYPES[deposit].bonus.items():
                yields[res] = yields.get(res, 0) + rich * amount
        if i in world.rivers and biome in RIVERSIDE_FARMLAND:
            yields["food"] = yields.get("food", 0) + 1
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
