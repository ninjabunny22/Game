"""Builds CivSim's own models in Blender, in the style of the KayKit packs, and exports them as
glTF into godot/assets. Run from the repository root:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender/make_models.py

Every part is a low-poly primitive, flat shaded, painted from one cell of a pack's colour
texture: light at the top of the part and darker at its foot, the way the pack's own models
are. Buildings and machines use the Medieval Hexagon texture (hexagons_medieval.png), so the
parts painted from its faction cell take each civ's colour like the pack's buildings do. The
spear uses the Adventurers knight's texture, like the other weapons the soldiers hold.
"""

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HEXAGON_OUT = os.path.join(ROOT, "godot", "assets", "kaykit")
ADVENTURER_OUT = os.path.join(ROOT, "godot", "assets", "adventurers")

# Cells of hexagons_medieval.png (8 columns x 4 rows), by what they paint.
HEX = {
    "black": (0, 0), "white": (1, 0), "steel": (2, 0), "stone": (3, 0), "iron": (4, 0),
    "clay": (5, 0), "brick": (6, 0), "rust": (7, 0),
    "sky": (0, 1), "water": (1, 1), "wood": (2, 1), "gold": (3, 1), "leaf": (4, 1), "sand": (5, 1),
    "rock": (6, 1), "timber": (7, 1),
    "hay": (0, 2), "pine": (1, 2), "slate": (2, 2), "plank": (3, 2), "cream": (5, 2), "crimson": (6, 2),
    "blue": (0, 3), "red": (1, 3), "amber": (2, 3), "team": (3, 3), "orange": (4, 3), "linen": (5, 3),
    "taupe": (6, 3), "dark_wood": (7, 3),
}
# Cells of the Adventurers knight_texture.png (8 x 4 as well).
KNIGHT = {"steel": (3, 0), "dark_steel": (4, 0), "leather": (5, 0), "wood": (6, 0), "team": (0, 1)}


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


class Model:
    """Parts gathered into one mesh, each painted from a texture cell."""

    def __init__(self, cells: dict):
        self.cells = cells
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def _paint(self, faces, cell: str, shade: float, start: float = 0.0) -> None:
        col, row = self.cells[cell]
        verts = {v for f in faces for v in f.verts}
        low = min(v.co.z for v in verts)
        high = max(v.co.z for v in verts)
        span = max(high - low, 1e-6)
        u = (col + 0.5) / 8.0
        for face in faces:
            face.smooth = False
            for loop in face.loops:
                # Light at the top of the part, darker at its foot, as the pack paints them.
                t = start + (high - loop.vert.co.z) / span * shade
                v_image = (row + 0.08 + 0.84 * t) / 4.0
                loop[self.uv].uv = (u, 1.0 - v_image)

    def _add(self, geom, cell: str, matrix: Matrix, shade: float) -> None:
        verts = [g for g in geom if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.transform(self.bm, matrix=matrix, verts=verts)
        faces = list({f for v in verts for f in v.link_faces})
        self._paint(faces, cell, shade)

    def box(self, cell, size, at=(0, 0, 0), turn=0.0, tilt=0.0, shade=0.6):
        """A box `size` (x, y, z) with its foot at `at`."""
        geom = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        matrix = (Matrix.Translation(Vector(at)) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Rotation(tilt, 4, "X")
                  @ Matrix.Translation((0, 0, size[2] / 2)) @ Matrix.Diagonal((*size, 1.0)))
        self._add(geom, cell, matrix, shade)

    def cylinder(self, cell, radius, height, at=(0, 0, 0), segments=8, top=None, axis="Z", turn=0.0, shade=0.6):
        """A cylinder (or with `top`, a cone) standing on `at`; `axis` X or Y lays it down."""
        geom = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segments,
                                     radius1=radius, radius2=radius if top is None else top, depth=height)["verts"]
        lay = Matrix.Identity(4)
        if axis == "X":
            lay = Matrix.Rotation(math.pi / 2, 4, "Y")
        elif axis == "Y":
            lay = Matrix.Rotation(math.pi / 2, 4, "X")
        matrix = (Matrix.Translation(Vector(at)) @ Matrix.Rotation(turn, 4, "Z") @ lay
                  @ Matrix.Translation((0, 0, height / 2)))
        self._add(geom, cell, matrix, shade)

    def roof(self, cell, width, depth, height, at=(0, 0, 0), turn=0.0, overhang=0.06, shade=0.5):
        """A gable roof over a `width` x `depth` box, ridge along y."""
        w, d, h = width / 2 + overhang, depth / 2 + overhang, height
        coords = [(-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0), (0, -d, h), (0, d, h)]
        verts = [self.bm.verts.new(c) for c in coords]
        for face in ((0, 1, 4), (2, 3, 5), (0, 4, 5, 3), (1, 2, 5, 4), (0, 3, 2, 1)):
            self.bm.faces.new([verts[i] for i in face])
        matrix = Matrix.Translation(Vector(at)) @ Matrix.Rotation(turn, 4, "Z")
        self._add(verts, cell, matrix, shade)

    def rock(self, cell, radius, height, at=(0, 0, 0), segments=7, squash=1.0, twist=0.0, shade=0.7):
        """A low-poly boulder: a cone cut flat at the top, a little uneven."""
        geom = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segments,
                                     radius1=radius, radius2=radius * 0.45, depth=height)["verts"]
        for i, v in enumerate(geom):
            v.co.x *= 1.0 + 0.12 * math.sin(i * 2.3 + twist)
            v.co.y *= squash * (1.0 + 0.12 * math.cos(i * 1.7 + twist))
        matrix = Matrix.Translation(Vector(at)) @ Matrix.Rotation(twist, 4, "Z") @ Matrix.Translation((0, 0, height / 2))
        self._add(geom, cell, matrix, shade)

    def _hull_rings(self, sections, inset=0.0):
        rings = []
        for y, w, keel, top in sections:
            w, keel = w * (1.0 - inset), keel + inset * (top - keel)
            mid = keel + (top - keel) * 0.45
            ring = [(-w, y, top), (-w * 0.98, y, mid + (top - mid) * 0.5), (-w * 0.85, y, mid),
                    (-w * 0.5, y, keel + (mid - keel) * 0.25), (0.0, y, keel),
                    (w * 0.5, y, keel + (mid - keel) * 0.25), (w * 0.85, y, mid),
                    (w * 0.98, y, mid + (top - mid) * 0.5), (w, y, top)]
            rings.append([self.bm.verts.new(p) for p in ring])
        return rings

    def loft(self, cell, sections, shade=0.7, lining=None, inset=0.1):
        """A rounded hull through cross-sections (y, half-width, keel height, gunwale height),
        each a U of nine points; the ends are closed. With `lining` (a cell) the hull has an
        inside too, and a rim along the gunwale, so it is not seen through from above."""
        rings = self._hull_rings(sections)
        faces = []
        for a, b in zip(rings, rings[1:]):
            for i in range(len(a) - 1):
                faces.append(self.bm.faces.new((a[i], a[i + 1], b[i + 1], b[i])))
        faces.append(self.bm.faces.new(rings[0][::-1]))
        faces.append(self.bm.faces.new(rings[-1]))
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        self._add([v for ring in rings for v in ring], cell, Matrix.Identity(4), shade)
        if lining is None:
            return
        inner = self._hull_rings(sections, inset)
        for a, b in zip(inner, inner[1:]):  # wound to face inward and up
            for i in range(len(a) - 1):
                self.bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
        self.bm.faces.new(inner[0])  # the inside of the bow ...
        self.bm.faces.new(inner[-1][::-1])  # ... and of the stern
        for (oa, ia), (ob, ib) in zip(zip(rings, inner), zip(rings[1:], inner[1:])):
            self.bm.faces.new((oa[0], ia[0], ib[0], ob[0]))  # the rim, port ...
            self.bm.faces.new((oa[-1], ob[-1], ib[-1], ia[-1]))  # ... and starboard
        self._add([v for ring in inner for v in ring], lining, Matrix.Identity(4), shade)

    def deck(self, cell, sections, z, inset=0.1, shade=0.3):
        """A deck at height `z` inside a hull lofted through `sections` with a lining at `inset`:
        cut to the hull's own outline there, coming to a point where the keel rises to meet it."""
        def half_width(w, keel, top):
            w, keel = w * (1.0 - inset), keel + inset * (top - keel)
            mid = keel + (top - keel) * 0.45
            profile = [(0.0, keel), (w * 0.5, keel + (mid - keel) * 0.25), (w * 0.85, mid),
                       (w * 0.98, mid + (top - mid) * 0.5), (w, top)]
            for (x0, z0), (x1, z1) in zip(profile, profile[1:]):
                if z0 <= z <= z1:
                    return x0 + (x1 - x0) * (z - z0) / max(z1 - z0, 1e-9)
            return w if z > top else None  # None: the keel is above the deck here

        outline = []  # (y, half-width), bow to stern
        previous = None
        for y, w, keel, top in sections:
            width = half_width(w, keel, top)
            for other, here in ((previous, (y, w, keel, top)), ((y, w, keel, top), previous)):
                # Where the keel crosses the deck between two sections, the deck comes to a point.
                if other is not None and here is not None and (half_width(*other[1:]) is None) != (width is None) \
                        and half_width(*here[1:]) is not None and other[2] != here[2]:
                    t = (z - (other[2] + inset * (other[3] - other[2]))) / (
                        (here[2] + inset * (here[3] - here[2])) - (other[2] + inset * (other[3] - other[2])))
                    outline.append((other[0] + (here[0] - other[0]) * min(max(t, 0.0), 1.0), 0.0))
            if width is not None:
                outline.append((y, width * 0.99))
            previous = (y, w, keel, top)
        outline.sort()
        verts = []
        for (y0, w0), (y1, w1) in zip(outline, outline[1:]):
            corners = [(-w0, y0, z), (w0, y0, z), (w1, y1, z), (-w1, y1, z)]
            if w0 == 0.0:
                corners = corners[1:]
            elif w1 == 0.0:
                corners = corners[:3]
            face = [self.bm.verts.new(c) for c in corners]
            self.bm.faces.new(face)  # wound to face up
            verts += face
        self._add(verts, cell, Matrix.Identity(4), shade)

    def hull(self, cell, length, width, height, at=(0, 0, 0), shade=0.7):
        """A ship's hull, bow toward -y (forward in Godot), stern at +y."""
        l, w, h = length / 2, width / 2, height
        coords = [
            (0, -l, h * 1.15),                      # 0 bow, raised
            (-w, -l * 0.45, h), (w, -l * 0.45, h),  # 1, 2 forward of the beam
            (-w, l * 0.55, h), (w, l * 0.55, h),    # 3, 4 aft of the beam
            (-w * 0.6, l, h * 1.05), (w * 0.6, l, h * 1.05),  # 5, 6 stern
            (0, -l * 0.8, 0.0),                     # 7 keel at the bow
            (-w * 0.35, -l * 0.3, 0.0), (w * 0.35, -l * 0.3, 0.0),
            (-w * 0.35, l * 0.6, 0.0), (w * 0.35, l * 0.6, 0.0),
        ]
        v = [self.bm.verts.new(c) for c in coords]
        faces = [(0, 1, 2), (1, 3, 4, 2), (3, 5, 6, 4),          # deck line
                 (0, 7, 8, 1), (0, 2, 9, 7), (1, 8, 10, 3), (2, 4, 11, 9), (3, 10, 5), (4, 6, 11),
                 (5, 10, 11, 6), (7, 9, 11, 10, 8)]
        for face in faces:
            self.bm.faces.new([v[i] for i in face])
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[-len(faces):])
        self._add(v, cell, Matrix.Translation(Vector(at)), shade)

    def export(self, name: str, folder: str) -> None:
        mesh = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(mesh)
        self.bm.free()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        for other in bpy.context.scene.objects:
            other.select_set(other is obj)
        bpy.context.view_layer.objects.active = obj
        path = os.path.join(folder, name + ".gltf")
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLTF_SEPARATE", use_selection=True,
                                  export_materials="NONE", export_apply=True, export_yup=True)
        bpy.data.objects.remove(obj)
        print("made", path)


# -- the models ------------------------------------------------------------------------------

def gold_mine() -> None:
    """A gold mine on its vein: a rocky mound with a timbered adit, a rail out to a cart heaped
    with gold, ore piles, and the holder's pennant. About 1.9 across."""
    m = Model(HEX)
    m.rock("rock", 0.82, 0.75, at=(0.1, 0.25, 0), segments=7, twist=0.4)
    m.rock("stone", 0.55, 0.55, at=(-0.45, 0.45, 0), segments=6, twist=1.3)
    m.rock("rock", 0.4, 0.85, at=(0.5, 0.5, 0.2), segments=6, twist=2.1)
    m.rock("gold", 0.12, 0.1, at=(-0.2, 0.05, 0.62), segments=5, twist=0.3, shade=0.4)
    m.rock("gold", 0.09, 0.08, at=(0.38, 0.0, 0.5), segments=5, twist=1.1, shade=0.4)
    # The adit: a dark mouth framed in timber, facing the front (-y).
    m.box("black", (0.4, 0.12, 0.42), at=(0.0, -0.5, 0))
    for side in (-0.23, 0.23):
        m.box("wood", (0.08, 0.08, 0.5), at=(side, -0.58, 0))
    m.box("wood", (0.6, 0.1, 0.09), at=(0.0, -0.58, 0.48))
    # Rails out of the mine and a cart of gold on them.
    for side in (-0.1, 0.1):
        m.box("iron", (0.03, 0.75, 0.03), at=(side, -0.95, 0))
    for i in range(5):
        m.box("timber", (0.3, 0.05, 0.02), at=(0, -0.65 - i * 0.15, 0))
    m.box("wood", (0.26, 0.34, 0.16), at=(0.0, -1.05, 0.07))
    for x in (-0.15, 0.15):
        for y in (-0.95, -1.15):
            m.cylinder("iron", 0.055, 0.04, at=(x, y, 0.055), axis="X", segments=8)
    for i, (x, y) in enumerate(((-0.06, -1.0), (0.06, -1.1), (0.0, -1.05), (0.05, -0.98))):
        m.rock("gold", 0.07, 0.07, at=(x, y, 0.21), segments=5, twist=i, shade=0.35)
    # Heaps of ore beside the mouth.
    m.rock("gold", 0.18, 0.14, at=(-0.55, -0.55, 0), segments=6, twist=0.7, shade=0.5)
    m.rock("amber", 0.14, 0.1, at=(-0.42, -0.78, 0), segments=5, twist=2.2, shade=0.5)
    m.rock("gold", 0.15, 0.12, at=(0.55, -0.6, 0), segments=6, twist=1.7, shade=0.5)
    # A pennant in the holder's colour.
    m.cylinder("timber", 0.02, 0.9, at=(0.62, 0.15, 0.6), segments=6)
    m.box("team", (0.02, 0.26, 0.16), at=(0.62, 0.02, 1.32), shade=0.3)
    m.export("civsim_gold_mine", HEXAGON_OUT)


def ship() -> None:
    """A three-masted cog, as a war fleet's flagship: a deep, round wooden hull rising to a
    castle at the stern, a bowsprit, white sails striped in the owner's colour on all three
    masts, a crow's nest on the mainmast and pennants at the mastheads. No one stands on deck:
    an army at sea is shown as its ship alone. About 2 long, bow forward."""
    m = Model(HEX)
    # The hull, lofted through cross-sections from bow (-y) to stern (+y):
    # (y, half-width, keel height, gunwale height).
    sections = [(-1.0, 0.04, 0.42, 0.62), (-0.82, 0.22, 0.12, 0.5), (-0.5, 0.36, 0.02, 0.44),
                (0.0, 0.4, 0.0, 0.42), (0.45, 0.37, 0.03, 0.5), (0.78, 0.3, 0.12, 0.7),
                (0.95, 0.24, 0.25, 0.74)]
    m.loft("clay", sections, lining="brick", inset=0.07)
    m.deck("plank", sections, 0.38, inset=0.07)  # cut to the hull, so no corner shows through it
    m.box("brick", (0.62, 0.05, 0.06), at=(0, -0.58, 0.43))  # a wale across the bow
    m.box("clay", (0.5, 0.42, 0.24), at=(0, 0.72, 0.5))  # the stern castle
    m.box("brick", (0.54, 0.46, 0.05), at=(0, 0.72, 0.74))  # its rail
    m.box("water", (0.3, 0.02, 0.1), at=(0, 0.935, 0.55), shade=0.2)  # its windows, astern
    m.box("timber", (0.06, 0.62, 0.06), at=(0, -1.07, 0.6), tilt=-0.43)  # the bowsprit, rising forward from the foredeck
    # Masts: (y, height, sails as (width, height) from the bottom up).
    masts = [(-0.48, 1.35, [(0.62, 0.36), (0.5, 0.3)]),
             (0.05, 1.75, [(0.82, 0.46), (0.66, 0.36)]),
             (0.55, 1.4, [(0.6, 0.34), (0.48, 0.28)])]
    for y, height, sails in masts:
        m.cylinder("timber", 0.035, height, at=(0, y, 0.36), segments=6)
        z = 0.62
        for width, sail_height in sails:
            m.box("timber", (width + 0.08, 0.035, 0.035), at=(0, y - 0.01, z + sail_height))  # its yard
            m.box("white", (width, 0.03, sail_height), at=(0, y - 0.05, z), shade=0.35)  # the sail
            for x in (-width * 0.22, width * 0.22):  # two stripes in the owner's colour
                m.box("team", (width * 0.13, 0.05, sail_height * 0.98), at=(x, y - 0.05, z + 0.003), shade=0.35)
            z += sail_height + 0.07
        m.box("team", (0.02, 0.16, 0.08), at=(0, y + 0.08, 0.36 + height - 0.1), shade=0.3)  # a pennant
    m.cylinder("wood", 0.09, 0.08, at=(0, 0.05, 0.36 + 1.75 - 0.42), segments=8)  # the crow's nest
    m.export("civsim_ship", HEXAGON_OUT)


def fishing_boat() -> None:
    """A villager's boat for crossing water: a small open hull with two benches, a basket of
    the day's catch in the bow and a short mast whose sail carries the owner's colour. No one
    is drawn aboard, as with the ship; the oars are their own model (oar), so they can row.
    About 1 long, bow forward."""
    m = Model(HEX)
    m.loft("clay", [(-0.5, 0.02, 0.15, 0.27), (-0.36, 0.13, 0.04, 0.215), (-0.1, 0.2, 0.0, 0.19),
                    (0.2, 0.2, 0.0, 0.19), (0.42, 0.15, 0.03, 0.21), (0.5, 0.1, 0.08, 0.235)],
           lining="brick")
    m.box("plank", (0.24, 0.56, 0.02), at=(0, 0.06, 0.085), shade=0.3)  # the bottom boards ...
    m.box("plank", (0.1, 0.18, 0.02), at=(0, -0.31, 0.105), shade=0.3)  # ... and the bow's, higher
    for side in (-1, 1):
        m.box("iron", (0.03, 0.03, 0.035), at=(side * 0.19, 0.1, 0.19))  # a rowlock
    m.box("timber", (0.38, 0.07, 0.02), at=(0, 0.28, 0.15))  # the stern bench
    m.box("timber", (0.34, 0.06, 0.02), at=(0, -0.2, 0.15))  # the mast bench
    m.cylinder("hay", 0.055, 0.07, at=(0, -0.33, 0.125), segments=7, top=0.065)  # the basket ...
    m.box("steel", (0.07, 0.035, 0.02), at=(0.01, -0.33, 0.19), turn=0.5)  # ... and a fish in it
    m.cylinder("timber", 0.016, 0.6, at=(0, -0.2, 0.1), segments=6)  # the mast
    m.box("timber", (0.36, 0.02, 0.02), at=(0, -0.2, 0.64))  # its yard
    m.box("white", (0.32, 0.014, 0.3), at=(0, -0.222, 0.335), shade=0.35)  # the sail
    m.box("team", (0.1, 0.022, 0.296), at=(0, -0.222, 0.337), shade=0.35)  # a stripe in the owner's colour
    m.box("team", (0.012, 0.09, 0.045), at=(0, -0.15, 0.655), shade=0.3)  # a pennant
    m.export("civsim_fishing_boat", HEXAGON_OUT)


def oar() -> None:
    """One oar of the fishing boat, pivoting at its rowlock (the origin): the shaft runs
    outboard along +x to the blade, with the handle a little inboard."""
    m = Model(HEX)
    m.cylinder("timber", 0.012, 0.5, at=(-0.1, 0, 0), segments=5, axis="X")
    m.box("plank", (0.15, 0.012, 0.06), at=(0.455, 0, -0.03), shade=0.3)  # the blade
    m.export("civsim_oar", HEXAGON_OUT)


def harbour() -> None:
    """A harbour on a 2 x 2 square: a stone quay on the land side, a timber pier running out
    over the water (+y in Blender, the side that is turned to face the water), a storehouse
    with a roof in the owner's colour, a crane over the pier, and cargo."""
    m = Model(HEX)
    m.box("stone", (1.9, 0.9, 0.24), at=(0, -0.5, 0))  # the quay wall
    m.box("rock", (1.84, 0.84, 0.05), at=(0, -0.5, 0.24), shade=0.25)  # its paving
    for i in range(7):
        m.box("slate", (0.24, 0.1, 0.08), at=(-0.84 + i * 0.28, -0.08, 0.26), shade=0.4)  # coping stones
    for x in (-0.7, 0.0):
        m.cylinder("iron", 0.04, 0.1, at=(x, -0.13, 0.33), segments=6)  # bollards
    m.box("plank", (0.55, 1.05, 0.06), at=(0.35, 0.45, 0.22))  # the pier
    for x in (0.12, 0.58):
        for y in (0.1, 0.5, 0.9):
            m.cylinder("dark_wood", 0.045, 0.3, at=(x, y, -0.05), segments=6)
    # The storehouse.
    m.box("cream", (0.72, 0.55, 0.42), at=(-0.45, -0.6, 0.28))
    m.box("timber", (0.76, 0.06, 0.08), at=(-0.45, -0.33, 0.62))
    m.box("dark_wood", (0.2, 0.04, 0.26), at=(-0.45, -0.31, 0.28))  # its door
    m.roof("team", 0.72, 0.55, 0.32, at=(-0.45, -0.6, 0.7), turn=math.pi / 2)
    # A crane over the pier.
    m.box("timber", (0.08, 0.08, 0.85), at=(0.6, -0.15, 0.28))
    m.box("timber", (0.06, 0.6, 0.06), at=(0.6, 0.1, 1.08))
    m.box("iron", (0.015, 0.015, 0.45), at=(0.6, 0.38, 0.65))
    m.box("wood", (0.14, 0.14, 0.12), at=(0.6, 0.38, 0.53))
    # Cargo on the quay.
    for i, (x, y) in enumerate(((0.15, -0.65), (0.35, -0.75), (0.25, -0.45))):
        m.box("wood" if i % 2 else "plank", (0.17, 0.17, 0.17), at=(x, y, 0.28), turn=i * 0.4)
    for x, y in ((-0.85, -0.2), (-0.7, -0.15)):
        m.cylinder("wood", 0.08, 0.2, at=(x, y, 0.28), segments=8)
    m.export("civsim_harbour", HEXAGON_OUT)


def stable() -> None:
    """A stable on a 2 x 2 square: a long timber barn with a roof in the owner's colour, stall
    doors, a fenced paddock, hay, and a water trough."""
    m = Model(HEX)
    m.box("plank", (1.15, 0.7, 0.5), at=(-0.25, 0.3, 0))
    for i in range(4):
        m.box("dark_wood", (0.2, 0.03, 0.32), at=(-0.66 + i * 0.28, -0.06, 0.02))  # stall doors
    for x in (-0.82, 0.32):
        m.box("timber", (0.07, 0.74, 0.56), at=(x, 0.3, 0))
    m.roof("team", 1.15, 0.7, 0.38, at=(-0.25, 0.3, 0.5), turn=math.pi / 2)
    m.box("timber", (0.1, 0.1, 0.12), at=(-0.25, 0.3, 0.86))  # a vent on the ridge
    # The paddock fence.
    posts = [(0.45, -0.85), (0.9, -0.85), (0.9, -0.3), (0.9, 0.25), (0.45, 0.25), (-0.05, -0.85), (-0.55, -0.85)]
    for x, y in posts:
        m.box("timber", (0.05, 0.05, 0.32), at=(x, y, 0))
    for (x1, y1), (x2, y2) in zip(posts[:4], posts[1:5]):
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        length = math.hypot(x2 - x1, y2 - y1)
        turn = math.atan2(x2 - x1, y2 - y1)
        for z in (0.12, 0.25):
            m.box("wood", (0.03, length, 0.03), at=(mid[0], mid[1], z), turn=-turn)
    for x in (-0.3, 0.2):
        m.box("wood", (0.03, 0.5, 0.03), at=(x, -0.85, 0.2), turn=math.pi / 2)
    # Hay and a trough.
    m.cylinder("hay", 0.14, 0.24, at=(0.6, 0.0, 0.14), axis="X", segments=10, shade=0.4)
    m.cylinder("hay", 0.14, 0.24, at=(0.62, -0.15, 0.14), axis="X", segments=10, shade=0.4)
    m.box("wood", (0.45, 0.14, 0.12), at=(0.62, -0.62, 0))
    m.box("water", (0.4, 0.1, 0.02), at=(0.62, -0.62, 0.1), shade=0.2)
    m.export("civsim_stable", HEXAGON_OUT)


def catapult() -> None:
    """A siege catapult: a wheeled timber frame, a throwing arm with its bucket, and a stone
    ready to throw. About 1 long."""
    m = Model(HEX)
    for side in (-0.2, 0.2):
        m.box("wood", (0.07, 0.95, 0.09), at=(side, 0, 0.1))
        for y in (-0.32, 0.32):
            m.cylinder("dark_wood", 0.13, 0.06, at=(side + (0.04 if side > 0 else -0.1), y, 0.13), axis="X", segments=10)
    for y in (-0.38, 0.38):
        m.box("wood", (0.46, 0.07, 0.07), at=(0, y, 0.15))
    # Uprights and the crossbar the arm swings from.
    for side in (-0.17, 0.17):
        m.box("timber", (0.07, 0.07, 0.5), at=(side, 0.05, 0.18), tilt=-0.25)
    m.box("timber", (0.42, 0.07, 0.07), at=(0, -0.05, 0.62))
    m.box("wood", (0.07, 0.95, 0.07), at=(0, 0.1, 0.3), tilt=-0.55)  # the arm, cocked
    m.cylinder("dark_wood", 0.1, 0.06, at=(0, 0.5, 0.58), segments=8)  # its bucket
    m.rock("stone", 0.07, 0.1, at=(0, 0.5, 0.62), segments=5)
    m.box("iron", (0.3, 0.06, 0.12), at=(0, -0.38, 0.22))  # the winch
    m.export("civsim_catapult", HEXAGON_OUT)


def ram() -> None:
    """A battering ram under a roof: a wheeled frame, a slung log with an iron head, and a
    hide roof in the owner's colour. About 1.1 long, the head forward."""
    m = Model(HEX)
    for side in (-0.24, 0.24):
        m.box("wood", (0.07, 1.0, 0.08), at=(side, 0, 0.1))
        for y in (-0.33, 0.33):
            m.cylinder("dark_wood", 0.12, 0.06, at=(side + (0.04 if side > 0 else -0.1), y, 0.12), axis="X", segments=10)
        for y in (-0.42, 0.42):
            m.box("timber", (0.06, 0.06, 0.48), at=(side, y, 0.17))
    m.roof("team", 0.52, 0.95, 0.3, at=(0, 0, 0.62), turn=0.0)
    m.cylinder("timber", 0.08, 1.15, at=(0, -0.05, 0.38), axis="Y", segments=8)  # the log
    m.cylinder("iron", 0.1, 0.12, at=(0, -0.65, 0.38), axis="Y", segments=8, top=0.06)  # its head
    for y in (-0.25, 0.25):
        m.box("iron", (0.015, 0.015, 0.25), at=(0, y, 0.43))  # chains
    m.export("civsim_ram", HEXAGON_OUT)


def spear() -> None:
    """A spear for the foot soldier's hand: a long shaft and a steel head, held at the grip
    like the pack's other weapons (up along the hand's axis)."""
    m = Model(KNIGHT)
    m.cylinder("wood", 0.035, 2.4, at=(0, 0, -0.85), segments=6, shade=0.3)
    m.cylinder("dark_steel", 0.05, 0.08, at=(0, 0, 1.5), segments=6)  # the socket
    m.cylinder("steel", 0.07, 0.38, at=(0, 0, 1.58), segments=4, top=0.0)  # the head
    m.cylinder("leather", 0.045, 0.22, at=(0, 0, -0.1), segments=6)  # the grip
    m.export("civsim_spear", ADVENTURER_OUT)


def bridge() -> None:
    """A bridge's deck over shallow water, one unit long along +y (the way it runs), to be
    stretched from one shore to the other: planks with a kerb and a rail along each side. It has
    nothing that would look wrong stretched; the supports are their own model (bridge_pier)."""
    m = Model(HEX)
    m.box("plank", (0.62, 1.0, 0.07), at=(0, 0, 0.2))  # the deck
    m.box("dark_wood", (0.66, 1.0, 0.05), at=(0, 0, 0.15), shade=0.3)  # the beam under it
    for side in (-1, 1):
        m.box("timber", (0.05, 1.0, 0.06), at=(side * 0.3, 0, 0.27))  # kerb
        m.box("timber", (0.04, 1.0, 0.04), at=(side * 0.3, 0, 0.47))  # rail
    m.export("civsim_bridge", HEXAGON_OUT)


def bridge_pier() -> None:
    """The support under a bridge's deck, set every couple of tiles along it: two piles down
    into the water, a cap beam across, and the posts that carry the rails."""
    m = Model(HEX)
    for side in (-1, 1):
        m.cylinder("dark_wood", 0.05, 0.5, at=(side * 0.24, 0, -0.32), segments=6)  # pile
        m.box("timber", (0.05, 0.05, 0.24), at=(side * 0.3, 0, 0.27))  # rail post
    m.box("dark_wood", (0.7, 0.09, 0.07), at=(0, 0, 0.1))  # cap beam
    m.export("civsim_bridge_pier", HEXAGON_OUT)


if __name__ == "__main__":
    for make in (gold_mine, ship, fishing_boat, oar, harbour, stable, catapult, ram, spear, bridge, bridge_pier):
        reset()
        make()
