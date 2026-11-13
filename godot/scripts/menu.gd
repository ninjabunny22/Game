extends CanvasLayer
## The main menu, and the step after it where a ruler chooses a civ.
##
## A slim panel on the left, over the game behind: (1) how to play (watch every civ play itself,
## or rule one), (2) which map, (3) once a map is picked, the options (how many civs, court
## intrigue, the rulers' difficulty) and Start. Picking a map puts it behind the menu on
## its first day (the simulation starts it paused), and a card at the bottom right shows it in
## small with each civ's start; the game then started is that very one. A game to be ruled
## then shows its civs, paused, for the player to pick one.

signal start_requested(mode: String, size: String, civs: int, map_id: String, difficulty: String, intrigue: String)
signal civ_chosen(civ_id: int)  # -1: watch after all
## The game behind the menu should become the chosen map with this many civs, on its first day.
signal preview_requested(size: String, map_id: String, civs: int)

const Minimap := preload("res://scripts/minimap.gd")
const ACCENT := Color(0.36, 0.62, 1.0)
const GOLD := Color(0.91, 0.74, 0.36)
const GLASS := Color(0.05, 0.065, 0.095, 0.92)
const PANEL_WIDTH := 430.0
const MODES := [
	["watch", "Watch", "Every civ plays itself: sit back and see who wins."],
	["rule", "Rule", "Take one civ in hand; the others play against you."],
]
const INTRIGUE_LEVELS := [
	["off", "Off", "No plots or murders: the houses only age, marry and die."],
	["rare", "Rare", "A plot now and then."],
	["normal", "Normal", "Plots, murders and now and then a rebellion."],
	["frequent", "Frequent", "Courts full of knives: rebellions are common."],
]
const DIFFICULTY_LEVELS := [["easy", "Easy"], ["normal", "Normal"], ["hard", "Hard"]]
## "Any size": a map of any size, picked at random.
const ANY_SIZE := {"id": "random", "name": "Any", "civs": 4, "min_civs": 2, "max_civs": 5, "maps": []}

var _root: Control
var _menu: Control
var _pick: Control
var _sizes: Array = []
var _mode := "watch"
var _size := "medium"
var _civs := 4
var _map := ""  # the map asked for by id, or "" for any of the size's
var _map_chosen := false  # the options and Start appear once a map is picked
var _difficulty := "normal"  # how hard the other civs go on a ruler
var _intrigue := "normal"
var _mode_buttons := {}
var _mode_hint: Label
var _size_tabs := {}
var _map_list: VBoxContainer
var _map_buttons := {}
var _premise: Label  # what the chosen map is about
var _options: Control
var _civ_count: Label
var _civ_hint: Label
var _fewer: Button
var _more: Button
var _intrigue_buttons := {}
var _intrigue_hint: Label
var _difficulty_box: Control
var _difficulty_buttons := {}
var _start: Button
var _quiet := true  # while the menu is being built, choices do not ask for a new backdrop
var _preview_timer: Timer
var _preview_panel: PanelContainer
var _preview_map: Control
var _preview_list: RichTextLabel
var _world_civs: Array = []  # the backdrop's civs, from its init message
var _world_colors: Array = []


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
	_map_chosen = false
	_clear()
	visible = true
	var panel := _panel(GLASS, 18, 22)
	panel.set_anchors_preset(Control.PRESET_LEFT_WIDE)
	panel.offset_left = 16
	panel.offset_top = 16
	panel.offset_bottom = -16
	panel.offset_right = 16 + PANEL_WIDTH
	_root.add_child(panel)
	_menu = panel
	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 14)
	panel.add_child(outer)
	# Everything but Start scrolls, so Start stays in reach on a short window.
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	outer.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 12)
	scroll.add_child(column)

	var title := Label.new()
	title.text = "CivSim"
	title.add_theme_font_size_override("font_size", 32)
	title.add_theme_color_override("font_color", Color(0.96, 0.9, 0.72))
	column.add_child(title)
	var tagline := _note(column, "Civilizations rise, trade, ally and go to war. Watch them, or lead one.")
	tagline.modulate = Color(1, 1, 1, 0.6)

	_step(column, 1, "How to play")
	var modes := _segments(column)
	_mode_buttons.clear()
	for mode: Array in MODES:
		var id: String = mode[0]
		_mode_buttons[id] = _segment(modes, str(mode[1]), func() -> void: _set_mode(id))
	_mode_hint = _note(column, "")

	_step(column, 2, "Map")
	var tabs := _segments(column)
	_size_tabs.clear()
	for size: Dictionary in _sizes + [ANY_SIZE]:
		var id: String = size["id"]
		_size_tabs[id] = _segment(tabs, str(size["name"]), func() -> void: _set_size(id))
	_map_list = VBoxContainer.new()
	_map_list.add_theme_constant_override("separation", 6)
	column.add_child(_map_list)
	_premise = _note(column, "")

	# Step 3: the options, once a map is picked.
	var options := VBoxContainer.new()
	options.add_theme_constant_override("separation", 10)
	column.add_child(options)
	_options = options
	_step(options, 3, "Options")
	var count := HBoxContainer.new()
	count.add_theme_constant_override("separation", 10)
	options.add_child(count)
	var count_label := _label(count, "Civilizations")
	count_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_fewer = _round_button(count, "−", func() -> void: _set_civs(_civs - 1))
	_civ_count = Label.new()
	_civ_count.custom_minimum_size = Vector2(36, 0)
	_civ_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_civ_count.add_theme_font_size_override("font_size", 24)
	count.add_child(_civ_count)
	_more = _round_button(count, "+", func() -> void: _set_civs(_civs + 1))
	_civ_hint = _note(options, "")
	_label(options, "Court intrigue")
	var plots := _segments(options)
	_intrigue_buttons.clear()
	for level: Array in INTRIGUE_LEVELS:
		var id: String = level[0]
		_intrigue_buttons[id] = _segment(plots, str(level[1]), func() -> void: _set_intrigue(id))
	_intrigue_hint = _note(options, "")
	var difficulty := VBoxContainer.new()
	difficulty.add_theme_constant_override("separation", 6)
	options.add_child(difficulty)
	_difficulty_box = difficulty
	_label(difficulty, "How hard the other rulers play")
	var levels := _segments(difficulty)
	_difficulty_buttons.clear()
	for level: Array in DIFFICULTY_LEVELS:
		var id: String = level[0]
		_difficulty_buttons[id] = _segment(levels, str(level[1]), func() -> void: _set_difficulty(id))

	_start = Button.new()
	_start.custom_minimum_size = Vector2(0, 52)
	_start.focus_mode = Control.FOCUS_NONE
	_start.add_theme_font_size_override("font_size", 20)
	_style_button(_start, ACCENT.darkened(0.1), ACCENT, 12)
	_start.pressed.connect(func() -> void:
		start_requested.emit(_mode, _size, _civs, _map, _difficulty, _intrigue))
	outer.add_child(_start)
	_build_preview()

	_set_mode(_mode)
	_set_intrigue(_intrigue)
	_set_difficulty(_difficulty)
	_set_size(_size if _size_tabs.has(_size) else str(_sizes[0]["id"]))
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


func _set_mode(mode: String) -> void:
	_mode = mode
	for id: String in _mode_buttons:
		_light(_mode_buttons[id], id == mode)
	for entry: Array in MODES:
		if entry[0] == mode:
			_mode_hint.text = str(entry[2])
	_difficulty_box.visible = mode == "rule"
	_refresh_start()


func _set_intrigue(level: String) -> void:
	_intrigue = level
	for id: String in _intrigue_buttons:
		_light(_intrigue_buttons[id], id == level)
	for entry: Array in INTRIGUE_LEVELS:
		if entry[0] == level:
			_intrigue_hint.text = str(entry[2])


func _set_difficulty(level: String) -> void:
	_difficulty = level
	for id: String in _difficulty_buttons:
		_light(_difficulty_buttons[id], id == level)


## A size: its maps listed, none picked yet (so the options fold away until one is).
func _set_size(size: String) -> void:
	_size = size
	for id: String in _size_tabs:
		_light(_size_tabs[id], id == size)
	for child in _map_list.get_children():
		child.queue_free()
	_map_buttons.clear()
	var rows: Array = []
	for entry: Dictionary in _spec().get("maps", []):
		rows.append([str(entry["id"]), str(entry["name"]), "%d × %d  ·  %s civs" % [int(entry["width"]),
			int(entry["height"]), _range_text(_counts(entry))]])
	var any := "any of the %d maps" % _all_maps().size() if size == "random" else \
		"any of the %s maps" % str(_spec()["name"]).to_lower()
	rows.append(["", "Surprise me", any])
	for row: Array in rows:
		var id: String = row[0]
		_map_buttons[id] = _row(_map_list, str(row[1]), str(row[2]), func() -> void: _set_map(id))
	_map = ""
	_map_chosen = false
	_civs = int(_spec()["civs"])  # each size starts on the number that suits it
	_premise.text = "Pick a map: it appears behind the menu as it will be on the first day."
	_refresh_choice()


func _set_map(id: String) -> void:
	_map = id
	_map_chosen = true
	var entry := _map_entry()
	if entry.is_empty():
		_premise.text = "A map picked at random from %s." % (
			"all nine" if _size == "random" else "the " + str(_spec()["name"]).to_lower() + " maps")
	else:
		var best := str(entry.get("best", ""))
		_premise.text = str(entry.get("premise", "")) + ("  Best with %s civs." % best if best != "" else "")
	_set_civs(_civs)
	_refresh_choice()
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
	_civ_hint.text = "%s on %s" % [_range_text(counts), where]
	_ask_preview()


## The map rows lit for the choice; the options and the preview shown once a map is picked.
func _refresh_choice() -> void:
	for key: String in _map_buttons:
		_light(_map_buttons[key], _map_chosen and key == _map)
	_options.visible = _map_chosen
	if _preview_panel != null and is_instance_valid(_preview_panel):
		_preview_panel.visible = _map_chosen
	_refresh_start()


func _refresh_start() -> void:
	if _start == null or not is_instance_valid(_start):
		return
	_start.disabled = not _map_chosen
	_start.text = "Pick a map to begin" if not _map_chosen else (
		"Start watching" if _mode == "watch" else "Choose your civ")


## A new backdrop for the choice, once the clicking has settled.
func _ask_preview() -> void:
	if _quiet or _preview_timer == null or not _map_chosen:
		return
	_preview_timer.start()


## The card at the bottom right: the chosen map in small, each civ's start marked, and who
## starts where.
func _build_preview() -> void:
	if _preview_timer == null:
		_preview_timer = Timer.new()
		_preview_timer.one_shot = true
		_preview_timer.wait_time = 0.4
		_preview_timer.timeout.connect(func() -> void: preview_requested.emit(_size, _map, _civs))
		add_child(_preview_timer)
	_preview_panel = _panel(GLASS, 16, 14)
	_preview_panel.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_preview_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	_preview_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_preview_panel.offset_right = -16
	_preview_panel.offset_bottom = -16
	_preview_panel.visible = false
	_root.add_child(_preview_panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	_preview_panel.add_child(column)
	var title := _label(column, "How the game begins")
	title.add_theme_font_size_override("font_size", 16)
	_preview_map = Minimap.new()
	_preview_map.longest_side = 260.0
	_preview_map.docked = false
	_preview_map.show_view = false
	_preview_map.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_preview_map)
	_preview_list = RichTextLabel.new()
	_preview_list.bbcode_enabled = true
	_preview_list.fit_content = true
	_preview_list.scroll_active = false
	_preview_list.custom_minimum_size = Vector2(272, 0)
	_preview_list.add_theme_font_size_override("normal_font_size", 13)
	_preview_list.add_theme_font_size_override("bold_font_size", 13)
	column.add_child(_preview_list)
	_fill_preview()


## For scripted runs: choose a map and a number of civs, as if clicked.
func open_preview_for(size: String, map_id: String, civs: int, mode := "watch") -> void:
	_set_mode(mode)
	_set_size(size)
	_set_map(map_id)
	_set_civs(civs)
	_preview_timer.stop()
	preview_requested.emit(_size, _map, _civs)


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
		lines.append("[color=%s]●[/color] [b]%s[/b]  [color=#a9b0ba]at %s[/color]" % [civ["color"], civ["name"],
			civ.get("capital_name", "?")])
	_preview_list.text = "\n".join(lines)


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

## "2 to 5", or "2 or 4" when a map skips some numbers.
func _range_text(counts: Array[int]) -> String:
	if counts.size() < counts[-1] - counts[0] + 1:
		return " or ".join(counts.map(func(n: int) -> String: return str(n)))
	return "%d to %d" % [counts[0], counts[-1]] if counts.size() > 1 else str(counts[0])


## A numbered step: a small gold number in a ring and its heading.
func _step(parent: Control, number: int, text: String) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	parent.add_child(row)
	var badge := Label.new()
	badge.text = str(number)
	badge.custom_minimum_size = Vector2(22, 22)
	badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	badge.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	badge.add_theme_font_size_override("font_size", 12)
	badge.add_theme_color_override("font_color", Color(0.08, 0.07, 0.05))
	var ring := StyleBoxFlat.new()
	ring.bg_color = GOLD
	ring.set_corner_radius_all(11)
	badge.add_theme_stylebox_override("normal", ring)
	row.add_child(badge)
	var heading := Label.new()
	heading.text = text.to_upper()
	heading.add_theme_font_size_override("font_size", 13)
	heading.add_theme_color_override("font_color", GOLD.lightened(0.2))
	row.add_child(heading)


func _label(parent: Control, text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 15)
	parent.add_child(label)
	return label


## A line of small print under a choice, wrapped to the panel.
func _note(parent: Control, text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size = Vector2(PANEL_WIDTH - 60, 0)
	label.add_theme_font_size_override("font_size", 13)
	label.modulate = Color(1, 1, 1, 0.72)
	parent.add_child(label)
	return label


## A row of buttons that share the width: one of them is the choice.
func _segments(parent: Control) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	parent.add_child(row)
	return row


func _segment(row: HBoxContainer, text: String, on_pressed: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.focus_mode = Control.FOCUS_NONE
	button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	button.custom_minimum_size = Vector2(0, 38)
	button.add_theme_font_size_override("font_size", 15)
	button.pressed.connect(on_pressed)
	_light(button, false)
	row.add_child(button)
	return button


## A map in the list: its name, and its size and civs in small print under it.
func _row(parent: Control, title: String, detail: String, on_pressed: Callable) -> Button:
	var row := Button.new()
	row.custom_minimum_size = Vector2(0, 50)
	row.focus_mode = Control.FOCUS_NONE
	row.pressed.connect(on_pressed)
	var text := VBoxContainer.new()
	text.set_anchors_preset(Control.PRESET_FULL_RECT)
	text.offset_left = 14
	text.alignment = BoxContainer.ALIGNMENT_CENTER
	text.add_theme_constant_override("separation", 0)
	text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(text)
	var heading := Label.new()
	heading.text = title
	heading.add_theme_font_size_override("font_size", 16)
	text.add_child(heading)
	var body := Label.new()
	body.text = detail
	body.add_theme_font_size_override("font_size", 12)
	body.modulate = Color(1, 1, 1, 0.6)
	text.add_child(body)
	_light(row, false)
	parent.add_child(row)
	return row


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


## A large choice: a title and a line or two under it (the ruler's civ cards). Returns the button.
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
	button.custom_minimum_size = Vector2(38, 38)
	button.focus_mode = Control.FOCUS_NONE
	button.add_theme_font_size_override("font_size", 20)
	_style_button(button, Color(1, 1, 1, 0.08), Color(1, 1, 1, 0.2), 19)
	button.pressed.connect(on_pressed)
	parent.add_child(button)
	return button


func _style_button(button: Button, normal: Color, hover: Color, radius: int) -> void:
	for state: Array in [["normal", normal], ["hover", hover], ["pressed", hover], ["disabled", Color(1, 1, 1, 0.04)]]:
		var style := StyleBoxFlat.new()
		style.bg_color = state[1]
		style.set_corner_radius_all(radius)
		style.set_content_margin_all(8)
		button.add_theme_stylebox_override(state[0], style)


## The choice lit in the accent colour, with a bright edge; the others dark glass.
func _light(button: Button, chosen: bool) -> void:
	if chosen:
		_style_button(button, ACCENT.darkened(0.45), ACCENT.darkened(0.3), 10)
		for state: String in ["normal", "hover"]:
			var style: StyleBoxFlat = button.get_theme_stylebox(state)
			style.set_border_width_all(1)
			style.border_width_left = 3
			style.border_color = ACCENT.lightened(0.2)
	else:
		_style_button(button, Color(1, 1, 1, 0.05), Color(1, 1, 1, 0.12), 10)
