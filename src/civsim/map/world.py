import base64
from collections.abc import Iterator

from .biomes import BIOME_INFO, Biome

_ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))

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
        self.yields: list[dict[str, int]] = [{} for _ in range(size)]
        self.owner: list[int] = [-1] * size
        self.territory_rev = 0

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

    def claim(self, i: int, civ_id: int) -> None:
        if not 0 <= civ_id < MAX_CIVS:
            raise ValueError(f"civ id {civ_id} does not fit the territory encoding (0..{MAX_CIVS - 1})")
        self.owner[i] = civ_id
        self.territory_rev += 1

    def encode_territory(self) -> str:
        """Base64 of one byte per tile, row-major: the owning civ's id, or 255 if unowned."""
        return base64.b64encode(bytes(UNOWNED_BYTE if o < 0 else o for o in self.owner)).decode("ascii")
