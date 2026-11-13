from ..map import Biome, WorldMap
from ..military.units import tier_cost, upkeep_per_soldier
from .modifiers import Modifiers
from .rules import (
    DESERTION_RATE,
    HORSE_FOOD,
    HORSE_WATER,
    MOUNTED_WORKERS,
    CONSUMPTION_PER_TECH,
    FOOD_PER_POP,
    EARLY_GROWTH,
    EARLY_GROWTH_FADE,
    EARLY_GROWTH_UNTIL,
    GROWTH_RATE,
    MIN_POPULATION,
    ARMS_BOUGHT,
    RECRUIT_GOLD,
    RECRUIT_ORE,
    RECRUIT_RATE,
    TRAIN_LEVY,
    TRAIN_LEVY_PER_POP,
    TRAIN_PER_BARRACKS,
    RESOURCES,
    SCIENCE_PER_POP,
    SETTLEMENT_YIELDS,
    SOLDIER_FOOD,
    SOLDIER_GOLD,
    SOLDIER_ORE,
    STARVE_RATE,
    THIRST_RATE,
    WATER_GROWTH_MARGIN,
    WATER_PER_POP,
    WATER_RESERVE_TICKS,
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

    lakes = {n for tile in civ.territory for n in world.neighbors(tile) if world.biomes[n] == Biome.LAKE}
    civ.water_access = {
        "river": sum(world.rivers.get(tile, 0) for tile in civ.territory),
        "lake": len(lakes),
        "coast": sum(1 for tile in civ.territory if world.biomes[tile] == Biome.SHALLOWS),
    }


def food_need(civ) -> float:
    """Food eaten per tick. More advanced societies eat more per head; soldiers eat extra, and so do horses."""
    return (civ.population * FOOD_PER_POP * _living_standard(civ) + civ.soldiers * SOLDIER_FOOD
            + civ.herd * HORSE_FOOD)


def _living_standard(civ) -> float:
    return 1 + CONSUMPTION_PER_TECH * len(civ.known_techs)


def water_balance(civ, mods: Modifiers) -> tuple[float, float]:
    """(supply, use) of water per tick, counting trade deals on both sides."""
    return mods.income["water"] + civ.imports["water"], civ.upkeep["water"] + civ.exports["water"]


def water_growth_factor(civ, mods: Modifiers) -> float:
    """How freely the population may grow given its water: 1 with a comfortable margin,
    falling to 0 as use catches up with supply, so growth eases off before the wells run dry."""
    supply, use = water_balance(civ, mods)
    if supply <= 0:
        return 0.0
    headroom = (supply - use) / supply
    return max(0.0, min(1.0, headroom / WATER_GROWTH_MARGIN))


def water_urgency(civ, mods: Modifiers) -> float:
    """How pressing water is for this civ, 0 (comfortable) to 1 (dry or about to be).

    Up to 0.5 while supply still covers use but the margin is thin; above that
    once the civ is living off its stores, rising as they run down.
    """
    supply, use = water_balance(civ, mods)
    tightness = 1 - water_growth_factor(civ, mods)
    if use <= supply:
        return 0.5 * tightness
    ticks_left = civ.resources["water"] / (use - supply)
    return 0.5 + 0.5 * max(0.0, min(1.0, 1 - ticks_left / WATER_RESERVE_TICKS))


def early_growth(tick: int | None) -> float:
    """How much faster a young civ grows: the full bonus at first, fading away to nothing."""
    if tick is None:
        return 0.0
    return EARLY_GROWTH * max(0.0, min(1.0, (EARLY_GROWTH_UNTIL + EARLY_GROWTH_FADE - tick) / EARLY_GROWTH_FADE))


def soldier_cost(mods: Modifiers) -> float:
    """What a soldier costs to arm and to pay, as a share of the usual: research lowers it."""
    return max(0.3, 1 + mods.soldier_cost)


def produce(civ, mods: Modifiers, building_defs, tick: int | None = None) -> None:
    """Gather with the current worker allocation, pay upkeep, then feed and grow the population."""
    before = dict(civ.resources)
    # A mounted villager at work on the land does the work of several.
    riders = dict.fromkeys(RESOURCES, 0)
    for villager in civ.villagers:
        if villager.mounted and villager.task == "gather" and villager.tile == villager.target and villager.gathers:
            riders[villager.gathers] += 1
    for res in RESOURCES:
        workers = min(civ.workers[res], civ.capacity[res]) + MOUNTED_WORKERS * riders[res]
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

    _maintain_army(civ, upkeep, mods)

    # Thirst: the population shrinks slowly, in proportion to how much water is missing.
    thirst = WATER_PER_POP * civ.population * max(0.2, 1 + mods.water_use) + civ.herd * HORSE_WATER
    available = civ.resources["water"]
    civ.thirsty = not _charge(civ, upkeep, "water", thirst)
    if civ.thirsty:
        shortfall = 1 - available / thirst
        civ.population = max(MIN_POPULATION, civ.population * (1 - THIRST_RATE * shortfall))

    food = food_need(civ)
    fed = _charge(civ, upkeep, "food", food)
    if not fed:
        civ.population = max(MIN_POPULATION, civ.population * (1 - STARVE_RATE))
    elif warm and not civ.thirsty and civ.population < mods.housing:
        crowding = 1 - civ.population / mods.housing
        growth = max(0.02, GROWTH_RATE * civ.population * crowding) * (1 + mods.growth + early_growth(tick))
        # No growing blindly into a drought: growth eases off as water use nears supply.
        growth *= water_growth_factor(civ, mods)
        civ.population = min(mods.housing, civ.population + growth)
    civ.soldiers = min(civ.soldiers, civ.population)

    civ.science_rate = (SCIENCE_PER_POP * civ.population + mods.science) * (1 + mods.science_mult)
    civ.science += civ.science_rate
    civ.upkeep = upkeep
    civ.income = {res: civ.resources[res] - before[res] for res in RESOURCES}


def training_rate(civ) -> float:
    """Soldiers the civ can train per tick: a levy that grows with its people, and its barracks."""
    barracks = sum(b.level for b in civ.buildings if b.type == "barracks" and b.complete and b.active)
    return TRAIN_LEVY + TRAIN_LEVY_PER_POP * civ.population + TRAIN_PER_BARRACKS * barracks


def _maintain_army(civ, upkeep: dict[str, float], mods: Modifiers) -> None:
    """Recruit or demobilise toward the standing order, then pay and equip the soldiers."""
    target = min(civ.soldier_target, max(0.0, civ.population - MIN_POPULATION - civ.wounded))
    factors = upkeep_per_soldier(civ.unit_counts())
    cheaper = soldier_cost(mods)
    change = max(-(RECRUIT_RATE * civ.population + 0.2), target - civ.soldiers)
    if change > 0:
        # The wounded in hospital will be back in the ranks: nobody is trained to replace them.
        change = max(0.0, change - civ.wounded)
        # Soldiers are trained and armed: only so many a day, and only those that can be paid for.
        change = 0.0 if civ.unpaid else min(change, training_rate(civ))  # nobody enlists in an unpaid army
        # Better arms cost more; research into supply makes every soldier cheaper.
        arms = cheaper * tier_cost(mods.tier)
        gold, ore = arms * RECRUIT_GOLD * factors["gold"], arms * RECRUIT_ORE * factors["ore"]
        if civ.resources["ore"] < change * ore:
            gold, ore = gold + ARMS_BOUGHT * ore, 0.0  # no ore of its own: the arms are bought in, dearly
        change = max(0.0, min(change, civ.resources["gold"] / gold if gold > 0 else change))
        civ.resources["gold"] -= change * gold
        civ.resources["ore"] -= change * ore
    civ.soldiers = max(0.0, civ.soldiers + change)
    # What the army costs depends on what it is made of: swordsmen need ore, archers wood, cavalry gold.
    civ.unpaid = not _charge(civ, upkeep, "gold", civ.soldiers * cheaper * SOLDIER_GOLD * factors["gold"])
    civ.unsupplied = not _charge(civ, upkeep, "ore", civ.soldiers * cheaper * SOLDIER_ORE * factors["ore"])
    _charge(civ, upkeep, "wood", civ.soldiers * factors["wood"])
    if civ.unpaid:
        civ.soldiers *= 1 - DESERTION_RATE


def _charge(civ, upkeep: dict[str, float], res: str, amount: float) -> bool:
    """Take `amount` from stock (or whatever is left). False if there was not enough."""
    upkeep[res] += amount
    enough = civ.resources[res] >= amount
    civ.resources[res] = max(0.0, civ.resources[res] - amount)
    return enough
