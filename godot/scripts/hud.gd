extends CanvasLayer
## Overlay UI. Watching, it is one bar across the top (the date and controls, and a
## scoreboard chip per civ), one drawer on the right with everything about the civ whose chip
## was clicked (overview, army, diplomacy, its path in the tech tree), the minimap, and the
## log. Ruling a civ, the older layout stays: the ruler's panel, a card per civ, the log.

signal command_requested(action: String, value: Variant)
signal follow_requested(civ_id: int)  # keep the camera on this civ's largest army or capital; -1 to stop
signal jump_requested(x: float, y: float)  # a clicked event: bring the camera to this tile

const TechTree := preload("res://scripts/tech_tree.gd")
const WarBanner := preload("res://scripts/war_banner.gd")
const FamilyTree := preload("res://scripts/family_tree.gd")
const WarsPanel := preload("res://scripts/wars_panel.gd")
var _wars: PanelContainer  # the ongoing wars, top right while watching
var _family_tree: PanelContainer
const LINK_LEGEND := "[color=#ff4033]━[/color] war   [color=#59a6ff]━[/color] alliance   [color=#59e666]━[/color] trade   [color=#aaaaaa]━[/color] neutral"

const MAX_HEADLINES := 5
const ROUTINE_WINDOW := 100  # days over which routine events are counted for the summary line
# Events worth a line of their own. Everything else is only counted.
const HEADLINE_KINDS := ["war", "diplomacy", "region", "era", "family", "rally"]
const ROUTINE_LABELS := {"capture": "buildings captured", "village": "village changes", "tech": "discoveries",
	"trade": "trade changes", "building": "buildings finished", "demolition": "buildings pulled down"}
const MAX_TECHS_LISTED := 6
## What each building is for, in a few words (the castle popup's list).
const PURPOSES := {"house": "houses people", "farm": "food", "lumber_camp": "wood", "mine": "stone, and ore from level 2",
	"storehouse": "stores every resource", "market": "gold", "school": "research", "workshop": "builds faster, more wood, stone, ore",
	"barracks": "trains soldiers, army strength", "stables": "horses", "harbour": "food, gold, boats"}  # the most recent ones; the full list no longer fits a card
const RESOURCE_LABELS := {"food": "Food", "wood": "Wood", "stone": "Stone", "ore": "Ore", "gold": "Gold", "water": "Water"}
const STANCE_COLORS := {"trade": "#7ccf7c", "ally": "#6fb7ff", "ignore": "#8a93a0", "aggression": "#e07a6a"}

var _status: Label
var _spectating := true  # nobody rules a civ: the watch layout
var _bar: PanelContainer  # the top bar
var _chips: HBoxContainer  # one scoreboard chip per civ, in the bar
var _chip_buttons := {}  # civ id -> Button
var _side: PanelContainer  # the civ cards (ruler mode)
var _ruler_panel: PanelContainer
var _log_panel: PanelContainer
var _drawer: PanelContainer  # everything about one civ, while watching
var _drawer_civ := -1
var _drawer_title: RichTextLabel
var _drawer_tabs: TabBar
var _drawer_text: RichTextLabel
var _follow_button: Button
var _following := -1
var _last_data := {}
# The ticker (the newest headline, at the bottom) and the chronicle (every headline, by civ).
var _ticker: PanelContainer
var _ticker_text: RichTextLabel
var _ticker_age := 0.0
var _chronicle: PanelContainer
var _chronicle_text: RichTextLabel
var _chronicle_filter: OptionButton
var _chronicle_entries: Array = []  # [civ ids involved, bbcode line, the event, routine?]
var _chronicle_routine: CheckBox  # the routine events listed too
var _routine_footer := ""
const CHRONICLE_LIMIT := 1200
const TICKER_BRIGHT := 6.0  # seconds a new headline stays bright before it dims
var _pause_button: Button
var _tech_tree: PanelContainer  # tech_tree.gd: the tree as the civs climb it, while spectating
var _banners: VBoxContainer  # war_banner.gd: declarations of war, proclaimed mid-screen
var _legend: RichTextLabel
var _icons := {}  # icon name -> Texture2D
var _log: RichTextLabel
var _cards_box: VBoxContainer
var _cards_scroll: ScrollContainer
var _reserved_bottom_right := 0.0  # height kept clear at the bottom right (the minimap)
var _diplomacy_panel: PanelContainer
var _castle_panel: PanelContainer
var _regions_needed := 0  # regions that win by domination (with every rival's home seat)
var _regions_at := {}  # capital tile -> the region it rules, from init
var _castle_text: RichTextLabel
var _castle_title: Label
var _castle_at := Vector2i(-1, -1)  # the castle being looked at, by tile; (-1, -1) for none
var _castle_anchor := Vector3.INF  # the point above that castle the panel stands beside, in the world
var _diplomacy: RichTextLabel
var _cards := {}  # civ id -> RichTextLabel
var _expanded := -1  # civ whose card shows full detail, or -1
var _latest := {}  # civ id -> its state in the latest tick
var _paused_banner: Label
var _ruler_box: VBoxContainer  # the player's own panel: which civ they rule and their orders
var _victory: Variant = null  # who has won and how, once the game is decided
var _ruler_folded := false
var _ruler_signature := ""  # what the panel was last built from, so it is only rebuilt on a change
var _routine: Array = []  # [tick, kind] of recent routine events

var _connected := false
var _tick := 0
var _seed := 0
var _map_name := ""
var _popup: Control = null  # the dialogue asking the player something that will not wait
var _paused := false
var _waiting_for: Array = []  # civ ids whose strategist the clock is being held for
var _armies := {}  # civ id -> that civ's armies, from the latest tick
var _speed := 2.0
var _civ_info := {}  # civ id -> static info from init
var _tech_names := {}
var _building_names := {}
var _unit_names := {}
var _region_names := {}
var _resources: Array = []
var _log_lines: Array[String] = []
var _help: Label
var _relations := {}  # "a:b" with a < b -> relation from the latest tick
var _deals := {}  # "a:b" with a < b -> deal


var _leave: ConfirmationDialog  # the Esc "back to the menu?" question


func _ready() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	# The bar across the top: the date and the controls, then a chip per civ.
	var controls := _panel(root)
	_bar = controls
	controls.anchor_right = 1.0
	controls.offset_left = 10
	controls.offset_right = -10
	controls.offset_top = 8
	var column := VBoxContainer.new()
	controls.add_child(column)
	var top_row := HBoxContainer.new()
	top_row.add_theme_constant_override("separation", 10)
	column.add_child(top_row)
	_status = Label.new()
	_status.add_theme_font_size_override("font_size", 16)
	_status.custom_minimum_size = Vector2(150, 0)
	top_row.add_child(_status)
	# One row of icons; each says what it does, and its key, when the mouse rests on it.
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 4)
	top_row.add_child(buttons)
	var gap := Control.new()
	gap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top_row.add_child(gap)
	_chips = HBoxContainer.new()
	_chips.add_theme_constant_override("separation", 6)
	top_row.add_child(_chips)
	_pause_button = _icon_button(buttons, "pause", "Pause / resume  (Space)",
		func() -> void: command_requested.emit("toggle_pause", null))
	_icon_button(buttons, "step", "One day on  ( . )", func() -> void: command_requested.emit("step", null))
	_icon_button(buttons, "slower", "Slower  ( - )", func() -> void: request_speed(0.5))
	_icon_button(buttons, "faster", "Faster  ( = )", func() -> void: request_speed(2.0))
	_icon_button(buttons, "diplomacy", "Diplomacy: every war, alliance and trade deal  (Tab)", toggle_diplomacy)
	var help := Label.new()
	help.text = ("Drag: pan   Right-drag: orbit   Wheel: zoom   B: region borders\n"
			+ "Space: pause   . : step   - / = : speed   Tab: diplomacy   T: tech tree   1-5: a civ\n"
			+ "[ and ] : smaller / larger text   Esc: close, or the menu   L: chronicle\n"
			+ "Lines between castles: red war, blue alliance, green trade, grey neutral")
	help.add_theme_font_size_override("font_size", 12)
	help.modulate = Color(1, 1, 1, 0.6)
	help.visible = false  # H or the ? button shows the keys
	column.add_child(help)
	_help = help
	_icon_button(buttons, "chronicle", "The chronicle: every headline so far  (L)", toggle_chronicle)
	_icon_button(buttons, "help", "Keys and controls  (H)", toggle_help)
	var legend := RichTextLabel.new()
	legend.bbcode_enabled = true
	legend.fit_content = true
	legend.scroll_active = false
	legend.autowrap_mode = TextServer.AUTOWRAP_OFF
	legend.mouse_filter = Control.MOUSE_FILTER_IGNORE
	legend.add_theme_font_size_override("normal_font_size", 12)
	legend.text = LINK_LEGEND
	legend.visible = false  # the legend icon shows it
	column.add_child(legend)
	_legend = legend

	# The ruler's panel: take a civ in hand, and give it its orders.
	var ruler_panel := _panel(root)
	_ruler_panel = ruler_panel
	ruler_panel.position = Vector2(10, 124)
	_ruler_box = VBoxContainer.new()
	_ruler_box.custom_minimum_size = Vector2(420, 0)
	_ruler_box.add_theme_constant_override("separation", 6)
	ruler_panel.add_child(_ruler_box)

	# Diplomacy: every war, alliance and trade deal in force. Toggled with the button or Tab.
	_diplomacy_panel = _panel(root)
	_diplomacy_panel.position = Vector2(470, 124)
	_diplomacy_panel.custom_minimum_size = Vector2(390, 0)
	_diplomacy_panel.visible = false
	_diplomacy = RichTextLabel.new()
	_diplomacy.bbcode_enabled = true
	_diplomacy.fit_content = true
	_diplomacy.scroll_active = false
	_diplomacy.custom_minimum_size = Vector2(370, 0)
	_diplomacy.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_diplomacy.add_theme_font_size_override("normal_font_size", 13)
	_diplomacy.add_theme_font_size_override("bold_font_size", 13)
	_diplomacy_panel.add_child(_diplomacy)
	# The ruler's panel sits just below the bar, however tall it is (the legend and the help
	# add lines); diplomacy opens beside the bar, clear of the civ cards.
	var place := func() -> void:
		var below := controls.position.y + controls.size.y + 8.0
		ruler_panel.position.y = below
		_diplomacy_panel.position = Vector2(470, below)
		_side.offset_top = below
		_drawer.offset_top = below
		_wars.offset_top = below + 6
	controls.resized.connect(place)

	# Event log.
	var log_panel := _panel(root)
	_log_panel = log_panel
	log_panel.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	log_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	log_panel.offset_left = 10
	log_panel.offset_top = -10
	log_panel.offset_bottom = -10
	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.fit_content = true
	_log.scroll_active = false
	_log.custom_minimum_size = Vector2(440, 0)
	_log.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_log.add_theme_font_size_override("normal_font_size", 13)
	log_panel.add_child(_log)

	_build_ticker(root)

	# Civ cards: two lines each, so all of them always fit; one at a time opens to full detail.
	var side := _panel(root)
	_side = side
	side.anchor_left = 1.0
	side.anchor_right = 1.0
	side.offset_left = -400
	side.offset_right = -10
	side.offset_top = 10
	# The tech tree, opened from the tree button beside the cards (only while spectating).
	_tech_tree = TechTree.new()
	_tech_tree.set_anchors_preset(Control.PRESET_FULL_RECT)
	_tech_tree.offset_left = 20
	_tech_tree.offset_top = 100  # below the icon bar
	_tech_tree.offset_right = -20
	_tech_tree.offset_bottom = -20
	add_child(_tech_tree)  # beside the overlay's root, so it can come in front of the minimap too
	_family_tree = FamilyTree.new()
	add_child(_family_tree)
	_wars = WarsPanel.new()
	root.add_child(_wars)  # under the banners, which stand in front of it
	_banners = WarBanner.new()
	root.add_child(_banners)
	# The cards scroll when there are more than fit above the minimap.
	_cards_scroll = ScrollContainer.new()
	_cards_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	side.add_child(_cards_scroll)
	_cards_box = VBoxContainer.new()
	_cards_box.custom_minimum_size = Vector2(370, 0)
	_cards_box.add_theme_constant_override("separation", 10)
	_cards_box.resized.connect(_fit_cards)
	_cards_scroll.add_child(_cards_box)

	_build_drawer(root)

	# A castle clicked on the map: who holds it, who is inside and with how many. It stands
	# beside the castle and follows it as the camera moves; closed by its X or a click elsewhere.
	_castle_panel = _panel(root)
	_castle_panel.visible = false
	(_castle_panel.get_theme_stylebox("panel") as StyleBoxFlat).bg_color.a = 0.96  # drawn over the cards, it must not show them through
	var castle_column := VBoxContainer.new()
	castle_column.add_theme_constant_override("separation", 6)
	_castle_panel.add_child(castle_column)
	var title_bar := HBoxContainer.new()
	castle_column.add_child(title_bar)
	_castle_title = Label.new()
	_castle_title.add_theme_font_size_override("font_size", 16)
	_castle_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_bar.add_child(_castle_title)
	var close := _button(title_bar, "×", func() -> void: show_castle(-1, -1))
	close.tooltip_text = "Close"
	var rule := HSeparator.new()
	rule.modulate = Color(1, 1, 1, 0.3)
	castle_column.add_child(rule)
	_castle_text = RichTextLabel.new()
	_castle_text.bbcode_enabled = true
	_castle_text.fit_content = true
	_castle_text.scroll_active = false
	_castle_text.custom_minimum_size = Vector2(320, 0)
	_castle_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_castle_text.add_theme_font_size_override("normal_font_size", 13)
	_castle_text.add_theme_font_size_override("bold_font_size", 13)
	castle_column.add_child(_castle_text)

	# Impossible to miss when the sim is paused.
	_paused_banner = Label.new()
	_paused_banner.text = "PAUSED"
	_paused_banner.add_theme_font_size_override("font_size", 30)
	_paused_banner.add_theme_color_override("font_color", Color(1.0, 0.85, 0.3))
	_paused_banner.add_theme_color_override("font_outline_color", Color(0, 0, 0))
	_paused_banner.add_theme_constant_override("outline_size", 8)
	_paused_banner.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_paused_banner.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_paused_banner.offset_top = 14
	_paused_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_paused_banner.visible = false
	root.add_child(_paused_banner)

	_refresh_status()


## The player's panel. With no civ in hand it offers the living ones; with one, the orders a
## ruler can give: what the realm concentrates on, what to research and build next, and how
## to stand toward each other civ. "Auto" leaves a choice to the civ itself.
func _refresh_ruler(ruler: Variant) -> void:
	var others: Array = []
	for civ_id: int in _latest:
		if _latest[civ_id]["alive"]:
			others.append([civ_id, _relation_word(ruler, civ_id)])
	var signature := JSON.stringify([ruler, others, _ruler_folded])
	if signature == _ruler_signature:
		return
	_ruler_signature = signature
	for child in _ruler_box.get_children():
		child.queue_free()

	if ruler == null:
		_small_label(_ruler_box, "Rule a civ yourself, or just watch:")
		var row := HBoxContainer.new()
		_ruler_box.add_child(row)
		for pair: Array in others:
			var civ_id: int = pair[0]
			var pick := _button(row, str(_civ_info[civ_id]["name"]), func() -> void: command_requested.emit("take_control", {"civ": civ_id}))
			pick.add_theme_color_override("font_color", Color.html(_civ_info[civ_id]["color"]).lightened(0.25))
		return

	var mine := int(ruler["civ"])
	var header := HBoxContainer.new()
	_ruler_box.add_child(header)
	var title := Label.new()
	title.text = ("You rule %s" if ruler["alive"] else "%s has fallen") % str(_civ_info[mine]["name"])
	title.add_theme_font_size_override("font_size", 18)
	title.add_theme_color_override("font_color", Color.html(_civ_info[mine]["color"]).lightened(0.25))
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	# The orders fold away, so the panel does not sit over the map while nothing is being changed.
	_button(header, "Orders ▸" if _ruler_folded else "Orders ▾", func() -> void:
		_ruler_folded = not _ruler_folded
		_refresh_ruler(ruler))
	_button(header, "Hand back" if ruler["alive"] else "Watch on", func() -> void: command_requested.emit("release_control", {}))
	if not ruler["alive"]:
		return
	_show_popup(ruler)
	var leading: Variant = ruler.get("rally")
	if leading != null:
		var rally_row := HBoxContainer.new()
		_ruler_box.add_child(rally_row)
		var rally_text := Label.new()
		rally_text.text = ("Your rally gathers at %s for %s: %d days" % [leading["city"], leading["target"], int(leading["days_left"])]
				if leading["state"] == "gathering" else "Your rally is marching on %s" % leading["target"])
		rally_text.add_theme_font_size_override("font_size", 13)
		rally_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		rally_row.add_child(rally_text)
		_button(rally_row, "Call off", func() -> void: command_requested.emit("cancel_rally", {}))
	else:
		for enemy: Variant in ruler.get("rally_targets", []):
			var foe := int(enemy)
			var call_row := HBoxContainer.new()
			_ruler_box.add_child(call_row)
			_button(call_row, "Call a rally against %s" % str(_civ_info[foe]["name"]), func() -> void:
				command_requested.emit("start_rally", {"civ": foe}))
	var standing: Variant = ruler.get("reinforcing")
	if standing != null:
		var stand_row := HBoxContainer.new()
		_ruler_box.add_child(stand_row)
		var stand_text := Label.new()
		var with_whom := str(_civ_info[int(standing["civ"])]["name"])
		stand_text.text = ("Your army stands with %s in %s" % [with_whom, standing["city"]]
				if standing["city"] != null else "An army will set out to stand with %s" % with_whom)
		stand_text.add_theme_font_size_override("font_size", 13)
		stand_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		stand_row.add_child(stand_text)
		_button(stand_row, "Call back", func() -> void: command_requested.emit("recall_reinforcement", {}))
	else:
		for friend: Variant in ruler.get("reinforce_targets", []):
			var ally := int(friend)
			var send_row := HBoxContainer.new()
			_ruler_box.add_child(send_row)
			_button(send_row, "Reinforce %s" % str(_civ_info[ally]["name"]), func() -> void:
				command_requested.emit("reinforce_ally", {"civ": ally}))
	for offer: Dictionary in ruler.get("proposals", []):
		if offer.get("popup", false):
			continue  # asked in a dialogue of its own
		var from := int(offer["civ"])
		var row := HBoxContainer.new()
		_ruler_box.add_child(row)
		var words := Label.new()
		words.text = str(offer["text"])
		words.add_theme_font_size_override("font_size", 13)
		words.add_theme_color_override("font_color", Color.html(_civ_info[from]["color"]).lightened(0.25))
		words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(words)
		_button(row, "Accept", func() -> void:
			command_requested.emit("answer_proposal", {"civ": from, "kind": offer["kind"], "accept": true}))
		_button(row, "Refuse", func() -> void:
			command_requested.emit("answer_proposal", {"civ": from, "kind": offer["kind"], "accept": false}))
	if _ruler_folded:
		return

	_small_label(_ruler_box, "The realm concentrates on")
	var focuses := HBoxContainer.new()
	_ruler_box.add_child(focuses)
	for focus: String in ruler["focuses"]:
		var chosen: bool = focus == ruler["focus"]
		_choice(focuses, focus.capitalize(), chosen, func() -> void: command_requested.emit("set_focus", {"focus": focus}))

	_order_menu("Research next", ruler["research_options"], ruler["research_order"],
			func(id: Variant) -> void: command_requested.emit("set_research", {"tech": id}))
	_order_menu("Build next", ruler["build_options"], ruler["build_order"],
			func(id: Variant) -> void: command_requested.emit("set_build", {"building": id}))

	_small_label(_ruler_box, "Toward the others")
	for pair: Array in others:
		var other: int = pair[0]
		if other == mine:
			continue
		var row := HBoxContainer.new()
		_ruler_box.add_child(row)
		var name_label := Label.new()
		name_label.text = "%s  (%s)" % [str(_civ_info[other]["name"]), pair[1]]
		name_label.add_theme_font_size_override("font_size", 13)
		name_label.add_theme_color_override("font_color", Color.html(_civ_info[other]["color"]).lightened(0.25))
		name_label.custom_minimum_size = Vector2(150, 0)
		row.add_child(name_label)
		var order: Variant = ruler["stances"].get(str(other))
		var current: String = order["stance"] if order != null else "auto"
		for stance: Array in [["auto", "Auto"], ["trade", "Trade"], ["ally", "Ally"], ["aggression", "Attack"], ["ignore", "Ignore"]]:
			_choice(row, stance[1], current == stance[0], func() -> void:
				command_requested.emit("set_stance", {"civ": other, "stance": stance[0]}))


## A question that will not wait is put in a dialogue in the middle of the screen: an ally
## asking the player to join its rally.
func _show_popup(ruler: Dictionary) -> void:
	var asked: Variant = null
	for offer: Dictionary in ruler.get("proposals", []):
		if offer.get("popup", false):
			asked = offer
			break
	if asked == null:
		if _popup != null:
			_popup.queue_free()
			_popup = null
		return
	if _popup != null:
		_popup.queue_free()
	var from := int(asked["civ"])
	var centre := CenterContainer.new()
	centre.set_anchors_preset(Control.PRESET_FULL_RECT)
	centre.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(centre)
	_popup = centre
	var panel := _panel(centre)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	panel.add_child(column)
	var title := Label.new()
	title.text = "A call to arms"
	title.add_theme_font_size_override("font_size", 20)
	title.add_theme_color_override("font_color", Color.html(_civ_info[from]["color"]).lightened(0.25))
	column.add_child(title)
	var words := Label.new()
	words.text = str(asked["text"])
	words.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	words.custom_minimum_size = Vector2(380, 0)
	column.add_child(words)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 12)
	column.add_child(row)
	_button(row, "Join the rally", func() -> void:
		command_requested.emit("answer_proposal", {"civ": from, "kind": asked["kind"], "accept": true}))
	_button(row, "Stay out of it", func() -> void:
		command_requested.emit("answer_proposal", {"civ": from, "kind": asked["kind"], "accept": false}))


## How things stand between the ruled civ and another: war, alliance, truce or peace.
func _relation_word(ruler: Variant, other: int) -> String:
	if ruler == null or int(ruler["civ"]) == other:
		return ""
	var mine := int(ruler["civ"])
	var relation: Variant = _relations.get("%d:%d" % [mini(mine, other), maxi(mine, other)])
	if relation == null:
		return "peace"
	if relation["status"] == "peace" and relation["truce"]:
		return "truce"
	return str(relation["status"])


func _small_label(parent: Control, text: String) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 12)
	label.modulate = Color(1, 1, 1, 0.6)
	parent.add_child(label)


## One of a row of choices; the one in force is lit.
func _choice(parent: Control, text: String, chosen: bool, on_pressed: Callable) -> void:
	var button := _button(parent, text, on_pressed)
	button.add_theme_font_size_override("font_size", 13)
	if chosen:
		var lit := StyleBoxFlat.new()
		lit.bg_color = Color(0.36, 0.62, 1.0, 0.75)
		lit.set_corner_radius_all(8)
		lit.content_margin_left = 12
		lit.content_margin_right = 12
		lit.content_margin_top = 5
		lit.content_margin_bottom = 5
		for state: String in ["normal", "hover", "pressed"]:
			button.add_theme_stylebox_override(state, lit)


## A drop-down for an order with many options; the first entry hands the choice back to the civ.
func _order_menu(caption: String, options: Array, current: Variant, on_chosen: Callable) -> void:
	var row := HBoxContainer.new()
	_ruler_box.add_child(row)
	var label := Label.new()
	label.text = caption
	label.add_theme_font_size_override("font_size", 13)
	label.custom_minimum_size = Vector2(110, 0)
	row.add_child(label)
	var menu := OptionButton.new()
	menu.focus_mode = Control.FOCUS_NONE
	menu.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	menu.add_theme_font_size_override("font_size", 13)
	menu.add_item("The realm decides")
	for i in options.size():
		menu.add_item(str(options[i]["name"]))
		if options[i]["id"] == current:
			menu.select(i + 1)
	menu.item_selected.connect(func(index: int) -> void: on_chosen.call(null if index == 0 else options[index - 1]["id"]))
	row.add_child(menu)


func toggle_help() -> void:
	_help.visible = not _help.visible


func set_connected(connected: bool) -> void:
	_connected = connected
	_refresh_status()


func setup(init: Dictionary) -> void:
	_families.clear()
	for house: Dictionary in init.get("families", []):
		_families[int(house["civ"])] = house
	_regions_at.clear()
	for region: Dictionary in init.get("regions", []):
		_regions_at[Vector2i(int(region["x"]), int(region["y"]))] = region
	_seed = int(init["seed"])
	_map_name = str(init.get("map_name", ""))
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
	_tints.clear()
	for civ: Dictionary in init["civs"]:
		_add_card(civ)
		_add_tint(str(civ["name"]), str(civ["color"]))
	var natives: Dictionary = init.get("native_faction", {})
	_add_tint(str(natives.get("name", "")), str(natives.get("color", "#9a9488")))
	_expanded = -1
	_latest.clear()
	_routine.clear()
	_log_lines.clear()
	_log.text = ""
	_ruler_signature = ""
	_tech_tree.setup(init)
	_banners.clear()
	_make_chips()
	_chronicle_entries.clear()
	_ticker_text.text = ""
	_ticker.visible = false
	_chronicle_filter.clear()
	_chronicle_filter.add_item("Every civ", -1)
	for civ_id: int in _civ_info:
		_chronicle_filter.add_item(str(_civ_info[civ_id]["name"]), civ_id)
	_drawer_civ = -1
	_following = -1
	_drawer.visible = false
	_wars.clear()


func _add_card(civ: Dictionary) -> void:
	var civ_id := int(civ["id"])
	_civ_info[civ_id] = civ
	var card := RichTextLabel.new()
	card.bbcode_enabled = true
	card.fit_content = true
	card.scroll_active = false
	card.custom_minimum_size = Vector2(370, 0)
	card.mouse_filter = Control.MOUSE_FILTER_STOP  # clickable: opens and closes the detail
	card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	card.gui_input.connect(_on_card_input.bind(civ_id))
	card.add_theme_font_size_override("normal_font_size", 13)
	card.add_theme_font_size_override("bold_font_size", 13)
	_cards_box.add_child(card)
	_cards[civ_id] = card


## A civ born in the middle of the game (a rebellion): a card, a chip on the bar, a place in
## the chronicle's filter and the tech tree.
func add_civ(civ: Dictionary) -> void:
	if _civ_info.has(int(civ["id"])):
		return
	_add_card(civ)
	_add_tint(str(civ["name"]), str(civ["color"]))
	_make_chips()
	_chronicle_filter.add_item(str(civ["name"]), int(civ["id"]))
	_tech_tree.add_civ(civ)
	_fit_cards()


func set_status(status: Dictionary) -> void:
	_paused = status["paused"]
	_waiting_for = status.get("waiting_for", [])
	_speed = float(status["speed"])
	_refresh_status()


func update(tick: int, data: Dictionary) -> void:
	_tick = tick
	_regions_needed = int(data.get("domination", {}).get("regions", 0))
	set_status(data["status"])
	_relations.clear()
	for relation: Dictionary in data["relations"]:
		_relations["%d:%d" % [int(relation["a"]), int(relation["b"])]] = relation
	_deals.clear()
	for deal: Dictionary in data["deals"]:
		_deals["%d:%d" % [mini(int(deal["a"]), int(deal["b"])), maxi(int(deal["a"]), int(deal["b"]))]] = deal
	for civ: Dictionary in data["civs"]:
		_latest[int(civ["id"])] = civ
	_last_data = data
	for house: Dictionary in data.get("families", []):
		_families[int(house["civ"])] = house
	_refresh_ruler(data.get("ruler"))
	_refresh_castle()
	# Watching: the bar's chips and the drawer. Ruling: the older panels.
	var watching: bool = data.get("ruler") == null
	if watching != _spectating:
		_spectating = watching
		if not watching:
			select_civ(-1)
	_chips.visible = _spectating
	_log_panel.visible = not _spectating
	_ticker.visible = _spectating and _ticker_text.text != "" and not _chronicle.visible
	if not _spectating:
		_chronicle.visible = false
	_side.visible = not _spectating
	_ruler_panel.visible = not _spectating
	_refresh_chips()
	_refresh_drawer()
	_wars.visible = _spectating and not _drawer.visible
	if _wars.visible:
		_wars.update(data, _civ_info)
	# The tech tree is a spectator's view: a ruler sees only what his own civ knows.
	if not _spectating:
		_tech_tree.visible = false
	_tech_tree.update(data)
	_victory = data.get("victory")
	_refresh_status()
	_armies.clear()
	for army: Dictionary in data["armies"]:
		var owner := int(army["civ"])
		if not _armies.has(owner):
			_armies[owner] = []
		_armies[owner].append(army)
	_refresh_cards()
	if _diplomacy_panel.visible:
		_diplomacy.text = _diplomacy_text_panel(data)

	# Headlines get a line each; routine events are only counted.
	_banners.tick(tick)
	var ruled: Variant = data.get("ruler")
	for event: Dictionary in data["events"]:
		if event["kind"] in HEADLINE_KINDS:
			var color: String = _civ_info[int(event["civ"])]["color"]
			var line := "[color=#8a93a0]Day %d[/color]  %s" % [tick, _tint(str(event["text"]))]
			_log_lines.append(line)
			var involved := [int(event["civ"])]
			if event.has("target"):
				involved.append(int(event["target"]))
			var family: Dictionary = event.get("family", {})
			for other: Variant in family.get("civs", []):
				if not int(other) in involved:
					involved.append(int(other))
			if family.get("banner", false) and (ruled == null or int(ruled["civ"]) in involved):
				_announce_family(tick, event, family, color)
			if event.has("proclamation"):
				var words := "        [i]“%s”[/i]" % _tint(str(event["proclamation"]))
				_log_lines.append(words)
				line += "\n" + words
				# A banner while watching, and when you rule, for a war on or by your civ.
				var mine := ruled == null or int(ruled["civ"]) in [int(event["civ"]), int(event.get("target", -1))]
				if mine:
					_banners.proclaim(tick, _tint(str(_civ_info[int(event["civ"])]["name"])),
						_tint(str(_civ_info[int(event["target"])]["name"])), Color.html(color),
						_tint(str(event.get("war_name", ""))), _tint(str(event["proclamation"])), event_clicked.bind(event))
			_chronicle_entries.append([involved, line, event, false])
			_show_on_ticker(line)
		elif ROUTINE_LABELS.has(event["kind"]):
			_routine.append([tick, event["kind"]])
			var plain := "[color=#8a93a0]Day %d  %s[/color]" % [tick, _tint(str(event["text"]))]
			_chronicle_entries.append([[int(event["civ"])], plain, event, true])
	if _log_lines.size() > MAX_HEADLINES:
		_log_lines = _log_lines.slice(_log_lines.size() - MAX_HEADLINES)
	while not _routine.is_empty() and int(_routine[0][0]) <= tick - ROUTINE_WINDOW:
		_routine.pop_front()
	var counts := {}
	for entry: Array in _routine:
		counts[entry[1]] = counts.get(entry[1], 0) + 1
	var summary: Array[String] = []
	for kind: String in ROUTINE_LABELS:
		if counts.has(kind):
			summary.append("%d %s" % [counts[kind], ROUTINE_LABELS[kind]])
	var footer := "[color=#8a93a0]Last %d days: %s[/color]" % [
		ROUTINE_WINDOW, ", ".join(summary) if not summary.is_empty() else "quiet"]
	_log.text = "\n".join(_log_lines + [footer])
	_routine_footer = footer
	if _chronicle_entries.size() > CHRONICLE_LIMIT:
		_chronicle_entries = _chronicle_entries.slice(_chronicle_entries.size() - CHRONICLE_LIMIT)
	if _chronicle.visible:
		_refresh_chronicle()


## One tick is one day.
func _days(ticks: int) -> String:
	return "%d day%s" % [ticks, "" if ticks == 1 else "s"]


## Keep the bottom right clear for `height` pixels (the minimap): the cards stop above it.
func reserve_bottom_right(height: float) -> void:
	_reserved_bottom_right = height
	_wars.bottom_reserve = height + 20.0
	_drawer.offset_bottom = -(height + 20.0)
	_fit_cards()


func _fit_cards() -> void:
	if _cards_scroll == null:
		return
	var room := get_viewport().get_visible_rect().size.y - 10.0 - 30.0 - _reserved_bottom_right - 20.0
	_cards_scroll.custom_minimum_size = Vector2(370, minf(_cards_box.get_combined_minimum_size().y, maxf(120.0, room)))


func _refresh_cards() -> void:
	for civ_id: int in _latest:
		if _cards.has(civ_id):
			var civ: Dictionary = _latest[civ_id]
			_cards[civ_id].text = _card_text(_civ_info[civ_id], civ) if civ_id == _expanded else _compact_text(_civ_info[civ_id], civ)


## Show the castle standing on tile (x, y), or close the panel if `x` is negative. `anchor`
## is the point in the world the panel stands beside (above the castle's keep).
func show_castle(x: int, y: int, anchor := Vector3.INF) -> void:
	_castle_at = Vector2i(x, y)
	_castle_anchor = anchor
	_refresh_castle()
	_place_castle_panel()


func _process(delta: float) -> void:
	_place_castle_panel()
	_ticker_age += delta
	if _ticker != null:  # a new headline is bright for a few seconds, then stays, dimmed
		_ticker.modulate.a = 1.0 if _ticker_age < TICKER_BRIGHT else maxf(0.45, 1.0 - (_ticker_age - TICKER_BRIGHT) * 0.25)


## Keeps the castle panel beside its castle on screen, to the right of it (to the left when
## there is no room), and wholly on screen.
func _place_castle_panel() -> void:
	if not _castle_panel.visible:
		return
	var view := _castle_panel.get_viewport_rect().size
	var size := _castle_panel.get_combined_minimum_size()
	var at := Vector2(view.x - size.x - 10, view.y - size.y - 10)  # with nowhere to stand: bottom right
	var camera := get_viewport().get_camera_3d()
	if camera != null and _castle_anchor != Vector3.INF and not camera.is_position_behind(_castle_anchor):
		var point := camera.unproject_position(_castle_anchor)
		at = Vector2(point.x + 40, point.y - size.y * 0.5)
		if at.x + size.x > view.x - 10:
			at.x = point.x - 40 - size.x
	at.x = clampf(at.x, 10, maxf(10, view.x - size.x - 10))
	at.y = clampf(at.y, 10, maxf(10, view.y - size.y - 10))
	_castle_panel.position = at
	_castle_panel.size = size


func _refresh_castle() -> void:
	_castle_panel.visible = false
	if _castle_at.x < 0:
		return
	for civ: Dictionary in _latest.values():
		for settlement: Dictionary in civ.get("settlements", []):
			if int(settlement["x"]) != _castle_at.x or int(settlement["y"]) != _castle_at.y:
				continue
			var lines: Array[String] = []
			var main: bool = civ["settlements"][0] == settlement
			_castle_title.text = str(settlement["name"])
			lines.append(_civ_name(int(civ["id"])))
			lines.append("[color=#8a93a0]%s[/color]" % ("The capital of the realm" if main else "A regional capital"))
			if settlement.get("ruled_by") != null:
				lines.append("[color=#8a93a0]Ruled by:[/color] [color=#e8cf8a]%s[/color]" % settlement["ruled_by"])
			var city: Dictionary = _regions_at.get(_castle_at, {})
			if not city.is_empty():
				var standing: Array[String] = []
				for building: Dictionary in civ.get("buildings", []):
					if int(building.get("region", -1)) == int(city["id"]) and building["complete"]:
						var kind := str(building["type"])
						standing.append("%s %d [color=#8a93a0](%s)[/color]" % [_building_names.get(kind, kind),
							int(building.get("level", 1)), PURPOSES.get(kind, "")])
				if not standing.is_empty():
					lines.append("[color=#8a93a0]Buildings (level):[/color]\n  " + "\n  ".join(standing))
			var region: Dictionary = _regions_at.get(_castle_at, {})
			if not region.is_empty():
				var worth := "[color=#8a93a0]%s · worth %d point%s[/color]" % [str(region["name"]), int(region.get("points", 1)),
					"" if int(region.get("points", 1)) == 1 else "s"]
				if region.get("stronghold", false):
					worth += "  [color=#d9a441](a former native stronghold)[/color]"
				lines.append(worth)
				for rich: Variant in region.get("rich", []):
					lines.append("[color=#e8b84a]★ %s[/color] [color=#8a93a0](yields three times as much)[/color]" % str(rich))
			if settlement.has("garrison"):
				lines.append("[color=#8a93a0]Garrison:[/color] %d soldiers" % int(settlement["garrison"]))
			else:
				lines.append("[color=#8a93a0]Garrison:[/color] about %d soldiers [color=#8a93a0](attack it to count them)[/color]" % int(settlement["about"]))
			# Who is inside its walls (none of them is drawn on the map), and the generals among them.
			var inside: Dictionary = settlement.get("inside", {})
			if not inside.is_empty():
				var soldiers := int(inside["soldiers"])
				lines.append("[color=#8a93a0]Inside:[/color] %d villager%s, %s%d soldier%s" % [
					int(inside["villagers"]), "" if int(inside["villagers"]) == 1 else "s",
					"about " if inside.get("about", false) else "", soldiers, "" if soldiers == 1 else "s"])
			var generals: Array[String] = []
			for general: Dictionary in inside.get("generals", settlement.get("generals", [])):
				generals.append("%s (level %d)" % [general["name"], int(general["level"])])
			lines.append("[color=#8a93a0]Generals here:[/color] %s" % (", ".join(generals) if not generals.is_empty() else "none"))
			lines.append("[color=#8a93a0]Hospital:[/color] %d of %d beds taken" % [int(settlement.get("wounded", 0)), int(settlement.get("beds", 0))])
			if settlement.get("held_by") != null:
				lines.append("[color=#e07a6a]Held by %s: %d%% taken[/color]" % [
					str(_civ_info[int(settlement["held_by"])]["name"]), int(float(settlement.get("hold", 0.0)) * 100.0)])
			_castle_text.text = "\n".join(lines)
			_castle_panel.visible = true
			return


func toggle_tech_tree() -> void:
	if _spectating:
		_tech_tree.pick(_drawer_civ)
		_tech_tree.toggle()


# -- the watch layout: the ticker and the chronicle --------------------------------------

func _build_ticker(root: Control) -> void:
	_ticker = _panel(root)
	_ticker.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_ticker.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_ticker.offset_left = 10
	_ticker.offset_top = -10
	_ticker.offset_bottom = -10
	_ticker.visible = false
	_ticker.mouse_filter = Control.MOUSE_FILTER_STOP
	_ticker.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	_ticker.tooltip_text = "The chronicle: every headline so far  (L)"
	_ticker.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			toggle_chronicle())
	_ticker_text = RichTextLabel.new()
	_ticker_text.bbcode_enabled = true
	_ticker_text.fit_content = true
	_ticker_text.scroll_active = false
	_ticker_text.custom_minimum_size = Vector2(560, 0)
	_ticker_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ticker_text.add_theme_font_size_override("normal_font_size", 14)
	_ticker.add_child(_ticker_text)

	_chronicle = _panel(root)
	_chronicle.anchor_bottom = 1.0
	_chronicle.offset_left = 10
	_chronicle.offset_top = 70
	_chronicle.offset_right = 460  # clear of the battle alert at the top centre
	_chronicle.offset_bottom = -70
	_chronicle.visible = false
	(_chronicle.get_theme_stylebox("panel") as StyleBoxFlat).bg_color.a = 0.94
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	_chronicle.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var title := Label.new()
	title.text = "Chronicle"
	title.add_theme_font_size_override("font_size", 18)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	_chronicle_filter = OptionButton.new()
	_chronicle_filter.focus_mode = Control.FOCUS_NONE
	_chronicle_filter.tooltip_text = "Only the headlines about one civ"
	_chronicle_filter.item_selected.connect(func(_index: int) -> void: _refresh_chronicle())
	header.add_child(_chronicle_filter)
	_chronicle_routine = CheckBox.new()
	_chronicle_routine.text = "Routine"
	_chronicle_routine.focus_mode = Control.FOCUS_NONE
	_chronicle_routine.tooltip_text = "List the routine events too: buildings, villages, discoveries, trade"
	_chronicle_routine.toggled.connect(func(_on: bool) -> void: _refresh_chronicle())
	header.add_child(_chronicle_routine)
	_icon_button(header, "close", "Close  (Esc)", toggle_chronicle).custom_minimum_size = Vector2(32, 30)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	_chronicle_text = RichTextLabel.new()
	_chronicle_text.bbcode_enabled = true
	_chronicle_text.fit_content = true
	_chronicle_text.scroll_active = false
	_chronicle_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_chronicle_text.mouse_filter = Control.MOUSE_FILTER_PASS  # its lines are links: click one to go to it
	_chronicle_text.meta_underlined = false
	_chronicle_text.meta_clicked.connect(func(meta: Variant) -> void:
		var index := int(str(meta))
		if index >= 0 and index < _chronicle_entries.size():
			event_clicked(_chronicle_entries[index][2]))
	_chronicle_text.add_theme_font_size_override("normal_font_size", 13)
	scroll.add_child(_chronicle_text)


func _show_on_ticker(line: String) -> void:
	_ticker_text.text = line
	_ticker_age = 0.0
	_ticker.visible = _spectating and not _chronicle.visible


func toggle_chronicle() -> void:
	_chronicle.visible = not _chronicle.visible and _spectating
	_ticker.visible = _spectating and _ticker_text.text != "" and not _chronicle.visible  # it would repeat the top line
	if _chronicle.visible:
		_chronicle.move_to_front()
		_refresh_chronicle()


## Every headline so far, newest first, for every civ or the one chosen; the routine counts last.
func _refresh_chronicle() -> void:
	var only := _chronicle_filter.get_selected_id() if _chronicle_filter.selected >= 0 else -1
	var lines: Array[String] = []
	var routine := _chronicle_routine.button_pressed
	for i in range(_chronicle_entries.size() - 1, -1, -1):
		var entry: Array = _chronicle_entries[i]
		if (only < 0 or only in entry[0]) and (routine or not entry[3]):
			lines.append("[url=%d]%s[/url]" % [i, entry[1]])
	if lines.is_empty():
		lines.append("[color=#8a93a0]Nothing yet.[/color]")
	_chronicle_text.text = "\n".join(lines) + "\n\n" + _routine_footer


# -- the watch layout: scoreboard chips and the civ drawer ------------------------------

const DRAWER_TABS := ["Overview", "Family", "Army", "Diplomacy", "Tech"]
var _families := {}  # civ id -> its ruling house (civ/family.py), as last sent
var _tints: Array = []  # [RegEx, BBCode] per civ (and the native faction): its name in its colour


func _build_drawer(root: Control) -> void:
	_drawer = _panel(root)
	_drawer.anchor_left = 1.0
	_drawer.anchor_right = 1.0
	_drawer.anchor_bottom = 1.0
	_drawer.offset_left = -450
	_drawer.offset_right = -10
	_drawer.offset_bottom = -20
	_drawer.visible = false
	(_drawer.get_theme_stylebox("panel") as StyleBoxFlat).bg_color.a = 0.94
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	_drawer.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	_drawer_title = RichTextLabel.new()
	_drawer_title.bbcode_enabled = true
	_drawer_title.fit_content = true
	_drawer_title.scroll_active = false
	_drawer_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_drawer_title.add_theme_font_size_override("normal_font_size", 14)
	_drawer_title.add_theme_font_size_override("bold_font_size", 20)
	header.add_child(_drawer_title)
	_follow_button = _button(header, "Follow", func() -> void:
		_following = -1 if _following == _drawer_civ else _drawer_civ
		follow_requested.emit(_following)
		_refresh_drawer())
	_follow_button.tooltip_text = "Keep the camera on this civ's largest army, or its capital"
	var take := _button(header, "Rule it", func() -> void:
		command_requested.emit("take_control", {"civ": _drawer_civ}))
	take.tooltip_text = "Take this civ in hand yourself"
	var close := _icon_button(header, "close", "Close  (Esc)", func() -> void: select_civ(-1))
	close.custom_minimum_size = Vector2(32, 30)
	_drawer_tabs = TabBar.new()
	for tab: String in DRAWER_TABS:
		_drawer_tabs.add_tab(tab)
	_drawer_tabs.focus_mode = Control.FOCUS_NONE
	_drawer_tabs.tab_changed.connect(_on_drawer_tab)
	column.add_child(_drawer_tabs)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	_drawer_text = RichTextLabel.new()
	_drawer_text.bbcode_enabled = true
	_drawer_text.fit_content = true
	_drawer_text.scroll_active = false
	_drawer_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_drawer_text.mouse_filter = Control.MOUSE_FILTER_PASS  # its "family tree" link is clicked
	_drawer_text.meta_clicked.connect(func(meta: Variant) -> void:
		if str(meta) == "tree":
			show_family_tree())
	_drawer_text.add_theme_font_size_override("normal_font_size", 13)
	_drawer_text.add_theme_font_size_override("bold_font_size", 13)
	scroll.add_child(_drawer_text)


func _make_chips() -> void:
	for chip: Node in _chips.get_children():
		chip.queue_free()
	_chip_buttons.clear()
	var crowded := _civ_info.size() > 5  # rebels have joined: tighter chips, so all fit on the bar
	for civ_id: int in _civ_info:
		var color := Color.html(_civ_info[civ_id]["color"])
		var chip := Button.new()
		chip.focus_mode = Control.FOCUS_NONE
		chip.add_theme_font_size_override("font_size", 11 if crowded else 13)
		chip.add_theme_color_override("font_color", color.lightened(0.45))
		chip.add_theme_color_override("font_hover_color", Color.WHITE)
		chip.add_theme_constant_override("icon_max_width", 16)
		for state: Array in [["normal", 0.22], ["hover", 0.4], ["pressed", 0.55]]:
			var style := StyleBoxFlat.new()
			style.bg_color = Color(color.darkened(0.35), state[1])
			style.border_color = color
			style.border_width_bottom = 3
			style.set_corner_radius_all(7)
			style.content_margin_left = 4 if crowded else 7
			style.content_margin_right = 4 if crowded else 7
			style.content_margin_top = 4
			style.content_margin_bottom = 4
			chip.add_theme_stylebox_override(state[0], style)
		chip.pressed.connect(func() -> void: select_civ(-1 if _drawer_civ == civ_id else civ_id))
		_chips.add_child(chip)
		_chip_buttons[civ_id] = chip


## The scoreboard: each civ's name and points; swords while it is at war; dim once fallen.
func _refresh_chips() -> void:
	for civ_id: int in _chip_buttons:
		if not _latest.has(civ_id):
			continue
		var civ: Dictionary = _latest[civ_id]
		var chip: Button = _chip_buttons[civ_id]
		var at_war := false
		var allied := false
		for key: String in _relations:
			var pair := key.split(":")
			if int(pair[0]) == civ_id or int(pair[1]) == civ_id:
				at_war = at_war or _relations[key]["status"] == "war"
				allied = allied or _relations[key]["status"] == "alliance"
		chip.text = "%s %d" % [_civ_info[civ_id]["name"], int(civ.get("regions_held", 0))]
		chip.icon = _icon("battle") if at_war and civ["alive"] else null
		chip.modulate = Color(1, 1, 1, 1.0 if civ["alive"] else 0.45)
		chip.tooltip_text = "%s (%s): %s%s\n%s  ·  Pop %d  ·  Army %d\n%s%s%s" % [
			_civ_info[civ_id]["name"], _personality(civ_id), _toward_victory(civ),
			"  ·  at war" if at_war else ("  ·  allied" if allied else ""), civ["era_name"], int(civ["population"]),
			int(civ["soldiers"]), "Goal: %s" % civ["strategy"] if str(civ.get("strategy", "")) != "" else "",
			"" if civ["alive"] else "\nDestroyed", _ruler_line(civ_id, "\n")]
		var selected := civ_id == _drawer_civ
		(chip.get_theme_stylebox("normal") as StyleBoxFlat).bg_color.a = 0.6 if selected else 0.22


func show_drawer_tab(tab: String) -> void:
	if DRAWER_TABS.has(tab):
		_drawer_tabs.current_tab = DRAWER_TABS.find(tab)
		_refresh_drawer()


## Open the drawer on one civ (or close it with -1).
func select_civ(civ_id: int) -> void:
	_drawer_civ = civ_id if _civ_info.has(civ_id) else -1
	_drawer.visible = _drawer_civ >= 0 and _spectating
	_wars.visible = _spectating and not _drawer.visible  # they share the corner
	_tech_tree.pick(_drawer_civ)
	_refresh_chips()
	_refresh_drawer()


func _on_drawer_tab(tab: int) -> void:
	if DRAWER_TABS[tab] == "Tech":
		# The tree is too big for the drawer: it opens over the map, on this civ's path.
		_tech_tree.pick(_drawer_civ)
		if not _tech_tree.visible:
			_tech_tree.toggle()
	_refresh_drawer()


func _refresh_drawer() -> void:
	if _drawer_civ < 0 or not _latest.has(_drawer_civ) or not _drawer.visible:
		return
	var info: Dictionary = _civ_info[_drawer_civ]
	var civ: Dictionary = _latest[_drawer_civ]
	_drawer_title.text = "[b][color=%s]%s[/color][/b]\n[color=#8a93a0]%s · %s · score %d[/color]" % [
		info["color"], info["name"], _personality(_drawer_civ), _toward_victory(civ), int(civ.get("score", 0))]
	_follow_button.text = "Following" if _following == _drawer_civ else "Follow"
	var tab: String = DRAWER_TABS[_drawer_tabs.current_tab]
	var text := ""
	if not civ["alive"]:
		text = "[color=#e07a6a]Destroyed: its last capital has fallen[/color]"
	elif tab == "Overview" or tab == "Tech":
		text = _status_line(_drawer_civ, civ)
		if str(civ.get("strategy", "")) != "":
			text += "\n[color=#8a93a0]Goal:[/color] %s" % civ["strategy"]
		if str(civ.get("plan", "")) != "":
			text += "\n[color=#d98a5a]%s[/color]" % civ["plan"]
		if civ.get("sickness") != null:
			text += "\n[color=#c9a23a]Struck by %s (%d days left)[/color]" % [civ["sickness"]["name"], int(civ["sickness"]["days"])]
		text += "\n\n" + _card_text(info, civ, false).split("\n", true, 1)[-1]
	elif tab == "Family":
		text = _family_text(_drawer_civ)
	elif tab == "Army":
		text = _army_text(civ)
	elif tab == "Diplomacy":
		text = "[b]%s's relations[/b]\n%s\n\n%s" % [info["name"], _diplomacy_text(_drawer_civ, civ),
			_diplomacy_text_panel(_last_data) if not _last_data.is_empty() else ""]
	_drawer_text.text = text


## The ruler of a civ, as "King Edric Valedorn (56), heir Cedric", or "" if unknown.
func _ruler_line(civ_id: int, before: String) -> String:
	if not _families.has(civ_id):
		return ""
	var house: Dictionary = _families[civ_id]
	var ruler := ""
	var heir := ""
	for member: Dictionary in house["members"]:
		if member["ruler"] and member["alive"]:
			ruler = "%s %s %s (%d)" % [member["title"], member["name"], house["house"], int(member["age"])]
		elif member["heir"]:
			heir = member["name"]
	if ruler == "":
		return ""
	return before + ruler + ("  ·  heir %s" % heir if heir != "" else "") + ("  ·  [unsettled]" if house["unrest"] else "")


## A civ plans by its ruler's personality: it changes with each new ruler.
func _personality(civ_id: int) -> String:
	if _families.has(civ_id):
		for member: Dictionary in _families[civ_id]["members"]:
			if member["ruler"] and member["alive"] and str(member.get("personality", "")) != "":
				return str(member["personality"])
	return str(_civ_info[civ_id]["personality"]) if _civ_info.has(civ_id) else ""


const FAMILY_COLUMNS := 4
const TRAIT_COLORS := {"brave": "#e8b84a", "sickly": "#9ab07a", "learned": "#7ab0e0", "cruel": "#e07a6a",
	"ambitious": "#d98a5a", "usurper": "#e05a4a", "pious": "#d8d0a8", "shrewd": "#e8b84a", "kind": "#8fd18f",
	"proud": "#c98fd1"}

## The drawer's Family tab: a portrait for each living member (the ruler first, the heir
## marked), then the dead in grey with when and how they died.
func _family_text(civ_id: int) -> String:
	if not _families.has(civ_id):
		return "[color=#8a93a0]No ruling house[/color]"
	var house: Dictionary = _families[civ_id]
	var living: Array = house["members"].filter(func(m: Dictionary) -> bool: return m["alive"])
	var dead: Array = house["members"].filter(func(m: Dictionary) -> bool: return not m["alive"])
	var text := "[b]House %s[/b]%s%s   [url=tree][color=#59a6ff]family tree[/color][/url]\n" % [house["house"],
		"  [color=#8a93a0](%s)[/color]" % house["branch"] if str(house.get("branch", "")) != "" else "",
		"  [color=#c9a23a](a new ruler, not yet settled)[/color]" if house["unrest"] else ""]
	text += _portrait_table(living, str(house.get("crest", "")), false)
	if not dead.is_empty():
		text += "\n[color=#8a93a0]Gone before[/color]\n" + _portrait_table(dead, str(house.get("crest", "")), true)
	return text


func _portrait_table(members: Array, crest: String, dead: bool) -> String:
	var text := "[table=%d]" % FAMILY_COLUMNS
	for member: Dictionary in members:
		var picture := str(member["portrait"])
		if picture == "" or not ResourceLoader.exists(picture):
			picture = crest
		var face := ""
		if picture != "" and ResourceLoader.exists(picture):
			face = "[img=80x100%s]%s[/img]\n" % [" color=#8c8c8c" if dead else "", picture]
		var role := ""
		if member["ruler"]:
			role = "[color=#e8b84a]♛ rules[/color]\n"
		elif member.get("regent", false):
			role = "[color=#e8b84a]regent[/color]\n"
		elif member["heir"]:
			role = "[color=#e8b84a]heir[/color]\n"
		var about := ""
		if dead:
			if member["died"] != null:
				about = "[color=#8a93a0]died day %d, aged %d\n%s[/color]" % [int(member["died"]), int(member["age"]), member["cause"]]
			else:
				about = "[color=#8a93a0]%s[/color]" % member["cause"]
		else:
			var notes: Array[String] = ["%d" % int(member["age"])]
			if member["ill"]:
				notes.append("[color=#c9a23a]ill[/color]")
			if int(member["wounds"]) > 0:
				notes.append("[color=#d98a5a]wounded[/color]")
			if str(member.get("governs", "")) != "":
				notes.append("rules %s" % member["governs"])
				if str(member.get("governor_bonus", "")) != "":
					notes.append("[color=#e8cf8a]%s[/color]" % member["governor_bonus"])
			if str(member.get("captive", "")) != "":
				notes.append("[color=#e07a6a]held by %s[/color]" % member["captive"])
			if member.get("deposed", false):
				notes.append("deposed")
			for quality: Variant in member.get("traits", []):
				notes.append("[color=%s]%s[/color]" % [TRAIT_COLORS.get(str(quality), "#c9b48a"), quality])
			if str(member.get("born", "")) != "":
				notes.append("née %s" % member["born"] if member["sex"] == "f" else "of %s" % member["born"])
			about = "[color=#8a93a0]%s[/color]" % " · ".join(notes)
		text += "[cell][center]%s%s[font_size=12]%s %s[/font_size]\n[font_size=11]%s[/font_size][/center][/cell]" % [
			face, role, member["title"], member["name"], about]
	return text + "[/table]\n"


## Each civ's name (and the native faction's) in its own colour, a little lightened so it reads
## on the dark panels; the rest of the text keeps the standard colour. Several names in one
## line each get their own.
func _add_tint(civ_name: String, color: String) -> void:
	if civ_name == "":
		return
	var pattern := RegEx.new()
	pattern.compile("\\b" + civ_name + "\\b")
	_tints.append([pattern, "[color=#%s]%s[/color]" % [Color.html(color).lightened(0.3).to_html(false), civ_name]])


func _tint(text: String) -> String:
	for tint: Array in _tints:
		text = (tint[0] as RegEx).sub(text, tint[1], true)
	return text


## A clicked event (a chronicle line or a banner): a family event opens the house's tree with
## the person picked out; anything with a place brings the camera there; a war, to the
## attacked civ's capital.
func event_clicked(event: Dictionary) -> void:
	var family: Dictionary = event.get("family", {})
	if not family.is_empty():
		var person := int(family.get("person", -1))
		for civ_id: int in _families:
			for member: Dictionary in _families[civ_id]["members"]:
				if int(member["id"]) == person:
					_family_tree.show_house(_families[civ_id], Color.html(_civ_info[civ_id]["color"]), person)
					return
	if event.has("x") and event.has("y"):
		jump_requested.emit(float(event["x"]), float(event["y"]))
		return
	var where := int(event.get("target", event.get("civ", -1)))
	if _latest.has(where) and not _latest[where]["settlements"].is_empty():
		var home: Dictionary = _latest[where]["settlements"][0]
		jump_requested.emit(float(home["x"]), float(home["y"]))


## A death, a murder, a succession or a marriage between ruling houses: a banner like a war's.
func _announce_family(tick: int, event: Dictionary, family: Dictionary, color: String) -> void:
	var kind := str(family["type"])
	var icon: String = "res://assets/icons/%s.svg" % {"assassination": "dagger", "marriage": "rings",
		"rebellion": "dagger", "execution": "dagger", "usurpation": "dagger", "claim": "battle",
		"pledge": "rings", "betrayal": "dagger", "captured": "dagger",
		"exchange": "rings", "rescue": "crown", "unrest": "battle"}.get(kind, "crown")
	var title: String = {"death": "A death in the house", "succession": "The crown passes",
		"assassination": "Murder!", "marriage": "A royal wedding", "rebellion": "Rebellion!",
		"execution": "An execution", "usurpation": "The crown is seized", "claim": "A claim to a throne",
		"ransom": "A prince comes home", "pledge": "An oath to the rebel", "betrayal": "Betrayed!",
		"captured": "Taken prisoner", "exchange": "An exchange of prisoners",
		"rescue": "Set free", "unrest": "The people stir"}.get(kind, "News of the court")
	var portrait := str(family.get("portrait", ""))
	if portrait == "":
		portrait = str(family.get("crest", ""))
	_banners.announce(tick, "[b]%s[/b]  %s" % [_tint(str(_civ_info[int(event["civ"])]["name"])), title],
		Color.html(color), _tint(str(family.get("line", ""))), _tint(str(event["text"])), icon, portrait,
		bool(family.get("dead", false)), event_clicked.bind(event))


func toggle_card(civ_id: int) -> void:
	if _spectating:
		select_civ(-1 if _drawer_civ == civ_id else civ_id)
		return
	if not _cards.has(civ_id):
		return
	_expanded = -1 if _expanded == civ_id else civ_id
	_tech_tree.pick(_expanded)  # an open card shows that civ's path in the tech tree
	_refresh_cards()


func _on_card_input(event: InputEvent, civ_id: int) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		toggle_card(civ_id)


func toggle_diplomacy() -> void:
	if _spectating:  # watching: diplomacy is a tab of the drawer
		if _drawer_civ < 0:
			select_civ(_first_alive())
		_drawer_tabs.current_tab = DRAWER_TABS.find("Diplomacy")
		_refresh_drawer()
		return
	_diplomacy_panel.visible = not _diplomacy_panel.visible


func _first_alive() -> int:
	for civ_id: int in _latest:
		if _latest[civ_id]["alive"]:
			return civ_id
	return -1


## Esc: close what is open, the most recent first.
## The drawer's civ's house as a tree, over the map.
func show_family_tree() -> void:
	if _families.has(_drawer_civ):
		_family_tree.show_house(_families[_drawer_civ], Color.html(_civ_info[_drawer_civ]["color"]))


## Esc with nothing open: ask before leaving, so a stray key never ends a game.
func ask_leave() -> void:
	if _leave == null:
		_leave = ConfirmationDialog.new()
		_leave.title = "Leave the game"
		_leave.dialog_text = "Go back to the menu? This game ends."
		_leave.ok_button_text = "Back to the menu"
		_leave.cancel_button_text = "Keep playing"
		_leave.confirmed.connect(func() -> void: command_requested.emit("end_game", {}))
		add_child(_leave)
	_leave.popup_centered()


## Where a civ stands toward domination: "12 of 16 regions, 2/3 rival seats".
func _toward_victory(civ: Dictionary) -> String:
	var seats: Array = civ.get("seats", [0, 0])
	return "%d of %d regions, %d/%d rival seats" % [int(civ.get("regions_held", 0)), _regions_needed,
		int(seats[0]), int(seats[1])]


func close_top() -> bool:
	if _family_tree.visible:
		_family_tree.visible = false
		return true
	if _chronicle.visible:
		_chronicle.visible = false
		return true
	if _tech_tree.visible:
		_tech_tree.visible = false
		return true
	if _drawer.visible:
		select_civ(-1)
		return true
	return false


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
		lines.append("[b]%s[/b]  [color=#8a93a0]%s[/color]" % [name, _days(_tick - started)])
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
			lines.append("  [color=#8a93a0]castles taken %d / %d   losses %d / %d[/color]" % [
				int(war["regions_taken"][str(attacker)]), int(war["regions_taken"][str(defender)]),
				int(war["casualties"][str(attacker)]), int(war["casualties"][str(defender)]),
			])

	lines.append("")
	lines.append("[b][color=#6fb7ff]ALLIANCES[/color][/b]")
	if alliances.is_empty():
		lines.append("[color=#8a93a0]  None.[/color]")
	for alliance: Dictionary in alliances:
		var name: String = str(alliance["name"]) if alliance["name"] != null else "Alliance"
		lines.append("[b]%s[/b]" % name)
		lines.append("  %s and %s  [color=#8a93a0]formed day %d (%s ago)[/color]" % [
			_civ_name(int(alliance["a"])), _civ_name(int(alliance["b"])), int(alliance["since"]),
			_days(_tick - int(alliance["since"])),
		])

	lines.append("")
	lines.append("[b][color=#7ccf7c]TRADE DEALS[/color][/b]")
	if data["deals"].is_empty():
		lines.append("[color=#8a93a0]  None.[/color]")
	for deal: Dictionary in data["deals"]:
		lines.append("  %s sends %s %s/tick,  %s sends %s %s/tick  [color=#8a93a0]%s left[/color]" % [
			_civ_name(int(deal["a"])), String.num(float(deal["a_gives"]["rate"]), 2), deal["a_gives"]["resource"],
			_civ_name(int(deal["b"])), String.num(float(deal["b_gives"]["rate"]), 2), deal["b_gives"]["resource"],
			_days(int(deal["ends"]) - _tick),
		])
	return "\n".join(lines)


## Multiplies the sim speed; the server clamps it to its allowed range.
func request_speed(factor: float) -> void:
	command_requested.emit("set_speed", _speed * factor)


func _refresh_status() -> void:
	# The banner says why the days are not passing: paused, or held for a strategist's answer.
	var holding: Array[String] = []
	for civ_id in _waiting_for:
		if _civ_info.has(int(civ_id)):
			holding.append(str(_civ_info[int(civ_id)]["name"]))
	_paused_banner.visible = _connected and (_paused or not holding.is_empty() or _victory != null)
	_paused_banner.text = "PAUSED" if _paused or holding.is_empty() else "Waiting for %s to decide" % " and ".join(holding)
	if _victory != null and _civ_info.has(int(_victory["civ"])):
		# The game is decided; it can be played on, so the banner also says if it is paused.
		var how: String = {"conquest": "by conquest", "domination": "by holding most of the world",
			"score": "on score"}.get(_victory["kind"], "")
		_paused_banner.text = "★ %s wins %s (day %d)%s" % [_civ_info[int(_victory["civ"])]["name"], how,
			int(_victory["tick"]), "\npaused: Resume to play on" if _paused else ""]
	if not _connected:
		_status.text = "Waiting for sim on ws://127.0.0.1:8765 ..."
		return
	# One tick is one day; speed is shown as days per minute, which is what a spectator feels.
	var pace := "paused" if _paused else "%s days/min" % String.num(_speed * 60.0, 0)
	_status.text = "Day %d  ·  %s" % [_tick, pace.replace(" days/min", "/min")]
	_status.tooltip_text = "%s  ·  %s" % [_map_name if _map_name != "" else "seed %d" % _seed, pace]
	_status.mouse_filter = Control.MOUSE_FILTER_PASS
	_pause_button.icon = _icon("play" if _paused else "pause")


## The two-line card: who they are, how big, and the one thing most worth knowing about them now.
func _compact_text(info: Dictionary, civ: Dictionary) -> String:
	var title := "[font_size=16][b][color=%s]%s[/color][/b][/font_size]  [color=#8a93a0]%s[/color]" % [
		info["color"], info["name"], info["personality"]]
	if not civ["alive"]:
		return title + "\n[color=#e07a6a]Destroyed[/color]"
	var facts := "%s   %s   Pop %d   Army %d   [color=#d9c36a]Score %d[/color]" % [
		civ["era_name"], _toward_victory(civ), int(civ["population"]), int(civ["soldiers"]), int(civ.get("score", 0))]
	var goal := ""
	if str(civ.get("strategy", "")) != "":
		goal = "\n[color=#8a93a0]Goal: %s[/color]" % civ["strategy"]
	var ill := ""
	if civ.get("sickness") != null:
		ill = "\n[color=#c9a23a]Struck by %s (%d days left)[/color]" % [civ["sickness"]["name"], int(civ["sickness"]["days"])]
	if str(civ.get("plan", "")) != "":
		goal += "\n[color=#d98a5a]%s[/color]" % civ["plan"]
	return "%s\n%s\n%s%s%s" % [title, facts, _status_line(int(civ["id"]), civ), ill, goal]


## What is going on with this civ, most pressing first.
func _status_line(civ_id: int, civ: Dictionary) -> String:
	var enemies: Array[String] = []
	var allies: Array[String] = []
	for other_key: String in civ["stances"]:
		var other := int(other_key)
		var key := "%d:%d" % [mini(civ_id, other), maxi(civ_id, other)]
		if not _relations.has(key):
			continue
		if _relations[key]["status"] == "war":
			enemies.append(_civ_name(other))
		elif _relations[key]["status"] == "alliance":
			allies.append(_civ_name(other))
	var parts: Array[String] = []
	if not enemies.is_empty():
		parts.append("[color=#ff5a4a]At war with[/color] %s" % ", ".join(enemies))
	if civ["thirsty"]:
		parts.append("[color=#e07a6a]out of water[/color]")
	if int(civ["distrusted_for"]) > 0:
		parts.append("[color=#e07a6a]distrusted[/color]")
	if not allies.is_empty():
		parts.append("[color=#6fb7ff]Allied with[/color] %s" % ", ".join(allies))
	if parts.is_empty():
		parts.append("[color=#8a93a0]At peace[/color]")
	return "   ".join(parts)


func _card_text(info: Dictionary, civ: Dictionary, with_army := true) -> String:
	var lines: Array[String] = []
	lines.append("[font_size=17][b][color=%s]%s[/color][/b][/font_size]  [color=#8a93a0]%s[/color]"
			% [info["color"], info["name"], _personality(int(info.get("id", -1)))])
	if _families.has(int(info.get("id", -1))):
		lines.append("[color=#c9b48a]%s[/color]" % _ruler_line(int(info["id"]), ""))
	if not civ["alive"]:
		lines.append("[color=#e07a6a]Destroyed: its last capital has fallen[/color]")
		return "\n".join(lines)
	var regions_held: Array[String] = []
	for region_id: Variant in civ["regions"]:
		regions_held.append(_region_names.get(int(region_id), "?"))
	lines.append("[color=#8a93a0]Regions (%d):[/color] %s" % [regions_held.size(), ", ".join(regions_held)])
	if int(civ.get("mines", 0)) > 0:
		lines.append("[color=#d9c36a]Gold mines: %d[/color] [color=#8a93a0](each pays a gold a day, once Mining is known)[/color]" % int(civ["mines"]))
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
	if with_army:
		lines.append(_army_text(civ))
	lines.append("[color=#8a93a0]Diplomacy points[/color] %d   %s" % [int(civ["diplomacy_points"]), _diplomacy_text(int(civ["id"]), civ)])
	if civ["thinking"]:
		lines.append("[color=#8a93a0]Strategist is thinking ...[/color]")
	elif civ["reason"] != "" and not str(civ["reason"]).begins_with("Rule-based policy"):
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


## "12 archers, 8 swordsmen", largest first.
func _unit_mix(units: Dictionary) -> String:
	var order := units.keys()
	order.sort_custom(func(a: String, b: String) -> bool: return int(units[a]) > int(units[b]))
	var parts: Array[String] = []
	for unit_id: String in order:
		parts.append("%d %s" % [int(units[unit_id]), _unit_names.get(unit_id, unit_id).to_lower()])
	return ", ".join(parts)


func _army_text(civ: Dictionary) -> String:
	# The total is every soldier the civ has; below it, each army with exactly what is in it.
	var text := "Soldiers %d in all   strength %d" % [int(civ["soldiers"]), int(civ["army_strength"])]
	var total_mix := _unit_mix(civ["units"])
	if total_mix != "":
		text += "\n[color=#8a93a0]%s[/color]" % total_mix
	for army: Dictionary in _armies.get(int(civ["id"]), []):
		var who := "Garrison"
		if army["role"] == "field":
			var commander: Variant = army["commander"]
			who = "Army under %s (level %d)" % [commander["name"], int(commander["level"])] if commander != null else "Army, no commander"
		text += "\n   [color=#8a93a0]%s:[/color] %d  [color=#8a93a0]%s[/color]" % [who, int(army["size"]), _unit_mix(army["units"])]
	var problems: Array[String] = []
	if civ["unpaid"]:
		problems.append("unpaid")
	if civ["unsupplied"]:
		problems.append("no ore")
	if not problems.is_empty():
		text += "   [color=#e07a6a](%s)[/color]" % ", ".join(problems)
	text += "\n[color=#8a93a0]Commanders:[/color] %d of %d" % [int(civ["commanders"]), int(civ["commander_cap"])]
	var posted: Array[String] = []
	for officer: Dictionary in civ["commanders_in_reserve"]:
		if officer["post"] != null:
			posted.append("%s (level %d) holds %s" % [officer["name"], int(officer["level"]), officer["post"]])
	if not posted.is_empty():
		text += "\n   " + "\n   ".join(posted)
	text += "\n[color=#8a93a0]Troops:[/color] tier %d   [color=#8a93a0]In hospital:[/color] %d of %d beds" % [
		int(civ.get("tier", 1)), int(civ["wounded"]), int(civ.get("beds", 0))]
	if int(civ.get("hospital_deaths", 0)) > 0:
		text += "   [color=#d98a8a]%d died for want of a bed[/color]" % int(civ["hospital_deaths"])
	if not civ["captives"].is_empty():
		var held: Array[String] = []
		for captive: Dictionary in civ["captives"]:
			held.append("%s (level %d, of %s)" % [captive["name"], int(captive["level"]), _civ_info[int(captive["home"])]["name"]])
		text += "\n[color=#8a93a0]Holding prisoner:[/color] %s" % ", ".join(held)
	if int(civ["distrusted_for"]) > 0:
		text += "\n[color=#e07a6a]Distrusted for betrayal: %s left[/color]" % _days(int(civ["distrusted_for"]))
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
	style.bg_color = Color(0.06, 0.075, 0.1, 0.8)
	style.set_corner_radius_all(12)
	style.set_content_margin_all(12)
	style.set_border_width_all(1)
	style.border_color = Color(1, 1, 1, 0.09)
	style.shadow_color = Color(0, 0, 0, 0.35)
	style.shadow_size = 10
	style.shadow_offset = Vector2(0, 3)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	return panel


## A square button with an icon from res://assets/icons (made by tools/make_icons.py) and a tooltip.
func _icon_button(parent: Control, icon_name: String, tip: String, on_pressed: Callable) -> Button:
	var button := _button(parent, "", on_pressed)
	button.icon = _icon(icon_name)
	button.tooltip_text = tip
	button.expand_icon = true
	button.custom_minimum_size = Vector2(38, 34)
	for state: String in ["normal", "hover", "pressed"]:
		var style: StyleBoxFlat = button.get_theme_stylebox(state)
		style.content_margin_left = 7
		style.content_margin_right = 7
	return button


func _icon(icon_name: String) -> Texture2D:
	if not _icons.has(icon_name):
		_icons[icon_name] = load("res://assets/icons/%s.svg" % icon_name)
	return _icons[icon_name]


func _button(parent: Control, text: String, on_pressed: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.focus_mode = Control.FOCUS_NONE
	for state: Array in [["normal", 0.1], ["hover", 0.2], ["pressed", 0.3]]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color(1, 1, 1, state[1])
		style.set_corner_radius_all(8)
		style.content_margin_left = 12
		style.content_margin_right = 12
		style.content_margin_top = 5
		style.content_margin_bottom = 5
		button.add_theme_stylebox_override(state[0], style)
	button.pressed.connect(on_pressed)
	parent.add_child(button)
	return button
