extends PanelContainer
## A royal house as a tree. Each generation is a row, labelled at the left (relative to the
## ruler: elders, the ruler's generation, children, grandchildren); a married couple stands
## side by side joined by a line; children stand centred under their parents, joined by
## straight lines. Each member has their portrait (greyed if dead), name and age, their traits
## as small tags; the ruler wears a crown and the heir a paler one. One member can be picked
## out (a clicked event). It only draws what the simulation sent (civ/family.py).

const CARD := Vector2(108, 168)  # one member: portrait, name, age, tags
const FACE := Vector2(72, 90)
const GAP := 16.0  # between families in a row
const COUPLE_GAP := 10.0  # between husband and wife
const ROW := 214.0
const LABEL_WIDTH := 150.0
const GREY := Color(0.55, 0.55, 0.55)
const TRAIT_COLORS := {"brave": "#e8b84a", "sickly": "#9ab07a", "learned": "#7ab0e0", "cruel": "#e07a6a",
	"ambitious": "#d98a5a", "usurper": "#e05a4a", "pious": "#d8d0a8", "shrewd": "#e8b84a", "kind": "#8fd18f",
	"proud": "#c98fd1"}

var _title: Label
var _canvas: Control
var _cards := {}  # member id -> its card on the canvas
var _members := {}  # member id -> member dict
var _color := Color.WHITE
var _rows: Array = []  # [y, label] of each generation, for the labels drawn at the left


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
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(scroll)
	_canvas = Control.new()
	_canvas.draw.connect(_draw_lines)
	scroll.add_child(_canvas)


## Show a house; `pick` is a member to single out (from a clicked event), or -1.
func show_house(house: Dictionary, color: Color, pick := -1) -> void:
	_color = color
	_title.text = "House %s%s: family tree" % [house["house"],
		" (%s)" % house["branch"] if str(house.get("branch", "")) != "" else ""]
	for child: Node in _canvas.get_children():
		child.queue_free()
	_cards.clear()
	_members.clear()
	for member: Dictionary in house["members"]:
		_members[int(member["id"])] = member
	var width := _layout(str(house.get("crest", "")), pick)
	_canvas.custom_minimum_size = Vector2(width, GAP + _rows.size() * ROW)
	_canvas.queue_redraw()
	visible = true
	move_to_front()


## Generations by descent; the families (a member, their spouse, their children) laid out
## from the eldest down, each family's children centred under it. Returns the width used.
func _layout(crest: String, pick: int) -> float:
	var level := _levels()
	var ruler_level := 0
	var deepest := 0
	for id: int in level:
		deepest = maxi(deepest, level[id])
		if _members[id]["ruler"]:
			ruler_level = level[id]
	var names := {-2: "Grandparents", -1: "Elders", 0: "The ruler's", 1: "Children", 2: "Grandchildren",
		3: "Great-grandchildren"}
	_rows.clear()
	for g in deepest + 1:
		_rows.append([GAP + g * ROW, str(names.get(g - ruler_level, "Generation %d" % (g + 1)))])
	var placed := {}
	var x := LABEL_WIDTH + GAP
	var roots: Array = _members.keys().filter(func(id: int) -> bool: return level[id] == 0 and not _is_married_in(id))
	roots.sort_custom(func(a: int, b: int) -> bool: return _age(a) > _age(b))
	for root: int in roots:
		if not placed.has(root):
			x = _place_family(root, level, x, placed, crest, pick) + GAP
	for id: int in _members:  # anyone not reached (their family gone from the house): at the end of their row
		if not placed.has(id):
			_put(id, Vector2(x, GAP + level[id] * ROW), crest, pick, placed)
			x += CARD.x + GAP
	return x


## `id`, their spouse beside them and their children's families under them, from `x`.
## Returns the right edge of the family.
func _place_family(id: int, level: Dictionary, x: float, placed: Dictionary, crest: String, pick: int) -> float:
	placed[id] = true  # claimed now, so no family reaches back to it
	var spouse := _spouse_in_house(id)
	var with_spouse := spouse >= 0 and not placed.has(spouse)
	if with_spouse:
		placed[spouse] = true
	var couple_width := CARD.x + ((COUPLE_GAP + CARD.x) if with_spouse else 0.0)
	var right := x
	var child_x := x
	var any_kids := false
	for kid: int in _children(id):
		if placed.has(kid):
			continue
		any_kids = true
		right = _place_family(kid, level, child_x, placed, crest, pick)
		child_x = right + GAP
	var start := x + maxf(0.0, ((right - x) - couple_width) * 0.5) if any_kids else x  # centred over its children
	var y: float = GAP + level[id] * ROW
	_put(id, Vector2(start, y), crest, pick, placed)
	if with_spouse:
		_put(spouse, Vector2(start + CARD.x + COUPLE_GAP, y), crest, pick, placed)
	return maxf(start + couple_width, right)


func _put(id: int, at: Vector2, crest: String, pick: int, placed: Dictionary) -> void:
	var card := _card(_members[id], crest, id == pick)
	card.position = at
	_canvas.add_child(card)
	_cards[id] = card
	placed[id] = true


func _levels() -> Dictionary:
	var level := {}
	for id: int in _members:
		level[id] = 0
	var changed := true
	while changed:  # a child is a row below the lower of its parents
		changed = false
		for id: int in _members:
			for parent: Variant in _members[id].get("parents", []):
				if _members.has(int(parent)) and level[id] <= level[int(parent)]:
					level[id] = level[int(parent)] + 1
					changed = true
	for id: int in _members:  # one married in stands in their partner's row
		if _is_married_in(id):
			level[id] = level[_spouse_in_house(id)]
	return level


func _has_parents(id: int) -> bool:
	return _members[id].get("parents", []).any(func(p: Variant) -> bool: return _members.has(int(p)))


func _is_married_in(id: int) -> bool:
	var spouse := _spouse_in_house(id)
	return not _has_parents(id) and spouse >= 0 and _has_parents(spouse)


func _spouse_in_house(id: int) -> int:
	var spouse: Variant = _members[id].get("spouse")
	return int(spouse) if spouse != null and _members.has(int(spouse)) else -1


## Children of `id` (or of their spouse) in the house, eldest first.
func _children(id: int) -> Array:
	var spouse := _spouse_in_house(id)
	var kids: Array = _members.keys().filter(func(k: int) -> bool:
		var parents: Array = _members[k].get("parents", []).map(func(p: Variant) -> int: return int(p))
		return parents.has(id) or (spouse >= 0 and parents.has(spouse)))
	kids.sort_custom(func(a: int, b: int) -> bool: return _age(a) > _age(b))
	return kids


func _age(id: int) -> int:
	var age: Variant = _members[id].get("age")
	return int(age) if age != null else 200  # the long dead first


func _card(member: Dictionary, crest: String, picked: bool) -> Control:
	var alive: bool = member["alive"]
	var card := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(1, 1, 1, 0.045 if alive else 0.02)
	style.set_corner_radius_all(8)
	style.set_content_margin_all(4)
	style.set_border_width_all(2 if picked else 1)
	style.border_color = Color(0.95, 0.8, 0.35) if picked else Color(1, 1, 1, 0.08 if alive else 0.04)
	card.add_theme_stylebox_override("panel", style)
	card.custom_minimum_size = CARD
	card.size = CARD
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 1)
	card.add_child(column)
	var top := Control.new()
	top.custom_minimum_size = FACE
	top.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	top.clip_contents = false
	column.add_child(top)
	var face := TextureRect.new()
	var picture := str(member.get("portrait", ""))
	if picture == "" or not ResourceLoader.exists(picture):
		picture = crest
	if picture != "" and ResourceLoader.exists(picture):
		face.texture = load(picture)
	face.expand_mode = TextureRect.EXPAND_IGNORE_SIZE  # before the size, or the picture's own size wins
	face.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	face.custom_minimum_size = FACE
	face.size = FACE
	if not alive:
		face.modulate = GREY
	top.add_child(face)
	if alive and (member["ruler"] or member["heir"]):  # a crown for the ruler, a paler one for the heir
		var mark := TextureRect.new()
		mark.texture = load("res://assets/icons/crown.svg")
		mark.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		mark.size = Vector2(22, 22)
		mark.position = Vector2(FACE.x - 16, -8)
		mark.modulate = Color.WHITE if member["ruler"] else Color(0.7, 0.8, 1.0, 0.8)
		top.add_child(mark)
	var words := RichTextLabel.new()
	words.bbcode_enabled = true
	words.fit_content = true
	words.scroll_active = false
	words.custom_minimum_size = Vector2(CARD.x - 8, 0)
	words.add_theme_font_size_override("normal_font_size", 11)
	words.add_theme_color_override("default_color", Color(0.95, 0.9, 0.8) if alive else GREY)
	var age := ""
	if member.get("age") != null:
		age = ("%d" % int(member["age"])) if alive else ("died at %d" % int(member["age"]))
	elif not alive:
		age = "died"
	var role := ""
	if alive and member["ruler"]:
		role = "  [color=#e8b84a]rules[/color]"
	elif alive and member["heir"]:
		role = "  [color=#a9c4ff]heir[/color]"
	var tags: Array[String] = []
	for quality: Variant in member.get("traits", []):
		tags.append("[color=%s]%s[/color]" % [TRAIT_COLORS.get(str(quality), "#c9b48a") if alive else "#777777", quality])
	words.text = "[center]%s %s\n%s%s\n%s[/center]" % [member["title"], member["name"], age, role, " · ".join(tags)]
	column.add_child(words)
	card.tooltip_text = "%s %s%s" % [member["title"], member["name"],
		"\n" + str(member["cause"]) if not alive and str(member.get("cause", "")) != "" else ""]
	return card


## Generation labels at the left; a line joining husband and wife; from between them (or under
## a lone parent) a straight line down to a bar, and from the bar down to each child.
func _draw_lines() -> void:
	var font := get_theme_default_font()
	for row: Array in _rows:
		_canvas.draw_string(font, Vector2(8, float(row[0]) + FACE.y * 0.5), str(row[1]), HORIZONTAL_ALIGNMENT_LEFT,
			LABEL_WIDTH - 12, 12, Color(0.7, 0.72, 0.78))
	var ink := Color(_color.lightened(0.35), 0.9)
	for id: int in _cards:
		var spouse := _spouse_in_house(id)
		if spouse > id and _cards.has(spouse):
			var a: Control = _cards[id]
			var b: Control = _cards[spouse]
			var y := a.position.y + FACE.y * 0.5
			_canvas.draw_line(Vector2(minf(a.position.x, b.position.x) + CARD.x, y),
				Vector2(maxf(a.position.x, b.position.x), y), ink, 2.0)
	var done := {}
	for id: int in _cards:
		if done.has(id):
			continue
		var kids: Array = _children(id).filter(func(k: int) -> bool: return _cards.has(k))
		var spouse := _spouse_in_house(id)
		done[id] = true
		if spouse >= 0:
			done[spouse] = true
		if kids.is_empty():
			continue
		var card: Control = _cards[id]
		var from := card.position + Vector2(CARD.x * 0.5, CARD.y)
		if spouse >= 0 and _cards.has(spouse):  # from the middle of the couple's line
			var other: Control = _cards[spouse]
			from = Vector2((minf(card.position.x, other.position.x) + CARD.x + maxf(card.position.x, other.position.x)) * 0.5,
				card.position.y + FACE.y * 0.5)
		var bar_y := card.position.y + CARD.y + (ROW - CARD.y) * 0.5
		var left := from.x
		var right := from.x
		for kid: int in kids:
			var top := (_cards[kid] as Control).position + Vector2(CARD.x * 0.5, 0)
			left = minf(left, top.x)
			right = maxf(right, top.x)
			_canvas.draw_line(Vector2(top.x, bar_y), top, ink, 1.5)
		_canvas.draw_line(from, Vector2(from.x, bar_y), ink, 1.5)
		_canvas.draw_line(Vector2(left, bar_y), Vector2(right, bar_y), ink, 1.5)
