"""Shortest paths over the tile grid, using the one crossing rule in WorldMap."""

import heapq
import math
from collections.abc import Collection

from .biomes import Biome
from .world import WorldMap

TERRAIN_COST = {Biome.FOREST: 1.2, Biome.HILLS: 1.5, Biome.MOUNTAIN: 2.5}  # default 1
PASS_COST = 2.5  # a pass through mountains or peaks: as slow as climbing a mountain
DIAGONAL = math.sqrt(2)  # a diagonal step goes this much further than a straight one


def step_cost(world: WorldMap, tile: int, bridges: bool, boats: bool) -> float | None:
    """Cost of moving onto `tile`, or None if it cannot be entered."""
    crossing = world.crossing_cost(tile, bridges, boats)
    if crossing is None:
        return None
    if tile in world.passes:
        return crossing * PASS_COST  # a pass is a way through, not an easy one
    return crossing * TERRAIN_COST.get(world.biomes[tile], 1.0)


def move_cost(world: WorldMap, here: int, there: int, bridges: bool, boats: bool) -> float | None:
    """Cost of one step from `here` to the neighbouring tile `there`, straight or diagonal, or
    None if it cannot be taken. A diagonal step goes DIAGONAL times as far, and cannot cut the
    corner between two tiles that cannot be entered (between two peaks, or across a point of
    land between two waters it has no boat for)."""
    cost = step_cost(world, there, bridges, boats)
    if cost is None:
        return None
    w = world.width
    dx, dy = there % w - here % w, there // w - here // w
    if dx and dy:
        if (step_cost(world, here + dx, bridges, boats) is None
                or step_cost(world, here + dy * w, bridges, boats) is None):
            return None
        return cost * DIAGONAL
    return cost


def find_path(world: WorldMap, start: int, goal: int, bridges: bool = False, boats: bool = False,
              max_nodes: int = 6000, ports: Collection[int] | None = None) -> list[int] | None:
    """Cheapest route from start to goal as the tiles to step onto, in order (start excluded).

    Steps go eight ways, so a route on the slant is as short as the same distance straight
    across (a route in four directions made some ways on the map far longer than others of the
    same length). Water (but for bridges) is impassable without boats, mountains without a
    pass, and rivers are slow without bridges. With `ports` given, water can only be entered
    from one of those land tiles (the ones near a working harbour); once afloat a traveller may
    land anywhere. Returns [] if already there and None if there is no route.
    """
    if start == goal:
        return []
    gx, gy = world.xy(goal)

    def estimate(tile: int) -> float:  # the octile distance: never more than the true cost
        x, y = world.xy(tile)
        dx, dy = abs(x - gx), abs(y - gy)
        return max(dx, dy) + (DIAGONAL - 1) * min(dx, dy)

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
        ashore = ports is not None and tile not in ports and not world.is_boat_water(tile)
        for n in world.neighbors(tile, diagonal=True):
            step = move_cost(world, tile, n, bridges, boats)
            if step is None or (ashore and world.is_boat_water(n)):
                continue
            new_cost = cost + step
            if new_cost < best.get(n, float("inf")):
                best[n] = new_cost
                parent[n] = tile
                heapq.heappush(frontier, (new_cost + estimate(n), new_cost, n))
    return None
