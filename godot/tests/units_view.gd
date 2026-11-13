extends SceneTree
## Draws armies the way the game does (unit_view.gd) on a flat field, to check by eye:
## one besieging another civ's capital (its siege engines up), one at sea (its ship alone, no
## one on deck), one marching, and two villagers crossing water (their fishing boats alone,
## rowing). Saves pictures of them:
##   Godot --path godot --script res://tests/units_view.gd -- <output folder>

const UnitView := preload("res://scripts/unit_view.gd")
const Models := preload("res://scripts/models.gd")
const Characters := preload("res://scripts/characters.gd")
const Adventurers := preload("res://scripts/adventurers.gd")
const Main := preload("res://scripts/main.gd")

## Stands in for the terrain: flat ground, one unit to a tile.
const FLAT := """
extends Node3D
var map_width := 40
var map_height := 40
func tile_position(x: int, y: int) -> Vector3:
	return Vector3(x, 0, y)
func height_at(_x: float, _z: float) -> float:
	return 0.0
"""

var _camera := Camera3D.new()
var _frames := 0
var _armies: Array = []
var _out := ""
var _units: Node3D
var _models := Models.new()


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if not args.is_empty() else ProjectSettings.globalize_path("user://units")
	var stage := Node3D.new()
	root.add_child(stage)
	var main: Node3D = Main.new()
	main._add_lighting()
	for child in main.get_children():
		child.reparent(stage, false)
	main.free()
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(40, 40)
	ground.mesh = plane
	ground.position = Vector3(20, 0, 20)
	var grass := StandardMaterial3D.new()
	grass.albedo_color = Color("#8dbb55")
	ground.material_override = grass
	stage.add_child(ground)
	var sea := MeshInstance3D.new()
	var sea_plane := PlaneMesh.new()
	sea_plane.size = Vector2(6, 6)
	sea.mesh = sea_plane
	sea.position = Vector3(30, 0.01, 20)
	var water := StandardMaterial3D.new()
	water.albedo_color = Color("#3f86c4")
	sea.material_override = water
	stage.add_child(sea)
	var flat_script := GDScript.new()
	flat_script.source_code = FLAT
	flat_script.reload()
	var flat: Node3D = flat_script.new()
	stage.add_child(flat)
	_units = UnitView.new()
	stage.add_child(_units)
	var colors := [Color("#3b78d9"), Color("#d9433b")]
	_units.setup(flat, {"unit_types": {"swordsman": {"name": "Swordsmen"}, "spearman": {"name": "Spearmen"}}},
		colors, Characters.new(), Adventurers.new(), _models)
	# Civ 1 holds a capital at (20, 20); civ 0's army besieges it from (18, 20).
	_units.update_posted([{"id": 1, "settlements": [{"x": 20, "y": 20}], "commanders_in_reserve": []}])
	var general := {"name": "Aldric", "level": 3, "battles": 4, "wins": 3}
	_armies = [
		_army(1, 0, 18, 20, "besieging", general, false),
		_army(2, 0, 30, 20, "marching", {"name": "Edda", "level": 2, "battles": 1, "wins": 1}, true),
		_army(3, 0, 14, 20, "marching", {"name": "Farid", "level": 1, "battles": 0, "wins": 0}, false,
			{"cavalry": 160, "swordsman": 40}, "cavalry"),
		_army(4, 1, 10, 20, "fighting", {"name": "Greta", "level": 2, "battles": 2, "wins": 1}, false,
			{"archer": 150, "spearman": 50}, "archer"),
	]
	_units.update(_armies, _boatmen(22))
	_units.set_detail(2)
	var ship: Node3D = _models.instance("civsim_ship", _models.tinted_material(colors[0]), 2.0)
	ship.position = Vector3(26, 0, 26)
	ship.rotation.y = 2.4
	stage.add_child(ship)
	stage.add_child(_camera)
	_camera.fov = 40
	_camera.make_current()


func _army(id: int, civ: int, x: int, y: int, state: String, commander: Dictionary, afloat: bool,
		units := {"swordsman": 120, "spearman": 60}, dominant := "swordsman") -> Dictionary:
	return {"id": id, "civ": civ, "x": x, "y": y, "role": "field", "state": state, "target_civ": 1,
		"duty": "attack", "units": units, "size": 200, "capacity": 200,
		"rally": null, "dominant": dominant, "afloat": afloat, "boat": afloat, "strength": 200.0,
		"commander": commander, "refit": false, "tier": 1.0, "scouted": true}


## Two villagers afloat, one of each civ, in row `y` of the sea.
func _boatmen(y: int) -> Array:
	return [
		{"id": 1, "civ": 0, "x": 31, "y": y, "task": "gather", "gathers": "food", "at_work": false,
			"mounted": false, "afloat": true},
		{"id": 2, "civ": 1, "x": 29, "y": y, "task": "build", "gathers": null, "at_work": false,
			"mounted": true, "afloat": true},
	]


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames == 2:
		_camera.look_at_from_position(Vector3(17.5, 3.0, 23.2), Vector3(18.3, 0.3, 20))
	elif _frames == 25:
		_save("siege")
		_camera.look_at_from_position(Vector3(30, 2.4, 22.8), Vector3(30, 0.3, 20))
	elif _frames == 35:
		_save("at_sea")
		_camera.look_at_from_position(Vector3(24.4, 1.7, 28.2), Vector3(26, 0.6, 26))
	elif _frames == 45:
		_save("ship")
		_camera.look_at_from_position(Vector3(16.2, 1.0, 21.6), Vector3(14, 0.45, 20))
	elif _frames == 60:
		_save("cavalry")
		_camera.look_at_from_position(Vector3(11.8, 1.1, 22.0), Vector3(10, 0.35, 20))
	elif _frames == 75:
		_save("archers_a")
	elif _frames == 85:
		_save("archers_b")
		_camera.look_at_from_position(Vector3(19.5, 1.1, 22.0), Vector3(18, 0.35, 20))
	elif _frames == 95:
		_save("swing_a")
	elif _frames == 101:
		_save("swing_b")
		_camera.look_at_from_position(Vector3(30.7, 1.2, 23.6), Vector3(30, 0.2, 21.0))
	elif _frames == 108:
		_save("fishing_boats_at_rest")
		_units.update(_armies, _boatmen(21))  # they row a tile on
	elif _frames == 116:
		_save("fishing_boats_rowing_a")
	elif _frames == 124:
		_save("fishing_boats_rowing_b")
		return true
	return false


func _save(name: String) -> void:
	root.get_texture().get_image().save_png(_out.path_join(name + ".png"))
