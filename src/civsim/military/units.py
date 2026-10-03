"""Army unit types, loaded from data/units.json. No dependencies on the rest of the sim."""

from dataclasses import dataclass

from ..datafiles import load_json

COUNTER_BONUS = 0.25


@dataclass(frozen=True)
class UnitType:
    id: str
    name: str
    strength: float  # relative to the base soldier
    speed: float  # tiles per tick over open ground
    requires: tuple[str, ...]  # techs
    upkeep: dict[str, float]  # gold and ore: multiples of the base soldier upkeep; wood: per soldier per tick
    counters: tuple[str, ...]
    share: float  # weight in the mix a civ recruits toward


def load_unit_types() -> dict[str, UnitType]:
    raw = load_json("units.json")
    return {
        unit_id: UnitType(id=unit_id, name=entry["name"], strength=entry["strength"], speed=entry["speed"],
                          requires=tuple(entry["requires"]), upkeep=entry["upkeep"],
                          counters=tuple(entry["counters"]), share=entry["share"])
        for unit_id, entry in raw.items() if not unit_id.startswith("_")
    }


UNIT_TYPES = load_unit_types()
BASE_UNIT = "spearman"  # what soldiers are when nothing better is known


def unit_strength(units: dict[str, float], enemy: dict[str, float] | None = None) -> float:
    """Strength of a body of troops before quality and leadership: each unit counts for its
    type's strength, plus the counter bonus in proportion to how much of the enemy it counters."""
    enemy_total = sum(enemy.values()) if enemy else 0.0
    total = 0.0
    for unit_id, count in units.items():
        unit = UNIT_TYPES[unit_id]
        edge = 0.0
        if enemy_total > 0:
            edge = COUNTER_BONUS * sum(enemy.get(target, 0.0) for target in unit.counters) / enemy_total
        total += count * unit.strength * (1 + edge)
    return total


def upkeep_per_soldier(units: dict[str, float]) -> dict[str, float]:
    """Average upkeep factors of a mix: gold and ore multipliers, wood per soldier."""
    total = sum(units.values())
    if total <= 0:
        return dict(UNIT_TYPES[BASE_UNIT].upkeep)
    return {res: sum(count * UNIT_TYPES[unit_id].upkeep[res] for unit_id, count in units.items()) / total
            for res in ("gold", "ore", "wood")}
