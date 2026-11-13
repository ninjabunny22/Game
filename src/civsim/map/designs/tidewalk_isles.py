"""Tidewalk Isles: five home isles in a ring, joined to each other and to Saltcrown in the middle
by long bridges over the shallows, the only ways across on foot. Each isle is rich in iron or in stone and
short of the other. Off Eyot lies Pearl Reef, which only boats can reach."""

from ..biomes import Biome
from ..blueprint import Blueprint, RegionSpec
from ..shapes import Band, Circle, Sector, towards

C = 48.0
RING = 28.0  # the home isles' centres lie this far from Saltcrown
ISLE = 14.0
HUB = 10.0  # Saltcrown's isle; the keep's own region is the inner part
KEEP = 4.8  # the hills about Saltcrown Keep
CAUSEWAY = 2.6
REEF = (13.5, 17.5)
ISLES = [  # bearing, name, what it is rich in, capitals of head, downs, strand
    (0, "Hollin", ("iron",), ("Hollinhead", "Hollinford", "Hollinstrand")),
    (72, "Brannock", ("stone",), ("Brannockhead", "Brannockby", "Brannock Sands")),
    (144, "Corrie", ("iron",), ("Corriehead", "Corrieford", "Corrie Sands")),
    (216, "Dunlin", ("stone",), ("Dunlinhead", "Dunlinby", "Dunlin Sands")),
    (288, "Eyot", ("iron", "stone"), ("Eyothead", "Eyotford", "Eyot Sands")),
]


def _k(name: str) -> str:
    return name.lower().replace(" ", "_")


def blueprint() -> Blueprint:
    centres = [towards(C, C, b, RING) for b, *_ in ISLES]
    land = [Circle(x, y, ISLE) for x, y in centres] + [Circle(C, C, HUB), Circle(*REEF, 4.6)]
    regions, zones, patches, deposits, links, shallows, protect, causeways = [], [], [], [], [], [], [], []
    for i, ((b, name, rich, capitals), (x, y)) in enumerate(zip(ISLES, centres)):
        parts = [("Head", b - 60, b + 60), ("Downs", b + 60, b + 180), ("Strand", b + 180, b + 300)]
        for (part, a0, a1), capital in zip(parts, capitals):
            mid = (a0 + a1) / 2
            at = towards(x, y, mid, 6.5)
            regions.append(RegionSpec(_k(f"{name} {part}"), f"{name} {part}", capital, (int(at[0]), int(at[1])),
                                      Sector(x, y, 0, ISLE + 4, a0, a1)))
        k = lambda part, n=name: _k(f"{n} {part}")  # noqa: E731
        links += [(k("Head"), k("Downs"), "land"), (k("Head"), k("Strand"), "land"), (k("Downs"), k("Strand"), "land")]
        # A causeway to the next isle round, from this isle's Downs to that isle's Strand ...
        nx, ny = centres[(i + 1) % len(centres)]
        shallows.append(Band(((x, y), (nx, ny)), CAUSEWAY))
        causeways.append([(x, y), (nx, ny)])  # a bridge along it: the way across on foot
        links.append((k("Downs"), _k(f"{ISLES[(i + 1) % len(ISLES)][1]} Strand"), "causeway"))
        # ... and one in to Saltcrown, from the Downs.
        landing = towards(x, y, b + 150, ISLE - 1)
        shallows.append(Band((landing, (C, C)), CAUSEWAY))
        causeways.append([landing, (C, C)])
        links.append((k("Downs"), "saltcrown", "causeway"))
        protect.append(Band(((x, y), (nx, ny)), CAUSEWAY + 4))
        protect.append(Band((landing, (C, C)), CAUSEWAY + 4))
        hx, hy = towards(x, y, b + 120, 6.0)
        # Iron needs hills, and hills are stone too: the iron isles' hills are kept small.
        zones.append((Circle(hx, hy, 1.9 if rich == ("iron",) else 3.2), Biome.HILLS))
        for j, res in enumerate(rich):
            size = (4 if res == "iron" else 8) if len(rich) == 1 else 3
            deposits.append((res, (int(hx) + j, int(hy) - j), size))
        deposits.append(("fertile_soil", tuple(int(v) for v in towards(x, y, b - 10, 5.0)), 6))
        if rich == ("stone",):  # stone builds less than iron arms: the stone isles grow more grain ...
            deposits.append(("fertile_soil", tuple(int(v) for v in towards(x, y, b + 35, 7.5)), 7))
            # ... and are short of iron, not without it (in play they lost far more often without).
            deposits.append(("iron", (int(hx) - 1, int(hy) + 1), 2))
        patches.append((Sector(x, y, 0, ISLE + 4, b - 180, b + 180), Biome.FOREST, 0.3))
        deposits.append(("game", tuple(int(v) for v in towards(x, y, b - 120, 6.5)), 4))
    regions.append(RegionSpec("saltcrown", "Saltcrown", "Saltcrown Keep", (48, 48), Circle(C, C, HUB + 4),
                              strength=2.0, defects=False, tags=("prize", "crossroads")))
    regions.append(RegionSpec("pearl_reef", "Pearl Reef", "Pearlhaven", (13, 17), Circle(*REEF, 8.0), strength=0.5))
    links += [("eyot_head", "pearl_reef", "sea:6")]
    zones.append((Circle(C, C, KEEP + 0.5), Biome.HILLS))
    return Blueprint(
        id="tidewalk_isles", name="Tidewalk Isles", width=96, height=96, seed=7201,
        premise="Five isles joined by causeways armies can walk; each is rich in iron or in stone and short of the other.",
        best="3 to 5",
        land=land, shallows=shallows, causeways=causeways, protect=protect + [Circle(C, C, HUB + 2)], coast_noise=0.9,
        zones=zones, patches=patches, deposits=deposits,
        scatter=[("fish", 18, None)], mines=[(45, 45), (51, 51), (16, 14)],
        regions=regions, links=links,
        starts={name: (_k(f"{name} Head"), _k(f"{name} Downs")) for _, name, *_ in ISLES},
        sets={2: ["Hollin", "Corrie"], 3: ["Hollin", "Brannock", "Dunlin"],
              4: ["Hollin", "Brannock", "Corrie", "Dunlin"], 5: ["Hollin", "Brannock", "Corrie", "Dunlin", "Eyot"]},
    )
