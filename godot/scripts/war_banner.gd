extends VBoxContainer
## War declarations, deaths in the royal houses and the like, proclaimed: a banner stands in the middle of the
## screen, on a half-transparent ground, with the declarer's name in its colour, the war's name
## and what it proclaims ("Ossyria shall be punished for taking our lands!"). It stays for
## DAYS days or until its X is clicked; several stack, the newest on top. The words come from
## the simulation (diplomacy/proclamations.py) with the declaration event.

const DAYS := 15
const WIDTH := 640.0

var _banners: Array = []  # [panel, the day it closes]


func _ready() -> void:
	set_anchors_preset(Control.PRESET_CENTER)
	alignment = BoxContainer.ALIGNMENT_CENTER
	add_theme_constant_override("separation", 10)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	grow_horizontal = Control.GROW_DIRECTION_BOTH
	grow_vertical = Control.GROW_DIRECTION_BOTH


## In the middle of the screen, whatever its size and however many banners are stacked.
func _process(_delta: float) -> void:
	size = get_combined_minimum_size()
	position = ((get_parent_area_size() - size) * 0.5).floor()


## A declaration: who declares, on whom, the war's name and the proclamation.
## The names come already in their civs' colours (hud.gd), as BBCode.
func proclaim(day: int, declarer: String, target: String, color: Color, war_name: String, line: String,
		action := Callable()) -> void:
	announce(day, "[b]%s[/b] declares war on [b]%s[/b]" % [declarer, target],
		color, line, "%s begins" % war_name, "res://assets/icons/battle.svg", "", false, action)


## Any proclamation: a title, the words in quotes, a footer, an icon, and a portrait beside
## the words if there is one (greyed for the dead).
func announce(day: int, title_text: String, color: Color, line: String, footer: String, icon: String,
		portrait: String = "", grey := false, action := Callable()) -> void:
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.07, 0.05, 0.05, 0.72)  # slightly see-through
	style.border_color = color
	style.set_border_width_all(2)
	style.border_width_top = 5
	style.set_corner_radius_all(12)
	style.set_content_margin_all(18)
	panel.add_theme_stylebox_override("panel", style)
	panel.custom_minimum_size = Vector2(WIDTH, 0)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 6)
	panel.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var swords := TextureRect.new()
	swords.texture = load(icon)
	swords.custom_minimum_size = Vector2(30, 30)
	swords.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	swords.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	header.add_child(swords)
	var title := RichTextLabel.new()
	title.bbcode_enabled = true
	title.fit_content = true
	title.scroll_active = false
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("normal_font_size", 22)
	title.add_theme_font_size_override("bold_font_size", 22)
	title.text = title_text
	header.add_child(title)
	var close := Button.new()
	close.icon = load("res://assets/icons/close.svg")
	close.expand_icon = true
	close.flat = true
	close.focus_mode = Control.FOCUS_NONE
	close.custom_minimum_size = Vector2(30, 30)
	close.tooltip_text = "Close"
	header.add_child(close)
	var body := HBoxContainer.new()
	body.add_theme_constant_override("separation", 14)
	column.add_child(body)
	if portrait != "" and ResourceLoader.exists(portrait):
		var face := TextureRect.new()
		face.texture = load(portrait)
		face.custom_minimum_size = Vector2(96, 120)
		face.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		face.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		if grey:
			face.modulate = Color(0.62, 0.62, 0.62)
		body.add_child(face)
	var words := _rich("[center]“%s”[/center]" % line, 26, Color(0.98, 0.93, 0.8))
	words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	words.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	body.add_child(words)
	var name_label := _rich("[center]%s  ·  day %d[/center]" % [footer, day], 14, Color(0.75, 0.7, 0.62))
	column.add_child(name_label)
	if action.is_valid():  # clicking the banner (not its X) goes to what it tells of
		panel.mouse_filter = Control.MOUSE_FILTER_STOP
		panel.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		panel.tooltip_text = "Click to go there"
		panel.gui_input.connect(func(event: InputEvent) -> void:
			if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
				action.call())
	add_child(panel)
	move_child(panel, 0)  # the newest on top
	move_to_front()  # over the cards and the other panels
	var entry := [panel, day + DAYS]
	_banners.append(entry)
	close.pressed.connect(func() -> void: _drop(entry))


## Text with BBCode (names in their civs' colours), wrapped and as tall as it needs.
func _rich(text: String, font_size: int, color: Color) -> RichTextLabel:
	var label := RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("normal_font_size", font_size)
	label.add_theme_font_size_override("italics_font_size", font_size)
	label.add_theme_font_size_override("bold_font_size", font_size)
	label.add_theme_color_override("default_color", color)
	label.text = text
	return label


## Called every day: banners whose time is up go.
func tick(day: int) -> void:
	for entry: Array in _banners.duplicate():
		if day >= int(entry[1]):
			_drop(entry)


func clear() -> void:
	for entry: Array in _banners.duplicate():
		_drop(entry)


func _drop(entry: Array) -> void:
	if entry in _banners:
		_banners.erase(entry)
		(entry[0] as Node).queue_free()
