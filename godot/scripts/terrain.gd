extends Node3D
## Terrain mesh built from the sim's heightmap: one vertex per tile, coloured by
## biome and tinted with the owning civ's colour. Tile (x, y) sits at world (x, h, y).

const HEIGHT_SCALE := 9.0
const TERRITORY_TINT := 0.3
const BORDER_TINT := 0.8
const UNOWNED := 46  # '.' in the territory string

var map_width := 0
var map_height := 0

var _heights := PackedFloat32Array()
var _base_colors := PackedColorArray()
var _vertices := PackedVector3Array()
var _normals := PackedVector3Array()
var _indices := PackedInt32Array()
var _land: MeshInstance3D
var _material: StandardMaterial3D


func build(map: Dictionary, biomes: Array) -> void:
	for child in get_children():
		child.queue_free()
	map_width = int(map["width"])
	map_height = int(map["height"])

	var palette := {}
	for biome: Dictionary in biomes:
		palette[int(biome["id"])] = Color.html(biome["color"])

	var size := map_width * map_height
	var heights: Array = map["heights"]
	var biome_ids: Array = map["biomes"]
	_heights.resize(size)
	_base_colors.resize(size)
	_vertices.resize(size)
	_normals.resize(size)
	for i in size:
		var h := float(heights[i])
		_heights[i] = h
		# Shade by altitude so relief reads even where the biome is uniform.
		var color: Color = palette[int(biome_ids[i])]
		_base_colors[i] = color.darkened(0.25).lerp(color.lightened(0.15), clampf(h, 0.0, 1.0))
		_vertices[i] = Vector3(i % map_width, h * HEIGHT_SCALE, i / map_width)

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


func center() -> Vector3:
	return Vector3((map_width - 1) / 2.0, 0.0, (map_height - 1) / 2.0)


## World position of a tile's surface; water tiles report the sea surface.
func tile_position(x: int, y: int) -> Vector3:
	return Vector3(x, maxf(_heights[y * map_width + x], 0.0) * HEIGHT_SCALE, y)


## `territory` has one char per tile: '.' for unowned, else the civ id digit.
func apply_territory(territory: String, civ_colors: Array) -> void:
	var owners := territory.to_ascii_buffer()
	if owners.size() != _base_colors.size():
		return
	var colors := _base_colors.duplicate()
	for i in owners.size():
		var civ := owners[i]
		if civ == UNOWNED:
			continue
		var x := i % map_width
		var y := i / map_width
		var on_border := (
			(x > 0 and owners[i - 1] != civ)
			or (x < map_width - 1 and owners[i + 1] != civ)
			or (y > 0 and owners[i - map_width] != civ)
			or (y < map_height - 1 and owners[i + map_width] != civ)
		)
		var civ_color: Color = civ_colors[civ - 48]
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
