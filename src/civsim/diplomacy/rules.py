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
ALLY_TRADE_BONUS = 0.15  # extra goods delivered, over what was sent, on a deal between allies
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
# There is no minimum army for declaring war: the strategist judges when it can win. What it
# must keep at home is the home guard: enough to hold off the strongest other civ in reach.
HOME_GUARD = 0.6  # ... as a share of that civ's strength (defenders fight on their own ground)
REACH = 4  # max gap, in tiles, across which two territories can fight
MIN_WAR = 50  # ticks before a war can end by mutual consent
MAX_WAR = 400  # ticks after which both sides are exhausted
TRUCE = 50
SURRENDER_TRUCE = 150
TRIBUTE = 0.5  # share of the loser's stock taken on surrender
# Sickness: a long war wears a people down, and sooner or later something breaks out in the camps.
SICKNESS_AFTER = 250  # ticks a civ must have been at war before an outbreak is possible
SICKNESS_CHECK = 25  # ticks between rolls
SICKNESS_CHANCE = 0.05  # per roll at SICKNESS_AFTER, doubling with every further SICKNESS_AFTER ticks of war
SICKNESS_TICKS = 150  # how long it lasts
SICKNESS_REST = 400  # ticks after it ends before another can start
SICKNESS_DEATHS = 0.08  # share of the population lost at the outbreak
SICKNESS_MILITARY = -0.25  # while it lasts: weaker soldiers ...
SICKNESS_GROWTH = -0.6  # ... slower growth ...
SICKNESS_YIELD = -0.1  # ... and less of everything from the land
SICKNESSES = ("camp fever", "the flux", "the sweating sickness", "a plague", "the pox")

# Friction: neighbours rub each other up the wrong way. What a civ holds against another grows
# with the border they share, and with wanting the same native land.
FRICTION_INTERVAL = 25  # ticks between reckonings
BORDER_FRICTION = 0.04  # held against each other per reckoning along a long shared border ...
LONG_BORDER = 20  # ... which is this many tiles; a shorter one counts in proportion
RIVAL_FRICTION = 0.03  # held against each other per reckoning by two civs after the same region
BEATEN_TO_IT = 0.6  # held against whoever takes a native region by the others who were after it

# Rivalry: the two strongest civs are each the only thing between the other and first place,
# and come to resent each other for it. Who they are is reckoned afresh every time.
RIVALRY = 0.06  # held against each other per reckoning by the strongest and the second strongest

# Demands: a civ strong enough may ask for tribute before it attacks. Paying buys a truce.
DEMAND_TRIBUTE = 0.15  # share of its stock a civ hands over to be left alone
DEMAND_TRUCE = 150  # ticks of truce that buys
DEMAND_LAPSE = 60  # ticks after which an unanswered demand is forgotten

# What a war teaches: a civ beaten by another wants a bigger edge before it tries again, and
# one that won grows bolder. Kept per pair, on the scale of the edge itself.
LESSON_LOST = 0.2
LESSON_WON = -0.1
CAUTION_RANGE = (-0.2, 0.6)
HELP_CAME = 0.6  # what a civ at war thinks of an ally who joins it ...
HELP_STAYED_AWAY = -0.3  # ... and of one who never did, once the war is over
HELP_WAR = 100  # ticks a war must have lasted for staying out of it to be held against an ally

# Ceding land: a side far ahead takes a whole region rather than tribute when peace is made.
CEDE_LEAD = 2  # castles taken, more than the other side

# Peace on terms: a side well ahead in a war is paid tribute when it ends, and will accept an
# offer of it once its own advance has stalled.
PEACE_LEAD = 1  # castles taken, more than the other side, to count as ahead
PEACE_TRIBUTE = 0.25  # share of the loser's stock handed over
TERMS_AFTER = 150  # ticks of war before an offer of tribute is listened to
STALL_TICKS = 80  # ... and only when the winner has taken nothing for this long
MUSTER = 0.3  # share of full mobilisation raised while a war is only threatened

# Regions and the native faction
CAPITAL_DEFENSE = 3.0  # a region capital costs this many times its terrain to capture
CAPITAL_HOLD = 100  # ticks an army that has broken into a civ's capital must hold it before the region falls
NATIVE_GARRISON = 6.0  # defenders of a neutral capital at the start, in soldier-equivalents ...
NATIVE_GROWTH = 0.012  # ... growing by this much per tick ...
NATIVE_GARRISON_MAX = 60.0  # ... up to this: weaker than a civ's army at any stage, but never trivial
NATIVE_RECOVERY = 0.02  # share of its losses a garrison makes good per tick when left alone

# Combat
HOME_BONUS = 0.25  # defenders fight better on their own land
MILITIA = 0.03  # share of a defender's population that fights as irregulars
CAPTURE_RATE = 0.5  # tiles of progress per tick at overwhelming superiority
CASUALTY_RATE = 0.01  # share of the engaged troops lost per tick in an even fight
TILE_DEFENSE = {Biome.SHALLOWS: 0.5, Biome.FOREST: 1.5, Biome.HILLS: 2.0, Biome.MOUNTAIN: 3.0}  # default 1
MEMORY_FADE = 0.9985  # per tick: what a civ holds for or against another halves in about 460 days
