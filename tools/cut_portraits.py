"""Cuts the royal portraits out of the boards in portraits_royalty/ into one small picture per
character (and a crest per house), for the viewer's family panel and banners. Run from the
repository root with a Python that has Pillow:

    python3 tools/cut_portraits.py            # writes godot/assets/portraits/<house>/<name>.png
    python3 tools/cut_portraits.py --sheet    # also a contact sheet of every crop, to check them

Each box is the panel's picture above its name plaque, measured by hand on the 1536 x 1024
boards; the plaque is left off because the game shows names and ages itself. A crop keeps the
top of its box (where the face is) at a 4:5 portrait shape.
"""

import os
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
BOARDS = os.path.join(ROOT, "portraits_royalty")
OUT = os.path.join(ROOT, "godot", "assets", "portraits")
SIZE = (200, 250)

VALEDORN = "House Valedorn Family Portraits.png"
ASHBOURNE = "House Ashbourne Family Portrait Board.png"
RAVENSHADE = "House Ravenshade_ A Regal Lineage.png"
THORNWICK = "House Thornwick Character Roster.png"
FROSTMERE = "House Frostmere_ Winter Dynasty.png"
FROSTMERE_OLD = "House Frostmere_ A Regal Lineage.png"
GREYTHORNE = "House Greythorne_ A Royal Portrait Gallery.png"
SILVERMERE = "Silvermere Family Portrait Montage.png"
INFOGRAPHIC = "Medieval Houses Portraits Infographic.png"
CHRONICLE = "Medieval Houses_ A Noble Family Chronicle.png"
CASTING = "Medieval Fantasy Portrait Casting Collage.png"  # six children above, the same six grown up below


def row(board: str, house: str, names: list[str], edges: list[int], top: int, bottom: int) -> list:
    """A strip of portraits side by side: `edges` are the x of each panel's sides."""
    return [(board, house, name, (edges[i] + 4, top, edges[i + 1] - 4, bottom)) for i, name in enumerate(names)]


CUTS = [
    # board, house, first name (or "crest"), box (x0, y0, x1, y1)
    (VALEDORN, "valedorn", "crest", (30, 20, 265, 300)),
    (VALEDORN, "valedorn", "edric", (290, 10, 682, 378)),
    (VALEDORN, "valedorn", "isolde", (692, 10, 1098, 378)),
    (VALEDORN, "valedorn", "cedric", (1108, 10, 1528, 378)),
    (VALEDORN, "valedorn", "elara", (8, 482, 388, 878)),
    (VALEDORN, "valedorn", "rowan", (396, 482, 760, 878)),
    (VALEDORN, "valedorn", "aldric", (772, 482, 1150, 860)),
    (VALEDORN, "valedorn", "maerwynn", (1158, 482, 1528, 860)),
    (ASHBOURNE, "ashbourne", "crest", (30, 20, 290, 300)),
    (ASHBOURNE, "ashbourne", "osric", (316, 10, 708, 418)),
    (ASHBOURNE, "ashbourne", "theobald", (718, 10, 1126, 418)),
    (ASHBOURNE, "ashbourne", "evelyne", (1136, 10, 1528, 418)),
    (ASHBOURNE, "ashbourne", "garrick", (8, 520, 380, 928)),
    (ASHBOURNE, "ashbourne", "mirabel", (388, 520, 768, 928)),
    (ASHBOURNE, "ashbourne", "owyn", (778, 520, 1146, 928)),
    (ASHBOURNE, "ashbourne", "aveline", (1156, 520, 1528, 928)),
    (RAVENSHADE, "ravenshade", "crest", (20, 30, 320, 330)),
    (RAVENSHADE, "ravenshade", "seraphine", (342, 10, 748, 470)),
    (RAVENSHADE, "ravenshade", "theron", (1158, 10, 1528, 470)),
    (THORNWICK, "thornwick", "crest", (40, 30, 340, 330)),
    (THORNWICK, "thornwick", "merek", (388, 10, 762, 410)),
    (THORNWICK, "thornwick", "garran", (774, 10, 1148, 410)),
    (THORNWICK, "thornwick", "vaelor", (1158, 10, 1528, 410)),
    (THORNWICK, "thornwick", "silas", (8, 516, 378, 922)),
    (THORNWICK, "thornwick", "ysella", (388, 516, 826, 922)),
    (THORNWICK, "thornwick", "dorian", (850, 516, 1220, 922)),
    (FROSTMERE, "frostmere", "crest", (25, 20, 335, 330)),
    (FROSTMERE, "frostmere", "elswyth", (366, 10, 750, 408)),
    (FROSTMERE, "frostmere", "alistair", (764, 10, 1143, 408)),
    (FROSTMERE, "frostmere", "freya", (1156, 10, 1528, 408)),
    (FROSTMERE, "frostmere", "eamon", (8, 512, 502, 918)),
    (FROSTMERE, "frostmere", "cadan", (516, 512, 1020, 918)),
    (FROSTMERE, "frostmere", "hadrien", (1034, 512, 1528, 918)),
    (FROSTMERE_OLD, "frostmere", "alaric", (1034, 512, 1528, 918)),
    (GREYTHORNE, "greythorne", "crest", (20, 30, 290, 330)),
    (GREYTHORNE, "greythorne", "roderic", (308, 10, 708, 400)),
    (GREYTHORNE, "greythorne", "lysandra", (718, 10, 1138, 400)),
    (GREYTHORNE, "greythorne", "dorian", (1148, 10, 1528, 400)),
    (GREYTHORNE, "greythorne", "seraphina", (8, 504, 386, 912)),
    (GREYTHORNE, "greythorne", "callum", (396, 504, 764, 912)),
    (GREYTHORNE, "greythorne", "marrek", (774, 504, 1148, 912)),
    (GREYTHORNE, "greythorne", "varen", (1158, 504, 1528, 912)),
    (SILVERMERE, "silvermere", "crest", (1400, 30, 1530, 230)),
    (SILVERMERE, "silvermere", "alaric", (4, 4, 508, 425)),
    (SILVERMERE, "silvermere", "maelis", (521, 4, 1028, 425)),
    (SILVERMERE, "silvermere", "lorcan", (1041, 4, 1532, 425)),
    (SILVERMERE, "silvermere", "cerys", (4, 504, 508, 925)),
    (SILVERMERE, "silvermere", "rohan", (521, 504, 1028, 925)),
    (SILVERMERE, "silvermere", "edrin", (1041, 504, 1532, 925)),
    # The two group boards: the houses that only marry in. Their crests are the small emblems
    # by each house's name.
    (INFOGRAPHIC, "emberfall", "crest", (234, 0, 284, 52)),
    (INFOGRAPHIC, "galenford", "crest", (1000, 0, 1048, 50)),
    (INFOGRAPHIC, "merewood", "crest", (230, 344, 284, 396)),
    (INFOGRAPHIC, "stonehart", "crest", (1000, 344, 1052, 398)),
    (INFOGRAPHIC, "whitecrest", "crest", (230, 674, 284, 728)),
    (INFOGRAPHIC, "blackvale", "crest", (996, 674, 1054, 730)),
    (CHRONICLE, "willowsong", "crest", (1018, 630, 1066, 668)),
    (CHRONICLE, "stormhold", "crest", (280, 822, 316, 860)),
    (CHRONICLE, "starhollow", "crest", (1024, 822, 1062, 860)),
]
CUTS += row(INFOGRAPHIC, "emberfall", ["lysandra", "cassian", "serilda", "lucan", "mathis"],
            [14, 133, 238, 345, 450, 555], 52, 252)
CUTS += row(INFOGRAPHIC, "galenford", ["alaric", "loras", "helena", "darian", "melisande"],
            [784, 912, 1040, 1163, 1288, 1410], 52, 252)
CUTS += row(INFOGRAPHIC, "merewood", ["eldyra", "arlen", "naelia", "torren", "ivor"],
            [14, 145, 262, 388, 513, 638], 398, 574)
CUTS += row(INFOGRAPHIC, "stonehart", ["hale", "derrik", "rowena", "gareth", "brienne"],
            [784, 913, 1040, 1168, 1290, 1410], 398, 574)
CUTS += row(INFOGRAPHIC, "whitecrest", ["marwenna", "taland", "elys", "caelan", "rhett"],
            [14, 145, 268, 390, 517, 640], 730, 926)
CUTS += row(INFOGRAPHIC, "blackvale", ["varric", "malric", "selene", "neran", "isolde"],
            [784, 915, 1040, 1168, 1290, 1410], 730, 926)
CUTS += row(CHRONICLE, "willowsong", ["aelwyn", "lyrin", "caelia", "naren", "thalia"],
            [784, 960, 1085, 1235, 1380, 1530], 668, 752)
CUTS += row(CHRONICLE, "stormhold", ["draven", "xeon", "nyra", "vale"],
            [14, 230, 360, 488, 615], 860, 952)
CUTS += row(CHRONICLE, "starhollow", ["mirelle", "orien", "selene", "aurel", "cassian"],
            [784, 968, 1100, 1240, 1385, 1530], 860, 952)
# Faces for those born in the game (and spouses from minor families): column i is one person,
# a child on top and grown up below; even columns are boys, odd ones girls.
for i in range(6):
    CUTS.append((CASTING, "common", f"child_{i}", (i * 256 + 4, 4, i * 256 + 252, 505)))
    CUTS.append((CASTING, "common", f"adult_{i}", (i * 256 + 4, 516, i * 256 + 252, 1020)))


def cut(image: Image.Image, box: tuple, crest: bool) -> Image.Image:
    x0, y0, x1, y1 = box
    piece = image.crop(box)
    if crest:  # a crest keeps its own shape, on a square
        piece.thumbnail((160, 160))
        return piece
    w, h = x1 - x0, y1 - y0
    want_h = round(w * SIZE[1] / SIZE[0])
    if want_h <= h:  # tall enough: keep the top, where the face is
        piece = piece.crop((0, 0, w, want_h))
    else:  # too short: keep the middle of its width
        want_w = round(h * SIZE[0] / SIZE[1])
        left = (w - want_w) // 2
        piece = piece.crop((left, 0, left + want_w, h))
    return piece.resize(SIZE, Image.LANCZOS)


def main() -> None:
    boards: dict[str, Image.Image] = {}
    crops = []
    for board, house, name, box in CUTS:
        if board not in boards:
            boards[board] = Image.open(os.path.join(BOARDS, board)).convert("RGB")
        picture = cut(boards[board], box, name == "crest")
        folder = os.path.join(OUT, house)
        os.makedirs(folder, exist_ok=True)
        picture.save(os.path.join(folder, name + ".png"))
        crops.append((f"{house}/{name}", picture))
    print(f"{len(crops)} pictures in {os.path.relpath(OUT, ROOT)}")
    if "--sheet" in sys.argv:
        cols = 12
        cell = (100, 125)
        sheet = Image.new("RGB", (cols * cell[0], -(-len(crops) // cols) * cell[1]), "white")
        for i, (_, picture) in enumerate(crops):
            thumb = picture.copy()
            thumb.thumbnail(cell)
            sheet.paste(thumb, ((i % cols) * cell[0], (i // cols) * cell[1]))
        path = sys.argv[sys.argv.index("--sheet") + 1] if len(sys.argv) > sys.argv.index("--sheet") + 1 else "sheet.png"
        sheet.save(path)
        print("sheet:", path)


if __name__ == "__main__":
    main()
