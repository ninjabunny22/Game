extends CanvasLayer
## Overlay UI: sim status and controls (top left), event log (bottom left) and one
## card per civ with era, economy, army, diplomacy, research and known techs (right).

signal command_requested(action: String, value: Variant)

const LINK_LEGEND := "[color=#ff4033]━[/color] war   [color=#59a6ff]━[/color] alliance   [color=#59e666]━[/color] trade   [color=#aaaaaa]━[/color] neutral"

const MAX_LOG_LINES := 9
const MAX_TECHS_LISTED := 6  # the most recent ones; the full list no longer fits a card
const RESOURCE_LABELS := {"food": "Food", "wood": "Wood", "stone": "Stone", "ore": "Ore", "gold": "Gold", "water": "Water"}
const STANCE_COLORS := {"trade": "#7ccf7c", "ally": "#6fb7ff", "ignore": "#8a93a0", "aggression": "#e07a6a"}

var _status: Label
var _pause_button: Button
var _log: RichTextLabel
var _cards_box: VBoxContainer
var _diplomacy_panel: PanelContainer
var _diplomacy: RichTextLabel
var _cards := {}  # civ id -> RichTextLabel

var _connected := false
var _tick := 0
var _seed := 0
var _paused := false
var _speed := 2.0
var _civ_info := {}  # civ id -> static info from init
var _tech_names := {}
var _building_names := {}
var _unit_names := {}
var _region_names := {}
var _resources: Array = []
var _log_lines: Array[String] = []
var _relations := {}  # "a:b" with a < b -> relation from the latest tick
var _deals := {}  # "a:b" with a < b -> deal


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
	_button(buttons, "Diplomacy", toggle_diplomacy)
	var help := Label.new()
	help.text = "Drag: pan   Right-drag: orbit   Wheel: zoom\nSpace: pause   . : step   - / = : speed   Tab: diplomacy"
	help.add_theme_font_size_override("font_size", 12)
	help.modulate = Color(1, 1, 1, 0.6)
	column.add_child(help)
	var legend := RichTextLabel.new()
	legend.bbcode_enabled = true
	legend.fit_content = true
	legend.scroll_active = false
	legend.autowrap_mode = TextServer.AUTOWRAP_OFF
	legend.mouse_filter = Control.MOUSE_FILTER_IGNORE
	legend.add_theme_font_size_override("normal_font_size", 12)
	legend.text = LINK_LEGEND
	column.add_child(legend)

	# Diplomacy: every war, alliance and trade deal in force. Toggled with the button or Tab.
	_diplomacy_panel = _panel(root)
	_diplomacy_panel.position = Vector2(10, 178)
	_diplomacy_panel.custom_minimum_size = Vector2(430, 0)
	_diplomacy_panel.visible = false
	_diplomacy = RichTextLabel.new()
	_diplomacy.bbcode_enabled = true
	_diplomacy.fit_content = true
	_diplomacy.scroll_active = false
	_diplomacy.custom_minimum_size = Vector2(410, 0)
	_diplomacy.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_diplomacy.add_theme_font_size_override("normal_font_size", 13)
	_diplomacy.add_theme_font_size_override("bold_font_size", 13)
	_diplomacy_panel.add_child(_diplomacy)

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
	_region_names.clear()
	for region: Dictionary in init["regions"]:
		_region_names[int(region["id"])] = region["name"]
	_unit_names.clear()
	for unit_id: String in init["unit_types"]:
		_unit_names[unit_id] = init["unit_types"][unit_id]["name"]
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
	_relations.clear()
	for relation: Dictionary in data["relations"]:
		_relations["%d:%d" % [int(relation["a"]), int(relation["b"])]] = relation
	_deals.clear()
	for deal: Dictionary in data["deals"]:
		_deals["%d:%d" % [mini(int(deal["a"]), int(deal["b"])), maxi(int(deal["a"]), int(deal["b"]))]] = deal
	for civ: Dictionary in data["civs"]:
		var civ_id := int(civ["id"])
		if _cards.has(civ_id):
			_cards[civ_id].text = _card_text(_civ_info[civ_id], civ)
	if _diplomacy_panel.visible:
		_diplomacy.text = _diplomacy_text_panel(data)
	for event: Dictionary in data["events"]:
		if event["kind"] in ["building", "demolition"]:
			continue  # too frequent to be worth a log line
		var color: String = _civ_info[int(event["civ"])]["color"]
		_log_lines.append("[color=#8a93a0]%5d[/color]  [color=%s]%s[/color]" % [tick, color, event["text"]])
	if _log_lines.size() > MAX_LOG_LINES:
		_log_lines = _log_lines.slice(_log_lines.size() - MAX_LOG_LINES)
	_log.text = "\n".join(_log_lines)


func toggle_diplomacy() -> void:
	_diplomacy_panel.visible = not _diplomacy_panel.visible


func _civ_name(civ_id: int) -> String:
	var info: Dictionary = _civ_info[civ_id]
	return "[color=%s]%s[/color]" % [info["color"], info["name"]]


## Wars (grouped by name, since allies join the same war), alliances and trade deals.
func _diplomacy_text_panel(data: Dictionary) -> String:
	var lines: Array[String] = []
	var wars := {}  # name -> list of relations
	var alliances: Array = []
	for relation: Dictionary in data["relations"]:
		if relation["status"] == "war":
			var name: String = str(relation["name"]) if relation["name"] != null else "Unnamed war"
			if not wars.has(name):
				wars[name] = []
			wars[name].append(relation)
		elif relation["status"] == "alliance":
			alliances.append(relation)

	lines.append("[b][color=#ff6a5a]WARS[/color][/b]")
	if wars.is_empty():
		lines.append("[color=#8a93a0]  The world is at peace.[/color]")
	for name: String in wars:
		var fronts: Array = wars[name]
		var started := _tick
		for front: Dictionary in fronts:
			started = mini(started, int(front["war"]["started"]))
		lines.append("[b]%s[/b]  [color=#8a93a0]%d ticks[/color]" % [name, _tick - started])
		for front: Dictionary in fronts:
			var war: Dictionary = front["war"]
			# The side that declared is named first.
			var attacker := int(war["declarer"]) if war["declarer"] != null else int(front["a"])
			var defender := int(front["b"]) if attacker == int(front["a"]) else int(front["a"])
			var note := ""
			if war["defending"] != null:
				note = "  [color=#8a93a0](defending %s)[/color]" % _civ_info[int(war["defending"])]["name"]
			elif war["betrayer"] != null:
				note = "  [color=#e07a6a](betrayal)[/color]"
			lines.append("  %s attacks %s%s" % [_civ_name(attacker), _civ_name(defender), note])
			lines.append("  [color=#8a93a0]tiles taken %d / %d   losses %d / %d[/color]" % [
				int(war["tiles_taken"][str(attacker)]), int(war["tiles_taken"][str(defender)]),
				int(war["casualties"][str(attacker)]), int(war["casualties"][str(defender)]),
			])

	lines.append("")
	lines.append("[b][color=#6fb7ff]ALLIANCES[/color][/b]")
	if alliances.is_empty():
		lines.append("[color=#8a93a0]  None.[/color]")
	for alliance: Dictionary in alliances:
		var name: String = str(alliance["name"]) if alliance["name"] != null else "Alliance"
		lines.append("[b]%s[/b]" % name)
		lines.append("  %s and %s  [color=#8a93a0]formed tick %d (%d ticks ago)[/color]" % [
			_civ_name(int(alliance["a"])), _civ_name(int(alliance["b"])), int(alliance["since"]), _tick - int(alliance["since"]),
		])

	lines.append("")
	lines.append("[b][color=#7ccf7c]TRADE DEALS[/color][/b]")
	if data["deals"].is_empty():
		lines.append("[color=#8a93a0]  None.[/color]")
	for deal: Dictionary in data["deals"]:
		lines.append("  %s sends %s %s/tick,  %s sends %s %s/tick  [color=#8a93a0]%d ticks left[/color]" % [
			_civ_name(int(deal["a"])), String.num(float(deal["a_gives"]["rate"]), 2), deal["a_gives"]["resource"],
			_civ_name(int(deal["b"])), String.num(float(deal["b_gives"]["rate"]), 2), deal["b_gives"]["resource"],
			int(deal["ends"]) - _tick,
		])
	return "\n".join(lines)


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
	if not civ["alive"]:
		lines.append("[color=#e07a6a]Destroyed: its last capital has fallen[/color]")
		return "\n".join(lines)
	var regions_held: Array[String] = []
	for region_id: Variant in civ["regions"]:
		regions_held.append(_region_names.get(int(region_id), "?"))
	lines.append("[color=#8a93a0]Regions (%d):[/color] %s" % [regions_held.size(), ", ".join(regions_held)])
	lines.append("[b]%s[/b] era   Pop %d/%d   Land %d   Buildings %d" % [
		civ["era_name"], int(civ["population"]), int(civ["housing"]),
		int(civ["territory_size"]), civ["buildings"].size(),
	])

	var stock: Array[String] = []
	for res: String in _resources:
		var income := float(civ["income"][res])
		var trend := "#7ccf7c" if income > 0.005 else ("#e07a6a" if income < -0.005 else "#8a93a0")
		var held := int(civ["resources"][res])
		var cap := int(civ["storage"][res])
		# Amber once a store is full: nothing more of it is produced until there is room.
		var amount := "[color=#e8b04a]%d/%d[/color]" % [held, cap] if held >= cap else "%d/%d" % [held, cap]
		stock.append("%s %s [color=%s]%+.1f[/color]" % [RESOURCE_LABELS.get(res, res), amount, trend, income])
	lines.append("   ".join(stock))
	if civ["thirsty"]:
		lines.append("[color=#e07a6a]Out of water: the population is shrinking[/color]")
	lines.append(_army_text(civ))
	lines.append("[color=#8a93a0]Diplomacy points[/color] %d   %s" % [int(civ["diplomacy_points"]), _diplomacy_text(int(civ["id"]), civ)])
	if civ["thinking"]:
		lines.append("[color=#8a93a0]Strategist is thinking ...[/color]")
	elif civ["reason"] != "":
		lines.append("[color=#8a93a0]\"%s\"[/color]" % civ["reason"])

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
	var listed := ", ".join(techs) if techs else "none yet"
	if techs.size() > MAX_TECHS_LISTED:
		listed = "... " + ", ".join(techs.slice(techs.size() - MAX_TECHS_LISTED))
	lines.append("[color=#8a93a0]Techs (%d):[/color] %s" % [techs.size(), listed])
	return "\n".join(lines)


func _army_text(civ: Dictionary) -> String:
	var text := "Army %d   strength %d" % [int(civ["soldiers"]), int(civ["army_strength"])]
	var mix: Array[String] = []
	for unit_id: String in civ["units"]:
		mix.append("%d %s" % [int(civ["units"][unit_id]), _unit_names.get(unit_id, unit_id).to_lower()])
	if not mix.is_empty():
		text += "\n[color=#8a93a0]%s[/color]" % ", ".join(mix)
	var problems: Array[String] = []
	if civ["unpaid"]:
		problems.append("unpaid")
	if civ["unsupplied"]:
		problems.append("no ore")
	if not problems.is_empty():
		text += "   [color=#e07a6a](%s)[/color]" % ", ".join(problems)
	if int(civ["distrusted_for"]) > 0:
		text += "\n[color=#e07a6a]Distrusted for betrayal: %d ticks left[/color]" % int(civ["distrusted_for"])
	return text


## One entry per other civ: what actually holds between them (war, alliance, a
## running deal), otherwise the stance this civ has taken toward them.
func _diplomacy_text(civ_id: int, civ: Dictionary) -> String:
	var parts: Array[String] = []
	for other_key: String in civ["stances"]:
		var other := int(other_key)
		var key := "%d:%d" % [mini(civ_id, other), maxi(civ_id, other)]
		var stance: String = civ["stances"][other_key]
		var label := stance
		var color: String = STANCE_COLORS.get(stance, "#8a93a0")
		var status: String = _relations[key]["status"] if _relations.has(key) else "peace"
		if status == "war":
			label = "AT WAR"
			color = "#ff5a4a"
		elif status == "alliance":
			label = "allied"
			color = STANCE_COLORS["ally"]
		if _deals.has(key):
			label += " + deal"
		elif status == "peace" and _relations.has(key) and _relations[key]["truce"]:
			label += " (truce)"
		parts.append("[color=%s]%s[/color] [color=%s]%s[/color]" % [_civ_info[other]["color"], _civ_info[other]["name"], color, label])
	return "   ".join(parts)


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
