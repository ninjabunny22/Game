from ..map import WorldMap
from .modifiers import Modifiers
from .rules import (
    FOOD_PER_POP,
    GROWTH_RATE,
    MIN_POPULATION,
    RESOURCES,
    SCIENCE_PER_POP,
    SETTLEMENT_YIELDS,
    STARVE_RATE,
    TAX_PER_POP,
    WORK_RATE,
)


def recompute_capacity(civ, world: WorldMap) -> None:
    """Work slots per resource available in the civ's territory."""
    capacity = {res: float(SETTLEMENT_YIELDS[res] * len(civ.settlements)) for res in RESOURCES}
    for tile in civ.territory:
        for res, amount in world.yields[tile].items():
            capacity[res] += amount
    civ.capacity = capacity


def produce(civ, mods: Modifiers) -> None:
    """Gather with the current worker allocation, then feed and grow the population."""
    before = dict(civ.resources)
    for res in RESOURCES:
        workers = min(civ.workers[res], civ.capacity[res])
        output = WORK_RATE * workers * (1 + mods.yield_mult[res]) + mods.income[res]
        if res == "gold":
            output += TAX_PER_POP * civ.population
        civ.resources[res] = min(mods.storage, civ.resources[res] + output)

    upkeep = civ.population * FOOD_PER_POP
    if civ.resources["food"] >= upkeep:
        civ.resources["food"] -= upkeep
        if civ.population < mods.housing:
            crowding = 1 - civ.population / mods.housing
            growth = max(0.02, GROWTH_RATE * civ.population * crowding) * (1 + mods.growth)
            civ.population = min(mods.housing, civ.population + growth)
    else:
        civ.resources["food"] = 0.0
        civ.population = max(MIN_POPULATION, civ.population * (1 - STARVE_RATE))

    civ.science_rate = (SCIENCE_PER_POP * civ.population + mods.science) * (1 + mods.science_mult)
    civ.science += civ.science_rate
    civ.income = {res: civ.resources[res] - before[res] for res in RESOURCES}
