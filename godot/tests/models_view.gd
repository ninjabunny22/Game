extends SceneTree
## Photographs CivSim's own models made in Blender (art/blender/make_models.py), in two civs'
## colours, beside a pack building for scale:
##   Godot --path godot --script res://tests/models_view.gd -- <output folder>

const Models := preload("res://scripts/models.gd")
const Adventurers := preload("res://scripts/adventurers.gd")
const Characters := preload("res://scripts/characters.gd")
const Main := preload("res://scripts/main.gd")
const MODELS := [["civsim_gold_mine", 1.0], ["civsim_ship", 1.0], ["civsim_harbour", 1.9], ["civsim_stable", 1.9],
	["civsim_catapult", 0.7], ["civsim_ram", 0.8], ["building_home_A_green", 0.78]]

var _camera := Camera3D.new()
var _frames := 0
var _out := ""


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if not args.is_empty() else ProjectSettings.globalize_path("user://models")
	var stage := Node3D.new()
	root.add_child(stage)
	var main: Node3D = Main.new()
	main._add_lighting()
	for child in main.get_children():
		child.reparent(stage, false)
	main.free()
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(40, 20)
	ground.mesh = plane
	var grass := StandardMaterial3D.new()
	grass.albedo_color = Color("#8dbb55")
	ground.material_override = grass
	stage.add_child(ground)
	var models := Models.new()
	for row in 2:
		var color := Color("#3b78d9") if row == 0 else Color("#d9433b")
		for i in MODELS.size():
			var model: Node3D = models.instance(MODELS[i][0], models.tinted_material(color), MODELS[i][1])
			if model == null:
				printerr("MODEL PROBLEM: %s did not load" % MODELS[i][0])
				continue
			model.position = Vector3(-6.0 + i * 2.1, 0, -1.2 + row * 2.4)
			model.rotation.y = 0.5
			stage.add_child(model)
	var adventurers := Adventurers.new()
	var characters := Characters.new()
	var soldier: Node3D = adventurers.instance("Knight:spearman", Color("#3b78d9"), 0.56)
	soldier.position = Vector3(8.6, 0, 0)
	stage.add_child(soldier)
	characters.play(soldier, "idle")
	stage.add_child(_camera)
	_camera.fov = 40
	_camera.make_current()


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames == 2:
		_camera.look_at_from_position(Vector3(1.5, 6.5, 8.5), Vector3(1.5, 0.3, 0))
	elif _frames == 20:
		root.get_texture().get_image().save_png(_out.path_join("models.png"))
		_camera.look_at_from_position(Vector3(-3.5, 2.2, 3.4), Vector3(-3.5, 0.4, 0))
	elif _frames == 30:
		root.get_texture().get_image().save_png(_out.path_join("models_near.png"))
		return true
	return false
