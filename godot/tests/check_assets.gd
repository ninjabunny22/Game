extends SceneTree
## Loads every model the viewer uses and checks it works, without opening a window:
##   Godot --headless --path godot --script res://tests/check_assets.gd
## Prints one line per problem and "assets ok" at the end; exits with 1 if anything failed.

const Adventurers := preload("res://scripts/adventurers.gd")
const Characters := preload("res://scripts/characters.gd")
const Models := preload("res://scripts/models.gd")
const CivView := preload("res://scripts/civ_view.gd")
const UnitView := preload("res://scripts/unit_view.gd")

var _problems := 0


func _init() -> void:
	var adventurers := Adventurers.new()
	var characters := Characters.new()
	var models := Models.new()
	var red := Color(0.85, 0.26, 0.23)
	var blue := Color(0.2, 0.4, 0.85)

	# Generals and foot soldiers from the Adventurers pack.
	var kinds: Array = Adventurers.GENERALS.duplicate()
	kinds += ["Knight:swordsman", "Knight:spearman"]
	for kind: String in kinds:
		var figure: Node3D = adventurers.instance(kind, red, 0.8)
		if figure == null:
			_fail("%s did not load" % kind)
			continue
		for animation: String in ["idle", "walk", "attack"]:
			if not characters.can_play(figure, animation):
				_fail("%s has no %s animation" % [kind, animation])
		var player: AnimationPlayer = figure.get_meta("player")
		var skeleton: Skeleton3D = figure.find_children("*", "Skeleton3D", true, false)[0]
		# The animation tracks must reach the skeleton: play one and see the bones move.
		root.add_child(figure)
		var leg := skeleton.find_bone("upperleg.l")
		player.play("walk")
		player.seek(0.1, true)
		var early := skeleton.get_bone_pose_rotation(leg)
		player.seek(0.5, true)
		if skeleton.get_bone_pose_rotation(leg).is_equal_approx(early):
			_fail("%s: the walk animation does not move its legs" % kind)
		var height: float = figure.get_meta("height")
		if absf(height - 0.8) > 0.01:
			_fail("%s stands %.2f tall, not 0.8" % [kind, height])
		var held := figure.find_children("*", "BoneAttachment3D", true, false).size()
		var kit: Dictionary = Adventurers.KITS.get(kind, {})
		var wanted := kit.values().filter(func(w: String) -> bool: return w != "").size()
		if held != wanted:
			_fail("%s holds %d weapons, not %d" % [kind, held, wanted])
		figure.free()

	# Team colour: two civs get different team cells, and the skin stays the same.
	for texture: String in Adventurers.TEAM_CELLS:
		var one: Image = (adventurers._material(texture, red).albedo_texture as ImageTexture).get_image()
		var two: Image = (adventurers._material(texture, blue).albedo_texture as ImageTexture).get_image()
		var cell: Vector2i = Adventurers.TEAM_CELLS[texture][0]
		var at := Vector2i(cell.x * 128 + 64, cell.y * 256 + 128)
		if one.get_pixelv(at).is_equal_approx(two.get_pixelv(at)):
			_fail("%s: the team colour does not change with the civ" % texture)
		if not one.get_pixel(64, 128).is_equal_approx(two.get_pixel(64, 128)):
			_fail("%s: the skin changes with the civ" % texture)

	# Our own characters and the pack's buildings and nature.
	for model: String in ["Archer", "Knight", "Rider", "Villager"]:
		if not characters.has(model):
			_fail("%s did not load" % model)
	var names := {}
	for spec: Dictionary in CivView.BUILDING_MODELS.values():
		for key in ["model", "alt"]:
			if spec.has(key) and not spec.has("scene"):
				names[spec[key]] = true
	for name: String in CivView.EXTRA_MODELS:
		names[name] = true
	for name: String in names:
		if models.parts(name, 1.0).is_empty():
			_fail("%s did not load" % name)

	print("assets ok" if _problems == 0 else "%d asset problem(s)" % _problems)
	quit(1 if _problems else 0)


func _fail(text: String) -> void:
	_problems += 1
	printerr("ASSET PROBLEM: " + text)
