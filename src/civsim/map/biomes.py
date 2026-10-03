from dataclasses import dataclass, field
from enum import IntEnum


class Biome(IntEnum):
    OCEAN = 0
    SHALLOWS = 1
    PLAINS = 2
    FOREST = 3
    DESERT = 4
    TUNDRA = 5
    HILLS = 6
    MOUNTAIN = 7
    LAKE = 8


@dataclass(frozen=True)
class BiomeInfo:
    name: str
    color: str
    # Work slots per tile, by resource. One slot employs one worker.
    yields: dict[str, int] = field(default_factory=dict)
    water: bool = False
    buildable: bool = True


BIOME_INFO: dict[Biome, BiomeInfo] = {
    Biome.OCEAN: BiomeInfo("Ocean", "#1f4e8c", {}, water=True, buildable=False),
    Biome.SHALLOWS: BiomeInfo("Shallows", "#3f86c4", {"food": 1}, water=True, buildable=False),
    Biome.PLAINS: BiomeInfo("Plains", "#8dbb55", {"food": 2}),
    Biome.FOREST: BiomeInfo("Forest", "#2f7d3b", {"wood": 2, "food": 1}),
    Biome.DESERT: BiomeInfo("Desert", "#dcc67a", {}),
    Biome.TUNDRA: BiomeInfo("Tundra", "#c9d6d3", {}),
    Biome.HILLS: BiomeInfo("Hills", "#9a8f62", {"stone": 2}),
    Biome.MOUNTAIN: BiomeInfo("Mountain", "#8a8a8f", {"stone": 1, "ore": 1}, buildable=False),
    Biome.LAKE: BiomeInfo("Lake", "#4aa3df", {}, water=True, buildable=False),
}
