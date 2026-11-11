extends Node3D
## Armies and villagers on the map.
##
## An army with a commander is shown as the commander, an animated model in the
## civ's colour that stands, walks or strikes according to what the army is doing,
## with the count of each unit type written above. An army without one is shown as
## a single figure of its dominant unit type: a mounted knight for cavalry and an archer
## for archers, animated and in the civ's colour, and a plain figure (spear, sword and
## shield) for the rest. An army that has put out from a harbour is shown as a ship until it
## lands. Villagers are animated too: walking, hammering at a building, working the
## land or drawing water; one with a horse from the stables is shown riding.
##
## How much is drawn follows the zoom. From afar a field army is a single marker
## in its civ's colour with its size, garrisons and villagers are left out, and
## nothing is captioned; the figures and the full captions appear closer in.

# Everything is drawn to fit the tile grid: figures stand well under a tile tall, beside
# buildings that fill one tile.
const FIGURE_SCALE := 0.65
const COMMANDER_HEIGHT := 0.8  # in tiles
const VILLAGER_HEIGHT := 0.45
const RIDER_HEIGHT := 0.62
const KNIGHT_HEIGHT := 0.72
const ARCHER_HEIGHT := 0.6
const SOLDIER_HEIGHT := 0.58  # a man-at-arms: the commander's model, smaller
## Unit types with a model of their own for an army without a commander: [model, height].
const SOLDIER_MODELS := {"cavalry": ["Knight", KNIGHT_HEIGHT], "archer": ["Archer", ARCHER_HEIGHT],
	"swordsman": ["Commander", SOLDIER_HEIGHT], "spearman": ["Commander", SOLDIER_HEIGHT]}
const SOLDIERS_PER_FIGURE := 12  # an army shows one more figure in its ranks for every so many soldiers
const MAX_RANKS := 8  # ... up to this many behind whoever leads it
const RANK_SPACING := 0.34
const STRIKES := ["attack", "shoot"]  # what a model's fighting animation may be called
const BOAT_LENGTH := 0.95
const GARRISON_SPOT := Vector3(0.5, 0, 1.3)  # before the castle gate, not inside the walls
const AT_ARMS := ["fighting", "besieging"]  # army states shown as striking
const MOVE_SPEED := 6.0  # how fast figures glide toward their tile, in tiles per second
const SKIN := Color(0.87, 0.72, 0.58)
const STEEL := Color(0.78, 0.8, 0.84)
const WOOD := Color(0.45, 0.3, 0.16)

var _terrain: Node3D
var _civ_colors: Array = []
var _unit_names := {}
var _armies := {}  # army id -> {"node", "label", "look", "target"}
var _villagers := {}  # villager id -> {"node", "look", "target"}
var _materials := {}
var _detail := 0  # 0 whole-map view, 1 closer, 2 full detail
var _swell := 0.0
var _characters: RefCounted  # characters.gd


func setup(terrain: Node3D, init: Dictionary, civ_colors: Array, characters: RefCounted) -> void:
	_characters = characters
	for child in get_children():
		child.queue_free()
	_armies.clear()
	_villagers.clear()
	_terrain = terrain
	_civ_colors = civ_colors
	_unit_names.clear()
	for unit_id: String in init["unit_types"]:
		_unit_names[unit_id] = init["unit_types"][unit_id]["name"]


func update(armies: Array, villagers: Array) -> void:
	var seen := {}
	for army: Dictionary in armies:
		var id := int(army["id"])
		seen[id] = true
		var civ := int(army["civ"])
		var commander: Variant = army["commander"]
		# What the piece looks like; rebuilt only when that changes.
		var look := "%d:%s:%s" % [civ, "commander" if commander != null else str(army["dominant"]), _ranks(army)]
		if not _armies.has(id) or _armies[id]["look"] != look:
			if _armies.has(id):
				_armies[id]["node"].queue_free()
			_armies[id] = _make_army(civ, army, look)
		var entry: Dictionary = _armies[id]
		entry["field"] = army["role"] == "field"
		entry["state"] = str(army["state"])
		entry["afloat"] = bool(army.get("boat", false))
		if entry["afloat"] and not entry.has("boat"):
			var boat: Node3D = _characters.instance("Boat", _civ_colors[civ], 0.0, BOAT_LENGTH)
			if boat != null:
				entry["node"].add_child(boat)
				entry["boat"] = boat
		entry["size"] = int(army["size"])
		entry["caption"] = _army_caption(army)
		_show_army(entry)
		_aim(entry, _spot(int(army["x"]), int(army["y"]), GARRISON_SPOT if army["role"] == "garrison" else Vector3.ZERO))
	_drop_missing(_armies, seen)

	seen = {}
	var crowd := {}  # tile -> villagers already placed there, to fan them out
	for villager: Dictionary in villagers:
		var id := int(villager["id"])
		seen[id] = true
		# Only what changes the model itself; what the villager is doing is shown by its animation.
		var plain: bool = not _characters.has("Villager")
		var look := "%d:%s:%s" % [int(villager["civ"]), villager["mounted"], villager["task"] if plain else ""]
		if not _villagers.has(id) or _villagers[id]["look"] != look:
			var at: Variant = null
			if _villagers.has(id):
				at = _villagers[id]["node"].position
				_villagers[id]["node"].queue_free()
			_villagers[id] = _make_villager(int(villager["civ"]), villager["task"], look, bool(villager["mounted"]))
			if at != null:  # same villager, new task: carry on from where it stands
				_villagers[id]["node"].position = at
				_villagers[id]["placed"] = true
		var key := "%d,%d" % [int(villager["x"]), int(villager["y"])]
		var n: int = crowd.get(key, 0)
		crowd[key] = n + 1
		var fan := Vector3(-0.3 + 0.3 * (n % 3), 0, 0.3 - 0.3 * (n / 3 % 3))
		_aim(_villagers[id], _spot(int(villager["x"]), int(villager["y"]), fan))
		_villagers[id]["afloat"] = bool(villager.get("afloat", false))  # aboard ship: not drawn
		_villagers[id]["node"].visible = not _villagers[id]["afloat"]
		# What it does once it has stopped walking.
		var doing := "idle"
		if villager["at_work"] and villager["task"] == "build":
			doing = "hammer"
		elif villager["at_work"] and villager["task"] == "gather":
			doing = "water" if villager["gathers"] == "water" else "pick"
		_villagers[id]["doing"] = doing
		_villagers[id]["mounted"] = bool(villager["mounted"])
	_drop_missing(_villagers, seen)


func set_detail(detail: int) -> void:
	_detail = detail
	for entry: Dictionary in _armies.values():
		_show_army(entry)
	for entry: Dictionary in _villagers.values():
		entry["node"].visible = not entry.get("afloat", false)


## Far: field armies are a marker and a number, garrisons are hidden. Closer: the
## figure, with its size. Closest: the figure with the full caption.
func _show_army(entry: Dictionary) -> void:
	var is_field: bool = entry.get("field", true)
	var figure: Node3D = entry["figure"]
	var marker: Node3D = entry["marker"]
	var label: Label3D = entry["label"]
	entry["node"].visible = is_field or _detail >= 1
	var afloat: bool = entry.get("afloat", false) and entry.has("boat")
	figure.visible = _detail >= 1 and not afloat
	for one: Node3D in entry["figures"]:
		_characters.set_active(one, figure.visible)
	(entry["dust"] as CPUParticles3D).emitting = figure.visible and entry.get("state", "") in AT_ARMS
	if entry.has("boat"):
		entry["boat"].visible = _detail >= 1 and afloat
	marker.visible = _detail == 0 and is_field
	if _detail == 0:
		label.visible = is_field
		label.text = str(entry.get("size", 0))
		label.pixel_size = 0.0007
		label.position.y = 7.4
	elif _detail == 1:
		label.visible = is_field
		label.text = str(entry.get("size", 0))
		label.pixel_size = 0.0005
		label.position.y = 1.3
	else:
		# Up close: exactly what is in the army, and who leads it.
		label.visible = entry.get("caption", "") != ""
		label.text = entry.get("caption", "")
		label.pixel_size = 0.00034
		label.position.y = 1.3


func _process(delta: float) -> void:
	for group: Dictionary in [_armies, _villagers]:
		for entry: Dictionary in group.values():
			var node: Node3D = entry["node"]
			var target: Vector3 = entry["target"]
			var offset := target - node.position
			var moving := offset.length() > 0.05
			if offset.length() > 0.01:
				if Vector2(offset.x, offset.z).length() > 0.05:
					node.rotation.y = atan2(offset.x, offset.z)
				node.position = node.position.move_toward(target, MOVE_SPEED * delta)
			# The right animation for the moment.
			if is_same(group, _armies):
				var state: String = entry.get("state", "idle")
				for figure: Node3D in entry["figures"]:
					var action := "walk" if moving else "idle"
					if moving and offset.length() > 1.5 and _characters.can_play(figure, "trot"):
						action = "trot"  # a mounted figure with ground to make up
					if state in AT_ARMS:
						for strike: String in STRIKES:
							if _characters.can_play(figure, strike):
								action = strike
					_characters.play(figure, action)
				if entry.has("boat") and entry.get("afloat", false):  # a ship rides the swell
					_swell += delta
					entry["boat"].position.y = 0.03 * sin(_swell * 1.7 + node.position.x)
					entry["boat"].rotation.z = 0.05 * sin(_swell * 1.3 + node.position.z)
			elif entry.get("mounted", false):
				_characters.play(node, ("trot" if offset.length() > 1.5 else "walk") if moving else "idle")
			else:
				_characters.play(node, "walk" if moving else entry.get("doing", "idle"))


## Sets where a figure should be. A figure seen for the first time appears there
## at once; afterwards it glides.
func _aim(entry: Dictionary, target: Vector3) -> void:
	entry["target"] = target
	if not entry.get("placed", false):
		entry["node"].position = target
		entry["placed"] = true


func _spot(x: int, y: int, offset: Vector3) -> Vector3:
	return _terrain.tile_position(x, y) + offset


func _drop_missing(group: Dictionary, seen: Dictionary) -> void:
	for id: int in group.keys():
		if not seen.has(id):
			group[id]["node"].queue_free()
			group.erase(id)


## "12 Archers, 8 Swordsmen", largest first.
func _army_caption(army: Dictionary) -> String:
	var units: Dictionary = army["units"]
	var order := units.keys()
	order.sort_custom(func(a: String, b: String) -> bool: return int(units[a]) > int(units[b]))
	var parts: Array[String] = []
	for unit_id: String in order:
		parts.append("%d %s" % [int(units[unit_id]), _unit_names.get(unit_id, unit_id)])
	if army["commander"] == null:
		return ", ".join(parts)
	var commander: Dictionary = army["commander"]
	return "%s\n%s  (level %d)" % [", ".join(parts), commander["name"], int(commander["level"])]


# -- figures -------------------------------------------------------------------

func _make_army(civ: int, army: Dictionary, look: String) -> Dictionary:
	var color: Color = _civ_colors[civ]
	var root := Node3D.new()
	var figure: Node3D = null
	if army["commander"] != null:
		figure = _characters.instance("Commander", color, COMMANDER_HEIGHT)
		if figure == null:
			figure = _commander_figure(color)  # the model is missing: the old placeholder
	elif SOLDIER_MODELS.has(str(army["dominant"])):
		var soldier: Array = SOLDIER_MODELS[str(army["dominant"])]
		figure = _characters.instance(soldier[0], color, soldier[1])
	if figure == null:
		figure = _soldier_figure(str(army["dominant"]), color)
	# The army itself: whoever leads it in front, its soldiers drawn up in ranks behind.
	var troop := Node3D.new()
	troop.add_child(figure)
	var figures: Array = [figure]
	var ranks := _ranks(army)
	for i in ranks.size():
		var soldier: Node3D = _soldier(ranks[i], color)
		soldier.position = Vector3((i % 3 - 1) * RANK_SPACING, 0, -(i / 3 + 1) * RANK_SPACING)
		troop.add_child(soldier)
		figures.append(soldier)
	root.add_child(troop)
	figure = troop

	# Dust where an army is fighting.
	var dust := CPUParticles3D.new()
	dust.emitting = false
	dust.amount = 18
	dust.lifetime = 1.1
	dust.mesh = _sphere(0.07)
	var dust_material := StandardMaterial3D.new()
	dust_material.albedo_color = Color(0.74, 0.66, 0.52, 0.5)
	dust_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	dust_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	dust.material_override = dust_material
	dust.emission_shape = CPUParticles3D.EMISSION_SHAPE_SPHERE
	dust.emission_sphere_radius = 0.45
	dust.direction = Vector3.UP
	dust.spread = 40.0
	dust.gravity = Vector3(0, 0.25, 0)
	dust.initial_velocity_min = 0.2
	dust.initial_velocity_max = 0.6
	dust.scale_amount_min = 0.6
	dust.scale_amount_max = 1.8
	dust.position.y = 0.1
	root.add_child(dust)

	# What stands in for the army in the whole-map view: a diamond in the civ's colour.
	var marker := MeshInstance3D.new()
	var marker_mesh := BoxMesh.new()
	marker_mesh.size = Vector3(2.6, 2.6, 2.6)
	var marker_material := StandardMaterial3D.new()
	marker_material.albedo_color = color
	marker_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	marker_mesh.material = marker_material
	marker.mesh = marker_mesh
	marker.position.y = 3.4
	marker.rotation = Vector3(PI / 4, 0, PI / 4)
	root.add_child(marker)

	var label := Label3D.new()
	label.font_size = 44
	label.fixed_size = true  # the same size on screen at every zoom
	label.outline_size = 12
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.modulate = color.lightened(0.55)
	root.add_child(label)

	add_child(root)
	return {"node": root, "figure": figure, "figures": figures, "dust": dust, "marker": marker, "label": label,
		"look": look, "target": Vector3.ZERO}


## The unit type of each figure in an army's ranks, most numerous first: one for every
## SOLDIERS_PER_FIGURE soldiers of that type.
func _ranks(army: Dictionary) -> Array:
	var units: Dictionary = army["units"]
	var order := units.keys()
	order.sort_custom(func(a: String, b: String) -> bool: return int(units[a]) > int(units[b]) or (int(units[a]) == int(units[b]) and a < b))
	var ranks: Array = []
	for unit_id: String in order:
		for n in int(units[unit_id]) / SOLDIERS_PER_FIGURE:
			if ranks.size() < MAX_RANKS:
				ranks.append(unit_id)
	return ranks


## One soldier of a unit type: its model if there is one, the plain figure otherwise.
func _soldier(unit_id: String, color: Color) -> Node3D:
	var soldier: Node3D = null
	if SOLDIER_MODELS.has(unit_id):
		soldier = _characters.instance(SOLDIER_MODELS[unit_id][0], color, SOLDIER_MODELS[unit_id][1])
	if soldier == null:
		return _soldier_figure(unit_id, color)
	if unit_id == "spearman":  # the same man-at-arms, with a spear grounded beside him
		_part(soldier, _cylinder(0.012, 0.8), WOOD, Vector3(0.17, 0.4, 0.05))
		_part(soldier, _box(0.035, 0.09, 0.035), STEEL, Vector3(0.17, 0.83, 0.05))
	return soldier


func _make_villager(civ: int, task: String, look: String, mounted: bool) -> Dictionary:
	var color: Color = _civ_colors[civ]
	var model: Node3D = _characters.instance("Rider", color, RIDER_HEIGHT) if mounted else _characters.instance("Villager", color, VILLAGER_HEIGHT)
	if model != null:
		add_child(model)
		return {"node": model, "look": look, "target": Vector3.ZERO}
	var figure := Node3D.new()
	figure.scale = Vector3.ONE * FIGURE_SCALE * 0.6
	_part(figure, _capsule(0.13, 0.5), color.lerp(Color(0.6, 0.5, 0.35), 0.5), Vector3(0, 0.25, 0))
	_part(figure, _sphere(0.11), SKIN, Vector3(0, 0.6, 0))
	if task == "build":  # a hammer
		_part(figure, _box(0.04, 0.34, 0.04), WOOD, Vector3(0.2, 0.42, 0.05))
		_part(figure, _box(0.16, 0.08, 0.08), STEEL, Vector3(0.2, 0.6, 0.05))
	elif task == "gather":  # a basket
		_part(figure, _box(0.2, 0.14, 0.2), WOOD.lightened(0.3), Vector3(0, 0.3, 0.2))
	add_child(figure)
	return {"node": figure, "look": look, "target": Vector3.ZERO}


func _soldier_figure(unit_id: String, color: Color) -> Node3D:
	var figure := Node3D.new()
	figure.scale = Vector3.ONE * FIGURE_SCALE
	var lift := 0.0
	if unit_id == "cavalry":  # the horse
		lift = 0.38
		_part(figure, _box(0.24, 0.26, 0.66), WOOD.darkened(0.2), Vector3(0, 0.36, 0))
		_part(figure, _box(0.14, 0.3, 0.16), WOOD.darkened(0.2), Vector3(0, 0.56, 0.36))
		for leg: Vector3 in [Vector3(0.09, 0.12, 0.25), Vector3(-0.09, 0.12, 0.25), Vector3(0.09, 0.12, -0.25), Vector3(-0.09, 0.12, -0.25)]:
			_part(figure, _box(0.06, 0.24, 0.06), WOOD.darkened(0.35), leg)
	_part(figure, _capsule(0.14, 0.52), color, Vector3(0, 0.26 + lift, 0))
	_part(figure, _sphere(0.12), SKIN, Vector3(0, 0.64 + lift, 0))
	match unit_id:
		"swordsman":
			_part(figure, _box(0.05, 0.46, 0.03), STEEL, Vector3(0.21, 0.5 + lift, 0.08))  # sword
			_part(figure, _box(0.16, 0.05, 0.05), WOOD, Vector3(0.21, 0.3 + lift, 0.08))  # crossguard
			_part(figure, _box(0.05, 0.34, 0.28), color.lightened(0.45), Vector3(-0.2, 0.36 + lift, 0.06))  # shield
			_part(figure, _sphere(0.13), STEEL, Vector3(0, 0.7 + lift, 0))  # helmet
		"archer":
			var bow := _part(figure, _torus(0.2, 0.235), WOOD, Vector3(-0.2, 0.42 + lift, 0.1))
			bow.rotation = Vector3(0, 0, PI / 2)
			bow.scale = Vector3(1.4, 1.0, 0.45)
			_part(figure, _box(0.07, 0.3, 0.07), WOOD.lightened(0.2), Vector3(0.1, 0.44 + lift, -0.15))  # quiver
		"cavalry":
			_part(figure, _cylinder(0.02, 1.0), WOOD, Vector3(0.2, 0.75 + lift, 0.1))  # lance
			_part(figure, _sphere(0.13), STEEL, Vector3(0, 0.7 + lift, 0))
		_:  # spearman
			_part(figure, _cylinder(0.02, 1.15), WOOD, Vector3(0.2, 0.6 + lift, 0.05))
			_part(figure, _box(0.06, 0.14, 0.06), STEEL, Vector3(0.2, 1.22 + lift, 0.05))
	return figure


func _commander_figure(color: Color) -> Node3D:
	var figure := Node3D.new()
	figure.scale = Vector3.ONE * FIGURE_SCALE * 1.25
	_part(figure, _capsule(0.15, 0.56), color.darkened(0.15), Vector3(0, 0.28, 0))
	_part(figure, _sphere(0.12), SKIN, Vector3(0, 0.68, 0))
	_part(figure, _box(0.3, 0.5, 0.04), color, Vector3(0, 0.3, -0.16))  # cape
	_part(figure, _cylinder(0.11, 0.07), Color(0.95, 0.78, 0.2), Vector3(0, 0.81, 0))  # crown
	_part(figure, _cylinder(0.02, 1.5), WOOD, Vector3(-0.24, 0.75, 0))  # banner pole
	_part(figure, _box(0.42, 0.28, 0.03), color.lightened(0.2), Vector3(-0.03, 1.33, 0))  # banner
	_part(figure, _box(0.05, 0.42, 0.03), STEEL, Vector3(0.22, 0.5, 0.08))  # sword
	return figure


func _part(parent: Node3D, mesh: Mesh, color: Color, at: Vector3) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.material_override = _material(color)
	instance.position = at
	parent.add_child(instance)
	return instance


func _material(color: Color) -> StandardMaterial3D:
	var key := color.to_html()
	if not _materials.has(key):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.85
		_materials[key] = material
	return _materials[key]


func _box(x: float, y: float, z: float) -> BoxMesh:
	var mesh := BoxMesh.new()
	mesh.size = Vector3(x, y, z)
	return mesh


func _sphere(radius: float) -> SphereMesh:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	mesh.radial_segments = 12
	mesh.rings = 6
	return mesh


func _capsule(radius: float, height: float) -> CapsuleMesh:
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = height
	mesh.radial_segments = 12
	return mesh


func _cylinder(radius: float, height: float) -> CylinderMesh:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = 8
	return mesh


func _torus(inner: float, outer: float) -> TorusMesh:
	var mesh := TorusMesh.new()
	mesh.inner_radius = inner
	mesh.outer_radius = outer
	mesh.rings = 16
	mesh.ring_segments = 6
	return mesh
