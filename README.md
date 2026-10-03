# CivSim

Four civilizations compete on a procedurally generated map. A Python simulation
core runs the world; a Godot 4 project renders it in 3D over a local WebSocket.

Built so far: **phase 1** (map, civs, economy, rule-based AI, viewer),
**phase 2** (base tech tree), **phase 3** (upkeep, trade, alliances, war, an
LLM strategic layer), water (rivers, lakes, bridges,
boats) and the first piece of **phase 4** (armies, unit types, commanders and
villagers on the map).

## Run it

Double-click `CivSim.command` in Finder (or run `./CivSim.command`). It starts
Ollama if it is not already running, starts the simulation, and opens the Godot
viewer once the simulation is ready. Closing the Godot window stops the
simulation, and Ollama too if the launcher started it. Arguments are passed to
the sim, for example `./CivSim.command --seed 42`. Logs go to `logs/`.

To run the pieces by hand:

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

The overlay is built for watching:

- **Date.** The top left shows the day (one tick is one day) and the pace in
  days per minute. A banner appears while the sim is paused.
- **Text size.** The whole overlay is drawn 35% larger than Godot's default;
  `[` and `]` make it smaller or larger while watching.
- **Headline log.** Only wars, peace, regions and capitals changing hands,
  alliances, betrayals, routs and new eras get a line. Routine events
  (buildings captured, discoveries, trade changes) are counted in one summary
  line for the last 100 days.
- **Civ cards.** Each civ has a three-line card: name, era, regions,
  population, army, and what matters most about it now (at war, out of water,
  distrusted, allied). Click a card, or press `1`-`4`, to open its full detail;
  one is open at a time.
- **Diplomacy panel.** `Tab` or the Diplomacy button: every war with its name,
  sides, duration, land taken and losses; every alliance with its name and
  when it formed; every trade deal with its terms.
- **Arcs** between capitals are colour-coded: red for war, blue for alliance,
  green for a trade deal, thin grey for neither.
- **Zoom-aware map.** From afar only each civ's own capital is named, field
  armies are a coloured marker with their size, and garrisons and villagers
  are left out. Closer in, every capital and alliance name appears and armies
  become figures; closest, armies show their unit counts and commander.
- **Territory** is tinted in a band along each civ's border, leaving the land's
  own colours inside. `B` toggles the region borders.

Start-up options, as environment variables: `CIVSIM_VIEW="x,y,distance"` starts
the camera on a tile, `CIVSIM_DIPLOMACY=1` opens the diplomacy panel, and
`CIVSIM_CARD=<civ id>` opens that civ's card.

Wars and alliances are named when they begin (`diplomacy/naming.py`) from the
world itself: the region being fought over, its capital, the kind of land it
is, or the resource the attacker lacks ("The Brackenfell Iron War", "The War
of Valewatch", "The Cinderford Accord"). Allies drawn into a war fight under
its name. A name used before returns as "The Second ..."

## Layout

```
src/civsim/
  map/         terrain noise, biomes, resource deposits, rivers and lakes, regions, pathfinding
  civ/         civilization state, personalities, the rule-based AI (ai.py)
  economy/     production, population, buildings, effect modifiers, constants (rules.py)
  tech/        tech tree loading/validation, research progress
  diplomacy/   stances, trade deals, alliances, war, region capture (diplomacy.py), the native
               faction (natives.py), constants (rules.py)
  strategy/    check-ins: context shown to a strategist, prompts, reply validation, brains
  military/    unit types, armies, commanders, villagers (army.py), marching and battles (warfare.py)
  llm/         the Ollama client (ollama.py) and the small interface the strategy layer codes against
  bridge/      WebSocket server and tick clock (server.py), wire format (protocol.py)
  simulation.py  owns the world and civs; step() advances one tick
  data/        buildings.json, techs.json, personalities.json, units.json, regions.json
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
work slots per resource from its biome plus any deposit. The seed also places
inland lakes (each at most 14 tiles) and rivers, which rise in hills and
mountains and run downhill to the sea, a lake or another river, widening from
size 1 to 3 along the way. A river runs through land tiles rather than
replacing them, and makes plains, forest and desert more fertile.

**Regions.** The land is divided into 16 regions of similar size (none under
60% or over 150% of the average), each with a capital on a random tile inside
it. Region and capital names come from a fixed list in `data/regions.json`,
shuffled by the seed. Whoever holds a region's capital holds the region.

Each civ starts with two whole regions: a home region, whose capital is its
own, and one beside it. Home regions are picked at random but far apart. The
other eight regions belong to **the Hinterfolk**, a native faction with no
strategist and no diplomacy. Each neutral capital has a garrison (6
soldier-equivalents at the start, growing to 60) that only fights armies sent
against it. A civ takes a neutral region in two ways:

- **Settling it.** Border expansion claims native land tile by tile, but never
  a capital. Every 25 ticks, once a civ holds over 30% of a neutral region,
  each native tile beside its land goes over to it with probability
  0.5 x (share - 0.3); over 60%, the capital itself joins with probability
  (share - 0.6), bringing the rest of the region with it.
- **Taking the capital.** A civ at peace, able to field about twice the
  garrison's defence, raises an expedition and storms a neighbouring neutral
  capital. This is rule-based: no declaration and no diplomacy points.

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

**Water.** A sixth resource, tradeable like the others, but not gathered by
workers: it flows in every tick from what a civ's territory gives access to.
The capital's well gives 0.8, each point of river size on owned tiles 0.12,
each lake tile on the civ's shore 0.3, and, once Water Purification is known,
each owned coast tile 0.15. The cap is 250 plus 10 per source, plus Cisterns.
Civs start with full water. People drink 0.03 each per tick, and farms, mines,
quarries, workshops, barracks and markets use it as upkeep. A civ that runs dry
loses up to 0.4% of its population per tick, in proportion to the shortfall,
and its thirsty buildings stop. A civ short of water steers its expansion
toward rivers, lakes and coast.

Population growth eases off before that point: it is unhindered while a
quarter of the supply is spare, slows in proportion below that, and stops when
use reaches supply (trade imports count as supply, exports as use). So a civ
levels off at what its water supports instead of growing into a drought.

Both strategists weigh water by an **urgency** from 0 to 1: up to 0.5 as the
spare margin disappears, and from 0.5 to 1 once the civ is living off its
stores, by how soon they run out (1 = dry). Below 0.3 a civ does not chase
water, and one with plenty sells it to neighbours who ask. From 0.3 it asks
for water before anything else and never trades its own away. From 0.7 every
trade it proposes is for water, it seeks alliance with water-rich neighbours,
and if none will deal it may attack one that is weaker and in reach. The
rule-based strategist follows this directly; the language model is told the
same in its prompt, and its replies are corrected to the first two rules
(`strategy/checkin.py`) whatever it answers.

**Crossing water.** One rule (`WorldMap.crossing_cost`) governs border
expansion and war reach, and is meant for unit movement later. Lakes and deep
sea can never be claimed. Without Bridge Building a river tile costs three
times as much to claim or to capture; with it, rivers cost nothing extra.
Without Boatbuilding, lakes and deep sea block expansion and attack entirely;
with it a civ can claim land and wage war across up to 6 tiles of open water.
Boats are transport only.

**Demolition.** A civ tears down its own buildings in two cases: one whose
upkeep has gone unpaid for 60 ticks, and, when it has no free tile left, its
least useful building if the one it wants scores at least twice as high.
Demolition frees the tile and refunds 10% of the base cost; at most one every
25 ticks. Four of the construction techs, one per era, raise the refund as one
of their effects: Mining (13%), Masonry (17%), Engineering (21%), Guilds (25%).

**Tech.** 36 techs over 7 eras in `techs.json`: Ancient, Bronze Age, Iron Age,
Medieval (18 techs), then Renaissance, Age of Reason and Industrial (6 each,
at roughly 3,500, 9,500 and 21,000 science). The tree is fixed and
hand-designed. A tech needs its prerequisites, a material cost paid up front,
then science, which is spent as it is produced. A civ with nothing left to
research banks at most 500 science. A civ's era is the highest era among its
known techs. In test games a typical civ finishes the tree around tick 3,000.

The later eras build on the systems below: Fortification and Siegecraft for
defence and capture speed, Military Academy and General Staff for commanders,
Navigation and Desalination for boats and coast water, Waterworks and
Sanitation for water, Civil Engineering for construction, villagers and the
demolition refund (35%), Banking for cheaper trade deals. Six buildings come
with them: Bank, Academy, Harbour (must be on the water), Fortress, Reservoir
and Factory.

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

The brain only sets intent. `diplomacy/diplomacy.py` executes it every tick.
Diplomatic actions are paid for in **diplomacy points**, not gold: every civ
earns 1 per tick automatically, up to 300, starts with 50, and cannot trade
them.

- **Trade.** When two civs both hold `trade` or `ally` toward each other and
  offer different resources, a deal opens: each sends its resource every tick
  for 100 ticks. Each side pays 20 diplomacy points to open it (free between
  allies). A
  rate is capped by what the giver can sustain, and a side that cannot deliver
  for 10 ticks cancels the deal. Gold can be traded like any resource.
- **Alliance.** Mutual `ally` forms one for 50 diplomacy points each plus 0.2
  per tick: +15% defence and +10% science per ally. It lapses when either side
  turns away. Allies see each other's intel at check-ins (exact army numbers,
  how troops are committed, stock and cap of every resource); about anyone
  else a strategist only gets a rough army comparison and public facts. An
  alliance is a defensive pact: when a civ is attacked, its
  allies are at war with the attacker at once, at no cost, for as long as that
  war and the alliance last (a civ allied to both sides stays out). Wars a
  civ starts are optional for its allies: one joins by taking `aggression`
  toward the same enemy, and one that stays out gets nothing. When allies are
  at war with the same enemy, a capture by either
  is joint: the tile and building go to the civ whose army took them, but the
  resources that come with it (the stock in a captured storage building, and
  tribute when a capital falls) are split by army strength at that moment. Shares
  within 5 points of equal (45-55% for two allies) are split evenly.
- **Betrayal.** Ending an alliance and declaring war on that former ally
  within 50 ticks is betrayal. For the first 10 ticks the betrayed
  civ has no home bonus and no militia and the betrayer captures 50% faster.
  For 50 ticks afterwards nobody forms a new alliance with the betrayer, and a
  new trade deal costs it four times the fee (in diplomacy points) and brings in half the partner's
  offer; a further betrayal while distrusted adds another 50. Ending an
  alliance without attacking carries no penalty.
- **War.** `aggression` declares war (100 diplomacy points) once the two territories are
  within 4 tiles (further across water with boats); until then the aggressor's
  border expands toward the target. Troop commitment mobilises up to 35% of the
  population as soldiers. Wars end when a civ's own capital falls, when
  neither side is aggressive (after 50 ticks), or after 400 ticks.

**Armies.** Soldiers are grouped into armies that move on the map
(`military/warfare.py`). Every civ has a garrison at its capital; at war it
also fields one army per enemy, taking four fifths of its soldiers between
them, each under a commander.

- **Unit types** (`data/units.json`): spearmen (from the start), archers (The
  Wheel), swordsmen (Bronze Working), cavalry (Animal Husbandry and Iron
  Working). They differ in strength, speed and upkeep (swordsmen need ore,
  archers wood, cavalry gold) and have mild counters, worth +25%: spearmen beat
  cavalry, cavalry beat archers, archers beat spearmen and swordsmen. Recruits
  are chosen to move the army toward a fixed mix of the types the civ knows,
  leaning on whatever counters the enemy's main arm.
- **Strength** is the phase 3 formula per army: soldiers x unit type (with
  counters) x quality (military techs, pay, ore) x commander skill.
- **Movement.** An aggressor's army paths to the nearest enemy capital; a
  defender's marches to meet armies on or at the edge of its land. Paths use the crossing rule: rivers slow
  an army without Bridge Building, open water needs Boatbuilding. Cavalry-only
  armies move two tiles a tick, others one, slower over forest, hills and
  mountains.
- **Battles.** Armies of warring civs within one tile of each other fight every
  tick until one breaks. There is no minimum or maximum length. Each tick both
  sides take the phase 3 casualties (at 2.5 times the base rate), the weaker
  side losing the larger share, so the gap widens; an army breaks when its
  strength falls below half its opponent's. A badly outmatched army is routed
  at once, armies within 10% of each other fight for roughly 40 to 100 ticks.
  An army on its own land adds militia and the home bonus. A routed army falls
  back to its capital to rest; a beaten garrison is scattered and cannot fight
  until it rallies. Assaults on native capitals work the same way.
- **Taking ground.** An army cannot step onto enemy land until it has captured
  the tile in its way, by the phase 3 capture rule against the local militia.
  Up to two cheap, undefended tiles beside a captured one fall with it.
  Buildings, stores and villagers on captured tiles change hands. An
  aggressor's army makes for the nearest capital its enemy holds; a capital
  costs three times its terrain to capture, and when it falls the whole region
  goes with it (land other civs hold there stays theirs). A civ that loses its
  own capital pays half its stock as tribute, moves its court to another
  capital it holds, and gets a 300-tick truce. A civ with no capital left is
  destroyed and what remains of it goes to its conqueror.
- **Commanders** lead field armies; garrisons have none. Experience comes only
  from combat: 1 per tick of battle, 25 for a win, 5 for a loss. Level is
  1 + sqrt(experience / 25), up to 10. Each level above the first adds 4% to
  the army's strength and takes 2% off its losses. A commander may be killed
  when the army is routed; otherwise they return to the civ's reserve after a
  war and the most experienced one leads the next army.

**Villagers.** Each civ has 2 to 12 villagers on the map, one per 25 people
(`economy/villagers.py`). A building only advances while a villager is standing
on its site, so building far from where they are takes longer. Villagers with
nothing to build walk out to work the land; that part is for show, since the
amounts gathered come from the worker allocation. Armies never harm villagers:
those on a captured tile change sides and wait for their new owner's orders.

## Protocol

JSON text frames, each an envelope `{"type", "version", "tick", "data"}`.

| Direction | Type | Content |
|---|---|---|
| sim -> viewer | `init` | Once on connect: map (heights, biomes, deposits, rivers, region id per tile), regions (name, capital), the native faction, biome/building/unit/tech definitions, civ names and colours |
| sim -> viewer | `tick` | After every tick: full state of every civ (including army, stances and the strategist's reason), every army (position, unit counts, commander) and villager on the map, who holds each region, the territory grid (base64, one byte per tile: owner id, 255 = unowned), relations, deals, pause/speed status, events of that tick. No deltas |
| sim -> viewer | `status` | When pause or speed changes |
| sim -> viewer | `error` | Reply to a bad command |
| viewer -> sim | `command` | `data.action`: `pause`, `resume`, `toggle_pause`, `step`, `set_speed` (with `data.value` in ticks/s, clamped to 0.25-60) |

Field-level detail is in `bridge/protocol.py`.
