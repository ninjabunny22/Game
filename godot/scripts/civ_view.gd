extends Node3D
## Everything that sits on the terrain: resource deposits, capitals and buildings.
## Buildings and capitals are low-poly models whose roofs and banners are painted in
## their owner's colour; they rise out of the ground while under construction. Where
## two building types share a model, a small pennant in the type's colour tells them
## apart, and models with nothing to paint fly their owner's flag instead. Arcs between capitals show
## what holds between two civs: a trade deal (green), an alliance (blue), a war (red).
##
## Every building stands on its own ground and is drawn at every zoom. Finished buildings
## are drawn in batches (batches.gd); a building site is a node of its own while it rises.
## Buildings belong to named villages, whose names appear closer in.

const Batches := preload("res://scripts/batches.gd")

const BUILDING_WIDTH := 0.62  # of the plain block used if a model is missing
const PLINTH_HEIGHT := 0.12

## Building type -> the model that stands for it.
##   size:   how much of the tile it covers
##   tinted: the model has parts in the faction colour (otherwise it flies the owner's flag)
##   marker: it shares its model with another type, so it carries a pennant in its own colour
## Where the houses of a village stand on its tile, by level (one more at each).
const HOUSE_CLUSTER := [Vector3(0, 0, 0), Vector3(0.32, 0, 0.22), Vector3(-0.32, 0, 0.2), Vector3(0.24, 0, -0.32),
	Vector3(-0.26, 0, -0.3)]
## How each building is drawn: its model, and the goods (KayKit ResourceBits) piled beside
## it from a level on, so an upgrade shows: [model, size, offset] for each level and up.
const BUILDING_MODELS := {
	"house": {"model": "building_home_A_green", "alt": "building_home_B_green", "size": 0.78, "tinted": true},
	"farm": {"model": "building_grain", "size": 0.95,
		"goods": {2: [["sack", 0.16, Vector3(0.4, 0, 0.4)]], 3: [["Pallet_Wood_Covered_A", 0.22, Vector3(-0.38, 0, 0.4)]]}},
	"lumber_camp": {"model": "building_lumbermill_green", "size": 0.9, "tinted": true,
		"goods": {2: [["Wood_Log_Stack", 0.24, Vector3(0.4, 0, 0.38)]], 3: [["Wood_Planks_Stack_Large", 0.26, Vector3(-0.38, 0, 0.4)]]}},
	"mine": {"model": "building_mine_green", "size": 0.9, "tinted": true,
		"goods": {1: [["Stone_Chunks_Small", 0.18, Vector3(0.4, 0, 0.38)]], 2: [["Iron_Nuggets", 0.16, Vector3(-0.38, 0, 0.4)]],
			3: [["Iron_Bars_Stack_Small", 0.2, Vector3(0.42, 0, -0.36)]]}},
	"storehouse": {"model": "building_windmill_green", "size": 0.85, "tinted": true,
		"goods": {1: [["Pallet_Wood_Covered_A", 0.2, Vector3(0.4, 0, 0.38)]], 2: [["Textiles_Stack_Small", 0.18, Vector3(-0.38, 0, 0.4)]],
			3: [["Stone_Bricks_Stack_Small", 0.2, Vector3(0.42, 0, -0.36)], ["Textiles_Stack_Large_Colored", 0.22, Vector3(-0.4, 0, -0.36)]]}},
	"market": {"model": "building_market_green", "size": 0.9, "tinted": true,
		"props": [["crate_A_small", 0.12, Vector3(0.42, 0, 0.36)], ["sack", 0.12, Vector3(0.3, 0, 0.44)]],
		"goods": {2: [["Gold_Bars_Stack_Small", 0.16, Vector3(-0.38, 0, 0.4)]], 3: [["Gold_Bars_Stack_Large", 0.2, Vector3(0.42, 0, -0.36)]]}},
	"school": {"model": "building_church_green", "size": 0.85, "tinted": true,
		"goods": {2: [["Textiles_Stack_Small", 0.16, Vector3(0.4, 0, 0.4)]], 3: [["Textiles_Stack_Large_Colored", 0.2, Vector3(-0.4, 0, 0.4)]]}},
	"workshop": {"model": "building_blacksmith_green", "size": 0.9, "tinted": true,
		"goods": {1: [["Parts_Pile_Small", 0.16, Vector3(0.4, 0, 0.38)]], 2: [["Parts_Cog", 0.16, Vector3(-0.38, 0, 0.4)]],
			3: [["Parts_Pile_Medium", 0.22, Vector3(0.42, 0, -0.36)], ["Iron_Bars_Stack_Small", 0.18, Vector3(-0.4, 0, -0.36)]]}},
	# A quay with a warehouse and a ship alongside; it is turned so the quay is on the water.
	# Made in Blender (tools/blender/make_models.py): turned so its pier runs out over the water.
	"harbour": {"model": "civsim_harbour", "size": 0.95, "faces_water": true, "tinted": true},
	# Barracks keep their arms racked outside, and a butt to practise on; an academy's tent from level 2.
	"barracks": {"model": "building_barracks_green", "size": 0.88, "tinted": true,
		"props": [["weaponrack", 0.2, Vector3(0.4, 0, 0.3)], ["target", 0.2, Vector3(0.36, 0, -0.38)]],
		"goods": {2: [["tent", 0.28, Vector3(-0.36, 0, 0.36)]]}},
	# Its own model, from assets/characters.
	"stables": {"model": "civsim_stable", "size": 0.95, "tinted": true},  # made in Blender
}
# Capitals have their own models in assets/characters; the pack's castle and tower stand in
# if a file is missing.
## Castles are put together from the pack's pieces, and grow with their civ: a palisade and
## a keep at first, then stone walls and towers, then a church and a smithy inside, then a
## tavern and a market, towers along the walls, and catapults on the corners. A civ's own
## capital is a step ahead of its others; a capital the natives hold stays as it began.
const NATIVE_CASTLE := 1
const NATIVE_STRONGHOLD := 4
const KEEP := "building_castle_green"
## A building going up: the pack's three stages, from footings to roof, by how far it has got.
const SITE_STAGES := ["building_stage_A", "building_stage_B", "building_stage_C"]
const SITE_SIZE := 0.85
## Every pack model drawn other than through BUILDING_MODELS, for the asset check.
const EXTRA_MODELS := ["civsim_gold_mine", "civsim_ship", "civsim_fishing_boat", "civsim_oar", "civsim_catapult", "civsim_ram", "building_destroyed", "building_scaffolding", "flag_green", "wall_straight", "wall_straight_gate",
	"fence_wood_straight", "fence_wood_straight_gate", "building_tower_base_green", "building_tower_A_green",
	"building_tower_catapult_green", "building_church_green", "building_blacksmith_green", "building_well_green",
	"building_tavern_green", "building_market_green", "building_castle_green", "building_tower_A_green", "building_stage_A",
	"building_stage_B", "building_stage_C", "sack", "crate_A_small", "crate_B_small", "tent", "weaponrack", "target"]
## Castle pieces: [model, at level, size as a share of the castle's footprint, where (as a
## share of the footprint from the centre; the gate is at +z), faces (quarter turns), tinted].
const CASTLE_INSIDE := [
	["building_church_green", 3, 0.17, Vector2(-0.24, -0.26), 0, true],
	["building_blacksmith_green", 3, 0.17, Vector2(0.24, -0.26), 0, true],
	["building_well_green", 2, 0.08, Vector2(0.0, -0.33), 0, false],
	["building_tavern_green", 4, 0.16, Vector2(-0.3, 0.0), 1, true],
	["building_market_green", 4, 0.18, Vector2(0.3, 0.0), 3, true],
]
const YARD_STONE := Color(0.5, 0.48, 0.44)  # the paved yard inside stone walls
const YARD_EARTH := Color(0.55, 0.45, 0.32)  # ... and the packed earth inside a palisade
const WALL_SEGMENTS := {"main": 5, "town": 3}  # wall pieces along each side; the gate takes the middle one
# A castle stands on its capital's tile and the two rings around it (5 x 5 tiles), where the
# sim builds nothing.
const CASTLE_REACH := 2  # tiles each way from a capital that its castle stands on (economy/buildings.py)
const CAPITAL_FOOTPRINT := 4.4
const TOWN_FOOTPRINT := 3.6
## Every castle has its hospital: a tent in the courtyard, and one more for each hospital tech.
const HOSPITAL_TECHS := ["field_medicine", "surgeons", "military_hospitals"]
const TENT_SIZE := 0.3
## Where the tents stand in each castle's courtyard, in tiles from its centre (the gate is at +z).
const TENT_SPOTS := {
	"main": [Vector3(1.15, 0, 1.15), Vector3(1.5, 0, 1.15), Vector3(1.15, 0, 1.5), Vector3(1.5, 0, 1.5)],
	"town": [Vector3(0.75, 0, 0.8), Vector3(1.05, 0, 0.8), Vector3(0.75, 0, 1.1), Vector3(1.05, 0, 1.1)],
}
## Puts a castle together on `root` from the pack's pieces. Returns the height of its keep.
func _compose_castle(root: Node3D, color: Color, is_main: bool, level: int) -> float:
	var footprint := CAPITAL_FOOTPRINT if is_main else TOWN_FOOTPRINT
	var tinted: Material = _models.tinted_material(color)
	var plain: Material = _models.base_material()
	var half := footprint * 0.5 - 0.2  # where the walls run
	var segments: int = WALL_SEGMENTS["main" if is_main else "town"]
	var length := 2.0 * half / segments
	var stone := level >= 1
	# A yard inside the walls: packed earth behind a palisade, paving behind stone walls.
	var yard := MeshInstance3D.new()
	var yard_mesh := PlaneMesh.new()
	yard_mesh.size = Vector2(2.0 * half, 2.0 * half)
	yard_mesh.material = _flat_material(YARD_STONE if stone else YARD_EARTH)
	yard.mesh = yard_mesh
	yard.position.y = 0.025
	yard.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(yard)
	for side in 4:
		var turn := side * PI / 2.0  # side 0 faces the gate's way, +z
		for i in segments:
			var along := -half + length * (i + 0.5)
			var gate := side == 0 and i == segments / 2
			var piece: String
			if stone:
				piece = "wall_straight_gate" if gate else "wall_straight"
			else:
				piece = "fence_wood_straight_gate" if gate else "fence_wood_straight"
			var at := Basis(Vector3.UP, turn) * Vector3(along, 0, half)
			# The fences run along z in the pack, the walls along x.
			_castle_piece(root, piece, plain, length * (1.0 if stone else 1.02), at, turn + (0.0 if stone else PI / 2.0))
			if level >= 4 and side > 0 and i == segments / 2:
				_castle_piece(root, "building_tower_base_green", tinted, footprint * 0.11, at, turn)  # towers along the walls
	if stone:
		var corner := "building_tower_catapult_green" if level >= 5 else "building_tower_A_green"
		for corner_at: Vector3 in [Vector3(half, 0, half), Vector3(-half, 0, half), Vector3(half, 0, -half), Vector3(-half, 0, -half)]:
			_castle_piece(root, corner, tinted, footprint * 0.13, corner_at, 0.0)
	if level >= 2:  # towers either side of the gate
		for flank: float in [-length * 0.6, length * 0.6]:
			_castle_piece(root, "building_tower_base_green", tinted, footprint * 0.09, Vector3(flank, 0, half + 0.05), 0.0)
	var keep_size := footprint * (0.4 if is_main else 0.34)
	_castle_piece(root, KEEP, tinted, keep_size, Vector3(0, 0, -footprint * 0.04), 0.0)
	for inside: Array in CASTLE_INSIDE:
		if level >= int(inside[1]):
			var spot: Vector2 = inside[3]
			_castle_piece(root, inside[0], tinted if inside[5] else plain, footprint * float(inside[2]),
				Vector3(spot.x, 0, spot.y) * footprint, int(inside[4]) * PI / 2.0)
	return _models.height(KEEP, keep_size)


func _castle_piece(root: Node3D, model: String, material: Material, size: float, at: Vector3, turn: float) -> void:
	var piece: Node3D = _models.instance_centred(model, material, size)
	if piece != null:
		piece.position = at
		piece.rotation.y = turn
		root.add_child(piece)


## A gold mine: a fixed site on its vein, in the colours of whoever holds its region.
const GOLD_MINE := {"model": "civsim_gold_mine", "size": 1.0, "tinted": true}  # made in Blender
## A capital an enemy has broken into: rubble against its walls while the hold lasts.
const RUIN_SPOTS := [["building_destroyed", 1.0, Vector3(-1.1, 0, 1.4)], ["building_destroyed", 0.85, Vector3(1.3, 0, -1.2)],
	["building_scaffolding", 0.9, Vector3(1.25, 0, 1.35)]]

const WATER_SIDE := PI  # turn that brings the harbour model's pier round to face the water

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
var _civ_names := {}  # civ id -> name
var _mines: Array = []  # gold mines from the init message: x, y, region
var _rally_labels := {}  # rally id -> Label3D over the city it gathers in, or the city it marches on
var _sieges := {}  # region id -> Label3D over a capital an enemy army has broken into
var _detail := 0  # 0 whole-map view, 1 closer, 2 full detail
var _view_distance := 110.0  # how far the camera is, for what is sized to the screen
var _batches: Node3D  # batches.gd: every finished building of the pack's
var _batched := {}  # building key -> true, for the ones drawn there
var _marker_cache := {}
var _rich_nodes: Array = []  # {"material", "label", "node", "phase"} for each rich node, glowing
var _links_instance: MeshInstance3D  # the arcs between capitals
var _deposit_instance: MultiMeshInstance3D  # every deposit's cube
var _capitals: Array = []  # capital nodes, for fading the names of those far from the focus
var _focus := Vector3.ZERO  # the point the camera looks at
var _fade_wait := 0.0
var show_lines := true  # map layers the viewer can turn off (beside the minimap)
var show_resources := true
var _glow := 0.0
var _link_material: StandardMaterial3D


func setup(terrain: Node3D, init: Dictionary, civ_colors: Array, models: RefCounted, characters: RefCounted) -> void:
	_models = models
	_characters = characters
	for child in get_children():
		child.queue_free()
	_nodes.clear()
	_batched.clear()
	_marker_cache.clear()
	_rich_nodes.clear()
	_capitals.clear()
	_batches = Batches.new()
	add_child(_batches)
	_link_labels.clear()
	_sieges.clear()
	_rally_labels.clear()
	_body_meshes.clear()
	_plinth_meshes.clear()
	_terrain = terrain
	_building_defs = init["buildings"]
	_civ_colors = civ_colors
	_add_deposits(init["map"]["deposits"], init["deposit_types"], init["regions"])
	_regions.clear()
	_mines = init.get("mines", [])
	_civ_names.clear()
	for civ: Dictionary in init["civs"]:
		_civ_names[int(civ["id"])] = str(civ["name"])
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
	_links_instance = MeshInstance3D.new()
	_links_instance.mesh = _links
	_links_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_links_instance)


## `regions` is the tick's list of who holds each region (owner null = the native faction).
func update(civs: Array, regions: Array) -> void:
	var seen := {}
	_show_sieges(regions)
	_show_mines(regions, seen)
	# Capitals still held by the native faction.
	for region: Dictionary in regions:
		if region["owner"] != null:
			continue
		var info: Dictionary = _regions[int(region["id"])]
		var key := "n:%d" % int(region["id"])
		seen[key] = true
		if not _nodes.has(key):
			var stronghold: bool = info.get("stronghold", false)
			# A stronghold's walls stand as high as a great capital's.
			_nodes[key] = _make_capital(_native_color, str(info["capital"]), int(info["x"]), int(info["y"]), stronghold,
					NATIVE_STRONGHOLD if stronghold else NATIVE_CASTLE)
			# Only the castle's name from afar; its region's name too, close in. A shield over a stronghold.
			_nodes[key].set_meta("long", "%s\n%s" % [info["capital"], info["name"]])
			if stronghold:
				_add_shield(_nodes[key])
			_show_capital_label(_nodes[key])
			_terrain.set_clearing(key, _nodes[key].position, TOWN_FOOTPRINT * 0.5 + 0.15)
	for civ: Dictionary in civs:
		var civ_id := int(civ["id"])
		var index := 0
		for settlement: Dictionary in civ["settlements"]:
			# The first capital in the list is the civ's own; it is marked with a star and a taller flag.
			var is_main := index == 0
			index += 1
			# A castle grows with its civ: rebuilt when the civ enters a new era.
			var level := castle_level(int(civ.get("era", 0)), is_main)
			var key := "%d:%d:%d:%s:%d" % [civ_id, int(settlement["x"]), int(settlement["y"]), is_main, level]
			seen[key] = true
			if not _nodes.has(key):
				var caption := ("★ " if is_main else "") + str(settlement["name"])
				_nodes[key] = _make_capital(_civ_colors[civ_id], caption, int(settlement["x"]), int(settlement["y"]), is_main, level)
				# A castle is wider than its tile: fell the trees it would stand in.
				_terrain.set_clearing(key, _nodes[key].position, (CAPITAL_FOOTPRINT if is_main else TOWN_FOOTPRINT) * 0.5 + 0.15)
			_show_hospital(_nodes[key], civ.get("techs", []), _civ_colors[civ_id], is_main)
		var capital_tiles := {}  # "x:y" -> footprint of the capital standing there
		index = 0
		for settlement: Dictionary in civ["settlements"]:
			capital_tiles["%d:%d" % [int(settlement["x"]), int(settlement["y"])]] = CAPITAL_FOOTPRINT if index == 0 else TOWN_FOOTPRINT
			index += 1
		for building: Dictionary in civ["buildings"]:
			# Its level is in the key: an upgraded building is drawn again, bigger.
			var key := "b:%d:%d:%d" % [civ_id, int(building["id"]), int(building.get("level", 1))]
			seen[key] = true
			# A finished building of the pack's is drawn in the batches, not as a node of its own.
			if building["complete"] and _batchable(str(building["type"])):
				if not _batches.has(key):
					if _nodes.has(key):  # it was a building site until now
						_nodes[key].queue_free()
						_nodes.erase(key)
					_batch_building(key, civ_id, building)
				continue
			# A site shows the stage it has reached; it is rebuilt as each stage begins.
			var stage := -1 if building["complete"] else mini(SITE_STAGES.size() - 1, int(float(building["progress"]) * SITE_STAGES.size()))
			if _nodes.has(key) and int(_nodes[key].get_meta("stage", -1)) != stage:
				_nodes[key].queue_free()
				_nodes.erase(key)
			if not _nodes.has(key):
				_nodes[key] = _make_building(civ_id, building) if stage < 0 else _make_site(civ_id, building, stage)
				# Fell the trees on the ground it stands on.
				_terrain.set_clearing(key, _nodes[key].position, float(_nodes[key].get_meta("clearing")))
		for village: Dictionary in civ["villages"]:
			if village["capital"]:
				continue  # the capital is already labelled
			var key := "v:%d:%d" % [civ_id, int(village["id"])]
			seen[key] = true
			if not _nodes.has(key):
				_nodes[key] = _make_village(civ_id, village)
	for key: String in _nodes.keys():
		if not seen.has(key):
			if not _batches.has(key):
				_terrain.remove_clearing(key)
			_nodes[key].queue_free()
			_nodes.erase(key)
	for key: String in _batched.keys():
		if not seen.has(key):
			_terrain.remove_clearing(key)
			_batches.remove(key)
			_batched.erase(key)
	_batches.flush()


## What the map labels at each zoom. From afar only each civ's own capital is named,
## larger so it can be read; other capitals and alliance names appear closer in.
## War names always show: they are the news.
func set_view_distance(distance: float) -> void:
	_view_distance = distance


func set_detail(detail: int) -> void:
	_detail = detail
	_show_layers()
	for node: Node3D in _nodes.values():
		_show_capital_label(node)
		_show_settled(node)


## War and alliance arcs from mid zoom out; deposit cubes close in, rich nodes from mid zoom.
func _show_layers() -> void:
	if _links_instance != null:
		_links_instance.visible = show_lines and _detail <= 1
	for label: Label3D in _link_labels.values():
		_show_link_label(label)
	if _deposit_instance != null:
		_deposit_instance.visible = show_resources and _detail >= 2
	for rich: Dictionary in _rich_nodes:
		(rich["label"] as Label3D).visible = show_resources and _detail >= 1
		(rich["node"] as Node3D).visible = show_resources and _detail >= 1


func set_layer(layer: String, on: bool) -> void:
	match layer:
		"lines":
			show_lines = on
		"resources":
			show_resources = on
	_show_layers()


func add_civ(civ: Dictionary) -> void:
	_civ_names[int(civ["id"])] = str(civ["name"])


## A rally is marked where it gathers, with the days left, and then on the city it marches on.
func show_rallies(rallies: Array) -> void:
	var seen := {}
	for rally: Dictionary in rallies:
		var id := int(rally["id"])
		seen[id] = true
		if not _rally_labels.has(id):
			var label := Label3D.new()
			label.font_size = 40
			label.outline_size = 14
			label.fixed_size = true
			label.pixel_size = 0.00065
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.no_depth_test = true
			add_child(label)
			_rally_labels[id] = label
		var mark: Label3D = _rally_labels[id]
		var gathering: bool = rally["state"] == "gathering"
		var at: Dictionary = rally["city"] if gathering else rally["target"]
		mark.position = _terrain.tile_position(int(at["x"]), int(at["y"])) + Vector3(0.0, 7.6, 0.0)
		var leader := int(rally["leader"])
		mark.text = ("%s rallies here\n%d soldiers, marching in %d days" % [_civ_names.get(leader, "?"), int(rally["soldiers"]), int(rally["days_left"])]
				if gathering else "%s's rally is coming\n%d soldiers" % [_civ_names.get(leader, "?"), int(rally["soldiers"])])
		mark.modulate = (_civ_colors[leader] as Color).lightened(0.4)
	for id: int in _rally_labels.keys():
		if not seen.has(id):
			_rally_labels[id].queue_free()
			_rally_labels.erase(id)


## A capital an enemy army has broken into shows who holds it and how close it is to falling.
func _show_sieges(regions: Array) -> void:
	var held := {}
	for region: Dictionary in regions:
		if region.get("held_by") == null:
			continue
		var id := int(region["id"])
		var by := int(region["held_by"])
		held[id] = true
		if not _sieges.has(id):
			var info: Dictionary = _regions[id]
			var label := Label3D.new()
			label.font_size = 40
			label.outline_size = 14
			label.fixed_size = true
			label.pixel_size = 0.00065
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.no_depth_test = true
			label.position = _terrain.tile_position(int(info["x"]), int(info["y"])) + Vector3(0.0, 6.2, 0.0)
			add_child(label)
			# Rubble against the walls while the enemy is inside.
			for ruin: Array in RUIN_SPOTS:
				var piece: Node3D = _models.instance(ruin[0], _models.base_material(), float(ruin[1]))
				if piece != null:
					piece.position = Vector3(ruin[2]) - Vector3(0, 6.2, 0)
					piece.rotation.y = (id * 7 % 4) * PI / 2
					label.add_child(piece)
			_sieges[id] = label
		var siege: Label3D = _sieges[id]
		var done := clampf(float(region.get("hold", 0.0)), 0.0, 1.0)
		siege.text = "Held by %s\n%d%% taken" % [_civ_names.get(by, "?"), int(done * 100.0)]
		siege.modulate = (_civ_colors[by] as Color).lightened(0.35)
	for id: int in _sieges.keys():
		if not held.has(id):
			_sieges[id].queue_free()
			_sieges.erase(id)


## Gold mines, each in the colours of its region's holder; redrawn when the region changes hands.
func _show_mines(regions: Array, seen: Dictionary) -> void:
	var owners := {}
	for region: Dictionary in regions:
		owners[int(region["id"])] = region["owner"]
	for mine: Dictionary in _mines:
		var owner: Variant = owners.get(int(mine["region"]))
		var key := "m:%d:%d:%s" % [int(mine["x"]), int(mine["y"]), str(owner)]
		seen[key] = true
		if _nodes.has(key):
			continue
		var color: Color = _native_color if owner == null else _civ_colors[int(owner)]
		var root := Node3D.new()
		var spot: Vector3 = _terrain.tile_position(int(mine["x"]), int(mine["y"]))
		spot.y = _terrain.height_at(spot.x, spot.z)
		root.position = spot
		root.set_meta("kind", "mine")
		var model: Node3D = _models.instance(GOLD_MINE["model"], _models.tinted_material(color), float(GOLD_MINE["size"]))
		if model != null:
			model.rotation.y = (int(mine["x"]) * 7 + int(mine["y"]) * 13) % 4 * PI / 2
			root.add_child(model)
			_add_props(root, GOLD_MINE, color, 1, model.rotation.y)
		add_child(root)
		_nodes[key] = root
		_terrain.set_clearing(key, spot, 0.55)


## The castle's hospital: a tent in the courtyard, and one more for each hospital tech known.
func _show_hospital(castle: Node3D, techs: Array, color: Color, is_main: bool) -> void:
	var level := 1
	for tech: String in HOSPITAL_TECHS:
		if tech in techs:
			level += 1
	if int(castle.get_meta("tents", 0)) == level:
		return
	castle.set_meta("tents", level)
	var old: Node = castle.get_node_or_null("hospital")
	if old != null:
		old.queue_free()
	var hospital := Node3D.new()
	hospital.name = "hospital"
	var spots: Array = TENT_SPOTS["main" if is_main else "town"]
	for i in mini(level, spots.size()):
		var tent: Node3D = _models.instance("tent", _models.tinted_material(color), TENT_SIZE)
		if tent != null:
			tent.position = spots[i]
			hospital.add_child(tent)
	castle.add_child(hospital)


func _show_capital_label(node: Node3D) -> void:
	if not node.has_meta("label"):
		return
	var label: Label3D = node.get_meta("label")
	var is_main: bool = node.get_meta("main")
	label.visible = is_main or _detail >= 1
	label.text = node.get_meta("long") if _detail >= 2 and node.has_meta("long") else node.get_meta("short")
	if node.has_meta("shield"):
		var shield: Sprite3D = node.get_meta("shield")
		shield.visible = label.visible
		shield.offset.y = 52.0 if _detail >= 2 else 37.0  # over one line of name, or two


## A native stronghold: a small shield over its name instead of the word.
func _add_shield(node: Node3D) -> void:
	var label: Label3D = node.get_meta("label")
	var shield := Sprite3D.new()
	shield.texture = load("res://assets/icons/shield.svg")
	shield.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	shield.fixed_size = true
	shield.no_depth_test = true
	shield.pixel_size = label.pixel_size * 1.5
	shield.position = label.position
	shield.offset = Vector2(0, 37)  # just above the name, the same on screen at every zoom
	shield.render_priority = 1
	node.add_child(shield)
	node.set_meta("shield", shield)


## What the camera looks at: names of castles far from it fade, so the nearest read best.
func set_focus(point: Vector3) -> void:
	_focus = point


func _fade_names() -> void:
	var reach := maxf(_view_distance, 20.0)
	var kept: Array = []
	for entry: Variant in _capitals:  # untyped: some may have been freed since
		if not is_instance_valid(entry) or (entry as Node3D).is_queued_for_deletion():
			continue
		var node: Node3D = entry
		kept.append(node)
		var label: Label3D = node.get_meta("label")
		var away := Vector2(node.position.x - _focus.x, node.position.z - _focus.z).length()
		var alpha := 1.0 - clampf((away - 0.45 * reach) / (0.5 * reach), 0.0, 0.7)
		if node.get_meta("main"):
			alpha = maxf(alpha, 0.85)  # a civ's own capital stays readable
		label.modulate.a = alpha
		label.outline_modulate.a = alpha
		if node.has_meta("shield"):
			(node.get_meta("shield") as Sprite3D).modulate.a = alpha
	_capitals = kept


## Buildings are always drawn one by one; a village's name appears closer in.
func _show_settled(node: Node3D) -> void:
	match node.get_meta("kind", ""):
		"building":
			node.visible = true  # everything is drawn to one scale at every zoom
		"village":
			if node.has_meta("name_label"):
				var name_label: Label3D = node.get_meta("name_label")
				name_label.visible = _detail >= 1


func _show_link_label(label: Label3D) -> void:
	var is_war: bool = label.get_meta("war", false)
	label.visible = show_lines and _detail <= 1 and (is_war or _detail >= 1)


## Redraws the arcs between civ capitals. Every pair of living civs has one, coloured
## by what holds between them: red for war, blue for alliance, green for a trade
## deal, thin grey for nothing in particular. Wars and alliances carry their name.
func update_links(civs: Array, relations: Array, deals: Array) -> void:
	# The arcs are as wide on screen from close up as from across the map.
	var width := LINK_WIDTH * clampf(_view_distance / 110.0, 0.08, 1.6)
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
			named[key] = _add_link(capitals[a], capitals[b], LINK_COLORS["war"], 1.0, width * 1.5)
		elif status == "alliance":
			named[key] = _add_link(capitals[a], capitals[b], LINK_COLORS["alliance"], 1.0, width)
		if trading.has(key):
			_add_link(capitals[a], capitals[b], LINK_COLORS["deal"], 0.6, width)
		elif status == "peace":
			_add_link(capitals[a], capitals[b], LINK_COLORS["neutral"], 0.35, width * 0.45)
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
		label.fixed_size = true  # the same size on screen at every zoom
		label.pixel_size = 0.0005
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


## A building stands on a square of tiles, `size` a side (from the sim's building types), and
## is drawn to fill it: the middle of an odd-sized square is the building's own tile, and of
## an even-sized one half a tile further along both axes.
func _make_building(civ_id: int, building: Dictionary) -> Node3D:
	var type: String = building["type"]
	var x := int(building["x"])
	var y := int(building["y"])
	var tiles := int(_building_defs.get(type, {}).get("size", 1))
	var root := Node3D.new()
	var off := 0.5 if tiles % 2 == 0 else 0.0
	var spot: Vector3 = _terrain.tile_position(x, y) + Vector3(off, 0, off)
	spot.y = _terrain.height_at(spot.x, spot.z)
	root.position = spot
	root.set_meta("kind", "building")
	root.set_meta("clearing", tiles * 0.5 + 0.05)
	var color: Color = _civ_colors[civ_id]
	var spec: Dictionary = BUILDING_MODELS.get(type, {})
	var model: Node3D = null
	if spec.has("scene"):
		model = _characters.instance(spec["scene"], color, 0.0, float(spec["size"]) * tiles)
		if model != null:
			model.rotation.y = (x * 7 + y * 13) % 4 * PI / 2
			if spec.get("faces_water", false):
				model.rotation.y = _toward_water(spot, tiles * 0.5 + 0.5) + WATER_SIDE
			root.add_child(model)
			add_child(root)
			return root
		spec = spec.duplicate()
		spec["size"] = 0.9  # the model file is missing: fall back to the pack's building
	if not spec.is_empty() and spec.has("model") and model == null:
		var name: String = spec["model"]
		if spec.has("alt") and (x + y) % 2 == 1:
			name = spec["alt"]  # two looks for the commonest building, so a town is not all one house
		var material: Material = _models.tinted_material(color) if spec.get("tinted", false) else _models.base_material()
		model = _models.instance(name, material, float(spec["size"]) * tiles)
	if model == null:
		_add_block(root, civ_id, type)
	else:
		# Face one of four ways, the same way every time for a given tile.
		model.rotation.y = (x * 7 + y * 13) % 4 * PI / 2
		if spec.get("faces_water", false):
			model.rotation.y = _toward_water(spot, tiles * 0.5 + 0.5) + WATER_SIDE
		model.position.y = float(spec.get("lift", 0.0)) * tiles
		root.add_child(model)
		var top: float = (_models.height(spec["model"], float(spec["size"])) + float(spec.get("lift", 0.0))) * tiles
		if not spec.get("tinted", false):
			_add_flag(root, color)
		if spec.get("marker", false):
			_add_marker(root, Color.html(_building_defs[type]["color"]), top)
		_add_props(root, spec, color, tiles, model.rotation.y)
	add_child(root)
	return root


## A building site: the pack's construction stage, sized to the ground the building will
## take, with the owner's flag. Without the stage models it is the building itself, growing.
func _make_site(civ_id: int, building: Dictionary, stage: int) -> Node3D:
	var tiles := int(_building_defs.get(building["type"], {}).get("size", 1))
	var model: Node3D = _models.instance(SITE_STAGES[stage], _models.base_material(), SITE_SIZE * tiles)
	if model == null:
		var grown := _make_building(civ_id, building)
		grown.scale = Vector3(1.0, lerpf(0.15, 1.0, float(building["progress"])), 1.0)
		grown.set_meta("stage", stage)
		return grown
	var root := Node3D.new()
	var placed := _building_spot(building)
	root.position = placed.origin
	model.basis = placed.basis
	root.add_child(model)
	root.set_meta("kind", "building")
	root.set_meta("clearing", tiles * 0.5 + 0.05)
	root.set_meta("stage", stage)
	_add_flag(root, _civ_colors[civ_id])
	add_child(root)
	return root


## The small things set out beside a building (crates, a tent, a weapon rack), for a
## building drawn as a node of its own.
func _add_props(root: Node3D, spec: Dictionary, color: Color, tiles: int, turn: float) -> void:
	for prop: Array in spec.get("props", []):
		var model: Node3D = _models.instance(prop[0], _models.tinted_material(color), float(prop[1]) * tiles)
		if model != null:
			model.position = Basis(Vector3.UP, turn) * (prop[2] as Vector3) * tiles
			model.rotation.y = turn
			root.add_child(model)


## A village is its buildings; all that is added is its name, for closer in.
func _make_village(civ_id: int, village: Dictionary) -> Node3D:
	var root := Node3D.new()
	root.position = _terrain.tile_position(int(village["x"]), int(village["y"]))
	root.set_meta("kind", "village")
	var name_label := Label3D.new()
	name_label.text = str(village["name"])
	name_label.font_size = 40
	name_label.outline_size = 12
	name_label.fixed_size = true
	name_label.pixel_size = 0.00038
	name_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	name_label.no_depth_test = true
	name_label.modulate = (_civ_colors[civ_id] as Color).lightened(0.6)
	name_label.position.y = 1.5
	root.add_child(name_label)
	root.set_meta("name_label", name_label)
	_show_settled(root)
	add_child(root)
	return root


## True for a building type drawn with one of the pack's models, which can go in the batches.
func _batchable(type: String) -> bool:
	var spec: Dictionary = BUILDING_MODELS.get(type, {})
	# A harbour is turned to its water when placed, which the batches do not do.
	return spec.has("model") and not spec.has("scene") and not spec.get("faces_water", false) \
		and not _models.parts(spec["model"], 1.0).is_empty()


## Where a building stands and which way it faces: the same for a site and the finished thing.
func _building_spot(building: Dictionary) -> Transform3D:
	var x := int(building["x"])
	var y := int(building["y"])
	var tiles := int(_building_defs.get(building["type"], {}).get("size", 1))
	var off := 0.5 if tiles % 2 == 0 else 0.0
	var spot: Vector3 = _terrain.tile_position(x, y) + Vector3(off, 0, off)
	spot.y = _terrain.height_at(spot.x, spot.z)
	return Transform3D(Basis(Vector3.UP, (x * 7 + y * 13) % 4 * PI / 2), spot)


## Hand a finished building's parts to the batches: its model, and the flag or pennant with it.
func _batch_building(key: String, civ_id: int, building: Dictionary) -> void:
	var type: String = building["type"]
	var spec: Dictionary = BUILDING_MODELS[type]
	var tiles := int(_building_defs.get(type, {}).get("size", 1))
	var color: Color = _civ_colors[civ_id]
	var x := int(building["x"])
	var y := int(building["y"])
	var placed := _building_spot(building)
	var upright := Transform3D(Basis(), placed.origin)  # flags and pennants do not turn with the model
	var name: String = spec["model"]
	if spec.has("alt") and (x + y) % 2 == 1:
		name = spec["alt"]
	var material: Material = _models.tinted_material(color) if spec.get("tinted", false) else _models.base_material()
	var lift := Transform3D(Basis(), Vector3(0, float(spec.get("lift", 0.0)) * tiles, 0))
	# A village (a house) grows by its level into a cluster of houses; anything else grows larger.
	var level := int(building.get("level", 1))
	var copies: Array = [Vector3.ZERO]
	var grow := 1.0
	if type == "house" and level > 1:
		copies = HOUSE_CLUSTER.slice(0, level)
		grow = 0.7
	elif level > 1:
		grow = 1.0 + 0.15 * (level - 1)
	for offset: Vector3 in copies:
		var at := Transform3D(Basis(Vector3.UP, offset.length() * 2.0), offset)  # each house turned its own way
		for part: Array in _models.parts(name, float(spec["size"]) * tiles * grow):
			_batches.add(key, part[0], material, placed * at * lift * (part[1] as Transform3D))
	for prop: Array in spec.get("props", []):
		var beside := Transform3D(Basis(), (prop[2] as Vector3) * tiles)
		for part: Array in _models.parts(prop[0], float(prop[1]) * tiles):
			_batches.add(key, part[0], _models.tinted_material(color), placed * beside * (part[1] as Transform3D))
	# Goods piled beside it from a level on: an upgraded building shows it. The Hexagon pack's
	# own props (a sack, a tent) take its tinted material; the ResourceBits models their own.
	var goods: Dictionary = spec.get("goods", {})
	for from_level: int in goods:
		if level < from_level:
			continue
		for good: Array in goods[from_level]:
			var model := str(good[0])
			var stuff: Material = _models.goods_material() if model[0] == model[0].to_upper() else _models.tinted_material(color)
			var beside := Transform3D(Basis(), (good[2] as Vector3) * tiles)
			for part: Array in _models.parts(model, float(good[1]) * tiles):
				_batches.add(key, part[0], stuff, placed * beside * (part[1] as Transform3D))
	if not spec.get("tinted", false):
		var at := Transform3D(Basis(), Vector3(0.36, 0.0, 0.36) * tiles)
		for part: Array in _models.parts("flag_green", 0.42):
			_batches.add(key, part[0], _models.tinted_material(color), upright * at * (part[1] as Transform3D))
	if spec.get("marker", false):
		var top: float = (_models.height(name, float(spec["size"])) + float(spec.get("lift", 0.0))) * tiles
		var marker: Array = _marker_meshes(Color.html(_building_defs[type]["color"]))
		_batches.add(key, marker[0], marker[0].material, upright * Transform3D(Basis(), Vector3(-0.3, top + 0.05, -0.3)))
		_batches.add(key, marker[1], marker[1].material, upright * Transform3D(Basis(), Vector3(-0.17, top + 0.21, -0.3)))
	_batched[key] = true
	_terrain.set_clearing(key, placed.origin, tiles * 0.5 + 0.05)


## The pole and pennant meshes for a marker in `color`, shared by every marker of that colour.
func _marker_meshes(color: Color) -> Array:
	var key := color.to_html(false)
	if not _marker_cache.has(key):
		var pole := CylinderMesh.new()
		pole.top_radius = 0.02
		pole.bottom_radius = 0.02
		pole.height = 0.5
		pole.material = _flat_material(Color(0.25, 0.2, 0.15))
		var pennant := BoxMesh.new()
		pennant.size = Vector3(0.26, 0.17, 0.03)
		pennant.material = _flat_material(color)
		_marker_cache[key] = [pole, pennant]
	return _marker_cache[key]


## The direction (as a rotation about the vertical) from a spot to the lowest ground `reach`
## tiles from it, which for a building on the shore is the water.
func _toward_water(spot: Vector3, reach: float) -> float:
	var best := Vector2.RIGHT
	var lowest := INF
	for step: Vector2 in [Vector2(1, 0), Vector2(-1, 0), Vector2(0, 1), Vector2(0, -1)]:
		var there: Vector3 = spot + Vector3(step.x, 0, step.y) * reach
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


## How far a castle has grown, 0 to 6, from its civ's era: a civ's own capital is a step ahead.
static func castle_level(era: int, is_main: bool) -> int:
	return clampi(era + (1 if is_main else 0), 0, 6)


## A region capital: a castle built from the pack's pieces, in its holder's colour (the native
## faction's, for a capital no civ holds), with the name above.
func _make_capital(color: Color, caption: String, x: int, y: int, is_main: bool, level: int) -> Node3D:
	var root := Node3D.new()
	root.position = _terrain.tile_position(x, y)
	var top := _compose_castle(root, color, is_main, level)
	var model: Node3D = root if root.get_child_count() > 0 else null
	if model == null:  # no model at all: the old keep
		var keep := MeshInstance3D.new()
		var keep_mesh := BoxMesh.new()
		keep_mesh.size = Vector3(0.9, 1.3, 0.9)
		keep_mesh.material = _flat_material(color.lightened(0.35))
		keep.mesh = keep_mesh
		keep.position.y = 0.65
		root.add_child(keep)

	var label := Label3D.new()
	label.text = caption
	label.font_size = 52 if is_main else 34
	label.outline_size = 14
	label.fixed_size = true
	label.pixel_size = 0.00065
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = color.lightened(0.5)
	label.position.y = top + 1.3
	root.add_child(label)
	root.set_meta("label", label)
	root.set_meta("main", is_main)
	root.set_meta("short", caption)
	_show_capital_label(root)
	_capitals.append(root)

	add_child(root)
	return root


## A marker on each deposit, except under a castle's walls (the capital's tile and those
## within CASTLE_REACH of it), where nothing is ever worked.
func _add_deposits(all_deposits: Array, deposit_types: Dictionary, regions: Array) -> void:
	var deposits: Array = []
	for deposit: Dictionary in all_deposits:
		var walled := false
		for region: Dictionary in regions:
			if absi(int(deposit["x"]) - int(region["x"])) <= CASTLE_REACH and absi(int(deposit["y"]) - int(region["y"])) <= CASTLE_REACH:
				walled = true
				break
		if not walled:
			deposits.append(deposit)
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

	_deposit_instance = MultiMeshInstance3D.new()
	_deposit_instance.multimesh = multimesh
	add_child(_deposit_instance)
	for deposit: Dictionary in deposits:
		if deposit.get("rich"):
			_add_rich_node(deposit, Color.html(deposit_types[deposit["type"]]["color"]), deposit_types[deposit["type"]])


## Rich nodes glow, slowly and each on its own beat.
func _process(delta: float) -> void:
	_glow += delta
	_fade_wait -= delta
	if _fade_wait <= 0.0:
		_fade_wait = 0.1
		_fade_names()
	for rich: Dictionary in _rich_nodes:
		(rich["material"] as StandardMaterial3D).emission_energy_multiplier = 0.25 + 0.35 * (0.5 + 0.5 * sin(_glow * 1.6 + rich["phase"]))


## A rich node (a deposit yielding three times as much): a bigger marker in its colour that
## glows slowly, with its name over it from mid zoom.
func _add_rich_node(deposit: Dictionary, color: Color, dtype: Dictionary) -> void:
	var origin: Vector3 = _terrain.tile_position(int(deposit["x"]), int(deposit["y"]))
	var material := _flat_material(color)
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = 0.4
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.46, 0.46, 0.46)
	mesh.material = material
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.transform = Transform3D(Basis.from_euler(Vector3(PI / 4, PI / 4, 0)), origin + Vector3(0, 0.42, 0))
	add_child(node)
	var label := Label3D.new()
	label.text = "%s\n%s x3" % [str(deposit["rich"]), str(dtype.get("name", deposit["type"]))]
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.font_size = 40
	label.outline_size = 10
	label.pixel_size = 0.004
	label.modulate = color.lightened(0.35)
	label.position = origin + Vector3(0, 1.0, 0)
	label.no_depth_test = true
	add_child(label)
	_rich_nodes.append({"material": material, "label": label, "node": node, "phase": float(deposit["x"] * 7 + deposit["y"])})
	_show_layers()


func _flat_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	return material
