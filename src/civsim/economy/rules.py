"""Economy constants. All rates are per tick."""

RESOURCES = ("food", "wood", "stone", "ore", "gold")

WORK_RATE = 0.2  # output of one worker in one work slot
FOOD_PER_POP = 0.08
WOOD_PER_POP = 0.01  # fuel; without it the population stops growing
CONSUMPTION_PER_TECH = 0.04  # each known tech raises per-person food and fuel consumption by this fraction
TAX_PER_POP = 0.004  # gold
SCIENCE_PER_POP = 0.015
SCIENCE_BANK_CAP = 500.0  # most science a civ can hold while it has nothing to spend it on

# Army. Soldiers are part of the population but do not work.
GARRISON = 0.02  # peacetime share of the population under arms
MAX_MOBILIZATION = 0.35
RECRUIT_RATE = 0.01  # share of the population that can join or leave the army per tick
SOLDIER_FOOD = 0.04  # on top of what they eat as population
SOLDIER_GOLD = 0.02
SOLDIER_ORE = 0.005
UNPAID_QUALITY = 0.5
UNSUPPLIED_QUALITY = 0.6
DESERTION_RATE = 0.03  # of the army per tick while unpaid

GROWTH_RATE = 0.01
STARVE_RATE = 0.01
MIN_POPULATION = 5.0

BASE_HOUSING = 30.0
DEMOLITION_REFUND = 0.10  # share of a building's base cost recovered on demolition, before techs
BASE_STORAGE = 250.0

# Work slots a settlement provides regardless of the surrounding land.
SETTLEMENT_YIELDS = {"food": 4, "wood": 3, "stone": 2, "ore": 0, "gold": 1}

START_POPULATION = 20.0
START_RESOURCES = {"food": 100.0, "wood": 60.0, "stone": 20.0, "ore": 0.0, "gold": 10.0}
START_TERRITORY_RADIUS = 2.5
