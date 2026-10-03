"""Shortest paths over the tile grid, using the one crossing rule in WorldMap."""

import heapq

from .biomes import Biome
from .world import WorldMap

TERRAIN_COST = {Biome.FOREST: 1.2, Biome.HILLS: 1.5, Biome.MOUNTAIN: 2.5}  # default 1


def step_cost(world: WorldMap, tile: int, bridges: bool, boats: bool) -> float | None:
    """Cost of moving onto `tile`, or None if it cannot be entered."""
    crossing = world.crossing_cost(tile, bridges, boats)
    if crossing is None:
        return None
    return crossing * TERRAIN_COST.get(world.biomes[tile], 1.0)


def find_path(world: WorldMap, start: int, goal: int, bridges: bool = False, boats: bool = False,
              max_nodes: int = 6000) -> list[int] | None:
    """Cheapest route from start to goal as the tiles to step onto, in order (start excluded).

    Open water is impassable without boats and rivers are slow without bridges.
    Returns [] if already there and None if there is no route.
    """
    if start == goal:
        return []
    gx, gy = world.xy(goal)

    def estimate(tile: int) -> float:
        x, y = world.xy(tile)
        return abs(x - gx) + abs(y - gy)

    best = {start: 0.0}
    parent: dict[int, int] = {}
    frontier = [(estimate(start), 0.0, start)]
    expanded = 0
    while frontier and expanded < max_nodes:
        _, cost, tile = heapq.heappop(frontier)
        if tile == goal:
            path = []
            while tile != start:
                path.append(tile)
                tile = parent[tile]
            return path[::-1]
        if cost > best.get(tile, float("inf")):
            continue
        expanded += 1
        for n in world.neighbors(tile):
            step = step_cost(world, n, bridges, boats)
            if step is None:
                continue
            new_cost = cost + step
            if new_cost < best.get(n, float("inf")):
                best[n] = new_cost
                parent[n] = tile
                heapq.heappush(frontier, (new_cost + estimate(n), new_cost, n))
    return None
