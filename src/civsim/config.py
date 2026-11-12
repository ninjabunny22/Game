from dataclasses import dataclass


@dataclass
class SimConfig:
    seed: int = 0
    map_seed: int | None = None  # the map to play on; None = whatever the game's own seed makes
    map_name: str = ""
    map_file: str = ""  # a drawn map, saved in civsim/data/maps; overrides map_seed
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
# The three map sizes. `civs` is how many suit a map of the size; min_civs and max_civs span
# what its maps take (each drawn map has its own range). `side` is the size of a generated map.
MAP_SIZES = {
    "small": {"name": "Small", "side": 64, "civs": 3, "min_civs": 2, "max_civs": 4, "end_tick": 6000},
    "medium": {"name": "Medium", "side": 96, "civs": 4, "min_civs": 2, "max_civs": 5, "end_tick": 8000},
    "large": {"name": "Large", "side": 128, "civs": 5, "min_civs": 2, "max_civs": 5, "end_tick": 10000},
}

# The maps themselves: three of each size, all drawn by hand. A game is played on one of these;
# only which civs take which start, and how they behave, differs from game to game. Each is
# built from its blueprint in civsim/map/designs and saved in civsim/data/maps
# (`python -m civsim.mapmaker bake`), with its own size, start slots and range of civs. The
# entry here is what the menu shows; the tests check it agrees with the design.
# (An entry with a `seed` instead of `file` would be a generated map, civs starting at random.)
MAPS = {
    "small": [{"id": "gilded_isle", "name": "The Gilded Isle", "file": True, "width": 72, "height": 72,
               "civs": (2, 4), "best": "2 or 4",
               "premise": "A ring of coast round a lagoon; the only gold lies on the isle in its middle."},
              {"id": "confluence", "name": "Confluence", "file": True, "width": 72, "height": 72,
               "civs": (2, 3), "best": "3",
               "premise": "Three rivers cut the land into wedges round a rich heartland; each has one old bridge."},
              {"id": "highgate", "name": "Highgate", "file": True, "width": 72, "height": 72,
               "civs": (2, 4), "best": "2 or 4",
               "premise": "A plateau of iron and gold walled in by peaks; four passes lead in, one beside each start."}],
    "medium": [{"id": "tidewalk_isles", "name": "Tidewalk Isles", "file": True, "width": 96, "height": 96,
                "civs": (2, 5), "best": "3 to 5",
                "premise": "Five isles joined by causeways armies can walk; each is rich in iron or in stone and short of the other."},
               {"id": "emberwaste", "name": "Emberwaste", "file": True, "width": 96, "height": 96,
                "civs": (2, 5), "best": "3 to 5",
                "premise": "Fertile valleys ring a great desert; the gold lies in the sand, and Kesh at its heart."},
               {"id": "the_divide", "name": "The Divide", "file": True, "width": 96, "height": 96,
                "civs": (2, 5), "best": "2 or 4",
                "premise": "A ridge of peaks splits the land in two; three passes cross it, the Kingsgate in the middle."}],
    "large": [{"id": "five_gates", "name": "The Five Gates", "file": True, "width": 160, "height": 160,
               "civs": (2, 5), "best": "5",
               "premise": "Five home lands round a walled heartland; each has its own gate into the Old Crown."},
              {"id": "long_march", "name": "The Long March", "file": True, "width": 256, "height": 112,
               "civs": (2, 5), "best": "2 to 5",
               "premise": "A long continent: neighbours fight, the far ends are safe, and the Crossroads lies in the middle."},
              {"id": "narrow_sea", "name": "The Narrow Sea", "file": True, "width": 176, "height": 144,
               "civs": (2, 5), "best": "2 or 4",
               "premise": "Two continents across an inland sea, joined only by the Wyrm's Neck; gold lies on the Drowned Crown."}],
}


def game_config(size: str = "medium", civs: int | None = None, seed: int = 0, map: str | None = None,
                **kwargs) -> SimConfig:
    """The config for a game on one of the maps of a size: the one named, or one picked by the
    game's seed. Raises ValueError for a size or map that does not exist or a number of civs
    the map has no room for."""
    asked = civs if isinstance(civs, int) and not isinstance(civs, bool) else None
    if size == "random":  # any map of any size
        sizes = [k for k in MAP_SIZES if asked is None or any(
            civ_range(k, m)[0] <= asked <= civ_range(k, m)[1] for m in MAPS[k])] or list(MAP_SIZES)
        size = sizes[seed % len(sizes)]
    if size not in MAP_SIZES:
        raise ValueError(f"map size must be one of {', '.join(MAP_SIZES)}")
    spec = MAP_SIZES[size]
    pool = MAPS[size]
    if map in (None, "random"):
        # Any of the size's maps: one that takes the civs asked for, picked by the seed.
        fitting = [m for m in pool if asked is None or civ_range(size, m)[0] <= asked <= civ_range(size, m)[1]] or pool
        chosen = fitting[seed % len(fitting)]
    else:
        chosen = next((m for m in pool if m["id"] == map), None)
    if chosen is None:
        raise ValueError(f"the {size} maps are {', '.join(m['id'] for m in pool)}")
    fewest, most = civ_range(size, chosen)
    if chosen.get("file"):
        kwargs = {"map_file": chosen["id"], "map_name": chosen["name"], **kwargs}
        width, height = chosen["width"], chosen["height"]
    else:
        kwargs = {"map_seed": chosen["seed"], "map_name": chosen["name"], **kwargs}
        width = height = spec["side"]
    civs = min(max(spec["civs"], fewest), most) if civs is None else civs
    if isinstance(civs, bool) or not isinstance(civs, int) or not fewest <= civs <= most:
        raise ValueError(f"{chosen['name']} takes {fewest} to {most} civs")
    return SimConfig(seed=seed, width=width, height=height, num_civs=civs, end_tick=spec["end_tick"], **kwargs)


def civ_range(size: str, entry: dict) -> tuple[int, int]:
    """The fewest and most civs a map takes: its own range if drawn, else its size's."""
    if "civs" in entry:
        return tuple(entry["civs"])
    spec = MAP_SIZES[size]
    return spec["min_civs"], spec["max_civs"]
