"""Diplomacy, trade and war constants. Rates are per tick, costs are in gold."""

from ..map import Biome

# Trade
DEAL_DURATION = 100
DEAL_FEE = 15  # paid by each side when a deal opens; allies trade free
MIN_RATE = 0.05
MAX_RATE = 2.0
SUSTAIN_TICKS = 50  # a side never promises more per tick than stock / this
SURPLUS_FILL = 0.9  # a side refuses a resource it already holds this share of storage of
DEAL_MISS_LIMIT = 10  # consecutive short deliveries before a deal is cancelled

# Alliance
ALLIANCE_COST = 40
ALLIANCE_UPKEEP = 0.1
ALLY_DEFENSE = 0.15
ALLY_SCIENCE = 0.1

# War
WAR_COST = 50
REACH = 4  # max gap, in tiles, across which two territories can fight
MIN_WAR = 50  # ticks before a war can end by mutual consent
MAX_WAR = 400  # ticks after which both sides are exhausted
TRUCE = 100
SURRENDER_TRUCE = 300
TRIBUTE = 0.5  # share of the loser's stock taken on surrender
MUSTER = 0.3  # share of full mobilisation raised while a war is only threatened

# Combat
HOME_BONUS = 0.25  # defenders fight better on their own land
MILITIA = 0.03  # share of a defender's population that fights as irregulars
COUNTER_ATTACK = 0.4  # offensive strength of a side that is only defending
CAPTURE_RATE = 0.5  # tiles of progress per tick at overwhelming superiority
CASUALTY_RATE = 0.01  # share of the engaged troops lost per tick in an even fight
TILE_DEFENSE = {Biome.SHALLOWS: 0.5, Biome.FOREST: 1.5, Biome.HILLS: 2.0, Biome.MOUNTAIN: 3.0}  # default 1
