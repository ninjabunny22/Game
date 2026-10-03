# CivSim

Four civilizations compete on a procedurally generated map. A Python simulation
core runs the world; a Godot 4 project renders it in 3D over a local WebSocket.

Built so far: **phase 1** (map, civs, economy, rule-based AI, viewer) and
**phase 2** (base tech tree). Trade, war, diplomacy and the LLM strategy layer
are not built yet.

## Run it

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python -m civsim                 # random seed, ws://127.0.0.1:8765, 2 ticks/s
.venv/bin/python -m civsim --seed 42 --tick-rate 10
.venv/bin/python -m civsim --headless --seed 42 --ticks 1500   # no server, prints a summary
.venv/bin/python -m pytest
```

Then open `godot/` in Godot 4.3 or newer and press Play (or
`godot --path godot`). The viewer and the sim can start in either order; the
viewer reconnects on its own.

Viewer controls: drag to pan, right-drag to orbit, wheel to zoom, `Space` to
pause, `.` to step one tick, `-` / `=` to change speed.

## Layout

```
src/civsim/
  map/         terrain noise, biomes, clustered resource deposits, start positions
  civ/         civilization state, personalities, the rule-based AI (ai.py)
  economy/     production, population, buildings, effect modifiers, constants (rules.py)
  tech/        tech tree loading/validation, research progress
  bridge/      WebSocket server and tick clock (server.py), wire format (protocol.py)
  simulation.py  owns the world and civs; step() advances one tick
  data/        buildings.json, techs.json, personalities.json
godot/         viewer: scripts/main.gd wires sim_client, terrain, civ_view, hud, camera_rig
tests/
```

The simulation is deterministic for a given seed and knows nothing about time
or the network; `bridge/server.py` decides when to call `step()`.

## How the pieces work

**Map.** 96x96 square grid. Simplex-noise elevation (pulled down at the edges so
land forms continents), moisture and a north-south temperature gradient pick one
of eight biomes. Deposits (fertile soil, fish, game, stone, iron, gold) are
seeded on suitable biomes and grown into contiguous clusters. Each tile offers
work slots per resource from its biome plus any deposit.

**Economy.** Each person is a worker. A worker in a slot produces 0.2 of that
resource per tick; a civ can only employ as many workers on a resource as its
territory has slots. People eat, populations grow toward the housing cap, and
stock is capped by storage. Buildings and techs share one effects vocabulary
(`yield_mult`, `housing`, `storage`, `science`, ... see `economy/modifiers.py`).

**AI.** Utility scoring: `score = personality weight x current need`, with
diminishing returns per copy. Each tick a civ picks a research target, picks a
project (a building or a territory expansion) and either starts it or saves for
it, then splits workers by what it is saving for. Each civ gets one archetype
from `personalities.json` plus seeded jitter. Tuning knobs are the constants at
the top of `civ/ai.py` and the JSON data files.

**Tech.** 15 techs over 4 eras in `techs.json`. A tech needs its prerequisites,
a material cost paid up front, then enough accumulated science. A civ's era is
the highest era among its known techs.

## Protocol

JSON text frames, each an envelope `{"type", "version", "tick", "data"}`.

| Direction | Type | Content |
|---|---|---|
| sim -> viewer | `init` | Once on connect: map (heights, biomes, deposits), biome/building/tech definitions, civ names and colours |
| sim -> viewer | `tick` | After every tick: full state of every civ, the territory grid, pause/speed status, events of that tick. No deltas |
| sim -> viewer | `status` | When pause or speed changes |
| sim -> viewer | `error` | Reply to a bad command |
| viewer -> sim | `command` | `data.action`: `pause`, `resume`, `toggle_pause`, `step`, `set_speed` (with `data.value` in ticks/s, clamped to 0.25-60) |

Field-level detail is in `bridge/protocol.py`.
