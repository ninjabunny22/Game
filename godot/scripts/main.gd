extends Node3D
## Viewer entry point. Builds the scene in code and wires the sim client to the
## terrain, the civ view and the HUD. The viewer holds no game logic: it redraws
## whatever the latest tick message says.

const SimClient := preload("res://scripts/sim_client.gd")
const Terrain := preload("res://scripts/terrain.gd")
const CivView := preload("res://scripts/civ_view.gd")
const UnitView := preload("res://scripts/unit_view.gd")
const CameraRig := preload("res://scripts/camera_rig.gd")
const Hud := preload("res://scripts/hud.gd")

const FAR_VIEW := 75.0  # camera further than this: the whole-map view
const NEAR_VIEW := 38.0  # camera closer than this: full detail

var _client := SimClient.new()
var _terrain := Terrain.new()
var _civ_view := CivView.new()
var _unit_view := UnitView.new()
var _camera := CameraRig.new()
var _hud := Hud.new()

var _ready_for_ticks := false
var _civ_colors: Array = []
var _territory_rev := -1
var _detail := -1  # how much the map shows, set from how far the camera is


func _ready() -> void:
	_add_lighting()
	add_child(_terrain)
	add_child(_civ_view)
	add_child(_unit_view)
	add_child(_camera)
	add_child(_hud)
	add_child(_client)

	_client.connection_changed.connect(_on_connection_changed)
	_client.init_received.connect(_on_init)
	_client.tick_received.connect(_on_tick)
	_client.status_received.connect(_hud.set_status)
	_hud.command_requested.connect(_client.send_command)


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
		KEY_1, KEY_2, KEY_3, KEY_4:
			_hud.toggle_card(event.keycode - KEY_1)


## Labels and figures are shown according to zoom, so the far view stays readable.
func _process(_delta: float) -> void:
	var distance: float = _camera.distance()
	var detail := 0 if distance > FAR_VIEW else (1 if distance > NEAR_VIEW else 2)
	if detail != _detail:
		_detail = detail
		_civ_view.set_detail(detail)
		_unit_view.set_detail(detail)


func _on_connection_changed(connected: bool) -> void:
	_hud.set_connected(connected)
	if not connected:
		_ready_for_ticks = false


func _on_init(data: Dictionary) -> void:
	_civ_colors.clear()
	for civ: Dictionary in data["civs"]:
		_civ_colors.append(Color.html(civ["color"]))
	_terrain.build(data["map"], data["biomes"], Color.html(data["native_faction"]["color"]))
	_civ_view.setup(_terrain, data, _civ_colors)
	_unit_view.setup(_terrain, data, _civ_colors)
	_hud.setup(data)
	_camera.focus(_terrain.center(), maxf(_terrain.map_width, _terrain.map_height) * 1.15)
	# CIVSIM_VIEW="x,y,distance" starts the camera on a tile instead of the whole map.
	var view := OS.get_environment("CIVSIM_VIEW").split_floats(",", false)
	if view.size() == 3:
		_camera.focus(_terrain.tile_position(int(view[0]), int(view[1])), view[2])
	if OS.get_environment("CIVSIM_DIPLOMACY") == "1":  # start with the diplomacy panel open
		_hud.toggle_diplomacy()
	if OS.get_environment("CIVSIM_CARD") != "":  # start with one civ's card open, by civ id
		_hud.toggle_card(int(OS.get_environment("CIVSIM_CARD")))
	_territory_rev = -1
	_ready_for_ticks = true


func _on_tick(tick: int, data: Dictionary) -> void:
	if not _ready_for_ticks:
		return
	var rev := int(data["territory_rev"])
	if rev != _territory_rev:
		_territory_rev = rev
		_terrain.apply_territory(data["territory"], _civ_colors)
	_civ_view.update(data["civs"], data["regions"])
	_civ_view.update_links(data["civs"], data["relations"], data["deals"])
	_unit_view.update(data["armies"], data["villagers"])
	_hud.update(tick, data)


func _add_lighting() -> void:
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 0.9
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, -35.0, 0.0)
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 300.0
	add_child(sun)
