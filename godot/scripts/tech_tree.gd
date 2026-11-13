extends PanelContainer
## The tech tree as the civs are climbing it, for a spectator: one column per era, one box per
## tech linked to what it needs. A dot in a civ's colour on every tech it knows; a frame and a
## progress bar in its colour on the one it is researching now. Resting the mouse on a tech
## says what it does. With a civ picked (its card clicked), the rest of the tree is dimmed to
## that civ's path: what it knows, what it is learning and what it could learn next.
## Everything comes from the simulation: the tree from the init message, each civ's techs and
## research from every tick.

const BOX := Color(0.15, 0.16, 0.19, 1.0)
const BOX_KNOWN := Color(0.2, 0.22, 0.26, 1.0)  # a tech somebody knows stands out a little
const BOX_EDGE := Color(1, 1, 1, 0.12)
const BAND := Color(1, 1, 1, 0.025)
const LINK := Color(1, 1, 1, 0.12)
const LINK_LIT := Color(0.95, 0.85, 0.6, 0.35)  # a link into a tech somebody knows
const TEXT := Color(0.93, 0.9, 0.84)
const DIM := 0.28  # how far a tech off the picked civ's path fades
const DOT := 3.5
const ROMAN := ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
## What a tech is for, by its effects: [effect keys, stripe colour, legend name].
const KINDS := {
	"army": [["military", "tier", "casualties", "capture_speed", "defense", "mobilization", "soldier_cost",
		"commander_xp", "commander_start", "officer_appointment", "beds", "home_speed", "reinforce"],
		Color(0.86, 0.36, 0.33), "Army"],
	"water": [["water_mult", "water_use", "purification"], Color(0.3, 0.72, 0.8), "Water"],
	"travel": [["boats", "bridges", "boat_range", "villager_speed"], Color(0.9, 0.7, 0.3), "Travel"],
	"learning": [["science_mult"], Color(0.45, 0.6, 0.95), "Learning"],
	"economy": [[], Color(0.45, 0.78, 0.42), "Economy"],
}

var _eras: Array = []
var _techs: Array = []  # tech dictionaries from the init message
var _by_id := {}  # tech id -> its dictionary
var _rects := {}  # tech id -> Rect2 inside the canvas, set by _layout
var _civs := {}  # civ id -> {"color", "name"}
var _hover: PanelContainer
var _hover_text: RichTextLabel
var _known := {}  # civ id -> {tech id: true}
var _research := {}  # civ id -> {"id", "progress"} or absent
var _picked := -1  # the civ whose path is shown, or -1
var _canvas := Control.new()
var _title := Label.new()


func _ready() -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.09, 0.11, 1.0)
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
	for kind: String in KINDS:  # the legend for the stripes
		var chip := ColorRect.new()
		chip.color = KINDS[kind][1]
		chip.custom_minimum_size = Vector2(10, 10)
		chip.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		header.add_child(chip)
		var label := Label.new()
		label.text = KINDS[kind][2] + "   "
		label.add_theme_font_size_override("font_size", 13)
		label.modulate = Color(1, 1, 1, 0.75)
		header.add_child(label)
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
	_canvas.draw.connect(_draw_tree)
	_canvas.resized.connect(_layout)
	column.add_child(_canvas)
	_canvas.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseMotion:
			_show_hover(_canvas.get_local_mouse_position()))
	_canvas.mouse_exited.connect(func() -> void: _hover.visible = false)
	# The hover card: what the tech under the mouse does, exactly, and who has it.
	_hover = PanelContainer.new()
	var card := StyleBoxFlat.new()
	card.bg_color = Color(0.05, 0.06, 0.08, 0.96)
	card.set_corner_radius_all(8)
	card.set_content_margin_all(10)
	card.set_border_width_all(1)
	card.border_color = Color(1, 1, 1, 0.15)
	_hover.add_theme_stylebox_override("panel", card)
	_hover.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hover.visible = false
	_hover_text = RichTextLabel.new()
	_hover_text.bbcode_enabled = true
	_hover_text.fit_content = true
	_hover_text.scroll_active = false
	_hover_text.custom_minimum_size = Vector2(300, 0)
	_hover_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hover_text.add_theme_font_size_override("normal_font_size", 13)
	_hover_text.add_theme_font_size_override("bold_font_size", 15)
	_hover.add_child(_hover_text)
	var layer := Control.new()  # free of the panel's layout, so the card goes where the mouse is
	layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(layer)
	layer.add_child(_hover)
	visible = false


func add_civ(civ: Dictionary) -> void:
	_civs[int(civ["id"])] = {"color": Color.html(civ["color"]), "name": civ["name"]}


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
		if get_index() < get_parent().get_child_count() - 1:
			move_to_front()  # stay over the minimap and panels added after it opened
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
	# Era bands: every other column a shade lighter, each headed by its number and name.
	for era in _eras.size():
		if era % 2 == 0:
			_canvas.draw_rect(Rect2(era * col_w, 0.0, col_w - 6.0, _canvas.size.y), BAND)
		var head := "%s  %s" % [ROMAN[mini(era, ROMAN.size() - 1)], str(_eras[era])]
		_canvas.draw_string(font, Vector2(era * col_w, 17.0), head, HORIZONTAL_ALIGNMENT_CENTER,
			col_w - 6.0, 13, Color(TEXT, 0.75))
	var path := _path(_picked)
	# Links first, under the boxes: a soft curve from each prerequisite's right edge to the tech's left.
	for tech: Dictionary in _techs:
		var rect: Rect2 = _rects[tech["id"]]
		var lit := _known_by_any(tech["id"])
		for need: Variant in tech["prereqs"]:
			if not _rects.has(need):
				continue
			var from: Rect2 = _rects[need]
			var a := Vector2(from.end.x, from.get_center().y)
			var b := Vector2(rect.position.x, rect.get_center().y)
			var faded := _picked >= 0 and not (path.has(tech["id"]) and path.has(need))
			var color := Color(LINK_LIT if lit else LINK, (LINK_LIT.a if lit else LINK.a) * (DIM if faded else 1.0))
			if a.x > b.x:  # within one era: a loop out to the left between the two
				a = Vector2(from.position.x, from.get_center().y)
				_canvas.draw_polyline(_curve(a, b, -14.0), color, 1.2, true)
			else:
				_canvas.draw_polyline(_curve(a, b, (b.x - a.x) * 0.5), color, 1.2, true)
	for tech: Dictionary in _techs:
		var tech_id: String = tech["id"]
		var rect: Rect2 = _rects[tech_id]
		var fade := 1.0 if _picked < 0 or path.has(tech_id) else DIM
		var known := _known_by_any(tech_id)
		var box := StyleBoxFlat.new()
		box.bg_color = Color(BOX_KNOWN if known else BOX, BOX.a * fade)
		box.set_corner_radius_all(6)
		box.set_border_width_all(1)
		box.border_color = Color(BOX_EDGE, BOX_EDGE.a * fade)
		box.anti_aliasing = true
		_canvas.draw_style_box(box, rect)
		# A stripe down the left in the colour of what the tech is for.
		var stripe := StyleBoxFlat.new()
		stripe.bg_color = Color(KINDS[_kind(tech)][1], 0.9 * fade)
		stripe.corner_radius_top_left = 6
		stripe.corner_radius_bottom_left = 6
		_canvas.draw_style_box(stripe, Rect2(rect.position, Vector2(4.0, rect.size.y)))
		_draw_name(font, str(tech["name"]), rect, Color(TEXT, fade if known or _picked >= 0 else 0.8 * fade))
		# Who knows it: a dot each, in a row along the bottom right.
		var dot := 0
		for civ_id: int in _civs:
			if _known.get(civ_id, {}).has(tech_id):
				var at := Vector2(rect.end.x - DOT - 5.0 - dot * (DOT * 2 + 2), rect.end.y - DOT - 5.0)
				_canvas.draw_circle(at, DOT + 1.0, Color(0, 0, 0, 0.5 * fade))
				_canvas.draw_circle(at, DOT, Color(_civs[civ_id]["color"], fade))
				dot += 1
		# Who is learning it now: a frame and a bar of its progress, one strip per civ.
		var strip := 0
		for civ_id: int in _research:
			if _research[civ_id]["id"] != tech_id:
				continue
			var color: Color = _civs[civ_id]["color"]
			var frame := StyleBoxFlat.new()
			frame.draw_center = false
			frame.set_corner_radius_all(6)
			frame.set_border_width_all(2)
			frame.border_color = Color(color, fade)
			_canvas.draw_style_box(frame, rect.grow(-strip * 2.0))
			var bar := Rect2(rect.position.x + 8, rect.end.y - 5 - strip * 4, (rect.size.x - 16) * float(_research[civ_id]["progress"]), 3)
			_canvas.draw_rect(bar, Color(color, fade))
			strip += 1


## A tech's name in its box: as large as fits, on two lines if it must, never cut short.
func _draw_name(font: Font, title: String, rect: Rect2, color: Color) -> void:
	var room := rect.size.x - 16.0
	var top := rect.position.y + rect.size.y * 0.42
	for size in range(clampi(int(rect.size.y * 0.3), 11, 15), 10, -1):
		if font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x <= room:
			_canvas.draw_string(font, Vector2(rect.position.x + 10.0, top + size * 0.38), title,
				HORIZONTAL_ALIGNMENT_LEFT, room, size, color)
			return
	var words := title.split(" ")
	var cut := maxi(1, words.size() / 2)
	var lines := [" ".join(words.slice(0, cut)), " ".join(words.slice(cut))]
	for i in 2:
		_canvas.draw_string(font, Vector2(rect.position.x + 10.0, top + (i - 0.5) * 13.0 + 4.0), lines[i],
			HORIZONTAL_ALIGNMENT_LEFT, room, 12, color)


## A smooth curve from a to b, leaving and arriving level, bowed `reach` pixels sideways.
func _curve(a: Vector2, b: Vector2, reach: float) -> PackedVector2Array:
	var points := PackedVector2Array()
	var c1 := a + Vector2(reach, 0.0)
	var c2 := b - Vector2(absf(reach) if reach < 0.0 else reach, 0.0)
	for i in 17:
		var t := i / 16.0
		var u := 1.0 - t
		points.append(a * u * u * u + c1 * 3.0 * u * u * t + c2 * 3.0 * u * t * t + b * t * t * t)
	return points


func _known_by_any(tech_id: String) -> bool:
	for civ_id: int in _known:
		if _known[civ_id].has(tech_id):
			return true
	return false


## What a tech is mainly for, from its effects: army, water, travel, learning or the economy.
func _kind(tech: Dictionary) -> String:
	var keys: Dictionary = tech.get("effects", {})
	for kind: String in ["army", "water", "travel", "learning"]:
		for key: String in keys:
			if key in KINDS[kind][0]:
				return kind
	return "economy"


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


func _show_hover(at: Vector2) -> void:
	var text := _tooltip_at(at)
	_hover.visible = text != ""
	if text == "":
		return
	_hover_text.text = text
	_hover.reset_size()
	var spot := _canvas.get_global_mouse_position() + Vector2(18, 18)
	var room := get_global_rect().end - _hover.size - Vector2(8, 8)
	_hover.global_position = Vector2(minf(spot.x, room.x), minf(spot.y, room.y))  # kept inside the tree


## What a tech does, in numbers (from its effects), what it costs, and who has it, each civ in its colour.
func _tooltip_at(at: Vector2) -> String:
	for tech_id: String in _rects:
		if (_rects[tech_id] as Rect2).has_point(at):
			var tech: Dictionary = _by_id[tech_id]
			var lines: Array[String] = ["[b]%s[/b]" % tech["name"], "[color=#b8bec8]%s[/color]" % tech.get("description", "")]
			var bonuses := _effects_text(tech.get("effects", {}))
			if not bonuses.is_empty():
				lines.append("[color=#8fd18f]" + "\n".join(bonuses) + "[/color]")
			var cost: Dictionary = tech.get("cost", {})
			if not cost.is_empty():
				var parts: Array[String] = []
				for res: String in cost:
					parts.append("%d %s" % [int(cost[res]), res])
				lines.append("[color=#8a93a0]Costs %s[/color]" % ", ".join(parts))
			var who: Array[String] = []
			for civ_id: int in _civs:
				if _known.get(civ_id, {}).has(tech_id):
					who.append(_named(civ_id))
			lines.append("Known to " + (", ".join(who) if not who.is_empty() else "nobody yet"))
			for civ_id: int in _research:
				if _research[civ_id]["id"] == tech_id:
					lines.append("%s is learning it (%d%%)" % [_named(civ_id), int(float(_research[civ_id]["progress"]) * 100.0)])
			return "\n".join(lines)
	return ""


func _named(civ_id: int) -> String:
	return "[color=#%s]%s[/color]" % [(_civs[civ_id]["color"] as Color).lightened(0.3).to_html(false), _civs[civ_id]["name"]]


## A tech's effects in words and numbers: "+25% all yields", "+1 building slot".
const PERCENT := {"growth": "growth", "science_mult": "research", "military": "army strength",
	"build_speed": "building speed", "defense": "defence at home", "water_mult": "water", "commander_xp": "generals' experience",
	"capture_speed": "capture speed", "casualties": "battle losses", "mobilization": "of the people under arms",
	"soldier_cost": "soldiers' cost", "deal_fee": "trade fees", "demolition_refund": "back on demolition",
	"water_use": "water drunk", "purification": "water from each coast tile"}
const PLAIN := {"storage": "storage of every resource", "beds": "hospital beds per castle", "housing": "housing",
	"bridges": "rivers crossed freely", "boats": "boats: lakes and the sea crossed", "tier": "troop tier",
	"build_slots": "building slot", "commander_start": "level for new generals", "officer_appointment": "officers can be appointed",
	"boat_range": "tiles of open water for boats", "villager_speed": "villager speed", "home_speed": "army speed at home",
	"reinforce": "speed home to refit"}

func _effects_text(effects: Dictionary) -> Array[String]:
	var out: Array[String] = []
	for key: String in effects:
		var value: Variant = effects[key]
		if value is Dictionary:
			for res: String in value:
				var amount := float(value[res])
				var what := "all yields" if res == "all" else res
				match key:
					"yield_mult":
						out.append("%s%d%% %s" % ["+" if amount >= 0 else "", roundi(amount * 100), what])
					"income":
						out.append("+%s %s a day" % [str(snappedf(amount, 0.1)), what])
					"store":
						out.append("+%d %s storage" % [roundi(amount), what])
					_:
						out.append("%s %s: %s" % [key, what, str(amount)])
		elif PERCENT.has(key):
			var amount := float(value)
			out.append("%s%d%% %s" % ["+" if amount >= 0 else "", roundi(amount * 100), PERCENT[key]])
		elif PLAIN.has(key):
			var amount := float(value)
			out.append("%s%s %s" % ["+" if amount >= 0 else "", str(snappedf(amount, 0.1)).trim_suffix(".0"), PLAIN[key]])
		else:
			out.append("%s: %s" % [key, str(value)])
	return out
