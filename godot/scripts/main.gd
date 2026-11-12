extends Node3D
## Viewer entry point. Builds the scene in code and wires the sim client to the
## terrain, the civ view and the HUD. The viewer holds no game logic: it redraws
## whatever the latest tick message says.

const SimClient := preload("res://scripts/sim_client.gd")
const Terrain := preload("res://scripts/terrain.gd")
const CivView := preload("res://scripts/civ_view.gd")
const UnitView := preload("res://scripts/unit_view.gd")
const Models := preload("res://scripts/models.gd")
const Characters := preload("res://scripts/characters.gd")
const Adventurers := preload("res://scripts/adventurers.gd")
const CameraRig := preload("res://scripts/camera_rig.gd")
const Hud := preload("res://scripts/hud.gd")
const Menu := preload("res://scripts/menu.gd")

const UI_SCALE := 1.35  # the whole overlay is drawn this much larger than Godot's default text size
const UI_SCALE_STEP := 0.1
const FAR_VIEW := 75.0  # camera further than this: the whole-map view
const NEAR_VIEW := 38.0  # camera closer than this: full detail

var _client := SimClient.new()
var _terrain := Terrain.new()
var _civ_view := CivView.new()
var _unit_view := UnitView.new()
var _camera := CameraRig.new()
var _hud := Hud.new()
var _menu := Menu.new()
var _auto_started := false
var _starting := ""  # the mode of the game just asked for from the menu: "watch" or "rule"
var _models := Models.new()
var _characters := Characters.new()
var _civs: Array = []  # the last tick's civs, for picking a castle under the mouse
var _press_at := Vector2(-1000, -1000)  # where the left button went down
const CLICK_SLOP := 6.0  # pixels the mouse may move between press and release and still be a click
var _adventurers := Adventurers.new()

var _ready_for_ticks := false
var _civ_colors: Array = []
var _territory_rev := -1
var _detail := -1  # how much the map shows, set from how far the camera is
var _perf_clock := 0.0  # CIVSIM_PERF=1 prints frame rate and draw calls every few seconds
var _tick := 0
var _ruled := -1  # the civ the player rules, or -1


func _ready() -> void:
	_set_ui_scale(UI_SCALE)
	_add_lighting()
	add_child(_terrain)
	add_child(_civ_view)
	add_child(_unit_view)
	add_child(_camera)
	add_child(_hud)
	add_child(_menu)
	_menu.start_requested.connect(_on_start_requested)
	_menu.civ_chosen.connect(_on_civ_chosen)
	add_child(_client)

	_client.connection_changed.connect(_on_connection_changed)
	_client.init_received.connect(_on_init)
	_client.tick_received.connect(_on_tick)
	_client.status_received.connect(_hud.set_status)
	_hud.command_requested.connect(_client.send_command)


## A left click (not a drag, which pans the map) on a castle opens its panel; anywhere else closes it.
func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT):
		return
	if event.pressed:
		_press_at = event.position
	elif _press_at.distance_to(event.position) < CLICK_SLOP:
		var tile: Vector2i = _castle_under(event.position)
		_hud.show_castle(tile.x, tile.y)


## The tile of the capital whose castle is under the screen point, or (-1, -1).
func _castle_under(at: Vector2) -> Vector2i:
	var camera := get_viewport().get_camera_3d()
	if camera == null or _terrain.map_width == 0:
		return Vector2i(-1, -1)
	var origin := camera.project_ray_origin(at)
	var direction := camera.project_ray_normal(at)
	# Walk down the ray until it meets the ground.
	var ground := Vector3.INF
	var t := 0.0
	while t < camera.far:
		var point := origin + direction * t
		var floor_y: float = _terrain.height_at(point.x, point.z)
		if point.y <= floor_y + 0.6:  # a castle stands well above its ground: aim for its walls
			ground = point
			break
		t += maxf(0.1, (point.y - floor_y) * 0.4)
	if ground == Vector3.INF:
		return Vector2i(-1, -1)
	var best := Vector2i(-1, -1)
	var nearest := CivView.CAPITAL_FOOTPRINT * 0.5 + 0.4
	for civ: Dictionary in _civs:
		for settlement: Dictionary in civ["settlements"]:
			var gap := Vector2(float(settlement["x"]) - ground.x, float(settlement["y"]) - ground.z).length()
			if gap < nearest:
				nearest = gap
				best = Vector2i(int(settlement["x"]), int(settlement["y"]))
	return best


func _unhandled_key_input(event: InputEvent) -> void:
	if not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_SPACE:
			_client.send_command("toggle_pause")
		KEY_PERIOD:
			_client.send_command("step")
		KEY_EQUAL, KEY_PLUS:
			_hud.request_speed(2.0)
		KEY_MINUS:
			_hud.request_speed(0.5)
		KEY_TAB:
			_hud.toggle_diplomacy()
		KEY_B:
			_terrain.toggle_region_borders()
		KEY_H:
			_hud.toggle_help()
		KEY_BRACKETLEFT:
			_set_ui_scale(get_window().content_scale_factor - UI_SCALE_STEP)
		KEY_BRACKETRIGHT:
			_set_ui_scale(get_window().content_scale_factor + UI_SCALE_STEP)
		KEY_1, KEY_2, KEY_3, KEY_4:
			_hud.toggle_card(event.keycode - KEY_1)


## Labels and figures are shown according to zoom, so the far view stays readable.
func _process(delta: float) -> void:
	if OS.get_environment("CIVSIM_PERF") == "1":
		_perf_clock += delta
		if _perf_clock >= 3.0:
			_perf_clock = 0.0
			print("perf tick %d: %d fps, %d draw calls, %d objects, %d nodes" % [
				_tick, Engine.get_frames_per_second(),
				Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
				Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME),
				Performance.get_monitor(Performance.OBJECT_NODE_COUNT)])
			var parts: Array[String] = []
			for system: Node in [_terrain, _civ_view, _unit_view, _hud]:
				var kinds := {}
				for node: Node in system.find_children("*", "", true, false):
					kinds[node.get_class()] = kinds.get(node.get_class(), 0) + 1
				parts.append("%s %s" % [system.get_script().resource_path.get_file(), kinds])
			print("  ", "  ".join(parts))
	# CIVSIM_QUIT_AT=<tick> closes the viewer once the game reaches that tick, for scripted runs.
	var quit_at := OS.get_environment("CIVSIM_QUIT_AT")
	if quit_at != "" and _tick >= int(quit_at):
		get_tree().quit()
	var distance: float = _camera.distance()
	_civ_view.set_view_distance(distance)
	var detail := 0 if distance > FAR_VIEW else (1 if distance > NEAR_VIEW else 2)
	if detail != _detail:
		_detail = detail
		_civ_view.set_detail(detail)
		_unit_view.set_detail(detail)


## Scales every panel and all overlay text together; the 3D map is unaffected.
func _set_ui_scale(factor: float) -> void:
	get_window().content_scale_factor = clampf(factor, 0.8, 2.2)


func _on_connection_changed(connected: bool) -> void:
	_hud.set_connected(connected)
	if not connected:
		_ready_for_ticks = false


## The menu asks for a game: the sim builds it and sends its map, as for any game.
func _on_start_requested(mode: String, size: String, civs: int, seed_text: String, map_id: String = "", difficulty: String = "normal") -> void:
	_starting = mode
	var game := {"mode": mode, "size": size, "civs": civs, "difficulty": difficulty}
	if map_id != "":
		game["map"] = map_id
	if seed_text.is_valid_int():
		game["seed"] = int(seed_text)
	_client.send_command("new_game", game)


## A game to be ruled waits, paused, until the player has chosen a civ (or chosen to watch).
func _on_civ_chosen(civ_id: int) -> void:
	_menu.close()
	if civ_id >= 0:
		_client.send_command("take_control", {"civ": civ_id})
	_client.send_command("resume")


func _on_init(data: Dictionary) -> void:
	_civ_colors.clear()
	for civ: Dictionary in data["civs"]:
		_civ_colors.append(Color.html(civ["color"]))
	_terrain.build(data["map"], data["biomes"], Color.html(data["native_faction"]["color"]), _models, data["regions"])
	_civ_view.setup(_terrain, data, _civ_colors, _models, _characters)
	_unit_view.setup(_terrain, data, _civ_colors, _characters, _adventurers, _models)
	_hud.setup(data)
	_camera.focus(_terrain.center(), maxf(_terrain.map_width, _terrain.map_height) * 1.15)
	# CIVSIM_VIEW="x,y,distance" starts the camera on a tile instead of the whole map.
	var view := OS.get_environment("CIVSIM_VIEW").split_floats(",", false)
	if view.size() == 3:
		_camera.focus(_terrain.tile_position(int(view[0]), int(view[1])), view[2])
	if OS.get_environment("CIVSIM_DIPLOMACY") == "1":  # start with the diplomacy panel open
		_hud.toggle_diplomacy()
	var castle := OS.get_environment("CIVSIM_CASTLE").split_floats(",", false)
	if castle.size() == 2:  # CIVSIM_CASTLE="x,y" starts with that castle's panel open
		_hud.show_castle(int(castle[0]), int(castle[1]))
	if OS.get_environment("CIVSIM_CARD") != "":  # start with one civ's card open, by civ id
		_hud.toggle_card(int(OS.get_environment("CIVSIM_CARD")))
	_territory_rev = -1
	_ruled = -1
	_ready_for_ticks = true
	# No game started yet: the main menu, over a game playing itself as the camera circles.
	var lobby: Variant = data.get("lobby")
	_hud.visible = lobby == null
	_camera.auto_orbit = lobby != null
	if lobby != null:
		_menu.show_menu(lobby)
		# CIVSIM_START="mode,size,civs" starts that game straight from the menu, for scripted runs.
		var start := OS.get_environment("CIVSIM_START").split(",", false)
		if start.size() == 3 and not _auto_started:
			_auto_started = true
			_on_start_requested.call_deferred(start[0], start[1], int(start[2]), "")
	elif _starting == "rule":
		var civs: Array = []
		for civ: Dictionary in data["civs"]:
			var entry := civ.duplicate()
			entry["capital"] = civ.get("capital_name", "")
			civs.append(entry)
		_menu.show_pick(civs)
	else:
		_menu.close()
	_starting = ""


func _on_tick(tick: int, data: Dictionary) -> void:
	if not _ready_for_ticks:
		return
	_tick = tick
	# Taking a civ in hand brings the camera to its capital.
	var ruled: int = int(data["ruler"]["civ"]) if data.get("ruler") != null else -1
	if ruled != _ruled:
		_ruled = ruled
		if ruled >= 0 and not data["civs"][ruled]["settlements"].is_empty():
			var home: Dictionary = data["civs"][ruled]["settlements"][0]
			_camera.focus(_terrain.tile_position(int(home["x"]), int(home["y"])), 46.0)
	var rev := int(data["territory_rev"])
	if rev != _territory_rev:
		_territory_rev = rev
		_terrain.apply_territory(data["territory"], _civ_colors)
	_civs = data["civs"]
	_civ_view.update(data["civs"], data["regions"])
	_civ_view.show_rallies(data.get("rallies", []))
	_civ_view.update_links(data["civs"], data["relations"], data["deals"])
	_unit_view.update(data["armies"], data["villagers"])
	_unit_view.update_posted(data["civs"])
	_hud.update(tick, data)
	# CIVSIM_FOLLOW="distance" keeps the camera on the largest army led by a general, for scripted runs.
	var follow := OS.get_environment("CIVSIM_FOLLOW")
	if follow != "":
		var best: Variant = null
		for army: Dictionary in data["armies"]:
			if army["role"] == "field" and army["commander"] != null and not army["afloat"] and (best == null or int(army["size"]) > int(best["size"])):
				best = army
		if best != null:
			_camera.focus(_terrain.tile_position(int(best["x"]), int(best["y"])), float(follow))


func _add_lighting() -> void:
	# A soft afternoon: warm low sun, cool sky fill, a little haze toward the horizon.
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.24, 0.44, 0.74)
	sky_material.sky_horizon_color = Color(0.74, 0.82, 0.9)
	sky_material.ground_bottom_color = Color(0.13, 0.2, 0.3)
	sky_material.ground_horizon_color = Color(0.74, 0.82, 0.9)
	sky_material.sun_angle_max = 12.0
	var sky := Sky.new()
	sky.sky_material = sky_material
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 0.75
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.tonemap_white = 6.0
	environment.adjustment_enabled = true
	environment.adjustment_saturation = 1.12
	environment.adjustment_contrast = 1.04
	# Contact shadows where buildings and trees meet the ground.
	environment.ssao_enabled = true
	environment.ssao_radius = 0.9
	environment.ssao_intensity = 1.6
	environment.ssao_power = 1.4
	# Bright roofs, water glints and snow bloom a little.
	environment.glow_enabled = true
	environment.glow_intensity = 0.35
	environment.glow_bloom = 0.08
	environment.glow_hdr_threshold = 1.05
	# Distance haze, so the far side of the map recedes instead of ending.
	environment.fog_enabled = true
	environment.fog_light_color = Color(0.72, 0.8, 0.9)
	environment.fog_density = 0.0016
	environment.fog_aerial_perspective = 0.4
	environment.fog_sky_affect = 0.0
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-46.0, -38.0, 0.0)
	sun.light_color = Color(1.0, 0.95, 0.86)
	sun.light_energy = 1.25
	sun.shadow_enabled = true
	sun.shadow_blur = 1.6
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_blend_splits = true
	sun.directional_shadow_max_distance = 260.0
	add_child(sun)
	# A weak cool light from the other side keeps the shaded faces of buildings readable.
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-30.0, 140.0, 0.0)
	fill.light_color = Color(0.7, 0.8, 1.0)
	fill.light_energy = 0.22
	fill.shadow_enabled = false
	add_child(fill)
