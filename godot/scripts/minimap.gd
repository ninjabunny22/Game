extends Control
## A small picture of the whole map, bottom right. Each land tile takes the colour of whoever
## holds its region (grey while the natives do), water is blue and peaks are dark; region
## borders are drawn darker and every region capital is a white dot. The picture is only
## redrawn when a region changes hands.
##
## Over it: each field army led by a general as a small square in its civ's colour, gliding
## as it does on the map, and left out while it is inside a castle (the simulation says
## which); and the part of the map the camera sees. Clicking or dragging on it moves the
## camera there. It shows only what the tick message holds, as the map does.

signal jump_requested(x: float, y: float)  # in tiles

const LONGEST_SIDE := 220.0  # pixels on its longest side; the map's shape is kept
const MARGIN := 6.0
const NEUTRAL := Color(0.52, 0.53, 0.52)
const WATER := Color(0.17, 0.33, 0.55)
const PEAKS := Color(0.2, 0.19, 0.21)
const BORDER_SHADE := 0.55  # a border pixel is the land's colour this much as bright
const OWNED_SHADE := 0.88
const ARMY_SIZE := 4.0
const MOVE_SPEED := 6.0  # tiles a second, as the figures on the map
const FAR_GROUND := 600.0  # how far a ray toward the horizon is followed for the view's outline

var longest_side := LONGEST_SIDE  # bigger in the menu's preview
var docked := true  # in the corner of the screen; false where a container places it (the menu's preview)
var show_view := true  # the outline of what the camera sees (not in the menu's preview)
var labels: Array = []  # [tile, name, colour] marks drawn over the map: the civs' starts, in the preview
var _rich: Array = []  # [map position, colour] of each rich node
var _width := 0
var _height := 0
var _scale := 1.0  # pixels per tile
var _pixels := Vector2i.ZERO  # the picture's size
var _pixel_region := PackedInt32Array()  # per pixel: its tile's region, -1 for open sea
var _pixel_kind := PackedByteArray()  # per pixel: 0 land, 1 water, 2 peaks
var _pixel_border := PackedByteArray()  # per pixel: 1 on a border between regions
var _owners := {}  # region id -> civ id, absent while natives hold it
var _owners_signature := ""
var _capitals: Array[Vector2] = []  # region capitals, in tiles
var _civ_colors: Array = []
var _image: Image
var _texture: ImageTexture
var _armies := {}  # army id -> {"at": Vector2, "target": Vector2, "civ": int}
var _style := StyleBoxFlat.new()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	if docked:
		set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
		grow_horizontal = Control.GROW_DIRECTION_BEGIN
		grow_vertical = Control.GROW_DIRECTION_BEGIN
	_style.bg_color = Color(0.06, 0.075, 0.1, 0.85)
	_style.set_corner_radius_all(8)
	_style.set_border_width_all(1)
	_style.border_color = Color(1, 1, 1, 0.12)
	_style.shadow_color = Color(0, 0, 0, 0.35)
	_style.shadow_size = 8
	visible = false


## From the init message: the map's shape, its regions and where their capitals stand.
func setup(init: Dictionary, civ_colors: Array) -> void:
	_civ_colors = civ_colors
	var map: Dictionary = init["map"]
	_width = int(map["width"])
	_height = int(map["height"])
	_scale = longest_side / float(maxi(_width, _height))
	_rich.clear()
	for deposit: Dictionary in map.get("deposits", []):
		if deposit.get("rich"):
			_rich.append([Vector2(int(deposit["x"]), int(deposit["y"])),
				Color.html(init["deposit_types"][deposit["type"]]["color"])])
	_pixels = Vector2i(roundi(_width * _scale), roundi(_height * _scale))
	var size_px := Vector2(_pixels) + Vector2(MARGIN, MARGIN) * 2.0
	custom_minimum_size = size_px
	if docked:
		offset_left = -10.0 - size_px.x
		offset_top = -10.0 - size_px.y
		offset_right = -10.0
		offset_bottom = -10.0

	var water := {}
	var peaks := {}
	for biome: Dictionary in init["biomes"]:
		water[int(biome["id"])] = bool(biome["water"])
		peaks[int(biome["id"])] = str(biome["name"]) == "Peaks"
	var region_ids: Array = map["region_ids"]
	var biomes: Array = map["biomes"]
	var count := _pixels.x * _pixels.y
	_pixel_region.resize(count)
	_pixel_kind.resize(count)
	_pixel_border.resize(count)
	for py in _pixels.y:
		var ty := mini(int(py / _scale), _height - 1)
		for px in _pixels.x:
			var tx := mini(int(px / _scale), _width - 1)
			var tile := ty * _width + tx
			var i := py * _pixels.x + px
			_pixel_region[i] = int(region_ids[tile])
			var biome := int(biomes[tile])
			_pixel_kind[i] = 1 if water.get(biome, false) or int(region_ids[tile]) < 0 else (2 if peaks.get(biome, false) else 0)
	# A pixel lies on a border when the one right of it or below it is in another region.
	for py in _pixels.y:
		for px in _pixels.x:
			var i := py * _pixels.x + px
			var here := _pixel_region[i]
			var edge := false
			if px + 1 < _pixels.x and _pixel_region[i + 1] != here:
				edge = true
			elif py + 1 < _pixels.y and _pixel_region[i + _pixels.x] != here:
				edge = true
			_pixel_border[i] = 1 if edge and here >= 0 else 0

	_capitals.clear()
	for region: Dictionary in init["regions"]:
		_capitals.append(Vector2(float(region["x"]), float(region["y"])))
	_owners.clear()
	_owners_signature = ""
	_armies.clear()
	_image = Image.create(_pixels.x, _pixels.y, false, Image.FORMAT_RGB8)
	_paint()
	_texture = ImageTexture.create_from_image(_image)
	visible = true
	queue_redraw()


## From each tick: who holds each region (the picture is repainted only on a change) and
## where the field armies led by a general stand.
func update(data: Dictionary) -> void:
	if _width == 0:
		return
	var owners := {}
	for region: Dictionary in data["regions"]:
		if region["owner"] != null:
			owners[int(region["id"])] = int(region["owner"])
	var signature := str(owners)
	if signature != _owners_signature:
		_owners_signature = signature
		_owners = owners
		_paint()
		_texture.update(_image)

	var seen := {}
	for army: Dictionary in data["armies"]:
		if army["role"] != "field" or army["commander"] == null or army.get("in_castle", false):
			continue
		var id := int(army["id"])
		seen[id] = true
		var target := Vector2(float(army["x"]), float(army["y"]))
		if not _armies.has(id):
			_armies[id] = {"at": target, "target": target, "civ": int(army["civ"])}
		_armies[id]["target"] = target
	for id: int in _armies.keys():
		if not seen.has(id):
			_armies.erase(id)


func _paint() -> void:
	for py in _pixels.y:
		for px in _pixels.x:
			var i := py * _pixels.x + px
			var color: Color
			match _pixel_kind[i]:
				1:
					color = WATER
				2:
					color = PEAKS
				_:
					var owner: int = _owners.get(_pixel_region[i], -1)
					color = (_civ_colors[owner] as Color) * OWNED_SHADE if owner >= 0 and owner < _civ_colors.size() else NEUTRAL
			if _pixel_border[i] == 1:
				color = color * BORDER_SHADE
			color.a = 1.0
			_image.set_pixel(px, py, color)


func _process(delta: float) -> void:
	if not visible:
		return
	for entry: Dictionary in _armies.values():
		entry["at"] = (entry["at"] as Vector2).move_toward(entry["target"], MOVE_SPEED * delta)
	queue_redraw()  # the armies glide and the camera moves


## Tile coordinates to a point on the minimap.
func _to_map(tile: Vector2) -> Vector2:
	return Vector2(MARGIN, MARGIN) + (tile + Vector2(0.5, 0.5)) * _scale


func _draw() -> void:
	if _texture == null:
		return
	draw_style_box(_style, Rect2(Vector2.ZERO, size))
	var picture := Rect2(Vector2(MARGIN, MARGIN), Vector2(_pixels))
	draw_texture_rect(_texture, picture, false)
	for rich: Array in _rich:  # rich nodes: small diamonds in their resource's colour
		var at := _to_map(rich[0])
		draw_colored_polygon(PackedVector2Array([at + Vector2(0, -3), at + Vector2(3, 0), at + Vector2(0, 3), at + Vector2(-3, 0)]),
			rich[1])
	for capital: Vector2 in _capitals:
		draw_circle(_to_map(capital), 2.2, Color(0, 0, 0, 0.6))
		draw_circle(_to_map(capital), 1.5, Color.WHITE)
	for entry: Dictionary in _armies.values():
		var at := _to_map(entry["at"])
		var half := ARMY_SIZE * 0.5
		draw_rect(Rect2(at - Vector2(half + 1, half + 1), Vector2(ARMY_SIZE + 2, ARMY_SIZE + 2)), Color(0, 0, 0, 0.8))
		draw_rect(Rect2(at - Vector2(half, half), Vector2(ARMY_SIZE, ARMY_SIZE)), _civ_colors[int(entry["civ"])])
	var font := get_theme_default_font()
	for label: Array in labels:  # a civ's start: a ring in its colour and its name
		var at := _to_map(label[0])
		draw_circle(at, 7.0, Color(0, 0, 0, 0.75))
		draw_circle(at, 5.0, label[2])
		draw_string_outline(font, at + Vector2(9, 5), str(label[1]), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, 4, Color(0, 0, 0, 0.85))
		draw_string(font, at + Vector2(9, 5), str(label[1]), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, (label[2] as Color).lightened(0.4))
	if show_view:
		_draw_view(picture)


## The ground the camera sees: where the rays through the screen's corners meet the land,
## outlined and kept within the picture.
func _draw_view(picture: Rect2) -> void:
	var camera := get_viewport().get_camera_3d()
	if camera == null:
		return
	var screen := get_viewport().get_visible_rect().size
	var corners: Array[Vector2] = [Vector2.ZERO, Vector2(screen.x, 0), screen, Vector2(0, screen.y)]
	var outline := PackedVector2Array()
	for corner: Vector2 in corners:
		var origin := camera.project_ray_origin(corner)
		var direction := camera.project_ray_normal(corner)
		var t := FAR_GROUND
		if direction.y < -0.001:
			t = minf(FAR_GROUND, -origin.y / direction.y)
		var ground := origin + direction * t
		var point := Vector2(MARGIN, MARGIN) + Vector2(ground.x + 0.5, ground.z + 0.5) * _scale
		outline.append(point.clamp(picture.position, picture.end))
	outline.append(outline[0])
	draw_polyline(outline, Color(1, 1, 1, 0.9), 1.5, true)


func _gui_input(event: InputEvent) -> void:
	var pressed: bool = event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed
	var dragged: bool = event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0
	if pressed or dragged:
		var tile: Vector2 = (event.position - Vector2(MARGIN, MARGIN)) / _scale
		tile = tile.clamp(Vector2.ZERO, Vector2(_width - 1, _height - 1))
		jump_requested.emit(tile.x, tile.y)
		accept_event()
