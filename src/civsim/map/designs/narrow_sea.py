"""The Narrow Sea: two continents across an inland sea. Frostmark in the north (pine, iron,
fish) and Sunmarch in the south (grain, stone). In the west they are joined by
the Wyrm's Neck, a narrow isthmus with a native fortress; in the east two small isles step across
the strait; in mid-sea lies the Drowned Crown with two gold mines, too far out for settlers
before Navigation."""

from ..biomes import Biome
from ..blueprint import Blueprint, RegionSpec
from ..shapes import Circle, Polygon, Rect

W, H = 176, 144
COLS = 7
X0, X1 = 6, 170
NORTH_Y = (6, 32, 58)  # high row, shore row
SOUTH_Y = (86, 112, 138)  # shore row, high row
NECK_X = (6, 24)
NAMES_N = [("Wolfheights", "Frostwick"), ("Elkheights", "Pinewater"), ("Bearheights", "Sealsands"),
           ("Owlheights", "Grayshore"), ("Hawkheights", "Coldharbour"), ("Lynxheights", "Icewater"),
           ("Crowheights", "Stormcape")]
NAMES_S = [("Lionfield", "Wyrmshore"), ("Oxfield", "Barleysands"), ("Boarfield", "Goldshore"),
           ("Stagfield", "Wheatshore"), ("Harefield", "Sunharbour"), ("Foxfield", "Ambershore"),
           ("Bullfield", "Sunrise Cape")]


def _k(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")


def _col(i: int) -> tuple[float, float]:
    width = (X1 - X0) / COLS
    return X0 + i * width, X0 + (i + 1) * width


def blueprint() -> Blueprint:
    north = Polygon(((X0, 12), (12, 6), (164, 6), (X1, 12), (X1, 64), (146, 64), (140, 58), (X0, 58)))
    south = Polygon(((X0, 86), (140, 86), (146, 80), (X1, 80), (X1, 132), (164, 138), (12, 138), (X0, 132)))
    neck = Rect(NECK_X[0], 56, NECK_X[1], 88)
    isles = [Circle(150.0, 72.0, 3.7), Circle(163.0, 72.0, 3.7), Circle(88.0, 72.0, 4.8)]
    regions, links, zones, patches, deposits = [], [], [], [], []
    for i in range(COLS):
        x0, x1 = _col(i)
        left, right = (-5 if i == 0 else x0), (W + 5 if i == COLS - 1 else x1)
        mx = int((x0 + x1) / 2)
        (nh, ns), (ss, sh) = NAMES_N[i], NAMES_S[i]
        regions += [
            RegionSpec(_k(nh), nh, f"{nh[:-7]}hold", (mx, 18), Rect(left, -5, right, NORTH_Y[1])),
            RegionSpec(_k(ns), ns, f"{ns}ton" if " " not in ns else ns.replace(" ", "") + "ton", (mx, 46),
                       Rect(left, NORTH_Y[1], right, 66) - neck),
            RegionSpec(_k(ss), ss, f"{ss[:-5]}stead", (mx, 125), Rect(left, SOUTH_Y[1], right, H + 5)),
            RegionSpec(_k(sh), sh, f"{sh}ton" if " " not in sh else sh.replace(" ", "") + "ton", (mx, 98),
                       Rect(left, 78, right, SOUTH_Y[1]) - neck),
        ]
        links += [(_k(nh), _k(ns), "land"), (_k(ss), _k(sh), "land")]
        if i < COLS - 1:
            (nh2, ns2), (ss2, sh2) = NAMES_N[i + 1], NAMES_S[i + 1]
            links += [(_k(nh), _k(nh2), "land"), (_k(ns), _k(ns2), "land"), (_k(ss), _k(ss2), "land"),
                      (_k(sh), _k(sh2), "land")]
        # North: iron. South: grain and stone.
        zones.append((Circle(mx - 4.5, 24.5, 2.4), Biome.HILLS))
        deposits.append(("iron", (mx - 5, 24), 4))
        deposits.append(("game", (mx + 4, 40), 4))
        zones.append((Circle(mx - 4.5, 119.5, 3.2), Biome.HILLS))
        deposits.append(("stone", (mx - 5, 119), 5))
        deposits.append(("iron", (mx - 3, 121), 2))  # the south is short of iron, not without it
        deposits.append(("fertile_soil", (mx + 4, 104), 8))
        deposits.append(("fertile_soil", (mx - 6, 130), 6))
    regions += [
        RegionSpec("neck_north", "Neck North", "Northgate", (14, 62), Rect(NECK_X[0] - 6, 58, NECK_X[1], 67)),
        RegionSpec("wyrms_neck", "The Wyrm's Neck", "Wyrmhold", (14, 72), Rect(NECK_X[0] - 6, 67, NECK_X[1], 77),
                   strength=2.0, defects=False, tags=("neck",)),
        RegionSpec("neck_south", "Neck South", "Southgate", (14, 82), Rect(NECK_X[0] - 6, 77, NECK_X[1], 86)),
        RegionSpec("skerry", "The Skerry", "Skerryhaven", (149, 71), Circle(150.0, 72.0, 6.0)),
        RegionSpec("holm", "The Holm", "Holmhaven", (162, 71), Circle(163.0, 72.0, 6.0)),
        RegionSpec("drowned_crown", "The Drowned Crown", "Crownwater", (88, 72), Circle(88.0, 72.0, 9.0),
                   strength=2.0, defects=False, tags=("prize",)),
    ]
    links += [("neck_north", _k(NAMES_N[0][1]), "land"), ("neck_north", "wyrms_neck", "neck"),
              ("wyrms_neck", "neck_south", "neck"), ("neck_south", _k(NAMES_S[0][1]), "land"),
              ("skerry", _k(NAMES_N[6][1]), "sea:6"), ("skerry", _k(NAMES_S[6][1]), "sea:6"),
              ("holm", _k(NAMES_N[6][1]), "sea:6"), ("holm", _k(NAMES_S[6][1]), "sea:6"), ("skerry", "holm", "sea:6"),
              ("drowned_crown", _k(NAMES_N[3][1]), "sea:10"), ("drowned_crown", _k(NAMES_S[3][1]), "sea:10")]
    zones.append((Rect(0, 0, W, 13), Biome.TUNDRA))
    zones.append((Rect(NECK_X[0], 67, NECK_X[1], 77), Biome.HILLS))
    patches += [(Rect(0, 13, W, 58), Biome.FOREST, 0.42), (Rect(0, 86, W, H), Biome.FOREST, 0.12)]
    return Blueprint(
        id="narrow_sea", name="The Narrow Sea", width=W, height=H, seed=7303,
        premise="Two continents across an inland sea, joined only by the Wyrm's Neck; gold lies on the Drowned Crown.",
        best="2 or 4",
        land=[north, south, neck] + isles, coast_noise=1.3,
        protect=[Rect(0, 52, 30, 92), Rect(136, 56, W, 88), Circle(88.0, 72.0, 8.0)],
        zones=zones, patches=patches, deposits=deposits,
        scatter=[("fish", 34, None)], mines=[(13, 70), (86, 70), (90, 74)],
        regions=regions, links=links,
        starts={"NW": (_k(NAMES_N[1][1]), _k(NAMES_N[1][0])), "NE": (_k(NAMES_N[5][1]), _k(NAMES_N[5][0])),
                "SW": (_k(NAMES_S[1][1]), _k(NAMES_S[1][0])), "SE": (_k(NAMES_S[5][1]), _k(NAMES_S[5][0])),
                "NeckN": ("wyrms_neck", "neck_north"), "NeckS": ("wyrms_neck", "neck_south")},
        sets={2: ["NW", "SW"], 3: ["NW", "NE", "SW"], 4: ["NW", "NE", "SW", "SE"],
              5: [["NW", "NE", "SW", "SE", "NeckN"], ["NW", "NE", "SW", "SE", "NeckS"]]},
    )
