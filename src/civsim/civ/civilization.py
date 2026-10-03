from dataclasses import dataclass, field

from ..economy.rules import RESOURCES
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
    buildings: list[Building] = field(default_factory=list)

    # Economy state, refreshed every tick.
    workers: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    idle: float = 0.0
    capacity: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    income: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    upkeep: dict[str, float] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0.0))
    goal: Goal | None = None

    # Army. Soldiers are counted in `population`.
    soldiers: float = 0.0
    unpaid: bool = False
    unsupplied: bool = False

    # Standing orders from the diplomacy layer, executed by the economy and the AI.
    soldier_target: float = 0.0
    military_need: float = 0.0  # 0 = at peace and unthreatened, 1 = at war
    march_target: int | None = None  # civ to expand toward, to bring it within reach
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
