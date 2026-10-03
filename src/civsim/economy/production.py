from ..map import WorldMap
from .modifiers import Modifiers
from .rules import (
    DESERTION_RATE,
    CONSUMPTION_PER_TECH,
    FOOD_PER_POP,
    GROWTH_RATE,
    MIN_POPULATION,
    RECRUIT_RATE,
    RESOURCES,
    SCIENCE_PER_POP,
    SETTLEMENT_YIELDS,
    SOLDIER_FOOD,
    SOLDIER_GOLD,
    SOLDIER_ORE,
    STARVE_RATE,
    TAX_PER_POP,
    WOOD_PER_POP,
    WORK_RATE,
)


def recompute_capacity(civ, world: WorldMap) -> None:
    """Work slots per resource available in the civ's territory."""
    capacity = {res: float(SETTLEMENT_YIELDS[res] * len(civ.settlements)) for res in RESOURCES}
    for tile in civ.territory:
        for res, amount in world.yields[tile].items():
            capacity[res] += amount
    civ.capacity = capacity


def food_need(civ) -> float:
    """Food eaten per tick. More advanced societies eat more per head; soldiers eat extra."""
    return civ.population * FOOD_PER_POP * _living_standard(civ) + civ.soldiers * SOLDIER_FOOD


def _living_standard(civ) -> float:
    return 1 + CONSUMPTION_PER_TECH * len(civ.known_techs)


def produce(civ, mods: Modifiers, building_defs) -> None:
    """Gather with the current worker allocation, pay upkeep, then feed and grow the population."""
    before = dict(civ.resources)
    for res in RESOURCES:
        workers = min(civ.workers[res], civ.capacity[res])
        output = WORK_RATE * workers * (1 + mods.yield_mult[res]) + mods.income[res]
        if res == "gold":
            output += TAX_PER_POP * civ.population
        # Never produce past the cap. Stock already above it (captured stores) is left alone.
        civ.resources[res] = max(civ.resources[res], min(mods.storage[res], civ.resources[res] + output))

    upkeep = dict.fromkeys(RESOURCES, 0.0)

    # Buildings whose upkeep cannot be paid stop working until it can.
    for building in civ.buildings:
        if not building.complete:
            continue
        cost = building_defs[building.type].upkeep
        for res, amount in cost.items():
            upkeep[res] += amount
        building.active = civ.can_afford(cost)
        if building.active:
            civ.pay(cost)
            building.unpaid_ticks = 0
        else:
            building.unpaid_ticks += 1

    fuel = WOOD_PER_POP * civ.population * _living_standard(civ)
    warm = _charge(civ, upkeep, "wood", fuel)

    _maintain_army(civ, upkeep)

    food = food_need(civ)
    fed = _charge(civ, upkeep, "food", food)
    if not fed:
        civ.population = max(MIN_POPULATION, civ.population * (1 - STARVE_RATE))
    elif warm and civ.population < mods.housing:
        crowding = 1 - civ.population / mods.housing
        growth = max(0.02, GROWTH_RATE * civ.population * crowding) * (1 + mods.growth)
        civ.population = min(mods.housing, civ.population + growth)
    civ.soldiers = min(civ.soldiers, civ.population)

    civ.science_rate = (SCIENCE_PER_POP * civ.population + mods.science) * (1 + mods.science_mult)
    civ.science += civ.science_rate
    civ.upkeep = upkeep
    civ.income = {res: civ.resources[res] - before[res] for res in RESOURCES}


def _maintain_army(civ, upkeep: dict[str, float]) -> None:
    """Recruit or demobilise toward the standing order, then pay and equip the soldiers."""
    target = min(civ.soldier_target, max(0.0, civ.population - MIN_POPULATION))
    step = RECRUIT_RATE * civ.population + 0.2
    civ.soldiers = max(0.0, civ.soldiers + max(-step, min(step, target - civ.soldiers)))
    civ.unpaid = not _charge(civ, upkeep, "gold", civ.soldiers * SOLDIER_GOLD)
    civ.unsupplied = not _charge(civ, upkeep, "ore", civ.soldiers * SOLDIER_ORE)
    if civ.unpaid:
        civ.soldiers *= 1 - DESERTION_RATE


def _charge(civ, upkeep: dict[str, float], res: str, amount: float) -> bool:
    """Take `amount` from stock (or whatever is left). False if there was not enough."""
    upkeep[res] += amount
    enough = civ.resources[res] >= amount
    civ.resources[res] = max(0.0, civ.resources[res] - amount)
    return enough
