import math
from dataclasses import dataclass, field

from ..datafiles import load_json
from ..map import BIOME_INFO, WorldMap
from .villagers import builders_on_site

COST_GROWTH_PER_COPY = 0.2
TILE_SLOTS = 3  # buildings a tile can hold, capitals included; never two of the same type
FILL_FIRST = 1000.0  # a tile already built on (or a capital) is preferred to breaking new ground
FILL_FIRST_YIELD = 1.0  # ... for buildings placed by yield, worth half a point of yield
# Large buildings that take a whole tile: nothing shares it with them, and they do not go on a
# capital's tile, where the capital itself stands.
EXCLUSIVE = frozenset({"harbour", "stables"})


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


def load_building_defs() -> dict[str, BuildingDef]:
    return {bid: BuildingDef(id=bid, **raw) for bid, raw in load_json("buildings.json").items()}


def placement_problem(civ, world: WorldMap, bdef: BuildingDef, tile: int, without=None,
                      on_tile: dict | None = None) -> str | None:
    """Why a building of this type cannot stand on `tile`, or None if it can.

    The one rule for where buildings go, whoever is placing them. `without` is a building
    to reckon as already gone (one about to be demolished to make room); `on_tile` is
    civ.buildings_by_tile(), for a caller asking about many tiles at once.
    """
    capital = tile in world.capital_tiles or any(s.tile == tile for s in civ.settlements)
    if bdef.id == "stables" and capital:
        return "stables need room for the horses: never on a capital's tile"
    if tile not in civ.territory:
        return "not the civ's land"
    if not BIOME_INFO[world.biomes[tile]].buildable:
        return "the ground cannot be built on"
    standing = civ.buildings if on_tile is None else on_tile.get(tile, ())
    there = [b for b in standing if b.tile == tile and b is not without]
    if len(there) >= TILE_SLOTS:
        return "the tile is full"
    if any(b.type == bdef.id for b in there):
        return "one of these stands here already"
    if any(b.type in EXCLUSIVE for b in there):
        return "a building that takes the whole tile stands here"
    if bdef.id in EXCLUSIVE and (there or capital):
        return "it takes a whole tile to itself"
    if bdef.placement == "coast" and not any(world.is_water(n) for n in world.neighbors(tile)):
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


def may_stand(world: WorldMap, building_type: str, tile: int) -> bool:
    """False for a building that could never have been placed on this tile whoever owned it
    (stables on a capital's tile). Checked when buildings change hands with their tile."""
    return not (building_type == "stables" and tile in world.capital_tiles)


def find_site(civ, world: WorldMap, bdef: BuildingDef) -> int | None:
    """Best tile in the civ's territory where placement_problem allows this building, or None.

    A tile holds up to TILE_SLOTS buildings, no two of the same type; a harbour or stables
    takes a tile to itself. Tiles already built on are filled before new ones are started,
    so buildings gather into villages.
    """
    on_tile = civ.buildings_by_tile()
    settled = set(on_tile) | {s.tile for s in civ.settlements}
    cx, cy = world.xy(civ.capital.tile)
    resource = bdef.placement.partition(":")[2]
    best, best_score = None, -math.inf
    for tile in sorted(civ.territory):
        if placement_problem(civ, world, bdef, tile, on_tile=on_tile):
            continue
        x, y = world.xy(tile)
        distance = math.hypot(x - cx, y - cy)
        if resource:
            tile_yield = world.yields[tile].get(resource, 0)
            if tile_yield <= 0:
                continue
            score = 2 * tile_yield - 0.15 * distance + (FILL_FIRST_YIELD if tile in settled else 0.0)
        else:
            score = -distance + (FILL_FIRST if tile in settled else 0.0)
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
    active = [b for b in civ.buildings if not b.complete][: mods.build_slots]
    for building in active:
        if building.id not in staffed:
            continue
        bdef = building_defs[building.type]
        building.progress += (1 + mods.build_speed) / bdef.build_time
        if building.progress >= 1:
            building.progress = 1.0
            building.complete = True
            events.append({"civ": civ.id, "kind": "building", "text": f"{civ.name} built a {bdef.name}"})
