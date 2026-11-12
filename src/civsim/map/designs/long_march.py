"""The Long March: one long continent, eleven bands from west to east, each a north coast (cold:
tundra, pine, iron, fish), a spine of hills and a south coast (warm grain). In the middle, the
Crossroads: a great lake, the best farmland and a stronghold. The west is the east in a mirror,
so each start has its twin; the far ends are quiet, timber-rich backwaters."""

from ..biomes import Biome
from ..blueprint import Blueprint, Ridge, RegionSpec
from ..shapes import Circle, Polygon, Rect

W, H = 224, 112
BANDS = 11
X0, X1 = 6, 218
ROWS = {"north": (-5, 40), "spine": (40, 72), "south": (72, 120)}
NAMES = [  # per band west to east: north, spine, south
    ("Frostend", "Greyspine", "Westhaven"), ("Pinewick", "Larkfell", "Barleyhythe"),
    ("Sealmoor", "Rookfell", "Corncombe"), ("Ironwold", "Hawkfell", "Wheatley"),
    ("Snowmere", "Kitefell", "Oatfield"), ("Northcross", "The Crossroads", "Southcross"),
    ("Coldmere", "Merlinfell", "Ryefield"), ("Steelwold", "Falconfell", "Hayley"),
    ("Walrusmoor", "Ravenfell", "Millcombe"), ("Firwick", "Owlfell", "Hopshythe"),
    ("Iceend", "Duskspine", "Easthaven"),
]
SLOTS = {"West End": 0, "West March": 3, "Middle": 5, "East March": 7, "East End": 10}


def _k(name: str) -> str:
    return name.lower().replace(" ", "_").replace("the_", "")


def _band(b: int) -> tuple[float, float]:
    width = (X1 - X0) / BANDS
    return X0 + b * width, X0 + (b + 1) * width


def _mirror(x: float) -> float:
    return W - x


def blueprint() -> Blueprint:
    land = Polygon(((X0, 30), (14, 12), (40, 9), (112, 12), (184, 9), (210, 12), (X1, 30),
                    (X1, 82), (210, 100), (184, 103), (112, 100), (40, 103), (14, 100), (X0, 82)))
    regions, links, zones, patches, deposits, mines = [], [], [], [], [], []
    for b, names in enumerate(NAMES):
        x0, x1 = _band(b)
        mx = int((x0 + x1) / 2)
        if b > BANDS // 2:  # the east is the west's mirror image, down to the capitals' tiles
            mx = W - 1 - int(_band(BANDS - 1 - b)[0] + (x1 - x0) / 2)
        left, right = (-5 if b == 0 else x0), (W + 5 if b == BANDS - 1 else x1)
        for row, name in zip(("north", "spine", "south"), names):
            y0, y1 = ROWS[row]
            cy = {"north": 26, "spine": 56, "south": 86}[row]
            cx = mx
            if row == "spine" and b == 5:
                cy = 66  # below the Crossroads lake
            tags = ("prize", "crossroads") if b == 5 and row == "spine" else ()
            regions.append(RegionSpec(_k(name), name, f"{name.split()[-1]}ton" if row != "spine" else f"{name.split()[-1]} Hold",
                                      (cx, cy), Rect(left, y0, right, y1), strength=2.0 if tags else 1.0,
                                      defects=not tags, tags=tags))
        n, s, c = (_k(x) for x in names)
        links += [(n, s, "land"), (s, c, "land")]
        if b < BANDS - 1:
            n2, s2, c2 = (_k(x) for x in NAMES[b + 1])
            links += [(n, n2, "land"), (c, c2, "land")]
            if b not in (1, 8):  # two stretches of the spine are high peaks
                links.append((s, s2, "land"))
    # The spine: hills all along, and two impassable stretches near the ends.
    zones.append((Rect(0, 46, W, 66), Biome.HILLS))
    ridges = [Ridge(((_band(2)[0], 40), (_band(2)[0], 72)), width=3.0, flank=1.0),
              Ridge(((_band(9)[0], 40), (_band(9)[0], 72)), width=3.0, flank=1.0)]
    # North: tundra on the coldest coast, pine woods, iron. South: grain.
    zones.append((Rect(0, 0, W, 17), Biome.TUNDRA))
    patches += [(Rect(0, 17, W, 46), Biome.FOREST, 0.45), (Rect(0, 66, W, H), Biome.FOREST, 0.12)]
    for b in range(BANDS):
        x0, x1 = _band(b)
        mx = (x0 + x1) / 2
        deposits.append(("iron", (int(mx) - 3, 50), 5 if 2 <= b <= 8 else 3))
        deposits.append(("fertile_soil", (int(mx) + 2, 80), 6 if 2 <= b <= 8 else 4))
        deposits.append(("game", (int(mx) - 4, 30), 4))
        if b in (0, 10):  # the backwaters' timber
            patches.append((Rect(x0, 0, x1, H), Biome.FOREST, 0.5))
    # The Crossroads: a great lake and the best farmland, and gold in the spine either side.
    cx = (W / 2)
    lakes = [Circle(cx, 55, 5.0)]
    zones.append((Rect(_band(5)[0], 40, _band(5)[1], 72), Biome.PLAINS))
    deposits += [("fertile_soil", (int(cx) - 8, 50), 9), ("fertile_soil", (W - 1 - (int(cx) - 8), 50), 9)]
    spine4 = int((_band(4)[0] + _band(4)[1]) / 2)
    mines += [(int(cx), 45), (spine4, 60), (W - 1 - spine4, 60)]
    rivers = [[(_band(2)[0] + 6, 66), (_band(2)[0] + 5, 85), (_band(2)[0] + 6, 104)],
              [(_mirror(_band(2)[0] + 6), 66), (_mirror(_band(2)[0] + 5), 85), (_mirror(_band(2)[0] + 6), 104)],
              [(_band(4)[0] + 3, 46), (_band(4)[0] + 4, 25), (_band(4)[0] + 3, 6)],
              [(_mirror(_band(4)[0] + 3), 46), (_mirror(_band(4)[0] + 4), 25), (_mirror(_band(4)[0] + 3), 6)]]
    return Blueprint(
        id="long_march", name="The Long March", width=W, height=H, seed=7302,
        premise="A long continent: neighbours fight, the far ends are safe, and the Crossroads lies in the middle.",
        best="2 to 5",
        land=[land], coast_noise=1.3, zones=zones, patches=patches, ridges=ridges, lakes=lakes, rivers=rivers,
        deposits=deposits, scatter=[("fish", 36, None)], mines=mines, regions=regions, links=links,
        starts={slot: (_k(NAMES[b][2]), _k(NAMES[b][0])) for slot, b in SLOTS.items()},
        sets={2: ["West End", "East End"], 3: ["West End", "Middle", "East End"],
              4: ["West End", "West March", "East March", "East End"], 5: list(SLOTS)},
    )
