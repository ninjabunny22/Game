"""Passes through mountains. Mountains block armies and villagers; a pass is a mountain (or a
gap in a ridge of peaks) they can get through, slowly. A drawn map has its passes drawn; any
map also gets passes carved wherever its mountains would otherwise cut land in two, so no
stretch of land is walled off by mountains alone."""

import heapq

from .biomes import Biome
from .world import WorldMap


def _land_parts(world: WorldMap, through) -> list[int]:
    """Component id per tile of the land `through` allows (-1 elsewhere), orthogonal steps."""
    part = [-1] * len(world.biomes)
    label = 0
    for start in range(len(world.biomes)):
        if part[start] >= 0 or not through(start):
            continue
        part[start] = label
        stack = [start]
        while stack:
            tile = stack.pop()
            for n in world.neighbors(tile):
                if part[n] < 0 and through(n):
                    part[n] = label
                    stack.append(n)
        label += 1
    return part


def carve_passes(world: WorldMap) -> None:
    """Mark mountain tiles as passes until mountains alone divide no land: for each stretch of
    walkable land cut off from the rest of its landmass by mountains, the shortest way over the
    mountains to the rest becomes a pass. Uses no dice, so a map is the same however often it
    is built."""
    def ground(t: int) -> bool:  # what can be walked once mountains count as land
        return not world.is_water(t) and not world.is_peak(t) or t in world.bridges

    def walkable(t: int) -> bool:
        return world.walkable(t)

    masses = _land_parts(world, ground)
    while True:
        parts = _land_parts(world, walkable)
        # The landmasses whose walkable land is in more than one piece.
        pieces: dict[int, set[int]] = {}
        for t, p in enumerate(parts):
            if p >= 0 and masses[t] >= 0:
                pieces.setdefault(masses[t], set()).add(p)
        split = sorted(m for m, ps in pieces.items() if len(ps) > 1)
        if not split:
            return
        carved = len(world.passes)
        for mass in split:
            ps = sorted(pieces[mass], key=lambda p: -sum(1 for x in parts if x == p))
            main = ps[0]
            # Shortest way from the main piece to any other, over mountains (each counts 1).
            sources = [t for t, p in enumerate(parts) if p == main]
            dist = {t: 0 for t in sources}
            back: dict[int, int] = {}
            heap = [(0, t) for t in sources]
            found = None
            while heap:
                d, t = heapq.heappop(heap)
                if d > dist[t]:
                    continue
                if parts[t] >= 0 and parts[t] != main:
                    found = t
                    break
                for n in world.neighbors(t):
                    if masses[n] != mass:
                        continue
                    step = 0 if walkable(n) else 1 if world.biomes[n] == Biome.MOUNTAIN else None
                    if step is None:
                        continue
                    if d + step < dist.get(n, 1 << 30):
                        dist[n] = d + step
                        back[n] = t
                        heapq.heappush(heap, (d + step, n))
            if found is None:
                continue
            t = found
            while t in back:
                if world.biomes[t] == Biome.MOUNTAIN:
                    world.passes.add(t)
                t = back[t]
        if len(world.passes) == carved:
            return  # what is left apart is parted by more than mountains
