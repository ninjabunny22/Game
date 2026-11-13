extends Control
## Fights as a spectator follows them: a box floating over each battle, siege or assault on a
## native capital that is on screen, and a crossed-swords alert when none is.
##
## The box: a headline ("General Aldric (Zhanlu) assaults Cragford with 180 soldiers"), a bar
## per side (soldiers left of what it started with, in its colour, with today's losses), for a
## siege a breach bar and then a "held N / 60 days" bar, and the last notes of the fight.
## From afar a fight is only a small crossed-swords marker: clicking it opens its box. A box
## stays a few seconds once its fight is over, showing how it ended.
## Everything here comes from the simulation's "engagements", sent only while spectating.

signal jump_requested(x: float, y: float)  # the alert was clicked: look at this fight

const BOX_WIDTH := 300.0
const MAX_BOXES := 4  # at most this many boxes at once: those nearest the screen's centre
const LIFT := 1.6  # how high over the fight its box floats, in world units
const MARKER := 13.0  # half the crossed-swords marker's size, in pixels
const NATIVE := Color(0.61, 0.56, 0.48)
const INK := Color(0.95, 0.92, 0.86)
const MUTED := Color(0.62, 0.65, 0.7)
const PANEL := Color(0.08, 0.09, 0.11, 0.86)

var _terrain: Node3D
var _civ_colors: Array = []
var _engagements: Array = []  # from the latest tick
var _opened := {}  # engagement id -> true: opened from afar by clicking its marker
var _detail := 0  # 0 whole-map view, 1 closer, 2 full detail (as unit_view)
var _alert: Button
var _next := 0  # which fight the alert takes the camera to next
var _swords: Texture2D = load("res://assets/icons/battle.svg")
var _boxes: Array = []  # [engagement, screen point] drawn this frame
var _markers: Array = []  # [engagement, screen point] drawn as markers this frame


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_alert = Button.new()
	_alert.icon = _swords
	_alert.add_theme_constant_override("icon_max_width", 26)
	_alert.focus_mode = Control.FOCUS_NONE
	_alert.add_theme_font_size_override("font_size", 18)
	_alert.custom_minimum_size = Vector2(86, 40)
	_alert.anchor_left = 0.5
	_alert.anchor_right = 0.5
	_alert.offset_left = -43
	_alert.offset_right = 43
	_alert.offset_top = 62  # just under the top bar
	_alert.tooltip_text = "Fights under way out of sight: click to go to one (again for the next)"
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.45, 0.12, 0.1, 0.9)
	style.set_corner_radius_all(9)
	style.set_content_margin_all(6)
	_alert.add_theme_stylebox_override("normal", style)
	var hover := style.duplicate()
	hover.bg_color = Color(0.6, 0.16, 0.12, 0.95)
	_alert.add_theme_stylebox_override("hover", hover)
	_alert.add_theme_stylebox_override("pressed", hover)
	_alert.pressed.connect(_go_to_next)
	_alert.visible = false
	add_child(_alert)


func setup(terrain: Node3D, civ_colors: Array) -> void:
	_terrain = terrain
	_civ_colors = civ_colors
	_engagements = []
	_opened.clear()


func set_detail(detail: int) -> void:
	_detail = detail


func update(data: Dictionary) -> void:
	_engagements = data.get("engagements", [])
	var alive := {}
	for fight: Dictionary in _engagements:
		alive[fight["id"]] = true
	for id: Variant in _opened.keys():
		if not alive.has(id):
			_opened.erase(id)


## A click on the map: on a fight's marker it opens that fight's box. True if it was used.
func click(at: Vector2) -> bool:
	for pair: Array in _markers:
		if (pair[1] as Vector2).distance_to(at) <= MARKER + 4:
			_opened[pair[0]["id"]] = true
			return true
	return false


func _process(_delta: float) -> void:
	# Over the whole screen, whatever its size (a child of the overlay's layer, not of a Control).
	position = Vector2.ZERO
	size = get_viewport_rect().size
	queue_redraw()


func _draw() -> void:
	_boxes.clear()
	_markers.clear()
	var camera := get_viewport().get_camera_3d()
	if camera == null or _terrain == null:
		_alert.visible = false
		return
	var screen := get_viewport_rect()
	var centre := screen.size * 0.5
	var shown: Array = []
	for fight: Dictionary in _engagements:
		var world: Vector3 = _terrain.tile_position(int(fight["x"]), int(fight["y"])) + Vector3(0, LIFT, 0)
		if camera.is_position_behind(world):
			continue
		var at := camera.unproject_position(world)
		if not screen.grow(-20).has_point(at):
			continue
		shown.append([fight, at])
	_alert.visible = shown.is_empty() and _engagements.any(func(f: Dictionary) -> bool: return not f.get("over", false))
	if _alert.visible:
		var live := _engagements.filter(func(f: Dictionary) -> bool: return not f.get("over", false))
		_alert.text = " %d" % live.size()
	shown.sort_custom(func(a: Array, b: Array) -> bool:
		return (a[1] as Vector2).distance_squared_to(centre) < (b[1] as Vector2).distance_squared_to(centre))
	var boxes := 0
	for pair: Array in shown:
		var fight: Dictionary = pair[0]
		if (_detail >= 1 or _opened.has(fight["id"])) and boxes < MAX_BOXES:
			_draw_box(fight, pair[1])
			boxes += 1
		else:
			_draw_marker(fight, pair[1])


func _draw_marker(fight: Dictionary, at: Vector2) -> void:
	_markers.append([fight, at])
	draw_circle(at, MARKER + 3, Color(0.45, 0.12, 0.1, 0.85))
	draw_texture_rect(_swords, Rect2(at - Vector2(MARKER, MARKER), Vector2(MARKER, MARKER) * 2), false)


func _draw_box(fight: Dictionary, at: Vector2) -> void:
	var font := get_theme_default_font()
	var width := BOX_WIDTH - 20.0
	var sides: Array = fight.get("sides", [])
	var notes: Array = fight.get("notes", [])
	var siege: Variant = fight.get("siege")
	var para := TextParagraph.new()  # the headline, wrapped to the box
	para.width = width
	para.add_string(str(fight.get("headline", "")), font, 14)
	var height := 8.0 + para.get_size().y + 6.0 + sides.size() * 34.0 + (36.0 if siege != null else 0.0) \
		+ mini(3, notes.size()) * 17.0 + 6.0
	var rect := Rect2(at - Vector2(BOX_WIDTH * 0.5, height + 10.0), Vector2(BOX_WIDTH, height))
	var screen := get_viewport_rect().grow(-8)
	rect.position.x = clampf(rect.position.x, screen.position.x, screen.end.x - rect.size.x)
	rect.position.y = clampf(rect.position.y, screen.position.y + 60.0, screen.end.y - rect.size.y)
	var fade := 0.55 if fight.get("over", false) else 1.0
	draw_rect(rect, Color(PANEL, PANEL.a * fade))
	draw_rect(rect, Color(1, 1, 1, 0.12 * fade), false, 1.0)
	draw_line(Vector2(at.x, rect.end.y), at, Color(1, 1, 1, 0.35 * fade), 1.5)
	var x := rect.position.x + 10.0
	var y := rect.position.y + 8.0
	para.draw(get_canvas_item(), Vector2(x, y), Color(INK, fade))
	y += para.get_size().y + 6.0
	# One bar per side: what is left of what it brought.
	for side: Dictionary in sides:
		var color := _side_color(side)
		var start := maxf(1.0, float(side.get("start", 1)))
		var now := float(side.get("soldiers", 0))
		var label := "%s  %d" % [str(side.get("label", side.get("name", ""))), int(now)]
		var today := int(side.get("lost_today", 0))
		draw_string(font, Vector2(x, y + 12), label, HORIZONTAL_ALIGNMENT_LEFT, width - 70, 12, Color(INK, fade))
		if today > 0:
			draw_string(font, Vector2(x + width - 66, y + 12), "-%d today" % today, HORIZONTAL_ALIGNMENT_RIGHT, 66, 12,
				Color(0.95, 0.5, 0.45, fade))
		var bar := Rect2(x, y + 17, width, 8)
		draw_rect(bar, Color(1, 1, 1, 0.08 * fade))
		draw_rect(Rect2(bar.position, Vector2(width * clampf(now / start, 0.0, 1.0), 8)), Color(color, fade))
		y += 34.0
	# A siege: the walls, then the hold.
	if siege != null:
		var breach := clampf(float(siege.get("breach", 0.0)), 0.0, 1.0)
		var held := int(siege.get("held", 0))
		var needed := maxi(1, int(siege.get("needed", 100)))
		var text := "Breaching the walls: %d%%" % int(breach * 100.0) if held == 0 and breach < 1.0 \
			else "Holding the castle: %d / %d days" % [held, needed]
		var share := breach if held == 0 and breach < 1.0 else float(held) / needed
		draw_string(font, Vector2(x, y + 12), text, HORIZONTAL_ALIGNMENT_LEFT, width, 12, Color(MUTED, fade))
		var bar := Rect2(x, y + 17, width, 8)
		draw_rect(bar, Color(1, 1, 1, 0.08 * fade))
		draw_rect(Rect2(bar.position, Vector2(width * share, 8)), Color(0.91, 0.72, 0.29, fade))
		y += 36.0
	# The last few things that happened, newest last.
	for note: Variant in notes.slice(maxi(0, notes.size() - 3)):
		draw_string(font, Vector2(x, y + 12), str(note), HORIZONTAL_ALIGNMENT_LEFT, width, 11, Color(MUTED, fade))
		y += 17.0
	_boxes.append([fight, at])


func _side_color(side: Dictionary) -> Color:
	var civ: Variant = side.get("civ")
	if civ == null or int(civ) < 0 or int(civ) >= _civ_colors.size():
		return NATIVE
	return _civ_colors[int(civ)]


func _go_to_next() -> void:
	var live := _engagements.filter(func(f: Dictionary) -> bool: return not f.get("over", false))
	if live.is_empty():
		return
	# Largest first, then on to the next with each click.
	live.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return int(a.get("size", 0)) > int(b.get("size", 0)))
	var fight: Dictionary = live[_next % live.size()]
	_next += 1
	jump_requested.emit(float(fight["x"]), float(fight["y"]))
