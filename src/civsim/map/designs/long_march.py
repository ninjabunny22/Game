"""The Long March: one long continent, twelve bands from west to east, each a north coast (cold:
tundra, pine, iron, fish), a spine of hills and a south coast (warm grain). In the middle the
two central bands share the Crossroads: a great lake, the best farmland and a stronghold. The
west is the east in a mirror, so each start has its twin; the far ends are quiet, timber-rich
backwaters."""

from ..biomes import Biome
from ..blueprint import Blueprint, Ridge, RegionSpec
from ..shapes import Circle, Polygon, Rect

W, H = 256, 112
BANDS = 12
X0, X1 = 6, 250
ROWS = {"north": (-5, 40), "spine": (40, 72), "south": (72, 120)}
MIDDLE = (5, 6)  # the two central bands, whose spines are the Crossroads
NAMES = [  # per band west to east: north, spine, south
    ("Frostend", "Greyspine", "Westhaven"), ("Pinewick", "Larkfell", "Barleyhythe"),
    ("Sealmoor", "Rookfell", "Corncombe"), ("Ironwold", "Hawkfell", "Wheatley"),
    ("Snowmere", "Kitefell", "Oatfield"), ("Northcross", None, "Southcross"),
    ("Coldcross", None, "Suncross"), ("Coldmere", "Merlinfell", "Ryefield"),
    ("Steelwold", "Falconfell", "Hayley"), ("Walrusmoor", "Ravenfell", "Millcombe"),
    ("Firwick", "Owlfell", "Hopshythe"), ("Iceend", "Duskspine", "Easthaven"),
]
PEAKS = (2, 10)  # the spine is impassable where these bands begin


def _k(name: str) -> str:
    return name.lower().replace(" ", "_").replace("the_", "")


def _band(b: int) -> tuple[float, float]:
    width = (X1 - X0) / BANDS
    return X0 + b * width, X0 + (b + 1) * width


def _mirror(x: float) -> float:
    return W - x


def _spine(b: int) -> str:
    return "crossroads" if b in MIDDLE else _k(NAMES[b][1])


def blueprint() -> Blueprint:
    land = Polygon(((X0, 30), (14, 12), (40, 9), (128, 12), (216, 9), (242, 12), (X1, 30),
                    (X1, 82), (242, 100), (216, 103), (128, 100), (40, 103), (14, 100), (X0, 82)))
    regions, links, zones, patches, deposits, mines = [], [], [], [], [], []
    for b, names in enumerate(NAMES):
        x0, x1 = _band(b)
        mx = int((x0 + x1) / 2)
        if b >= BANDS // 2:  # the east is the west's mirror image, down to the capitals' tiles
            mx = W - 1 - int(sum(_band(BANDS - 1 - b)) / 2)
        left, right = (-5 if b == 0 else x0), (W + 5 if b == BANDS - 1 else x1)
        for row, name in zip(("north", "spine", "south"), names):
            if name is None:
                continue
            y0, y1 = ROWS[row]
            cy = {"north": 26, "spine": 56, "south": 86}[row]
            capital = f"{name.split()[-1]}ton" if row != "spine" else f"{name.split()[-1]} Hold"
            regions.append(RegionSpec(_k(name), name, capital, (mx, cy), Rect(left, y0, right, y1)))
        n, c = _k(names[0]), _k(names[2])
        links += [(n, _spine(b), "land"), (_spine(b), c, "land")]
        if b < BANDS - 1:
            links += [(n, _k(NAMES[b + 1][0]), "land"), (c, _k(NAMES[b + 1][2]), "land")]
            if b + 1 not in PEAKS and not (b in MIDDLE and b + 1 in MIDDLE):
                links.append((_spine(b), _spine(b + 1), "land"))
    # The Crossroads: one region across the two central spines.
    cross = (_band(MIDDLE[0])[0], _band(MIDDLE[1])[1])
    regions.append(RegionSpec("crossroads", "The Crossroads", "Crossroads Hold", (127, 66),
                              Rect(cross[0], 40, cross[1], 72), strength=2.0, defects=False,
                              tags=("prize", "crossroads")))
    links = list(dict.fromkeys(links))  # each spine joins the Crossroads once from each side
    # The spine: hills all along, and two impassable stretches near the ends.
    zones.append((Rect(0, 46, W, 66), Biome.HILLS))
    ridges = [Ridge(((_band(b)[0], 40), (_band(b)[0], 72)), width=3.0, flank=1.0) for b in PEAKS]
    # North: tundra on the coldest coast, pine woods, iron. South: grain.
    zones.append((Rect(0, 0, W, 17), Biome.TUNDRA))
    patches += [(Rect(0, 17, W, 46), Biome.FOREST, 0.45), (Rect(0, 66, W, H), Biome.FOREST, 0.12)]
    for b in range(BANDS):
        x0, x1 = _band(b)
        mx = (x0 + x1) / 2
        inner = 2 <= b <= BANDS - 3
        deposits.append(("iron", (int(mx) - 3, 50), 5 if inner else 3))
        deposits.append(("fertile_soil", (int(mx) + 2, 80), 6 if inner else 4))
        deposits.append(("game", (int(mx) - 4, 30), 4))
        if b in (0, BANDS - 1):  # the backwaters' timber
            patches.append((Rect(x0, 0, x1, H), Biome.FOREST, 0.5))
    # The Crossroads: a great lake and the best farmland, and gold in the spine either side.
    cx = W / 2
    lakes = [Circle(cx, 55, 5.0)]
    zones.append((Rect(cross[0], 40, cross[1], 72), Biome.PLAINS))
    deposits += [("fertile_soil", (int(cx) - 10, 50), 9), ("fertile_soil", (W - 1 - (int(cx) - 10), 50), 9)]
    spine = int(sum(_band(MIDDLE[0] - 1)) / 2)
    mines += [(int(cx) - 1, 45), (spine, 60), (W - 1 - spine, 60)]
    rivers = [[(_band(2)[0] + 6, 66), (_band(2)[0] + 5, 85), (_band(2)[0] + 6, 104)],
              [(_mirror(_band(2)[0] + 6), 66), (_mirror(_band(2)[0] + 5), 85), (_mirror(_band(2)[0] + 6), 104)],
              [(_band(4)[0] + 3, 46), (_band(4)[0] + 4, 25), (_band(4)[0] + 3, 6)],
              [(_mirror(_band(4)[0] + 3), 46), (_mirror(_band(4)[0] + 4), 25), (_mirror(_band(4)[0] + 3), 6)]]
    return Blueprint(
        id="long_march", name="The Long March", width=W, height=H, seed=7302,
        premise="A long continent: neighbours fight, the far ends are safe, and the Crossroads lies in the middle.",
        best="4",
        land=[land], coast_noise=1.3, zones=zones, patches=patches, ridges=ridges, lakes=lakes, rivers=rivers,
        deposits=deposits, scatter=[("fish", 40, None)], mines=mines, regions=regions, links=links,
        # The civs start in the four corners. Two take the west end, north and south coast, so
        # they meet (from opposite ends, four games in ten never saw a war). No fifth: a start
        # in the middle sat beside the Crossroads and won far too often.
        starts={"NW": ("frostend", "pinewick"), "SW": ("westhaven", "barleyhythe"),
                "NE": ("iceend", "firwick"), "SE": ("easthaven", "hopshythe")},
        sets={2: ["NW", "SW"], 4: ["NW", "SW", "NE", "SE"]},
    )
