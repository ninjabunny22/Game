"""Highgate: a high plateau walled in by impassable peaks, entered through four passes. Behind
the passes lie four vales of iron and stone and, at the centre, Highgate itself with the gold.
Around the wall, fertile lowlands run down to the sea."""

from ..biomes import Biome
from ..blueprint import Blueprint, Ridge, RegionSpec
from ..shapes import Circle, Polygon, Sector, towards

C = 36.0
WALL = 17.0  # the ring of peaks
CORE = 6.5  # Highgate's own region
LOWLANDS = [  # bearing, region, capital; corners and pass mouths alternate
    (315, "Ashdale", "Ashford"), (0, "Brackenford", "Brackenbury"), (45, "Elmridge", "Elmstead"),
    (90, "Cragmouth", "Cragford"), (135, "Fernmoor", "Fernby"), (180, "Southmouth", "Southgate"),
    (225, "Greywood", "Greyhold"), (270, "Westmouth", "Westgate"),
]
VALES = [(0, "North Vale", "Northcairn"), (90, "East Vale", "Eastcairn"), (180, "South Vale", "Southcairn"),
         (270, "West Vale", "Westcairn")]


def _k(name: str) -> str:
    return name.lower().replace(" ", "_")


def blueprint() -> Blueprint:
    land = Polygon(((3, 9), (9, 3), (63, 3), (69, 9), (69, 63), (63, 69), (9, 69), (3, 63)))
    ring = tuple(towards(C, C, a, WALL) for a in range(0, 361, 6))
    passes = tuple((*towards(C, C, a, WALL), 2.6) for a in (0, 90, 180, 270))
    regions, zones, patches, deposits, links = [], [], [], [], []
    for i, (a, name, capital) in enumerate(LOWLANDS):
        corner = a % 90 == 45
        at = towards(C, C, a, 28.0 if corner else 25.5)
        regions.append(RegionSpec(_k(name), name, capital, (int(at[0]), int(at[1])),
                                  Sector(C, C, WALL, 60, a - 22.5, a + 22.5)))
        nxt = LOWLANDS[(i + 1) % len(LOWLANDS)][1]
        links.append((_k(name), _k(nxt), "land"))
        if corner:
            deposits.append(("fertile_soil", tuple(int(v) for v in towards(C, C, a - 8, 23.0)), 7))
            hx, hy = towards(C, C, a + 10, 30.0)
            zones.append((Circle(hx, hy, 2.2), Biome.HILLS))
            deposits.append(("iron", (int(hx), int(hy)), 2))
            patches.append((Sector(C, C, WALL + 2, 60, a - 22.5, a + 22.5), Biome.FOREST, 0.3))
        else:
            patches.append((Sector(C, C, WALL + 2, 60, a - 22.5, a + 22.5), Biome.FOREST, 0.15))
            deposits.append(("game", tuple(int(v) for v in towards(C, C, a + 12, 27.0)), 4))
    for a, name, capital in VALES:
        at = towards(C, C, a, 11.5)
        regions.append(RegionSpec(_k(name), name, capital, (int(at[0]), int(at[1])),
                                  Sector(C, C, CORE, WALL, a - 45, a + 45), strength=1.5))
        mouth = next(n for b, n, _ in LOWLANDS if b == a)
        links += [(_k(mouth), _k(name), "pass"), (_k(name), "highgate", "land")]
        deposits.append(("iron", tuple(int(v) for v in towards(C, C, a - 20, 12.5)), 4))
        deposits.append(("stone", tuple(int(v) for v in towards(C, C, a + 22, 12.0)), 4))
    for i, (a, name, _) in enumerate(VALES):
        links.append((_k(name), _k(VALES[(i + 1) % 4][1]), "land"))
    regions.append(RegionSpec("highgate", "Highgate", "Highgate Keep", (36, 36), Circle(C, C, CORE),
                              strength=2.0, defects=False, tags=("prize",)))
    zones.append((Circle(C, C, WALL), Biome.HILLS))
    zones.append((Circle(C, C, CORE + 0.5), Biome.PLAINS))
    return Blueprint(
        id="highgate", name="Highgate", width=72, height=72, seed=7103,
        premise="A plateau of iron and gold walled in by peaks; four passes lead in, one beside each start.",
        best="2 or 4",
        land=[land], zones=zones, patches=patches,
        ridges=[Ridge(ring, width=2.6, flank=1.2, gaps=passes)],
        deposits=deposits, scatter=[("fish", 10, None)], mines=[(32, 33), (40, 39)],
        regions=regions, links=links,
        starts={"NW": ("ashdale", "brackenford"), "NE": ("elmridge", "cragmouth"),
                "SE": ("fernmoor", "southmouth"), "SW": ("greywood", "westmouth")},
        sets={2: ["NW", "SE"], 3: ["NW", "NE", "SE"], 4: ["NW", "NE", "SE", "SW"]},
    )
