from dataclasses import dataclass


@dataclass
class SimConfig:
    seed: int = 0
    width: int = 96
    height: int = 96
    num_civs: int = 4
    end_tick: int = 8000  # the game is decided on score on this day, if nobody has won it before; 0 = never
    tick_rate: float = 2.0  # ticks per second when served over the bridge
    host: str = "127.0.0.1"
    port: int = 8765


MAX_CIVS = 5
# The three maps a game can be played on. `civs` is how many suit the map: enough left
# unclaimed at the start that there is room to grow before the civs meet.
MAP_SIZES = {
    "small": {"name": "Small", "side": 64, "civs": 2, "min_civs": 2, "max_civs": 3, "end_tick": 6000},
    "medium": {"name": "Medium", "side": 96, "civs": 4, "min_civs": 2, "max_civs": 5, "end_tick": 8000},
    "large": {"name": "Large", "side": 128, "civs": 5, "min_civs": 2, "max_civs": 5, "end_tick": 10000},
}


def game_config(size: str = "medium", civs: int | None = None, seed: int = 0, **kwargs) -> SimConfig:
    """The config for a game on one of the three maps. Raises ValueError for a size that does
    not exist or a number of civs the map has no room for."""
    if size not in MAP_SIZES:
        raise ValueError(f"map size must be one of {', '.join(MAP_SIZES)}")
    spec = MAP_SIZES[size]
    civs = spec["civs"] if civs is None else civs
    if isinstance(civs, bool) or not isinstance(civs, int) or not spec["min_civs"] <= civs <= spec["max_civs"]:
        raise ValueError(f"a {size} map takes {spec['min_civs']} to {spec['max_civs']} civs")
    return SimConfig(seed=seed, width=spec["side"], height=spec["side"], num_civs=civs,
                     end_tick=spec["end_tick"], **kwargs)
