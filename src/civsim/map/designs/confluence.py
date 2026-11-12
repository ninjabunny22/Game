"""Confluence: three rivers run in from the coast to the Mere of Three Waters and cut the land
into three wedges. Around the Mere lies the richest farmland on the map; each river has one
old bridge, and until Bridges are researched every other crossing is slow and costly."""

from ..biomes import Biome
from ..blueprint import Blueprint, RegionSpec
from ..shapes import Circle, Sector, towards

C = 36.0
MERE = 5.0
HEART = 13.0  # the heartland reaches this far from the Mere's centre
INNER = 23.0  # the wedges' hills and woods reach this far; the coasts lie beyond
RIVERS = (300.0, 60.0, 180.0)  # bearings: each river runs in from the coast along one
WEDGES = [  # centre bearing, coast, hills, woods, heart: (region, capital) each
    (0.0, ("Northfold", "Fordham"), ("Kestrel Hills", "Kestrel Hold"), ("Ashwood", "Ashby"),
     ("Northmead", "Meadowcross")),
    (120.0, ("Brightfold", "Brightwater"), ("Ember Hills", "Emberton"), ("Thornwood", "Thornby"),
     ("Eastmead", "Ferrymead")),
    (240.0, ("Westfold", "Westerby"), ("Raven Hills", "Ravenhold"), ("Elderwood", "Elderby"),
     ("Westmead", "Millmead")),
]
SLOTS = ("A", "B", "C")


def _k(name: str) -> str:
    return name.lower().replace(" ", "_")


def blueprint() -> Blueprint:
    land = Circle(C, C, 33.5)  # round, so the three wedges are alike
    regions, zones, patches, deposits, mines, links = [], [], [], [], [], []
    for a, coast, hills, woods, heart in WEDGES:
        left, right = a - 60, a + 60
        regions += [
            RegionSpec(_k(coast[0]), coast[0], coast[1], tuple(int(v) for v in towards(C, C, a, 28.5)),
                       Sector(C, C, INNER, 60, left, right)),
            RegionSpec(_k(hills[0]), hills[0], hills[1], tuple(int(v) for v in towards(C, C, a - 30, 17.5)),
                       Sector(C, C, HEART, INNER, left, a)),
            RegionSpec(_k(woods[0]), woods[0], woods[1], tuple(int(v) for v in towards(C, C, a + 30, 17.5)),
                       Sector(C, C, HEART, INNER, a, right)),
            RegionSpec(_k(heart[0]), heart[0], heart[1], tuple(int(v) for v in towards(C, C, a, 9.5)),
                       Sector(C, C, 0, HEART, left, right), tags=("prize",)),
        ]
        hx, hy = towards(C, C, a - 33, 19.5)
        zones.append((Circle(hx, hy, 3.2), Biome.HILLS))
        deposits += [("stone", (int(hx) - 1, int(hy)), 4), ("iron", (int(hx) + 1, int(hy) + 1), 3)]
        mines.append(tuple(int(v) for v in towards(C, C, a - 42, 20.5)))
        zones.append((Sector(C, C, HEART + 1, INNER, a + 4, right - 4), Biome.FOREST))
        patches.append((Sector(C, C, HEART, INNER, a, right), Biome.PLAINS, 0.25))
        patches.append((Sector(C, C, INNER, 60, left, right), Biome.FOREST, 0.2))
        deposits.append(("game", tuple(int(v) for v in towards(C, C, a + 32, 20.0)), 5))
        deposits.append(("fertile_soil", tuple(int(v) for v in towards(C, C, a - 18, 9.0)), 7))
        deposits.append(("fertile_soil", tuple(int(v) for v in towards(C, C, a + 18, 9.0)), 7))
        sx, sy = towards(C, C, a, 32)
        zones.append((Circle(sx, sy, 2.5), Biome.HILLS))
        deposits.append(("stone", (int(sx), int(sy)), 3))
        links += [(_k(coast[0]), _k(hills[0]), "land"), (_k(coast[0]), _k(woods[0]), "land"),
                  (_k(hills[0]), _k(woods[0]), "land"), (_k(hills[0]), _k(heart[0]), "land"),
                  (_k(woods[0]), _k(heart[0]), "land")]
    for i, (a, coast, hills, woods, heart) in enumerate(WEDGES):
        nxt = WEDGES[(i + 1) % 3]
        links += [(_k(coast[0]), _k(nxt[1][0]), "river"), (_k(woods[0]), _k(nxt[2][0]), "bridge"),
                  (_k(heart[0]), _k(nxt[4][0]), "river")]
    # Where three regions meet at a river, the squares of the grid let a corner of one touch the
    # far bank: crossings like any other along the river.
    links += [("kestrel_hills", "westfold", "river"), ("ashwood", "brightfold", "river"),
              ("northmead", "ember_hills", "river"), ("northmead", "elderwood", "river")]
    rivers, bridges = [], []
    for b in RIVERS:
        rivers.append([towards(C, C, b, 31.0), towards(C, C, b + 3, 20.0), towards(C, C, b - 2, 11.0),
                       towards(C, C, b, MERE - 1.0)])
        bridges.append(tuple(int(v) for v in towards(C, C, b + 2.0, 18.0)))
        zones.append((Circle(*towards(C, C, b, 30.5), 3.0), Biome.HILLS))
    return Blueprint(
        id="confluence", name="Confluence", width=72, height=72, seed=7102,
        premise="Three rivers cut the land into wedges round a rich heartland; each has one old bridge.",
        best="3",
        land=[land], protect=[], zones=zones, patches=patches,
        lakes=[Circle(C, C, MERE)], rivers=rivers, bridges=bridges,
        deposits=deposits, scatter=[("fish", 10, None)], mines=mines,
        regions=regions, links=links,
        starts={slot: (_k(w[1][0]), _k(w[2][0])) for slot, w in zip(SLOTS, WEDGES)},
        sets={2: ["A", "B"], 3: ["A", "B", "C"]},
    )
