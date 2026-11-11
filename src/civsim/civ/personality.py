import random
from dataclasses import dataclass

from ..datafiles import load_json


@dataclass(frozen=True)
class Personality:
    name: str
    weights: dict[str, float]


def assign_personalities(count: int, rng: random.Random) -> list[Personality]:
    """Give each civ a distinct archetype (while they last), jittered by the seed."""
    data = load_json("personalities.json")
    jitter = data["jitter"]
    names = sorted(data["archetypes"])
    rng.shuffle(names)
    result = []
    for i in range(count):
        name = names[i % len(names)]
        weights = {
            key: round(value * (1 + rng.uniform(-jitter, jitter)), 3)
            for key, value in data["archetypes"][name].items()
        }
        result.append(Personality(name, weights))
    return result


# What a realm can concentrate on, and what that does to the weights its AI plans by.
FOCUSES = {
    "balanced": {},
    "growth": {"growth": 1.6, "food": 1.4},
    "economy": {"wealth": 1.6, "industry": 1.4, "infrastructure": 1.2},
    "military": {"military": 1.8},
    "science": {"science": 1.8},
    "expansion": {"expansion": 1.8},
}


def with_focus(born: Personality, focus: str) -> Personality:
    """The personality a civ plans by while it concentrates on `focus`: its own, tilted."""
    tilt = FOCUSES[focus]
    return Personality(born.name, {key: round(value * tilt.get(key, 1.0), 3) for key, value in born.weights.items()})
