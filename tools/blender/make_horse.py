"""Builds the horse the cavalry and mounted generals ride, and writes it with idle, walk and
trot animations to godot/assets/adventurers/civsim_horse.glb. Run from the repository root:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender/make_horse.py

A faceted low-poly horse after the user's reference picture: a deep chest and a dipped back,
a high arched neck under a black mane, a long head with a white blaze, slim legs with knees,
hocks and fetlocks, black hooves, and a black tail. Body, neck, head, legs and tail are each
lofted through cross-sections (twelve-sided, shaded smooth). It is painted from the Adventurers
knight's texture, light on top and darker below, so horse and rider share one material; a
saddle cloth in the owner's colour (the texture's team cell) and a saddle are added. Each part
is rigid on one bone; it faces -y, like the pack's characters, and a rider sits on "saddle".
"""

import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
from make_models import KNIGHT, Model  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "godot", "assets", "adventurers", "civsim_horse.glb")
FPS = 30
CELLS = dict(KNIGHT, coat=(5, 0), dark=(2, 0), muzzle=(6, 0), cloth=(0, 1), steel=(3, 0), blaze=(1, 1))
LEGS = ("fl", "fr", "bl", "br")
SIDES = 12  # sides of each cross-section: enough to read as rounded

# The trunk (body, neck and head) is one mesh, lofted from rump to muzzle through cross-sections
# set by the horse's side outline: for each, a point on the top line (back, withers, crest of
# the neck, poll, then the line of the face) and one on the bottom line (belly, chest, the front
# of the neck, the throat, then the jaw and chin), as (y, z), and half its width. Each section
# spans the two points, so the neck flows out of the chest and into the head with no seam.
# The bone each section moves with is given too.
TRUNK = [
    ((0.70, 0.92), (0.70, 0.76), 0.07, "body"),     # the point of the rump
    ((0.64, 1.02), (0.64, 0.60), 0.16, "body"),
    ((0.52, 1.05), (0.52, 0.53), 0.22, "body"),     # quarters
    ((0.32, 1.03), (0.32, 0.51), 0.22, "body"),
    ((0.10, 1.00), (0.10, 0.49), 0.21, "body"),     # the dip of the back
    ((-0.12, 1.02), (-0.12, 0.46), 0.22, "body"),
    ((-0.30, 1.09), (-0.32, 0.45), 0.21, "body"),   # withers and girth
    ((-0.38, 1.14), (-0.48, 0.48), 0.19, "body"),   # shoulder
    ((-0.44, 1.21), (-0.59, 0.62), 0.16, "neck"),   # the base of the neck and the breast
    ((-0.50, 1.31), (-0.66, 0.82), 0.125, "neck"),
    ((-0.56, 1.42), (-0.70, 1.00), 0.105, "neck"),
    ((-0.62, 1.52), (-0.73, 1.17), 0.088, "neck"),  # the neck tapers up to the throat
    ((-0.68, 1.60), (-0.79, 1.31), 0.08, "head"),   # poll and throatlatch
    ((-0.78, 1.61), (-0.89, 1.24), 0.094, "head"),  # forehead and the deep round of the jaw
    ((-0.88, 1.52), (-0.95, 1.21), 0.082, "head"),
    ((-0.97, 1.42), (-1.01, 1.18), 0.074, "head"),  # down the face
    ((-1.04, 1.34), (-1.06, 1.13), 0.082, "head"),  # the muzzle, fuller
    ((-1.085, 1.28), (-1.085, 1.15), 0.072, "head"),  # its blunt end
]
MANE = range(6, 13)  # the sections the mane runs along, withers to poll
MANE_HEIGHT = 0.07  # how far the mane stands up from the crest


def section(i: int) -> tuple[Vector, Vector, float, float, Vector]:
    """Section i of the trunk: its centre, its top point, half its depth, half its width, and
    the direction from its bottom to its top."""
    (ty, tz), (by, bz), width, _bone = TRUNK[i]
    top, bottom = Vector((0, ty, tz)), Vector((0, by, bz))
    return (top + bottom) / 2, top, (top - bottom).length / 2, width, (top - bottom).normalized()


def surface(at: float, angle: float) -> tuple[Vector, Vector]:
    """A point on the trunk's surface and the way out from it: `at` sections along (fractions
    between them), `angle` round the section (0 the right side, 90 the top, 180 the left)."""
    i = min(int(at), len(TRUNK) - 2)
    t = at - i
    a, b = section(i), section(i + 1)
    centre = a[0].lerp(b[0], t)
    up = a[4].lerp(b[4], t).normalized()
    depth, width = a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t
    side = Vector((1, 0, 0))
    r = math.radians(angle)
    point = centre + side * (math.cos(r) * width) + up * (math.sin(r) * depth)
    out = (side * (math.cos(r) / width) + up * (math.sin(r) / depth)).normalized()
    return point, out


def decal(m: Model, cell: str, at: float, angle: float, size: tuple, sink: float = 0.4) -> None:
    """A small flat patch (eye, nostril) laid on the trunk's surface, `size` (across, along,
    thick), sunk `sink` of its thickness into it so it reads as part of the face."""
    import bmesh
    point, out = surface(at, angle)
    ahead = (surface(at + 0.05, angle)[0] - surface(at - 0.05, angle)[0]).normalized()
    across = out.cross(ahead).normalized()
    ahead = across.cross(out).normalized()
    geom = bmesh.ops.create_cube(m.bm, size=1.0)["verts"]
    frame = Matrix((across * size[0], ahead * size[1], out * size[2])).transposed().to_4x4()
    frame.translation = point + out * (size[2] * (0.5 - sink))
    bmesh.ops.transform(m.bm, matrix=frame, verts=geom)
    faces = list({f for v in geom for f in v.link_faces})
    bmesh.ops.recalc_face_normals(m.bm, faces=faces)  # facing out, whichever way the frame turned
    m._paint(faces, cell, 0.2)


TAIL = [(0.65, 0.9, 0.04, 0.05), (0.72, 0.78, 0.045, 0.055), (0.76, 0.6, 0.04, 0.05), (0.77, 0.45, 0.02, 0.025)]
# Each leg: where it leaves the body, its joint (knee or hock), fetlock and the ground, with
# the thickness at each. Front legs are straight; hind legs bend back at the hock.
FRONT = [((0.0, 0.0, 0.72), 0.075), ((0.0, 0.0, 0.42), 0.05), ((0.0, 0.0, 0.38), 0.048),
         ((0.0, 0.01, 0.14), 0.034), ((0.0, 0.0, 0.11), 0.04), ((0.0, -0.02, 0.06), 0.034)]
HIND = [((0.0, 0.0, 0.76), 0.09), ((0.0, 0.05, 0.5), 0.06), ((0.0, 0.07, 0.44), 0.05),
        ((0.0, 0.05, 0.15), 0.034), ((0.0, 0.04, 0.11), 0.04), ((0.0, 0.02, 0.06), 0.034)]
LEG_ROOTS = {"fl": (0.11, -0.4), "fr": (-0.11, -0.4), "bl": (0.12, 0.45), "br": (-0.12, 0.45)}


COAT_START = 0.38  # the coat is painted from the deeper end of the texture's brown: a chestnut


def tube(m: Model, cell: str, rings: list, shade: float = 0.7, x: float = 0.0, close: bool = True,
         facing: Vector | None = None, ups: list | None = None, smooth: bool = True) -> list:
    """A loft through rings of (centre, half width, half depth), each eight-sided, square to
    the line it follows (or, with `facing`, all with their depth along it); the ends are closed."""
    bm = m.bm
    centres = [Vector(c) for c, _w, _d in rings]
    made = []
    for i, (centre, width, depth) in enumerate(rings):
        centre = Vector(centre) + Vector((x, 0, 0))
        ahead = (centres[min(i + 1, len(centres) - 1)] - centres[max(i - 1, 0)]).normalized()
        side = Vector((1, 0, 0))
        if ups is not None:
            up = ups[i]
        else:
            up = ahead.cross(side).normalized() if facing is None else facing.normalized()
            if up.z < 0 and facing is None:
                up = -up
        ring = []
        for k in range(SIDES):
            angle = 2 * math.pi * (k + 0.5) / SIDES
            ring.append(bm.verts.new(centre + side * (math.cos(angle) * width) + up * (math.sin(angle) * depth)))
        made.append(ring)
    faces = []
    for a, b in zip(made, made[1:]):
        for k in range(SIDES):
            faces.append(bm.faces.new((a[k], a[(k + 1) % SIDES], b[(k + 1) % SIDES], b[k])))
    if close:
        faces.append(bm.faces.new(made[0]))
        faces.append(bm.faces.new(made[-1][::-1]))
    import bmesh
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    m._paint(faces, cell, min(shade, 1.0 - COAT_START), COAT_START if cell == "coat" else 0.0)
    for face in faces:
        face.smooth = smooth  # shaded smooth: the body reads as one rounded form, not a set of facets
    return made


def leg_rings(leg: str, which: str) -> list:
    """A leg's rings for its upper part (to the knee or hock) or its lower (to the ground)."""
    x, y = LEG_ROOTS[leg]
    shape = FRONT if leg.startswith("f") else HIND
    points = [((x + p[0], y + p[1], p[2]), r, r) for p, r in shape]
    return points[:3] if which == "upper" else points[2:]


def parts(bone: str, m: Model) -> None:
    """What hangs on each bone."""
    if bone == "body":  # (the trunk itself is built in trunk())
        m.box("cloth", (0.46, 0.42, 0.035), at=(0, -0.05, 1.03), shade=0.3)  # saddle cloth over the back
        for side in (-1, 1):  # and down each flank
            m.box("cloth", (0.02, 0.4, 0.2), at=(side * 0.225, -0.05, 0.84), shade=0.4)
        m.box("leather", (0.26, 0.3, 0.07), at=(0, -0.05, 1.06))  # the saddle
        m.box("leather", (0.22, 0.06, 0.09), at=(0, -0.19, 1.09))  # its pommel
    elif bone == "head":
        poll = section(12)[1]
        for angle in (35, 145):  # eyes high on the sides, nostrils at the front of the muzzle
            decal(m, "dark", 13.35, angle, (0.032, 0.042, 0.012))
            decal(m, "dark", 16.55, 62 if angle < 90 else 118, (0.024, 0.04, 0.012))
        for side in (-1, 1):
            m.cylinder("coat", 0.03, 0.14, at=(side * 0.045, poll.y - 0.03, poll.z - 0.035), segments=4,
                       top=0.0)  # ears, standing from the poll
    elif bone == "tail":
        tube(m, "dark", [((0, y, z), w, d) for y, z, w, d in TAIL], shade=0.3)
    elif bone.startswith("upper_"):
        tube(m, "coat", leg_rings(bone[6:], "upper"), shade=0.5)
    elif bone.startswith("lower_"):
        rings = leg_rings(bone[6:], "lower")
        tube(m, "coat", rings, shade=0.5)  # down through the fetlock to the pastern
        (hx, hy, _hz), _r, _ = rings[-1]
        m.cylinder("dark", 0.05, 0.08, at=(hx, hy - 0.01, 0.0), segments=8, top=0.036, shade=0.3)  # the hoof, under it


def trunk() -> bpy.types.Object:
    """The body, neck and head as one smooth mesh, with the mane and the blaze laid along it.
    Each section's vertices move with that section's bone."""
    m = Model(CELLS)
    groups: dict[str, list[int]] = {}

    def note(rings: list, bones: list) -> None:
        for ring, bone in zip(rings, bones):
            groups.setdefault(bone, []).extend(v.index for v in ring)

    sections = [section(i) for i in range(len(TRUNK))]
    bones = [bone for _t, _b, _w, bone in TRUNK]
    m.bm.verts.index_update()
    rings = tube(m, "coat", [(c, w, d) for c, _top, d, w, _up in sections], shade=0.75,
                 ups=[up for *_rest, up in sections])
    m.bm.verts.index_update()
    note(rings, bones)
    # The mane: a ridge along the crest, from the withers to the poll, standing up off it.
    mane = [sections[i] for i in MANE]
    rings = tube(m, "dark", [(top + up * (MANE_HEIGHT * 0.45), 0.03 if k else 0.015, MANE_HEIGHT * 0.6)
                             for k, (_c, top, _d, _w, up) in enumerate(mane)],
                 shade=0.3, ups=[up for *_rest, up in mane], smooth=False)
    m.bm.verts.index_update()
    note(rings, [bones[i] for i in MANE])
    # The blaze: a white stripe down the line of the face.
    face = [sections[i] for i in range(13, 17)]
    rings = tube(m, "blaze", [(top - up * (d * 0.03), 0.017, 0.004) for _c, top, d, _w, up in face], shade=0.2,
                 ups=[up for *_rest, up in face], smooth=False)
    m.bm.verts.index_update()
    note(rings, ["head"] * len(face))
    mesh = bpy.data.meshes.new("Trunk")
    m.bm.normal_update()
    m.bm.to_mesh(mesh)
    m.bm.free()
    obj = bpy.data.objects.new("Trunk", mesh)
    bpy.context.scene.collection.objects.link(obj)
    for bone, indices in groups.items():
        obj.vertex_groups.new(name=bone).add(indices, 1.0, "REPLACE")
    return obj


def bones() -> dict:
    """name -> (head, tail, parent)."""
    out = {
        "root": ((0, 0, 0), (0, 0, 0.3), None),
        "body": ((0, 0.6, 0.82), (0, -0.5, 0.86), "root"),
        "neck": (tuple(section(8)[0]), tuple(section(12)[0]), "body"),
        "head": (tuple(section(12)[0]), tuple(section(17)[0]), "neck"),
        "tail": ((0, 0.65, 0.92), (0, 0.76, 0.5), "body"),
        "saddle": ((0, -0.05, 1.07), (0, -0.05, 1.27), "body"),
    }
    for leg in LEGS:
        x, y = LEG_ROOTS[leg]
        shape = FRONT if leg.startswith("f") else HIND
        top, joint, ground = shape[0][0], shape[2][0], shape[-1][0]
        out[f"upper_{leg}"] = ((x, y + top[1], top[2]), (x, y + joint[1], joint[2]), "body")
        out[f"lower_{leg}"] = ((x, y + joint[1], joint[2]), (x, y + ground[1], 0.0), f"upper_{leg}")
    return out


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    layout = bones()
    data = bpy.data.armatures.new("Horse")
    rig = bpy.data.objects.new("Horse", data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, _parent) in layout.items():
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = Vector(head), Vector(tail)
        bone.roll = 0.0
    for name, (_head, _tail, parent) in layout.items():
        if parent:
            data.edit_bones[name].parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")

    pieces = [trunk()]
    for name in layout:
        m = Model(CELLS)
        parts(name, m)
        if not m.bm.verts:
            m.bm.free()
            continue
        mesh = bpy.data.meshes.new(name)
        m.bm.normal_update()
        m.bm.to_mesh(mesh)
        m.bm.free()
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        group = obj.vertex_groups.new(name=name)
        group.add(range(len(mesh.vertices)), 1.0, "REPLACE")
        pieces.append(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in pieces:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    bpy.ops.object.join()
    body = bpy.context.view_layer.objects.active
    body.name = "Horse_Body"
    body.parent = rig
    modifier = body.modifiers.new("Armature", "ARMATURE")
    modifier.object = rig
    return rig, body


def animate(rig) -> None:
    """Idle, walk and trot, each a loop: legs swing in diagonal pairs, the body bobs."""
    rig.animation_data_create()
    for bone in rig.pose.bones:
        bone.rotation_mode = "XYZ"

    def cycle(name: str, length: float, swing: float, lift: float, bob: float, nod: float, steps: int = 8):
        action = bpy.data.actions.new(name)
        rig.animation_data.action = action
        for i in range(steps + 1):
            t = i / steps
            frame = round(t * length * FPS)
            phase = t * 2 * math.pi
            for leg in LEGS:
                pair = 0.0 if leg in ("fl", "br") else math.pi  # diagonal pairs move together
                angle = swing * math.sin(phase + pair)
                rig.pose.bones[f"upper_{leg}"].rotation_euler = (angle, 0, 0)
                # The lower leg folds as the leg comes forward.
                fold = lift * max(0.0, math.sin(phase + pair + math.pi / 2))
                rig.pose.bones[f"lower_{leg}"].rotation_euler = (-fold, 0, 0)
            rig.pose.bones["root"].location = (0, 0, bob * abs(math.sin(phase)))
            rig.pose.bones["neck"].rotation_euler = (nod * math.sin(phase * 2), 0, 0)
            rig.pose.bones["tail"].rotation_euler = (0, 0, 0.15 * math.sin(phase))
            for bone in rig.pose.bones:
                bone.keyframe_insert("rotation_euler", frame=frame)
                bone.keyframe_insert("location", frame=frame)
        action.use_fake_user = True

    def idle():
        action = bpy.data.actions.new("Idle")
        rig.animation_data.action = action
        for i in range(9):
            t = i / 8
            phase = t * 2 * math.pi
            rig.pose.bones["neck"].rotation_euler = (0.12 * math.sin(phase), 0, 0)
            rig.pose.bones["head"].rotation_euler = (0.08 * math.sin(phase + 1.0), 0, 0)
            rig.pose.bones["tail"].rotation_euler = (0, 0, 0.25 * math.sin(phase * 2))
            for leg in LEGS:
                rig.pose.bones[f"upper_{leg}"].rotation_euler = (0, 0, 0)
                rig.pose.bones[f"lower_{leg}"].rotation_euler = (0, 0, 0)
            rig.pose.bones["root"].location = (0, 0, 0)
            frame = round(t * 3.0 * FPS)
            for bone in rig.pose.bones:
                bone.keyframe_insert("rotation_euler", frame=frame)
                bone.keyframe_insert("location", frame=frame)
        action.use_fake_user = True

    idle()
    cycle("Walk", 1.0, 0.32, 0.5, 0.03, 0.06)
    cycle("Trot", 0.6, 0.5, 0.8, 0.07, 0.1)
    rig.animation_data.action = bpy.data.actions["Idle"]


def main() -> None:
    rig, body = build()
    animate(rig)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_materials="NONE",
                              export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
                              export_frame_range=False, export_yup=True)
    print("made", OUT)


if __name__ == "__main__":
    main()
