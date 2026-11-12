extends RefCounted
## Loads the characters of the KayKit Adventurers pack (CC0) from res://assets/adventurers
## at run time: the generals, and the knight who serves as the foot soldier.
##
## The six characters share one rig, Rig_Medium. They come without animations: those are in
## two files of their own on the same rig (Rig_Medium_General, Rig_Medium_MovementBasic),
## read once and given to every figure under the names the rest of the viewer asks for
## (idle, walk, trot, attack). Weapons are separate models held at the rig's hand slots.
##
## Each character is painted from one texture of flat colour cells. The cells of its cape
## and trim are repainted in the owner's colour, keeping their shading, as models.gd does for
## the buildings; skin, steel and leather are left as they are. A figure's parts are fused
## into one skinned mesh, so a whole army of them costs few draw calls.

const DIR := "res://assets/adventurers/"
## The characters a general can be, in a fixed order: a general's look is picked from these.
const GENERALS := ["Knight", "Barbarian", "Ranger", "Rogue", "Rogue_Hooded", "Mage"]
## The texture each character (and its weapons) is painted from.
const TEXTURES := {"Knight": "knight", "Barbarian": "barbarian", "Ranger": "ranger", "Rogue": "rogue",
	"Rogue_Hooded": "rogue", "Mage": "mage"}
## The cells of each texture that take the owner's colour: [column, row] of a 128 x 256 grid.
const TEAM_CELLS := {
	"knight": [Vector2i(0, 1), Vector2i(2, 2)],  # cape and rosette, the shield's paint
	"barbarian": [Vector2i(0, 1), Vector2i(2, 2)],  # war paint and the bindings of his axe: he wears no cloth
	"ranger": [Vector2i(0, 1), Vector2i(1, 2)],  # cape and hood
	"rogue": [Vector2i(0, 1), Vector2i(1, 1), Vector2i(1, 2)],  # cape and tunic
	"mage": [Vector2i(0, 1), Vector2i(1, 1), Vector2i(7, 1), Vector2i(2, 1), Vector2i(1, 2)],  # robe and trim
}
const CELL := Vector2i(128, 256)
## What each kind of figure holds: hand slot -> weapon model. A "kind" is a character, or a
## character and a variant after a colon.
const KITS := {
	"Knight": {"handslot.r": "sword_2handed", "handslot.l": ""},
	"Knight:swordsman": {"handslot.r": "sword_1handed", "handslot.l": "shield_round_color"},
	"Knight:spearman": {"handslot.r": "civsim_spear", "handslot.l": "shield_badge_color"},  # the spear is made in Blender
	"Barbarian": {"handslot.r": "axe_2handed"},
	"Ranger": {"handslot.l": "bow_withString"},
	"Rogue": {"handslot.r": "dagger", "handslot.l": "dagger"},
	"Rogue_Hooded": {"handslot.r": "dagger", "handslot.l": "dagger"},
	"Mage": {"handslot.r": "staff", "handslot.l": "spellbook_closed"},
}
## Parts left off a kind: a knight general goes with his visor up, so his face shows; the
## soldier keeps his shut. (Both wear the cape: it is what carries the civ's colour.)
const LEFT_OFF := {"Knight": ["Knight_HelmetVisor"]}
## Our animation names -> [file, animation in it]. The free pack has no sword swing: the
## overarm throw is the nearest thing to a blow.
const ANIMATIONS := {
	"idle": ["Rig_Medium_General", "Idle_A"],
	"walk": ["Rig_Medium_MovementBasic", "Walking_A"],
	"trot": ["Rig_Medium_MovementBasic", "Running_A"],
	"attack": ["Rig_Medium_General", "Throw"],
}

var _prototypes := {}  # kind -> {"scene": Node3D, "aabb": AABB}, or {} if it failed to load
var _library: AnimationLibrary
var _images := {}  # texture name -> Image
var _materials := {}  # "texture:colour" -> StandardMaterial3D
var _weapons := {}  # weapon name -> Array of [mesh, transform], or [] if it failed to load


## A figure of this kind standing `height` tall in `color`, or null if it could not be made.
## The holder carries the "player" and "height" metadata characters.gd's play() reads.
func instance(kind: String, color: Color, height: float) -> Node3D:
	var data: Dictionary = _load(kind)
	if data.is_empty():
		return null
	var aabb: AABB = data["aabb"]
	var factor: float = height / maxf(aabb.size.y, 0.01)
	var holder := Node3D.new()
	var copy: Node3D = (data["scene"] as Node3D).duplicate()
	copy.scale = Vector3.ONE * factor
	copy.position = Vector3(0, -aabb.position.y * factor, 0)  # on its own origin: the feet
	holder.add_child(copy)
	# Weapons are fixed to each copy's own rig: an attachment copied with the figure loses its bone.
	var skeleton: Skeleton3D = copy.find_children("*", "Skeleton3D", true, false)[0]
	var kit: Dictionary = KITS.get(kind, {})
	for slot: String in kit:
		if kit[slot] != "":
			_hold(skeleton, slot, kit[slot])
	var material := _material(TEXTURES[kind.get_slice(":", 0)], color)
	for mesh: MeshInstance3D in copy.find_children("*", "MeshInstance3D", true, false):
		mesh.material_override = material
	var players := copy.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty():
		holder.set_meta("player", players[0])
	holder.set_meta("height", aabb.size.y * factor)
	return holder


func has(kind: String) -> bool:
	return not _load(kind).is_empty()


## The general's look: one of GENERALS, the same for the same general every time.
static func general_for(civ: int, name: String) -> String:
	return GENERALS[absi(("%d:%s" % [civ, name]).hash()) % GENERALS.size()]


## The character's texture with its team cells repainted in `color`.
func _material(texture: String, color: Color) -> StandardMaterial3D:
	var key := "%s:%s" % [texture, color.to_html(false)]
	if _materials.has(key):
		return _materials[key]
	var image := _image(texture)
	var material := StandardMaterial3D.new()
	material.roughness = 0.85
	if image != null:
		var painted: Image = image.duplicate()
		for cell: Vector2i in TEAM_CELLS.get(texture, []):
			var top := painted.get_pixel(cell.x * CELL.x + CELL.x / 2, cell.y * CELL.y + CELL.y / 8)
			var bright := maxf(top.v, 0.01)  # the light end of the cell's gradient
			for y in range(cell.y * CELL.y, (cell.y + 1) * CELL.y):
				for x in range(cell.x * CELL.x, (cell.x + 1) * CELL.x):
					# Keep the cell's light-to-dark shading, swap its hue and saturation for the owner's.
					var shade := clampf(painted.get_pixel(x, y).v / bright, 0.0, 1.0)
					painted.set_pixel(x, y, Color.from_hsv(color.h, color.s, clampf(color.v * (0.35 + 0.75 * shade), 0, 1)))
		material.albedo_texture = ImageTexture.create_from_image(painted)
	_materials[key] = material
	return material


func _image(texture: String) -> Image:
	if not _images.has(texture):
		_images[texture] = Image.load_from_file(ProjectSettings.globalize_path(DIR + texture + "_texture.png"))
	return _images[texture]


## The loaded originals are never in the scene tree, so they have to be freed by hand.
func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		for data: Dictionary in _prototypes.values():
			if not data.is_empty() and is_instance_valid(data["scene"]):
				data["scene"].free()


func _load(kind: String) -> Dictionary:
	if _prototypes.has(kind):
		return _prototypes[kind]
	var result := {}
	var scene := _read(kind.get_slice(":", 0) + ".glb")
	var skeleton: Skeleton3D = null
	if scene != null:
		var found := scene.find_children("*", "Skeleton3D", true, false)
		skeleton = found[0] if not found.is_empty() else null
	if skeleton != null:
		for part: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
			if part.name in LEFT_OFF.get(kind, []):
				part.get_parent().remove_child(part)
				part.free()
		var aabb := _fuse(skeleton)
		var player := AnimationPlayer.new()
		player.name = "AnimationPlayer"
		scene.add_child(player)
		var library := _animations()
		if library != null:
			player.add_animation_library("", library)
		if aabb.size.y > 0.0:
			result = {"scene": scene, "aabb": aabb}
	if result.is_empty():
		push_warning("Character %s could not be loaded; the plain placeholder is used instead" % kind)
		if scene != null:
			scene.free()
	_prototypes[kind] = result
	return result


func _read(file: String) -> Node3D:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var path := ProjectSettings.globalize_path(DIR + file)
	if not FileAccess.file_exists(path) or document.append_from_file(path, state) != OK:
		return null
	var scene := document.generate_scene(state)
	if scene is Node3D:
		return scene
	if scene != null:
		scene.free()
	return null


## The pack's animations, under our names, read once and shared by every figure.
func _animations() -> AnimationLibrary:
	if _library != null:
		return _library
	_library = AnimationLibrary.new()
	var sources := {}
	for ours: String in ANIMATIONS:
		var file: String = ANIMATIONS[ours][0]
		if not sources.has(file):
			sources[file] = _read(file + ".glb")
		var source: Node3D = sources[file]
		if source == null:
			continue
		for player: AnimationPlayer in source.find_children("*", "AnimationPlayer", true, false):
			if player.has_animation(ANIMATIONS[ours][1]):
				var animation: Animation = player.get_animation(ANIMATIONS[ours][1]).duplicate()
				animation.loop_mode = Animation.LOOP_LINEAR
				_library.add_animation(ours, animation)
				break
	for source: Node3D in sources.values():
		if source != null:
			source.free()
	return _library


## Fix a weapon to a hand slot of the rig.
func _hold(skeleton: Skeleton3D, slot: String, weapon: String) -> void:
	if skeleton.find_bone(slot) < 0:
		return
	if not _weapons.has(weapon):
		var parts: Array = []
		var scene := _read(weapon + ".gltf")
		if scene != null:
			_collect(scene, Transform3D.IDENTITY, parts)
			scene.free()
		_weapons[weapon] = parts
	var attachment := BoneAttachment3D.new()
	attachment.name = "%s_%s" % [slot, weapon]
	skeleton.add_child(attachment)
	attachment.bone_name = slot
	for part: Array in _weapons[weapon]:
		var mesh := MeshInstance3D.new()
		mesh.mesh = part[0]
		mesh.transform = part[1]
		attachment.add_child(mesh)


func _collect(node: Node, parent: Transform3D, parts: Array) -> void:
	var xform := parent
	if node is Node3D:
		xform = parent * (node as Node3D).transform
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		parts.append([(node as MeshInstance3D).mesh, xform])
	for child in node.get_children():
		_collect(child, xform, parts)


## The character's body parts, each skinned on its own, fused into one skinned mesh that
## keeps its texture coordinates. Returns the bounds of the body as it stands at rest.
func _fuse(skeleton: Skeleton3D) -> AABB:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	var indices := PackedInt32Array()
	var skin := Skin.new()
	var parts: Array[MeshInstance3D] = []
	var aabb := AABB()
	var first := true
	for part: MeshInstance3D in skeleton.find_children("*", "MeshInstance3D", true, false):
		if part.mesh == null or part.skin == null:
			continue
		var offset := skin.get_bind_count()
		for i in part.skin.get_bind_count():
			var bone_name := part.skin.get_bind_name(i)
			if bone_name != &"":
				skin.add_named_bind(bone_name, part.skin.get_bind_pose(i))
			else:
				skin.add_bind(part.skin.get_bind_bone(i), part.skin.get_bind_pose(i))
		for surface in part.mesh.get_surface_count():
			var arrays := part.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var their_bones: Variant = arrays[Mesh.ARRAY_BONES]
			var their_weights: Variant = arrays[Mesh.ARRAY_WEIGHTS]
			if points.is_empty() or their_bones == null or their_weights == null \
					or (their_bones as PackedInt32Array).size() != points.size() * 4:
				continue
			var base := vertices.size()
			vertices.append_array(points)
			normals.append_array(arrays[Mesh.ARRAY_NORMAL] if arrays[Mesh.ARRAY_NORMAL] != null else PackedVector3Array())
			var their_uvs: Variant = arrays[Mesh.ARRAY_TEX_UV]
			if their_uvs != null:
				uvs.append_array(their_uvs)
			else:
				for i in points.size():
					uvs.append(Vector2.ZERO)
			for bone: int in their_bones:
				bones.append(bone + offset)
			weights.append_array(their_weights)
			var their_indices: Variant = arrays[Mesh.ARRAY_INDEX]
			for i in (their_indices.size() if their_indices != null else points.size()):
				indices.append(base + (their_indices[i] if their_indices != null else i))
			var box := part.mesh.get_aabb()
			aabb = box if first else aabb.merge(box)
			first = false
		parts.append(part)
	if parts.is_empty() or normals.size() != vertices.size():
		return aabb
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_BONES] = bones
	arrays[Mesh.ARRAY_WEIGHTS] = weights
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var body := MeshInstance3D.new()
	body.name = "body"
	body.mesh = mesh
	body.skin = skin
	skeleton.add_child(body)
	body.skeleton = NodePath("..")
	for part in parts:
		part.get_parent().remove_child(part)
		part.free()
	return aabb
