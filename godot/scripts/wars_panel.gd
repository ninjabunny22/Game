extends PanelContainer
## Ongoing wars, under the civ chips at the top right while watching. The heading counts them;
## each war is a row with both civs' shields and names in their colours, facing each other
## across crossed swords. Clicking a row folds open a side-by-side comparison (military
## strength, field armies, regions held), updated every tick from the data the simulation
## sends (relations, civs, armies). Rows appear and go as wars begin and end. It only shows
## what it is sent; it decides nothing.

const WIDTH := 372.0
const MAX_HEIGHT := 420.0  # beyond this the list scrolls, so the map stays in view
const TEXT := Color(0.93, 0.9, 0.84)
const FAINT := Color(0.66, 0.7, 0.76)

var _title: Label
var _fold: Button
var _scroll: ScrollContainer
var _list: VBoxContainer
var _rows := {}  # "a:b" -> {"root", "details", "values": {stat: [label a, label b]}}
var _open := {}  # "a:b" -> true while folded open
var _allies_title: Label
var _allies: VBoxContainer  # one row per alliance: its members' shields and names
var _allies_signature := ""
var _collapsed := false
var bottom_reserve := 0.0  # the height kept free at the bottom right (the minimap and its toggles), from hud.gd


func _ready() -> void:
	set_anchors_preset(Control.PRESET_TOP_RIGHT)
	grow_horizontal = Control.GROW_DIRECTION_BEGIN
	offset_right = -10
	offset_left = -10 - WIDTH
	custom_minimum_size = Vector2(WIDTH, 0)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.06, 0.075, 0.1, 0.88)
	style.set_corner_radius_all(10)
	style.set_content_margin_all(10)
	style.set_border_width_all(1)
	style.border_color = Color(1, 1, 1, 0.1)
	add_theme_stylebox_override("panel", style)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	add_child(column)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	column.add_child(header)
	header.add_child(_icon("res://assets/icons/battle.svg", 24, Color.WHITE))
	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 17)
	_title.add_theme_color_override("font_color", TEXT)
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(_title)
	_fold = Button.new()
	_fold.flat = true
	_fold.focus_mode = Control.FOCUS_NONE
	_fold.add_theme_font_size_override("font_size", 18)
	_fold.tooltip_text = "Show or hide the wars"
	_fold.pressed.connect(func() -> void:
		_collapsed = not _collapsed
		_fit())
	header.add_child(_fold)
	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(_scroll)
	var inside := VBoxContainer.new()
	inside.add_theme_constant_override("separation", 8)
	inside.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.add_child(inside)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 6)
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inside.add_child(_list)
	# Who stands with whom: every alliance (allies of allies together), in the civs' colours.
	_allies_title = Label.new()
	_allies_title.add_theme_font_size_override("font_size", 14)
	_allies_title.add_theme_color_override("font_color", FAINT)
	inside.add_child(_allies_title)
	_allies = VBoxContainer.new()
	_allies.add_theme_constant_override("separation", 4)
	inside.add_child(_allies)
	visible = false


## From each tick: the wars going on, and the figures each row compares. `info` is the HUD's
## civ id -> {name, color} from the init message. Allies fighting the same enemy are one side:
## a war of A and its ally C against B (and B's allies in it) is one row, their figures added.
func update(data: Dictionary, info: Dictionary) -> void:
	var civs := {}
	for civ: Dictionary in data["civs"]:
		civs[int(civ["id"])] = civ
	var armies := {}  # civ id -> its armies in the field
	for army: Dictionary in data["armies"]:
		if army["role"] == "field":
			armies[int(army["civ"])] = armies.get(int(army["civ"]), 0) + 1
	var at_war := {}  # "a:b" (a < b) -> true
	var allied := {}
	for relation: Dictionary in data["relations"]:
		var pair := "%d:%d" % [mini(int(relation["a"]), int(relation["b"])), maxi(int(relation["a"]), int(relation["b"]))]
		if relation["status"] == "war":
			at_war[pair] = true
		elif relation["status"] == "alliance":
			allied[pair] = true
	var sides_of := {}  # row key -> [side ids, side ids]
	for pair: String in at_war:
		var a := int(pair.split(":")[0])
		var b := int(pair.split(":")[1])
		if not (info.has(a) and info.has(b) and civs.has(a) and civs.has(b)):
			continue
		var left := _side(a, b, civs, at_war, allied)
		var right := _side(b, a, civs, at_war, allied)
		if left[0] > right[0]:
			var swap := left
			left = right
			right = swap
		sides_of["%s|%s" % [",".join(left.map(func(n: int) -> String: return str(n))),
			",".join(right.map(func(n: int) -> String: return str(n)))]] = [left, right]
	for key: String in sides_of:
		if not _rows.has(key):
			_rows[key] = _make_row(key, sides_of[key][0], sides_of[key][1], info)
		var values: Dictionary = _rows[key]["values"]
		for side in 2:
			var strength := 0
			var count := 0
			var regions := 0
			for civ_id: int in sides_of[key][side]:
				strength += int(civs[civ_id].get("army_strength", 0))
				count += int(armies.get(civ_id, 0))
				regions += int(civs[civ_id].get("regions", []).size())
			(values["strength"][side] as Label).text = _thousands(strength)
			(values["armies"][side] as Label).text = "%d %s" % [count, "army" if count == 1 else "armies"]
			(values["regions"][side] as Label).text = "%d %s" % [regions, "region" if regions == 1 else "regions"]
	for key: String in _rows.keys():
		if not sides_of.has(key):  # the war is over, or its sides have changed
			(_rows[key]["root"] as Node).queue_free()
			_rows.erase(key)
			_open.erase(key)
	_title.text = "Ongoing Wars (%d)" % _rows.size()
	_show_alliances(allied, info, civs)
	_fit.call_deferred()  # once the rows of wars just ended are really gone


## The alliances as groups (an ally of an ally stands in the same group), one row each.
func _show_alliances(allied: Dictionary, info: Dictionary, civs: Dictionary) -> void:
	var group := {}  # civ id -> group id
	for pair: String in allied:
		var a := int(pair.split(":")[0])
		var b := int(pair.split(":")[1])
		if not (info.has(a) and info.has(b) and civs.has(a) and civs.has(b)):
			continue
		var ga: int = group.get(a, a)
		var gb: int = group.get(b, b)
		for civ_id: int in group.keys():  # merge b's group into a's
			if group[civ_id] == gb:
				group[civ_id] = ga
		group[a] = ga
		group[b] = ga
	var groups := {}
	for civ_id: int in group:
		if not groups.has(group[civ_id]):
			groups[group[civ_id]] = []
		groups[group[civ_id]].append(civ_id)
	var signature := str(groups)
	_allies_title.text = "Alliances (%d)" % groups.size() if not groups.is_empty() else "No alliances"
	if signature == _allies_signature:
		return
	_allies_signature = signature
	for child: Node in _allies.get_children():
		child.queue_free()
	for key: int in groups:
		var members: Array = groups[key]
		members.sort()
		var line := HBoxContainer.new()
		line.add_theme_constant_override("separation", 4)
		for civ_id: int in members:
			line.add_child(_icon("res://assets/icons/shield.svg", 18, Color.html(info[civ_id]["color"]).lightened(0.15)))
		line.add_child(_names(members, info, false, 14))
		_allies.add_child(line)


## One side of the war of `civ_id` against `enemy`: the civ and its allies also at war with
## that enemy, smallest id first.
func _side(civ_id: int, enemy: int, civs: Dictionary, at_war: Dictionary, allied: Dictionary) -> Array:
	var side := [civ_id]
	for other: int in civs:
		if other == civ_id or other == enemy or not civs[other].get("alive", true):
			continue
		var with_civ := "%d:%d" % [mini(civ_id, other), maxi(civ_id, other)]
		var with_enemy := "%d:%d" % [mini(enemy, other), maxi(enemy, other)]
		if allied.has(with_civ) and at_war.has(with_enemy):
			side.append(other)
	side.sort()
	return side


func clear() -> void:
	for key: String in _rows:
		(_rows[key]["root"] as Node).queue_free()
	_rows.clear()
	_open.clear()


## The list as tall as its rows, up to MAX_HEIGHT; folded away when collapsed or empty.
func _fit() -> void:
	_fold.text = "+" if _collapsed else "−"
	_scroll.visible = not _collapsed
	for key: String in _rows:
		(_rows[key]["details"] as Control).visible = _open.has(key)
	# Never down over the minimap: the list gets the room left above it, at most MAX_HEIGHT.
	var room := get_viewport().get_visible_rect().size.y - offset_top - bottom_reserve - 80.0
	_scroll.custom_minimum_size = Vector2(0, minf(_list.get_combined_minimum_size().y, clampf(room, 90.0, MAX_HEIGHT)))
	reset_size.call_deferred()  # shrink to fit when a row folds shut or a war ends


## One war: a clickable bar with both sides facing each other, and the comparison under it.
func _make_row(key: String, left: Array, right: Array, info: Dictionary) -> Dictionary:
	if OS.get_environment("CIVSIM_WARS_OPEN") == "1":  # scripted runs: every war folded open
		_open[key] = true
	var color_a := Color.html(info[left[0]]["color"])
	var color_b := Color.html(info[right[0]]["color"])
	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 0)
	_list.add_child(root)
	var bar := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 1, 1, 0.05)
	style.set_corner_radius_all(8)
	style.set_content_margin_all(6)
	style.set_border_width_all(1)
	style.border_color = color_a.lerp(color_b, 0.5).darkened(0.2)
	bar.add_theme_stylebox_override("panel", style)
	bar.mouse_filter = Control.MOUSE_FILTER_STOP
	bar.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	bar.tooltip_text = "Click to compare the two sides"
	bar.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			if _open.has(key):
				_open.erase(key)
			else:
				_open[key] = true
			_fit())
	root.add_child(bar)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 4)
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_child(line)
	for civ_id: int in left:
		line.add_child(_icon("res://assets/icons/shield.svg", 22, Color.html(info[civ_id]["color"]).lightened(0.15)))
	line.add_child(_names(left, info, false, 15))
	line.add_child(_icon("res://assets/icons/battle.svg", 22, Color(1, 0.55, 0.5)))
	line.add_child(_names(right, info, true, 15))
	for civ_id: int in right:
		line.add_child(_icon("res://assets/icons/shield.svg", 22, Color.html(info[civ_id]["color"]).lightened(0.15)))
	# The comparison, folded away until the row is clicked.
	var details := PanelContainer.new()
	var inner := StyleBoxFlat.new()
	inner.bg_color = Color(0, 0, 0, 0.25)
	inner.set_corner_radius_all(6)
	inner.set_content_margin_all(8)
	details.add_theme_stylebox_override("panel", inner)
	details.visible = false
	root.add_child(details)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 6)
	details.add_child(grid)
	grid.add_child(Control.new())
	grid.add_child(_names(left, info, false, 13, true))
	grid.add_child(_names(right, info, false, 13, true))
	var values := {}
	for stat: Array in [["strength", "Military strength"], ["armies", "Armies in the field"], ["regions", "Regions held"]]:
		var label := _cell(str(stat[1]), FAINT)
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
		grid.add_child(label)
		var pair := [_cell("", color_a.lightened(0.45)), _cell("", color_b.lightened(0.45))]
		grid.add_child(pair[0])
		grid.add_child(pair[1])
		values[stat[0]] = pair
	return {"root": root, "details": details, "values": values}


## A side's names, each in its civ's colour, joined by "+".
func _names(side: Array, info: Dictionary, right_aligned: bool, font_size: int, centred := false) -> RichTextLabel:
	var parts: Array[String] = []
	for civ_id: int in side:
		parts.append("[color=#%s]%s[/color]" % [Color.html(info[civ_id]["color"]).lightened(0.3).to_html(false),
			info[civ_id]["name"]])
	var label := RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART  # a long alliance wraps; the panel keeps its width
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("normal_font_size", font_size)
	var text := " + ".join(parts)
	label.text = ("[center]%s[/center]" if centred else ("[right]%s[/right]" if right_aligned else "%s")) % text
	return label


func _cell(text: String, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("font_size", 13)
	label.add_theme_color_override("font_color", color)
	return label


func _icon(path: String, side: int, tint: Color) -> TextureRect:
	var icon := TextureRect.new()
	icon.texture = load(path)
	icon.custom_minimum_size = Vector2(side, side)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.modulate = tint
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return icon


## 46800 as "46,800".
func _thousands(value: int) -> String:
	var digits := str(absi(value))
	var out := ""
	while digits.length() > 3:
		out = "," + digits.substr(digits.length() - 3) + out
		digits = digits.substr(0, digits.length() - 3)
	return ("-" if value < 0 else "") + digits + out
