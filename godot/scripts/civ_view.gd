extends Node3D
## Everything that sits on the terrain: resource deposits, settlements and buildings.
## Buildings are blocks in their type's colour on a plinth in the owner's colour;
## they rise out of the ground while under construction.

const BUILDING_WIDTH := 0.62
const PLINTH_HEIGHT := 0.12

var _terrain: Node3D
var _building_defs := {}
var _civ_colors: Array = []
var _nodes := {}  # "civ:x:y" -> Node3D
var _body_meshes := {}  # building type -> BoxMesh
var _plinth_meshes := {}  # civ id -> BoxMesh


func setup(terrain: Node3D, init: Dictionary, civ_colors: Array) -> void:
	for child in get_children():
		child.queue_free()
	_nodes.clear()
	_body_meshes.clear()
	_plinth_meshes.clear()
	_terrain = terrain
	_building_defs = init["buildings"]
	_civ_colors = civ_colors
	_add_deposits(init["map"]["deposits"], init["deposit_types"])


func update(civs: Array) -> void:
	var seen := {}
	for civ: Dictionary in civs:
		var civ_id := int(civ["id"])
		for settlement: Dictionary in civ["settlements"]:
			var key := "%d:%d:%d" % [civ_id, int(settlement["x"]), int(settlement["y"])]
			seen[key] = true
			if not _nodes.has(key):
				_nodes[key] = _make_settlement(civ_id, settlement)
		for building: Dictionary in civ["buildings"]:
			var key := "%d:%d:%d" % [civ_id, int(building["x"]), int(building["y"])]
			seen[key] = true
			if not _nodes.has(key):
				_nodes[key] = _make_building(civ_id, building)
			var node: Node3D = _nodes[key]
			node.scale.y = 1.0 if building["complete"] else lerpf(0.15, 1.0, float(building["progress"]))
	for key: String in _nodes.keys():
		if not seen.has(key):
			_nodes[key].queue_free()
			_nodes.erase(key)


func _make_building(civ_id: int, building: Dictionary) -> Node3D:
	var type: String = building["type"]
	var height := float(_building_defs[type]["height"])
	var root := Node3D.new()
	root.position = _terrain.tile_position(int(building["x"]), int(building["y"]))

	if not _body_meshes.has(type):
		var body_mesh := BoxMesh.new()
		body_mesh.size = Vector3(BUILDING_WIDTH, height, BUILDING_WIDTH)
		body_mesh.material = _flat_material(Color.html(_building_defs[type]["color"]))
		_body_meshes[type] = body_mesh
	var body := MeshInstance3D.new()
	body.mesh = _body_meshes[type]
	body.position.y = PLINTH_HEIGHT + height / 2.0
	root.add_child(body)

	if not _plinth_meshes.has(civ_id):
		var plinth_mesh := BoxMesh.new()
		plinth_mesh.size = Vector3(0.94, PLINTH_HEIGHT, 0.94)
		plinth_mesh.material = _flat_material(_civ_colors[civ_id])
		_plinth_meshes[civ_id] = plinth_mesh
	var plinth := MeshInstance3D.new()
	plinth.mesh = _plinth_meshes[civ_id]
	plinth.position.y = PLINTH_HEIGHT / 2.0
	root.add_child(plinth)

	add_child(root)
	return root


func _make_settlement(civ_id: int, settlement: Dictionary) -> Node3D:
	var color: Color = _civ_colors[civ_id]
	var root := Node3D.new()
	root.position = _terrain.tile_position(int(settlement["x"]), int(settlement["y"]))

	var keep := MeshInstance3D.new()
	var keep_mesh := BoxMesh.new()
	keep_mesh.size = Vector3(0.9, 1.3, 0.9)
	keep_mesh.material = _flat_material(color.lightened(0.35))
	keep.mesh = keep_mesh
	keep.position.y = 0.65
	root.add_child(keep)

	var pole := MeshInstance3D.new()
	var pole_mesh := CylinderMesh.new()
	pole_mesh.top_radius = 0.05
	pole_mesh.bottom_radius = 0.05
	pole_mesh.height = 3.2
	pole_mesh.material = _flat_material(Color(0.9, 0.9, 0.9))
	pole.mesh = pole_mesh
	pole.position.y = 1.3 + 1.6
	root.add_child(pole)

	var flag := MeshInstance3D.new()
	var flag_mesh := BoxMesh.new()
	flag_mesh.size = Vector3(1.1, 0.7, 0.06)
	flag_mesh.material = _flat_material(color)
	flag.mesh = flag_mesh
	flag.position = Vector3(0.6, 4.1, 0.0)
	root.add_child(flag)

	var label := Label3D.new()
	label.text = settlement["name"]
	label.font_size = 64
	label.outline_size = 16
	label.pixel_size = 0.02
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = color.lightened(0.5)
	label.position.y = 5.6
	root.add_child(label)

	add_child(root)
	return root


func _add_deposits(deposits: Array, deposit_types: Dictionary) -> void:
	var material := _flat_material(Color.WHITE)
	material.vertex_color_use_as_albedo = true
	material.vertex_color_is_srgb = true
	var marker := BoxMesh.new()
	marker.size = Vector3(0.28, 0.28, 0.28)
	marker.material = material

	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = true
	multimesh.mesh = marker
	multimesh.instance_count = deposits.size()
	# Markers sit in the corner of their tile, leaving the centre for buildings.
	var tilt := Basis.from_euler(Vector3(PI / 4, PI / 4, 0))
	for i in deposits.size():
		var deposit: Dictionary = deposits[i]
		var origin: Vector3 = _terrain.tile_position(int(deposit["x"]), int(deposit["y"]))
		multimesh.set_instance_transform(i, Transform3D(tilt, origin + Vector3(-0.3, 0.2, -0.3)))
		multimesh.set_instance_color(i, Color.html(deposit_types[deposit["type"]]["color"]))

	var instance := MultiMeshInstance3D.new()
	instance.multimesh = multimesh
	add_child(instance)


func _flat_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	return material
