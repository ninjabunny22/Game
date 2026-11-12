"""The Five Gates: a ring of impassable mountains encloses the Old Crown, the heartland of a
fallen empire, entered through five passes. Outside, five wedge-shaped home lands run down to
the sea, each with its own gate, divided from one another by rivers with one old bridge each,
and each with an island off its coast."""

from ..biomes import Biome
from ..blueprint import Blueprint, Ridge, RegionSpec
from ..shapes import Circle, Sector, towards

C = 80.0
WALL = 22.0
CROWN = 8.0  # Crownhold's own region
COAST = 62.0
ISLE_AT, ISLE = 72.0, 5.0
BANDS = (WALL, 32.0, 44.0, 53.0, 80.0)  # gate approach | riversides | vale | coast
WEDGES = [  # per wedge: coast, vale, west riverside, east riverside, gate approach, crown region, island
    ("Northreach", "Kestrel Vale", "Larchbank", "Willowbank", "North Gate", "Crown of the North", "Gull Isle"),
    ("Eastmarch", "Amber Vale", "Reedbank", "Alderbank", "Dawn Gate", "Crown of the Dawn", "Seal Isle"),
    ("Southhaven", "Golden Vale", "Mossbank", "Fernbank", "Sun Gate", "Crown of the Sun", "Tern Isle"),
    ("Westmarch", "Rowan Vale", "Ashbank", "Elmbank", "Dusk Gate", "Crown of the Dusk", "Otter Isle"),
    ("Stormcoast", "Heron Vale", "Birchbank", "Hollybank", "Storm Gate", "Crown of the Storm", "Puffin Isle"),
]


def _k(name: str) -> str:
    return name.lower().replace(" ", "_").replace("of_the_", "")


def _at(a: float, r: float) -> tuple[int, int]:
    x, y = towards(C, C, a, r)
    return int(x), int(y)


def blueprint() -> Blueprint:
    regions, zones, patches, deposits, links, mines, rivers, bridges, islands = [], [], [], [], [], [], [], [], []
    isles, may = [], []
    for k, (coast, vale, west, east, gate, crown, isle) in enumerate(WEDGES):
        w = 72.0 * k
        lo, hi = w - 36, w + 36
        g0, r1, r2, r3, r4 = BANDS
        regions += [
            RegionSpec(_k(coast), coast, f"{coast.split()[0]}port" if " " in coast else f"{coast}ton", _at(w, 57.5),
                       Sector(C, C, r3, r4, lo, hi)),
            RegionSpec(_k(vale), vale, f"{vale.split()[0]}hold", _at(w, 48.5), Sector(C, C, r2, r3, lo, hi)),
            RegionSpec(_k(west), west, f"{west[:-4]}ford", _at(w - 18, 38.0), Sector(C, C, r1, r2, lo, w)),
            RegionSpec(_k(east), east, f"{east[:-4]}ford", _at(w + 18, 38.0), Sector(C, C, r1, r2, w, hi)),
            RegionSpec(_k(gate), gate, f"{gate.split()[0]}watch", _at(w + 14, 29.0), Sector(C, C, g0, r1, lo, hi),
                       tags=("gate",)),
            RegionSpec(_k(crown), crown, f"{crown.split()[-1]}crown", _at(w, 15.0), Sector(C, C, CROWN, WALL, lo, hi),
                       strength=2.0, tags=("prize",)),
        ]
        isles.append(RegionSpec(_k(isle), isle, f"{isle.split()[0]}haven", _at(w, ISLE_AT),
                                Circle(*towards(C, C, w, ISLE_AT), ISLE + 3), strength=0.8))
        islands.append(Circle(*towards(C, C, w, ISLE_AT), ISLE))
        nxt = WEDGES[(k + 1) % 5]
        links += [(_k(coast), _k(vale), "land"), (_k(vale), _k(west), "land"), (_k(vale), _k(east), "land"),
                  (_k(west), _k(east), "land"), (_k(west), _k(gate), "land"), (_k(east), _k(gate), "land"),
                  (_k(gate), _k(crown), "pass"), (_k(crown), "crownhold", "land"), (_k(crown), _k(nxt[5]), "land"),
                  (_k(coast), _k(isle), "sea:6"),
                  # Across the river on the wedge's east side, into the next wedge.
                  (_k(coast), _k(nxt[0]), "river"), (_k(vale), _k(nxt[1]), "river"),
                  (_k(east), _k(nxt[2]), "bridge"), (_k(gate), _k(nxt[4]), "land")]
        bands = [_k(coast), _k(vale), _k(east), _k(gate)]
        theirs = [_k(nxt[0]), _k(nxt[1]), _k(nxt[2]), _k(nxt[4])]
        may += [(a, b) for i, a in enumerate(bands) for j, b in enumerate(theirs) if abs(i - j) == 1]
        river = w + 36
        rivers.append([towards(C, C, river, 26.5), towards(C, C, river - 2, 40.0), towards(C, C, river + 1, 52.0),
                       towards(C, C, river, COAST + 4)])
        bridges.append(_at(river - 1.5, 40.0))
        mines.append(_at(w + 9, 48.0))
        zones.append((Circle(*towards(C, C, w - 12, 28.0), 3.0), Biome.HILLS))
        deposits += [("stone", _at(w - 12, 28.0), 4), ("iron", _at(w - 10, 29.5), 3)]
        deposits += [("fertile_soil", _at(w - 10, 57.0), 7), ("fertile_soil", _at(w + 20, 37.0), 6),
                     ("fertile_soil", _at(w, 14.0), 6), ("iron", _at(w + 14, 16.5), 3)]
        patches += [(Sector(C, C, r1, r2, lo, hi), Biome.FOREST, 0.4), (Sector(C, C, r3, r4, lo, hi), Biome.FOREST, 0.18)]
        deposits.append(("game", _at(w - 20, 40.0), 5))
    regions = isles + regions  # first, so the coasts' shapes do not take the islands' land
    regions.append(RegionSpec("crownhold", "The Old Crown", "Crownhold", (80, 80), Circle(C, C, CROWN), strength=3.0,
                              defects=False, tags=("prize", "crossroads")))
    zones.append((Circle(C, C, WALL), Biome.PLAINS))
    ring = tuple(towards(C, C, a, WALL + 1.0) for a in range(0, 361, 5))
    gaps = tuple((*towards(C, C, 72.0 * k, WALL + 1.0), 2.8) for k in range(5))
    mines += [(77, 77), (83, 83)]
    return Blueprint(
        id="five_gates", name="The Five Gates", width=160, height=160, seed=7301,
        premise="Five home lands round a walled heartland; each has its own gate into the Old Crown.",
        best="5",
        land=[Circle(C, C, COAST)] + islands, coast_noise=1.3, protect=[Circle(C, C, WALL + 6)],
        zones=zones, patches=patches,
        ridges=[Ridge(ring, width=3.0, flank=1.4, gaps=gaps)],
        rivers=rivers, bridges=bridges, deposits=deposits,
        scatter=[("fish", 30, None)], mines=mines, regions=regions, links=links, may_touch=may,
        starts={f"W{k + 1}": (_k(w[0]), _k(w[1])) for k, w in enumerate(WEDGES)},
        sets={2: ["W1", "W3"], 3: ["W1", "W2", "W4"], 4: ["W1", "W2", "W3", "W4"], 5: ["W1", "W2", "W3", "W4", "W5"]},
    )
