from dataclasses import dataclass, field

from ..economy.rules import RESOURCES
from ..military.army import Army, Captive, Commander, Villager
from .personality import Personality


@dataclass
class Settlement:
    name: str
    tile: int


@dataclass
class Building:
    type: str
    tile: int
    progress: float = 0.0
    complete: bool = False
    active: bool = True  # False while its upkeep goes unpaid
    unpaid_ticks: int = 0  # consecutive ticks it has been inactive
    id: int = 0  # given when the building is first seen by the simulation; a tile can hold several
    village: int | None = None  # the village or town it belongs to


@dataclass
class Goal:
    """What the civ is currently saving up for."""

    kind: str  # "build"
    target: str | None
    cost: dict[str, float]


@dataclass
class Research:
    tech_id: str
    paid: bool = False  # material cost paid; science now flows into it
    progress: float = 0.0  # science spent on it so far


@dataclass
class Civilization:
    id: int
    name: str
    color: str
    personality: Personality
    population: float
    resources: dict[str, float]
    settlements: list[Settlement] = field(default_factory=list)
    territory: set[int] = field(default_factory=set)
    alive: bool = True  # False once the civ has lost its last region capital
    buildings: list[Building] = field(default_factory=list)

    # Economy state, refreshed every tick.
    workers: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    idle: float = 0.0
    capacity: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    income: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    upkeep: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    # Fresh-water access of the territory: river size points, shore lake tiles, coast tiles.
    water_access: dict[str, int] = field(default_factory=lambda: {"river": 0, "lake": 0, "coast": 0})
    thirsty: bool = False
    goal: Goal | None = None

    # Army. Soldiers are counted in `population`.
    soldiers: float = 0.0
    unpaid: bool = False
    unsupplied: bool = False

    # The army on the map. `soldiers` is the head count; the armies say what they are and where.
    armies: list[Army] = field(default_factory=list)
    commanders: list[Commander] = field(default_factory=list)  # not currently leading an army
    villagers: list[Villager] = field(default_factory=list)
    horses: float = 0.0  # in the stables without a rider; cavalry and mounted villagers have theirs
    horse_progress: float = 0.0  # toward the next foal
    wounded: float = 0.0  # soldiers in hospital: they neither fight nor work until they are healed
    # The wounded by the day they leave hospital: [tick, soldiers by unit type, their tier].
    hospital: list[list] = field(default_factory=list)
    beds_short: int = -10_000  # the last tick wounded soldiers died for want of a bed
    hospital_deaths: float = 0.0  # ... and how many have, in all
    reinforce_order: int | None = None  # the ally a human ruler has ordered an army sent to stand with
    captives: list[Captive] = field(default_factory=list)  # enemy commanders this civ holds

    # Standing orders from the diplomacy layer, executed by the economy and the AI.
    soldier_target: float = 0.0
    military_need: float = 0.0  # 0 = at peace and unthreatened, 1 = at war
    march_target: int | None = None  # civ to take land toward, to bring it within reach
    # The capital its next harbour should face: the most valuable place it can only reach by
    # water (set by the AI before it picks a harbour's site; None: the nearest foreign capital).
    harbour_goal: int | None = None
    # Places its villagers found no way to, and for how many more days they are left alone.
    out_of_reach: dict[int, int] = field(default_factory=dict)
    campaign_muster: float = 0.0  # share of the population wanted under arms for a campaign against natives
    campaign_cooldown: int = 0  # tick before which no new campaign is launched

    # Influence: earned every tick, spent on trade deals, alliances and declarations of war.
    diplomacy_points: float = 0.0
    exports: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))  # per tick, via deals
    imports: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))

    # Strategic layer.
    thinking: bool = False  # a check-in is waiting on the strategy brain
    last_reason: str = ""

    last_demolition: int = -10_000  # tick; demolitions are rate-limited

    # The long view (see strategy/utility.py): what the civ is working toward, in words, the
    # kind of strategy that is, who it is aimed at, and what the realm concentrates on for it.
    strategy: str = ""
    strategy_kind: str = ""
    strategy_target: int | None = None
    focus: str = "balanced"
    born: Personality | None = None  # its personality before any focus tilted it
    sickness: str = ""  # the sickness a long war has brought on it, while it lasts
    sick_until: int = 0
    sick_rest: int = 0  # no new outbreak before this tick
    last_war: int = 0  # the last tick it was at war with anyone (0 = never)
    strategy_since: int = 0  # the tick it settled on its present strategy
    plan_target: int | None = None  # the civ it is preparing a war against, if any ...
    plan_since: int = 0  # ... since when ...
    plan: str = ""  # ... and what it is doing about it, in words
    last_rout: int = -10_000  # the last tick one of its armies was routed

    # Orders from a human ruler (see ruler.py); None leaves the choice to the civ's AI.
    research_order: str | None = None  # the tech to research next
    build_order: str | None = None  # the building to put up next

    known_techs: list[str] = field(default_factory=list)
    research: Research | None = None
    science: float = 0.0
    science_rate: float = 0.0

    @property
    def capital(self) -> Settlement:
        return self.settlements[0]

    @property
    def garrison(self) -> Army | None:
        return next((army for army in self.armies if army.role == "garrison"), None)

    def unit_counts(self) -> dict[str, float]:
        """Soldiers by unit type across all armies."""
        counts: dict[str, float] = {}
        for army in self.armies:
            for unit_id, count in army.units.items():
                counts[unit_id] = counts.get(unit_id, 0.0) + count
        return counts

    @property
    def workforce(self) -> float:
        return max(0.0, self.population - self.soldiers - self.wounded)

    @property
    def herd(self) -> float:
        """Every horse the civ has: in the stables, under cavalry, and under villagers."""
        cavalry = sum(army.units.get("cavalry", 0.0) for army in self.armies)
        return self.horses + cavalry + sum(1 for villager in self.villagers if villager.mounted)

    def buildings_by_tile(self) -> dict[int, list[Building]]:
        tiles: dict[int, list[Building]] = {}
        for building in self.buildings:
            tiles.setdefault(building.tile, []).append(building)
        return tiles

    def count(self, building_type: str) -> int:
        """Buildings of this type, including ones still under construction."""
        return sum(1 for b in self.buildings if b.type == building_type)

    def can_afford(self, cost: dict[str, float]) -> bool:
        return all(self.resources[res] >= amount for res, amount in cost.items())

    def pay(self, cost: dict[str, float]) -> None:
        for res, amount in cost.items():
            self.resources[res] -= amount
