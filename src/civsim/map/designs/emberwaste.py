"""Emberwaste: a great desert ringed by fertile river valleys along the coast. The desert grows
no food, but its hills hold the gold, and at its heart lies the Oasis of Kesh. Small caravan
oases cross the sand like stepping stones."""

from ..biomes import Biome
from ..blueprint import Blueprint, RegionSpec
from ..shapes import Circle, Sector, towards

C = 48.0
COAST = 44.0
SAND = 30.0  # the valleys lie between this and the coast; the desert within
KESH = 11.0
VALLEYS = [  # one name and capital per valley, clockwise from north-north-west
    ("Ashara", "Asharad"), ("Belqis", "Belqar"), ("Corvan", "Corvanis"), ("Dalmir", "Dalmirra"),
    ("Esmer", "Esmerin"), ("Faran", "Faranis"), ("Galen", "Galeth"), ("Hazir", "Hazira"),
    ("Imra", "Imrath"), ("Jessa", "Jessamir"),
]
DESERTS = [("Red Waste", "Redwell"), ("Saltpan", "Panhold"), ("Glass Dunes", "Glasswell"),
           ("Ember Sands", "Emberwell"), ("Bone Flats", "Bonewell")]
SLOTS = ("S1", "S2", "S3", "S4", "S5")


def _k(name: str) -> str:
    return name.lower().replace(" ", "_")


def blueprint() -> Blueprint:
    regions, zones, patches, deposits, links, lakes, rivers, mines = [], [], [], [], [], [], [], []
    for k in range(5):
        a = 72.0 * k  # the slot's middle, where its river runs down to the sea
        for j, (lo, hi) in enumerate(((a - 36, a), (a, a + 36))):
            name, capital = VALLEYS[2 * k + j]
            at = towards(C, C, (lo + hi) / 2, 37.0)
            regions.append(RegionSpec(_k(name), name, capital, (int(at[0]), int(at[1])),
                                      Sector(C, C, SAND, 70, lo, hi)))
            deposits.append(("fertile_soil", tuple(int(v) for v in towards(C, C, (lo + hi) / 2 + 8, 34.0)), 7))
        name, capital = DESERTS[k]
        at = towards(C, C, a - 16, 21.0)
        # The desert's natives are few (in play, stronger ones were never taken, and the game
        # stalled with the civs penned in their valleys).
        regions.append(RegionSpec(_k(name), name, capital, (int(at[0]), int(at[1])),
                                  Sector(C, C, KESH, SAND, a - 36, a + 36), strength=0.6))
        rivers.append([towards(C, C, a, SAND + 0.5), towards(C, C, a + 3, 38.0), towards(C, C, a, 47.0)])
        # The desert's gold, and a caravan oasis on the way in.
        hx, hy = towards(C, C, a + 14, 22.0)
        zones.append((Circle(hx, hy, 3.0), Biome.HILLS))
        deposits.append(("stone", (int(hx) - 1, int(hy) + 1), 4))
        mines.append((int(hx), int(hy)))
        ox, oy = towards(C, C, a - 20, 15.5)
        lakes.append(Circle(ox, oy, 1.8))
        zones.append((Circle(ox, oy, 3.6), Biome.PLAINS))
        deposits.append(("fertile_soil", (int(ox) + 2, int(oy)), 6))  # the oasis feeds its caravanserai
        links += [(_k(VALLEYS[2 * k][0]), _k(VALLEYS[2 * k + 1][0]), "river"),
                  (_k(VALLEYS[2 * k + 1][0]), _k(VALLEYS[(2 * k + 2) % 10][0]), "land"),
                  (_k(VALLEYS[2 * k][0]), _k(name), "land"), (_k(VALLEYS[2 * k + 1][0]), _k(name), "land"),
                  (_k(name), _k(DESERTS[(k + 1) % 5][0]), "land"), (_k(name), "kesh", "land")]
    # Where a valley's corner meets the next desert round, the grid lets them touch.
    links += [("ashara", "bone_flats", "land"), ("belqis", "saltpan", "land"), ("saltpan", "esmer", "land"),
              ("hazir", "bone_flats", "land")]
    regions.append(RegionSpec("kesh", "Oasis of Kesh", "Kesh", (48, 48), Circle(C, C, KESH),
                              strength=1.5, defects=False, tags=("prize", "crossroads")))
    zones = [(Circle(C, C, SAND), Biome.DESERT)] + zones
    zones += [(Circle(C, C, 7.5), Biome.FOREST), (Circle(C, C, 3.5), Biome.PLAINS)]
    zones += [(Circle(C, C, 10.0) - Circle(C, C, 7.5), Biome.HILLS)]
    for k in range(5):  # the oasis's five pools, round the town
        lakes.append(Circle(*towards(C, C, 36 + 72 * k, 5.6), 1.7))
    patches = [(Circle(C, C, COAST + 3) - Circle(C, C, SAND + 2), Biome.FOREST, 0.28)]
    mines += [tuple(int(v) for v in towards(C, C, 108, 8.8)), tuple(int(v) for v in towards(C, C, 252, 8.8))]
    deposits.append(("fertile_soil", (48, 52), 5))
    return Blueprint(
        id="emberwaste", name="Emberwaste", width=96, height=96, seed=7202,
        premise="Fertile valleys ring a great desert; the gold lies in the sand, and Kesh at its heart.",
        best="3 to 5",
        land=[Circle(C, C, COAST)], coast_noise=1.3,
        zones=zones, patches=patches, lakes=lakes, rivers=rivers,
        deposits=deposits, scatter=[("fish", 16, None), ("game", 6, None)], mines=mines,
        regions=regions, links=links,
        starts={slot: (_k(VALLEYS[2 * k][0]), _k(VALLEYS[2 * k + 1][0])) for k, slot in enumerate(SLOTS)},
        sets={2: ["S1", "S3"], 3: ["S1", "S2", "S4"], 4: ["S1", "S2", "S3", "S4"], 5: list(SLOTS)},
    )
