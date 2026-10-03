# CivSim

Four civilizations compete on a procedurally generated map. A Python simulation
core runs the world; a Godot 4 project renders it in 3D over a local WebSocket.

Built so far: **phase 1** (map, civs, economy, rule-based AI, viewer),
**phase 2** (base tech tree) and **phase 3** (upkeep, trade, alliances, war, an
LLM strategic layer and LLM-invented techs).

## Run it

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python -m civsim                 # random seed, ws://127.0.0.1:8765, 2 ticks/s
.venv/bin/python -m civsim --seed 42 --tick-rate 10
.venv/bin/python -m civsim --llm rules     # no language model: built-in deterministic strategy
.venv/bin/python -m civsim --headless --seed 42 --ticks 1500 --llm rules   # no server, prints a summary
.venv/bin/python -m pytest
```

By default the strategic layer talks to a local [Ollama](https://ollama.com)
server at `http://localhost:11434` using `llama3.1:8b` (`ollama pull llama3.1:8b`).
`--model` and `--llm-url` change that. If Ollama is not running the sim still
runs; civs simply keep their previous stances. The tests never need a model.

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
  tech/        tech tree loading/validation, research progress, invented techs (invention.py)
  diplomacy/   stances, trade deals, alliances, war and combat (diplomacy.py), constants (rules.py)
  strategy/    check-ins: context shown to a strategist, prompts, reply validation, brains
  llm/         the Ollama client (ollama.py) and the small interface the strategy layer codes against
  bridge/      WebSocket server and tick clock (server.py), wire format (protocol.py)
  simulation.py  owns the world and civs; step() advances one tick
  data/        buildings.json, techs.json, personalities.json, invention.json
godot/         viewer: scripts/main.gd wires sim_client, terrain, civ_view, hud, camera_rig
tests/
```

The simulation knows nothing about time, the network or language models. A
driver (`bridge/server.py`, the headless runner, a test) decides when to call
`step()` and answers the strategic check-ins the sim raises. With `--llm rules`
a run is fully deterministic for a given seed.

## How the pieces work

**Map.** 96x96 square grid. Simplex-noise elevation (pulled down at the edges so
land forms continents), moisture and a north-south temperature gradient pick one
of eight biomes. Deposits (fertile soil, fish, game, stone, iron, gold) are
seeded on suitable biomes and grown into contiguous clusters. Each tile offers
work slots per resource from its biome plus any deposit.

**Economy.** Each person is a worker. A worker in a slot produces 0.2 of that
resource per tick; a civ can only employ as many workers on a resource as its
territory has slots. People eat, populations grow toward the housing cap, and
each resource has a hard storage cap: a base of 250 plus 300 for every storage
building for that resource (Granary, Lumber Yard, Stone Yard, Ore Depot,
Treasury), each of which takes a tile and has upkeep. No workers are put on a
resource that is at its cap; they move to other resources or stand idle, and a
filling store pushes the civ to build more room for it. Buildings and techs
share one effects vocabulary (`yield_mult`, `housing`, `store`, `science`, ...
see `economy/modifiers.py`).

**AI.** Utility scoring: `score = personality weight x current need`, with
diminishing returns per copy. Each tick a civ picks a research target, picks a
project (a building or a territory expansion) and either starts it or saves for
it, then splits workers by what it is saving for. Each civ gets one archetype
from `personalities.json` plus seeded jitter. Tuning knobs are the constants at
the top of `civ/ai.py` and the JSON data files.

**Upkeep.** Buildings cost resources every tick (`upkeep` in `buildings.json`)
and stop working while unpaid. People burn wood as fuel, and food and fuel use
per head rise with every tech known. Soldiers cost gold, ore and extra food.

**Demolition.** A civ tears down its own buildings in two cases: one whose
upkeep has gone unpaid for 60 ticks, and, when it has no free tile left, its
least useful building if the one it wants scores at least twice as high.
Demolition frees the tile and refunds 10% of the base cost; at most one every
25 ticks. Four of the construction techs, one per era, raise the refund as one
of their effects: Mining (13%), Masonry (17%), Engineering (21%), Guilds (25%).

**Tech.** 15 techs over 4 eras in `techs.json`. A tech needs its prerequisites,
a material cost paid up front, then science, which is spent as it is produced.
A civ with nothing to research banks at most 500 science. A civ's era is the
highest era among its known techs.

**Strategic layer.** Every 50 ticks (staggered between civs) the sim raises a
check-in for each civ: its own state, each neighbour's visible state and recent
dealings between them. A *brain* answers with one stance per neighbour -
`trade`, `ally`, `ignore` or `aggression` - plus terms (a resource to give and
one to want, or a troop commitment) and a short reason. `LLMBrain` asks a
language model for JSON matching a schema; `RuleBrain` is a deterministic
stand-in. Replies are validated and clamped (`strategy/checkin.py`); a missing
or unusable reply leaves the previous stances in place. With the server, calls
run in the background and the sim keeps ticking; an answer is applied on the
tick after it arrives. Headless runs wait for each answer.

The brain only sets intent. `diplomacy/diplomacy.py` executes it every tick:

- **Trade.** When two civs both hold `trade` or `ally` toward each other and
  offer different resources, a deal opens: each sends its resource every tick
  for 100 ticks. Each side pays 15 gold to open it (free between allies). A
  rate is capped by what the giver can sustain, and a side that cannot deliver
  for 10 ticks cancels the deal. Gold can be traded like any resource.
- **Alliance.** Mutual `ally` forms one for 40 gold each plus 0.1 gold per
  tick: +15% defence and +10% science per ally. It lapses when either side
  turns away.
- **War.** `aggression` declares war (50 gold) once the two territories are
  within 4 tiles; until then the aggressor's border expands toward the target.
  There are no units on the map. Troop commitment mobilises up to 35% of the
  population as soldiers. Each tick a side's attack (soldiers x quality) is
  compared with the other's defence (soldiers plus militia, with home, walls
  and ally bonuses); the stronger side accumulates progress and captures the
  cheapest enemy tile in reach. Any building on a captured tile, of any type,
  finished or not, becomes the captor's: it pays the upkeep and gets the
  effects for as long as it holds the tile, and loses it the same way if the
  tile is retaken. A storage building brings its share of the stored resource
  with it, kept even above the captor's cap. Both sides take
  casualties, the weaker more. A civ surrenders when a tile next to its capital
  falls: it pays half its stock as tribute and gets a 300-tick truce. Wars also
  end when neither side is aggressive (after 50 ticks) or after 400 ticks.

**Invented techs.** Once a civ has the whole base tree, its brain is asked to
propose a new tech: a name, up to two effects from the shared effects
vocabulary and up to two materials. `tech/invention.py` clamps each effect to
the caps in `invention.json` and sets the science and material cost itself from
the effect size and how many techs the civ has already invented (each 35%
dearer). Invented techs are private to their inventor.

## Protocol

JSON text frames, each an envelope `{"type", "version", "tick", "data"}`.

| Direction | Type | Content |
|---|---|---|
| sim -> viewer | `init` | Once on connect: map (heights, biomes, deposits), biome/building/tech definitions, civ names and colours |
| sim -> viewer | `tick` | After every tick: full state of every civ (including army, stances and the strategist's reason), the territory grid (base64, one byte per tile: owner id, 255 = unowned), relations, deals, invented techs, pause/speed status, events of that tick. No deltas |
| sim -> viewer | `status` | When pause or speed changes |
| sim -> viewer | `error` | Reply to a bad command |
| viewer -> sim | `command` | `data.action`: `pause`, `resume`, `toggle_pause`, `step`, `set_speed` (with `data.value` in ticks/s, clamped to 0.25-60) |

Field-level detail is in `bridge/protocol.py`.
