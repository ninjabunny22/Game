import base64

from .biomes import BIOME_INFO, Biome

_ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))

RIVER_CROSSING_COST = 3.0
_WATER = frozenset(b for b, info in BIOME_INFO.items() if info.water)
_OPEN_WATER = frozenset((Biome.OCEAN, Biome.LAKE))
_UNWALKABLE = _WATER | {Biome.PEAKS}  # fording a river without bridges
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
        # Rich nodes: deposits yielding RICH_YIELD times as much. Centre tile -> its name, and
        # every tile of the node (the deposit's tiles of that kind within reach of the centre).
        self.rich: dict[int, str] = {}
        self.rich_tiles: set[int] = set()
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
        self._around4: list[tuple[int, ...]] | None = None  # neighbours of each tile, see neighbors()
        self._around8: list[tuple[int, ...]] | None = None

    def idx(self, x: int, y: int) -> int:
        return y * self.width + x

    def xy(self, i: int) -> tuple[int, int]:
        return i % self.width, i // self.width

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def neighbors(self, i: int, diagonal: bool = False) -> tuple[int, ...]:
        """The tiles beside tile i (four, or eight with diagonals; fewer at the edge), in a fixed
        order. Worked out once per map: the simulation asks this tens of millions of times."""
        table = self._around8 if diagonal else self._around4
        if table is None:
            table = self._neighbour_table(diagonal)
        return table[i]

    def _neighbour_table(self, diagonal: bool) -> list[tuple[int, ...]]:
        offsets = _ORTHOGONAL + _DIAGONAL if diagonal else _ORTHOGONAL
        table = []
        for i in range(self.width * self.height):
            x, y = i % self.width, i // self.width
            table.append(tuple(self.idx(x + dx, y + dy) for dx, dy in offsets if self.in_bounds(x + dx, y + dy)))
        if diagonal:
            self._around8 = table
        else:
            self._around4 = table
        return table

    def is_water(self, i: int) -> bool:
        return self.biomes[i] in _WATER

    def is_open_water(self, i: int) -> bool:
        """Deep sea or lake: nothing can be claimed or built there, and it takes boats to cross."""
        return self.biomes[i] in _OPEN_WATER

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
        biome = self.biomes[i]
        if biome in _UNWALKABLE:
            return False
        return biome != Biome.MOUNTAIN or i in self.passes

    def is_boat_water(self, i: int) -> bool:
        """Water that only boats cross: sea, shallows and lakes, but for bridges."""
        return self.biomes[i] in _WATER and i not in self.bridges

    def crossing_cost(self, i: int, bridges: bool, boats: bool) -> float | None:
        """Cost of moving onto a tile, or None if it cannot be entered: the one rule for how
        water, mountains and rivers affect movement (armies, villagers, war reach), and what a
        river costs to claim or to capture."""
        if i in self.bridges:
            return 1.0
        biome = self.biomes[i]
        if biome in _WATER:
            return 1.0 if boats else None
        if biome == Biome.PEAKS or (biome == Biome.MOUNTAIN and i not in self.passes):
            return None
        if not bridges and i in self.rivers:
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
