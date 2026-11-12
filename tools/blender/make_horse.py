"""Builds a chunky, rigged horse in the Adventurers style and writes it, with idle, walk and
trot animations, to godot/assets/adventurers/civsim_horse.glb. Run from the repository root:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender/make_horse.py

It is painted from the Adventurers knight's texture, like the knight who rides it: a bay
coat, dark mane and hooves, a saddle cloth in the owner's colour (the texture's team cell)
and a steel chamfron. Each part is rigid on one bone. The horse faces -y here, as the pack's
characters do; a rider sits on the "saddle" bone.
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
CELLS = dict(KNIGHT, coat=(5, 0), dark=(2, 0), muzzle=(6, 0), cloth=(0, 1), steel=(3, 0))

# Bones: name -> (head, tail, parent).
BONES = {
    "root": ((0, 0, 0), (0, 0, 0.3), None),
    "body": ((0, 0.45, 0.78), (0, -0.45, 0.78), "root"),
    "neck": ((0, -0.42, 0.92), (0, -0.62, 1.3), "body"),
    "head": ((0, -0.62, 1.3), (0, -0.95, 1.12), "neck"),
    "tail": ((0, 0.5, 0.9), (0, 0.72, 0.5), "body"),
    "saddle": ((0, 0.02, 1.04), (0, 0.02, 1.24), "body"),
}
LEGS = {"fl": (0.16, -0.36), "fr": (-0.16, -0.36), "bl": (0.16, 0.36), "br": (-0.16, 0.36)}
for leg, (x, y) in LEGS.items():
    BONES[f"upper_{leg}"] = ((x, y, 0.62), (x, y, 0.33), "body")
    BONES[f"lower_{leg}"] = ((x, y, 0.33), (x, y, 0.02), f"upper_{leg}")


def parts(bone: str, m: Model) -> None:
    """What hangs on each bone."""
    if bone == "body":
        m.cylinder("coat", 0.27, 1.0, at=(0, 0.5, 0.78), axis="Y", segments=8, shade=0.5)
        m.box("coat", (0.5, 0.32, 0.4), at=(0, -0.4, 0.62))  # the chest
        m.box("cloth", (0.58, 0.5, 0.06), at=(0, 0.02, 0.98), shade=0.3)  # saddle cloth
        m.box("cloth", (0.6, 0.48, 0.28), at=(0, 0.02, 0.74), shade=0.4)  # its hang down the flanks
        m.box("leather", (0.32, 0.36, 0.08), at=(0, 0.02, 1.03))  # the saddle
        m.box("leather", (0.3, 0.06, 0.1), at=(0, -0.16, 1.07))  # its pommel
    elif bone == "neck":
        m.box("coat", (0.24, 0.26, 0.5), at=(0, -0.52, 0.86), tilt=0.5)
        m.box("dark", (0.08, 0.3, 0.5), at=(0, -0.46, 0.94), tilt=0.5)  # mane
    elif bone == "head":
        m.box("coat", (0.22, 0.42, 0.22), at=(0, -0.8, 1.12), tilt=-0.35)
        m.box("muzzle", (0.2, 0.14, 0.18), at=(0, -0.98, 1.0), tilt=-0.35)
        m.box("steel", (0.24, 0.3, 0.06), at=(0, -0.78, 1.25), tilt=-0.35)  # the chamfron
        for x in (-0.07, 0.07):
            m.cylinder("coat", 0.04, 0.12, at=(x, -0.64, 1.3), segments=4, top=0.0)  # ears
    elif bone == "tail":
        m.box("dark", (0.1, 0.12, 0.42), at=(0, 0.6, 0.48), tilt=-0.4)
    elif bone.startswith("upper_"):
        x, y = LEGS[bone[6:]]
        m.cylinder("coat", 0.075, 0.32, at=(x, y, 0.32), segments=6, shade=0.4)
    elif bone.startswith("lower_"):
        x, y = LEGS[bone[6:]]
        m.cylinder("coat", 0.06, 0.26, at=(x, y, 0.06), segments=6, shade=0.4)
        m.box("dark", (0.13, 0.15, 0.07), at=(x, y - 0.01, 0.0))  # hoof


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    data = bpy.data.armatures.new("Horse")
    rig = bpy.data.objects.new("Horse", data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, _parent) in BONES.items():
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = Vector(head), Vector(tail)
        bone.roll = 0.0
    for name, (_head, _tail, parent) in BONES.items():
        if parent:
            data.edit_bones[name].parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")

    pieces = []
    for name in BONES:
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
