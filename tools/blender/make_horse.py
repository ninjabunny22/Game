"""Builds the horse the cavalry and mounted generals ride, and writes it with idle, walk and
trot animations to godot/assets/adventurers/civsim_horse.glb. Run from the repository root:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender/make_horse.py

A faceted low-poly horse after the user's reference picture: a deep chest and a dipped back,
a high arched neck under a black mane, a long head with a white blaze, slim legs with knees,
hocks and fetlocks, black hooves, and a black tail. Body, neck, head, legs and tail are each
lofted through cross-sections (eight-sided, flat shaded). It is painted from the Adventurers
knight's texture, light on top and darker below, so horse and rider share one material; a
saddle cloth in the owner's colour (the texture's team cell) and a saddle are added. Each part
is rigid on one bone; it faces -y, like the pack's characters, and a rider sits on "saddle".
"""

import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
from make_models import KNIGHT, Model  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "godot", "assets", "adventurers", "civsim_horse.glb")
FPS = 30
CELLS = dict(KNIGHT, coat=(5, 0), dark=(2, 0), muzzle=(6, 0), cloth=(0, 1), steel=(3, 0), blaze=(1, 1))
LEGS = ("fl", "fr", "bl", "br")
SIDES = 8

# The body, rump to chest: (y, z of the middle, half its width, half its depth).
BODY = [(0.68, 0.84, 0.08, 0.1), (0.62, 0.82, 0.17, 0.21), (0.5, 0.79, 0.22, 0.26),
        (0.32, 0.77, 0.22, 0.26), (0.1, 0.75, 0.21, 0.26), (-0.12, 0.75, 0.22, 0.29),
        (-0.32, 0.77, 0.21, 0.32), (-0.47, 0.81, 0.17, 0.3), (-0.57, 0.87, 0.1, 0.2)]
# The neck rises forward and up from the withers in an arch: (y, z, half width, half depth).
NECK = [(-0.38, 0.98, 0.15, 0.25), (-0.52, 1.15, 0.125, 0.19), (-0.63, 1.31, 0.1, 0.14),
        (-0.71, 1.44, 0.085, 0.115), (-0.76, 1.53, 0.075, 0.1)]
# The head, from the poll down to the muzzle.
# The head runs from the poll down to the muzzle along HEAD_AXIS. Its front (the line of the
# face) is straight; it is deep at the jaw and cheek, narrows along the face, and swells a
# little at a blunt muzzle. Rings: (share of the length, half width, half depth).
HEAD_POLL = Vector((0.0, -0.74, 1.58))
HEAD_AXIS = Vector((0.0, -0.66, -0.75)).normalized()
HEAD_LENGTH = 0.46
HEAD_JAW = Vector((0.0, -HEAD_AXIS.z, HEAD_AXIS.y))  # square to the axis, toward the jaw (back and down)
HEAD_FACE = 0.06  # how far the line of the face stands from the axis
HEAD = [(0.0, 0.07, 0.065), (0.12, 0.08, 0.125), (0.3, 0.078, 0.12), (0.5, 0.066, 0.085),
        (0.7, 0.064, 0.07), (0.88, 0.078, 0.074), (1.0, 0.072, 0.06)]


def on_head(share: float, toward_jaw: float, x: float = 0.0) -> Vector:
    """A point of the head: `share` of the way from poll to muzzle, `toward_jaw` from the axis."""
    return HEAD_POLL + HEAD_AXIS * (share * HEAD_LENGTH) + HEAD_JAW * toward_jaw + Vector((x, 0, 0))
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
         facing: Vector | None = None) -> None:
    """A loft through rings of (centre, half width, half depth), each eight-sided, square to
    the line it follows (or, with `facing`, all with their depth along it); the ends are closed."""
    bm = m.bm
    centres = [Vector(c) for c, _w, _d in rings]
    made = []
    for i, (centre, width, depth) in enumerate(rings):
        centre = Vector(centre) + Vector((x, 0, 0))
        ahead = (centres[min(i + 1, len(centres) - 1)] - centres[max(i - 1, 0)]).normalized()
        side = Vector((1, 0, 0))
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


def leg_rings(leg: str, which: str) -> list:
    """A leg's rings for its upper part (to the knee or hock) or its lower (to the ground)."""
    x, y = LEG_ROOTS[leg]
    shape = FRONT if leg.startswith("f") else HIND
    points = [((x + p[0], y + p[1], p[2]), r, r) for p, r in shape]
    return points[:3] if which == "upper" else points[2:]


def parts(bone: str, m: Model) -> None:
    """What hangs on each bone."""
    if bone == "body":
        tube(m, "coat", [((0, y, z), w, d) for y, z, w, d in BODY], shade=0.75)
        m.box("cloth", (0.46, 0.42, 0.035), at=(0, -0.05, 1.03), shade=0.3)  # saddle cloth over the back
        for side in (-1, 1):  # and down each flank
            m.box("cloth", (0.02, 0.4, 0.2), at=(side * 0.225, -0.05, 0.84), shade=0.4)
        m.box("leather", (0.26, 0.3, 0.07), at=(0, -0.05, 1.06))  # the saddle
        m.box("leather", (0.22, 0.06, 0.09), at=(0, -0.19, 1.09))  # its pommel
    elif bone == "neck":
        tube(m, "coat", [((0, y, z), w, d) for y, z, w, d in NECK], shade=0.6)
        for (y1, z1, _w, d1), (y2, z2, _w2, d2) in zip(NECK, NECK[1:]):  # the mane along its crest
            mid_y, mid_z = (y1 + y2) / 2, (z1 + d1 + z2 + d2) / 2
            tilt = math.atan2(z2 - z1, -(y2 - y1))
            m.box("dark", (0.06, math.hypot(y2 - y1, z2 - z1) * 1.2, 0.12), at=(0, mid_y + 0.04, mid_z - 0.06),
                  tilt=-tilt + math.pi / 2 - math.pi / 2, shade=0.3)
    elif bone == "head":
        # Each ring sits so that its face side stays on one straight line.
        rings = [(tuple(on_head(s, depth - HEAD_FACE)), w, depth) for s, w, depth in HEAD]
        tube(m, "coat", rings, shade=0.5, facing=-HEAD_JAW)
        along = math.atan2(HEAD_AXIS.z, HEAD_AXIS.y)  # the tilt that lays a box along the head
        m.box("blaze", (0.034, HEAD_LENGTH * 0.72, 0.012), at=tuple(on_head(0.52, -HEAD_FACE - 0.004)), tilt=along,
              shade=0.2)  # a white blaze down the face
        m.box("dark", (0.09, 0.08, 0.008), at=tuple(on_head(0.93, 0.045)), tilt=along, shade=0.3)  # the mouth
        for side in (-1, 1):
            m.box("dark", (0.008, 0.032, 0.024), at=tuple(on_head(0.2, -0.02, side * 0.072)), tilt=along,
                  shade=0.2)  # eyes, set into the sides high up
            m.box("dark", (0.008, 0.026, 0.02), at=tuple(on_head(0.93, -0.025, side * 0.064)), tilt=along,
                  shade=0.2)  # nostrils
            m.cylinder("coat", 0.028, 0.13, at=tuple(on_head(0.04, -0.03, side * 0.038)), segments=4,
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


def bones() -> dict:
    """name -> (head, tail, parent)."""
    out = {
        "root": ((0, 0, 0), (0, 0, 0.3), None),
        "body": ((0, 0.6, 0.82), (0, -0.5, 0.86), "root"),
        "neck": ((0, -0.42, 1.0), (0, -0.76, 1.5), "body"),
        "head": (tuple(HEAD_POLL), tuple(on_head(1.0, 0.0)), "neck"),
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

    pieces = []
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
