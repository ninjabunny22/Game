"""Hand-drawn maps: a blueprint is drawn in shapes, built into a map, checked, and saved.

What is drawn is exact: the coast's outline, the regions and their borders, which regions
touch and how (`links`), ridges and their passes, rivers, old bridges, capitals, gold mines,
start slots. What is generated, from the blueprint's own seed, is only the detail inside
that: the coast's wobble (never where `protect` covers), patches of forest and plain, hills,
heights for drawing, and small fish and game deposits. The checker (`check`) proves the
built map keeps to the drawing: every drawn link is there and no undrawn one is.
"""

import math
import random
from collections import deque
from dataclasses import dataclass, field

from opensimplex import OpenSimplex

from .biomes import BIOME_INFO, Biome
from .regions import Region
from .resources import DEPOSIT_TYPES, _grow_cluster, _pick_centre, compute_yields
from .passes import carve_passes
from .shapes import Shape, distance_to_line
from .world import BOAT_RANGE, WorldMap

LAND_LINKS = ("land", "pass", "neck", "river", "bridge", "causeway")  # links walked overland; "sea:N" is by boat
SETTLING_REACH = BOAT_RANGE  # open-water tiles a civ with boats (and no Navigation) can settle across
MIN_REGION_LAND = 25
SPECK = 10  # land smaller than this, holding no capital, is washed away
HOLE = 5  # enclosed water smaller than this is filled in, unless drawn as sea or shallows

HEIGHT = {Biome.PLAINS: 0.07, Biome.FOREST: 0.1, Biome.DESERT: 0.08, Biome.TUNDRA: 0.12,
          Biome.HILLS: 0.3, Biome.MOUNTAIN: 0.55, Biome.PEAKS: 0.85}
LEAST_HEIGHT = {Biome.HILLS: 0.2, Biome.MOUNTAIN: 0.42, Biome.PEAKS: 0.7}


@dataclass(frozen=True)
class Ridge:
    """A mountain chain: impassable peaks along the line, mountains on its flanks, and
    passes where a gap is drawn (walked as hills)."""
    points: tuple[tuple[float, float], ...]
    width: float = 3.0
    flank: float = 1.5
    gaps: tuple[tuple[float, float, float], ...] = ()  # (x, y, radius)


@dataclass(frozen=True)
class RegionSpec:
    key: str
    name: str
    capital_name: str
    capital: tuple[int, int]
    shape: Shape
    strength: float = 1.0
    defects: bool = True
    tags: tuple[str, ...] = ()


@dataclass
class Blueprint:
    id: str
    name: str
    width: int
    height: int
    seed: int
    premise: str
    land: list[Shape]
    regions: list[RegionSpec]
    links: list[tuple[str, str, str]]  # (region, region, kind): land, pass, bridge, causeway or sea:<gap>
    starts: dict[str, tuple[str, str]]  # slot -> (home region, second region)
    sets: dict[int, list]  # number of civs -> the slots used (or several such lists, one taken per game)
    best: str = ""  # the civ counts it plays best with, for the menu
    sea: list[Shape] = field(default_factory=list)  # cut out of the land: lagoons, straits
    shallows: list[Shape] = field(default_factory=list)  # water made wadeable: causeways
    protect: list[Shape] = field(default_factory=list)  # the coast keeps its drawn line here
    coast_noise: float = 1.2
    base: Biome = Biome.PLAINS
    zones: list[tuple[Shape, Biome]] = field(default_factory=list)  # painted in order
    patches: list[tuple[Shape, Biome, float]] = field(default_factory=list)  # share of the shape
    ridges: list[Ridge] = field(default_factory=list)
    lakes: list[Shape] = field(default_factory=list)
    rivers: list[list[tuple[float, float]]] = field(default_factory=list)  # source to mouth
    bridges: list[tuple[int, int]] = field(default_factory=list)
    deposits: list[tuple[str, tuple[int, int], int]] = field(default_factory=list)
    scatter: list[tuple[str, int, Shape | None]] = field(default_factory=list)
    mines: list[tuple[int, int]] = field(default_factory=list)
    # Pairs that may touch, but need not: corners of regions meeting across a river, where the
    # squares of the grid decide. Any that do touch are kept as links of kind "river".
    may_touch: list[tuple[str, str]] = field(default_factory=list)
    # Bridges over water, as drawn lines: every water tile a line crosses is bridged, the only
    # way across on foot (Tidewalk's causeways).
    causeways: list[list[tuple[float, float]]] = field(default_factory=list)

    @property
    def civs(self) -> tuple[int, int]:
        return min(self.sets), max(self.sets)


class BlueprintError(ValueError):
    pass


# -- building ------------------------------------------------------------------

def build(bp: Blueprint) -> WorldMap:
    """The map a blueprint draws. The same blueprint always builds the same map."""
    w, h = bp.width, bp.height
    world = WorldMap(w, h, bp.seed)
    world.map_id = bp.id
    rng = random.Random(bp.seed)
    noise = OpenSimplex(bp.seed)

    def wave(x: int, y: int, scale: float, salt: int = 0) -> float:
        return noise.noise2((x + 0.5) / scale + 97.0 * salt, (y + 0.5) / scale - 53.0 * salt)

    def covered(shapes: list[Shape]) -> list[bool]:
        return [any(s.contains(x + 0.5, y + 0.5) for s in shapes) for y in range(h) for x in range(w)]

    drawn = [a and not b for a, b in zip(covered(bp.land), covered(bp.sea))]
    protected = covered(bp.protect)
    capitals = {world.idx(*spec.capital) for spec in bp.regions}
    land = _wobble(world, drawn, protected, bp.coast_noise, wave)
    land = _tidy(world, land, capitals, covered(bp.sea) if bp.sea else [False] * (w * h), covered(bp.shallows))

    # Biomes: the base, then the drawn zones, then patches, then ridges.
    for i in range(w * h):
        world.biomes[i] = bp.base if land[i] else Biome.OCEAN
    for shape, biome in bp.zones:
        for i in _tiles_in(world, shape):
            if land[i]:
                world.biomes[i] = biome
    for k, (shape, biome, share) in enumerate(bp.patches):
        tiles = [i for i in _tiles_in(world, shape) if land[i]]
        if tiles:
            ranked = sorted(tiles, key=lambda i: (wave(*world.xy(i), 5.0, 10 + k), i))
            for i in ranked[: round(share * len(ranked))]:
                world.biomes[i] = biome
    for ridge in bp.ridges:
        for i in range(w * h):
            if not land[i]:
                continue
            x, y = world.xy(i)
            d = distance_to_line(ridge.points, x + 0.5, y + 0.5)
            if d > ridge.width / 2 + ridge.flank:
                continue
            gap = any((x + 0.5 - gx) ** 2 + (y + 0.5 - gy) ** 2 <= r * r for gx, gy, r in ridge.gaps)
            if gap:
                world.biomes[i] = Biome.HILLS
                world.passes.add(i)  # walked through, slowly
            else:
                world.biomes[i] = Biome.PEAKS if d <= ridge.width / 2 else Biome.MOUNTAIN
    for shape in bp.lakes:
        for i in _tiles_in(world, shape):
            if land[i] and not any(not land[n] and world.biomes[n] != Biome.LAKE
                                   for n in world.neighbors(i, diagonal=True)):
                world.biomes[i] = Biome.LAKE
    wadeable = covered(bp.shallows)
    for i in range(w * h):
        if world.biomes[i] == Biome.OCEAN and (wadeable[i] or any(
                land[n] for n in world.neighbors(i, diagonal=True))):
            world.biomes[i] = Biome.SHALLOWS

    _heights(world, wave)
    _rivers(world, bp)
    for x, y in bp.bridges:
        # Drawn near enough: the river tile nearest the drawn point, within two tiles.
        near = [t for t in world.rivers if abs(world.xy(t)[0] - x) <= 2 and abs(world.xy(t)[1] - y) <= 2]
        if not near:
            raise BlueprintError(f"{bp.id}: the bridge at {x},{y} is not on a river")
        world.bridges.add(min(near, key=lambda t: ((world.xy(t)[0] - x) ** 2 + (world.xy(t)[1] - y) ** 2, t)))
    for line in bp.causeways:
        tiles = _line_tiles(world, line)
        wet = [k for k, tile in enumerate(tiles) if world.is_water(tile)]
        for k in wet:
            world.bridges.add(tiles[k])
        if wet:  # the bridge as drawn: from the last land before the water to the first after it
            first, last = tiles[max(0, wet[0] - 1)], tiles[min(len(tiles) - 1, wet[-1] + 1)]
            world.spans.append((*world.xy(first), *world.xy(last)))
    carve_passes(world)
    _deposits(world, bp, rng)
    compute_yields(world)
    _regions(world, bp)
    world.links = [(_key(bp, a), _key(bp, b), kind) for a, b, kind in bp.links]
    walked = walking_links(world)
    drawn = {(min(a, b), max(a, b)) for a, b, _ in world.links}
    for a, b in bp.may_touch:
        pair = (min(_key(bp, a), _key(bp, b)), max(_key(bp, a), _key(bp, b)))
        if pair in walked and pair not in drawn:
            world.links.append((pair[0], pair[1], "river"))
            drawn.add(pair)
    world.starts = {slot: (_key(bp, home), _key(bp, second)) for slot, (home, second) in bp.starts.items()}
    world.start_sets = {n: [list(s) for s in (slots if isinstance(slots[0], list) else [slots])]
                        for n, slots in bp.sets.items()}
    assign_points(world)
    return world


def _key(bp: Blueprint, key: str) -> int:
    for i, spec in enumerate(bp.regions):
        if spec.key == key:
            return i
    raise BlueprintError(f"{bp.id}: no region called {key!r}")


def _tiles_in(world: WorldMap, shape: Shape) -> list[int]:
    return [world.idx(x, y) for y in range(world.height) for x in range(world.width)
            if shape.contains(x + 0.5, y + 0.5)]


def _distances(world: WorldMap, sources: list[int], through) -> list[int]:
    """Steps (orthogonal) from the nearest source, moving only onto tiles `through` allows."""
    far = len(world.biomes)
    dist = [far] * far
    queue = deque()
    for s in sources:
        dist[s] = 0
        queue.append(s)
    while queue:
        tile = queue.popleft()
        for n in world.neighbors(tile):
            if dist[n] == far and through(n):
                dist[n] = dist[tile] + 1
                queue.append(n)
    return dist


def _wobble(world, drawn, protected, amount, wave) -> list[bool]:
    """The drawn coast, nudged in and out by up to about `amount` tiles."""
    if amount <= 0:
        return list(drawn)
    size = len(drawn)
    to_water = _distances(world, [i for i in range(size) if not drawn[i]], lambda n: drawn[n])
    to_land = _distances(world, [i for i in range(size) if drawn[i]], lambda n: not drawn[n])
    land = []
    for i in range(size):
        x, y = world.xy(i)
        edge = x == 0 or y == 0 or x == world.width - 1 or y == world.height - 1
        if protected[i] or (edge and not drawn[i]):
            land.append(drawn[i])
            continue
        depth = to_water[i] - 0.5 if drawn[i] else 0.5 - to_land[i]
        land.append(depth + amount * wave(x, y, 6.0, 1) > 0)
    return land


def _components(world, mask) -> list[list[int]]:
    seen = [False] * len(mask)
    parts = []
    for start in range(len(mask)):
        if not mask[start] or seen[start]:
            continue
        seen[start] = True
        part = [start]
        for tile in part:
            for n in world.neighbors(tile):
                if mask[n] and not seen[n]:
                    seen[n] = True
                    part.append(n)
        parts.append(part)
    return parts


def _tidy(world, land, capitals, sea, wadeable) -> list[bool]:
    """Wash away specks of land and fill in pinholes of water the wobble left."""
    land = list(land)
    for part in _components(world, land):
        if len(part) < SPECK and not capitals.intersection(part):
            for i in part:
                land[i] = False
    for part in _components(world, [not t for t in land]):
        if len(part) < HOLE and not any(sea[i] or wadeable[i] for i in part):
            for i in part:
                land[i] = True
    return land


def _heights(world: WorldMap, wave) -> None:
    size = len(world.biomes)
    land = [not world.is_water(i) or world.biomes[i] == Biome.LAKE for i in range(size)]
    raw = [0.0] * size
    for i in range(size):
        if land[i] and world.biomes[i] != Biome.LAKE:
            x, y = world.xy(i)
            raw[i] = HEIGHT[world.biomes[i]] + 0.035 * wave(x, y, 9.0, 2) + 0.02 * wave(x, y, 3.0, 3)
    for _ in range(2):  # soften the steps between biomes
        smooth = list(raw)
        for i in range(size):
            if land[i] and world.biomes[i] != Biome.LAKE:
                around = [raw[n] for n in world.neighbors(i, diagonal=True)
                          if land[n] and world.biomes[n] != Biome.LAKE]
                smooth[i] = 0.5 * raw[i] + 0.5 * sum(around) / len(around) if around else raw[i]
        raw = smooth
    to_land = _distances(world, [i for i in range(size) if land[i]], lambda n: not land[n])
    for i in range(size):
        biome = world.biomes[i]
        if biome == Biome.LAKE:
            continue
        if not land[i]:
            world.heights[i] = -0.04 if biome == Biome.SHALLOWS else round(-min(0.5, 0.04 + 0.06 * to_land[i]), 3)
        else:
            world.heights[i] = round(min(1.0, max(0.02, raw[i], LEAST_HEIGHT.get(biome, 0.0))), 3)
    for lake in _components(world, [b == Biome.LAKE for b in world.biomes]):
        shore = [world.heights[n] for t in lake for n in world.neighbors(t) if world.biomes[n] != Biome.LAKE]
        level = round(max(0.01, min(shore, default=0.05) - 0.01), 3)
        for t in lake:
            world.heights[t] = level


def _line_tiles(world: WorldMap, points) -> list[int]:
    """The tiles a drawn line passes through, as one orthogonally connected chain."""
    chain: list[tuple[int, int]] = []
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        steps = max(1, int(math.hypot(bx - ax, by - ay) * 4))
        for k in range(steps + 1):
            x = int(math.floor(ax + (bx - ax) * k / steps))
            y = int(math.floor(ay + (by - ay) * k / steps))
            if chain and chain[-1] == (x, y):
                continue
            if chain:
                px, py = chain[-1]
                if px != x and py != y:  # a diagonal step: go round by the side
                    chain.append((x, py))
            chain.append((x, y))
    return [world.idx(x, y) for x, y in chain if world.in_bounds(x, y)]


def _rivers(world: WorldMap, bp: Blueprint) -> None:
    from .water import MAX_RIVER_SIZE, TILES_PER_SIZE_STEP
    for line in bp.rivers:
        path: list[int] = []
        mouth = None
        for tile in _line_tiles(world, line):
            if world.is_water(tile) or tile in world.rivers:
                mouth = tile
                break
            if world.is_peak(tile):
                raise BlueprintError(f"{bp.id}: a river runs into peaks at {world.xy(tile)}")
            if tile not in path:
                path.append(tile)
        if mouth is None:
            raise BlueprintError(f"{bp.id}: the river from {line[0]} never reaches water or another river")
        for distance, tile in enumerate(path):
            world.rivers[tile] = min(MAX_RIVER_SIZE, 1 + distance // TILES_PER_SIZE_STEP)
            world.river_flow[tile] = path[distance + 1] if distance + 1 < len(path) else mouth
        joined = mouth
        while joined in world.rivers:  # a tributary swells the river it joins
            world.rivers[joined] = min(MAX_RIVER_SIZE, world.rivers[joined] + 1)
            joined = world.river_flow[joined]


def _deposits(world: WorldMap, bp: Blueprint, rng: random.Random) -> None:
    for type_id, (x, y), size in bp.deposits:
        _grow_cluster(world, rng, world.idx(x, y), type_id, DEPOSIT_TYPES[type_id], size)
    for x, y in bp.mines:
        tile = world.idx(x, y)
        if world.is_water(tile) or world.is_peak(tile):
            raise BlueprintError(f"{bp.id}: the mine at {x},{y} is not on open land")
        if world.deposits.get(tile) != "gold":
            _grow_cluster(world, rng, tile, "gold", DEPOSIT_TYPES["gold"], 3)
        world.mines.append(tile)
    for type_id, count, shape in bp.scatter:
        dtype = DEPOSIT_TYPES[type_id]
        inside = set(_tiles_in(world, shape)) if shape is not None else None
        eligible = [i for i, b in enumerate(world.biomes) if b in dtype.biomes and i not in world.deposits
                    and (inside is None or i in inside)]
        centres = [t for t, d in world.deposits.items() if d == type_id]
        for _ in range(count):
            if not eligible:
                break
            centre = _pick_centre(world, rng, eligible, centres, dtype.spacing)
            if centre is None:
                break
            centres.append(centre)
            _grow_cluster(world, rng, centre, type_id, dtype, rng.randint(*dtype.size))


def _regions(world: WorldMap, bp: Blueprint) -> None:
    size = len(world.biomes)
    region_of = [-1] * size
    for i in range(size):
        if world.is_water(i) and world.biomes[i] != Biome.LAKE:
            continue
        x, y = world.xy(i)
        for r, spec in enumerate(bp.regions):
            if spec.shape.contains(x + 0.5, y + 0.5):
                region_of[i] = r
                break
    # Land the drawing missed (the coast's wobble) goes to the nearest region over land.
    queue = deque(i for i in range(size) if region_of[i] >= 0)
    while queue:
        tile = queue.popleft()
        for n in world.neighbors(tile):
            if region_of[n] < 0 and not (world.is_water(n) and world.biomes[n] != Biome.LAKE):
                region_of[n] = region_of[tile]
                queue.append(n)
    # Shallows belong to the region of the nearest land.
    queue = deque(i for i in range(size) if region_of[i] >= 0)
    while queue:
        tile = queue.popleft()
        for n in world.neighbors(tile):
            if region_of[n] < 0 and world.biomes[n] == Biome.SHALLOWS:
                region_of[n] = region_of[tile]
                queue.append(n)
    world.region_of = region_of
    world.regions = []
    for r, spec in enumerate(bp.regions):
        capital = world.idx(*spec.capital)
        tiles = [t for t in range(size) if region_of[t] == r and world.biomes[t] not in (Biome.LAKE, Biome.PEAKS)]
        world.regions.append(Region(r, spec.name, spec.capital_name, capital, tiles, strength=spec.strength,
                                    defects=spec.defects, tags=tuple(spec.tags)))
    world.capital_tiles = {region.capital: region.id for region in world.regions}


def assign_points(world: WorldMap) -> None:
    """What each region is worth for holding it: 1 to 3 points, from its land and its riches,
    each measured against the map's average region. A drawn prize is worth at least 2."""
    land = [sum(1 for t in r.tiles if not world.is_water(t)) for r in world.regions]
    riches = []
    for r in world.regions:
        total = 0.0
        for t in r.tiles:
            y = world.yields[t]
            total += y.get("food", 0) + 0.7 * y.get("wood", 0) + y.get("stone", 0) + 1.5 * y.get("ore", 0)
            total += 2.0 * y.get("gold", 0)
        total += 25.0 * sum(1 for m in world.mines if world.region_of[m] == r.id)
        riches.append(total)
    mean_land = sum(land) / len(land)
    mean_riches = sum(riches) / len(riches)
    for r, a, b in zip(world.regions, land, riches):
        worth = 0.4 * a / mean_land + 0.6 * b / mean_riches
        r.points = 1 if worth < 0.75 else 2 if worth < 1.4 else 3
        if "prize" in r.tags:
            r.points = max(2, r.points)


# -- checking ------------------------------------------------------------------

def walking_links(world: WorldMap) -> set[tuple[int, int]]:
    """Pairs of regions an army can walk between: neighbouring tiles, both walkable."""
    pairs = set()
    for t, r in enumerate(world.region_of):
        if r < 0 or not world.walkable(t):
            continue
        for n in world.neighbors(t):
            other = world.region_of[n]
            if other >= 0 and other != r and world.walkable(n):
                pairs.add((min(r, other), max(r, other)))
    return pairs


def sea_gap(world: WorldMap, a: int, b: int) -> int | None:
    """Fewest open-water tiles between the land of two regions (orthogonal steps), the way
    settlers with boats reach across; None if no water joins them."""
    starts = [t for t in world.regions[a].tiles if any(world.is_open_water(n) for n in world.neighbors(t))]
    targets = set(world.regions[b].tiles)
    far = len(world.biomes)
    dist = {}
    queue = deque()
    for t in starts:
        for n in world.neighbors(t):
            if world.is_open_water(n) and n not in dist:
                dist[n] = 1
                queue.append(n)
    while queue:
        tile = queue.popleft()
        for n in world.neighbors(tile):
            if n in targets:
                return dist[tile]
            if world.is_open_water(n) and n not in dist:
                dist[n] = dist[tile] + 1
                if dist[n] < far:
                    queue.append(n)
    return None


def check(world: WorldMap, bp: Blueprint) -> list[str]:
    """Everything about the built map that breaks the drawing. Empty when it keeps to it."""
    from ..economy.buildings import CASTLE_REACH
    from .pathfinding import find_path
    problems = []
    names = {r.id: r.name for r in world.regions}
    for region in world.regions:
        land = [t for t in region.tiles if not world.is_water(t)]
        if len(land) < MIN_REGION_LAND:
            problems.append(f"{region.name} has only {len(land)} land tiles")
        cx, cy = world.xy(region.capital)
        if world.region_of[region.capital] != region.id:
            problems.append(f"{region.capital_name} lies outside {region.name}")
        for dy in range(-CASTLE_REACH, CASTLE_REACH + 1):
            for dx in range(-CASTLE_REACH, CASTLE_REACH + 1):
                if not world.in_bounds(cx + dx, cy + dy):
                    problems.append(f"{region.capital_name}'s castle runs off the map")
                    continue
                t = world.idx(cx + dx, cy + dy)
                if not BIOME_INFO[world.biomes[t]].buildable or world.region_of[t] != region.id or t in world.rivers:
                    problems.append(f"{region.capital_name}'s castle ground at {cx + dx},{cy + dy} is not open "
                                    f"{region.name} land ({world.biomes[t].name.lower()})")
    for t in range(len(world.biomes)):
        if world.claimable(t) and world.region_of[t] < 0:
            problems.append(f"land at {world.xy(t)} belongs to no region")
            break

    drawn = set()
    for a, b, kind in world.links:
        if kind in LAND_LINKS:
            drawn.add((min(a, b), max(a, b)))
        elif kind.startswith("sea:"):
            gap = sea_gap(world, a, b)
            if gap is None or gap > int(kind[4:]):
                problems.append(f"{names[a]} to {names[b]}: {gap} tiles of open water, drawn as at most {kind[4:]}")
        else:
            problems.append(f"unknown link kind {kind!r}")
    actual = walking_links(world)
    for a, b in sorted(drawn - actual):
        problems.append(f"{names[a]} and {names[b]} are drawn as touching but cannot be walked between")
    for a, b in sorted(actual - drawn):
        problems.append(f"{names[a]} and {names[b]} touch, but no link between them is drawn")

    for slot, (home, second) in world.starts.items():
        # A slot's two regions need not touch (on the Long March the spine lies between a
        # band's coasts), but one must be reachable from the other over land.
        if find_path(world, world.regions[home].capital, world.regions[second].capital, bridges=True,
                     boats=False, max_nodes=10 ** 6) is None:
            problems.append(f"slot {slot}: {names[second]} cannot be reached overland from {names[home]}")
    for n, options in world.start_sets.items():
        for slots in options:
            if len(slots) != n or len(set(slots)) != n:
                problems.append(f"{n} civs: {len(slots)} slots")
                continue
            taken = [r for s in slots for r in world.starts[s]]
            if len(taken) != len(set(taken)):
                problems.append(f"{n} civs: slots {slots} share a region")
            homes = [world.regions[world.starts[s][0]].capital for s in slots]
            for i, a in enumerate(homes):
                for b in homes[i + 1:]:
                    if find_path(world, a, b, bridges=True, boats=True, max_nodes=10 ** 6) is None:
                        problems.append(f"{n} civs: {names[world.region_of[a]]} cannot reach {names[world.region_of[b]]}")
            if len(world.regions) <= 2 * n:
                problems.append(f"{n} civs leave no region unclaimed")
    return problems
