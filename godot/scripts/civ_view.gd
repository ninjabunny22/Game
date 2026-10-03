extends Node3D
## Everything that sits on the terrain: resource deposits, settlements and buildings.
## Buildings are blocks in their type's colour on a plinth in the owner's colour;
## they rise out of the ground while under construction. Arcs between capitals show
## what holds between two civs: a trade deal (green), an alliance (blue), a war (red).

const BUILDING_WIDTH := 0.62
const PLINTH_HEIGHT := 0.12
const LINK_COLORS := {"deal": Color(0.35, 0.9, 0.4), "alliance": Color(0.35, 0.65, 1.0), "war": Color(1.0, 0.25, 0.2),
	"neutral": Color(0.75, 0.75, 0.78, 0.45)}
const LINK_WIDTH := 0.45
const LINK_SEGMENTS := 24

var _terrain: Node3D
var _building_defs := {}
var _civ_colors: Array = []
var _nodes := {}  # "civ:x:y" -> Node3D
var _body_meshes := {}  # building type -> BoxMesh
var _plinth_meshes := {}  # civ id -> BoxMesh
var _regions := {}  # region id -> static info from init
var _native_color := Color(0.6, 0.55, 0.48)
var _native_name := ""
var _links: ImmediateMesh
var _link_labels := {}  # "a:b" -> Label3D naming the war or alliance
var _detail := 0  # 0 whole-map view, 1 closer, 2 full detail
var _link_material: StandardMaterial3D


func setup(terrain: Node3D, init: Dictionary, civ_colors: Array) -> void:
	for child in get_children():
		child.queue_free()
	_nodes.clear()
	_link_labels.clear()
	_body_meshes.clear()
	_plinth_meshes.clear()
	_terrain = terrain
	_building_defs = init["buildings"]
	_civ_colors = civ_colors
	_add_deposits(init["map"]["deposits"], init["deposit_types"])
	_regions.clear()
	for region: Dictionary in init["regions"]:
		_regions[int(region["id"])] = region
	_native_color = Color.html(init["native_faction"]["color"])
	_native_name = init["native_faction"]["name"]

	_link_material = StandardMaterial3D.new()
	_link_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_link_material.vertex_color_use_as_albedo = true
	_link_material.vertex_color_is_srgb = true
	_link_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	_link_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_links = ImmediateMesh.new()
	var links_instance := MeshInstance3D.new()
	links_instance.mesh = _links
	links_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(links_instance)


## `regions` is the tick's list of who holds each region (owner null = the native faction).
func update(civs: Array, regions: Array) -> void:
	var seen := {}
	# Capitals still held by the native faction.
	for region: Dictionary in regions:
		if region["owner"] != null:
			continue
		var info: Dictionary = _regions[int(region["id"])]
		var key := "n:%d" % int(region["id"])
		seen[key] = true
		if not _nodes.has(key):
			var caption := "%s\n%s" % [info["capital"], info["name"]]
			_nodes[key] = _make_capital(_native_color, caption, int(info["x"]), int(info["y"]), false)
	for civ: Dictionary in civs:
		var civ_id := int(civ["id"])
		var index := 0
		for settlement: Dictionary in civ["settlements"]:
			# The first capital in the list is the civ's own; it is marked with a star and a taller flag.
			var is_main := index == 0
			index += 1
			var key := "%d:%d:%d:%s" % [civ_id, int(settlement["x"]), int(settlement["y"]), is_main]
			seen[key] = true
			if not _nodes.has(key):
				var caption := ("★ " if is_main else "") + str(settlement["name"])
				_nodes[key] = _make_capital(_civ_colors[civ_id], caption, int(settlement["x"]), int(settlement["y"]), is_main)
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


## What the map labels at each zoom. From afar only each civ's own capital is named,
## larger so it can be read; other capitals and alliance names appear closer in.
## War names always show: they are the news.
func set_detail(detail: int) -> void:
	_detail = detail
	for node: Node3D in _nodes.values():
		_show_capital_label(node)
	for label: Label3D in _link_labels.values():
		_show_link_label(label)


func _show_capital_label(node: Node3D) -> void:
	if not node.has_meta("label"):
		return
	var label: Label3D = node.get_meta("label")
	var is_main: bool = node.get_meta("main")
	label.visible = is_main or _detail >= 1
	label.pixel_size = 0.042 if _detail == 0 else 0.02


func _show_link_label(label: Label3D) -> void:
	var is_war: bool = label.get_meta("war", false)
	label.visible = is_war or _detail >= 1
	label.pixel_size = 0.04 if _detail == 0 else 0.018


## Redraws the arcs between civ capitals. Every pair of living civs has one, coloured
## by what holds between them: red for war, blue for alliance, green for a trade
## deal, thin grey for nothing in particular. Wars and alliances carry their name.
func update_links(civs: Array, relations: Array, deals: Array) -> void:
	var capitals := {}
	for civ: Dictionary in civs:
		if civ["alive"] and not civ["settlements"].is_empty():
			var capital: Dictionary = civ["settlements"][0]
			capitals[int(civ["id"])] = _terrain.tile_position(int(capital["x"]), int(capital["y"])) + Vector3(0, 4.4, 0)
	var trading := {}
	for deal: Dictionary in deals:
		trading["%d:%d" % [mini(int(deal["a"]), int(deal["b"])), maxi(int(deal["a"]), int(deal["b"]))]] = true

	_links.clear_surfaces()
	var named := {}
	for relation: Dictionary in relations:
		var a := int(relation["a"])
		var b := int(relation["b"])
		if not capitals.has(a) or not capitals.has(b):
			continue
		var key := "%d:%d" % [a, b]
		var status: String = relation["status"]
		if status == "war":
			named[key] = _add_link(capitals[a], capitals[b], LINK_COLORS["war"], 1.0, LINK_WIDTH * 1.5)
		elif status == "alliance":
			named[key] = _add_link(capitals[a], capitals[b], LINK_COLORS["alliance"], 1.0, LINK_WIDTH)
		if trading.has(key):
			_add_link(capitals[a], capitals[b], LINK_COLORS["deal"], 0.6, LINK_WIDTH)
		elif status == "peace":
			_add_link(capitals[a], capitals[b], LINK_COLORS["neutral"], 0.35, LINK_WIDTH * 0.45)
		if named.has(key):
			_name_link(key, str(relation["name"]) if relation["name"] != null else "", named[key], LINK_COLORS[status])
	for key: String in _link_labels.keys():
		if not named.has(key):
			_link_labels[key].queue_free()
			_link_labels.erase(key)


## A ribbon arcing from one point to another; `lift` scales how high it rises.
## Returns the top of the arc, where a name can go.
func _add_link(from: Vector3, to: Vector3, color: Color, lift: float, width: float) -> Vector3:
	var side := (to - from).cross(Vector3.UP).normalized() * width / 2.0
	var height := lift * (5.0 + 0.15 * from.distance_to(to))
	_links.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP, _link_material)
	for i in LINK_SEGMENTS + 1:
		var t := float(i) / LINK_SEGMENTS
		var point := from.lerp(to, t) + Vector3.UP * height * sin(PI * t)
		_links.surface_set_color(color)
		_links.surface_add_vertex(point - side)
		_links.surface_set_color(color)
		_links.surface_add_vertex(point + side)
	_links.surface_end()
	return from.lerp(to, 0.5) + Vector3.UP * (height + 1.2)


## The name of a war or alliance, floating at the top of its arc.
func _name_link(key: String, text: String, at: Vector3, color: Color) -> void:
	if not _link_labels.has(key):
		var label := Label3D.new()
		label.font_size = 40
		label.outline_size = 12
		label.pixel_size = 0.018
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		add_child(label)
		_link_labels[key] = label
	var node: Label3D = _link_labels[key]
	node.text = text
	node.modulate = color.lightened(0.45)
	node.position = at
	node.set_meta("war", color == LINK_COLORS["war"])
	_show_link_label(node)


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


## A region capital: a keep with a flag in its holder's colour and its name above.
func _make_capital(color: Color, caption: String, x: int, y: int, is_main: bool) -> Node3D:
	var root := Node3D.new()
	root.position = _terrain.tile_position(x, y)
	var size := 1.0 if is_main else 0.8

	var keep := MeshInstance3D.new()
	var keep_mesh := BoxMesh.new()
	keep_mesh.size = Vector3(0.9 * size, 1.3 * size, 0.9 * size)
	keep_mesh.material = _flat_material(color.lightened(0.35))
	keep.mesh = keep_mesh
	keep.position.y = 0.65 * size
	root.add_child(keep)

	var pole_height := 3.2 * size
	var pole := MeshInstance3D.new()
	var pole_mesh := CylinderMesh.new()
	pole_mesh.top_radius = 0.05
	pole_mesh.bottom_radius = 0.05
	pole_mesh.height = pole_height
	pole_mesh.material = _flat_material(Color(0.9, 0.9, 0.9))
	pole.mesh = pole_mesh
	pole.position.y = 1.3 * size + pole_height / 2.0
	root.add_child(pole)

	var flag := MeshInstance3D.new()
	var flag_mesh := BoxMesh.new()
	flag_mesh.size = Vector3(1.1 * size, 0.7 * size, 0.06)
	flag_mesh.material = _flat_material(color)
	flag.mesh = flag_mesh
	flag.position = Vector3(0.6 * size, 1.3 * size + pole_height - 0.4, 0.0)
	root.add_child(flag)

	var label := Label3D.new()
	label.text = caption
	label.font_size = 64 if is_main else 44
	label.outline_size = 16
	label.pixel_size = 0.02
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = color.lightened(0.5)
	label.position.y = 1.3 * size + pole_height + 1.2
	root.add_child(label)
	root.set_meta("label", label)
	root.set_meta("main", is_main)
	_show_capital_label(root)

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
