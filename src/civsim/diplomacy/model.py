from dataclasses import dataclass, field
from enum import Enum

from .rules import DEAL_DURATION


class Stance(str, Enum):
    TRADE = "trade"
    ALLY = "ally"
    IGNORE = "ignore"
    AGGRESSION = "aggression"


FRIENDLY = (Stance.TRADE, Stance.ALLY)


@dataclass
class Intent:
    """What one civ wants from another, as set by its strategic layer at a check-in."""

    stance: Stance = Stance.IGNORE
    give: str | None = None  # trade offer: resource and amount per tick
    give_rate: float = 0.0
    want: str | None = None
    want_rate: float = 0.0
    commitment: float = 0.0  # aggression: share of full mobilisation, 0..1
    tick: int = 0


@dataclass
class Deal:
    """A standing trade: each side sends its resource every tick until the deal ends."""

    id: int
    a: int
    b: int
    a_gives: tuple[str, float]  # resource, amount per tick
    b_gives: tuple[str, float]
    start: int
    duration: int = DEAL_DURATION
    missed: dict[int, int] = field(default_factory=dict)  # civ id -> consecutive short deliveries

    @property
    def end(self) -> int:
        return self.start + self.duration

    def flows(self) -> tuple[tuple[int, int, str, float], tuple[int, int, str, float]]:
        """(giver, receiver, resource, rate) for both directions."""
        return (self.a, self.b, *self.a_gives), (self.b, self.a, *self.b_gives)


@dataclass
class War:
    a: int
    b: int
    start: int
    aggressors: set[int] = field(default_factory=set)  # sides currently pressing the attack
    progress: dict[int, float] = field(default_factory=dict)  # civ id -> capture progress, in tiles
    tiles_taken: dict[int, int] = field(default_factory=dict)
    casualties: dict[int, float] = field(default_factory=dict)


@dataclass
class Relation:
    status: str = "peace"  # "peace" | "alliance" | "war"
    since: int = 0
    truce_until: int = 0
    war: War | None = None
