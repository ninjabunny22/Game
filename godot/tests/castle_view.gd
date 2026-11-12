extends SceneTree
## Photographs the castles at every stage of their growth, a civ's own and a town, from
## above and from the side, to check how the pieces fit:
##   Godot --path godot --script res://tests/castle_view.gd -- <output folder>

const Models := preload("res://scripts/models.gd")
const Main := preload("res://scripts/main.gd")
const CivView := preload("res://scripts/civ_view.gd")

var _camera := Camera3D.new()
var _frames := 0
var _out := ""
var _stage := Node3D.new()


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if not args.is_empty() else ProjectSettings.globalize_path("user://castle")
	root.add_child(_stage)
	var main: Node3D = Main.new()
	main._add_lighting()
	for child in main.get_children():
		child.reparent(_stage, false)
	main.free()
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(60, 30)
	ground.mesh = plane
	var grass := StandardMaterial3D.new()
	grass.albedo_color = Color("#8dbb55")
	ground.material_override = grass
	_stage.add_child(ground)
	var view: Node3D = CivView.new()
	view._models = Models.new()
	view._civ_colors = [Color("#3b78d9")]
	for level in 7:  # a civ's own castle at every level along the front row, a town behind
		var castle := Node3D.new()
		castle.position = Vector3(-15.0 + level * 5.0, 0, 0)
		view._compose_castle(castle, Color("#3b78d9"), true, level)
		view._show_hospital(castle, ["field_medicine", "surgeons"] if level >= 3 else [], Color("#3b78d9"), true)
		_stage.add_child(castle)
		var town := Node3D.new()
		town.position = Vector3(-15.0 + level * 5.0, 0, -5.5)
		view._compose_castle(town, Color("#d9433b"), false, level)
		_stage.add_child(town)
	_stage.add_child(_camera)
	_camera.fov = 40
	_camera.make_current()


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames == 2:
		_camera.look_at_from_position(Vector3(0, 16, 14), Vector3(0, 0, -2.5))
	elif _frames == 20:
		_save("all")
		_camera.look_at_from_position(Vector3(15, 4.5, 5.2), Vector3(15, 0.4, 0))
	elif _frames == 30:
		_save("main_late")
		_camera.look_at_from_position(Vector3(15, 7.5, 0.01), Vector3(15, 0, 0))
	elif _frames == 40:
		_save("main_late_top")
		_camera.look_at_from_position(Vector3(-5, 4.5, 5.2), Vector3(-5, 0.4, 0))
	elif _frames == 50:
		_save("main_early")
		return true
	return false


func _save(name: String) -> void:
	root.get_texture().get_image().save_png(_out.path_join(name + ".png"))
