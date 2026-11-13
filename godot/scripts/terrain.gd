extends Node3D
## Terrain mesh built from the sim's heightmap: one vertex per tile, coloured by
## biome and tinted with the owning civ's colour, or the native faction's where no civ
## holds the land. Region borders are drawn as dark lines. Tile (x, y) sits at world (x, h, y).
## Forests and mountains are dressed with models, and the sea, lakes and rivers are
## drawn with small shaders: banded depth colour, foam at the shore, moving water.

const HEIGHT_SCALE := 9.0
const BORDER_TINT := 0.8  # the tile on a civ's border
const NEAR_BORDER_TINT := 0.4  # the tile behind it
const INTERIOR_TINT := 0.1  # everything further in: the land shows through
const UNOWNED := 255
const RIVER_COLOR := Color(0.2, 0.5, 0.9)
const NATIVE_TINT := 0.16
const REGION_BORDER_COLOR := Color(0.07, 0.07, 0.09)
const REGION_BORDER_WIDTH := 0.14
const CASTLE_PAD := 2  # tiles each way from a capital that are levelled flat for its castle ...
const PAD_EASE := 2  # ... and how many more over which the level eases back into the land
const PAD_ABOVE_SEA := 0.02  # a castle's ground stays at least this high (in map height) above the sea
const LAKE_DEPTH := 0.9  # how far the bed of a lake is sunk below its surface, so the water has depth
const TREES_PER_TILE := 2
const STAND_SHARE := 0.35  # share of forest tiles drawn as a stand of trees rather than single ones
## Trees are drawn at this share of the pack's size, as its buildings are fitted to a tile: at full
## size a forest stood over the armies and hid their generals.
const TREE_SCALE := 0.68

const WATER_SHADER := """
shader_type spatial;
render_mode cull_disabled;

uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;
uniform vec3 shallow_color : source_color = vec3(0.33, 0.76, 0.82);
uniform vec3 mid_color : source_color = vec3(0.16, 0.50, 0.74);
uniform vec3 deep_color : source_color = vec3(0.07, 0.26, 0.52);
uniform vec3 foam_color : source_color = vec3(0.96, 0.98, 1.0);
uniform float depth_range = 3.2;
uniform float foam_width = 0.23;

// The water is still: the surface stays flat at its level, so it never rises over the shore.
// (A swell used to lift it by up to 0.09, which carried it onto low-lying land.)

void fragment() {
	// How much water lies between the surface and whatever is behind it.
	float raw = texture(depth_texture, SCREEN_UV).r;
	vec4 behind = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	behind.xyz /= behind.w;
	float depth = max(0.0, VERTEX.z - behind.z);
	float t = clamp(depth / depth_range, 0.0, 1.0);
	// Three flat bands rather than a smooth fade, to sit with the low-poly models.
	vec3 color = t < 0.28 ? shallow_color : (t < 0.7 ? mid_color : deep_color);
	// A line of foam along the shore, of a steady width.
	float foam = 1.0 - smoothstep(0.0, foam_width, depth);
	ALBEDO = mix(color, foam_color, foam);
	ALPHA = mix(0.80, 0.97, t);
	ROUGHNESS = 0.18;
	SPECULAR = 0.45;
}
"""

const RIVER_SHADER := """
shader_type spatial;
render_mode cull_disabled, unshaded;

uniform vec3 water_color : source_color = vec3(0.20, 0.55, 0.86);
uniform vec3 light_color : source_color = vec3(0.70, 0.90, 1.0);

void fragment() {
	// UV.x runs along the river, UV.y across it.
	float across = abs(UV.y - 0.5) * 2.0;
	// Light streaks along the current, standing still.
	float streak = smoothstep(0.72, 1.0, 0.5 + 0.5 * sin(UV.x * 9.0 + UV.y * 3.0)) * (1.0 - across);
	float bank = smoothstep(0.72, 1.0, across);
	ALBEDO = mix(water_color, light_color, max(streak * 0.8, bank * 0.6));
}
"""

var _deck := {}  # tile -> the height of the bridge deck over it, for tiles under a long bridge
const DECK_TOP := 0.24  # a bridge deck's walking surface above where the model stands
var map_width := 0
var map_height := 0

var _heights := PackedFloat32Array()
var _base_colors := PackedColorArray()
var _vertices := PackedVector3Array()
var _normals := PackedVector3Array()
var _indices := PackedInt32Array()
var _land: MeshInstance3D
var _material: StandardMaterial3D
var _region_ids := PackedInt32Array()
var _is_land := PackedByteArray()
var _native_color := Color(0.6, 0.55, 0.48)
var _castle_ground := {}  # tiles where a capital's castle stands, and the ring around them
var _region_lines: MeshInstance3D
var _water_material: ShaderMaterial
var _trees: Array = []  # every forest tree: {multimesh, index, place, felled}
var _clearings := {}  # key -> [centre, radius]: where trees are felled for a large building


## `capitals` is the init message's list of regions: each capital's ground is levelled for its castle.
func build(map: Dictionary, biomes: Array, native_color: Color, models: RefCounted, capitals: Array = []) -> void:
	_deck.clear()
	for child in get_children():
		child.queue_free()
	_trees.clear()
	_clearings.clear()
	map_width = int(map["width"])
	map_height = int(map["height"])

	_native_color = native_color
	var palette := {}
	var water := {}
	var ids := {}  # biome name -> id
	for biome: Dictionary in biomes:
		palette[int(biome["id"])] = Color.html(biome["color"])
		water[int(biome["id"])] = biome["water"]
		ids[biome["name"]] = int(biome["id"])
	var lakes: Array[int] = []
	var forests: Array[int] = []
	var mountains: Array[int] = []
	var high_peaks: Array[int] = []  # impassable: drawn as a solid wall of peaks
	var hills: Array[int] = []

	var size := map_width * map_height
	var biome_ids: Array = map["biomes"]
	var passes := {}  # tiles of a pass: walked through, so kept clear of peaks
	for tile: Dictionary in map.get("passes", []):
		passes[int(tile["y"]) * int(map["width"]) + int(tile["x"])] = true
	var heights: Array = _level_capitals(map["heights"], biome_ids, water, capitals)
	_heights.resize(size)
	_region_ids.resize(size)
	_is_land.resize(size)
	_base_colors.resize(size)
	_vertices.resize(size)
	_normals.resize(size)
	for i in size:
		var h := float(heights[i])
		_heights[i] = h
		_region_ids[i] = int(map["region_ids"][i])
		_is_land[i] = 0 if water[int(biome_ids[i])] else 1
		# Shade by altitude so relief reads even where the biome is uniform.
		var color: Color = palette[int(biome_ids[i])]
		_base_colors[i] = color.darkened(0.25).lerp(color.lightened(0.15), clampf(h, 0.0, 1.0))
		_vertices[i] = Vector3(i % map_width, h * HEIGHT_SCALE, i / map_width)
		var biome_id := int(biome_ids[i])
		if biome_id == ids.get("Lake", -1):
			# The lake's bed is sunk below its surface; the water is drawn separately at the surface.
			lakes.append(i)
			_vertices[i].y -= LAKE_DEPTH
			_base_colors[i] = Color(0.55, 0.5, 0.38)
		elif biome_id == ids.get("Forest", -1):
			forests.append(i)
		elif biome_id == ids.get("Mountain", -1):
			if passes.has(i):
				hills.append(i)
			else:
				mountains.append(i)
		elif biome_id == ids.get("Peaks", -1):
			high_peaks.append(i)
		elif biome_id == ids.get("Hills", -1):
			hills.append(i)

	# Rivers run through land tiles: darken the bank a little under the ribbon drawn by _add_rivers.
	for river: Dictionary in map.get("rivers", []):
		var tile := int(river["y"]) * map_width + int(river["x"])
		_base_colors[tile] = _base_colors[tile].lerp(RIVER_COLOR, 0.25)

	for y in map_height:
		for x in map_width:
			var left := _world_height(x - 1, y)
			var right := _world_height(x + 1, y)
			var up := _world_height(x, y - 1)
			var down := _world_height(x, y + 1)
			_normals[y * map_width + x] = Vector3(left - right, 2.0, up - down).normalized()

	_indices.clear()
	for y in map_height - 1:
		for x in map_width - 1:
			var i := y * map_width + x
			# Clockwise seen from above = front face up.
			_indices.append_array([i, i + 1, i + map_width, i + 1, i + map_width + 1, i + map_width])

	_material = StandardMaterial3D.new()
	_material.vertex_color_use_as_albedo = true
	_material.vertex_color_is_srgb = true
	_material.roughness = 1.0

	_land = MeshInstance3D.new()
	add_child(_land)
	_commit(_base_colors)
	_water_material = ShaderMaterial.new()
	var water_shader := Shader.new()
	water_shader.code = WATER_SHADER
	_water_material.shader = water_shader
	_add_sea()
	_add_lakes(lakes)
	_add_rivers(map, biomes)
	_add_bridges(map, models)
	_add_region_borders()
	_add_forests(forests, models)
	_add_mountains(mountains, models)
	_add_high_peaks(high_peaks, models)
	_add_hills(hills, models)
	_add_shallows(lakes, models)


## The ground under each region capital, levelled so its castle stands on it rather than
## half inside a hillside: flat across the castle's square, then easing back into the land
## around it. Only the drawn ground changes; water tiles and the simulation's map do not.
func _level_capitals(heights: Array, biome_ids: Array, water: Dictionary, capitals: Array) -> Array:
	var levelled := heights.duplicate()
	_castle_ground.clear()
	for capital: Dictionary in capitals:
		var cx := int(capital["x"])
		var cy := int(capital["y"])
		# No peak or boulder stands where the castle will.
		for dy in range(-CASTLE_PAD - 1, CASTLE_PAD + 2):
			for dx in range(-CASTLE_PAD - 1, CASTLE_PAD + 2):
				if cx + dx >= 0 and cy + dy >= 0 and cx + dx < map_width and cy + dy < map_height:
					_castle_ground[(cy + dy) * map_width + cx + dx] = true
		var ground: Array[float] = []
		for dy in range(-CASTLE_PAD, CASTLE_PAD + 1):
			for dx in range(-CASTLE_PAD, CASTLE_PAD + 1):
				var x := cx + dx
				var y := cy + dy
				if x >= 0 and y >= 0 and x < map_width and y < map_height and not water[int(biome_ids[y * map_width + x])]:
					ground.append(float(levelled[y * map_width + x]))
		if ground.is_empty():
			continue
		ground.sort()
		var pad := maxf(ground[ground.size() / 2], PAD_ABOVE_SEA)  # the middle height: no deep pit, no tall mound
		var reach := CASTLE_PAD + PAD_EASE
		for dy in range(-reach, reach + 1):
			for dx in range(-reach, reach + 1):
				var x := cx + dx
				var y := cy + dy
				if x < 0 or y < 0 or x >= map_width or y >= map_height:
					continue
				var i := y * map_width + x
				if water[int(biome_ids[i])]:
					continue  # the shore stays where it is
				var away := maxi(absi(dx), absi(dy)) - CASTLE_PAD  # 0 or less: under the castle
				var keep := clampf(float(away) / float(PAD_EASE + 1), 0.0, 1.0)
				levelled[i] = lerpf(pad, float(levelled[i]), keep)
	return levelled


## Height of the ground at any point, between tile centres as well as on them.
func height_at(x: float, z: float) -> float:
	var x0 := clampi(floori(x), 0, map_width - 2)
	var z0 := clampi(floori(z), 0, map_height - 2)
	var fx := clampf(x - x0, 0.0, 1.0)
	var fz := clampf(z - z0, 0.0, 1.0)
	var top := lerpf(_world_height(x0, z0), _world_height(x0 + 1, z0), fx)
	var bottom := lerpf(_world_height(x0, z0 + 1), _world_height(x0 + 1, z0 + 1), fx)
	return lerpf(top, bottom, fz)


func center() -> Vector3:
	return Vector3((map_width - 1) / 2.0, 0.0, (map_height - 1) / 2.0)


## World position of a tile's surface; water tiles report the sea surface.
func tile_position(x: int, y: int) -> Vector3:
	var tile := y * map_width + x
	if _deck.has(tile):
		return Vector3(x, _deck[tile], y)  # on a bridge over water
	return Vector3(x, maxf(_heights[tile], 0.0) * HEIGHT_SCALE, y)


## `territory` is base64 of one byte per tile: the owning civ's id, or 255 if unowned.
func apply_territory(territory: String, civ_colors: Array) -> void:
	var owners := Marshalls.base64_to_raw(territory)
	if owners.size() != _base_colors.size():
		return
	# Which tiles lie on a civ's border.
	var edge := PackedByteArray()
	edge.resize(owners.size())
	for i in owners.size():
		var civ := owners[i]
		if civ >= civ_colors.size():
			continue
		var x := i % map_width
		var y := i / map_width
		if ((x > 0 and owners[i - 1] != civ) or (x < map_width - 1 and owners[i + 1] != civ)
				or (y > 0 and owners[i - map_width] != civ) or (y < map_height - 1 and owners[i + map_width] != civ)):
			edge[i] = 1

	# Colour a band along each border strongly and leave the interior close to the land's own colours.
	var colors := _base_colors.duplicate()
	for i in owners.size():
		var civ := owners[i]
		if civ >= civ_colors.size():
			# No civ holds it: native land shows the native faction's colour.
			if _is_land[i] == 1 and _region_ids[i] >= 0:
				colors[i] = colors[i].lerp(_native_color, NATIVE_TINT)
			continue
		var tint := INTERIOR_TINT
		if edge[i] == 1:
			tint = BORDER_TINT
		else:
			var x := i % map_width
			var y := i / map_width
			if ((x > 0 and edge[i - 1] == 1) or (x < map_width - 1 and edge[i + 1] == 1)
					or (y > 0 and edge[i - map_width] == 1) or (y < map_height - 1 and edge[i + map_width] == 1)):
				tint = NEAR_BORDER_TINT
		var civ_color: Color = civ_colors[civ]
		colors[i] = colors[i].lerp(civ_color, tint)
	_commit(colors)


func set_region_borders(on: bool) -> void:
	if _region_lines != null:
		_region_lines.visible = on


func _world_height(x: int, y: int) -> float:
	x = clampi(x, 0, map_width - 1)
	y = clampi(y, 0, map_height - 1)
	return _heights[y * map_width + x] * HEIGHT_SCALE


func _commit(colors: PackedColorArray) -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _vertices
	arrays[Mesh.ARRAY_NORMAL] = _normals
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = _indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, _material)
	_land.mesh = mesh


## Rivers as ribbons lying on the terrain, drawn along the way the water actually
## flows: each river tile is joined to the one tile it drains into and to the tiles
## that drain into it, and to nothing else. So a river is a single clean course even
## where it passes close to another, and a tributary meets the main river at one point
## instead of tangling with it. Wider rivers get wider ribbons, and the shader makes
## the surface run.
func _add_rivers(map: Dictionary, biomes: Array) -> void:
	var water_biomes := {}
	for biome: Dictionary in biomes:
		if biome["water"]:
			water_biomes[int(biome["id"])] = true
	var sizes := {}
	var downstream := {}  # river tile -> the tile its water flows into
	var upstream := {}  # river tile -> the river tiles that flow into it
	for river: Dictionary in map.get("rivers", []):
		var tile := int(river["y"]) * map_width + int(river["x"])
		var into := int(river["to"][1]) * map_width + int(river["to"][0])
		sizes[tile] = float(river["size"])
		downstream[tile] = into
		if not upstream.has(into):
			upstream[into] = []
		upstream[into].append(tile)
	if sizes.is_empty():
		return

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var lift := Vector3(0, 0.14, 0)
	for tile: int in sizes:
		var here: Vector3 = tile_position(tile % map_width, tile / map_width) + lift
		var into: int = downstream[tile]
		var there: Vector3 = tile_position(into % map_width, into / map_width) + lift
		# A mouth runs a little way out into the water rather than stopping at the bank.
		var into_water: bool = water_biomes.has(int(map["biomes"][into]))
		var exit := here.lerp(there, 0.8 if into_water else 0.5)
		var width: float = 0.11 + 0.07 * float(sizes[tile])
		var feeders: Array = upstream.get(tile, [])
		if feeders.is_empty():
			_river_ribbon(surface, here, here.lerp(exit, 0.5), exit, width)  # a spring
		for feeder: int in feeders:
			var from: Vector3 = tile_position(feeder % map_width, feeder / map_width) + lift
			# Each feeder arrives at its own width and leaves at this tile's.
			_river_ribbon(surface, here.lerp(from, 0.5), here, exit, width)

	var material := ShaderMaterial.new()
	var shader := Shader.new()
	shader.code = RIVER_SHADER
	material.shader = shader
	var ribbons := MeshInstance3D.new()
	ribbons.mesh = surface.commit()
	ribbons.material_override = material
	ribbons.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(ribbons)


## One stretch of river: a curve from `from` to `to`, pulled toward `through`.
func _river_ribbon(surface: SurfaceTool, from: Vector3, through: Vector3, to: Vector3, width: float) -> void:
	const STEPS := 6
	var previous_left := Vector3.ZERO
	var previous_right := Vector3.ZERO
	for step in STEPS + 1:
		var t := float(step) / STEPS
		var point := from.lerp(through, t).lerp(through.lerp(to, t), t)
		var heading := (through - from).lerp(to - through, t)
		var side := heading.cross(Vector3.UP).normalized() * width
		var left := point - side
		var right := point + side
		if step > 0:
			var u0 := float(step - 1) / STEPS
			for corner: Array in [[previous_left, u0, 0.0], [previous_right, u0, 1.0], [right, t, 1.0],
					[previous_left, u0, 0.0], [right, t, 1.0], [left, t, 0.0]]:
				surface.set_uv(Vector2(corner[1], corner[2]))
				surface.set_normal(Vector3.UP)
				surface.add_vertex(corner[0])
		previous_left = left
		previous_right = right


## Dark lines along every edge where two regions meet.
func _add_region_borders() -> void:
	var material := StandardMaterial3D.new()
	material.albedo_color = REGION_BORDER_COLOR
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var half := REGION_BORDER_WIDTH / 2.0
	var any := false
	for y in map_height:
		for x in map_width:
			var here := _region_ids[y * map_width + x]
			if here < 0:
				continue
			# Edge shared with the tile to the east, then with the tile to the south.
			for step: Vector2i in [Vector2i(1, 0), Vector2i(0, 1)]:
				var nx := x + step.x
				var ny := y + step.y
				if nx >= map_width or ny >= map_height:
					continue
				var there := _region_ids[ny * map_width + nx]
				if there < 0 or there == here:
					continue
				var top := maxf(maxf(_world_height(x, y), _world_height(nx, ny)), 0.0) + 0.16
				var mid := Vector3(x + step.x * 0.5, top, y + step.y * 0.5)
				var along := Vector3(0.5 * step.y, 0, 0.5 * step.x)  # the edge runs across the step
				var across := Vector3(half * step.x, 0, half * step.y)
				var a := mid - along
				var b := mid + along
				for corner: Vector3 in [a - across, a + across, b + across, a - across, b + across, b - across]:
					surface.add_vertex(corner)
				any = true
	if not any:
		return
	var lines := MeshInstance3D.new()
	lines.mesh = surface.commit()
	lines.material_override = material
	lines.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(lines)
	_region_lines = lines


func _add_sea() -> void:
	var extent := Vector2(map_width + 400, map_height + 400)
	var surface := MeshInstance3D.new()
	var surface_mesh := PlaneMesh.new()
	surface_mesh.size = extent
	surface.mesh = surface_mesh
	surface.material_override = _water_material
	surface.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	surface.position = center()
	add_child(surface)

	# Sea floor beyond the edge of the map, level with the deepest terrain.
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_color = Color(0.07, 0.2, 0.38)
	floor_material.roughness = 1.0
	var sea_floor := MeshInstance3D.new()
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = extent
	floor_mesh.material = floor_material
	sea_floor.mesh = floor_mesh
	sea_floor.position = center() + Vector3(0, -0.5 * HEIGHT_SCALE - 0.05, 0)
	add_child(sea_floor)


## A sheet of water over every lake tile, at the lake's own level, drawn like the sea.
func _add_lakes(lakes: Array[int]) -> void:
	if lakes.is_empty():
		return
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for tile: int in lakes:
		var x := tile % map_width
		var z := tile / map_width
		var level := _world_height(x, z) - 0.08
		var a := Vector3(x - 0.5, level, z - 0.5)
		var b := Vector3(x + 0.5, level, z - 0.5)
		var c := Vector3(x + 0.5, level, z + 0.5)
		var d := Vector3(x - 0.5, level, z + 0.5)
		for corner: Vector3 in [a, b, c, a, c, d]:
			surface.set_normal(Vector3.UP)
			surface.add_vertex(corner)
	var water := MeshInstance3D.new()
	water.mesh = surface.commit()
	water.material_override = _water_material
	water.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(water)


## Trees on every forest tile: on most a couple of single trees, each a little different;
## on some a whole stand, so a forest has thickets and glades rather than an even planting.
func _add_forests(forests: Array[int], models: RefCounted) -> void:
	var stands := ["trees_A_small", "trees_A_medium", "trees_B_small", "trees_B_medium"]
	var thick: Array[int] = []
	var open: Array[int] = []
	for tile: int in forests:
		(thick if _hash(tile * 59 + 3) < STAND_SHARE else open).append(tile)
	for kind in stands.size():
		var stand_mesh: Mesh = models.mesh(stands[kind])
		if stand_mesh == null:
			open.append_array(thick.filter(func(t: int) -> bool: return int(_hash(t * 61) * 1000.0) % stands.size() == kind))
			continue
		var places: Array[Transform3D] = []
		for tile: int in thick:
			if int(_hash(tile * 61) * 1000.0) % stands.size() != kind:
				continue
			var px := float(tile % map_width) + (_hash(tile * 67) - 0.5) * 0.3
			var pz := float(tile / map_width) + (_hash(tile * 71) - 0.5) * 0.3
			var basis := Basis(Vector3.UP, _hash(tile * 73) * TAU).scaled(Vector3.ONE * TREE_SCALE * (0.5 + 0.12 * _hash(tile * 79)))
			places.append(Transform3D(basis, Vector3(px, height_at(px, pz) + 0.02, pz)))
		var multimesh := _scatter(stand_mesh, places, models.base_material())
		for i in places.size():
			_trees.append({"multimesh": multimesh, "index": i, "place": places[i], "felled": false})
	forests = open
	var kinds := ["tree_single_A", "tree_single_B"]
	for kind in kinds.size():
		var tree_mesh: Mesh = models.mesh(kinds[kind])
		if tree_mesh == null:
			continue
		var places: Array[Transform3D] = []
		for tile: int in forests:
			for n in TREES_PER_TILE:
				# Deterministic scatter: the same forest every time the map is drawn.
				var roll := _hash(tile * 7 + n * 131)
				if int(roll * 1000.0) % kinds.size() != kind:
					continue
				var px := float(tile % map_width) + (_hash(tile * 13 + n * 17) - 0.5) * 0.8
				var pz := float(tile / map_width) + (_hash(tile * 29 + n * 37) - 0.5) * 0.8
				var basis := Basis(Vector3.UP, roll * TAU).scaled(Vector3.ONE * TREE_SCALE * (0.75 + 0.45 * _hash(tile * 3 + n * 71)))
				places.append(Transform3D(basis, Vector3(px, height_at(px, pz) + 0.05, pz)))
		var multimesh := _scatter(tree_mesh, places, models.base_material())
		for i in places.size():
			_trees.append({"multimesh": multimesh, "index": i, "place": places[i], "felled": false})


## Fells the trees in the square reaching `radius` each way from `centre`, so a building there stands clear.
## The clearing is remembered by `key`; remove_clearing puts the trees back.
func set_clearing(key: String, centre: Vector3, radius: float) -> void:
	var at := Vector2(centre.x, centre.z)
	_clearings[key] = [at, radius]
	for tree: Dictionary in _trees:  # a new clearing only ever fells: no need to look at the others
		var place: Transform3D = tree["place"]
		if not tree["felled"] and absf(place.origin.x - at.x) <= radius and absf(place.origin.z - at.y) <= radius:
			tree["felled"] = true
			(tree["multimesh"] as MultiMesh).set_instance_transform(int(tree["index"]), place.scaled_local(Vector3.ZERO))


func remove_clearing(key: String) -> void:
	if _clearings.erase(key):
		_apply_clearings()


func _apply_clearings() -> void:
	for tree: Dictionary in _trees:
		var place: Transform3D = tree["place"]
		var at := Vector2(place.origin.x, place.origin.z)
		var felled := false
		for clearing: Array in _clearings.values():
			var centre: Vector2 = clearing[0]
			if absf(at.x - centre.x) <= float(clearing[1]) and absf(at.y - centre.y) <= float(clearing[1]):
				felled = true
				break
		if felled != tree["felled"]:
			tree["felled"] = felled
			# A felled tree is shrunk to nothing rather than removed, so it can come back.
			var shown: Transform3D = place.scaled_local(Vector3.ZERO) if felled else place
			(tree["multimesh"] as MultiMesh).set_instance_transform(int(tree["index"]), shown)


## Peaks on the mountain tiles: not one per tile, which would be a wall, but enough to read as a
## range, and loose stones between them. (The pack's grassy and wooded peaks rise in
## hexagonal terraces, which do not sit on a square map.)
func _add_mountains(mountains: Array[int], models: RefCounted) -> void:
	# Mountains are walls to armies and villagers (only passes lead through): drawn thick enough
	# to read as one.
	_add_peaks(mountains, ["mountain_A", "mountain_B", "mountain_C"], models, 0.6)
	_add_scatter(mountains, ["rock_single_D", "rock_single_E"], 0.3, 0.5, 0.0, models)


## A stone here and there on the hills. (The pack's hill models stand on hexagonal plinths,
## which do not sit on a square map; the relief of the ground itself shows the hills.)
func _add_hills(hills: Array[int], models: RefCounted) -> void:
	_add_scatter(hills, ["rock_single_D", "rock_single_E"], 0.2, 0.6, 0.0, models)


## Lilies and reeds on some lake tiles, near their edge.
func _add_shallows(lakes: Array[int], models: RefCounted) -> void:
	var places := {}  # model -> transforms
	var kinds := ["waterlily_A", "waterlily_B", "waterplant_A", "waterplant_B", "waterplant_C"]
	for tile: int in lakes:
		if _hash(tile * 83 + 1) > 0.35:
			continue
		var x := tile % map_width
		var z := tile / map_width
		var level := _world_height(x, z) - 0.08 + LAKE_DEPTH
		for n in 3:
			var kind: String = kinds[int(_hash(tile * 89 + n * 97) * 1000.0) % kinds.size()]
			var px := float(x) + (_hash(tile * 101 + n) - 0.5) * 0.8
			var pz := float(z) + (_hash(tile * 103 + n) - 0.5) * 0.8
			var basis := Basis(Vector3.UP, _hash(tile * 107 + n) * TAU).scaled(Vector3.ONE * 1.4)
			if not places.has(kind):
				places[kind] = [] as Array[Transform3D]
			(places[kind] as Array[Transform3D]).append(Transform3D(basis, Vector3(px, level, pz)))
	for kind: String in places:
		var mesh: Mesh = models.mesh(kind)
		if mesh != null:
			_scatter(mesh, places[kind], models.base_material())


## One of `kinds` on about `share` of the tiles, off-centre, at about `size` times its own size.
func _add_scatter(tiles: Array[int], kinds: Array, share: float, size: float, sink: float, models: RefCounted) -> void:
	for kind in kinds.size():
		var mesh: Mesh = models.mesh(kinds[kind])
		if mesh == null:
			continue
		var places: Array[Transform3D] = []
		for tile: int in tiles:
			var seed := tile * 109 + kinds.size() * 7 + int(size * 100.0)
			if _hash(seed) > share or int(_hash(seed + 1) * 1000.0) % kinds.size() != kind or _castle_ground.has(tile):
				continue
			var px := float(tile % map_width) + (_hash(seed + 2) - 0.5) * 0.7
			var pz := float(tile / map_width) + (_hash(seed + 3) - 0.5) * 0.7
			var basis := Basis(Vector3.UP, _hash(seed + 4) * TAU).scaled(Vector3.ONE * size * (0.8 + 0.4 * _hash(seed + 5)))
			places.append(Transform3D(basis, Vector3(px, height_at(px, pz) + sink, pz)))
		_scatter(mesh, places, models.base_material())


## The bridges of a drawn map. Over a river, the pack's stone bridge, square to the flow. Over
## shallow water, one long bridge laid whole from one shore to the other (a deck stretched to
## the length, with supports every couple of tiles), the only way over on foot.
func _add_bridges(map: Dictionary, models: RefCounted) -> void:
	var flow := {}
	for river: Dictionary in map["rivers"]:
		flow[Vector2i(int(river["x"]), int(river["y"]))] = Vector2i(int(river["to"][0]), int(river["to"][1]))
	var stone: Mesh = models.mesh("building_bridge_A")
	if stone != null:
		var places: Array[Transform3D] = []
		for bridge: Dictionary in map.get("bridges", []):
			var at := Vector2i(int(bridge["x"]), int(bridge["y"]))
			if not flow.has(at):
				continue  # a long bridge's tile: drawn with the span below
			var along: Vector2i = flow[at] - at
			# The model runs along its own z axis; turn that across the river's way.
			var angle := PI / 2.0 if along.y != 0 else 0.0
			var basis := Basis(Vector3.UP, angle).scaled(Vector3.ONE * 0.9)
			places.append(Transform3D(basis, Vector3(at.x, height_at(at.x, at.y) + 0.02, at.y)))
		_scatter(stone, places, models.base_material())
	var deck: Mesh = models.mesh("civsim_bridge")
	var pier: Mesh = models.mesh("civsim_bridge_pier")
	if deck == null:
		return
	var decks: Array[Transform3D] = []
	var piers: Array[Transform3D] = []
	for span: Dictionary in map.get("spans", []):
		var a := Vector3(float(span["from"][0]), 0.0, float(span["from"][1]))
		var b := Vector3(float(span["to"][0]), 0.0, float(span["to"][1]))
		var length := a.distance_to(b)
		if length < 0.5:
			continue
		# Level with the higher shore, and never below the water.
		var level := maxf(0.05, maxf(height_at(a.x, a.z), height_at(b.x, b.z)))
		var way := (b - a).normalized()
		var basis := Basis.looking_at(way, Vector3.UP)  # its -z along the way; the deck runs along z either way
		var middle := (a + b) / 2.0
		# Whoever crosses walks on the deck, not in the water under it.
		for k in range(int(length * 4.0) + 1):
			var on := a.lerp(b, k / (length * 4.0))
			var tile := roundi(on.z) * map_width + roundi(on.x)
			if tile >= 0 and tile < _heights.size() and _heights[tile] <= 0.0:
				_deck[tile] = level + DECK_TOP
		decks.append(Transform3D(basis * Basis.from_scale(Vector3(1.0, 1.0, length)), Vector3(middle.x, level, middle.z)))
		var count := maxi(1, int(length / 1.8))
		for k in range(1, count + 1):
			var at := a.lerp(b, float(k) / float(count + 1))
			piers.append(Transform3D(basis, Vector3(at.x, level, at.z)))
	_scatter(deck, decks, models.base_material())
	if pier != null:
		_scatter(pier, piers, models.base_material())


## High peaks no army can cross: a peak on every tile, taller than on ordinary mountains, so the
## range reads as a wall with its passes the only way through.
func _add_high_peaks(peaks: Array[int], models: RefCounted) -> void:
	_add_peaks(peaks, ["mountain_A", "mountain_B", "mountain_C"], models, 1.0, 1.15, 0.5)


func _add_peaks(mountains: Array[int], kinds: Array, models: RefCounted, share: float = 0.36,
		least: float = 0.7, spread: float = 0.6) -> void:
	for kind in kinds.size():
		var peak_mesh: Mesh = models.mesh(kinds[kind])
		if peak_mesh == null:
			continue
		var places: Array[Transform3D] = []
		for tile: int in mountains:
			var x := tile % map_width
			var z := tile / map_width
			# About one tile in three, picked irregularly and nudged off-centre so no pattern shows.
			if _hash(tile * 23 + 7) > share or int(_hash(tile * 11) * 1000.0) % kinds.size() != kind or _castle_ground.has(tile):
				continue
			var px := float(x) + (_hash(tile * 41) - 0.5) * 0.7
			var pz := float(z) + (_hash(tile * 43) - 0.5) * 0.7
			var basis := Basis(Vector3.UP, _hash(tile * 5) * TAU).scaled(Vector3.ONE * (least + spread * _hash(tile * 19)))
			places.append(Transform3D(basis, Vector3(px, height_at(px, pz) - 0.15, pz)))
		_scatter(peak_mesh, places, models.base_material())


## Many copies of one mesh, drawn in a single batch.
func _scatter(mesh: Mesh, places: Array[Transform3D], material: Material) -> MultiMesh:
	if places.is_empty():
		return null
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = mesh
	multimesh.instance_count = places.size()
	for i in places.size():
		multimesh.set_instance_transform(i, places[i])
	var instance := MultiMeshInstance3D.new()
	instance.multimesh = multimesh
	instance.material_override = material
	add_child(instance)
	return multimesh


## A repeatable pseudo-random number in [0, 1) for an integer.
func _hash(n: int) -> float:
	var value := sin(float(n) * 12.9898) * 43758.5453
	return value - floorf(value)
