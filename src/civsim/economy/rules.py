"""Economy constants. All rates are per tick."""

RESOURCES = ("food", "wood", "stone", "ore", "gold")

WORK_RATE = 0.2  # output of one worker in one work slot
FOOD_PER_POP = 0.08
TAX_PER_POP = 0.004  # gold
SCIENCE_PER_POP = 0.015

GROWTH_RATE = 0.01
STARVE_RATE = 0.01
MIN_POPULATION = 5.0

BASE_HOUSING = 30.0
BASE_STORAGE = 250.0

# Work slots a settlement provides regardless of the surrounding land.
SETTLEMENT_YIELDS = {"food": 4, "wood": 3, "stone": 2, "ore": 0, "gold": 1}

START_POPULATION = 20.0
START_RESOURCES = {"food": 100.0, "wood": 60.0, "stone": 20.0, "ore": 0.0, "gold": 10.0}
START_TERRITORY_RADIUS = 2.5
