extends Node3D
## Orbit camera. The rig sits on the point being looked at.
##   left-drag / WASD / arrows / two-finger scroll: pan
##   right- or middle-drag, Q / E: orbit
##   wheel / pinch: zoom

const MIN_DISTANCE := 8.0
const MAX_DISTANCE := 260.0
const MIN_PITCH := deg_to_rad(15.0)
const MAX_PITCH := deg_to_rad(88.0)

var _camera := Camera3D.new()
var _yaw := 0.0
var _pitch := deg_to_rad(55.0)
var _distance := 110.0


func _ready() -> void:
	_camera.far = 1200.0
	_camera.fov = 50.0
	add_child(_camera)
	_camera.make_current()
	_apply()


func focus(target: Vector3, distance: float) -> void:
	position = target
	_distance = clampf(distance, MIN_DISTANCE, MAX_DISTANCE)
	_apply()


func _process(delta: float) -> void:
	var move := Vector3.ZERO
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		move.z -= 1.0
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		move.z += 1.0
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		move.x -= 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		move.x += 1.0
	var turn := 0.0
	if Input.is_key_pressed(KEY_Q):
		turn -= 1.0
	if Input.is_key_pressed(KEY_E):
		turn += 1.0
	if move != Vector3.ZERO or turn != 0.0:
		_pan(move * _distance * 0.8 * delta)
		_yaw += turn * 1.5 * delta
		_apply()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_zoom(0.9)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_zoom(1.1)
	elif event is InputEventMouseMotion:
		if event.button_mask & (MOUSE_BUTTON_MASK_RIGHT | MOUSE_BUTTON_MASK_MIDDLE):
			_yaw -= event.relative.x * 0.006
			_pitch = clampf(_pitch + event.relative.y * 0.006, MIN_PITCH, MAX_PITCH)
			_apply()
		elif event.button_mask & MOUSE_BUTTON_MASK_LEFT:
			var scale_factor := _distance * 0.0016
			_pan(Vector3(-event.relative.x, 0.0, -event.relative.y) * scale_factor)
			_apply()
	elif event is InputEventMagnifyGesture:
		_zoom(1.0 / event.factor)
	elif event is InputEventPanGesture:
		_pan(Vector3(event.delta.x, 0.0, event.delta.y) * _distance * 0.02)
		_apply()


func _zoom(factor: float) -> void:
	_distance = clampf(_distance * factor, MIN_DISTANCE, MAX_DISTANCE)
	_apply()


func _pan(offset: Vector3) -> void:
	position += Basis(Vector3.UP, _yaw) * offset


func _apply() -> void:
	rotation = Vector3(0.0, _yaw, 0.0)
	_camera.position = Vector3(0.0, sin(_pitch), cos(_pitch)) * _distance
	_camera.rotation = Vector3(-_pitch, 0.0, 0.0)
	# Shift the view left so the focus point isn't hidden behind the HUD's side panel.
	_camera.h_offset = _distance * 0.13
