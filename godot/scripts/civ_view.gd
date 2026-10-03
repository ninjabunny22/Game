extends Node3D
## Everything that sits on the terrain: resource deposits, capitals and buildings.
## Buildings and capitals are low-poly models whose roofs and banners are painted in
## their owner's colour; they rise out of the ground while under construction. Where
## two building types share a model, a small pennant in the type's colour tells them
## apart, and models with nothing to paint fly their owner's flag instead. Arcs between capitals show
## what holds between two civs: a trade deal (green), an alliance (blue), a war (red).
##
## A tile holds up to three buildings, and buildings belong to named villages. The map
## shows them two ways, switching with the camera like villagers and labels do:
##   - from afar, each village is one consolidated cluster (bigger as it grows), and a
##     capital's town is a ring of houses around its castle or tower;
##   - closer in, every building is drawn on its own, sharing its tile with the others
##     there, and each village is named.

const BUILDING_WIDTH := 0.62  # of the plain block used if a model is missing
const PLINTH_HEIGHT := 0.12

## Building type -> the model that stands for it.
##   size:   how much of the tile it covers
##   tinted: the model has parts in the faction colour (otherwise it flies the owner's flag)
##   marker: it shares its model with another type, so it carries a pennant in its own colour
const BUILDING_MODELS := {
	"house": {"model": "building_home_A_green", "alt": "building_home_B_green", "size": 0.78, "tinted": true},
	"farm": {"model": "building_grain", "size": 0.95},
	"lumber_camp": {"model": "building_lumbermill_green", "size": 0.9, "tinted": true},
	"quarry": {"model": "building_mine_green", "size": 0.9, "tinted": true, "marker": true},
	"mine": {"model": "building_mine_green", "size": 0.9, "tinted": true},
	"granary": {"model": "building_windmill_green", "size": 0.85, "tinted": true},
	"lumber_yard": {"model": "resource_lumber", "size": 0.8},
	"stone_yard": {"model": "resource_stone", "size": 0.7},
	"ore_depot": {"model": "crate_A_big", "size": 0.55, "marker": true},
	"treasury": {"model": "building_tavern_green", "size": 0.85, "tinted": true, "marker": true},
	"cistern": {"model": "building_well_green", "size": 0.6, "tinted": true},
	"reservoir": {"model": "building_well_green", "size": 0.8, "tinted": true, "marker": true},
	"library": {"model": "building_church_green", "size": 0.8, "tinted": true},
	"university": {"model": "building_church_green", "size": 0.95, "tinted": true, "marker": true},
	"market": {"model": "building_market_green", "size": 0.95, "tinted": true},
	"bank": {"model": "building_tavern_green", "size": 0.95, "tinted": true, "marker": true},
	"workshop": {"model": "building_blacksmith_green", "size": 0.9, "tinted": true},
	"factory": {"model": "building_blacksmith_green", "size": 0.98, "tinted": true, "marker": true},
	"aqueduct": {"model": "building_bridge_A", "size": 0.95, "lift": 0.45},
	# A quay with a warehouse and a ship alongside; it is turned so the quay is on the water.
	"harbour": {"scene": "Harbour", "size": 3.6, "full_size": true, "faces_water": true,
		"model": "building_watermill_green", "tinted": true},
	"barracks": {"model": "building_barracks_green", "size": 0.95, "tinted": true},
	"academy": {"model": "building_archeryrange_green", "size": 0.95, "tinted": true},
	"walls": {"model": "wall_straight", "size": 0.98},
	"fortress": {"model": "building_tower_B_green", "size": 0.9, "tinted": true},
	# Its own model, from assets/characters: a long building that has to read beside a commander,
	# so it is drawn larger than its tile and keeps its size when it shares the tile.
	"stables": {"scene": "Stable", "size": 2.0, "full_size": true},
}
const CAPITAL_MODEL := "building_castle_green"  # a civ's own capital
const TOWN_MODEL := "building_tower_A_green"  # every other region capital
const CAPITAL_FOOTPRINT := 1.7
const TOWN_FOOTPRINT := 1.05

## How buildings sharing a tile are laid out: [scale, distance from the tile's centre].
const TILE_LAYOUT := {1: [1.0, 0.0], 2: [0.58, 0.25], 3: [0.52, 0.28]}
const WATER_SIDE := 0.0  # turn that brings the harbour model's quay round to face the water
const SHARED_SCALE := 0.5  # buildings on a capital's tile stand around it, this size

## A village seen from afar, by how many buildings it has: [at least, tiles across, models].
const VILLAGE_TIERS := [
	[20, 3.0, ["building_church_green", "building_market_green", "building_home_A_green", "building_home_B_green",
		"building_home_A_green", "building_windmill_green", "building_home_B_green"]],
	[6, 2.2, ["building_windmill_green", "building_home_A_green", "building_home_B_green", "building_home_A_green"]],
	[0, 1.5, ["building_home_A_green", "building_home_B_green"]],
]
## The town around a capital, from afar: houses ringing the castle or tower. [at least, houses, landmarks]
const CAPITAL_TIERS := [
	[45, 9, ["building_church_green", "building_market_green", "building_windmill_green"]],
	[20, 6, ["building_church_green"]],
	[5, 4, []],
	[0, 0, []],
]
const LINK_COLORS := {"deal": Color(0.35, 0.9, 0.4), "alliance": Color(0.35, 0.65, 1.0), "war": Color(1.0, 0.25, 0.2),
	"neutral": Color(0.75, 0.75, 0.78, 0.45)}
const LINK_WIDTH := 0.45
const LINK_SEGMENTS := 24

var _terrain: Node3D
var _building_defs := {}
var _civ_colors: Array = []
var _nodes := {}  # key -> Node3D: capitals, buildings ("b:...") and villages ("v:...")
var _body_meshes := {}  # building type -> BoxMesh
var _plinth_meshes := {}  # civ id -> BoxMesh
var _models: RefCounted  # models.gd
var _characters: RefCounted  # characters.gd
var _regions := {}  # region id -> static info from init
var _native_color := Color(0.6, 0.55, 0.48)
var _native_name := ""
var _links: ImmediateMesh
var _link_labels := {}  # "a:b" -> Label3D naming the war or alliance
var _detail := 0  # 0 whole-map view, 1 closer, 2 full detail
var _link_material: StandardMaterial3D


func setup(terrain: Node3D, init: Dictionary, civ_colors: Array, models: RefCounted, characters: RefCounted) -> void:
	_models = models
	_characters = characters
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
		var capital_tiles := {}  # "x:y" -> footprint of the capital standing there
		index = 0
		for settlement: Dictionary in civ["settlements"]:
			capital_tiles["%d:%d" % [int(settlement["x"]), int(settlement["y"])]] = CAPITAL_FOOTPRINT if index == 0 else TOWN_FOOTPRINT
			index += 1
		# Buildings share tiles: work out who stands where before drawing any of them.
		var on_tile := {}
		for building: Dictionary in civ["buildings"]:
			var tile := "%d:%d" % [int(building["x"]), int(building["y"])]
			if not on_tile.has(tile):
				on_tile[tile] = []
			on_tile[tile].append(building)
		for tile: String in on_tile:
			var there: Array = on_tile[tile]
			there.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return int(a["id"]) < int(b["id"]))
			var around: float = capital_tiles.get(tile, 0.0)
			for slot in there.size():
				var building: Dictionary = there[slot]
				# The key holds everything the node's look depends on, so a change rebuilds it.
				var key := "b:%d:%d:%d:%d:%.2f" % [civ_id, int(building["id"]), slot, there.size(), around]
				seen[key] = true
				if not _nodes.has(key):
					_nodes[key] = _make_building(civ_id, building, slot, there.size(), around)
				var node: Node3D = _nodes[key]
				var size: float = node.get_meta("size")
				var grown: float = 1.0 if building["complete"] else lerpf(0.15, 1.0, float(building["progress"]))
				node.scale = Vector3(size, size * grown, size)
		for village: Dictionary in civ["villages"]:
			var count := int(village["buildings"])
			var tiers: Array = CAPITAL_TIERS if village["capital"] else VILLAGE_TIERS
			var tier := 0
			while count < int(tiers[tier][0]):
				tier += 1
			var key := "v:%d:%d:%d" % [civ_id, int(village["id"]), tier]
			seen[key] = true
			if not _nodes.has(key):
				var footprint: float = capital_tiles.get("%d:%d" % [int(village["x"]), int(village["y"])], TOWN_FOOTPRINT)
				_nodes[key] = _make_village(civ_id, village, tier, footprint)
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
		_show_settled(node)
	for label: Label3D in _link_labels.values():
		_show_link_label(label)


func _show_capital_label(node: Node3D) -> void:
	if not node.has_meta("label"):
		return
	var label: Label3D = node.get_meta("label")
	var is_main: bool = node.get_meta("main")
	label.visible = is_main or _detail >= 1
	label.pixel_size = 0.042 if _detail == 0 else 0.02


## Buildings one by one up close; whole villages from afar.
func _show_settled(node: Node3D) -> void:
	match node.get_meta("kind", ""):
		"building":
			node.visible = _detail >= 1
		"village":
			node.get_meta("cluster").visible = _detail == 0
			if node.has_meta("name_label"):
				var name_label: Label3D = node.get_meta("name_label")
				name_label.visible = _detail >= 1
				name_label.pixel_size = 0.014 if _detail == 1 else 0.009


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


## `slot` of `count` buildings on the tile; `around` is the footprint of the capital
## standing on that tile (0 for an ordinary tile), which the buildings then stand around.
func _make_building(civ_id: int, building: Dictionary, slot: int, count: int, around: float) -> Node3D:
	var type: String = building["type"]
	var x := int(building["x"])
	var y := int(building["y"])
	var root := Node3D.new()
	var layout: Array = TILE_LAYOUT[clampi(count, 1, 3)]
	var size: float = layout[0]
	var out: float = layout[1]
	if around > 0.0:
		size = SHARED_SCALE
		out = around * 0.5 + 0.22
	# Spread the tile's buildings evenly round its centre, starting somewhere different on each tile.
	var angle := TAU * slot / maxi(count, 3 if around > 0.0 else count) + (x * 5 + y * 3) % 6 * PI / 3
	var spot: Vector3 = _terrain.tile_position(x, y) + Vector3(cos(angle), 0, sin(angle)) * out
	if out > 0.0:
		spot.y = _terrain.height_at(spot.x, spot.z)
	root.position = spot
	if BUILDING_MODELS.get(type, {}).get("full_size", false):
		size = 1.0
	root.set_meta("kind", "building")
	root.set_meta("size", size)
	root.visible = _detail >= 1
	var color: Color = _civ_colors[civ_id]
	var spec: Dictionary = BUILDING_MODELS.get(type, {})
	var model: Node3D = null
	if spec.has("scene"):
		model = _characters.instance(spec["scene"], color, 0.0, float(spec["size"]))
		if model != null:
			model.rotation.y = (x * 7 + y * 13 + slot) % 4 * PI / 2
			if spec.get("faces_water", false):
				model.rotation.y = _toward_water(x, y) + WATER_SIDE
				root.position = _terrain.tile_position(x, y)  # on the shore itself, not pushed to a corner
			root.add_child(model)
			add_child(root)
			return root
		spec = spec.duplicate()
		spec["size"] = 0.9  # the model file is missing: fall back to the pack's building
	if not spec.is_empty() and spec.has("model") and model == null:
		var name: String = spec["model"]
		if spec.has("alt") and (x + y + slot) % 2 == 1:
			name = spec["alt"]  # two looks for the commonest building, so a town is not all one house
		var material: Material = _models.tinted_material(color) if spec.get("tinted", false) else _models.base_material()
		model = _models.instance(name, material, float(spec["size"]))
	if model == null:
		_add_block(root, civ_id, type)
	else:
		# Face one of four ways, the same way every time for a given tile.
		model.rotation.y = (x * 7 + y * 13 + slot) % 4 * PI / 2
		model.position.y = float(spec.get("lift", 0.0))
		root.add_child(model)
		var top: float = _models.height(spec["model"], float(spec["size"])) + float(spec.get("lift", 0.0))
		if not spec.get("tinted", false):
			_add_flag(root, color)
		if spec.get("marker", false):
			_add_marker(root, Color.html(_building_defs[type]["color"]), top)
	add_child(root)
	return root


## A village as one cluster of models, for the whole-map view, with its name for closer in.
## A capital's town has no name of its own (the capital is already labelled) and its
## houses ring the castle or tower instead of standing at the centre.
func _make_village(civ_id: int, village: Dictionary, tier: int, footprint: float) -> Node3D:
	var x := int(village["x"])
	var y := int(village["y"])
	var color: Color = _civ_colors[civ_id]
	var material: Material = _models.tinted_material(color)
	var root := Node3D.new()
	root.position = _terrain.tile_position(x, y)
	root.set_meta("kind", "village")
	var cluster := Node3D.new()
	root.add_child(cluster)
	root.set_meta("cluster", cluster)
	var start := (x * 5 + y * 3) % 6 * PI / 3
	var name_label: Label3D = null
	if village["capital"]:
		var spec: Array = CAPITAL_TIERS[tier]
		var houses := int(spec[1])
		var landmarks: Array = spec[2]
		var ring := footprint * 0.5 + 0.75
		for i in houses + landmarks.size():
			var model_name: String = landmarks[i - houses] if i >= houses else ("building_home_A_green" if i % 2 == 0 else "building_home_B_green")
			_place(cluster, model_name, material, 1.25 if i >= houses else 0.95, start + TAU * i / (houses + landmarks.size()), ring)
	else:
		var spec: Array = VILLAGE_TIERS[tier]
		var across: float = spec[1]
		var models: Array = spec[2]
		# The first model is the landmark at the centre; the rest stand round it.
		_place(cluster, models[0], material, across * 0.5, start, 0.0)
		for i in range(1, models.size()):
			_place(cluster, models[i], material, across * 0.36, start + TAU * i / (models.size() - 1), across * 0.42)
		name_label = Label3D.new()
		name_label.text = str(village["name"])
		name_label.font_size = 40
		name_label.outline_size = 12
		name_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		name_label.no_depth_test = true
		name_label.modulate = color.lightened(0.6)
		name_label.position.y = 1.5
		root.add_child(name_label)
	if name_label != null:
		root.set_meta("name_label", name_label)
	_show_settled(root)
	add_child(root)
	return root


func _place(parent: Node3D, model_name: String, material: Material, footprint: float, angle: float, out: float) -> void:
	var model: Node3D = _models.instance(model_name, material, footprint)
	if model == null:
		return
	var offset := Vector3(cos(angle), 0, sin(angle)) * out
	var origin: Vector3 = parent.get_parent().position
	model.position = offset
	model.position.y = _terrain.height_at(origin.x + offset.x, origin.z + offset.z) - origin.y
	model.rotation.y = -angle + PI / 2
	parent.add_child(model)


## The direction (as a rotation about the vertical) from a tile to the lowest ground beside it,
## which for a shore tile is the water.
func _toward_water(x: int, y: int) -> float:
	var best := Vector2.RIGHT
	var lowest := INF
	for step: Vector2 in [Vector2(1, 0), Vector2(-1, 0), Vector2(0, 1), Vector2(0, -1)]:
		var there: Vector3 = _terrain.tile_position(x, y) + Vector3(step.x, 0, step.y)
		var ground: float = _terrain.height_at(there.x, there.z)
		if ground < lowest:
			lowest = ground
			best = step
	return atan2(best.x, best.y)


## Nothing on the model shows whose it is: plant the owner's flag at the corner of the tile.
func _add_flag(root: Node3D, color: Color) -> void:
	var flag: Node3D = _models.instance("flag_green", _models.tinted_material(color), 0.42)
	if flag != null:
		flag.position = Vector3(0.36, 0.0, 0.36)
		root.add_child(flag)


## A pennant in the building type's own colour, for types that share a model.
func _add_marker(root: Node3D, color: Color, top: float) -> void:
	var pole := MeshInstance3D.new()
	var pole_mesh := CylinderMesh.new()
	pole_mesh.top_radius = 0.02
	pole_mesh.bottom_radius = 0.02
	pole_mesh.height = 0.5
	pole_mesh.material = _flat_material(Color(0.25, 0.2, 0.15))
	pole.mesh = pole_mesh
	pole.position = Vector3(-0.3, top + 0.05, -0.3)
	root.add_child(pole)
	var pennant := MeshInstance3D.new()
	var pennant_mesh := BoxMesh.new()
	pennant_mesh.size = Vector3(0.26, 0.17, 0.03)
	pennant_mesh.material = _flat_material(color)
	pennant.mesh = pennant_mesh
	pennant.position = Vector3(-0.17, top + 0.21, -0.3)
	root.add_child(pennant)


## The plain block used when a building has no model, or its model failed to load.
func _add_block(root: Node3D, civ_id: int, type: String) -> void:
	var height := float(_building_defs[type]["height"])
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


## A region capital. A civ's own capital is a castle, clearly the largest thing on the
## map; every other capital is a tall tower. Both wear their holder's colour (the
## native faction's, for a capital no civ holds), with the name above.
func _make_capital(color: Color, caption: String, x: int, y: int, is_main: bool) -> Node3D:
	var root := Node3D.new()
	root.position = _terrain.tile_position(x, y)
	var model_name := CAPITAL_MODEL if is_main else TOWN_MODEL
	var footprint := CAPITAL_FOOTPRINT if is_main else TOWN_FOOTPRINT
	var model: Node3D = _models.instance(model_name, _models.tinted_material(color), footprint)
	var top := 3.0
	if model != null:
		root.add_child(model)
		top = _models.height(model_name, footprint)
	else:  # no model: the old keep
		var keep := MeshInstance3D.new()
		var keep_mesh := BoxMesh.new()
		keep_mesh.size = Vector3(0.9, 1.3, 0.9)
		keep_mesh.material = _flat_material(color.lightened(0.35))
		keep.mesh = keep_mesh
		keep.position.y = 0.65
		root.add_child(keep)

	var label := Label3D.new()
	label.text = caption
	label.font_size = 64 if is_main else 44
	label.outline_size = 16
	label.pixel_size = 0.02
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = color.lightened(0.5)
	label.position.y = top + 1.3
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
