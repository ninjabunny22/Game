extends CanvasLayer
## The main menu, and the step after it where a ruler chooses a civ.
##
## The menu sits over a game that is playing itself. It asks how to play (watch every civ
## play itself, or rule one), on which of the three maps, and with how many civs: each map
## suggests a number and limits the choice to what it has room for. A game to be ruled then
## shows its civs, paused, for the player to pick one.

signal start_requested(mode: String, size: String, civs: int, seed_text: String, map_id: String, difficulty: String)
signal civ_chosen(civ_id: int)  # -1: watch after all
## The game behind the menu should become the chosen map with this many civs, on its first day
## (the simulation starts it paused; the game then started from the menu is that very one).
signal preview_requested(size: String, map_id: String, civs: int)

const Minimap := preload("res://scripts/minimap.gd")
var _quiet := true  # while the menu is being built, choices do not ask for a new backdrop
var _preview_timer: Timer
var _preview_panel: PanelContainer
var _preview_map: Control
var _preview_list: RichTextLabel
var _world_civs: Array = []  # the backdrop's civs, from its init message
var _world_colors: Array = []

const ACCENT := Color(0.36, 0.62, 1.0)
const MODES := [
	["watch", "Watch a simulation", "Every civ plays itself.\nSit back and see who wins."],
	["rule", "Rule a civ", "Take one civ in hand.\nThe others play against you."],
]

var _root: Control
var _menu: Control
var _pick: Control
var _sizes: Array = []
var _mode := "watch"
var _size := "medium"
var _civs := 4
var _mode_cards := {}
var _difficulty := "normal"  # how hard the other civs go on a ruler
var _difficulty_row: HBoxContainer
var _difficulty_buttons := {}
var _map := ""  # the map asked for by id, or "" for any of the size's
var _map_row: HBoxContainer
var _map_buttons := {}
var _premise: Label  # what the chosen map is about
## "Any size": a map of any size, picked at random.
const ANY_SIZE := {"id": "random", "name": "Random", "civs": 4, "min_civs": 2, "max_civs": 5, "maps": []}
var _size_cards := {}
var _civ_count: Label
var _civ_hint: Label
var _fewer: Button
var _more: Button
var _seed: LineEdit


func _ready() -> void:
	layer = 5
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	visible = false


## Show the menu. `lobby` is what the sim offers: the map sizes and how many civs each takes.
func show_menu(lobby: Dictionary) -> void:
	if visible and _menu != null and is_instance_valid(_menu):
		return  # already open (the backdrop was only swapped for a preview): keep every choice
	_quiet = true
	_sizes = lobby["sizes"]
	_mode = "watch"  # each visit starts from watching, whatever the last game was
	_clear()
	visible = true
	# The game behind stays visible, darkened toward the edges of the panel.
	var shade := ColorRect.new()
	shade.color = Color(0.02, 0.04, 0.08, 0.5)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(shade)
	var centre := CenterContainer.new()
	centre.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(centre)
	_menu = centre
	var panel := _panel(Color(0.05, 0.065, 0.095, 0.9), 22, 26)
	centre.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	panel.add_child(column)

	var title := Label.new()
	title.text = "C I V S I M"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 44)
	title.add_theme_color_override("font_color", Color(0.96, 0.9, 0.72))
	title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	title.add_theme_constant_override("outline_size", 6)
	column.add_child(title)
	var tagline := Label.new()
	tagline.text = "Civilizations rise, trade, ally and go to war. Watch them, or lead one."
	tagline.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	tagline.add_theme_font_size_override("font_size", 14)
	tagline.modulate = Color(1, 1, 1, 0.65)
	column.add_child(tagline)

	_heading(column, "How do you want to play?")
	var modes := HBoxContainer.new()
	modes.add_theme_constant_override("separation", 12)
	column.add_child(modes)
	_mode_cards.clear()
	for mode: Array in MODES:
		_mode_cards[mode[0]] = _card(modes, mode[1], mode[2], Vector2(300, 96), func() -> void: _set_mode(mode[0]))

	_heading(column, "Map")
	var sizes := HBoxContainer.new()
	sizes.add_theme_constant_override("separation", 12)
	column.add_child(sizes)
	_size_cards.clear()
	for size: Dictionary in _sizes + [ANY_SIZE]:
		var detail := "%d maps · %d to %d civs" % [size["maps"].size(), int(size["min_civs"]), int(size["max_civs"])]
		if size["id"] == "random":
			detail = "Any of the %d maps" % _all_maps().size()
		var id: String = size["id"]
		_size_cards[id] = _card(sizes, str(size["name"]), detail, Vector2(150, 92), func() -> void: _set_size(id))
	# Which of the size's maps to play on: one picked at random, or one by name.
	_map_row = HBoxContainer.new()
	_map_row.add_theme_constant_override("separation", 8)
	_map_row.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(_map_row)
	_premise = Label.new()
	_premise.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_premise.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_premise.custom_minimum_size = Vector2(620, 0)
	_premise.add_theme_font_size_override("font_size", 13)
	_premise.modulate = Color(1, 1, 1, 0.75)
	column.add_child(_premise)

	_heading(column, "Civilizations")
	var count := HBoxContainer.new()
	count.add_theme_constant_override("separation", 12)
	count.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(count)
	_fewer = _round_button(count, "−", func() -> void: _set_civs(_civs - 1))
	_civ_count = Label.new()
	_civ_count.custom_minimum_size = Vector2(60, 0)
	_civ_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_civ_count.add_theme_font_size_override("font_size", 34)
	count.add_child(_civ_count)
	_more = _round_button(count, "+", func() -> void: _set_civs(_civs + 1))
	_civ_hint = Label.new()
	_civ_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_civ_hint.add_theme_font_size_override("font_size", 13)
	_civ_hint.modulate = Color(1, 1, 1, 0.6)
	column.add_child(_civ_hint)

	# How hard the other civs go on you; it only matters when you rule one.
	_difficulty_row = HBoxContainer.new()
	_difficulty_row.add_theme_constant_override("separation", 8)
	_difficulty_row.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(_difficulty_row)
	_difficulty_buttons.clear()
	for level: Array in [["easy", "Easy"], ["normal", "Normal"], ["hard", "Hard"]]:
		var id: String = level[0]
		var button := Button.new()
		button.text = str(level[1])
		button.focus_mode = Control.FOCUS_NONE
		button.custom_minimum_size = Vector2(120, 34)
		button.pressed.connect(func() -> void: _set_difficulty(id))
		_difficulty_row.add_child(button)
		_difficulty_buttons[id] = button
	_set_difficulty(_difficulty)

	var last := HBoxContainer.new()
	last.add_theme_constant_override("separation", 12)
	last.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(last)
	_seed = LineEdit.new()
	_seed.placeholder_text = "Seed (blank: new starts)"
	_seed.custom_minimum_size = Vector2(230, 44)
	_seed.max_length = 9
	last.add_child(_seed)
	var start := Button.new()
	start.text = "Start"
	start.custom_minimum_size = Vector2(230, 44)
	start.add_theme_font_size_override("font_size", 20)
	_style_button(start, ACCENT.darkened(0.1), ACCENT, 12)
	start.pressed.connect(func() -> void: start_requested.emit(_mode, _size, _civs, _seed.text.strip_edges(), _map, _difficulty))
	var look := Button.new()
	look.text = "Preview"
	look.tooltip_text = "Where each civ starts on this map, and how the map looks on the first day"
	look.custom_minimum_size = Vector2(130, 44)
	look.add_theme_font_size_override("font_size", 18)
	_style_button(look, Color(1, 1, 1, 0.1), Color(1, 1, 1, 0.2), 12)
	look.pressed.connect(_open_preview)
	last.add_child(look)
	last.add_child(start)
	_build_preview()

	_set_mode(_mode)
	_set_size(_size if _size_cards.has(_size) else str(_sizes[0]["id"]))
	_quiet = false


## Show the civs of a game about to be ruled, for the player to choose one.
func show_pick(civs: Array) -> void:
	_clear()
	visible = true
	var holder := MarginContainer.new()
	holder.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	holder.grow_vertical = Control.GROW_DIRECTION_BEGIN
	holder.add_theme_constant_override("margin_bottom", 28)
	holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(holder)
	_pick = holder
	var centre := CenterContainer.new()
	centre.mouse_filter = Control.MOUSE_FILTER_IGNORE
	holder.add_child(centre)
	var panel := _panel(Color(0.05, 0.065, 0.095, 0.9), 18, 22)
	centre.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	panel.add_child(column)
	var title := Label.new()
	title.text = "Choose the civ you will rule"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 24)
	column.add_child(title)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_child(row)
	for civ: Dictionary in civs:
		var civ_id := int(civ["id"])
		var color := Color.html(civ["color"])
		var card := _card(row, str(civ["name"]), "%s\nHome: %s" % [civ["personality"], civ.get("capital", "")],
				Vector2(180, 92), func() -> void: civ_chosen.emit(civ_id))
		(card.get_meta("title") as Label).add_theme_color_override("font_color", color.lightened(0.25))
		_style_button(card, color.darkened(0.72), color.darkened(0.45), 14)
	var watch := Button.new()
	watch.text = "Just watch instead"
	watch.focus_mode = Control.FOCUS_NONE
	_style_button(watch, Color(1, 1, 1, 0.08), Color(1, 1, 1, 0.18), 10)
	watch.pressed.connect(func() -> void: civ_chosen.emit(-1))
	column.add_child(watch)


func close() -> void:
	_clear()
	visible = false


func _clear() -> void:
	for child in _root.get_children():
		child.queue_free()
	_menu = null
	_pick = null
	_preview_panel = null
	_preview_map = null
	_preview_list = null


func _set_difficulty(level: String) -> void:
	_difficulty = level
	for key: String in _difficulty_buttons:
		var chosen: bool = key == level
		_style_button(_difficulty_buttons[key], ACCENT.darkened(0.25) if chosen else Color(1, 1, 1, 0.07),
				ACCENT.darkened(0.1) if chosen else Color(1, 1, 1, 0.14), 10)


func _set_mode(mode: String) -> void:
	_mode = mode
	if _difficulty_row != null:
		_difficulty_row.visible = mode == "rule"
	for id: String in _mode_cards:
		_light(_mode_cards[id], id == mode)


func _set_size(size: String) -> void:
	_size = size
	for id: String in _size_cards:
		_light(_size_cards[id], id == size)
	for child in _map_row.get_children():
		child.queue_free()
	_map_buttons.clear()
	var choices: Array = [{"id": "", "name": "Random"}]
	choices.append_array(_spec().get("maps", []))
	for choice: Dictionary in choices:
		var id := str(choice["id"])
		var button := Button.new()
		button.text = str(choice["name"])
		if choice.has("width"):
			button.text += "\n%d × %d · %d–%d civs" % [int(choice["width"]), int(choice["height"]),
				int(choice["min_civs"]), int(choice["max_civs"])]
		button.focus_mode = Control.FOCUS_NONE
		button.custom_minimum_size = Vector2(130, 48)
		button.pressed.connect(func() -> void: _set_map(id))
		_map_row.add_child(button)
		_map_buttons[id] = button
	_map_row.visible = size != "random"
	_set_map("")
	_set_civs(int(_spec()["civs"]))  # each size starts on the number that suits it


func _set_map(id: String) -> void:
	_map = id
	for key: String in _map_buttons:
		var chosen: bool = key == id
		_style_button(_map_buttons[key], ACCENT.darkened(0.25) if chosen else Color(1, 1, 1, 0.07),
				ACCENT.darkened(0.1) if chosen else Color(1, 1, 1, 0.14), 10)
	var entry := _map_entry()
	if entry.is_empty():
		_premise.text = "A map picked at random from the %s." % (
			"nine" if _size == "random" else str(_spec()["name"]).to_lower() + " maps")
	else:
		var best := str(entry.get("best", ""))
		_premise.text = str(entry.get("premise", "")) + ("  Best with %s civs." % best if best != "" else "")
	if _civ_count != null:
		_set_civs(_civs)
	_ask_preview()


func _set_civs(civs: int) -> void:
	var limits := _limits()
	var counts := _counts(limits)
	# The nearest number the map takes, in the direction asked for (Highgate takes 2 or 4).
	if not counts.has(civs):
		var above := counts.filter(func(n: int) -> bool: return n > _civs)
		var below := counts.filter(func(n: int) -> bool: return n < _civs)
		if civs > _civs and not above.is_empty():
			civs = above.min()
		elif civs < _civs and not below.is_empty():
			civs = below.max()
	_civs = clampi(civs, counts[0], counts[-1])
	_civ_count.text = str(_civs)
	_fewer.disabled = _civs <= counts[0]
	_more.disabled = _civs >= counts[-1]
	var where := str(limits["name"]) if limits.has("width") else "a %s map" % str(limits["name"]).to_lower()
	var which := "%d to %d" % [counts[0], counts[-1]]
	if counts.size() < counts[-1] - counts[0] + 1:
		which = " or ".join(counts.map(func(n: int) -> String: return str(n)))
	_civ_hint.text = "%s on %s" % [which, where]
	_ask_preview()


## A new backdrop for the choice, once the clicking has settled.
func _ask_preview() -> void:
	if _quiet or _preview_timer == null:
		return
	_preview_timer.start()


## The preview: the menu steps aside so the map's first day shows behind, and a panel at the
## side holds the map in small with each civ's start marked.
func _build_preview() -> void:
	if _preview_timer == null:
		_preview_timer = Timer.new()
		_preview_timer.one_shot = true
		_preview_timer.wait_time = 0.4
		_preview_timer.timeout.connect(func() -> void: preview_requested.emit(_size, _map, _civs))
		add_child(_preview_timer)
	_preview_panel = _panel(Color(0.05, 0.065, 0.095, 0.92), 18, 18)
	_preview_panel.set_anchors_preset(Control.PRESET_CENTER_LEFT)
	_preview_panel.offset_left = 30
	_preview_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	_preview_panel.visible = false
	_root.add_child(_preview_panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	_preview_panel.add_child(column)
	var title := Label.new()
	title.text = "How the game begins"
	title.add_theme_font_size_override("font_size", 22)
	column.add_child(title)
	_preview_map = Minimap.new()
	_preview_map.longest_side = 380.0
	_preview_map.docked = false
	_preview_map.show_view = false
	_preview_map.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_preview_map)
	_preview_list = RichTextLabel.new()
	_preview_list.bbcode_enabled = true
	_preview_list.fit_content = true
	_preview_list.scroll_active = false
	_preview_list.custom_minimum_size = Vector2(380, 0)
	_preview_list.add_theme_font_size_override("normal_font_size", 14)
	column.add_child(_preview_list)
	var back := Button.new()
	back.text = "Back to the menu"
	back.custom_minimum_size = Vector2(0, 40)
	_style_button(back, ACCENT.darkened(0.1), ACCENT, 10)
	back.pressed.connect(func() -> void:
		_preview_panel.visible = false
		_menu.visible = true)
	column.add_child(back)
	_fill_preview()


## For scripted runs: choose a map and a number of civs, and open the preview.
func open_preview_for(size: String, map_id: String, civs: int) -> void:
	_set_size(size)
	_set_map(map_id)
	_set_civs(civs)
	_open_preview()


func _open_preview() -> void:
	_preview_timer.stop()
	preview_requested.emit(_size, _map, _civs)  # make sure the backdrop is this very choice
	_menu.visible = false
	_preview_panel.visible = true


## The backdrop's map and civs, as each new one arrives (main.gd).
func set_world(init: Dictionary, colors: Array) -> void:
	_world_civs = init.get("civs", [])
	_world_colors = colors
	if _preview_map != null and is_instance_valid(_preview_map):
		_preview_map.setup(init, colors)
		_fill_preview()


func set_tick(data: Dictionary) -> void:
	if _preview_map == null or not is_instance_valid(_preview_map) or not is_instance_valid(_preview_panel) \
			or not _preview_panel.visible:
		return
	_preview_map.update(data)
	var labels: Array = []
	for civ: Dictionary in data["civs"]:
		var civ_id := int(civ["id"])
		if civ["settlements"].is_empty() or civ_id >= _world_civs.size():
			continue
		var home: Dictionary = civ["settlements"][0]
		labels.append([Vector2(int(home["x"]), int(home["y"])), str(_world_civs[civ_id]["name"]), _world_colors[civ_id]])
	_preview_map.labels = labels
	_preview_map.queue_redraw()


func _fill_preview() -> void:
	if _preview_list == null:
		return
	var lines: Array[String] = []
	for civ: Dictionary in _world_civs:
		lines.append("[color=%s]●[/color] [b]%s[/b] starts at %s" % [civ["color"], civ["name"], civ.get("capital_name", "?")])
	_preview_list.text = "\n".join(lines) + "\n[color=#8a93a0]Start the game with the seed left blank and it is this one.[/color]"


## The numbers of civs a choice takes, smallest first.
func _counts(limits: Dictionary) -> Array[int]:
	var counts: Array[int] = []
	if limits.has("counts"):
		for n: Variant in limits["counts"]:
			counts.append(int(n))
	else:
		for n in range(int(limits["min_civs"]), int(limits["max_civs"]) + 1):
			counts.append(n)
	return counts


## The chosen map's entry, or {} when one is to be picked at random.
func _map_entry() -> Dictionary:
	for entry: Dictionary in _spec().get("maps", []):
		if str(entry["id"]) == _map:
			return entry
	return {}


## How many civs can play: the chosen map's range, or its size's.
func _limits() -> Dictionary:
	var entry := _map_entry()
	return entry if not entry.is_empty() else _spec()


func _all_maps() -> Array:
	var maps := []
	for size: Dictionary in _sizes:
		maps.append_array(size["maps"])
	return maps


func _spec() -> Dictionary:
	for size: Dictionary in _sizes:
		if size["id"] == _size:
			return size
	return ANY_SIZE if _size == "random" else _sizes[0]


# -- pieces --------------------------------------------------------------------

func _heading(parent: Control, text: String) -> void:
	var label := Label.new()
	label.text = text.to_upper()
	label.add_theme_font_size_override("font_size", 12)
	label.modulate = Color(1, 1, 1, 0.5)
	parent.add_child(label)


func _panel(color: Color, radius: int, margin: int) -> PanelContainer:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.set_corner_radius_all(radius)
	style.set_content_margin_all(margin)
	style.set_border_width_all(1)
	style.border_color = Color(1, 1, 1, 0.1)
	style.shadow_color = Color(0, 0, 0, 0.45)
	style.shadow_size = 24
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", style)
	return panel


## A large choice: a title and a line or two under it. Returns the button it is.
func _card(parent: Control, title: String, detail: String, size: Vector2, on_pressed: Callable) -> Button:
	var card := Button.new()
	card.custom_minimum_size = size
	card.focus_mode = Control.FOCUS_NONE
	card.pressed.connect(on_pressed)
	_style_button(card, Color(1, 1, 1, 0.06), Color(1, 1, 1, 0.14), 14)
	var text := VBoxContainer.new()
	text.set_anchors_preset(Control.PRESET_FULL_RECT)
	text.alignment = BoxContainer.ALIGNMENT_CENTER
	text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	card.add_child(text)
	var heading := Label.new()
	heading.text = title
	heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	heading.add_theme_font_size_override("font_size", 19)
	text.add_child(heading)
	var body := Label.new()
	body.text = detail
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.add_theme_font_size_override("font_size", 12)
	body.modulate = Color(1, 1, 1, 0.65)
	text.add_child(body)
	card.set_meta("title", heading)
	parent.add_child(card)
	return card


func _round_button(parent: Control, text: String, on_pressed: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(46, 46)
	button.focus_mode = Control.FOCUS_NONE
	button.add_theme_font_size_override("font_size", 24)
	_style_button(button, Color(1, 1, 1, 0.08), Color(1, 1, 1, 0.2), 23)
	button.pressed.connect(on_pressed)
	parent.add_child(button)
	return button


func _style_button(button: Button, normal: Color, hover: Color, radius: int) -> void:
	for state: Array in [["normal", normal], ["hover", hover], ["pressed", hover], ["disabled", Color(1, 1, 1, 0.03)]]:
		var style := StyleBoxFlat.new()
		style.bg_color = state[1]
		style.set_corner_radius_all(radius)
		style.set_content_margin_all(8)
		button.add_theme_stylebox_override(state[0], style)


## The card that is the current choice is lit in the accent colour.
func _light(card: Button, chosen: bool) -> void:
	if chosen:
		_style_button(card, ACCENT.darkened(0.45), ACCENT.darkened(0.3), 14)
		var style: StyleBoxFlat = card.get_theme_stylebox("normal")
		style.set_border_width_all(2)
		style.border_color = ACCENT.lightened(0.2)
	else:
		_style_button(card, Color(1, 1, 1, 0.06), Color(1, 1, 1, 0.14), 14)
