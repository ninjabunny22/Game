import math
from dataclasses import dataclass, field

from ..datafiles import load_json
from ..map import BIOME_INFO, WorldMap

COST_GROWTH_PER_COPY = 0.2


@dataclass(frozen=True)
class BuildingDef:
    id: str
    name: str
    category: str  # which personality weight / need drives it
    placement: str  # "center" or "yield:<resource>"
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


def find_site(civ, world: WorldMap, bdef: BuildingDef) -> int | None:
    """Best free buildable tile in the civ's territory for this building, or None."""
    occupied = civ.occupied()
    cx, cy = world.xy(civ.capital.tile)
    resource = bdef.placement.partition(":")[2]
    best, best_score = None, -math.inf
    for tile in sorted(civ.territory):
        if tile in occupied or not BIOME_INFO[world.biomes[tile]].buildable:
            continue
        x, y = world.xy(tile)
        distance = math.hypot(x - cx, y - cy)
        if resource:
            tile_yield = world.yields[tile].get(resource, 0)
            if tile_yield <= 0:
                continue
            score = 2 * tile_yield - 0.15 * distance
        else:
            score = -distance
        if score > best_score:
            best, best_score = tile, score
    return best


def demolish(civ, building, mods, building_defs, events: list) -> None:
    """Tear down one of the civ's own buildings, freeing its tile and recovering some materials.

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
    active = [b for b in civ.buildings if not b.complete][: mods.build_slots]
    for building in active:
        bdef = building_defs[building.type]
        building.progress += (1 + mods.build_speed) / bdef.build_time
        if building.progress >= 1:
            building.progress = 1.0
            building.complete = True
            events.append({"civ": civ.id, "kind": "building", "text": f"{civ.name} built a {bdef.name}"})
