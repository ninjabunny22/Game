"""Aggregates the effects of a civ's completed buildings and known techs.

Buildings and techs share one effects vocabulary (see data/*.json):
  yield_mult {res|"all": frac}, income {res: per tick}, housing, science,
  storage (cap of every resource), store {res: cap of that resource only},
  science_mult, build_speed, growth, expand_cost, build_slots, demolition_refund,
  military (army strength), defense (strength when holding own land),
  purification (water per owned coast tile), water_mult, water_use, bridges, boats,
  boat_range, commander_xp, commander_start, capture_speed, casualties, mobilization,
  home_speed, reinforce, villager_speed, deal_fee
"""

from dataclasses import dataclass, field

from .rules import (
    BASE_HOUSING,
    BASE_STORAGE,
    DEMOLITION_REFUND,
    LAKE_WATER,
    RESOURCES,
    RIVER_WATER,
    WATER_CAP_PER_SOURCE,
    WELL_WATER,
)


@dataclass
class Modifiers:
    yield_mult: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    income: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    housing: float = BASE_HOUSING
    # Hard cap on the stock of each resource: a base amount plus storage buildings.
    storage: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, BASE_STORAGE))
    science: float = 0.0
    science_mult: float = 0.0
    build_speed: float = 0.0
    growth: float = 0.0
    expand_cost: float = 0.0
    build_slots: int = 1
    military: float = 0.0
    defense: float = 0.0
    demolition_refund: float = DEMOLITION_REFUND  # share of base cost recovered when demolishing
    purification: float = 0.0  # water drawn per tick from each owned coast tile
    water_mult: float = 0.0
    bridges: int = 0  # > 0: rivers cost nothing extra to cross
    boats: int = 0  # > 0: lakes and deep sea can be crossed
    boat_range: int = 0  # extra tiles of open water boats can cross
    water_use: float = 0.0  # change to what each person drinks (negative = less)
    commander_xp: float = 0.0  # extra experience commanders gain, as a fraction
    commander_start: int = 0  # levels above 1 that new commanders start at
    capture_speed: float = 0.0  # extra speed at which armies take enemy tiles
    casualties: float = 0.0  # change to battle losses (negative = fewer)
    mobilization: float = 0.0  # added to the share of the population that can be under arms
    home_speed: float = 0.0  # extra army movement per tick on the civ's own land
    reinforce: float = 0.0  # extra speed at which soldiers reach armies in the field
    villager_speed: int = 0  # extra tiles a villager walks per tick
    deal_fee: float = 0.0  # change to the cost of opening a trade deal (negative = cheaper)

    def apply(self, effects: dict) -> None:
        for key, value in effects.items():
            if key == "yield_mult":
                for res, amount in value.items():
                    for target in RESOURCES if res == "all" else (res,):
                        self.yield_mult[target] += amount
            elif key == "income":
                for res, amount in value.items():
                    self.income[res] += amount
            elif key == "store":
                for res, amount in value.items():
                    self.storage[res] += amount
            elif key == "storage":
                for res in RESOURCES:
                    self.storage[res] += value
            else:
                setattr(self, key, getattr(self, key) + value)


def compute_modifiers(civ, building_defs, tech_tree) -> Modifiers:
    mods = Modifiers()
    for building in civ.buildings:
        if building.complete and building.active:
            mods.apply(building_defs[building.type].effects)
    for tech_id in civ.known_techs:
        mods.apply(tech_tree.techs[tech_id].effects)
    _apply_water_access(civ, mods)
    return mods


def _apply_water_access(civ, mods: Modifiers) -> None:
    """Water supply and cap follow what the territory actually gives access to."""
    access = civ.water_access
    coast = access["coast"] if mods.purification > 0 else 0
    inflow = WELL_WATER + RIVER_WATER * access["river"] + LAKE_WATER * access["lake"] + mods.purification * coast
    mods.income["water"] += inflow * (1 + mods.water_mult)
    mods.storage["water"] += WATER_CAP_PER_SOURCE * (access["river"] + access["lake"] + coast)
