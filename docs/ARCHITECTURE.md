# CivSim architecture

How the implemented code fits together. Rules and numbers live in the README (project root); this file is
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
- **The protocol** (`bridge/protocol.py`, version 19):
  - `init` once per game: map (with old bridges), regions (with points and strongholds),
    mines, definitions; in the lobby, every map with its size, civ range and premise;
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
   - run the rule-based AI (`civ/ai.py`): research, building, workers;
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
| `map/` | drawn maps: shapes, blueprints and their builder and checker (`blueprint.py`), the nine designs (`designs/`), saved maps (`saved.py`, files in `data/maps`), PNG previews; generated maps for tests (noise, biomes, rivers, lakes, deposits); regions; pathfinding | none |
| `economy/` | production, population, buildings and placement (one rule; `town_plots` gives the fixed plots, `PLOTS` for town buildings and `VILLAGE_PLOTS` for villages; caps per region and levels from `buildings.json`, effects counted once per level), modifiers, villagers, horses, harbours | map |
| `tech/` | tech tree (`data/techs.json`), research progress | none |
| `civ/` | civ state, personalities, the rule-based AI | economy, tech |
| `military/` | units and tiers, armies, commanders, warfare (march, battle, siege, capital hold, rally, reinforcing allies, holding own castles, scouting, hospitals) | map, economy, diplomacy, strategy.geography |
| `diplomacy/` | relations, war and peace, alliances, tribute, sickness, friction, the natives, region capture | military, economy |
| `strategy/` | what each region is worth to each civ (`geography.py`), the context shown to a strategist (`context.py`), validating replies (`checkin.py`), brains (`utility.py`, `brain.py`) | reads everything; writes only through replies |
| `ruler.py` | a human ruler's orders and proposals; overrides the strategist for that civ | simulation |
| `bridge/` | server and wire format | simulation |
| `config.py` | game setup, the list of maps and the civ counts each takes (`civ_counts`), difficulty | none |
| `survey.py`, `league.py` | measurement tools: full games, strategist comparison | simulation |
| `mapmaker.py`, `fairness.py` | build, check, save and draw the drawn maps; compare their start slots by geography | map, strategy.geography |

Data files in `src/civsim/data/` (buildings, techs, units, personalities, regions) define the
content; code reads it through `economy/buildings.py`, `tech/tree.py` and `military/units.py`.

## How decisions flow

- **Two layers per civ:**
  - The **rule-based AI** (`civ/ai.py`) runs every tick: what to research and build and
    how to place workers. It scores options by personality weight times current need.
  - The **strategist** (`strategy/utility.py`, `Params` holds every number) runs at
    check-ins. It sees a context (neighbours, rough or scouted strength, wars, deals,
    forecasts) and replies with a stance toward each civ, a commitment, a long-term
    strategy and a war plan, each with a reason.
- **Turning stances into action:**
  - Diplomacy turns stances into wars, alliances and deals. It sets each civ's soldier
    target and march target, which the economy and the AI then work toward.
  - The military turns war into armies, marches, battles and sieges. A capital falls only
    after being held for 100 days.
  - Army duties (`Army.duty`): `attack` (makes for the enemy's capitals), `defend` (a home
    force), `reinforce` (stands in an ally's threatened capital), `hold` (a force a general
    left in one of his own threatened castles). These are decided by rules in `warfare.py`,
    not by the strategist.
- **Economy and military:** the economy recruits and pays soldiers, and `Military._sync`
  keeps the armies' head count equal to it. Battle losses go back into the economy as
  wounded (hospital), dead or escaped (garrison).
- **One valuation of land:** `strategy/geography.Geography` (made by the simulation) prices
  each region for each civ, refreshed every 25 days. It is read by campaigns against the
  natives (`_campaign_target`, nearest regions first), war targets (`_plan`), harbour sites
  (`civ.harbour_goal` → `find_site`) and the strategist's context (`prize`, `prizes`), so all
  of them want the same places for the same reasons.
- **Movement, one rule:** `WorldMap.walkable` says where feet can go (not peaks, not
  mountain outside a pass, not water unless a bridge spans it); `crossing_cost` prices a step
  and `pathfinding.move_cost` adds diagonals (√2, no cutting corners). Armies, villagers and
  route searches all go through them. Passes are carved when a map is built
  (`map/passes.carve_passes`); bridges come from a design's `causeways`.
- **Fights for spectators:** `military/engagements.py` keeps one record per battle, siege and
  assault on a native capital, filled in by `warfare.py` where the fighting happens
  (`_battle_tick`, `_besiege`, `_storm`, `_rout`), and sent as `engagements` only while nobody
  rules a civ. The viewer's `battle_view.gd` draws them; it decides nothing.
- **Royal houses:** `civ/family.py` (`Families`, built by the simulation after diplomacy and
  military, updated daily after diplomacy) holds every house from `data/houses.json`, one
  drawn per civ, with its members, ages (from `birth_day`), marriages, births, deaths and
  succession. It rolls its own seeded dice. A succession replaces `civ.born`
  (and so the strategist's weights) and sets a 60-day `unrest` that `strategy/context.py`
  passes to the strategist. Princes can command armies (`Commander.person`; `warfare.py`
  reports their deaths and wounds back). Its events have kind `family`; the viewer gets
  `families` on init, on a day a family changes and every 30 days. Portraits are cut from the
  boards in `art/portraits_royalty/` by `tools/cut_portraits.py` into `godot/assets/portraits`.
- **Civs born mid-game:** a rebellion (`Families._rebel`) calls `Simulation._spawn_rebel`, which
  appends a civ (id = its index; eight at most, one per name and colour), registers it with
  every keeper of a `civs` table (diplomacy via `add_civ`, natives, families, villages,
  military, geography), hands it a region (`Diplomacy.secede`) and soldiers
  (`Military.rebel_forces`) and starts its war (`Diplomacy.rebellion_war`). Every tick sends
  a `roster` of all civs; the viewer adds any it has not seen (`main.gd`, `hud.add_civ`), and
  every view looks colours up in one shared array, so they all pick it up.
- **Land in whole regions:** a civ's `territory` is always every tile of the regions it holds.
  Tiles change hands only through `Diplomacy.capture_region` (a native capital stormed, an
  enemy castle held for 60 days, a treaty) and `_eliminate`; there is no tile-by-tile
  settling, defection or capture.
- **Victory by points:** `Simulation.points_held` and `domination_target` (80% of the map's
  region points and half its regions); `score()` counts the same points.
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
  - still water, rivers, old bridges and territory tint;
  - trees, peaks (a solid wall of them on high peaks) and rocks, scattered with MultiMesh.
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
  - `adventurers.gd`: rigged characters, the KayKit animation sets (a library per kind, by
    weapon), weapons, and the rigged horse with its rider on the saddle bone;
  - `characters.gd`: the older custom villager and rider.

## Constraints

- **Full state every tick:** this is the main cost at high speed.
- **Determinism:** a run is deterministic for a seed only with `--brain rules`.
- **The protocol version must match** on both sides (`PROTOCOL_VERSION` in Python and
  GDScript).
- **Saved maps:** games load the nine maps from `data/maps`; changing a design or the
  builder changes nothing until the map is baked again (`civsim.mapmaker bake`), and the
  tests fail while a saved map is out of date with its design. A drawn map's start slots are
  fixed; a game's seed only assigns civs to them.
- **Art:** pack textures are the only materials. A new model must be painted from a pack
  texture's cells to recolour per civ. The Blender sources are scripts in `tools/blender/`;
  the raw packs live in `art/` (ignored by git).
