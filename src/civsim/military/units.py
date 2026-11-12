"""Army unit types, loaded from data/units.json. No dependencies on the rest of the sim."""

from dataclasses import dataclass

from ..datafiles import load_json

COUNTER_BONUS = 0.25
# Troop tiers: research lets a civ equip its soldiers better. A tier-4 soldier is worth nearly
# two of tier 1, and costs half as much again to arm.
MAX_TIER = 4
TIER_STRENGTH = (1.0, 1.25, 1.55, 1.9)
TIER_COST = (1.0, 1.15, 1.3, 1.5)


def _at_tier(table: tuple[float, ...], tier: float) -> float:
    """The table's value at a tier, which for a mixed body of troops lies between two whole ones."""
    tier = max(1.0, min(float(MAX_TIER), tier))
    low = int(tier) - 1
    if low >= MAX_TIER - 1:
        return table[-1]
    return table[low] + (table[low + 1] - table[low]) * (tier - 1 - low)


def tier_strength(tier: float) -> float:
    return _at_tier(TIER_STRENGTH, tier)


def tier_cost(tier: float) -> float:
    return _at_tier(TIER_COST, tier)


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
