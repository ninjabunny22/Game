extends PanelContainer
## The tech tree as the civs are climbing it, for a spectator: one column per era, one box per
## tech linked to what it needs. A dot in a civ's colour on every tech it knows; a frame and a
## progress bar in its colour on the one it is researching now. Resting the mouse on a tech
## says what it does. With a civ picked (its card clicked), the rest of the tree is dimmed to
## that civ's path: what it knows, what it is learning and what it could learn next.
## Everything comes from the simulation: the tree from the init message, each civ's techs and
## research from every tick.

const BOX := Color(0.16, 0.17, 0.2, 0.95)
const BOX_EDGE := Color(1, 1, 1, 0.16)
const LINK := Color(1, 1, 1, 0.18)
const TEXT := Color(0.93, 0.9, 0.84)
const DIM := 0.28  # how far a tech off the picked civ's path fades
const DOT := 4.0

var _eras: Array = []
var _techs: Array = []  # tech dictionaries from the init message
var _by_id := {}  # tech id -> its dictionary
var _rects := {}  # tech id -> Rect2 inside the canvas, set by _layout
var _civs := {}  # civ id -> {"color", "name"}
var _known := {}  # civ id -> {tech id: true}
var _research := {}  # civ id -> {"id", "progress"} or absent
var _picked := -1  # the civ whose path is shown, or -1
var _canvas := Control.new()
var _title := Label.new()


func _ready() -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.09, 0.11, 0.98)
	style.set_corner_radius_all(10)
	style.set_content_margin_all(12)
	add_theme_stylebox_override("panel", style)
	var column := VBoxContainer.new()
	add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	_title.text = "Tech tree"
	_title.add_theme_font_size_override("font_size", 18)
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(_title)
	var close := Button.new()
	close.icon = load("res://assets/icons/close.svg")
	close.expand_icon = true
	close.custom_minimum_size = Vector2(30, 30)
	close.focus_mode = Control.FOCUS_NONE
	close.flat = true
	close.tooltip_text = "Close"
	close.pressed.connect(func() -> void: visible = false)
	header.add_child(close)
	_canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_canvas.custom_minimum_size = Vector2(320, 220)
	_canvas.mouse_filter = Control.MOUSE_FILTER_PASS
	_canvas.tooltip_text = " "  # tooltips on: the text comes from _tooltip_at
	_canvas.draw.connect(_draw_tree)
	_canvas.resized.connect(_layout)
	column.add_child(_canvas)
	_canvas.gui_input.connect(func(_event: InputEvent) -> void:
		_canvas.tooltip_text = _tooltip_at(_canvas.get_local_mouse_position()))
	visible = false


func setup(init: Dictionary) -> void:
	_eras = init["tech_tree"]["eras"]
	_techs = init["tech_tree"]["techs"]
	_by_id.clear()
	for tech: Dictionary in _techs:
		_by_id[tech["id"]] = tech
	_civs.clear()
	for civ: Dictionary in init["civs"]:
		_civs[int(civ["id"])] = {"color": Color.html(civ["color"]), "name": civ["name"]}
	_picked = -1
	_layout()


func update(data: Dictionary) -> void:
	_known.clear()
	_research.clear()
	for civ: Dictionary in data["civs"]:
		var civ_id := int(civ["id"])
		var known := {}
		for tech_id: Variant in civ.get("techs", []):
			known[tech_id] = true
		_known[civ_id] = known
		if civ.get("research") != null and civ.get("alive", true):
			_research[civ_id] = civ["research"]
	if visible:
		_canvas.queue_redraw()


## Show the path of one civ (its card was clicked), or of none with -1.
func pick(civ_id: int) -> void:
	_picked = civ_id
	_title.text = "Tech tree" if civ_id < 0 or not _civs.has(civ_id) else "Tech tree: %s's path" % _civs[civ_id]["name"]
	_canvas.queue_redraw()


func toggle() -> void:
	visible = not visible
	if visible:
		move_to_front()  # over the cards and the minimap while it is open
		_layout()


func _layout() -> void:
	_rects.clear()
	if _eras.is_empty():
		return
	var area := _canvas.size
	var columns := _eras.size()
	var col_w := area.x / columns
	var per_era := {}
	for tech: Dictionary in _techs:
		var era := int(tech["era"])
		if not per_era.has(era):
			per_era[era] = []
		per_era[era].append(tech)
	var rows := 1
	for era: int in per_era:
		rows = maxi(rows, per_era[era].size())
	var row_h := (area.y - 26.0) / rows
	for era: int in per_era:
		var list: Array = per_era[era]
		var top := 26.0 + (area.y - 26.0 - row_h * list.size()) * 0.5  # each column centred
		for i in list.size():
			var rect := Rect2(era * col_w + 6.0, top + i * row_h + 2.0, col_w - 18.0, row_h - 4.0)
			_rects[list[i]["id"]] = rect
	_canvas.queue_redraw()


func _draw_tree() -> void:
	if _rects.is_empty():
		return
	var font := get_theme_default_font()
	var col_w := _canvas.size.x / maxi(1, _eras.size())
	for era in _eras.size():
		_canvas.draw_string(font, Vector2(era * col_w + 6.0, 16.0), str(_eras[era]), HORIZONTAL_ALIGNMENT_LEFT,
			col_w - 12.0, 13, Color(TEXT, 0.7))
	var path := _path(_picked)
	# Links first, under the boxes: from each prerequisite's right edge to the tech's left.
	for tech: Dictionary in _techs:
		var rect: Rect2 = _rects[tech["id"]]
		for need: Variant in tech["prereqs"]:
			if not _rects.has(need):
				continue
			var from: Rect2 = _rects[need]
			var a := Vector2(from.end.x, from.get_center().y)
			var b := Vector2(rect.position.x, rect.get_center().y)
			if a.x > b.x:  # within one era: join the sides facing each other
				a = Vector2(from.position.x + 4.0, from.get_center().y)
				b = Vector2(rect.position.x + 4.0, rect.get_center().y)
			var faded := _picked >= 0 and not (path.has(tech["id"]) and path.has(need))
			_canvas.draw_line(a, b, Color(LINK, LINK.a * (DIM if faded else 1.0)), 1.0, true)
	for tech: Dictionary in _techs:
		var tech_id: String = tech["id"]
		var rect: Rect2 = _rects[tech_id]
		var fade := 1.0 if _picked < 0 or path.has(tech_id) else DIM
		_canvas.draw_rect(rect, Color(BOX, BOX.a * fade))
		_canvas.draw_rect(rect, Color(BOX_EDGE, BOX_EDGE.a * fade), false, 1.0)
		var size := clampi(int(rect.size.y * 0.42), 9, 13)
		_canvas.draw_string(font, rect.position + Vector2(5, rect.size.y * 0.5 + size * 0.38), str(tech["name"]),
			HORIZONTAL_ALIGNMENT_LEFT, rect.size.x - 10 - DOT * 2.4 * 2, size, Color(TEXT, fade))
		# Who knows it: a dot each, along the right edge.
		var dot := 0
		for civ_id: int in _civs:
			if _known.get(civ_id, {}).has(tech_id):
				var at := Vector2(rect.end.x - DOT - 2 - (dot % 3) * (DOT * 2 + 1), rect.position.y + DOT + 2 + (dot / 3) * (DOT * 2 + 1))
				_canvas.draw_circle(at, DOT, Color(_civs[civ_id]["color"], fade))
				dot += 1
		# Who is learning it now: a frame and a bar of its progress, one strip per civ.
		var strip := 0
		for civ_id: int in _research:
			if _research[civ_id]["id"] != tech_id:
				continue
			var color: Color = _civs[civ_id]["color"]
			_canvas.draw_rect(rect.grow(-1.0 - strip * 2.0), Color(color, fade), false, 2.0)
			var bar := Rect2(rect.position.x + 2, rect.end.y - 4 - strip * 4, (rect.size.x - 4) * float(_research[civ_id]["progress"]), 3)
			_canvas.draw_rect(bar, Color(color, fade))
			strip += 1


## A civ's path: what it knows, what it is learning, and what it could start next. Empty for -1.
func _path(civ_id: int) -> Dictionary:
	var path := {}
	if civ_id < 0:
		return path
	var known: Dictionary = _known.get(civ_id, {})
	for tech: Dictionary in _techs:
		var tech_id: String = tech["id"]
		if known.has(tech_id):
			path[tech_id] = true
			continue
		var ready := true
		for need: Variant in tech["prereqs"]:
			if not known.has(need):
				ready = false
		if ready:
			path[tech_id] = true
	if _research.has(civ_id):
		path[_research[civ_id]["id"]] = true
	return path


func _tooltip_at(at: Vector2) -> String:
	for tech_id: String in _rects:
		if (_rects[tech_id] as Rect2).has_point(at):
			var tech: Dictionary = _by_id[tech_id]
			var lines: Array[String] = [str(tech["name"]), str(tech.get("description", ""))]
			var cost: Dictionary = tech.get("cost", {})
			if not cost.is_empty():
				var parts: Array[String] = []
				for res: String in cost:
					parts.append("%d %s" % [int(cost[res]), res])
				lines.append("Costs " + ", ".join(parts))
			var who: Array[String] = []
			for civ_id: int in _civs:
				if _known.get(civ_id, {}).has(tech_id):
					who.append(str(_civs[civ_id]["name"]))
			lines.append("Known to " + (", ".join(who) if not who.is_empty() else "nobody yet"))
			for civ_id: int in _research:
				if _research[civ_id]["id"] == tech_id:
					lines.append("%s is learning it (%d%%)" % [_civs[civ_id]["name"], int(float(_research[civ_id]["progress"]) * 100.0)])
			return "\n".join(lines)
	return ""
