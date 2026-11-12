extends RefCounted
## Loads the characters of the KayKit Adventurers pack (CC0) from res://assets/adventurers
## at run time: the generals, the knight who serves as the foot soldier, the hooded archer,
## and, on our own horse (tools/blender/make_horse.py), the cavalry and mounted generals.
##
## The six characters share one rig, Rig_Medium. They come without animations: those are in
## the KayKit Character Animations pack (CC0), a file per kind of animation on the same rig
## (general, movement, melee, ranged, sitting), read once and given to every figure under the
## names the rest of the viewer asks for (idle, walk, trot, attack, ride). Each kind fights
## and stands as its weapon suits: a two-handed chop, a dagger in each hand, a bow drawn and
## loosed, a spell. Weapons are separate models held at the rig's hand slots, each painted
## from its own texture.
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
	"Rogue_Hooded:archer": {"handslot.l": "bow_withString"},
	"Knight:cavalry": {"handslot.r": "civsim_spear", "handslot.l": "shield_round_color"},  # a lance, really
}
## The pack's animation files, by the short names used below.
const CLIP_FILES := {"General": "Rig_Medium_General", "Move": "Rig_Medium_MovementBasic",
	"Melee": "Rig_Medium_CombatMelee", "Ranged": "Rig_Medium_CombatRanged", "Sit": "Rig_Medium_Simulation"}
## Every figure's animations under our names: "file/clip", or a list of them played in turn
## as one. A rider sits as on a chair: the horse's body hides his knees.
const BASE_SET := {"idle": "General/Idle_A", "walk": "Move/Walking_A", "trot": "Move/Running_A",
	"attack": "General/Throw", "ride": "Sit/Sit_Chair_Idle"}
const BOW_SET := {"idle": "Ranged/Ranged_Bow_Idle", "attack": ["Ranged/Ranged_Bow_Draw", "Ranged/Ranged_Bow_Release"]}
## What each kind does differently, to suit its weapon.
const KIND_SETS := {
	"Knight": {"idle": "Melee/Melee_2H_Idle", "attack": "Melee/Melee_2H_Attack_Chop"},
	"Barbarian": {"idle": "Melee/Melee_2H_Idle", "attack": "Melee/Melee_2H_Attack_Slice"},
	"Rogue": {"attack": "Melee/Melee_Dualwield_Attack_Slice"},
	"Rogue_Hooded": {"attack": "Melee/Melee_Dualwield_Attack_Slice"},
	"Ranger": BOW_SET,
	"Rogue_Hooded:archer": BOW_SET,
	"Mage": {"attack": "Ranged/Ranged_Magic_Shoot"},
	"Knight:swordsman": {"attack": "Melee/Melee_1H_Attack_Slice_Diagonal"},
	"Knight:spearman": {"attack": "Melee/Melee_1H_Attack_Stab"},
	"Knight:cavalry": {"attack": "Melee/Melee_1H_Attack_Slice_Diagonal"},
}
## A rider sits on the horse's "saddle" bone, this far below it (the height of his hips).
const SEAT_DROP := 0.47
const HORSE_SIZE := 1.45  # the horse is drawn this much larger than it was built, beside its rider
const HORSE_ANIMATIONS := {"idle": "Idle", "walk": "Walk", "trot": "Trot"}
## Parts left off a kind: a knight general goes with his visor up, so his face shows; the
## soldier keeps his shut. (Both wear the cape: it is what carries the civ's colour.)
const LEFT_OFF := {"Knight": ["Knight_HelmetVisor"]}

var _prototypes := {}  # kind -> {"scene": Node3D, "aabb": AABB}, or {} if it failed to load
var _libraries := {}  # attack animation -> AnimationLibrary with it as "attack"
var _clips := {}  # "file:animation" -> Animation, read once
var _horse := {}  # {"scene", "aabb", "saddle"}: the horse, read once; {} if it failed to load
var _weapon_textures := {}  # weapon -> the texture it is painted from
var _images := {}  # texture name -> Image
var _materials := {}  # "texture:colour" -> StandardMaterial3D
var _weapons := {}  # weapon name -> Array of [mesh, transform], or [] if it failed to load


## A figure of this kind standing `height` tall in `color`, or null if it could not be made;
## with `mounted`, on horseback, `height` tall from the hooves to the top of the rider's head.
## The holder carries the "player" and "height" metadata characters.gd's play() reads.
func instance(kind: String, color: Color, height: float, mounted := false) -> Node3D:
	var figure := _figure(kind, color)
	if figure.is_empty():
		return null
	var holder := Node3D.new()
	var copy: Node3D = figure["copy"]
	var aabb: AABB = figure["aabb"]
	if mounted and _load_horse():
		var horse := Node3D.new()  # the horse at HORSE_SIZE, its rider at his own size on it
		var animal: Node3D = (_horse["scene"] as Node3D).duplicate()
		animal.scale = Vector3.ONE * HORSE_SIZE
		horse.add_child(animal)
		for mesh: MeshInstance3D in horse.find_children("*", "MeshInstance3D", true, false):
			mesh.material_override = _material("knight", color)
		var skeleton: Skeleton3D = horse.find_children("*", "Skeleton3D", true, false)[0]
		var seat := BoneAttachment3D.new()
		skeleton.add_child(seat)
		seat.bone_name = "saddle"
		copy.position = Vector3(0, (-SEAT_DROP - aabb.position.y) / HORSE_SIZE, 0)
		copy.scale = Vector3.ONE / HORSE_SIZE
		seat.add_child(copy)
		var rider: AnimationPlayer = figure["player"]
		rider.autoplay = "ride"  # he sits his horse whatever it is doing
		var box: AABB = _horse["aabb"]
		var top: float = maxf(box.end.y * HORSE_SIZE, float(_horse["saddle"]) * HORSE_SIZE - SEAT_DROP + aabb.size.y)
		var factor := height / maxf(top - box.position.y * HORSE_SIZE, 0.01)
		horse.scale = Vector3.ONE * factor
		horse.position = Vector3(0, -box.position.y * HORSE_SIZE * factor, 0)
		holder.add_child(horse)
		holder.set_meta("player", horse.find_children("*", "AnimationPlayer", true, false)[0])
		holder.set_meta("height", height)
		return holder
	var factor: float = height / maxf(aabb.size.y, 0.01)
	copy.scale = Vector3.ONE * factor
	copy.position = Vector3(0, -aabb.position.y * factor, 0)  # on its own origin: the feet
	holder.add_child(copy)
	holder.set_meta("player", figure["player"])
	holder.set_meta("height", aabb.size.y * factor)
	return holder


## A copy of the kind at its own size, armed and painted: {"copy", "aabb", "player"}, or {}.
func _figure(kind: String, color: Color) -> Dictionary:
	var data: Dictionary = _load(kind)
	if data.is_empty():
		return {}
	var copy: Node3D = (data["scene"] as Node3D).duplicate()
	# Weapons are fixed to each copy's own rig: an attachment copied with the figure loses its bone.
	var skeleton: Skeleton3D = copy.find_children("*", "Skeleton3D", true, false)[0]
	var kit: Dictionary = KITS.get(kind, {})
	for slot: String in kit:
		if kit[slot] != "":
			_hold(skeleton, slot, kit[slot])
	var texture: String = TEXTURES[kind.get_slice(":", 0)]
	for mesh: MeshInstance3D in copy.find_children("*", "MeshInstance3D", true, false):
		mesh.material_override = _material(str(mesh.get_meta("texture", texture)), color)
	var players := copy.find_children("*", "AnimationPlayer", true, false)
	return {"copy": copy, "aabb": data["aabb"], "player": players[0] if not players.is_empty() else null}


## The horse, read once: its scene with idle, walk and trot, its bounds, and its saddle's height.
func _load_horse() -> bool:
	if not _horse.is_empty():
		return _horse.has("scene")
	_horse = {"failed": true}
	var scene := _read("civsim_horse.glb")
	if scene == null:
		push_warning("The horse could not be loaded; riders are drawn on foot")
		return false
	var skeleton: Skeleton3D = scene.find_children("*", "Skeleton3D", true, false)[0]
	var players := scene.find_children("*", "AnimationPlayer", true, false)
	var library := AnimationLibrary.new()
	if not players.is_empty():
		var source: AnimationPlayer = players[0]
		for ours: String in HORSE_ANIMATIONS:
			if source.has_animation(HORSE_ANIMATIONS[ours]):
				var animation: Animation = source.get_animation(HORSE_ANIMATIONS[ours]).duplicate()
				animation.loop_mode = Animation.LOOP_LINEAR
				library.add_animation(ours, animation)
		for name: StringName in source.get_animation_library_list():
			source.remove_animation_library(name)
		source.add_animation_library("", library)
	var aabb := AABB()
	var first := true
	for mesh: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		var box: AABB = mesh.mesh.get_aabb()
		aabb = box if first else aabb.merge(box)
		first = false
	var saddle := skeleton.get_bone_global_rest(skeleton.find_bone("saddle")).origin.y
	_horse = {"scene": scene, "aabb": aabb, "saddle": saddle}
	return true


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
		var library := _animations(kind)
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


## A kind's animations under our names (BASE_SET, with its own from KIND_SETS), read once and
## shared by every figure of the kind.
func _animations(kind: String) -> AnimationLibrary:
	if _libraries.has(kind):
		return _libraries[kind]
	var library := AnimationLibrary.new()
	var wanted := BASE_SET.duplicate()
	wanted.merge(KIND_SETS.get(kind, {}), true)
	for ours: String in wanted:
		var parts: Array = wanted[ours] if wanted[ours] is Array else [wanted[ours]]
		var clips: Array[Animation] = []
		for part: String in parts:
			var clip := _clip(CLIP_FILES[part.get_slice("/", 0)], part.get_slice("/", 1))
			if clip != null:
				clips.append(clip)
		if clips.size() == 1:
			library.add_animation(ours, clips[0])
		elif clips.size() > 1:
			library.add_animation(ours, _joined(clips))
	_libraries[kind] = library
	return library


## Several animations played one after the other, as one that loops.
func _joined(clips: Array[Animation]) -> Animation:
	var joined := Animation.new()
	var offset := 0.0
	for clip in clips:
		for track in clip.get_track_count():
			var path := clip.track_get_path(track)
			var kind := clip.track_get_type(track)
			var into := joined.find_track(path, kind)
			if into < 0:
				into = joined.add_track(kind)
				joined.track_set_path(into, path)
			for key in clip.track_get_key_count(track):
				var at := offset + clip.track_get_key_time(track, key)
				var value: Variant = clip.track_get_key_value(track, key)
				match kind:
					Animation.TYPE_POSITION_3D:
						joined.position_track_insert_key(into, at, value)
					Animation.TYPE_ROTATION_3D:
						joined.rotation_track_insert_key(into, at, value)
					Animation.TYPE_SCALE_3D:
						joined.scale_track_insert_key(into, at, value)
					_:
						joined.track_insert_key(into, at, value)
		offset += clip.length
	joined.length = offset
	joined.loop_mode = Animation.LOOP_LINEAR
	return joined


## One animation from one of the rig's animation files, read once, set to loop.
func _clip(file: String, name: String) -> Animation:
	var key := "%s:%s" % [file, name]
	if _clips.has(key):
		return _clips[key]
	var found: Animation = null
	var source := _read(file + ".glb")
	if source != null:
		for player: AnimationPlayer in source.find_children("*", "AnimationPlayer", true, false):
			for other: String in player.get_animation_list():  # cache the file's others while it is open
				var clip: Animation = player.get_animation(other).duplicate()
				clip.loop_mode = Animation.LOOP_LINEAR
				_clips["%s:%s" % [file, other]] = clip
		source.free()
	found = _clips.get(key)
	_clips[key] = found
	return found


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
		_weapon_textures[weapon] = _texture_of(weapon)
	var attachment := BoneAttachment3D.new()
	attachment.name = "%s_%s" % [slot, weapon]
	skeleton.add_child(attachment)
	attachment.bone_name = slot
	for part: Array in _weapons[weapon]:
		var mesh := MeshInstance3D.new()
		mesh.mesh = part[0]
		mesh.transform = part[1]
		if _weapon_textures[weapon] != "":
			mesh.set_meta("texture", _weapon_textures[weapon])  # a ranger's bow in a rogue's hand stays a ranger's bow
		attachment.add_child(mesh)


## The texture a weapon's glTF is painted from ("ranger" for ranger_texture.png), or "".
func _texture_of(weapon: String) -> String:
	var text := FileAccess.get_file_as_string(ProjectSettings.globalize_path(DIR + weapon + ".gltf"))
	var parsed: Variant = JSON.parse_string(text) if text != "" else null
	if parsed is Dictionary:
		for image: Dictionary in parsed.get("images", []):
			var uri := str(image.get("uri", ""))
			if uri.ends_with("_texture.png"):
				return uri.trim_suffix("_texture.png")
	return ""


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
