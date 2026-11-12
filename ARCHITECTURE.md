# CivSim architecture

How the implemented code fits together. Rules and numbers live in README.md; this file is
about structure and data flow.

## Three parts

```
 Python simulation (src/civsim)        WebSocket, JSON           Godot viewer (godot/)
 ┌───────────────────────────┐   tick / init / status / error   ┌──────────────────────┐
 │ Simulation.step() per day │ ───────────────────────────────▶ │ sim_client.gd        │
 │ strategist answers        │                                  │ main.gd → terrain,   │
 │ check-ins (utility.py)    │ ◀─────────────────────────────── │ civ_view, unit_view, │
 │ bridge/server.py: clock   │      command (pause, speed,      │ hud, menu, camera    │
 └───────────────────────────┘      new_game, ruler orders)     └──────────────────────┘
```

- **The simulation** knows nothing about time or the network. A driver calls `step()`:
  `bridge/server.py` on a clock (0.25–60 days a second), the headless runner, the survey
  and league tools, or a test.
- **The server** (`bridge/server.py`):
  - steps the sim and answers each check-in on the spot with the chosen brain;
  - broadcasts a full `tick` message every day;
  - applies commands: pause, speed, new game, back to the menu, and ruler orders;
  - in the lobby, plays a game behind the main menu.
- **The protocol** (`bridge/protocol.py`, version 18):
  - `init` once per game: map, regions, mines, definitions;
  - `tick` every day, with no deltas: civs (including each castle's garrison, exact or
    "about"), armies, villagers, relations, deals, rallies, territory, events, and the
    ruler's state.
- **The viewer** draws, and sends commands. It holds no game rules. It loads every model at
  run time from `godot/assets/` (nothing is imported in the editor).

## One simulated day (`Simulation.step`)

1. Apply strategist answers from the last check-ins: stances, strategy and plans.
2. For each living civ, in rotating order:
   - compute modifiers from its buildings, techs and gold mines;
   - apply diplomacy's effects;
   - run the rule-based AI (`civ/ai.py`): research, building, expansion, workers;
   - move villagers and horses;
   - produce, feed, grow, recruit and pay soldiers (`economy/production.py`);
   - advance construction and research.
3. `Diplomacy.update`:
   - sickness, friction and memory;
   - each pair's relation: wars, peace terms, alliances;
   - trade deals;
   - **`Military.update`**: armies, battles, sieges, rallies, hospitals;
   - the natives;
   - standing orders for the economy (soldier targets, march targets).
4. Villages, the ruler's notices, the victory check.
5. Schedule check-ins: every civ, every day (every 10 days on Easy while a human rules).

## Systems and who depends on whom

| Package | Responsibility | Uses |
|---|---|---|
| `map/` | generation (noise, biomes, rivers, lakes, deposits, gold mines), regions, pathfinding | none |
| `economy/` | production, population, buildings and placement (one rule), modifiers, villagers, horses, harbours | map |
| `tech/` | tech tree (`data/techs.json`), research progress | none |
| `civ/` | civ state, personalities, the rule-based AI | economy, tech |
| `military/` | units and tiers, armies, commanders, warfare (march, battle, siege, hold, rally, reinforce, scouting, hospitals) | map, economy, diplomacy |
| `diplomacy/` | relations, war and peace, alliances, tribute, sickness, friction, the natives, region capture | military, economy |
| `strategy/` | the context shown to a strategist (`context.py`), validating replies (`checkin.py`), brains (`utility.py`, `brain.py`) | reads everything; writes only through replies |
| `ruler.py` | a human ruler's orders and proposals; overrides the strategist for that civ | simulation |
| `bridge/` | server and wire format | simulation |
| `config.py`, `maps.py` | game setup, the fixed maps, difficulty | none |
| `survey.py`, `league.py` | measurement tools: full games, strategist comparison | simulation |

Data files in `src/civsim/data/` (buildings, techs, units, personalities, regions) define the
content; code reads it through `economy/buildings.py`, `tech/tree.py` and `military/units.py`.

## How decisions flow

- **Two layers per civ:**
  - The **rule-based AI** (`civ/ai.py`) runs every tick: what to research and build, where to
    expand, how to place workers. It scores options by personality weight times current need.
  - The **strategist** (`strategy/utility.py`, `Params` holds every number) runs at
    check-ins. It sees a context (neighbours, rough or scouted strength, wars, deals,
    forecasts) and replies with a stance toward each civ, a commitment, a long-term
    strategy and a war plan, each with a reason.
- **Turning stances into action:**
  - Diplomacy turns stances into wars, alliances and deals. It sets each civ's soldier
    target and march target, which the economy and the AI then work toward.
  - The military turns war into armies, marches, battles and sieges. A capital falls only
    after being held for 100 days.
- **Economy and military:** the economy recruits and pays soldiers, and `Military._sync`
  keeps the armies' head count equal to it. Battle losses go back into the economy as
  wounded (hospital), dead or escaped (garrison).
- **Research** changes the modifiers, such as troop tier, soldier cost and hospital beds,
  which every system reads.

## Player control

- `ruler.py` holds one ruled civ. Its orders cover:
  - focus, the next research, the next building;
  - stances toward each other civ (or Auto);
  - answers to proposals;
  - rallies, and reinforcing an ally.
- Anything left on Auto is still decided by the civ itself. The other civs are untouched,
  apart from difficulty: on Easy they check in less often.
- **Hidden information is enforced in `protocol.py`:**
  - another civ's garrison is sent only as an estimate (`Military.garrison_guess`) unless it
    is known (`garrison_known`);
  - other civs' garrison armies are left out;
  - field armies carry a `scouted` flag.

## Viewer structure (`godot/scripts`)

- `main.gd`: connects, builds the scene on `init`, hands each `tick` to the parts, picks a
  castle under a click, and the zoom level (3 levels). It also reads the scripted-run env
  vars.
- `terrain.gd`:
  - the heightmap mesh, levelled under capitals;
  - still water, rivers and territory tint;
  - trees, peaks and rocks, scattered with MultiMesh.
- `civ_view.gd`:
  - buildings (batched in `batches.gd`), sites, props, villages;
  - castles assembled from Hexagon pieces by era, with hospital tents;
  - gold mines, siege rubble, labels, links.
- `unit_view.gd`:
  - armies: a general in front, ranks behind;
  - ships at sea, siege engines, generals in reserve, villagers.
  - Garrisons are not drawn.
- `hud.gd`, `menu.gd`: panels, civ cards, ruler controls, the castle panel, pop-ups, the menu.
- **Model loaders:**
  - `models.gd`: Hexagon and Blender-made glTF, recoloured by repainting the texture's
    faction rectangle;
  - `adventurers.gd`: rigged characters, the shared and our own animations, weapons, the
    horse;
  - `characters.gd`: the older custom models.

## Constraints

- **Full state every tick:** this is the main cost at high speed.
- **Determinism:** a run is deterministic for a seed only with `--brain rules`.
- **The protocol version must match** on both sides (`PROTOCOL_VERSION` in Python and
  GDScript).
- **Fixed maps:** changing map generation or its random calls changes them. Gold mines were
  added without consuming any random numbers.
- **Art:** pack textures are the only materials. A new model must be painted from a pack
  texture's cells to recolour per civ. The Blender sources are scripts in `tools/blender/`;
  the raw packs live in `art/` (ignored by git).
