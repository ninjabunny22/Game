extends SceneTree
## Photographs a civ's main castle and a town castle from above and from the side, at the
## size the viewer draws them, to check what stands inside the walls:
##   Godot --path godot --script res://tests/castle_view.gd -- <output folder>

const Characters := preload("res://scripts/characters.gd")
const Main := preload("res://scripts/main.gd")
const CivView := preload("res://scripts/civ_view.gd")

var _characters := Characters.new()
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
	plane.size = Vector2(30, 30)
	ground.mesh = plane
	var grass := StandardMaterial3D.new()
	grass.albedo_color = Color("#8dbb55")
	ground.material_override = grass
	_stage.add_child(ground)
	var main_castle: Node3D = _characters.instance(CivView.CAPITAL_SCENE, Color("#3b78d9"), 0.0, CivView.CAPITAL_FOOTPRINT)
	_stage.add_child(main_castle)
	var town: Node3D = _characters.instance(CivView.TOWN_SCENE, Color("#d9433b"), 0.0, CivView.TOWN_FOOTPRINT)
	town.position = Vector3(6, 0, 0)
	_stage.add_child(town)
	if _stage.has_method("add_castle_contents"):
		pass
	_stage.add_child(_camera)
	_camera.fov = 40
	_camera.make_current()


func extra(node: Node3D) -> void:
	_stage.add_child(node)


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames == 2:
		_camera.look_at_from_position(Vector3(0, 7, 0.01), Vector3.ZERO)
	elif _frames == 20:
		_save("main_top")
		_camera.look_at_from_position(Vector3(0, 3.2, 4.6), Vector3(0, 0.3, 0))
	elif _frames == 30:
		_save("main_side")
		_camera.look_at_from_position(Vector3(6, 6, 0.01), Vector3(6, 0, 0))
	elif _frames == 40:
		_save("town_top")
		return true
	return false


func _save(name: String) -> void:
	root.get_texture().get_image().save_png(_out.path_join(name + ".png"))
