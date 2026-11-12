from dataclasses import dataclass


@dataclass
class SimConfig:
    seed: int = 0
    map_seed: int | None = None  # the map to play on; None = whatever the game's own seed makes
    map_name: str = ""
    difficulty: str = "normal"  # how hard the other civs go on a human ruler: easy, normal or hard
    width: int = 96
    height: int = 96
    num_civs: int = 4
    end_tick: int = 8000  # the game is decided on score on this day, if nobody has won it before; 0 = never
    tick_rate: float = 2.0  # ticks per second when served over the bridge
    host: str = "127.0.0.1"
    port: int = 8765


MAX_CIVS = 5
# How many people each unit of population, and each soldier, in the simulation stands for.
# Every head count shown to a player is multiplied by it; per-person rates inside the sim
# are for one unit, which is the same thing as that many people at a fraction of the rate each.
HEADCOUNT = 4
DIFFICULTIES = ("easy", "normal", "hard")
# The three maps a game can be played on. `civs` is how many suit the map: enough left
# unclaimed at the start that there is room to grow before the civs meet.
MAP_SIZES = {
    "small": {"name": "Small", "side": 64, "civs": 3, "min_civs": 2, "max_civs": 3, "end_tick": 6000},
    "medium": {"name": "Medium", "side": 96, "civs": 4, "min_civs": 2, "max_civs": 5, "end_tick": 8000},
    "large": {"name": "Large", "side": 128, "civs": 5, "min_civs": 2, "max_civs": 5, "end_tick": 10000},
}

# The maps themselves: three of each size, chosen with `python -m civsim.maps` from a few
# hundred candidates for fair regions, water and deposits everywhere, one landmass, and games
# that came out even. A game is played on one of these; only where the civs start, who they
# are and how they behave differs from game to game. `seed` is what the generator makes it from.
MAPS = {
    "small": [{"id": "aldermark", "name": "Aldermark", "seed": 93},
              {"id": "sunreach", "name": "Sunreach", "seed": 231},
              {"id": "thornwald", "name": "Thornwald", "seed": 240}],
    "medium": [{"id": "greywater", "name": "Greywater", "seed": 126},
               {"id": "highmoor", "name": "Highmoor", "seed": 2},
               {"id": "saltfen", "name": "Saltfen", "seed": 227}],
    "large": [{"id": "ironreach", "name": "Ironreach", "seed": 2},
              {"id": "wyrmcoast", "name": "Wyrmcoast", "seed": 209},
              {"id": "the_long_march", "name": "The Long March", "seed": 126}],
}


def game_config(size: str = "medium", civs: int | None = None, seed: int = 0, map: str | None = None,
                **kwargs) -> SimConfig:
    """The config for a game on one of the maps of a size: the one named, or one picked by the
    game's seed. Raises ValueError for a size or map that does not exist or a number of civs
    the map has no room for."""
    if size not in MAP_SIZES:
        raise ValueError(f"map size must be one of {', '.join(MAP_SIZES)}")
    spec = MAP_SIZES[size]
    pool = MAPS[size]
    chosen = pool[seed % len(pool)] if map is None else next((m for m in pool if m["id"] == map), None)
    if chosen is None:
        raise ValueError(f"the {size} maps are {', '.join(m['id'] for m in pool)}")
    kwargs = {"map_seed": chosen["seed"], "map_name": chosen["name"], **kwargs}
    civs = spec["civs"] if civs is None else civs
    if isinstance(civs, bool) or not isinstance(civs, int) or not spec["min_civs"] <= civs <= spec["max_civs"]:
        raise ValueError(f"a {size} map takes {spec['min_civs']} to {spec['max_civs']} civs")
    return SimConfig(seed=seed, width=spec["side"], height=spec["side"], num_civs=civs,
                     end_tick=spec["end_tick"], **kwargs)
