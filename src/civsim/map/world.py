import base64
from collections.abc import Iterator

from .biomes import BIOME_INFO, Biome

_ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))

RIVER_CROSSING_COST = 3.0  # fording a river without bridges
BOAT_RANGE = 6  # tiles of open water boats can cross in one hop
UNOWNED_BYTE = 255
MAX_CIVS = UNOWNED_BYTE  # civ ids 0..254 fit the one-byte-per-tile territory encoding


class WorldMap:
    """Square tile grid. Tiles are addressed by a flat row-major index."""

    def __init__(self, width: int, height: int, seed: int):
        self.width = width
        self.height = height
        self.seed = seed
        size = width * height
        # Render height: 0 is sea level, land is (0, 1], sea floor is [-0.5, 0).
        self.heights: list[float] = [0.0] * size
        self.biomes: list[Biome] = [Biome.OCEAN] * size
        self.deposits: dict[int, str] = {}
        # Gold mines: one at the heart of every gold vein. Each pays its region's owner.
        self.mines: list[int] = []
        # Rivers run through land tiles: tile -> size (1 near the source, up to 3 downstream).
        self.rivers: dict[int, int] = {}
        # Where each river tile's water goes next: the next river tile downstream, or the
        # sea or lake tile it empties into. Rivers are these links, not just neighbouring tiles.
        self.river_flow: dict[int, int] = {}
        # Bridges drawn on the map: over a river, crossed at the plain cost before the Bridges
        # research; over shallow water, the only way across it on foot.
        self.bridges: set[int] = set()
        # Long bridges over water, as drawn: (x0, y0, x1, y1), from shore to shore.
        self.spans: list[tuple[int, int, int, int]] = []
        # Passes: mountain tiles (and gaps in ridges of peaks) that can be walked, slowly.
        self.passes: set[int] = set()
        # Start slots of a drawn map: slot -> (home region id, second region id), and which
        # slots a game of each number of civs uses. Empty on a generated map.
        self.starts: dict[str, tuple[int, int]] = {}
        # A number of civs may have more than one set of slots; a game takes one by its seed.
        self.start_sets: dict[int, list[list[str]]] = {}
        self.links: list[tuple[int, int, str]] = []  # drawn maps: how regions touch (see blueprint.py)
        self.map_id = ""
        self.yields: list[dict[str, int]] = [{} for _ in range(size)]
        self.owner: list[int] = [-1] * size
        # Regions (see regions.py): region id per tile (-1 for open sea), the regions
        # themselves, and capital tile -> region id.
        self.region_of: list[int] = [-1] * size
        self.regions: list = []
        self.capital_tiles: dict[int, int] = {}
        self.territory_rev = 0
        self.civs: list = []  # everyone on the map, set by the simulation

    def idx(self, x: int, y: int) -> int:
        return y * self.width + x

    def xy(self, i: int) -> tuple[int, int]:
        return i % self.width, i // self.width

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def neighbors(self, i: int, diagonal: bool = False) -> Iterator[int]:
        x, y = self.xy(i)
        offsets = _ORTHOGONAL + _DIAGONAL if diagonal else _ORTHOGONAL
        for dx, dy in offsets:
            if self.in_bounds(x + dx, y + dy):
                yield self.idx(x + dx, y + dy)

    def is_water(self, i: int) -> bool:
        return BIOME_INFO[self.biomes[i]].water

    def is_open_water(self, i: int) -> bool:
        """Deep sea or lake: nothing can be claimed or built there, and it takes boats to cross."""
        return self.biomes[i] in (Biome.OCEAN, Biome.LAKE)

    def is_peak(self, i: int) -> bool:
        """High peaks: impassable, and never settled or claimed tile by tile."""
        return self.biomes[i] == Biome.PEAKS

    def claimable(self, i: int) -> bool:
        """Can be settled or taken tile by tile: anything but open water and high peaks."""
        return not self.is_open_water(i) and not self.is_peak(i)

    def walkable(self, i: int) -> bool:
        """Can be walked by armies and villagers: land that is not high peaks, nor mountain
        unless a pass; and bridges. No water is walked, deep or shallow, except over a bridge."""
        if i in self.bridges:
            return True
        if self.is_water(i) or self.is_peak(i):
            return False
        return self.biomes[i] != Biome.MOUNTAIN or i in self.passes

    def is_boat_water(self, i: int) -> bool:
        """Water that only boats cross: sea, shallows and lakes, but for bridges."""
        return self.is_water(i) and i not in self.bridges

    def crossing_cost(self, i: int, bridges: bool, boats: bool) -> float | None:
        """Cost of moving onto a tile, or None if it cannot be entered: the one rule for how
        water, mountains and rivers affect movement (armies, villagers, war reach), and what a
        river costs to claim or to capture."""
        if self.is_boat_water(i):
            return 1.0 if boats else None
        if not self.walkable(i):
            return None
        if i in self.rivers and not bridges and i not in self.bridges:
            return RIVER_CROSSING_COST
        return 1.0

    def claim(self, i: int, civ_id: int) -> None:
        if not 0 <= civ_id < MAX_CIVS:
            raise ValueError(f"civ id {civ_id} does not fit the territory encoding (0..{MAX_CIVS - 1})")
        self.owner[i] = civ_id
        self.territory_rev += 1

    def encode_territory(self) -> str:
        """Base64 of one byte per tile, row-major: the owning civ's id, or 255 if unowned."""
        return base64.b64encode(bytes(UNOWNED_BYTE if o < 0 else o for o in self.owner)).decode("ascii")
