"""The Divide: one land split from west to east by a ridge of high peaks, crossed at West Pass,
East Pass and, in the middle, the Kingsgate, a fortress held by the natives. North of the ridge,
Frostmark (pine, iron, fish); south of it, Sunfold (grain, stone). The south is the north turned
half round, so every start has its twin."""

from ..biomes import Biome
from ..blueprint import Blueprint, Ridge, RegionSpec
from ..shapes import Circle, Polygon, Rect

RIDGE_Y = 48.0
COLUMNS = (4, 26, 48, 70, 92)
# North, west to east: (coast region, capital, capital tile), (foothill region, capital, capital tile).
NORTH = [
    (("Frostwick", "Frostby", (15, 17)), ("Westwatch", "Westwatch Hold", (15, 38))),
    (("Pinemere", "Pinehold", (37, 17)), ("Kingsfoot", "Kingsfoot Hall", (35, 37))),
    (("Ironwater", "Ironby", (59, 17)), ("Crownfell", "Crownfell Hold", (60, 37))),
    (("Seal Bay", "Sealhaven", (81, 17)), ("Eastwatch", "Eastwatch Hold", (81, 38))),
]
# South, west to east; each is the north region opposite it turned half round.
SOUTH = [
    (("Goldfield", "Goldby"), ("Westgate Vale", "Westgate")),
    (("Barleydown", "Barleyford"), ("Sunfoot", "Sunfoot Hall")),
    (("Wheatmere", "Wheatby"), ("Kingsmeadow", "Kingsmeadow Hall")),
    (("Sunreach", "Sunhaven"), ("Eastgate Vale", "Eastgate")),
]


def _k(name: str) -> str:
    return name.lower().replace(" ", "_")


def _turn(x: int, y: int) -> tuple[int, int]:
    return 95 - x, 95 - y


def blueprint() -> Blueprint:
    land = Polygon(((4, 10), (10, 5), (86, 5), (92, 10), (92, 86), (86, 91), (10, 91), (4, 86)))
    passes = ((16.5, RIDGE_Y, 2.6), (48.0, RIDGE_Y, 4.9), (79.5, RIDGE_Y, 2.6))
    regions = [RegionSpec("kingsgate", "The Kingsgate", "Kingsgate", (47, 47), Rect(40, 40, 56, 56),
                          strength=2.0, defects=False, tags=("prize", "gate"))]
    for i in range(4):
        x0, x1 = (COLUMNS[i] if i else -5), (COLUMNS[i + 1] if i < 3 else 101)
        (coast, coast_cap, coast_at), (foot, foot_cap, foot_at) = NORTH[i]
        regions.append(RegionSpec(_k(coast), coast, coast_cap, coast_at, Rect(x0, -5, x1, 26)))
        regions.append(RegionSpec(_k(foot), foot, foot_cap, foot_at, Rect(x0, 26, x1, RIDGE_Y),
                                  tags=("gate",) if i in (0, 3) else ()))
    for i in range(4):
        x0, x1 = (COLUMNS[i] if i else -5), (COLUMNS[i + 1] if i < 3 else 101)
        (coast, coast_cap), (foot, foot_cap) = SOUTH[i]
        twin = NORTH[3 - i]
        regions.append(RegionSpec(_k(coast), coast, coast_cap, _turn(*twin[0][2]), Rect(x0, 70, x1, 101)))
        regions.append(RegionSpec(_k(foot), foot, foot_cap, _turn(*twin[1][2]), Rect(x0, RIDGE_Y, x1, 70),
                                  tags=("gate",) if i in (0, 3) else ()))
    links = []
    for rows in ([(c[0], f[0]) for c, f in NORTH], [(c[0], f[0]) for c, f in SOUTH]):
        for i, (coast, foot) in enumerate(rows):
            links.append((_k(coast), _k(foot), "land"))
            if i < 3:
                links += [(_k(coast), _k(rows[i + 1][0]), "land"), (_k(foot), _k(rows[i + 1][1]), "land")]
    links += [("westwatch", "westgate_vale", "pass"), ("eastwatch", "eastgate_vale", "pass")]
    links += [(f, "kingsgate", "pass") for f in ("kingsfoot", "crownfell", "sunfoot", "kingsmeadow")]

    zones, patches, deposits = [], [], []
    # North: pine and iron, and fish along the cold coast. South: grain and stone.
    patches.append((Rect(0, 0, 96, RIDGE_Y - 3), Biome.FOREST, 0.45))
    zones.append((Rect(0, 0, 96, 9), Biome.TUNDRA))
    patches.append((Rect(0, RIDGE_Y + 3, 96, 96), Biome.FOREST, 0.15))
    for x, y in ((14, 32), (58, 34), (82, 30), (36, 20)):
        zones.append((Circle(x + 0.5, y + 0.5, 2.6), Biome.HILLS))
        deposits.append(("iron", (x, y), 4))
        sx, sy = _turn(x, y)
        zones.append((Circle(sx + 0.5, sy + 0.5, 2.6), Biome.HILLS))
        deposits.append(("stone", (sx, sy), 5))
    deposits += [("game", (26, 14), 5), ("game", (70, 22), 5)]
    deposits += [("fertile_soil", _turn(26, 14), 8), ("fertile_soil", _turn(70, 22), 8)]
    # Grain for the south to match the north's iron.
    deposits += [("fertile_soil", _turn(x, y), 7) for x, y in ((14, 22), (82, 22), (48, 30))]
    return Blueprint(
        id="the_divide", name="The Divide", width=96, height=96, seed=7203,
        premise="A ridge of peaks splits the land in two; three passes cross it, the Kingsgate in the middle.",
        best="2 or 4",
        land=[land], coast_noise=1.2, protect=[Rect(0, RIDGE_Y - 6, 96, RIDGE_Y + 6)],
        zones=zones, patches=patches,
        ridges=[Ridge(((-2, RIDGE_Y), (98, RIDGE_Y)), width=3.2, flank=1.6, gaps=passes)],
        deposits=deposits, scatter=[("fish", 16, None)],
        # The Kingsgate's mine, and two on each half, one either side of the Kingsgate's foothills
        # (with one a half, east of the middle, a middle start and the east fought over it and
        # the west did best).
        mines=[(43, 43), (37, 40), (58, 40), _turn(37, 40), _turn(58, 40)],
        regions=regions, links=links,
        starts={"NW": ("frostwick", "westwatch"), "NE": ("seal_bay", "eastwatch"), "N5": ("pinemere", "ironwater"),
                "SW": ("goldfield", "westgate_vale"), "SE": ("sunreach", "eastgate_vale"),
                "S5": ("barleydown", "wheatmere")},
        # No 3: two civs on one half and one alone on the other always made the lone one lose
        # (the pair ally against it: it won 1 game in 15).
        sets={2: ["NW", "SE"], 4: ["NW", "NE", "SW", "SE"], 5: ["NW", "N5", "NE", "SW", "SE"]},
    )
