extends RefCounted
## Loads the models in res://assets/characters straight from their .glb files at run
## time: the rigged, animated Commander, Villager, Rider and Knight, and the static Stable,
## Harbour, Boat, Castle and CapitalCastle. Each file is read once; every figure on the map is a copy of that.
##
## The models carry plain named materials rather than a texture, so a figure is put in
## its civ's colour by swapping the material of that name (the commander's cloth, the
## villager's tunic) for one in the civ's colour.

const DIR := "res://assets/characters/"
## The material on each model that takes the owner's colour.
const TEAM_MATERIALS := {
	"Commander": ["cloth_team"], "Villager": ["tunic_moss"], "Rider": ["tunic_moss", "saddle_blanket"],
	"Stable": ["cloth_team"], "Boat": ["cloth_team"], "Harbour": ["cloth_team"],
	"Knight": ["cloth_team", "cloth_deep"], "Archer": ["cloth_team"], "Castle": ["cloth_team"], "CapitalCastle": ["cloth_team"],
}

## Parts of a model that are left out: the stable comes on a wide plate of grass, which would
## either bury the neighbouring tiles or force the building itself to be drawn tiny.
const LEFT_OUT := {"Stable": ["grass"], "Harbour": ["grass", "dirt"], "Castle": ["grass"], "CapitalCastle": ["grass"]}
## Models made of thousands of small parts that never move: each is welded into one mesh
## with a surface per material when it is loaded, or every castle on the map would cost
## thousands of draw calls.
const WELDED := ["Castle", "CapitalCastle", "Stable", "Harbour", "Boat"]
## Models that stand on their own origin rather than the middle of their bounding box: the
## knight's lance reaches far out in front, and centring the box would push the horse back.
const ON_ORIGIN := ["Knight"]
const CACHE_VERSION := 1  # raise when welding changes, so old kept meshes are not used

var _prototypes := {}  # name -> {"scene": Node3D, "aabb": AABB}, or {} if it failed to load
var _tints := {}  # "material name:colour" -> Material


## A copy of the model standing `height` tall (or, with `across`, that many tiles wide),
## in `color`. Null if the file could not be loaded.
func instance(model: String, color: Color, height: float, across := 0.0) -> Node3D:
	var data: Dictionary = _load(model)
	if data.is_empty():
		return null
	var aabb: AABB = data["aabb"]
	var factor: float = height / maxf(aabb.size.y, 0.01)
	if across > 0.0:
		factor = across / maxf(maxf(aabb.size.x, aabb.size.z), 0.01)
	var holder := Node3D.new()
	var copy: Node3D = (data["scene"] as Node3D).duplicate()
	copy.scale = Vector3.ONE * factor
	# Stand it on the ground, centred on its spot.
	var centre := aabb.get_center()
	if model in ON_ORIGIN:
		centre = Vector3.ZERO
	copy.position = Vector3(-centre.x, -aabb.position.y, -centre.z) * factor
	holder.add_child(copy)
	_tint(copy, TEAM_MATERIALS.get(model, []), color)
	var players := copy.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty():
		holder.set_meta("player", players[0])
	holder.set_meta("height", aabb.size.y * factor)
	return holder


## The loaded originals are never in the scene tree, so they have to be freed by hand.
func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		for data: Dictionary in _prototypes.values():
			if not data.is_empty() and is_instance_valid(data["scene"]):
				data["scene"].free()


func has(model: String) -> bool:
	return not _load(model).is_empty()


## True if the figure has an animation of that name.
func can_play(holder: Node3D, animation: String) -> bool:
	return holder.has_meta("player") and (holder.get_meta("player") as AnimationPlayer).has_animation(animation)


## Switch a figure to the named animation, if it has one and is not already playing it.
func play(holder: Node3D, animation: String) -> void:
	if not holder.has_meta("player"):
		return
	var player: AnimationPlayer = holder.get_meta("player")
	if player.current_animation != animation and player.has_animation(animation):
		player.play(animation, 0.15)


## Animations cost nothing while nobody can see the figure.
func set_active(holder: Node3D, active: bool) -> void:
	if holder.has_meta("player"):
		(holder.get_meta("player") as AnimationPlayer).active = active


func _tint(node: Node, names: Array, color: Color) -> void:
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null and not names.is_empty():
		var instance := node as MeshInstance3D
		for surface in instance.mesh.get_surface_count():
			var material: Material = instance.mesh.surface_get_material(surface)
			if material != null and material.resource_name in names:
				var key := "%s:%s" % [material.resource_name, color.to_html(false)]
				if not _tints.has(key):
					var tinted: StandardMaterial3D = material.duplicate()
					# A model's darker cloth (the knight's cloak) takes a darker shade of the colour.
					tinted.albedo_color = color.darkened(0.4) if material.resource_name.ends_with("_deep") else color
					_tints[key] = tinted
				instance.set_surface_override_material(surface, _tints[key])
	for child in node.get_children():
		_tint(child, names, color)


func _load(model: String) -> Dictionary:
	if _prototypes.has(model):
		return _prototypes[model]
	var result := {}
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var path := ProjectSettings.globalize_path(DIR + model + ".glb")
	# A welded model is kept from one run to the next: welding the castles takes seconds.
	var cached := "user://welded/%s-%d-%d.res" % [model, FileAccess.get_modified_time(path), CACHE_VERSION]
	if model in WELDED and ResourceLoader.exists(cached):
		var kept := ResourceLoader.load(cached) as ArrayMesh
		if kept != null and kept.get_surface_count() > 0:
			var holder := Node3D.new()
			var instance := MeshInstance3D.new()
			instance.mesh = kept
			holder.add_child(instance)
			_prototypes[model] = {"scene": holder, "aabb": kept.get_aabb()}
			return _prototypes[model]
	if FileAccess.file_exists(path) and document.append_from_file(path, state) == OK:
		var scene := document.generate_scene(state)
		if scene is Node3D:
			_strip(scene, LEFT_OUT.get(model, []))
			if model in WELDED:
				scene = _weld(scene)
				DirAccess.make_dir_recursive_absolute("user://welded")
				ResourceSaver.save((scene.get_child(0) as MeshInstance3D).mesh, cached)
			else:
				_fuse(scene)
			var boxes: Array = []
			_measure(scene, Transform3D.IDENTITY, boxes)
			if not boxes.is_empty():
				var aabb: AABB = boxes[0]
				for box: AABB in boxes:
					aabb = aabb.merge(box)
				for player: AnimationPlayer in scene.find_children("*", "AnimationPlayer", true, false):
					for animation_name in player.get_animation_list():
						player.get_animation(animation_name).loop_mode = Animation.LOOP_LINEAR
				result = {"scene": scene, "aabb": aabb}
	if result.is_empty():
		push_warning("Model %s could not be loaded; the plain placeholder is used instead" % model)
	_prototypes[model] = result
	return result


func _strip(node: Node, names: Array) -> void:
	for child in node.get_children():
		_strip(child, names)
	if names.is_empty() or not node is MeshInstance3D:
		return
	var mesh: Mesh = (node as MeshInstance3D).mesh
	for surface in mesh.get_surface_count():
		var material: Material = mesh.surface_get_material(surface)
		if material == null or not material.resource_name in names:
			return
	(node as MeshInstance3D).mesh = null


## One mesh holding everything in `scene` where it stands, a surface per material. Only
## positions and normals are kept: these models are flat-coloured, with no textures.
func _weld(scene: Node3D) -> Node3D:
	var groups := {}  # Material -> [vertices, normals, indices]
	_gather(scene, Transform3D.IDENTITY, groups)
	var mesh := ArrayMesh.new()
	for material: Material in groups:
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = groups[material][0]
		arrays[Mesh.ARRAY_NORMAL] = groups[material][1]
		arrays[Mesh.ARRAY_INDEX] = groups[material][2]
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(mesh.get_surface_count() - 1, material)
	var welded := Node3D.new()
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	welded.add_child(instance)
	scene.free()
	return welded


## A rigged figure comes as dozens of small parts, each skinned to the skeleton on its own.
## Fuse them into one skinned mesh with a surface per material: it moves exactly as before
## and costs a fraction of the draw calls.
func _fuse(scene: Node3D) -> void:
	for skeleton: Skeleton3D in scene.find_children("*", "Skeleton3D", true, false):
		var groups := {}  # Material -> [vertices, normals, bones, weights, indices]
		var skin := Skin.new()
		var fused: Array[MeshInstance3D] = []
		for part: MeshInstance3D in skeleton.find_children("*", "MeshInstance3D", true, false):
			if part.mesh == null or part.skin == null or part.get_node_or_null(part.skeleton) != skeleton:
				continue
			if not _fusable(part.mesh):
				continue
			var offset := skin.get_bind_count()
			for i in part.skin.get_bind_count():
				var bone_name := part.skin.get_bind_name(i)
				if bone_name != &"":
					skin.add_named_bind(bone_name, part.skin.get_bind_pose(i))
				else:
					skin.add_bind(part.skin.get_bind_bone(i), part.skin.get_bind_pose(i))
			for surface in part.mesh.get_surface_count():
				var material: Material = part.mesh.surface_get_material(surface)
				var arrays := part.mesh.surface_get_arrays(surface)
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				if not groups.has(material):
					groups[material] = [PackedVector3Array(), PackedVector3Array(), PackedInt32Array(),
						PackedFloat32Array(), PackedInt32Array()]
				var group: Array = groups[material]
				var base: int = group[0].size()
				group[0].append_array(vertices)
				group[1].append_array(arrays[Mesh.ARRAY_NORMAL])
				for bone: int in arrays[Mesh.ARRAY_BONES]:
					group[2].append(bone + offset)
				group[3].append_array(arrays[Mesh.ARRAY_WEIGHTS])
				var indices: Variant = arrays[Mesh.ARRAY_INDEX]
				for i in (indices.size() if indices != null else vertices.size()):
					group[4].append(base + (indices[i] if indices != null else i))
			fused.append(part)
		if fused.size() < 2:
			continue
		var mesh := ArrayMesh.new()
		for material: Material in groups:
			var arrays := []
			arrays.resize(Mesh.ARRAY_MAX)
			arrays[Mesh.ARRAY_VERTEX] = groups[material][0]
			arrays[Mesh.ARRAY_NORMAL] = groups[material][1]
			arrays[Mesh.ARRAY_BONES] = groups[material][2]
			arrays[Mesh.ARRAY_WEIGHTS] = groups[material][3]
			arrays[Mesh.ARRAY_INDEX] = groups[material][4]
			mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			mesh.surface_set_material(mesh.get_surface_count() - 1, material)
		var body := MeshInstance3D.new()
		body.name = "body"
		body.mesh = mesh
		body.skin = skin
		skeleton.add_child(body)
		body.skeleton = NodePath("..")
		for part in fused:
			part.get_parent().remove_child(part)
			part.free()


## Only plain four-weight, untextured parts are fused; anything else is left as it came.
func _fusable(mesh: Mesh) -> bool:
	for surface in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		if mesh.surface_get_material(surface) == null or arrays[Mesh.ARRAY_NORMAL] == null \
				or arrays[Mesh.ARRAY_BONES] == null or arrays[Mesh.ARRAY_WEIGHTS] == null \
				or arrays[Mesh.ARRAY_BONES].size() != vertices.size() * 4:
			return false
	return true


func _gather(node: Node, parent: Transform3D, groups: Dictionary) -> void:
	var xform := parent
	if node is Node3D:
		xform = parent * (node as Node3D).transform
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		var mesh: Mesh = (node as MeshInstance3D).mesh
		var turn := xform.basis.inverse().transposed()  # what carries normals
		var mirrored := xform.basis.determinant() < 0.0
		for surface in mesh.get_surface_count():
			var material: Material = mesh.surface_get_material(surface)
			var arrays := mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			if material == null or vertices.is_empty():
				continue
			if not groups.has(material):
				groups[material] = [PackedVector3Array(), PackedVector3Array(), PackedInt32Array()]
			var group: Array = groups[material]
			var base: int = group[0].size()
			var normals: Variant = arrays[Mesh.ARRAY_NORMAL]
			for i in vertices.size():
				group[0].append(xform * vertices[i])
				group[1].append((turn * normals[i]).normalized() if normals != null else Vector3.UP)
			var indices: Variant = arrays[Mesh.ARRAY_INDEX]
			var count: int = indices.size() if indices != null else vertices.size()
			for i in range(0, count - 2, 3):
				var a: int = indices[i] if indices != null else i
				var b: int = indices[i + 1] if indices != null else i + 1
				var c: int = indices[i + 2] if indices != null else i + 2
				group[2].append(base + a)
				group[2].append(base + (c if mirrored else b))
				group[2].append(base + (b if mirrored else c))
	for child in node.get_children():
		_gather(child, xform, groups)


func _measure(node: Node, parent: Transform3D, boxes: Array) -> void:
	var xform := parent
	if node is Node3D:
		xform = parent * (node as Node3D).transform
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		boxes.append(xform * (node as MeshInstance3D).mesh.get_aabb())
	for child in node.get_children():
		_measure(child, xform, boxes)
