extends RefCounted
## Loads the low-poly models in res://assets/kaykit (KayKit Medieval Hexagon Pack, CC0)
## straight from their glTF files at run time, so nothing needs importing in the editor.
##
## Every model in the pack shares one small gradient texture, and the parts painted in
## a faction's colour all sit in one rectangle of it. Rather than ship a set of models
## per colour, the green set is used for everyone and that rectangle is repainted in
## each owner's colour: any civ colour works, including ones the pack never had.

const DIR := "res://assets/kaykit/"
const TEXTURE := "hexagons_medieval.png"
## Where the green faction colour lives in the texture, in pixels.
const FACTION_RECT := Rect2i(398, 783, 98, 228)
## Brightest value in that rectangle as shipped; repainting keeps the shading relative to it.
const FACTION_VALUE := 0.62

var _models := {}  # name -> {"parts": [{"mesh", "xform"}], "aabb": AABB}, or {} if it failed to load
var _atlas: Image
var _base_material: StandardMaterial3D
var _tinted := {}  # colour as html -> StandardMaterial3D


func _init() -> void:
	_atlas = Image.load_from_file(ProjectSettings.globalize_path(DIR + TEXTURE))
	_base_material = _material_for(_atlas)


## A copy of the model sized to stand on `footprint` tiles, or null if it could not be loaded.
## `material` is the shared one from base_material() or tinted_material().
func instance(model: String, material: Material, footprint: float) -> Node3D:
	var data: Dictionary = _load(model)
	if data.is_empty():
		return null
	var aabb: AABB = data["aabb"]
	var root := Node3D.new()
	root.scale = Vector3.ONE * (footprint / maxf(maxf(aabb.size.x, aabb.size.z), 0.01))
	for part: Dictionary in data["parts"]:
		var node := MeshInstance3D.new()
		node.mesh = part["mesh"]
		node.transform = part["xform"]
		node.material_override = material
		root.add_child(node)
	return root


## Height of the model once scaled to `footprint`, for placing labels above it.
func height(model: String, footprint: float) -> float:
	var data: Dictionary = _load(model)
	if data.is_empty():
		return 1.0
	var aabb: AABB = data["aabb"]
	return (aabb.position.y + aabb.size.y) * footprint / maxf(maxf(aabb.size.x, aabb.size.z), 0.01)


## The first mesh of a model, for scattering many copies with a MultiMesh.
func mesh(model: String) -> Mesh:
	var data: Dictionary = _load(model)
	return null if data.is_empty() else data["parts"][0]["mesh"]


func base_material() -> StandardMaterial3D:
	return _base_material


## The pack's material with its faction colour repainted as `color`.
func tinted_material(color: Color) -> StandardMaterial3D:
	var key := color.to_html(false)
	if not _tinted.has(key):
		if _atlas == null:
			return _base_material
		var image: Image = _atlas.duplicate()
		for y in range(FACTION_RECT.position.y, FACTION_RECT.end.y):
			for x in range(FACTION_RECT.position.x, FACTION_RECT.end.x):
				# Keep the texture's light-to-dark shading, swap its hue and saturation for the owner's.
				var shade := clampf(image.get_pixel(x, y).v / FACTION_VALUE, 0.0, 1.0)
				image.set_pixel(x, y, Color.from_hsv(color.h, color.s, color.v * shade))
		_tinted[key] = _material_for(image)
	return _tinted[key]


func _material_for(image: Image) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	if image != null:
		material.albedo_texture = ImageTexture.create_from_image(image)
	material.roughness = 0.9
	return material


func _load(model: String) -> Dictionary:
	if _models.has(model):
		return _models[model]
	var result := {}
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var path := ProjectSettings.globalize_path(DIR + model + ".gltf")
	if FileAccess.file_exists(path) and document.append_from_file(path, state) == OK:
		var scene := document.generate_scene(state)
		if scene != null:
			var parts: Array = []
			_collect(scene, Transform3D.IDENTITY, parts)
			scene.free()
			if not parts.is_empty():
				var aabb: AABB = parts[0]["xform"] * parts[0]["mesh"].get_aabb()
				for part: Dictionary in parts:
					aabb = aabb.merge(part["xform"] * part["mesh"].get_aabb())
				result = {"parts": parts, "aabb": aabb}
	if result.is_empty():
		push_warning("Model %s could not be loaded; a plain block is used instead" % model)
	_models[model] = result
	return result


func _collect(node: Node, parent: Transform3D, parts: Array) -> void:
	var xform := parent
	if node is Node3D:
		xform = parent * (node as Node3D).transform
	var found: Mesh = null
	if node is MeshInstance3D:
		found = (node as MeshInstance3D).mesh
	elif node is ImporterMeshInstance3D:
		found = (node as ImporterMeshInstance3D).mesh.get_mesh()
	if found != null:
		parts.append({"mesh": found, "xform": xform})
	for child in node.get_children():
		_collect(child, xform, parts)
