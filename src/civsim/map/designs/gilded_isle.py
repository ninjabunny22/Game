"""The Gilded Isle: a ring of coast round a lagoon, and in the lagoon a hilly isle with the
map's only gold. Every ring region is the same sail from it; two narrow necks split the ring
into halves."""

from ..biomes import Biome
from ..blueprint import Blueprint, RegionSpec
from ..shapes import Band, Circle, Sector, towards

C = 36.0  # the lagoon's centre
SHORE = 11.0  # the ring's inner shore
OUTER = 33.0  # its outer coast
ISLE = 5.5
NARROWS = (45.0, 225.0)

RING = [  # bearing, region, capital
    (0, "Northmere", "Northwick"), (30, "Saltwick", "Saltcombe"), (60, "Ambercove", "Amberley"),
    (90, "Eastreach", "Eastwold"), (120, "Coralbay", "Coralford"), (150, "Sunmere", "Sunhallow"),
    (180, "Southmere", "Southwick"), (210, "Driftholm", "Driftwell"), (240, "Willowstrand", "Willowby"),
    (270, "Westreach", "Westwold"), (300, "Tidecombe", "Tidebury"), (330, "Gullhaven", "Gullcastle"),
]


def _key(name: str) -> str:
    return name.lower()


def blueprint() -> Blueprint:
    # The two Narrows: an inlet from the open sea cuts the ring almost through, leaving a neck
    # three tiles wide along the lagoon.
    inlets = [Band((towards(C, C, a, SHORE + 3.0 + 5.0), towards(C, C, a, 48.0)), 10.0) for a in NARROWS]
    necks = [Circle(*towards(C, C, a, SHORE + 2.0), 7.0) for a in NARROWS]

    regions, zones, patches, deposits = [], [], [], []
    for k, (a, name, capital) in enumerate(RING):
        shape = Sector(C, C, SHORE - 3.0, 50.0, a - 15, a + 15)
        # Capitals in the ring's middle; the two beside each inlet sit a little off it.
        bearing = a
        for n in NARROWS:
            if abs((a - n + 180) % 360 - 180) == 15:
                bearing = a + (-6 if (a - n) % 360 > 180 else 6)
        x, y = towards(C, C, bearing, 22.0)
        regions.append(RegionSpec(_key(name), name, capital, (int(x), int(y)), shape))
        fertile = k % 2 == 0
        zones.append((shape, Biome.PLAINS if fertile else Biome.FOREST))
        patches.append((shape, Biome.FOREST if fertile else Biome.PLAINS, 0.22))
        hx, hy = towards(C, C, a + (7 if fertile else -7), 28.5)
        zones.append((Circle(hx, hy, 2.6), Biome.HILLS))
        deposits.append(("stone" if fertile else "iron", (int(hx), int(hy)), 4))
        fx, fy = towards(C, C, a - 6, 17.0)
        deposits.append(("fertile_soil" if fertile else "game", (int(fx), int(fy)), 6))
    for a in NARROWS:
        zones.append((Circle(*towards(C, C, a, SHORE + 2.0), 4.0), Biome.HILLS))
        deposits.append(("stone", tuple(int(v) for v in towards(C, C, a, SHORE + 1.5)), 4))
    regions.append(RegionSpec("goldcrown", "Goldcrown", "Gilded Keep", (36, 36), Circle(C, C, SHORE - 3.0),
                              strength=2.0, defects=False, tags=("prize",)))
    zones.append((Circle(C, C, ISLE + 1), Biome.HILLS))
    deposits.append(("iron", (37, 33), 3))

    ring_keys = [_key(name) for _, name, _ in RING]
    links = []
    for i, key in enumerate(ring_keys):
        nxt = ring_keys[(i + 1) % len(ring_keys)]
        across = any(abs(((RING[i][0] + 15) - n + 180) % 360 - 180) < 1 for n in NARROWS)
        links.append((key, nxt, "neck" if across else "land"))
        links.append((key, "goldcrown", "sea:6"))

    def slot(a: int) -> tuple[str, str]:
        i = a // 30
        return ring_keys[i], ring_keys[(i + 1) % 12]

    return Blueprint(
        id="gilded_isle", name="The Gilded Isle", width=72, height=72, seed=7101,
        premise="A ring of coast round a lagoon; the only gold lies on the isle in its middle.",
        best="2 or 4",
        land=[Circle(C, C, OUTER) - Circle(C, C, SHORE), Circle(C, C, ISLE)], sea=inlets,
        protect=[Circle(C, C, SHORE + 1.5)] + necks,
        zones=zones, patches=patches,
        lakes=[], deposits=deposits,
        scatter=[("fish", 12, Circle(C, C, SHORE + 1)), ("fish", 8, None)],
        mines=[(33, 34), (39, 38)],
        regions=regions, links=links,
        # With four, each pair of slots faces the other across a Narrows, and each slot holds one
        # of the four regions an inlet cuts into, so all four start alike.
        # With four, every home castle stands back from the Narrows it faces, its second region
        # on the Narrows (homes on the front lost far more often in play).
        starts={"A": slot(0), "B": slot(60)[::-1], "C": slot(120), "D": slot(180), "E": slot(240),
                "E4": slot(240)[::-1]},
        sets={2: ["A", "D"], 3: ["A", "C", "E"], 4: ["A", "B", "D", "E4"]},
    )
