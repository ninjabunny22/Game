"""Saved maps: a drawn map, built once and kept in civsim/data/maps so it never changes by
accident, whatever later happens to the code that builds maps."""

import gzip
import json
from importlib import resources
from pathlib import Path

from .biomes import Biome
from .regions import Region
from .resources import compute_yields
from .world import WorldMap

FORMAT = 1


def map_path(map_id: str) -> Path:
    return Path(str(resources.files("civsim").joinpath("data", "maps", f"{map_id}.map.json.gz")))


def to_data(world: WorldMap) -> dict:
    return {
        "format": FORMAT, "id": world.map_id, "width": world.width, "height": world.height, "seed": world.seed,
        "heights": world.heights, "biomes": [int(b) for b in world.biomes],
        "deposits": {str(t): d for t, d in sorted(world.deposits.items())},
        "mines": world.mines,
        "rivers": {str(t): s for t, s in sorted(world.rivers.items())},
        "river_flow": {str(t): to for t, to in sorted(world.river_flow.items())},
        "bridges": sorted(world.bridges),
        "passes": sorted(world.passes),
        "spans": [list(span) for span in world.spans],
        "region_of": world.region_of,
        "regions": [{"name": r.name, "capital_name": r.capital_name, "capital": r.capital, "strength": r.strength,
                     "defects": r.defects, "tags": list(r.tags), "points": r.points} for r in world.regions],
        "links": [list(link) for link in world.links],
        "starts": {slot: list(pair) for slot, pair in world.starts.items()},
        "start_sets": {str(n): slots for n, slots in sorted(world.start_sets.items())},
    }


def save(world: WorldMap, path: Path) -> None:
    text = json.dumps(to_data(world), separators=(",", ":"), sort_keys=True)
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as z:
        z.write(text.encode("utf-8"))


def from_data(data: dict) -> WorldMap:
    if data.get("format") != FORMAT:
        raise ValueError(f"saved map format {data.get('format')} is not {FORMAT}")
    world = WorldMap(data["width"], data["height"], data["seed"])
    world.map_id = data["id"]
    world.heights = list(data["heights"])
    world.biomes = [Biome(b) for b in data["biomes"]]
    world.deposits = {int(t): d for t, d in data["deposits"].items()}
    world.mines = list(data["mines"])
    world.rivers = {int(t): s for t, s in data["rivers"].items()}
    world.river_flow = {int(t): to for t, to in data["river_flow"].items()}
    world.bridges = set(data["bridges"])
    world.passes = set(data["passes"])
    world.spans = [tuple(span) for span in data["spans"]]
    world.region_of = list(data["region_of"])
    compute_yields(world)
    world.regions = []
    for r, spec in enumerate(data["regions"]):
        tiles = [t for t, owner in enumerate(world.region_of)
                 if owner == r and world.biomes[t] not in (Biome.LAKE, Biome.PEAKS)]
        world.regions.append(Region(r, spec["name"], spec["capital_name"], spec["capital"], tiles,
                                    strength=spec["strength"], defects=spec["defects"], tags=tuple(spec["tags"]),
                                    points=spec["points"]))
    world.capital_tiles = {region.capital: region.id for region in world.regions}
    world.links = [tuple(link) for link in data["links"]]
    world.starts = {slot: tuple(pair) for slot, pair in data["starts"].items()}
    world.start_sets = {int(n): [list(s) for s in options] for n, options in data["start_sets"].items()}
    return world


def load(path: Path) -> WorldMap:
    with gzip.open(path, "rb") as z:
        return from_data(json.loads(z.read().decode("utf-8")))


def load_map(map_id: str) -> WorldMap:
    """A saved map, fresh: every game gets its own copy to play on."""
    return load(map_path(map_id))
