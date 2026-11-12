"""Builds the horse the cavalry and mounted generals ride, and writes it with idle, walk and
trot animations to godot/assets/adventurers/civsim_horse.glb. Run from the repository root:

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender/make_horse.py

The shape is the low-poly horse in tools/blender/sources/low_poly_horse.obj, made of named
parts (torso, neck, head, each leg's upper, knee, lower and hoof, mane, tail) coloured by
vertex. It is turned to face -y like the pack's characters, scaled to a rider, its body
smoothed once, and painted from the Adventurers knight's texture (the nearest of its browns
for each part), so horse and rider share one material; a saddle, a saddle cloth in the
owner's colour (the texture's team cell) and a steel chamfron are added. Each part is
rigid on one bone; a rider sits on the "saddle" bone.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
from make_models import KNIGHT, Model  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOURCE = os.path.join(os.path.dirname(__file__), "sources", "low_poly_horse.obj")
OUT = os.path.join(ROOT, "godot", "assets", "adventurers", "civsim_horse.glb")
FPS = 30
SCALE = 0.5  # the source stands 2.9 tall; this brings its back to the saddle height a rider needs
CELLS = dict(KNIGHT, coat=(5, 0), dark=(2, 0), muzzle=(6, 0), cloth=(0, 1), steel=(3, 0))
SMOOTHED = {"Torso", "Hindquarters", "Shoulder", "Neck_blend", "Neck_core", "Cheek", "Head"}

# Which bone each of the source's parts hangs on. Its "near" side is the horse's left.
PART_BONES = {"Torso": "body", "Hindquarters": "body", "Shoulder": "body", "Mane_mid": "body",
              "Neck_core": "neck", "Neck_blend": "neck", "Mane_main": "neck",
              "Tail_base": "tail", "Tail_tip": "tail"}
for name in ("Head", "Cheek", "Muzzle", "Nose", "Near_ear", "Far_ear", "Near_eye", "Far_eye",
             "Near_nostril", "Far_nostril"):
    PART_BONES[name] = "head"
for side, leg in (("near", "l"), ("far", "r")):
    PART_BONES[f"Front_{side}_upper"] = f"upper_f{leg}"
    PART_BONES[f"{side.capitalize()}_front_knee"] = f"lower_f{leg}"
    PART_BONES[f"Front_{side}_lower"] = f"lower_f{leg}"
    PART_BONES[f"Front_{side}_hoof"] = f"lower_f{leg}"
    PART_BONES[f"Hind_{side}_thigh"] = f"upper_b{leg}"
    PART_BONES[f"{side.capitalize()}_hock"] = f"lower_b{leg}"
    PART_BONES[f"Hind_{side}_cannon"] = f"lower_b{leg}"
    PART_BONES[f"Hind_{side}_hoof"] = f"lower_b{leg}"
LEGS = ("fl", "fr", "bl", "br")


def place(x: float, y: float, z: float) -> Vector:
    """The source's head points to -x with z up: turn it to face -y, at our scale."""
    return Vector((-y, x, z)) * SCALE


def read_source() -> dict:
    """The OBJ's parts: name -> (vertices as (position, colour), faces as index lists)."""
    parts, order, current = {}, [], None
    vertices = []
    for line in open(SOURCE):
        if line.startswith("o "):
            current = line.split(None, 1)[1].strip()
            parts[current] = []
            order.append(current)
        elif line.startswith("v "):
            values = [float(v) for v in line.split()[1:7]]
            vertices.append((place(*values[:3]), tuple(values[3:6]) if len(values) >= 6 else (0.6, 0.35, 0.15)))
        elif line.startswith("f "):
            parts[current].append([int(token.split("/")[0]) - 1 for token in line.split()[1:]])
    return {name: (vertices, parts[name]) for name in order}


def cell_for(colour: tuple) -> tuple:
    """The knight texture's cell and the height in it nearest a source colour."""
    light = sum(colour) / 3
    if light < 0.16:
        return "dark", 0.3
    if light > 0.4:
        return "coat", 0.2
    if light > 0.33:
        return "coat", 0.55
    return "muzzle", 0.45


def part_object(name: str, vertices: list, faces: list) -> bpy.types.Object:
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    used = sorted({i for face in faces for i in face})
    made = {i: bm.verts.new(vertices[i][0]) for i in used}
    for face in faces:
        try:
            new = bm.faces.new([made[i] for i in face])
        except ValueError:
            continue  # a duplicate face
        cell, shade = cell_for(vertices[face[0]][1])
        col, row = CELLS[cell]
        for loop in new.loops:
            loop[uv].uv = ((col + 0.5) / 8.0, 1.0 - (row + 0.08 + 0.84 * shade) / 4.0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if name in SMOOTHED:  # rounded once and shaded smooth: the blocky body softened
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        subdivision = obj.modifiers.new("Smooth", "SUBSURF")
        subdivision.levels = 1
        subdivision.render_levels = 1
        bpy.ops.object.modifier_apply(modifier=subdivision.name)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    return obj


def bounds(objects: list) -> tuple[Vector, Vector]:
    points = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def tack(low: Vector, high: Vector) -> bpy.types.Object:
    """The saddle and its cloth in the owner's colour, fitted to the body's bounds."""
    width = high.x - low.x
    back = high.z
    m = Model(CELLS)
    m.box("cloth", (width + 0.03, 0.42, 0.04), at=(0, 0.02, back - 0.03), shade=0.3)  # over the back
    for side in (-1, 1):  # hanging down each flank
        m.box("cloth", (0.02, 0.4, 0.16), at=(side * (width / 2 + 0.005), 0.02, back - 0.18), shade=0.4)
    m.box("leather", (width * 0.7, 0.3, 0.07), at=(0, 0.02, back))
    m.box("leather", (width * 0.6, 0.06, 0.09), at=(0, -0.12, back + 0.03))
    mesh = bpy.data.meshes.new("Tack")
    m.bm.normal_update()
    m.bm.to_mesh(mesh)
    m.bm.free()
    obj = bpy.data.objects.new("Tack", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def chamfron(low: Vector, high: Vector) -> bpy.types.Object:
    """A steel plate down the front of the face, fitted to the head's bounds."""
    m = Model(CELLS)
    length = high.y - low.y
    m.box("steel", (high.x - low.x + 0.02, length * 0.55, 0.035), at=(0, low.y + length * 0.42, high.z - 0.09), tilt=-0.35)
    mesh = bpy.data.meshes.new("Chamfron")
    m.bm.normal_update()
    m.bm.to_mesh(mesh)
    m.bm.free()
    obj = bpy.data.objects.new("Chamfron", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    by_bone: dict[str, list] = {}
    for name, (vertices, faces) in read_source().items():
        bone = PART_BONES.get(name)
        if bone is None:
            print("no bone for part", name)
            continue
        by_bone.setdefault(bone, []).append(part_object(name, vertices, faces))
    trunk = [o for o in by_bone["body"] if o.name in ("Torso", "Hindquarters", "Shoulder")]
    torso_low, torso_high = bounds([o for o in trunk if o.name == "Torso"])
    by_bone["body"].append(tack(torso_low, torso_high))
    face = [o for o in by_bone["head"] if o.name in ("Head", "Cheek", "Muzzle")]
    by_bone["head"].append(chamfron(*bounds(face)))

    # The skeleton, from where the parts stand.
    bones = {"root": (Vector((0, 0, 0)), Vector((0, 0, 0.3)), None)}
    body_low, body_high = bounds([o for o in by_bone["body"] if o.name in ("Torso", "Hindquarters", "Shoulder")])
    middle = (body_low.z + body_high.z) / 2
    bones["body"] = (Vector((0, body_high.y, middle)), Vector((0, body_low.y, middle)), "root")
    neck_low, neck_high = bounds(by_bone["neck"])
    head_low, head_high = bounds(by_bone["head"])
    bones["neck"] = (Vector((0, neck_high.y, neck_low.z + 0.1)), Vector((0, head_high.y, head_low.z + 0.1)), "body")
    bones["head"] = (Vector((0, head_high.y, head_low.z + 0.1)), Vector((0, head_low.y, head_low.z + 0.05)), "neck")
    tail_low, tail_high = bounds(by_bone["tail"])
    bones["tail"] = (Vector((0, tail_low.y, tail_high.z)), Vector((0, tail_high.y, tail_low.z)), "body")
    bones["saddle"] = (Vector((0, 0.02, body_high.z)), Vector((0, 0.02, body_high.z + 0.2)), "body")
    for leg in LEGS:
        upper_low, upper_high = bounds(by_bone[f"upper_{leg}"])
        lower_low, lower_high = bounds(by_bone[f"lower_{leg}"])
        x, y = (upper_low.x + upper_high.x) / 2, (upper_low.y + upper_high.y) / 2
        knee = Vector(((lower_low.x + lower_high.x) / 2, (lower_low.y + lower_high.y) / 2, lower_high.z))
        bones[f"upper_{leg}"] = (Vector((x, y, upper_high.z)), knee, "body")
        bones[f"lower_{leg}"] = (knee, Vector((knee.x, knee.y, lower_low.z)), f"upper_{leg}")

    data = bpy.data.armatures.new("Horse")
    rig = bpy.data.objects.new("Horse", data)
    scene.collection.objects.link(rig)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, _parent) in bones.items():
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        bone.roll = 0.0
    for name, (_head, _tail, parent) in bones.items():
        if parent:
            data.edit_bones[name].parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")

    pieces = []
    for bone, objects in by_bone.items():
        for obj in objects:
            group = obj.vertex_groups.new(name=bone)
            group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
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
