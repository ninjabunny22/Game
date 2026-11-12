extends SceneTree
## Lines up the viewer's figures and new buildings on a plain field, under the game's light,
## and saves pictures of them, for checking scale, colour and animation by eye:
##   Godot --path godot --script res://tests/gallery.gd -- <output folder>
## Row 1: the six generals, each in a different civ's colour. Row 2: the same generals in one
## colour, to see a civ's generals side by side. Row 3: the ranks (sword, spear, archer,
## cavalry, villager). Row 4: buildings going up, and the buildings with props.

const Adventurers := preload("res://scripts/adventurers.gd")
const Characters := preload("res://scripts/characters.gd")
const Models := preload("res://scripts/models.gd")
const Main := preload("res://scripts/main.gd")
const UnitView := preload("res://scripts/unit_view.gd")
const CivView := preload("res://scripts/civ_view.gd")
const COLORS := [Color("#d9433b"), Color("#3b78d9"), Color("#e6c229"), Color("#9a4fd1"), Color("#3fae5a"), Color("#e07b2d")]

var _adventurers := Adventurers.new()
var _characters := Characters.new()
var _models := Models.new()
var _frames := 0
var _out := ""
var _camera := Camera3D.new()
var _walkers: Array[Node3D] = []
var _strikers: Array[Node3D] = []


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	_out = args[0] if not args.is_empty() else ProjectSettings.globalize_path("user://gallery")
	DirAccess.make_dir_recursive_absolute(_out)
	var stage := Node3D.new()
	root.add_child(stage)
	var main: Node3D = Main.new()
	main.set_process(false)
	# Borrow the game's sky, sun and post-processing.
	main._add_lighting()
	for child in main.get_children():
		child.reparent(stage, false)
	main.free()
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(20, 14)
	ground.mesh = plane
	var grass := StandardMaterial3D.new()
	grass.albedo_color = Color("#8dbb55")
	ground.material_override = grass
	stage.add_child(ground)

	for i in Adventurers.GENERALS.size():
		var name: String = Adventurers.GENERALS[i]
		_place(stage, _adventurers.instance(name, COLORS[i], UnitView.GENERAL_HEIGHT), Vector3(-3.0 + i * 1.2, 0, -3.0), "idle")
		_place(stage, _adventurers.instance(name, COLORS[0], UnitView.GENERAL_HEIGHT), Vector3(-3.0 + i * 1.2, 0, -1.6), "walk")
	var ranks := [
		_adventurers.instance("Knight:swordsman", COLORS[1], UnitView.FOOT_HEIGHT),
		_adventurers.instance("Knight:spearman", COLORS[1], UnitView.FOOT_HEIGHT),
		_characters.instance("Archer", COLORS[1], UnitView.ARCHER_HEIGHT),
		_characters.instance("Knight", COLORS[1], UnitView.KNIGHT_HEIGHT),
		_characters.instance("Villager", COLORS[1], UnitView.VILLAGER_HEIGHT),
		_adventurers.instance("Knight", COLORS[1], UnitView.GENERAL_HEIGHT),
	]
	for i in ranks.size():
		_place(stage, ranks[i], Vector3(-3.0 + i * 1.2, 0, -0.2), "attack" if i < 2 else "idle")
	var buildings := [["building_stage_A", 0.85], ["building_stage_B", 0.85], ["building_stage_C", 0.85],
		["building_mine_green", 0.8], ["building_church_green", 0.62], ["building_barracks_green", 0.88],
		["building_tower_catapult_green", 0.8], ["wall_straight_gate", 0.98], ["building_home_A_green", 0.78]]
	for i in buildings.size():
		var model: Node3D = _models.instance(buildings[i][0], _models.tinted_material(COLORS[i % COLORS.size()]), buildings[i][1])
		if model != null:
			model.position = Vector3(-4.8 + i * 1.2, 0, 1.6)
			stage.add_child(model)
		var spec: Dictionary = {}
		for type: String in CivView.BUILDING_MODELS:
			if CivView.BUILDING_MODELS[type].get("model", "") == buildings[i][0] and CivView.BUILDING_MODELS[type].has("props"):
				spec = CivView.BUILDING_MODELS[type]
		for prop: Array in spec.get("props", []):
			var thing: Node3D = _models.instance(prop[0], _models.tinted_material(COLORS[i % COLORS.size()]), float(prop[1]))
			if thing != null:
				thing.position = Vector3(-4.8 + i * 1.2, 0, 1.6) + prop[2]
				stage.add_child(thing)
	stage.add_child(_camera)
	_camera.fov = 40
	_camera.make_current()


func _place(stage: Node3D, figure: Node3D, at: Vector3, animation: String) -> void:
	if figure == null:
		printerr("GALLERY: a figure did not load")
		return
	figure.position = at
	stage.add_child(figure)
	_characters.play(figure, animation)


func _look(from: Vector3, to: Vector3) -> void:
	_camera.look_at_from_position(from, to)


func _process(_delta: float) -> bool:
	_frames += 1
	if _frames == 2:
		_look(Vector3(0, 5.5, 7.5), Vector3(0, 0.3, -0.6))
	elif _frames == 40:
		_save("overview")
		_look(Vector3(-1.2, 1.4, -0.2), Vector3(-1.2, 0.35, -2.4))
	elif _frames == 50:
		_save("generals")
		_look(Vector3(-1.8, 1.3, 1.7), Vector3(-1.8, 0.3, -0.2))
	elif _frames == 60:
		_save("ranks")
		_look(Vector3(-1.2, 2.4, 4.6), Vector3(-1.2, 0.3, 1.6))
	elif _frames == 70:
		_save("buildings")
		return true
	return false


func _save(name: String) -> void:
	var image := root.get_texture().get_image()
	image.save_png(_out.path_join(name + ".png"))
	print("saved ", name)
