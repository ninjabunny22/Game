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
