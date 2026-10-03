"""Economy constants. All rates are per tick."""

RESOURCES = ("food", "wood", "stone", "ore", "gold", "water")

WORK_RATE = 0.2  # output of one worker in one work slot
FOOD_PER_POP = 0.08
WOOD_PER_POP = 0.01  # fuel; without it the population stops growing
CONSUMPTION_PER_TECH = 0.04  # each known tech raises per-person food and fuel consumption by this fraction
TAX_PER_POP = 0.004  # gold

# Water is not gathered by workers: it flows in from what the territory gives access to.
WATER_PER_POP = 0.03
THIRST_RATE = 0.004  # share of the population lost per tick when there is no water at all
WATER_GROWTH_MARGIN = 0.25  # growth slows once spare supply falls below this share of supply, and stops at none
WATER_RESERVE_TICKS = 400  # a deficit is urgent in proportion to how far inside this the stores will run dry
WELL_WATER = 0.8  # every capital has a well
RIVER_WATER = 0.12  # per point of river size on owned tiles
LAKE_WATER = 0.3  # per lake tile on the civ's shore
WATER_CAP_PER_SOURCE = 10  # each river point, lake tile or purifying coast tile also adds to the cap
SCIENCE_PER_POP = 0.015
SCIENCE_BANK_CAP = 500.0  # most science a civ can hold while it has nothing to spend it on

# Army. Soldiers are part of the population but do not work.
GARRISON = 0.10  # peacetime share of the population under arms
MAX_MOBILIZATION = 0.35
RECRUIT_RATE = 0.02  # share of the population that can join or leave the army per tick
SOLDIER_FOOD = 0.04  # on top of what they eat as population
SOLDIER_GOLD = 0.02
SOLDIER_ORE = 0.005
UNPAID_QUALITY = 0.5
UNSUPPLIED_QUALITY = 0.6
DESERTION_RATE = 0.03  # of the army per tick while unpaid
# Horses, bred at stables.
HORSE_BREED_TICKS = 10  # ticks for one stable to raise one horse
HERD_PER_STABLE = 8  # horses a stable can keep, counting those out under riders
HORSE_FOOD = 0.16  # per horse per tick: twice what a person eats ...
HORSE_WATER = 0.06  # ... and drinks
MOUNTED_WORKERS = 3.0  # extra workers' worth of output from a mounted villager on the land he works
MOUNTED_SHARE = 0.5  # at most this share of a civ's villagers ride
WOUND_RECOVERY = 0.01  # share of the wounded who return to ordinary life each tick

GROWTH_RATE = 0.01
STARVE_RATE = 0.01
MIN_POPULATION = 5.0

BASE_HOUSING = 30.0
DEMOLITION_REFUND = 0.10  # share of a building's base cost recovered on demolition, before techs
BASE_STORAGE = 250.0

# Work slots a settlement provides regardless of the surrounding land.
SETTLEMENT_YIELDS = {"food": 4, "wood": 3, "stone": 2, "ore": 0, "gold": 1, "water": 0}

START_POPULATION = 20.0
# Water starts full: the simulation tops it up to the civ's cap once its territory is known.
START_RESOURCES = {"food": 100.0, "wood": 60.0, "stone": 20.0, "ore": 0.0, "gold": 10.0, "water": 0.0}
