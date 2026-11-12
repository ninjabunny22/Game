"""A picture of a map, as PNG, drawn without any imaging library: biomes, region borders,
rivers, capitals, gold mines, old bridges and start slots."""

import struct
import zlib

from .biomes import BIOME_INFO
from .world import WorldMap

SLOT_COLOURS = [(230, 60, 50), (40, 110, 230), (250, 200, 30), (150, 60, 200), (30, 190, 170), (240, 120, 30)]
RIVER = (40, 110, 200)
BRIDGE = (120, 70, 30)
MINE = (255, 205, 0)
CAPITAL = (255, 255, 255)
STRONGHOLD = (200, 20, 20)


def _hex(colour: str) -> tuple[int, int, int]:
    colour = colour.lstrip("#")
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16)


def png(world: WorldMap, scale: int = 5) -> bytes:
    w, h = world.width * scale, world.height * scale
    pixels = [[(0, 0, 0)] * w for _ in range(h)]

    def fill(tx: int, ty: int, colour, inset: int = 0) -> None:
        for py in range(ty * scale + inset, (ty + 1) * scale - inset):
            row = pixels[py]
            for px in range(tx * scale + inset, (tx + 1) * scale - inset):
                row[px] = colour

    for i, biome in enumerate(world.biomes):
        x, y = world.xy(i)
        r, g, b = _hex(BIOME_INFO[biome].color)
        shade = 0.85 + 0.3 * max(0.0, world.heights[i])
        fill(x, y, (min(255, int(r * shade)), min(255, int(g * shade)), min(255, int(b * shade))))
        if i in world.rivers:
            fill(x, y, BRIDGE if i in world.bridges else RIVER, inset=max(1, scale // 3))
        if i in world.deposits and i not in world.rivers:
            dr, dg, db = _hex(_deposit_colour(world.deposits[i]))
            pixels[y * scale + scale // 2][x * scale + scale // 2] = (dr, dg, db)
    # Region borders: a dark line on each side where the region changes.
    for i, region in enumerate(world.region_of):
        if region < 0:
            continue
        x, y = world.xy(i)
        for dx, dy in ((1, 0), (0, 1)):
            if world.in_bounds(x + dx, y + dy):
                other = world.region_of[world.idx(x + dx, y + dy)]
                if other >= 0 and other != region:
                    if dx:
                        for py in range(y * scale, (y + 1) * scale):
                            pixels[py][(x + 1) * scale - 1] = (25, 25, 25)
                    else:
                        for px in range(x * scale, (x + 1) * scale):
                            pixels[(y + 1) * scale - 1][px] = (25, 25, 25)
    for tile in world.mines:
        x, y = world.xy(tile)
        fill(x, y, MINE, inset=1)
    slot_of = {}
    for k, (slot, (home, second)) in enumerate(sorted(world.starts.items())):
        slot_of.setdefault(home, SLOT_COLOURS[k % len(SLOT_COLOURS)])
    for region in world.regions:
        x, y = world.xy(region.capital)
        ring = STRONGHOLD if region.strength > 1 else slot_of.get(region.id, (20, 20, 20))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if world.in_bounds(x + dx, y + dy):
                    fill(x + dx, y + dy, ring)
        fill(x, y, CAPITAL)
    return _encode(pixels)


def _deposit_colour(type_id: str) -> str:
    from .resources import DEPOSIT_TYPES
    return DEPOSIT_TYPES[type_id].color


def _encode(pixels) -> bytes:
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in pixels)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
