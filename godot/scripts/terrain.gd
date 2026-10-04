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
const LAKE_DEPTH := 0.9  # how far the bed of a lake is sunk below its surface, so the water has depth
const TREES_PER_TILE := 2

const WATER_SHADER := """
shader_type spatial;
render_mode cull_disabled;

uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;
uniform vec3 shallow_color : source_color = vec3(0.33, 0.76, 0.82);
uniform vec3 mid_color : source_color = vec3(0.16, 0.50, 0.74);
uniform vec3 deep_color : source_color = vec3(0.07, 0.26, 0.52);
uniform vec3 foam_color : source_color = vec3(0.96, 0.98, 1.0);
uniform float depth_range = 3.2;
uniform float wave_height = 0.045;

varying vec3 world_position;

void vertex() {
	world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX.y += wave_height * (sin(world_position.x * 0.55 + TIME * 0.9) + cos(world_position.z * 0.45 + TIME * 0.7));
}

void fragment() {
	// How much water lies between the surface and whatever is behind it.
	float raw = texture(depth_texture, SCREEN_UV).r;
	vec4 behind = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	behind.xyz /= behind.w;
	float depth = max(0.0, VERTEX.z - behind.z);
	float t = clamp(depth / depth_range, 0.0, 1.0);
	// Three flat bands rather than a smooth fade, to sit with the low-poly models.
	vec3 color = t < 0.28 ? shallow_color : (t < 0.7 ? mid_color : deep_color);
	// A line of foam along the shore, breathing in and out.
	float ripple = 0.5 + 0.5 * sin(world_position.x * 1.7 + world_position.z * 1.3 + TIME * 1.6);
	float foam = 1.0 - smoothstep(0.0, 0.16 + 0.14 * ripple, depth);
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
	float streak = smoothstep(0.72, 1.0, 0.5 + 0.5 * sin(UV.x * 9.0 - TIME * 2.6 + UV.y * 3.0)) * (1.0 - across);
	float bank = smoothstep(0.72, 1.0, across);
	ALBEDO = mix(water_color, light_color, max(streak * 0.8, bank * 0.6));
}
"""

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
var _region_lines: MeshInstance3D
var _water_material: ShaderMaterial
var _trees: Array = []  # every forest tree: {multimesh, index, place, felled}
var _clearings := {}  # key -> [centre, radius]: where trees are felled for a large building


func build(map: Dictionary, biomes: Array, native_color: Color, models: RefCounted) -> void:
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

	var size := map_width * map_height
	var heights: Array = map["heights"]
	var biome_ids: Array = map["biomes"]
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
			mountains.append(i)

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
	_add_region_borders()
	_add_forests(forests, models)
	_add_mountains(mountains, models)


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
	return Vector3(x, maxf(_heights[y * map_width + x], 0.0) * HEIGHT_SCALE, y)


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


func toggle_region_borders() -> void:
	if _region_lines != null:
		_region_lines.visible = not _region_lines.visible


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
	surface_mesh.subdivide_width = 160  # enough vertices for the swell to show
	surface_mesh.subdivide_depth = 160
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


## Trees on every forest tile, a couple per tile, each a little different.
func _add_forests(forests: Array[int], models: RefCounted) -> void:
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
				var basis := Basis(Vector3.UP, roll * TAU).scaled(Vector3.ONE * (0.75 + 0.45 * _hash(tile * 3 + n * 71)))
				places.append(Transform3D(basis, Vector3(px, height_at(px, pz) + 0.05, pz)))
		var multimesh := _scatter(tree_mesh, places, models.base_material())
		for i in places.size():
			_trees.append({"multimesh": multimesh, "index": i, "place": places[i], "felled": false})


## Fells the trees within `radius` of `centre`, so a large building there stands clear.
## The clearing is remembered by `key`; remove_clearing puts the trees back.
func set_clearing(key: String, centre: Vector3, radius: float) -> void:
	_clearings[key] = [Vector2(centre.x, centre.z), radius]
	_apply_clearings()


func remove_clearing(key: String) -> void:
	if _clearings.erase(key):
		_apply_clearings()


func _apply_clearings() -> void:
	for tree: Dictionary in _trees:
		var place: Transform3D = tree["place"]
		var at := Vector2(place.origin.x, place.origin.z)
		var felled := false
		for clearing: Array in _clearings.values():
			if at.distance_to(clearing[0]) <= float(clearing[1]):
				felled = true
				break
		if felled != tree["felled"]:
			tree["felled"] = felled
			# A felled tree is shrunk to nothing rather than removed, so it can come back.
			var shown: Transform3D = place.scaled_local(Vector3.ZERO) if felled else place
			(tree["multimesh"] as MultiMesh).set_instance_transform(int(tree["index"]), shown)


## Peaks on the mountain tiles: not one per tile, which would be a wall, but enough to read as a range.
func _add_mountains(mountains: Array[int], models: RefCounted) -> void:
	var kinds := ["mountain_A", "mountain_B", "mountain_C"]
	for kind in kinds.size():
		var peak_mesh: Mesh = models.mesh(kinds[kind])
		if peak_mesh == null:
			continue
		var places: Array[Transform3D] = []
		for tile: int in mountains:
			var x := tile % map_width
			var z := tile / map_width
			# About one tile in three, picked irregularly and nudged off-centre so no pattern shows.
			if _hash(tile * 23 + 7) > 0.36 or int(_hash(tile * 11) * 1000.0) % kinds.size() != kind:
				continue
			var px := float(x) + (_hash(tile * 41) - 0.5) * 0.7
			var pz := float(z) + (_hash(tile * 43) - 0.5) * 0.7
			var basis := Basis(Vector3.UP, _hash(tile * 5) * TAU).scaled(Vector3.ONE * (0.7 + 0.6 * _hash(tile * 19)))
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
