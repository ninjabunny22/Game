from dataclasses import dataclass, field

from ..economy.rules import RESOURCES
from ..military.army import Army, Commander, Villager
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


@dataclass
class Goal:
    """What the civ is currently saving up for."""

    kind: str  # "build" or "expand"
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
    base_territory: int = 0  # tiles held at the start; expansion is priced on what was added since
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

    # Standing orders from the diplomacy layer, executed by the economy and the AI.
    soldier_target: float = 0.0
    military_need: float = 0.0  # 0 = at peace and unthreatened, 1 = at war
    march_target: int | None = None  # civ to expand toward, to bring it within reach
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
        return max(0.0, self.population - self.soldiers)

    def occupied(self) -> set[int]:
        return {b.tile for b in self.buildings} | {s.tile for s in self.settlements}

    def count(self, building_type: str) -> int:
        """Buildings of this type, including ones still under construction."""
        return sum(1 for b in self.buildings if b.type == building_type)

    def can_afford(self, cost: dict[str, float]) -> bool:
        return all(self.resources[res] >= amount for res, amount in cost.items())

    def pay(self, cost: dict[str, float]) -> None:
        for res, amount in cost.items():
            self.resources[res] -= amount
