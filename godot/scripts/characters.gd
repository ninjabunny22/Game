extends RefCounted
## Loads the models in res://assets/characters straight from their .glb files at run
## time: the rigged, animated Commander, Villager and Rider, and the static Stable,
## Harbour and Boat. Each file is read once; every figure on the map is a copy of that.
##
## The models carry plain named materials rather than a texture, so a figure is put in
## its civ's colour by swapping the material of that name (the commander's cloth, the
## villager's tunic) for one in the civ's colour.

const DIR := "res://assets/characters/"
## The material on each model that takes the owner's colour.
const TEAM_MATERIALS := {
	"Commander": ["cloth_team"], "Villager": ["tunic_moss"], "Rider": ["tunic_moss", "saddle_blanket"],
	"Stable": ["cloth_team"], "Boat": ["cloth_team"], "Harbour": ["cloth_team"],
}

## Parts of a model that are left out: the stable comes on a wide plate of grass, which would
## either bury the neighbouring tiles or force the building itself to be drawn tiny.
const LEFT_OUT := {"Stable": ["grass"], "Harbour": ["grass", "dirt"]}

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
					tinted.albedo_color = color
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
	if FileAccess.file_exists(path) and document.append_from_file(path, state) == OK:
		var scene := document.generate_scene(state)
		if scene is Node3D:
			_strip(scene, LEFT_OUT.get(model, []))
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


func _measure(node: Node, parent: Transform3D, boxes: Array) -> void:
	var xform := parent
	if node is Node3D:
		xform = parent * (node as Node3D).transform
	if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
		boxes.append(xform * (node as MeshInstance3D).mesh.get_aabb())
	for child in node.get_children():
		_measure(child, xform, boxes)
