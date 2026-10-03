"""Aggregates the effects of a civ's completed buildings and known techs.

Buildings and techs share one effects vocabulary (see data/*.json):
  yield_mult {res|"all": frac}, income {res: per tick}, housing, storage, science,
  science_mult, build_speed, growth, expand_cost, build_slots
"""

from dataclasses import dataclass, field

from .rules import BASE_HOUSING, BASE_STORAGE, RESOURCES


@dataclass
class Modifiers:
    yield_mult: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    income: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    housing: float = BASE_HOUSING
    storage: float = BASE_STORAGE
    science: float = 0.0
    science_mult: float = 0.0
    build_speed: float = 0.0
    growth: float = 0.0
    expand_cost: float = 0.0
    build_slots: int = 1

    def apply(self, effects: dict) -> None:
        for key, value in effects.items():
            if key == "yield_mult":
                for res, amount in value.items():
                    for target in RESOURCES if res == "all" else (res,):
                        self.yield_mult[target] += amount
            elif key == "income":
                for res, amount in value.items():
                    self.income[res] += amount
            else:
                setattr(self, key, getattr(self, key) + value)


def compute_modifiers(civ, building_defs, tech_tree) -> Modifiers:
    mods = Modifiers()
    for building in civ.buildings:
        if building.complete:
            mods.apply(building_defs[building.type].effects)
    for tech_id in civ.known_techs:
        mods.apply(tech_tree.techs[tech_id].effects)
    return mods
