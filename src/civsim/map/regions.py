"""Regions: the map's land divided into fair-sized territories, each with a capital.

Whoever holds a region's capital holds the region. Regions no civ holds belong
to the native faction, which only defends its capitals.
"""

import random
from collections import deque
from dataclasses import dataclass

from ..datafiles import load_json
from .biomes import BIOME_INFO, Biome
from .world import WorldMap

REGION_COUNT = 16  # for a 96x96 map; scaled by map area
MIN_SHARE = 0.6  # no region smaller than this share of the average size ...
MAX_SHARE = 1.5  # ... or larger than this
CAPITAL_INSET = 2  # a capital sits at least this many tiles inside its region's border
ATTEMPTS = 12


@dataclass
class Region:
    id: int
    name: str
    capital_name: str
    capital: int  # tile
    tiles: list[int]  # every tile that can be owned: the region's land and coastal shallows
    owner: int | None = None  # civ id, or None while the native faction holds it
    garrison: float = 0.0  # native defenders at the capital, in soldier-equivalents
    under_attack: int = -1  # last tick an army fought the garrison

    @property
    def neutral(self) -> bool:
        return self.owner is None


def load_faction() -> dict:
    return load_json("regions.json")["faction"]


def generate_regions(world: WorldMap, rng: random.Random, count: int | None = None) -> None:
    """Split the land into regions of similar size, give each a capital and a name."""
    land = [i for i in range(len(world.biomes)) if not world.is_water(i)]
    if count is None:
        count = max(4, round(REGION_COUNT * world.width * world.height / (96 * 96)))
    count = min(count, max(1, len(land) // 12))

    best, best_fairness = None, -1.0
    for _ in range(ATTEMPTS):
        assignment = _grow(world, rng, land, count)
        _balance(world, assignment, count)
        sizes = _sizes(assignment, count)
        mean = sum(sizes) / count
        fairness = min(min(sizes) / mean, MAX_SHARE * mean / max(sizes) - 0.0)
        if fairness > best_fairness:
            best, best_fairness = assignment, fairness
        if min(sizes) >= MIN_SHARE * mean and max(sizes) <= MAX_SHARE * mean:
            best = assignment
            break

    # Coastal shallows and lakes belong to the region of the nearest land.
    region_of = [-1] * len(world.biomes)
    for tile, region in best.items():
        region_of[tile] = region
    queue = deque(sorted(best))
    while queue:
        tile = queue.popleft()
        for n in world.neighbors(tile):
            if region_of[n] < 0 and world.biomes[n] in (Biome.SHALLOWS, Biome.LAKE):
                region_of[n] = region_of[tile]
                queue.append(n)

    names = load_json("regions.json")
    region_names = rng.sample(names["regions"], count) if count <= len(names["regions"]) else [
        f"Region {i + 1}" for i in range(count)]
    capital_names = rng.sample(names["capitals"], count) if count <= len(names["capitals"]) else [
        f"Capital {i + 1}" for i in range(count)]

    world.region_of = region_of
    world.regions = []
    for region_id in range(count):
        tiles = [t for t, r in enumerate(region_of) if r == region_id and world.biomes[t] != Biome.LAKE]
        capital = _place_capital(world, rng, region_id, region_of)
        world.regions.append(Region(region_id, region_names[region_id], capital_names[region_id], capital, tiles))
    world.capital_tiles = {region.capital: region.id for region in world.regions}


def region_neighbours(world: WorldMap) -> dict[int, set[int]]:
    """Which regions touch which."""
    touching: dict[int, set[int]] = {region.id: set() for region in world.regions}
    for tile, region in enumerate(world.region_of):
        if region < 0:
            continue
        for n in world.neighbors(tile):
            other = world.region_of[n]
            if other >= 0 and other != region:
                touching[region].add(other)
    return touching


# -- generation ----------------------------------------------------------------

def _grow(world: WorldMap, rng: random.Random, land: list[int], count: int) -> dict[int, int]:
    """Seed regions across the landmasses in proportion to their size, then grow them evenly."""
    masses = _landmasses(world, land)
    quotas = _quotas([len(m) for m in masses], count)
    assignment: dict[int, int] = {}
    frontiers: list[deque[int]] = []
    sizes: list[int] = []
    for mass, quota in zip(masses, quotas):
        for seed in _spread(world, rng, mass, quota):
            assignment[seed] = len(sizes)
            frontiers.append(deque([seed]))
            sizes.append(1)

    # Always let the smallest region that can still grow take the next step.
    active = set(range(len(sizes)))
    while active:
        region = min(active, key=lambda r: (sizes[r], r))
        frontier = frontiers[region]
        if not frontier:
            active.discard(region)
            continue
        tile = frontier.popleft()
        for n in world.neighbors(tile):
            if n not in assignment and not world.is_water(n):
                assignment[n] = region
                sizes[region] += 1
                frontier.append(n)

    # Small islands that got no seed join whichever region is nearest across the water.
    queue = deque(sorted(assignment))
    reached = dict(assignment)
    while queue:
        tile = queue.popleft()
        for n in world.neighbors(tile):
            if n not in reached:
                reached[n] = reached[tile]
                queue.append(n)
    for tile in land:
        assignment.setdefault(tile, reached[tile])
    return assignment


def _balance(world: WorldMap, assignment: dict[int, int], count: int) -> None:
    """Hemmed-in regions take border tiles from larger neighbours until they are a fair size."""
    sizes = _sizes(assignment, count)
    mean = sum(sizes) / count
    for _ in range(60):
        small = [r for r in range(count) if sizes[r] < 0.8 * mean]
        if not small:
            return
        moved = False
        for region in small:
            edge = sorted(
                n for tile, r in assignment.items() if r == region
                for n in world.neighbors(tile)
                if assignment.get(n, region) != region and sizes[assignment[n]] > mean
            )
            for tile in dict.fromkeys(edge):
                donor = assignment[tile]
                if sizes[donor] <= mean or sizes[region] >= 0.8 * mean:
                    continue
                assignment[tile] = region
                sizes[donor] -= 1
                sizes[region] += 1
                moved = True
        if not moved:
            return


def _sizes(assignment: dict[int, int], count: int) -> list[int]:
    sizes = [0] * count
    for region in assignment.values():
        sizes[region] += 1
    return sizes


def _landmasses(world: WorldMap, land: list[int]) -> list[list[int]]:
    seen: set[int] = set()
    masses = []
    for start in land:
        if start in seen:
            continue
        mass = [start]
        seen.add(start)
        for tile in mass:
            for n in world.neighbors(tile):
                if n not in seen and not world.is_water(n):
                    seen.add(n)
                    mass.append(n)
        masses.append(mass)
    return sorted(masses, key=len, reverse=True)


def _quotas(sizes: list[int], count: int) -> list[int]:
    """Regions per landmass, proportional to size (largest remainder), so islands are not over-divided."""
    total = sum(sizes)
    exact = [count * size / total for size in sizes]
    quotas = [int(x) for x in exact]
    by_remainder = sorted(range(len(sizes)), key=lambda i: (exact[i] - quotas[i], sizes[i]), reverse=True)
    for i in by_remainder[: count - sum(quotas)]:
        quotas[i] += 1
    return quotas


def _spread(world: WorldMap, rng: random.Random, mass: list[int], quota: int) -> list[int]:
    """`quota` tiles of a landmass, each as far from the others as possible."""
    if quota <= 0:
        return []
    chosen = [rng.choice(mass)]
    nearest = {tile: _distance(world, tile, chosen[0]) for tile in mass}
    while len(chosen) < quota:
        # Far from every seed so far, with a little noise so maps differ beyond the first pick.
        pick = max(mass, key=lambda t: (nearest[t] + 2 * rng.random(), t))
        chosen.append(pick)
        for tile in mass:
            nearest[tile] = min(nearest[tile], _distance(world, tile, pick))
    return chosen


def _distance(world: WorldMap, a: int, b: int) -> int:
    ax, ay = world.xy(a)
    bx, by = world.xy(b)
    return abs(ax - bx) + abs(ay - by)


def _place_capital(world: WorldMap, rng: random.Random, region_id: int, region_of: list[int]) -> int:
    """A random buildable tile well inside the region; nearer the edge only if it has no interior."""
    land = [t for t, r in enumerate(region_of) if r == region_id and BIOME_INFO[world.biomes[t]].buildable]
    if not land:
        land = [t for t, r in enumerate(region_of) if r == region_id and not world.is_water(t)]

    def inside(tile: int, inset: int) -> bool:
        x, y = world.xy(tile)
        for dy in range(-inset, inset + 1):
            for dx in range(-inset, inset + 1):
                if not world.in_bounds(x + dx, y + dy):
                    return False
                other = region_of[world.idx(x + dx, y + dy)]
                if other != region_id and other >= 0:
                    return False
                if other < 0 and world.biomes[world.idx(x + dx, y + dy)] == Biome.OCEAN and inset == CAPITAL_INSET:
                    continue  # open sea is not another region's border
        return True

    for inset in range(CAPITAL_INSET, -1, -1):
        interior = [t for t in land if inside(t, inset)]
        if interior:
            return rng.choice(interior)
    return rng.choice(land)
