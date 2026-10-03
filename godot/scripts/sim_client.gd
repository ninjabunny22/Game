extends Node
## WebSocket client for the Python sim. Parses the JSON envelopes
## ({type, version, tick, data}) and re-emits them as signals.
## Reconnects automatically, so the viewer and the sim can start in either order.

signal connection_changed(connected: bool)
signal init_received(data: Dictionary)
signal tick_received(tick: int, data: Dictionary)
signal status_received(data: Dictionary)

const PROTOCOL_VERSION := 5
const RETRY_SECONDS := 1.5

@export var url := "ws://127.0.0.1:8765"

var _socket := WebSocketPeer.new()
var _connected := false
var _retry_in := 0.0


func _process(delta: float) -> void:
	_socket.poll()
	match _socket.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if not _connected:
				_connected = true
				connection_changed.emit(true)
			while _socket.get_available_packet_count() > 0:
				_handle(_socket.get_packet().get_string_from_utf8())
		WebSocketPeer.STATE_CLOSED:
			if _connected:
				_connected = false
				connection_changed.emit(false)
			_retry_in -= delta
			if _retry_in <= 0.0:
				_retry_in = RETRY_SECONDS
				_open()


func send_command(action: String, value: Variant = null) -> void:
	if not _connected:
		return
	var message := {"type": "command", "version": PROTOCOL_VERSION, "data": {"action": action, "value": value}}
	_socket.send_text(JSON.stringify(message))


func _open() -> void:
	_socket = WebSocketPeer.new()
	# The init message carries the whole map; the default 64 KiB buffer is too small.
	_socket.inbound_buffer_size = 4 * 1024 * 1024
	_socket.max_queued_packets = 4096
	_socket.connect_to_url(url)


func _handle(text: String) -> void:
	var message: Variant = JSON.parse_string(text)
	if typeof(message) != TYPE_DICTIONARY or typeof(message.get("data")) != TYPE_DICTIONARY:
		push_warning("Ignoring malformed message from sim")
		return
	if int(message.get("version", 0)) != PROTOCOL_VERSION:
		push_warning("Sim speaks protocol version %s, viewer expects %d" % [message.get("version"), PROTOCOL_VERSION])
		return
	var data: Dictionary = message["data"]
	match message.get("type"):
		"init":
			init_received.emit(data)
		"tick":
			tick_received.emit(int(message.get("tick", 0)), data)
		"status":
			status_received.emit(data)
		"error":
			push_warning("Sim rejected a command: %s" % data.get("message", ""))
