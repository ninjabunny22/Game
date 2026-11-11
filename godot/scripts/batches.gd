extends Node3D
## Draws many copies of the same mesh in one batch each.
##
## A finished building never moves, so instead of a node tree per building its parts are
## handed here: every (mesh, material) pair gets one MultiMesh, and a building is just some
## transforms in a few of them. Thousands of buildings then cost a few dozen draw calls.
## Each set of parts is filed under an owner key, by which it is removed again.

var _groups := {}  # "mesh:material" -> {"multimesh": MultiMesh, "items": {owner: [Transform3D]}, "dirty": bool}
var _owners := {}  # owner -> [group keys]


func clear() -> void:
	for child in get_children():
		child.queue_free()
	_groups.clear()
	_owners.clear()


func has(owner: String) -> bool:
	return _owners.has(owner)


## One copy of `mesh` in `material` at `xform`, belonging to `owner`. Call flush() afterwards.
func add(owner: String, mesh: Mesh, material: Material, xform: Transform3D) -> void:
	var key := "%d:%d" % [mesh.get_instance_id(), material.get_instance_id()]
	if not _groups.has(key):
		var multimesh := MultiMesh.new()
		multimesh.transform_format = MultiMesh.TRANSFORM_3D
		multimesh.mesh = mesh
		var instance := MultiMeshInstance3D.new()
		instance.multimesh = multimesh
		instance.material_override = material
		add_child(instance)
		_groups[key] = {"multimesh": multimesh, "items": {}, "dirty": false}
	var group: Dictionary = _groups[key]
	if not group["items"].has(owner):
		group["items"][owner] = []
		if not _owners.has(owner):
			_owners[owner] = []
		_owners[owner].append(key)
	group["items"][owner].append(xform)
	group["dirty"] = true


func remove(owner: String) -> void:
	for key: String in _owners.get(owner, []):
		_groups[key]["items"].erase(owner)
		_groups[key]["dirty"] = true
	_owners.erase(owner)


## Rebuild the batches that changed since the last flush.
func flush() -> void:
	for group: Dictionary in _groups.values():
		if not group["dirty"]:
			continue
		group["dirty"] = false
		var multimesh: MultiMesh = group["multimesh"]
		var count := 0
		for xforms: Array in group["items"].values():
			count += xforms.size()
		multimesh.instance_count = count
		var i := 0
		for xforms: Array in group["items"].values():
			for xform: Transform3D in xforms:
				multimesh.set_instance_transform(i, xform)
				i += 1
