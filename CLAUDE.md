# CivSim: project guide

Stable facts and rules. For where things stand now, read **CIVSIM_STATUS.md** first; for
plans, **ROADMAP.md**; for how the code fits together, **ARCHITECTURE.md**; for player-facing
rules and every number, **README.md**.

## What CivSim is

A civilisation simulation on a generated map, with two ways to use it:
- **Watch:** 2–5 civilisations expand, build, research, trade, ally, betray and go to war,
  each run by a built-in strategist that explains its decisions.
- **Rule:** the player takes one civ (focus, research, building, stance toward each other
  civ, rallies, reinforcing allies) while the others carry on by themselves.

## Stack

- **Simulation:** Python 3.11+ in `src/civsim` (dependencies: `opensimplex`, `websockets`).
  It holds all game state and every rule.
- **Viewer:** Godot 4.7 project in `godot/` (GDScript). It only draws and sends commands.
- **Link:** JSON over a local WebSocket (`ws://127.0.0.1:8765`), full state every tick, with a
  protocol version shared by both ends (`bridge/protocol.py`, `godot/scripts/sim_client.gd`).
- **Art:** KayKit Medieval Hexagon and Adventurers packs (CC0), our own models made by
  Blender scripts in `tools/blender/`, and two older custom models (villager, rider).
- **Launcher:** `CivSim.command` starts the sim, then the viewer.

## Principles (do not reverse casually)

- **The simulation is the single source of truth.** The viewer never decides anything; it
  draws what it is sent and sends commands back. Hidden information (garrison estimates,
  unscouted armies) is rounded or left out by the simulation, never by the viewer.
- **No language model plays.** Ollama and the LLM brain were removed on purpose. Civs are
  played by `strategy/utility.py` (`--brain rules` is the simple policy the tests use).
- **Civs decide every day**, under commitment rules (minimum war length, strategy and plan
  lengths) so they do not flip-flop.
- **Fixed maps:** three chosen seeds per size (`config.MAPS`); civs spawn at random places on
  them. Changing map generation changes these maps.
- **Square tile grid.** The hex tiles of the Hexagon pack are not used and must not be forced
  on the map.
- **One rule per thing:** building placement goes through `placement_problem`/`place`;
  every strategist number lives in `Params`.
- **Shown head counts are four to the unit** (`HEADCOUNT`); the economy is unscaled.
- **Art in the packs' style:** low-poly, flat colour cells; parts painted from a pack
  texture's faction cell take each civ's colour. New models are made by script, not by hand.
- **Water is still** (no swell or scrolling); castles stand on levelled ground.

## How to work on it

- **Plan first when asked to plan or discuss**: no code until the user approves. Keep
  answers short when asked to.
- **Tests:** `.venv/bin/python -m pytest` (about 9 minutes, all must pass before a commit).
  Viewer: `Godot --headless --path godot --script res://tests/check_assets.gd` (must print
  `assets ok`). Picture scenes in `godot/tests/` (gallery, castle, models, units views).
- **Measuring balance:** at most **3 simulated games** per measurement, one per map size,
  with short output (`scratch` scripts or `civsim.survey --size`).
- **Look before claiming:** check viewer changes with screenshots (scripted runs:
  `CIVSIM_VIEW`, `CIVSIM_FOLLOW`, `CIVSIM_QUIT_AT`, `CIVSIM_CASTLE` env vars in `main.gd`).
- **Commits:** one per finished step, on the working branch, after tests pass. Messages say
  what changed for the game; end with the co-author line the session asks for. Push only
  when asked.
- **Never put personal details** (names, emails) into files, commits or requests to outside
  services.

## Keeping the documentation current

After every substantial task:
- update **CIVSIM_STATUS.md** (always);
- update **ROADMAP.md** when priorities or plans change;
- update **ARCHITECTURE.md** when the structure changes;
- update **README.md** when rules or numbers the player sees change;
- update this file only when permanent principles change.

Say a thing once, in the file it belongs to.
