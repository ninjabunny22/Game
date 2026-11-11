#!/bin/bash
# Starts everything CivSim needs, in order, and opens the viewer:
#   1. the Python simulation
#   2. the Godot viewer, once the simulation is accepting connections
# Closing the Godot window stops the simulation.
#
# Double-click this file in Finder, or run it from a terminal:
#   ./CivSim.command                  (extra arguments go to the sim, e.g. --seed 42 --tick-rate 4)
#
# If Godot is somewhere unusual, point to it:  GODOT=/path/to/Godot.app ./CivSim.command

set -u
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
LOGS="$ROOT/logs"
SIM_PORT=8765
PYTHON="$ROOT/.venv/bin/python"

SIM_PID=""

cleanup() {
    trap - EXIT INT TERM HUP
    if [ -n "$SIM_PID" ] && kill -0 "$SIM_PID" 2>/dev/null; then
        echo "Stopping the simulation..."
        kill "$SIM_PID" 2>/dev/null
        wait "$SIM_PID" 2>/dev/null
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

fail() {
    echo
    echo "ERROR: $1"
    # Keep the window open when launched by double-click, so the message can be read.
    if [ -t 0 ]; then
        read -n 1 -s -r -p "Press any key to close."
        echo
    fi
    exit 1
}

sim_listening() { nc -z 127.0.0.1 "$SIM_PORT" 2>/dev/null; }

find_godot() {
    local app
    for app in "${GODOT:-}" "$ROOT/Godot.app" "/Applications/Godot.app" "$HOME/Applications/Godot.app" "$HOME/Downloads/Godot.app" \
               "$(mdfind "kMDItemCFBundleIdentifier == 'org.godotengine.godot'" 2>/dev/null | head -1)"; do
        [ -z "$app" ] && continue
        if [ -x "$app/Contents/MacOS/Godot" ]; then
            echo "$app/Contents/MacOS/Godot"
            return
        elif [ -f "$app" ] && [ -x "$app" ]; then
            echo "$app"  # GODOT pointed straight at an executable
            return
        fi
    done
}

mkdir -p "$LOGS"
echo "CivSim launcher"
echo "Logs: $LOGS"
echo

# -- checks before starting anything ------------------------------------------

GODOT_BIN="$(find_godot)"
[ -n "$GODOT_BIN" ] || fail "Godot not found. Put Godot.app in /Applications, or set GODOT=/path/to/Godot.app."
sim_listening && fail "Something is already listening on port $SIM_PORT. Is another copy of the sim running?"

if [ ! -x "$PYTHON" ]; then
    echo "First run: setting up the Python environment..."
    python3 -m venv "$ROOT/.venv" || fail "Could not create the Python environment."
    "$PYTHON" -m pip install -q -e "$ROOT" || fail "Could not install the simulation's dependencies."
fi

# -- 1. Simulation ---------------------------------------------------------------

echo "[1/2] Starting the simulation..."
"$PYTHON" -m civsim --port "$SIM_PORT" "$@" >"$LOGS/sim.log" 2>&1 &
SIM_PID=$!
for _ in $(seq 1 60); do
    sim_listening && break
    if ! kill -0 "$SIM_PID" 2>/dev/null; then
        tail -n 15 "$LOGS/sim.log"
        fail "The simulation exited while starting. Full log: $LOGS/sim.log"
    fi
    sleep 0.5
done
sim_listening || fail "The simulation did not start listening within 30 seconds. See $LOGS/sim.log"

# -- 2. Viewer -------------------------------------------------------------------

echo "[2/2] Opening the viewer. Close the Godot window to stop everything."
"$GODOT_BIN" --path "$ROOT/godot" >"$LOGS/godot.log" 2>&1

echo
echo "Viewer closed."
