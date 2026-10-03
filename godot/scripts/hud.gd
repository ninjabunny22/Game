extends CanvasLayer
## Overlay UI: sim status and controls (top left), event log (bottom left) and one
## card per civ with era, economy, current research and known techs (right).

signal command_requested(action: String, value: Variant)

const MAX_LOG_LINES := 9
const RESOURCE_LABELS := {"food": "Food", "wood": "Wood", "stone": "Stone", "ore": "Ore", "gold": "Gold"}

var _status: Label
var _pause_button: Button
var _log: RichTextLabel
var _cards_box: VBoxContainer
var _cards := {}  # civ id -> RichTextLabel

var _connected := false
var _tick := 0
var _seed := 0
var _paused := false
var _speed := 2.0
var _civ_info := {}  # civ id -> static info from init
var _tech_names := {}
var _building_names := {}
var _resources: Array = []
var _log_lines: Array[String] = []


func _ready() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	# Status and controls.
	var controls := _panel(root)
	controls.position = Vector2(10, 10)
	var column := VBoxContainer.new()
	controls.add_child(column)
	_status = Label.new()
	column.add_child(_status)
	var buttons := HBoxContainer.new()
	column.add_child(buttons)
	_pause_button = _button(buttons, "Pause", func() -> void: command_requested.emit("toggle_pause", null))
	_button(buttons, "Step", func() -> void: command_requested.emit("step", null))
	_button(buttons, "Slower", func() -> void: request_speed(0.5))
	_button(buttons, "Faster", func() -> void: request_speed(2.0))
	var help := Label.new()
	help.text = "Drag: pan   Right-drag: orbit   Wheel: zoom\nSpace: pause   . : step   - / = : speed"
	help.add_theme_font_size_override("font_size", 12)
	help.modulate = Color(1, 1, 1, 0.6)
	column.add_child(help)

	# Event log.
	var log_panel := _panel(root)
	log_panel.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	log_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	log_panel.offset_left = 10
	log_panel.offset_top = -10
	log_panel.offset_bottom = -10
	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.fit_content = true
	_log.scroll_active = false
	_log.autowrap_mode = TextServer.AUTOWRAP_OFF
	_log.custom_minimum_size = Vector2(360, 0)
	_log.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_log.add_theme_font_size_override("normal_font_size", 13)
	log_panel.add_child(_log)

	# Civ cards.
	var side := _panel(root)
	side.set_anchors_preset(Control.PRESET_RIGHT_WIDE)
	side.offset_left = -390
	side.offset_right = -10
	side.offset_top = 10
	side.offset_bottom = -10
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	side.add_child(scroll)
	_cards_box = VBoxContainer.new()
	_cards_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_cards_box.add_theme_constant_override("separation", 14)
	scroll.add_child(_cards_box)

	_refresh_status()


func set_connected(connected: bool) -> void:
	_connected = connected
	_refresh_status()


func setup(init: Dictionary) -> void:
	_seed = int(init["seed"])
	_resources = init["resources"]
	_tech_names.clear()
	for tech: Dictionary in init["tech_tree"]["techs"]:
		_tech_names[tech["id"]] = tech["name"]
	_building_names.clear()
	for building_id: String in init["buildings"]:
		_building_names[building_id] = init["buildings"][building_id]["name"]

	for card: Node in _cards_box.get_children():
		card.queue_free()
	_cards.clear()
	_civ_info.clear()
	for civ: Dictionary in init["civs"]:
		var civ_id := int(civ["id"])
		_civ_info[civ_id] = civ
		var card := RichTextLabel.new()
		card.bbcode_enabled = true
		card.fit_content = true
		card.scroll_active = false
		card.mouse_filter = Control.MOUSE_FILTER_IGNORE
		card.add_theme_font_size_override("normal_font_size", 13)
		card.add_theme_font_size_override("bold_font_size", 13)
		_cards_box.add_child(card)
		_cards[civ_id] = card
	_log_lines.clear()
	_log.text = ""


func set_status(status: Dictionary) -> void:
	_paused = status["paused"]
	_speed = float(status["speed"])
	_refresh_status()


func update(tick: int, data: Dictionary) -> void:
	_tick = tick
	set_status(data["status"])
	for civ: Dictionary in data["civs"]:
		var civ_id := int(civ["id"])
		if _cards.has(civ_id):
			_cards[civ_id].text = _card_text(_civ_info[civ_id], civ)
	for event: Dictionary in data["events"]:
		if event["kind"] == "building":
			continue  # too frequent to be worth a log line
		var color: String = _civ_info[int(event["civ"])]["color"]
		_log_lines.append("[color=#8a93a0]%5d[/color]  [color=%s]%s[/color]" % [tick, color, event["text"]])
	if _log_lines.size() > MAX_LOG_LINES:
		_log_lines = _log_lines.slice(_log_lines.size() - MAX_LOG_LINES)
	_log.text = "\n".join(_log_lines)


## Multiplies the sim speed; the server clamps it to its allowed range.
func request_speed(factor: float) -> void:
	command_requested.emit("set_speed", _speed * factor)


func _refresh_status() -> void:
	if not _connected:
		_status.text = "Waiting for sim on ws://127.0.0.1:8765 ..."
		return
	var state := "paused" if _paused else "%s ticks/s" % String.num(_speed, 2)
	_status.text = "Tick %d   %s   seed %d" % [_tick, state, _seed]
	_pause_button.text = "Resume" if _paused else "Pause"


func _card_text(info: Dictionary, civ: Dictionary) -> String:
	var lines: Array[String] = []
	lines.append("[font_size=17][b][color=%s]%s[/color][/b][/font_size]  [color=#8a93a0]%s[/color]"
			% [info["color"], info["name"], info["personality"]])
	lines.append("[b]%s[/b] era   Pop %d/%d   Land %d   Buildings %d" % [
		civ["era_name"], int(civ["population"]), int(civ["housing"]),
		int(civ["territory_size"]), civ["buildings"].size(),
	])

	var stock: Array[String] = []
	for res: String in _resources:
		var income := float(civ["income"][res])
		var trend := "#7ccf7c" if income > 0.005 else ("#e07a6a" if income < -0.005 else "#8a93a0")
		stock.append("%s %d [color=%s]%+.1f[/color]" % [RESOURCE_LABELS.get(res, res), int(civ["resources"][res]), trend, income])
	lines.append("   ".join(stock))

	var goal: Variant = civ["goal"]
	if goal != null:
		var what: String = "expand territory" if goal["kind"] == "expand" else _building_names.get(goal["target"], goal["target"])
		lines.append("Saving for: %s" % what)

	var research: Variant = civ["research"]
	if research == null:
		lines.append("Research: none   (%.1f science/tick)" % float(civ["science_rate"]))
	else:
		var progress := "%d%%" % int(float(research["progress"]) * 100.0) if research["paid"] else "gathering materials"
		lines.append("Research: [b]%s[/b] %s   (%.1f science/tick)"
				% [_tech_names.get(research["id"], research["id"]), progress, float(civ["science_rate"])])

	var techs: Array[String] = []
	for tech_id: String in civ["techs"]:
		techs.append(_tech_names.get(tech_id, tech_id))
	lines.append("[color=#8a93a0]Techs (%d/%d):[/color] %s"
			% [techs.size(), _tech_names.size(), ", ".join(techs) if techs else "none yet"])
	return "\n".join(lines)


func _panel(parent: Control) -> PanelContainer:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.07, 0.08, 0.1, 0.84)
	style.set_corner_radius_all(6)
	style.set_content_margin_all(10)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	return panel


func _button(parent: Control, text: String, on_pressed: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(on_pressed)
	parent.add_child(button)
	return button
