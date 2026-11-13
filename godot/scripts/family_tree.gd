extends PanelContainer
## A royal house as a tree: one row per generation, the oldest at the top, each member with
## their portrait (the dead greyed), a line joining husband and wife and lines down from
## parents to their children. Opened from the Family tab of a civ's drawer; it only draws
## what the simulation sent (civ/family.py).

const CARD := Vector2(92, 142)  # one member: the portrait and two lines under it
const FACE := Vector2(64, 80)
const GAP := 18.0
const ROW := 168.0

var _title: Label
var _scroll: ScrollContainer
var _canvas: Control
var _cards := {}  # member id -> its Control on the canvas
var _members := {}  # member id -> member dict
var _color := Color.WHITE


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	offset_left = 60
	offset_top = 80
	offset_right = -60
	offset_bottom = -60
	visible = false
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.07, 0.08, 0.1, 0.98)
	style.set_corner_radius_all(12)
	style.set_content_margin_all(14)
	add_theme_stylebox_override("panel", style)
	var column := VBoxContainer.new()
	add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 20)
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(_title)
	var close := Button.new()
	close.icon = load("res://assets/icons/close.svg")
	close.expand_icon = true
	close.flat = true
	close.focus_mode = Control.FOCUS_NONE
	close.custom_minimum_size = Vector2(30, 30)
	close.tooltip_text = "Close  (Esc)"
	close.pressed.connect(func() -> void: visible = false)
	header.add_child(close)
	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(_scroll)
	_canvas = Control.new()
	_canvas.draw.connect(_draw_lines)
	_scroll.add_child(_canvas)


func show_house(house: Dictionary, color: Color) -> void:
	_color = color
	_title.text = "House %s%s: family tree" % [house["house"],
		" (%s)" % house["branch"] if str(house.get("branch", "")) != "" else ""]
	for child: Node in _canvas.get_children():
		child.queue_free()
	_cards.clear()
	_members.clear()
	for member: Dictionary in house["members"]:
		_members[int(member["id"])] = member
	var rows := _generations()
	var width := 0.0
	for g in rows.size():
		var x := GAP
		for member_id: int in rows[g]:
			var card := _card(_members[member_id], str(house.get("crest", "")))
			card.position = Vector2(x, GAP + g * ROW)
			_canvas.add_child(card)
			_cards[member_id] = card
			x += CARD.x + GAP
		width = maxf(width, x)
	_canvas.custom_minimum_size = Vector2(width, GAP + rows.size() * ROW)
	_canvas.queue_redraw()
	visible = true
	move_to_front()


## Rows of member ids, oldest generation first: children a row below their parents, a spouse
## beside their partner, brothers and sisters together in order of birth.
func _generations() -> Array:
	var level := {}
	var changed := true
	for member_id: int in _members:
		level[member_id] = 0
	while changed:  # a child sits below the lower of its parents
		changed = false
		for member_id: int in _members:
			for parent: Variant in _members[member_id].get("parents", []):
				if _members.has(int(parent)) and level[member_id] <= level[int(parent)]:
					level[member_id] = level[int(parent)] + 1
					changed = true
	for member_id: int in _members:  # one married in sits with their partner
		var spouse: Variant = _members[member_id].get("spouse")
		var has_parents: bool = _members[member_id].get("parents", []).any(func(p: Variant) -> bool: return _members.has(int(p)))
		if spouse != null and _members.has(int(spouse)) and not has_parents:
			level[member_id] = level[int(spouse)]
	var deepest := 0
	for member_id: int in level:
		deepest = maxi(deepest, level[member_id])
	var rows := []
	var placed := {}  # member id -> its order, for the row below
	for g in deepest + 1:
		var row: Array = []
		var here: Array = level.keys().filter(func(m: int) -> bool: return level[m] == g)
		here.sort_custom(func(a: int, b: int) -> bool:
			var pa := _parent_order(a, placed)
			var pb := _parent_order(b, placed)
			if pa != pb:
				return pa < pb
			return int(_members[a].get("age", 0) if _members[a].get("age") != null else 0) > \
				int(_members[b].get("age", 0) if _members[b].get("age") != null else 0))
		for member_id: int in here:
			if member_id in row:
				continue
			row.append(member_id)
			var spouse: Variant = _members[member_id].get("spouse")
			if spouse != null and here.has(int(spouse)) and not int(spouse) in row:
				row.append(int(spouse))
		for i in row.size():
			placed[row[i]] = i
		rows.append(row)
	return rows


func _parent_order(member_id: int, placed: Dictionary) -> int:
	var best := 1000
	for parent: Variant in _members[member_id].get("parents", []):
		if placed.has(int(parent)):
			best = mini(best, int(placed[int(parent)]))
	return best


func _card(member: Dictionary, crest: String) -> Control:
	var card := VBoxContainer.new()
	card.custom_minimum_size = CARD
	card.size = CARD
	card.add_theme_constant_override("separation", 2)
	var face := TextureRect.new()
	var picture := str(member.get("portrait", ""))
	if picture == "" or not ResourceLoader.exists(picture):
		picture = crest
	if picture != "" and ResourceLoader.exists(picture):
		face.texture = load(picture)
	face.custom_minimum_size = FACE
	face.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	face.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	face.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	if not member["alive"]:
		face.modulate = Color(0.55, 0.55, 0.55)
	card.add_child(face)
	var words := Label.new()
	var note := ""
	if member["ruler"]:
		note = "  ·  rules"
	elif member["heir"]:
		note = "  ·  heir"
	var age_text := ""
	if member.get("age") != null:
		age_text = ("%d" if member["alive"] else "died at %d") % int(member["age"])
	elif not member["alive"]:
		age_text = "died"
	words.text = "%s %s\n%s%s" % [member["title"], member["name"], age_text, note]
	words.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	words.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	words.custom_minimum_size = Vector2(CARD.x, 0)
	words.add_theme_font_size_override("font_size", 11)
	words.add_theme_color_override("font_color", Color(0.95, 0.9, 0.8) if member["alive"] else Color(0.6, 0.6, 0.6))
	card.add_child(words)
	card.tooltip_text = "%s %s%s" % [member["title"], member["name"],
		"\n" + str(member["cause"]) if not member["alive"] and str(member.get("cause", "")) != "" else ""]
	return card


## Husband and wife joined side by side; from between them (or from a lone parent) a line
## down to each child.
func _draw_lines() -> void:
	var ink := Color(_color.lightened(0.3), 0.85)
	for member_id: int in _cards:
		var spouse: Variant = _members[member_id].get("spouse")
		if spouse != null and _cards.has(int(spouse)) and member_id < int(spouse):
			var a: Control = _cards[member_id]
			var b: Control = _cards[int(spouse)]
			if is_equal_approx(a.position.y, b.position.y):
				var y := a.position.y + FACE.y * 0.5
				_canvas.draw_line(Vector2(minf(a.position.x, b.position.x) + CARD.x * 0.5 + FACE.x * 0.5, y),
					Vector2(maxf(a.position.x, b.position.x) + CARD.x * 0.5 - FACE.x * 0.5, y), ink, 2.0)
	for member_id: int in _cards:
		var parents: Array = _members[member_id].get("parents", []).filter(func(p: Variant) -> bool: return _cards.has(int(p)))
		if parents.is_empty():
			continue
		var from := Vector2.ZERO
		if parents.size() >= 2:  # from the line between husband and wife
			for parent: Variant in parents:
				var card: Control = _cards[int(parent)]
				from += card.position + Vector2(CARD.x * 0.5, FACE.y * 0.5)
			from /= parents.size()
		else:  # from under a lone parent's name
			var card: Control = _cards[int(parents[0])]
			from = card.position + Vector2(CARD.x * 0.5, CARD.y - 4.0)
		var child: Control = _cards[member_id]
		var to := child.position + Vector2(CARD.x * 0.5, 0)
		var mid := (from.y + to.y) * 0.5 + 10.0
		_canvas.draw_polyline(PackedVector2Array([from, Vector2(from.x, mid), Vector2(to.x, mid), to]), ink, 1.5)
