extends Node3D
## Armies and villagers on the map.
##
## An army with a commander is led by the general, a character of the KayKit Adventurers
## pack (adventurers.gd): each general is one of six characters, the same one for life,
## larger than the ranks and caped in the civ's colour. Behind come the ranks: a knight of
## the same pack with sword or spear and shield for the foot, our own archer and mounted
## knight for archers and cavalry. Every figure stands, walks or strikes according to what
## the army is doing. An army without a commander is led by a figure of its dominant type. An army that has put out from a harbour is shown as a ship until it
## lands. Villagers are animated too: walking, hammering at a building, working the
## land or drawing water; one with a horse from the stables is shown riding.
## A villager crossing water is shown as a small fishing boat alone, its oars rowing.
##
## How much is drawn follows the zoom. From afar a field army is a single marker in its
## civ's colour with its size and its general's name; garrisons and villagers are left out.
## Closer in, the general and the first few of the ranks; closest, all of them, the full
## caption, and the generals in reserve standing at the gates of the capitals they hold.

# Everything is drawn to fit the tile grid: figures stand well under a tile tall, beside
# buildings that fill one tile.
const FIGURE_SCALE := 0.65
const COMMANDER_HEIGHT := 0.8  # in tiles: the old placeholder
const GENERAL_HEIGHT := 0.74  # a general of the Adventurers pack, a head taller than his soldiers
const FOOT_HEIGHT := 0.56  # a foot soldier of the same pack
const MID_RANKS := 3  # rank figures shown at middle zoom: enough to read as an army
const POSTED_SPOT := Vector3(-0.85, 0, 1.0)  # where a general in reserve stands: in the castle's front court
const VILLAGER_HEIGHT := 0.45
const RIDER_HEIGHT := 0.62
const SOLDIER_HEIGHT := 0.58  # a man-at-arms: the commander's model, smaller
## Unit types with a model of their own for an army without a commander: [model, height].
## Unit types drawn from the Adventurers pack, each with its own kit (adventurers.gd KITS): the
## knight for the foot, the hooded rogue with a bow for archers, the knight on horseback for cavalry.
const FOOT_MODELS := {"swordsman": "Knight:swordsman", "spearman": "Knight:spearman", "archer": "Rogue_Hooded:archer"}
const MOUNTED_MODELS := {"cavalry": "Knight:cavalry"}
const MOUNTED_HEIGHT := 0.8  # a horseman, hooves to helmet
const MOUNTED_GENERAL_HEIGHT := 0.98
const SOLDIERS_PER_FIGURE := 48  # an army shows one more figure in its ranks for every so many soldiers
const MAX_RANKS := 8  # ... up to this many behind whoever leads it
const RANK_SPACING := 0.34
const STRIKES := ["attack", "shoot"]  # what a model's fighting animation may be called
const BOAT_LENGTH := 0.95
# A villager's fishing boat: its length in tiles (half an army's ship), where its rowlocks are (in the model's own units, as tools/blender/make_models.py draws it) and how it rows.
const SKIFF_LENGTH := 0.45
const AFLOAT := 0.005  # a keel never sinks below the water's surface: it rides this far above at its lowest
const SKIFF_ROWLOCK := Vector3(0.2, 0.225, -0.1)
const STROKE_RATE := 6.0  # radians a second: about one stroke a second
const ROWING_ON := 1.5  # seconds the oars keep going after the boat last moved
## Siege engines an army brings up to an enemy capital's walls: [model, size, where (behind the leader)].
const SIEGE_ENGINES := [["civsim_ram", 0.55, Vector3(0.0, 0, 0.45)], ["civsim_catapult", 0.5, Vector3(0.55, 0, -0.65)]]
const SIEGE_REACH := 3  # tiles from an enemy capital within which a besieging army has its engines up
const GARRISON_SPOT := Vector3(0.8, 0, 1.15)  # the garrison is drawn up in the castle's front court
const AT_THE_GATE := Vector3(0, 0, 2.9)  # a field army in one of its own capitals waits outside the gate
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
var _clock := 0.0
var _characters: RefCounted  # characters.gd
var _adventurers: RefCounted  # adventurers.gd
var _models: RefCounted  # models.gd: the ship and the siege engines
var _posted := {}  # "civ:name" -> {"node", "look", "target"}: generals in reserve, at their capitals
var _capitals := {}  # "x,y" -> civ id, of every capital a civ holds (from the last tick)


func setup(terrain: Node3D, init: Dictionary, civ_colors: Array, characters: RefCounted,
		adventurers: RefCounted, models: RefCounted) -> void:
	_characters = characters
	_adventurers = adventurers
	_models = models
	for child in get_children():
		child.queue_free()
	_armies.clear()
	_villagers.clear()
	_posted.clear()
	_terrain = terrain
	_civ_colors = civ_colors
	_unit_names.clear()
	for unit_id: String in init["unit_types"]:
		_unit_names[unit_id] = init["unit_types"][unit_id]["name"]


func update(armies: Array, villagers: Array) -> void:
	var seen := {}
	for army: Dictionary in armies:
		if army["role"] == "garrison":
			continue  # a castle's garrison stays inside its walls: click the castle to see it
		var id := int(army["id"])
		seen[id] = true
		var civ := int(army["civ"])
		var commander: Variant = army["commander"]
		# What the piece looks like; rebuilt only when that changes.
		var look := "%d:%s:%s:%s" % [civ, str(commander["name"]) if commander != null else "-", str(army["dominant"]), _ranks(army)]
		if not _armies.has(id) or _armies[id]["look"] != look:
			if _armies.has(id):
				_armies[id]["node"].queue_free()
			_armies[id] = _make_army(civ, army, look)
		var entry: Dictionary = _armies[id]
		entry["field"] = army["role"] == "field"
		entry["state"] = str(army["state"])
		entry["afloat"] = bool(army.get("boat", false))
		if entry["afloat"] and not entry.has("boat"):
			var boat: Node3D = _models.instance("civsim_ship", _models.tinted_material(_civ_colors[civ]), BOAT_LENGTH)
			if boat != null:
				boat.position.y = AFLOAT  # on the water from its first frame
				entry["node"].add_child(boat)
				entry["boat"] = boat
		_show_siege_engines(entry, civ, army)
		entry["size"] = int(army["size"])
		entry["general"] = str(commander["name"]) if commander != null else ""
		# An army too far from the player's own armies and cities to count is shown roughly.
		var counted := bool(army.get("scouted", true))
		entry["size_text"] = str(entry["size"]) if counted else "~%d" % (maxi(1, roundi(entry["size"] / 50.0)) * 50)
		entry["caption"] = _army_caption(army) if counted else "About %s soldiers" % str(entry["size_text"]).substr(1)
		_show_army(entry)
		var offset := Vector3.ZERO
		if army["role"] == "garrison":
			offset = GARRISON_SPOT
		elif int(_capitals.get("%d,%d" % [int(army["x"]), int(army["y"])], -1)) == civ:
			offset = AT_THE_GATE  # not standing on the keep
		_aim(entry, _spot(int(army["x"]), int(army["y"]), offset))
	_drop_missing(_armies, seen)

	seen = {}
	var crowd := {}  # tile -> villagers already placed there, to fan them out
	for villager: Dictionary in villagers:
		var id := int(villager["id"])
		seen[id] = true
		# Only what changes the model itself; what the villager is doing is shown by its animation.
		var plain: bool = not _characters.has("Villager")
		var afloat := bool(villager.get("afloat", false))
		var mounted := bool(villager["mounted"])
		var look := "%d:%s:%s" % [int(villager["civ"]), mounted, villager["task"] if plain else ""]
		if not _villagers.has(id) or _villagers[id]["look"] != look:
			var at: Variant = null
			var skiff: Variant = null
			if _villagers.has(id):
				at = _villagers[id]["node"].position
				skiff = _villagers[id].get("skiff")
				_villagers[id]["node"].queue_free()
			_villagers[id] = _make_villager(int(villager["civ"]), villager["task"], look, mounted)
			if at != null:  # same villager, new task: carry on from where it stands
				_villagers[id]["node"].position = at
				_villagers[id]["placed"] = true
			if skiff != null:
				_villagers[id]["skiff"] = skiff
		var key := "%d,%d" % [int(villager["x"]), int(villager["y"])]
		var n: int = crowd.get(key, 0)
		crowd[key] = n + 1
		var fan := Vector3(-0.3 + 0.3 * (n % 3), 0, 0.3 - 0.3 * (n / 3 % 3))
		_aim(_villagers[id], _spot(int(villager["x"]), int(villager["y"]), fan))
		_villagers[id]["afloat"] = afloat
		# On water a villager crosses in a fishing boat, shown alone like an army's ship: it
		# comes and goes with the water.
		if afloat and not _villagers[id].has("skiff"):
			var made: Variant = _make_skiff(int(villager["civ"]))
			if made != null:
				_villagers[id]["skiff"] = made
				_villagers[id]["rowed"] = ROWING_ON
				_row(_villagers[id], false, 0.0)  # on the water where he is, from its first frame
		elif not afloat and _villagers[id].has("skiff"):
			_villagers[id]["skiff"]["node"].queue_free()
			_villagers[id].erase("skiff")
		_villagers[id]["node"].visible = not afloat
		# What it does once it has stopped walking.
		var doing := "idle"
		if villager["at_work"] and villager["task"] == "build":
			doing = "hammer"
		elif villager["at_work"] and villager["task"] == "gather":
			doing = "water" if villager["gathers"] == "water" else "pick"
		_villagers[id]["doing"] = doing
		_villagers[id]["mounted"] = mounted
	_drop_missing(_villagers, seen)


func set_detail(detail: int) -> void:
	_detail = detail
	for entry: Dictionary in _armies.values():
		_show_army(entry)
	for entry: Dictionary in _villagers.values():
		entry["node"].visible = not entry.get("afloat", false)
	for entry: Dictionary in _posted.values():
		entry["node"].visible = detail >= 2
		_characters.set_active(entry["node"], detail >= 2)


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
	var figures: Array = entry["figures"]
	for i in figures.size():
		# The general and a few of the ranks closer in; every rank only up close.
		var one: Node3D = figures[i]
		one.visible = i <= MID_RANKS or _detail >= 2
		_characters.set_active(one, figure.visible and one.visible)
	(entry["dust"] as CPUParticles3D).emitting = figure.visible and entry.get("state", "") in AT_ARMS
	if entry.has("boat"):
		entry["boat"].visible = _detail >= 1 and afloat
	if entry.has("engines"):  # up only at an enemy capital's walls, and seen from closer in
		(entry["engines"] as Node3D).visible = entry.get("at_walls", false) and _detail >= 1 and not afloat
	marker.visible = _detail == 0 and is_field
	if _detail == 0:
		label.visible = is_field
		label.text = str(entry.get("size_text", entry.get("size", 0)))
		if entry.get("general", "") != "":
			label.text += " · " + str(entry["general"])  # who leads it, readable from afar
		label.pixel_size = 0.0007
		label.position.y = 7.4
	elif _detail == 1:
		label.visible = is_field
		label.text = str(entry.get("size_text", entry.get("size", 0)))
		label.pixel_size = 0.0005
		label.position.y = 1.3
	else:
		# Up close: exactly what is in the army, and who leads it.
		label.visible = entry.get("caption", "") != ""
		label.text = entry.get("caption", "")
		label.pixel_size = 0.00034
		label.position.y = 1.3


func _process(delta: float) -> void:
	_clock += delta
	for group: Dictionary in [_armies, _villagers, _posted]:
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
					entry["boat"].position.y = AFLOAT + 0.03 * (1.0 + sin(_swell * 1.7 + node.position.x))
					entry["boat"].rotation.z = 0.05 * sin(_swell * 1.3 + node.position.z)
			elif entry.has("skiff"):
				_row(entry, moving, delta)
			elif entry.get("mounted", false):
				_characters.play(node, ("trot" if offset.length() > 1.5 else "walk") if moving else "idle")
			else:
				_characters.play(node, "walk" if moving else entry.get("doing", "idle"))


## A villager's boat goes where he would be (he is not drawn aboard), bow first, riding the water a little; its oars pull
## while it is under way and for a moment after, and otherwise lie still.
func _row(entry: Dictionary, moving: bool, delta: float) -> void:
	var skiff: Dictionary = entry["skiff"]
	var node: Node3D = entry["node"]
	var boat: Node3D = skiff["node"]
	entry["rowed"] = 0.0 if moving else float(entry.get("rowed", ROWING_ON)) + delta
	var rowing: bool = entry["rowed"] < ROWING_ON
	var bob := AFLOAT + 0.008 * (1.0 + sin(_clock * 1.7 + node.position.x))  # never below the surface
	boat.position = node.position + Vector3(0, bob, 0)
	boat.rotation = Vector3(0, node.rotation.y, 0.04 * sin(_clock * 1.3 + node.position.z))
	if rowing:
		skiff["stroke"] = float(skiff["stroke"]) + STROKE_RATE * delta
	var stroke: float = skiff["stroke"]
	# The blade sweeps back in the water, then lifts and comes forward through the air.
	var sweep := 0.5 * sin(stroke) if rowing else 0.0
	var dip := -0.3 - 0.16 * cos(stroke) if rowing else -0.12
	(skiff["oars"][0] as Node3D).rotation = Vector3(0, sweep, dip)
	(skiff["oars"][1] as Node3D).rotation = Vector3(0, PI - sweep, dip)


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
	for id: Variant in group.keys():  # army and villager ids, or "civ:name" for a posted general
		if not seen.has(id):
			if group[id].has("skiff"):
				group[id]["skiff"]["node"].queue_free()
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
	var what := ", ".join(parts)
	if float(army.get("tier", 1.0)) >= 1.05:
		what += "  (tier %s)" % str(snappedf(float(army["tier"]), 0.1))
	if bool(army.get("refit", false)):
		what += "\nGoing home to fill its ranks"
	elif str(army.get("duty", "")) == "reinforce":
		what += "\nStanding with an ally"
	elif str(army.get("duty", "")) == "hold":
		what += "\nHolding the castle"
	if army["commander"] == null:
		return what
	var commander: Dictionary = army["commander"]
	return "%s\n%s  (level %d)" % [what, commander["name"], int(commander["level"])]


# -- figures -------------------------------------------------------------------

func _make_army(civ: int, army: Dictionary, look: String) -> Dictionary:
	var color: Color = _civ_colors[civ]
	var root := Node3D.new()
	var figure: Node3D = null
	if army["commander"] != null:
		var character: String = _adventurers.general_for(civ, str(army["commander"]["name"]))
		# The general of a mounted army rides with it.
		var mounted := str(army["dominant"]) == "cavalry"
		figure = _adventurers.instance(character, color, MOUNTED_GENERAL_HEIGHT if mounted else GENERAL_HEIGHT, mounted)
		if figure == null:
			figure = _commander_figure(color)  # the model is missing: the old placeholder
	else:
		figure = _soldier(str(army["dominant"]), color)
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


## An army at the walls of another civ's capital brings up a catapult and a ram.
func _show_siege_engines(entry: Dictionary, civ: int, army: Dictionary) -> void:
	var at_walls := false
	if str(army["state"]) == "besieging":
		var x := int(army["x"])
		var y := int(army["y"])
		for dy in range(-SIEGE_REACH, SIEGE_REACH + 1):
			for dx in range(-SIEGE_REACH, SIEGE_REACH + 1):
				var holder := int(_capitals.get("%d,%d" % [x + dx, y + dy], -1))
				if holder >= 0 and holder != civ:
					at_walls = true
	if at_walls and not entry.has("engines"):
		var engines := Node3D.new()
		var material: Material = _models.tinted_material(_civ_colors[civ])
		for engine: Array in SIEGE_ENGINES:
			var model: Node3D = _models.instance(engine[0], material, float(engine[1]))
			if model != null:
				model.position = engine[2]
				engines.add_child(model)
		entry["node"].add_child(engines)
		entry["engines"] = engines
	entry["at_walls"] = at_walls


## One soldier of a unit type: its model if there is one, the plain figure otherwise.
func _soldier(unit_id: String, color: Color) -> Node3D:
	var soldier: Node3D = null
	if FOOT_MODELS.has(unit_id):
		soldier = _adventurers.instance(FOOT_MODELS[unit_id], color, FOOT_HEIGHT)
	elif MOUNTED_MODELS.has(unit_id):
		soldier = _adventurers.instance(MOUNTED_MODELS[unit_id], color, MOUNTED_HEIGHT, true)
	if soldier == null:
		return _soldier_figure(unit_id, color)
	return soldier


## Generals in reserve, stationed at capitals: each stands before the castle he holds, seen
## only up close. `civs` is the tick's list of civs.
func update_posted(civs: Array) -> void:
	var seen := {}
	_capitals.clear()
	for civ: Dictionary in civs:
		var civ_id := int(civ["id"])
		for settlement: Dictionary in civ.get("settlements", []):
			_capitals["%d,%d" % [int(settlement["x"]), int(settlement["y"])]] = civ_id
		var crowd := {}  # capital -> generals already standing there
		for commander: Dictionary in civ.get("commanders_in_reserve", []):
			if commander.get("x") == null:
				continue  # not posted anywhere
			var key := "%d:%s" % [civ_id, commander["name"]]
			seen[key] = true
			if not _posted.has(key):
				var figure: Node3D = _adventurers.instance(_adventurers.general_for(civ_id, str(commander["name"])),
					_civ_colors[civ_id], GENERAL_HEIGHT)
				if figure == null:
					continue
				add_child(figure)
				_posted[key] = {"node": figure, "look": key, "target": Vector3.ZERO}
			var at := "%d,%d" % [int(commander["x"]), int(commander["y"])]
			var n: int = crowd.get(at, 0)
			crowd[at] = n + 1
			var entry: Dictionary = _posted[key]
			_aim(entry, _spot(int(commander["x"]), int(commander["y"]), POSTED_SPOT + Vector3(0.35 * n, 0, 0)))
			entry["node"].visible = _detail >= 2
			_characters.set_active(entry["node"], _detail >= 2)
	_drop_missing(_posted, seen)


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


## A fishing boat in the civ's colour with its two oars, or null without the models.
func _make_skiff(civ: int) -> Variant:
	var material: Material = _models.tinted_material(_civ_colors[civ])
	var hull: Node3D = _models.instance("civsim_fishing_boat", material, SKIFF_LENGTH)
	if hull == null:
		return null
	var boat := Node3D.new()
	boat.add_child(hull)
	var measure := hull.scale.x
	var oars: Array[Node3D] = []
	for side: float in [1.0, -1.0]:
		var oar: Node3D = _models.instance("civsim_oar", material, 1.0)
		if oar == null:
			continue
		oar.scale = hull.scale  # drawn to the boat's measure, not sized on its own
		var pivot := Node3D.new()  # at the rowlock
		pivot.position = Vector3(side * SKIFF_ROWLOCK.x, SKIFF_ROWLOCK.y, SKIFF_ROWLOCK.z) * measure
		pivot.add_child(oar)
		boat.add_child(pivot)
		oars.append(pivot)
	if oars.size() < 2:
		boat.free()
		return null
	add_child(boat)
	return {"node": boat, "oars": oars, "stroke": 0.0}


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
