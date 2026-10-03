extends Node3D
## Terrain mesh built from the sim's heightmap: one vertex per tile, coloured by
## biome and tinted with the owning civ's colour, or the native faction's where no civ
## holds the land. Region borders are drawn as dark lines. Tile (x, y) sits at world (x, h, y).

const HEIGHT_SCALE := 9.0
const TERRITORY_TINT := 0.3
const BORDER_TINT := 0.8
const UNOWNED := 255
const RIVER_COLOR := Color(0.2, 0.5, 0.9)
const NATIVE_TINT := 0.3
const REGION_BORDER_COLOR := Color(0.07, 0.07, 0.09)
const REGION_BORDER_WIDTH := 0.14

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


func build(map: Dictionary, biomes: Array, native_color: Color) -> void:
	for child in get_children():
		child.queue_free()
	map_width = int(map["width"])
	map_height = int(map["height"])

	_native_color = native_color
	var palette := {}
	var water := {}
	for biome: Dictionary in biomes:
		palette[int(biome["id"])] = Color.html(biome["color"])
		water[int(biome["id"])] = biome["water"]

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
	_add_sea()
	_add_rivers(map, biomes)
	_add_region_borders()


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
	var colors := _base_colors.duplicate()
	for i in owners.size():
		var civ := owners[i]
		if civ >= civ_colors.size():
			# No civ holds it: native land shows the native faction's colour.
			if _is_land[i] == 1 and _region_ids[i] >= 0:
				colors[i] = colors[i].lerp(_native_color, NATIVE_TINT)
			continue
		var x := i % map_width
		var y := i / map_width
		var on_border := (
			(x > 0 and owners[i - 1] != civ)
			or (x < map_width - 1 and owners[i + 1] != civ)
			or (y > 0 and owners[i - map_width] != civ)
			or (y < map_height - 1 and owners[i + map_width] != civ)
		)
		var civ_color: Color = civ_colors[civ]
		colors[i] = colors[i].lerp(civ_color, BORDER_TINT if on_border else TERRITORY_TINT)
	_commit(colors)


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


## Rivers as ribbons lying on the terrain: each river tile is joined to the next
## river tile downstream or to the water it flows into. Wider rivers get wider ribbons.
func _add_rivers(map: Dictionary, biomes: Array) -> void:
	var water_biomes := {}
	for biome: Dictionary in biomes:
		if biome["water"]:
			water_biomes[int(biome["id"])] = true
	var sizes := {}
	for river: Dictionary in map.get("rivers", []):
		sizes[int(river["y"]) * map_width + int(river["x"])] = float(river["size"])
	if sizes.is_empty():
		return

	var material := StandardMaterial3D.new()
	material.albedo_color = RIVER_COLOR
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var lift := Vector3(0, 0.12, 0)
	for tile: int in sizes:
		var x := tile % map_width
		var y := tile / map_width
		var from: Vector3 = tile_position(x, y) + lift
		for offset: Vector2i in [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1)]:
			var nx := x + offset.x
			var ny := y + offset.y
			if nx < 0 or ny < 0 or nx >= map_width or ny >= map_height:
				continue
			var other := ny * map_width + nx
			var into_water: bool = water_biomes.has(int(map["biomes"][other]))
			# Draw each river-to-river link once; always draw the mouth.
			if not into_water and not (sizes.has(other) and other > tile):
				continue
			var to: Vector3 = tile_position(nx, ny) + lift
			var width: float = 0.1 + 0.07 * float(sizes[tile])
			var side: Vector3 = (to - from).cross(Vector3.UP).normalized() * width
			for corner: Vector3 in [from - side, from + side, to + side, from - side, to + side, to - side]:
				surface.add_vertex(corner)
	var ribbons := MeshInstance3D.new()
	ribbons.mesh = surface.commit()
	ribbons.material_override = material
	ribbons.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(ribbons)


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


func _add_sea() -> void:
	var extent := Vector2(map_width + 400, map_height + 400)

	var surface_material := StandardMaterial3D.new()
	surface_material.albedo_color = Color(0.13, 0.38, 0.66, 0.72)
	surface_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	surface_material.roughness = 0.2
	var surface := MeshInstance3D.new()
	var surface_mesh := PlaneMesh.new()
	surface_mesh.size = extent
	surface_mesh.material = surface_material
	surface.mesh = surface_mesh
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
