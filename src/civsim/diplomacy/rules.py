"""Diplomacy, trade and war constants. Rates are per tick. Diplomatic actions are paid for in
diplomacy points, which every civ earns automatically and cannot trade."""

from ..map import Biome

# Diplomacy points
DIPLOMACY_GAIN = 1.0  # earned by every civ every tick
DIPLOMACY_CAP = 300.0  # so influence cannot be hoarded for a string of wars
DIPLOMACY_START = 50.0

# Trade
DEAL_DURATION = 100
DEAL_FEE = 20  # diplomacy points, paid by each side when a deal opens; allies trade free
MIN_RATE = 0.05
MAX_RATE = 2.0
SUSTAIN_TICKS = 50  # a side never promises more per tick than stock / this
SURPLUS_FILL = 0.9  # a side refuses a resource it already holds this share of storage of
DEAL_MISS_LIMIT = 10  # consecutive short deliveries before a deal is cancelled

# Alliance
ALLIANCE_COST = 50  # diplomacy points, each
ALLIANCE_UPKEEP = 0.2  # diplomacy points per tick, each
ALLY_DEFENSE = 0.15
ALLY_SCIENCE = 0.1
EVEN_SPLIT_BAND = 0.05  # allies whose shares of the spoils are all this close to equal split evenly

# Betrayal: breaking an alliance by aggression and attacking that former ally soon after.
BETRAYAL_WINDOW = 50  # ticks between the break and the declaration for it to count
SURPRISE_TICKS = 10  # opening ticks in which the betrayed civ has no home bonus and no militia ...
SURPRISE_CAPTURE = 1.5  # ... and the betrayer takes tiles this much faster
DISTRUST_TICKS = 50  # how long other civs hold a betrayal against the betrayer
DISTRUST_FEE_FACTOR = 4  # a distrusted civ pays this many times the usual fee to open a deal
DISTRUST_RATE_FACTOR = 0.5  # and is sent only this share of what its partner offered

# War
WAR_COST = 100  # diplomacy points: about two check-ins' worth
REACH = 4  # max gap, in tiles, across which two territories can fight
MIN_WAR = 50  # ticks before a war can end by mutual consent
MAX_WAR = 400  # ticks after which both sides are exhausted
TRUCE = 100
SURRENDER_TRUCE = 300
TRIBUTE = 0.5  # share of the loser's stock taken on surrender
MUSTER = 0.3  # share of full mobilisation raised while a war is only threatened

# Regions and the native faction
CAPITAL_DEFENSE = 3.0  # a region capital costs this many times its terrain to capture
NATIVE_GARRISON = 6.0  # defenders of a neutral capital at the start, in soldier-equivalents ...
NATIVE_GROWTH = 0.012  # ... growing by this much per tick ...
NATIVE_GARRISON_MAX = 60.0  # ... up to this: weaker than a civ's army at any stage, but never trivial
NATIVE_RECOVERY = 0.02  # share of its losses a garrison makes good per tick when left alone
DEFECTION_INTERVAL = 25  # ticks between checks for natives going over to a civ
TILE_DEFECTION_SHARE = 0.3  # share of a region a civ must hold before its neighbours start to defect
TILE_DEFECTION_RATE = 0.5  # chance per check for each bordering tile, per unit of share above that
CAPITAL_DEFECTION_SHARE = 0.6  # share above which the capital itself may join; chance = share - this

# Combat
HOME_BONUS = 0.25  # defenders fight better on their own land
MILITIA = 0.03  # share of a defender's population that fights as irregulars
CAPTURE_RATE = 0.5  # tiles of progress per tick at overwhelming superiority
CASUALTY_RATE = 0.01  # share of the engaged troops lost per tick in an even fight
TILE_DEFENSE = {Biome.SHALLOWS: 0.5, Biome.FOREST: 1.5, Biome.HILLS: 2.0, Biome.MOUNTAIN: 3.0}  # default 1
