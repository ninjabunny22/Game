import functools
import math
from dataclasses import dataclass, field

from ..datafiles import load_json
from ..map import BIOME_INFO, WorldMap
from .villagers import builders_on_site

COST_GROWTH_PER_COPY = 0.2
# A tile holds one building. Each type has its own size: it stands on a square of that many
# tiles a side (BuildingDef.size), and no two buildings' ground overlaps.
FILL_FIRST = 1000.0  # a site beside something already built is preferred to breaking new ground
HARBOUR_SPREAD = 12  # tiles a civ's harbours keep apart, so they serve different shores
FILL_FIRST_YIELD = 1.0  # ... for buildings placed by yield, worth half a point of yield
CASTLE_REACH = 2  # a capital's castle stands on its own tile and the tiles this far around it: 5 x 5


@dataclass(frozen=True)
class BuildingDef:
    id: str
    name: str
    category: str  # which personality weight / need drives it
    placement: str  # "center", "coast" or "yield:<resource>"
    cost: dict[str, float]
    build_time: int
    effects: dict = field(default_factory=dict)
    upkeep: dict[str, float] = field(default_factory=dict)  # per tick; unpaid buildings stop working
    need_resource: str | None = None
    requires_tech: str | None = None
    max_count: int | None = None
    size: int = 1  # tiles a side of the square it stands on
    color: str = "#ffffff"
    height: float = 0.5

    @property
    def stores(self) -> dict[str, float]:
        """Storage capacity this building adds, by resource (empty for most buildings)."""
        return self.effects.get("store", {})

    def cost_for(self, existing: int) -> dict[str, float]:
        """Each copy already owned makes the next one more expensive."""
        factor = 1 + COST_GROWTH_PER_COPY * existing
        return {res: round(amount * factor) for res, amount in self.cost.items()}


@functools.cache
def load_building_defs() -> dict[str, BuildingDef]:
    return {bid: BuildingDef(id=bid, **raw) for bid, raw in load_json("buildings.json").items()}


def footprint(world: WorldMap, building_type: str, tile: int) -> list[int] | None:
    """The tiles a building of this type stands on when placed at `tile`, or None if the square
    runs off the map. An odd-sized square is centred on `tile`; an even one has `tile` as the
    corner nearest the map's origin, so a 2x2 building's middle is half a tile down and right."""
    size = load_building_defs()[building_type].size
    if size == 1:
        return [tile]
    x, y = world.xy(tile)
    x0, y0 = x - (size - 1) // 2, y - (size - 1) // 2
    if not (world.in_bounds(x0, y0) and world.in_bounds(x0 + size - 1, y0 + size - 1)):
        return None
    return [world.idx(x0 + dx, y0 + dy) for dy in range(size) for dx in range(size)]


def everything_built(civ, world: WorldMap) -> dict:
    """The building standing on each built-on tile, whoever owns it: a large building is under
    every tile of its square, and squares do not stop at borders."""
    built: dict = {}
    for owner in getattr(world, "civs", None) or [civ]:
        for building in owner.buildings:
            for tile in footprint(world, building.type, building.tile) or [building.tile]:
                built[tile] = building
    return built


def placement_problem(civ, world: WorldMap, bdef: BuildingDef, tile: int, without=None,
                      built: dict | None = None) -> str | None:
    """Why a building of this type cannot stand on `tile`, or None if it can.

    The one rule for where buildings go, whoever is placing them. A building stands on a
    square of its own size; every tile of it must be the civ's, buildable, and free of any
    other building and of a capital's castle (the capital's tile and those CASTLE_REACH around it).
    `without` is a building, or a list of them, to reckon as already gone (about to be
    demolished to make room); `built` is everything_built(), for a caller asking about many
    tiles at once.
    """
    gone = without if isinstance(without, list) else [without]
    if bdef.id == "stables" and (tile in world.capital_tiles or any(s.tile == tile for s in civ.settlements)):
        return "stables need room for the horses: never on a capital's tile"
    ground = footprint(world, bdef.id, tile)
    if ground is None:
        return "it would run off the map"
    if built is None:
        built = everything_built(civ, world)
    for part in ground:
        if part in world.mines:
            return "a gold mine stands here"
        if castle_ground(world, part) or any(
                _near(world, s.tile, part) for s in civ.settlements if s.tile not in world.capital_tiles):
            return "a capital's castle stands here"
        if part not in civ.territory:
            return "not the civ's land"
        if not BIOME_INFO[world.biomes[part]].buildable:
            return "the ground cannot be built on"
        if part in built and not any(built[part] is building for building in gone):
            return "something stands here already"
    if bdef.placement == "coast" and not any(world.is_water(n) for part in ground for n in world.neighbors(part)):
        return "a harbour has to be on the water"
    return None


def place(civ, world: WorldMap, bdef: BuildingDef, tile: int):
    """Start a building of this type on `tile`. The only way a building comes to stand anywhere:
    raises ValueError if the placement rules do not allow it there."""
    from ..civ.civilization import Building  # civ imports the economy, not the other way round

    problem = placement_problem(civ, world, bdef, tile)
    if problem:
        raise ValueError(f"{bdef.name} cannot be placed on tile {tile}: {problem}")
    building = Building(bdef.id, tile)
    civ.buildings.append(building)
    return building


def _near(world: WorldMap, a: int, b: int) -> bool:
    ax, ay = world.xy(a)
    bx, by = world.xy(b)
    return max(abs(ax - bx), abs(ay - by)) <= CASTLE_REACH


def castle_ground(world: WorldMap, tile: int) -> bool:
    """True if a capital's castle stands on this tile: the capital's own tile or one of
    those around it. Nothing is ever built there."""
    ground = getattr(world, "_castle_ground", None)
    if ground is None or ground[0] != len(world.capital_tiles):
        tiles = {n for capital in world.capital_tiles for n in castle_square(world, capital)}
        ground = world._castle_ground = (len(world.capital_tiles), tiles)
    return tile in ground[1]


def castle_square(world: WorldMap, tile: int) -> list[int]:
    """The tiles a castle on `tile` stands on: it and those within CASTLE_REACH, on the map."""
    x, y = world.xy(tile)
    return [(y + dy) * world.width + x + dx
            for dy in range(-CASTLE_REACH, CASTLE_REACH + 1) for dx in range(-CASTLE_REACH, CASTLE_REACH + 1)
            if 0 <= x + dx < world.width and 0 <= y + dy < world.height]


def may_stand(world: WorldMap, building_type: str, tile: int) -> bool:
    """False for a building that could never have been placed on this tile whoever owned it
    (anything where a castle stands, stables on a capital's tile above all). Checked when
    buildings change hands with their tile."""
    return not castle_ground(world, tile) and tile not in world.mines


def survey_ground(civ, world: WorldMap) -> tuple[set[int], set[int]]:
    """The civ's tiles that are free to build on, and the tiles beside something built.
    The same rule as placement_problem, worked out once for the whole territory; good until
    the next building goes up or comes down."""
    built = everything_built(civ, world)
    own_castles = {n for s in civ.settlements if s.tile not in world.capital_tiles
                   for n in castle_square(world, s.tile)}
    free, taken = set(), set(built)
    for tile in civ.territory:
        if castle_ground(world, tile) or tile in own_castles or tile in world.mines:
            taken.add(tile)
        elif tile not in built and BIOME_INFO[world.biomes[tile]].buildable and tile not in civ.out_of_reach:
            free.add(tile)
    # Off the map's side edge this wraps to the far side, which only ever costs a preference.
    width = world.width
    around = (-width - 1, -width, -width + 1, -1, 1, width - 1, width, width + 1)
    return free, {tile + step for tile in taken for step in around}


WRONG_WATER = 1000.0  # a harbour on water that does not lead to its goal is a last resort


def water_bodies(world: WorldMap, tiles) -> set[int]:
    """Which bodies of water (seas, lagoons, lakes: each joined stretch of water) the tiles touch."""
    bodies = getattr(world, "_water_bodies", None)
    if bodies is None:
        bodies = [-1] * len(world.biomes)
        label = 0
        for start in range(len(world.biomes)):
            if bodies[start] >= 0 or not world.is_water(start):
                continue
            bodies[start] = label
            stack = [start]
            while stack:
                tile = stack.pop()
                for n in world.neighbors(tile):
                    if bodies[n] < 0 and world.is_water(n):
                        bodies[n] = label
                        stack.append(n)
            label += 1
        world._water_bodies = bodies
    return {bodies[n] for t in tiles for n in world.neighbors(t) if bodies[n] >= 0}


def find_site(civ, world: WorldMap, bdef: BuildingDef, ground: tuple | None = None) -> int | None:
    """Best tile in the civ's territory where placement_problem allows this building, or None.

    Sites beside something already built (or beside a castle) are taken before new ground is
    broken, so buildings gather into villages. `ground` is survey_ground(), for a caller
    looking for several sites at once.
    """
    free, beside_something = ground or survey_ground(civ, world)
    cx, cy = world.xy(civ.capital.tile)
    resource = bdef.placement.partition(":")[2]
    # A harbour is for getting somewhere: it goes on the shore nearest a capital the civ does
    # not hold, and well away from any harbour it already has.
    own = {s.tile for s in civ.settlements}
    abroad = [world.xy(tile) for tile in world.capital_tiles if tile not in own]
    harbours = [world.xy(b.tile) for b in civ.buildings if b.type == bdef.id]
    goal = getattr(civ, "harbour_goal", None) if bdef.placement == "coast" else None
    goal_water = water_bodies(world, world.regions[world.region_of[goal]].tiles) if goal is not None else set()
    best, best_score = None, -math.inf
    for tile in sorted(free):
        ground = footprint(world, bdef.id, tile) if bdef.size > 1 else (tile,)
        if ground is None or any(part not in free for part in ground):
            continue
        if bdef.placement == "coast" and not any(world.is_water(n) for part in ground for n in world.neighbors(part)):
            continue
        beside = any(part in beside_something for part in ground)
        x, y = world.xy(tile)
        distance = math.hypot(x - cx, y - cy)
        if resource:
            tile_yield = max(world.yields[part].get(resource, 0) for part in ground)
            if tile_yield <= 0:
                continue
            score = 2 * tile_yield - 0.15 * distance + (FILL_FIRST_YIELD if beside else 0.0)
        elif bdef.placement == "coast" and goal is not None:
            # Facing the place it wants to reach: on water that leads there, as near as can be.
            gx, gy = world.xy(goal)
            score = -math.hypot(x - gx, y - gy)
            if not water_bodies(world, ground) & goal_water:
                score -= WRONG_WATER
            score -= sum(HARBOUR_SPREAD for hx, hy in harbours if math.hypot(x - hx, y - hy) < HARBOUR_SPREAD)
        elif bdef.placement == "coast" and abroad:
            score = -min(math.hypot(x - ax, y - ay) for ax, ay in abroad)
            score -= sum(HARBOUR_SPREAD for hx, hy in harbours if math.hypot(x - hx, y - hy) < HARBOUR_SPREAD)
        else:
            score = -distance + (FILL_FIRST if beside else 0.0)
        if score > best_score:
            best, best_score = tile, score
    return best


def demolish(civ, building, mods, building_defs, events: list) -> None:
    """Tear down one of the civ's own buildings, freeing its slot and recovering some materials.

    The refund is a share of the base cost: mods.demolition_refund, which techs raise.
    """
    civ.buildings.remove(building)
    bdef = building_defs[building.type]
    # Unfinished buildings return in proportion to how far along they were.
    share = mods.demolition_refund * (1.0 if building.complete else building.progress)
    for res, amount in bdef.cost.items():
        civ.resources[res] += share * amount
    events.append({"civ": civ.id, "kind": "demolition", "text": f"{civ.name} demolished a {bdef.name}"})


def advance_construction(civ, mods, building_defs, events: list) -> None:
    """Buildings under way advance, but only those with a villager on site building them."""
    staffed = builders_on_site(civ)
    from .villagers import buildings_under_way
    for building in buildings_under_way(civ, mods):
        if building.id not in staffed:
            continue
        bdef = building_defs[building.type]
        building.progress += (1 + mods.build_speed) / bdef.build_time
        if building.progress >= 1:
            building.progress = 1.0
            building.complete = True
            events.append({"civ": civ.id, "kind": "building", "text": f"{civ.name} built a {bdef.name}"})
