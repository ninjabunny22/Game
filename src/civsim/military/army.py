import math
from dataclasses import dataclass, field

from .units import UNIT_TYPES

MAX_COMMANDER_LEVEL = 10
XP_PER_LEVEL_STEP = 25  # level n needs 25 * (n - 1)^2 experience
STRENGTH_PER_LEVEL = 0.04  # each level above 1 adds this to the army's strength
CASUALTIES_PER_LEVEL = 0.02  # ... and takes this off its losses


@dataclass
class Commander:
    """Leads a field army, or holds a capital while in reserve. Skill grows with combat seen."""

    name: str
    experience: float = 0.0
    battles: int = 0
    wins: int = 0
    post: int | None = None  # tile of the capital a reserve commander is stationed at

    @property
    def level(self) -> int:
        return min(MAX_COMMANDER_LEVEL, 1 + int(math.sqrt(self.experience / XP_PER_LEVEL_STEP)))

    @property
    def strength_bonus(self) -> float:
        return STRENGTH_PER_LEVEL * (self.level - 1)

    @property
    def casualty_reduction(self) -> float:
        return CASUALTIES_PER_LEVEL * (self.level - 1)


@dataclass
class Captive:
    """A commander taken in defeat, held by the civ that caught him."""

    commander: Commander
    home: int  # the civ he served
    since: int  # tick he was taken


@dataclass
class Army:
    """A body of troops on the map: the piece that moves, fights and takes ground."""

    id: int
    civ: int
    tile: int
    role: str  # "garrison" (holds the capital, no commander) or "field"
    units: dict[str, float] = field(default_factory=dict)  # unit type -> soldiers
    commander: Commander | None = None
    target_civ: int | None = None  # the enemy a field army was raised against
    target_region: int | None = None  # or the neutral region an expedition was sent to take
    engaged_since: int | None = None  # tick an expedition began fighting a native garrison
    state: str = "idle"  # idle | marching | besieging | fighting | retreating | returning
    path: list[int] = field(default_factory=list)  # tiles still to walk, next first
    move_points: float = 0.0
    siege_progress: float = 0.0
    path_tick: int = -10_000  # when the path was last planned
    no_route: int | None = None  # the goal there was no way to when last planned
    leaderless_until: int = 0  # tick from which a commanderless field army gets a new one
    # Pursuit of a routed enemy: its id, where and until when the chase runs.
    pursuing: int | None = None
    pursuit_origin: int = -1
    pursuit_until: int = 0
    disordered_until: int = 0  # a pursuer is out of formation during the chase and for a while after
    rout_size: float = 0.0  # soldiers this army had when it broke
    boat: bool = False  # aboard ship on open water, having put out from near one of its civ's harbours

    @property
    def size(self) -> float:
        return sum(self.units.values())

    @property
    def speed(self) -> float:
        present = [UNIT_TYPES[u].speed for u, count in self.units.items() if count >= 0.5]
        return min(present) if present else 1.0

    @property
    def dominant(self) -> str | None:
        """The unit type most of the army is made of."""
        return max(sorted(self.units), key=lambda u: self.units[u]) if self.size > 0 else None

    def scale(self, factor: float) -> None:
        self.units = {u: count * factor for u, count in self.units.items()}

    def add(self, units: dict[str, float]) -> None:
        for unit_id, count in units.items():
            self.units[unit_id] = self.units.get(unit_id, 0.0) + count

    def take(self, amount: float) -> dict[str, float]:
        """Remove `amount` soldiers, spread across types in proportion, and return them."""
        size = self.size
        if size <= 0 or amount <= 0:
            return {}
        share = min(1.0, amount / size)
        taken = {u: count * share for u, count in self.units.items()}
        self.scale(1 - share)
        return taken


@dataclass
class Villager:
    """A non-combatant worker. Construction only advances while one is on the site.
    Villagers are never killed: on a captured tile they change sides and wait for orders."""

    id: int
    tile: int
    task: str = "idle"  # idle | build | gather
    target: int | None = None
    building: int = 0  # id of the building a builder is putting up (a tile may have several sites)
    gathers: str | None = None  # the resource a gathering villager is working
    mounted: bool = False  # riding a horse from the stables: does more on the land he works
    path: list[int] = field(default_factory=list)
