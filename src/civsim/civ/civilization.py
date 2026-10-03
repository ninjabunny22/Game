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


@dataclass
class Goal:
    """What the civ is currently saving up for."""

    kind: str  # "build" or "expand"
    target: str | None
    cost: dict[str, float]


@dataclass
class Research:
    tech_id: str
    paid: bool = False  # material cost paid; now waiting on science


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
    goal: Goal | None = None

    known_techs: list[str] = field(default_factory=list)
    research: Research | None = None
    science: float = 0.0
    science_rate: float = 0.0

    @property
    def capital(self) -> Settlement:
        return self.settlements[0]

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
