# CivSim

Two to five civilizations compete on one of nine hand-drawn maps. A Python simulation core runs the
world; a Godot 4 project renders it in 3D over a local WebSocket.

Project documentation: **CLAUDE.md** (guide and principles), **CIVSIM_STATUS.md** (where
things stand), **ROADMAP.md** (plans), **ARCHITECTURE.md** (how it fits together). This README
is the reference for the rules and numbers.

Built so far: **phase 1** (map, civs, economy, rule-based AI, viewer),
**phase 2** (base tech tree), **phase 3** (upkeep, trade, alliances, war, a
strategic layer), water (rivers, lakes, bridges,
boats) and the first piece of **phase 4** (armies, unit types, commanders and
villagers on the map).

## Run it

Double-click `CivSim.command` in Finder (or run `./CivSim.command`). It starts
the simulation and opens the Godot viewer once the simulation is ready. Closing
the Godot window stops the simulation. Arguments are passed to the sim, for
example `./CivSim.command --seed 42` or `./CivSim.command --rule 0` to play a
civ yourself. Logs go to `logs/`.

To run the pieces by hand:

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python -m civsim                 # random seed, ws://127.0.0.1:8765, 2 ticks/s
.venv/bin/python -m civsim --seed 42 --tick-rate 10
.venv/bin/python -m civsim --rule 0        # play civ 0 yourself (ruler's view)
.venv/bin/python -m civsim --headless --seed 42 --ticks 1500 --brain rules   # no server, prints a summary
.venv/bin/python -m pytest
.venv/bin/python -m civsim.survey                # eight full games: counts ships, crossings and large-building overlaps
```

The civs are played by the built-in strategist (`strategy/utility.py`): at each check-in
it weighs attacking, allying and trading with every neighbour from the civ's personality
and the situation, and says why. `--brain rules` uses the simpler policy the tests run on.

**Main menu.** Started with nothing said about the game (`./CivSim.command`), the
viewer opens on its main menu over a game playing itself. The menu chooses whether to
watch or to rule a civ, a map (any of the nine by name, a random one of a size, or a random
one of any size) and how many civs, within what that map takes. A game to be ruled starts
paused on a screen for choosing a civ. `--size`, `--map` and `--civs` choose the same from
the command line, and any of `--seed`, `--rule`, `--size`, `--map` or `--civs` skips the menu. The
Menu button in a game goes back.

**Playing a civ.** Any civ can be taken in hand from the viewer's panel ("Rule a civ
yourself"), or from the start with `--rule N`. A ruler sets what the realm
concentrates on, what to research and build next, and how to stand toward each other
civ; whatever is left on Auto is still decided by the civ itself, and the civ can be
handed back at any time (`ruler.py`).

**Winning.** The last civ standing wins by conquest. A civ holding 80% of the map's region
**points** (each region is worth 1 to 3, by its land and riches) and at least half of its
regions wins by domination; each civ's card shows its points against the target. Otherwise
the highest score (region points, people, techs) wins on the
last day (6,000 / 8,000 / 10,000 by map size, `SimConfig.end_tick`), but only once a war has
been fought. The game pauses when it is decided and can be played on.

Then open `godot/` in Godot 4.7 or newer and press Play (or
`godot --path godot`). The viewer and the sim can start in either order; the
viewer reconnects on its own.

Viewer controls: drag to pan, right-drag to orbit, wheel to zoom, `Space` to
pause, `.` to step one tick, `-` / `=` to change speed.

The overlay is built for watching:

- **Date.** The top left shows the day (one tick is one day) and the pace in
  days per minute. A banner appears while the sim is paused.
- **Text size.** The whole overlay is drawn 35% larger than Godot's default;
  `[` and `]` make it smaller or larger while watching.
- **Sieges.** A civ's capital does not fall the moment an army breaks in: the army
  has to hold it for 100 days. The map shows who holds it and how far along they are,
  and the defender's armies drop everything to drive them out.
- **Peace on terms.** A side well ahead in a war (five tiles or more) is paid a quarter of
  the loser's stores when it ends, and a winner whose advance has stalled accepts an offer
  of tribute rather than fight on.
- **Allies and betrayal.** Civs join an ally's war when together they outmatch the enemy,
  gang up on a civ running away with the game, and a warlike civ may turn on a weak ally
  that has no other friends.
- **Proposals.** When you rule a civ, the others put alliances, trades and peace to you;
  accept or refuse them at the top of the ruler's panel.
- **Drawn maps.** A game is played on one of nine hand-drawn maps, three of each size, each
  built around one strategic idea (`MAPS` in `config.py`):

  | Map | Size | Civs | What it is about |
  |---|---|---|---|
  | The Gilded Isle | 72x72 | 2-4 | a ring of coast round a lagoon; the only gold is on the stronghold isle in the middle |
  | Confluence | 72x72 | 2-3 | three rivers cut the land into wedges round a rich heartland; one old bridge each |
  | Highgate | 72x72 | 2 or 4 | a plateau of iron and gold walled in by peaks; one pass beside each start |
  | Tidewalk Isles | 96x96 | 2-5 | five isles joined by long bridges over the shallows; iron isles and stone isles |
  | Emberwaste | 96x96 | 2-5 | fertile valleys round a desert that holds the gold; the Oasis of Kesh at the centre |
  | The Divide | 96x96 | 2, 4 or 5 | a ridge of peaks splits the land; three passes, the Kingsgate fortress in the middle |
  | The Five Gates | 160x160 | 2-5 | five home lands round a walled heartland, each with its own gate |
  | The Long March | 256x112 | 2-5 | a long continent of twelve bands; the Crossroads shared by the middle two |
  | The Narrow Sea | 176x144 | 2-5 | two continents joined by the Wyrm's Neck; gold on the Drowned Crown in mid-sea |

  Each map has fixed start slots for each number of civs; the seed only decides which civ
  takes which slot, and who the civs are.
- **Sickness.** A civ at war for 250 days or more may be struck by sickness: it loses people
  at once and for 150 days fights worse and grows slower. Neighbours see it; enemies press
  harder and a warlike ally may turn on it.
- **No peace lasts for ever.** The longer a civ has gone without a war the more it wants one,
  the warlike soonest, until even an equal will do; and a civ whose army is away or has just
  been beaten is attacked sooner. A game nobody has fought in does not end on score.
- **Ceding land.** A side at least twenty tiles behind when peace is made gives up a region
  (never its home) instead of paying tribute.
- **More war, sooner.** Civs reconsider every 10 days. Restlessness sets in after about 250
  days of peace for the most warlike and 500 for the most peaceable; truces last 50 days
  (150 after a capital falls). Neighbours build a grudge along a shared border and over
  native land both are settling. A civ much bigger than a neighbour attacks it whatever
  its temper, and the two strongest civs resent each other, ally less and are quicker to
  betray one another. An alliance lasts only while both sides still choose it, and is
  let go after 100 days in which neither ally is at war.
- **Judgement.** Civs reconsider every day, and keep their word to themselves: a war is
  fought for 50 days before peace is sought, an alliance kept for 100, a goal held for 200.
  A war is forecast before it is started (the march, the walls, who would join, what must
  stay home), prepared against one target (the army is raised first, shown on the civ's
  card), and where the gap is wide tribute is demanded first; the weak and peaceable pay.
  A civ beaten by another wants a bigger edge next time, and never again allies with one
  that betrayed it. Armies make for the capital cheapest to take, keep more at home while
  a third civ threatens, and fall back from fights they cannot win. Builders prepare long
  and guard their homes, Expansionists strike fast, Merchants pay others to fight.
  Research heads for the techs the civ's goal needs. When you rule a civ, the menu's
  Easy / Normal / Hard sets how hard the others go on you.
- **League.** Every number the strategist decides by is a field of `Params`
  (`strategy/utility.py`). `python -m civsim.league --tweak NAME=VALUE ...` plays a changed
  set against the standard one in six games, half the civs on each; `--evolve N` mutates,
  keeps what wins, and refuses anything that makes games duller.
- **Armies are built.** Soldiers are trained a few a day (a levy that grows with the
  population, plus 0.6 a day for each working barracks) and each costs gold and ore to arm;
  a civ with no ore buys its arms in for more gold. Standing down is quick. A lost army
  takes time and money to replace.
- **Bigger armies sooner.** A civ starts with 160 people (shown) and grows twice as fast for
  its first 750 days. Barracks need no research. Gold mines on the map pay their region's
  holder (see Gold mines below). Three late techs (Logistics, Quartermasters, Standing Army) each
  make a soldier 15% cheaper to arm and to pay.
- **Troop tiers.** Iron Working, Machinery and Gunpowder each let a civ arm its soldiers one
  tier better (strength x1.25, x1.55, x1.9; arms cost x1.15, x1.3, x1.5). Recruits get the
  best there is; older soldiers are re-armed, a few a day and for gold and ore, while they
  stand in one of the civ's capitals. An army in the field keeps what it has.
- **Hospitals.** Every capital's castle has its own hospital, with 40 beds shown. Field Medicine
  (era 1), Surgeons (era 3) and Military Hospitals (era 5) each add 40 more to every castle. The
  wounded go to these beds. After 10 days they are healed and join the garrison; they are back
  with an army only when it next fills its ranks. Wounded there is no bed for die.
- **Ranks are filled at home.** An army takes soldiers from the garrison only while it stands
  in one of its civ's capitals. One worn down to under half of what its general can lead,
  with soldiers waiting at home, goes back for them.
- **Standing with an ally.** A civ sends an army to stand in an ally's capital that an enemy
  holds or has an army within 4 tiles of. It adds to the city's defence, fights whoever the
  civ is itself at war with, and goes home 30 days after the danger has passed. A ruler
  sends his with the "Reinforce" button and calls it back himself.
- **Holding a castle.** When one of a civ's own capitals is threatened (an enemy holds it or has
  an army within 4 tiles) and its share of the garrison, with any force already holding it,
  is weaker than the threat, the nearest general within 6 tiles leaves part of his army there:
  enough to match the threat, at most half his army, never fewer than 3. The force stands in
  the castle, counts in its defence and in its garrison as shown, fights intruders, and joins
  the garrison 30 days after the danger has passed. Every civ's generals do this, a ruled
  civ's too.
- **Scouting.** An army's exact size is known only to its own civ, its allies, and a civ with
  an army or capital within 6 tiles. A strategist with most of a neighbour's soldiers in
  sight knows its power exactly; otherwise it has only the rough comparison. When you rule
  a civ, armies out of sight are shown as "~150".
- **More than one army.** Against each enemy a civ fields a main body; from 60 soldiers a
  second column sets out for another of the enemy's capitals; and an intruder far from
  every army gets a home force raised against it, which never leaves its own land. Allies
  at war with the same enemy make for the same capital, and a second army in the breach
  brings a held capital down half as fast again.
- **Generals and garrisons.** A general leads only so many (30 units at level 1, 8 more a
  level; every head count shown is four to the unit), and a civ has at most five armies
  out. The rest of its soldiers wait in its capitals, defend them, and fill the ranks of
  armies that come home.
- **Rallies.** A civ at war can call a rally in one of its cities against one enemy city.
  Allies at war with the same enemy have 40 days to bring an army; whoever is there then
  marches as a single army under the leader's general, with no limit on its size. The
  leader can call it off; it breaks up when the city falls or the army is beaten, each
  ally's survivors going home, and those who helped take a city are paid from the spoils.
  A ruler can call and cancel rallies, and is asked in a dialogue to join an ally's.
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

**Models and water.** The art comes from two KayKit packs by Kay Lousberg (CC0), with our
own models where neither has what is needed. All of it is loaded straight from the files at
run time, so nothing needs importing in the editor. The packs as downloaded (fbx, obj and
gltf of everything) are kept in `art/kaykit/`, which git ignores; the game uses only the
copies in `godot/assets/`.

| Folder | Pack | What it is | Loaded by |
|---|---|---|---|
| `godot/assets/kaykit/` | Medieval Hexagon | buildings, building sites, props, trees, mountains, rocks, water plants | `scripts/models.gd` |
| `godot/assets/adventurers/` | Adventurers, and Character Animations | the six generals, the foot soldier, the archer, their weapons; the animation sets | `scripts/adventurers.gd` |
| `godot/assets/adventurers/civsim_horse.glb` | made in Blender (`tools/blender/make_horse.py`), after a reference picture | the horse the cavalry and mounted generals ride | `scripts/adventurers.gd` |
| `godot/assets/kaykit/civsim_*` | made in Blender, painted from the Hexagon texture | gold mine, ship, harbour, stable, catapult, ram | `scripts/models.gd` |
| `godot/assets/adventurers/civsim_spear` | made in Blender, painted from the knight's texture | the spearman's spear | `scripts/adventurers.gd` |
| `godot/assets/characters/` | our own, older | villager, rider (a villager on horseback) | `scripts/characters.gd` |

The Blender models are built by a script, `tools/blender/make_models.py`
(`/Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender/make_models.py`): each
part is a low-poly primitive painted from one cell of a pack texture, light at its top and
darker at its foot like the pack's own, so the parts painted from the faction cell take each
civ's colour. `godot/tests/models_view.gd`, `castle_view.gd` and `units_view.gd` photograph them.

The pack's hex ground tiles and its terraced hills and grassy peaks are not used: they are
shaped for a hex grid, and CivSim's map is square. `godot/tests/check_assets.gd` loads every
model the viewer uses and checks the animations, weapons and colours
(`Godot --headless --path godot --script res://tests/check_assets.gd`).
`godot/tests/gallery.gd` lines up every figure and the new buildings and saves pictures of them.

- **Generals** are the Adventurers characters: Knight, Barbarian, Ranger, Rogue, hooded
  Rogue and Mage, each with a weapon of its own fixed to the rig's hand slots (two-handed
  sword, axe, bow, daggers, staff and spellbook). A general's character is picked from their
  name and civ, so they keep it for life. They stand a head taller than their soldiers and
  lead from the front. Generals in reserve stand at the gate of the capital they hold.
  From afar the army's marker carries the general's name; at middle zoom the general and
  three of the ranks show; up close, every rank and the full caption.
- **Soldiers:** swordsmen and spearmen are the Adventurers knight with visor down, shield, and
  sword or spear; archers the hooded rogue with a bow; cavalry the knight on horseback, with a
  saddle cloth in his colour. The general of an army that is mostly cavalry rides too.
- **Animations** come from the KayKit Character Animations pack, a file per kind on the same
  rig, each kind as its weapon suits: two-handed chops and a two-handed guard for the knight
  general and the barbarian, slices with a dagger in each hand for the rogues, a bow drawn and
  loosed for the ranger and the archers, a spell for the mage, a diagonal stroke for swordsmen,
  a thrust for spearmen, and seated for riders. The horse walks and trots
  (`tools/blender/make_horse.py`).
- **Colour.** Each Adventurers character is painted from one texture of flat colour cells;
  the cells of its cape and trim are repainted in the owner's colour, keeping their
  shading, and the same texture paints its weapons and shield. Skin, steel and leather are
  never touched. Each figure's body is fused into one skinned mesh.

- Every model shares one small texture, and the faction-coloured parts all sit
  in one rectangle of it. That rectangle is repainted per owner, so roofs and
  banners take any civ's exact colour, and a neutral tan for the Hinterfolk.
- Each building type maps to a model in `BUILDING_MODELS` (`civ_view.gd`).
  Types that share a model carry a small pennant in the type's colour; models
  with nothing to repaint (fields, walls, stockpiles) fly their owner's flag.
- **Ships.** An army that puts out from a harbour is drawn as its ship alone, a three-masted cog
  with sails striped in its civ's colour: its general and soldiers are not seen again until it
  lands. **Siege engines:** an army besieging another civ's capital brings up a ram and a catapult.
- **Buildings.** A building going up shows the pack's three construction stages in turn.
  Barracks have a weapon
  rack and an archery butt, the academy a butt and a tent, the market crates. The fortress is
  the catapult tower, and walls alternate with gatehouses.
- **Castles** are put together from the Hexagon pack's pieces and grow with their civ: a
  palisade and a keep (Ancient), then stone walls with corner towers, towers either side of the
  gate, a well, a church and a smithy, a tavern and a market with towers along the walls, and
  catapults on the corners. A civ's own capital is a step ahead of its others; one the natives
  hold stays at the first stone walls. They stand on 5 x 5 tiles that the simulation keeps free
  of buildings: 4.4 tiles across for a civ's own capital, 3.6 for its others, with a paved yard. The ground under each is levelled so it never
  sinks into a hillside, then eases back into the land; the shore and water are left as they
  are. Inside the walls stand the castle's hospital (a tent, and one more for each hospital
  tech) and the generals in reserve. Soldiers without a general (the garrison) are not drawn:
  click a castle to see who holds it, its garrison, generals, hospital and any enemy hold.
  When you rule a civ, another civ's garrison shows only as "about N" (within 30 of the
  truth, steady from day to day) unless one of your armies has besieged or fought at that
  castle in the last 30 days. An army waiting in its own capital stands outside the gate.
- **Gold mines** are fixed sites drawn on each map, mostly in the regions worth fighting for. Each pays 1 gold a day to whoever holds its region, once that civ knows
  Mining. Nothing can be built on a mine's tile. While an enemy holds a capital, rubble
  and scaffolding lie against its walls.
- **Our own figures.** Archers, cavalry knights, villagers, mounted villagers, the stables, the
  harbour, the ship and the two castles are models in `godot/assets/characters` (`Knight.glb`,
  `Archer.glb`, `Villager.glb`, `Rider.glb`, `Stable.glb`, `Harbour.glb`, `Boat.glb`,
  `Castle.glb`, `CapitalCastle.glb`), loaded by `scripts/characters.gd` and put in their
  civ's colour by swapping one named material. A villager walks, hammers at a building, works
  the land or draws water; a rider stands, walks or trots. If a model file is missing the
  old placeholder is drawn instead.
- **One scale.** Everything is drawn to fit the tile grid. A building fills the
  square of tiles the sim gives it (1, 2 or 3 tiles a side by type), figures
  stand well under a tile tall, and trees on built ground are felled. The same
  things are drawn at every zoom; only armies change, to a marker with their
  size in the whole-map view. The harbour is turned so its quay faces the water.
- A civ's own capital is the large castle (`CapitalCastle.glb`); every other
  region capital is the smaller one (`Castle.glb`). A castle stands on its
  capital's tile and the two rings around it (5 x 5). Each is made of thousands of small
  parts, welded into one mesh when first loaded.
- Buildings are drawn one by one at every zoom, each on its own ground; a
  village's name appears closer in.
- Forest tiles are scattered with trees and mountain tiles with peaks.
- The sea and lakes use a small shader: three bands of colour by depth, a foam
  line at the shore and a gentle swell. Rivers are curved ribbons with a
  flowing surface.

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
  strategy/    check-ins: context shown to a strategist, reply validation, brains
  military/    unit types, armies, commanders, villagers (army.py), marching and battles (warfare.py)
  bridge/      WebSocket server and tick clock (server.py), wire format (protocol.py)
  simulation.py  owns the world and civs; step() advances one tick
  data/        buildings.json, techs.json, personalities.json, units.json, regions.json
godot/         viewer: scripts/main.gd wires sim_client, terrain, civ_view, hud, camera_rig
tests/
```

The simulation knows nothing about time, the network or who plays the civs. A
driver (`bridge/server.py`, the headless runner, a test) decides when to call
`step()` and answers the strategic check-ins the sim raises. With `--brain rules`
a run is fully deterministic for a given seed.

## Timing

Every length of time the game runs on, in days, and where it is set. (Strategist numbers live
in `Params` in `strategy/utility.py`; rules in `diplomacy/rules.py`, `military/warfare.py`,
`economy/rules.py`; game length in `config.py`.)

| What | Days | Where |
|---|---|---|
| Last day (game decided on score) | 6,000 / 8,000 / 10,000 by size | `MAP_SIZES` |
| Early growth bonus | first 750 | `EARLY_GROWTH_UNTIL` |
| Campaigns against the natives: rest between / after a failure | 150 / 200 | `CAMPAIGN_REST`, `CAMPAIGN_RETRY` |
| Peace lasts before any civ grows restless | 350 ÷ its taste for war | `LONG_PEACE` |
| Mustering before a war; preparing one at most | 29+ / 150 | `PREP_MIN`, `PLAN_MAX` |
| A war is fought at least | 50 | `MIN_WAR`, `WAR_MIN` |
| Peace terms (tribute) listened to after | 150 | `TERMS_AFTER` |
| A war is kept up only from strength after | 300 | `WAR_WEARY_TICKS` |
| Both sides exhausted after | 400 | `MAX_WAR` |
| A broken-into capital falls if held | 100 | `CAPITAL_HOLD` |
| Truce after peace / after a surrender or tribute | 50 / 150 | `TRUCE`, `SURRENDER_TRUCE`, `DEMAND_TRUCE` |
| Sickness possible after this long at war; lasts; rest after | 250 / 150 / 400 | `SICKNESS_*` |
| An alliance is kept at least; lapses after this long at peace; re-allying waits | 100 / 100 / 300 | `ALLIANCE_MIN`, `ALLIANCE_WEARS`, `ALLIANCE_REST` |
| A long-term strategy is held at least | 200 | `STRATEGY_MIN` |
| Allies have to reach a rally; before calling another | 40 / 200 | `RALLY_GATHER`, `RALLY_REST` |
| Healing in hospital | 10 | `HEAL_TICKS` |
| Memory of a deed halves | about 460 | `MEMORY_FADE` |

## How the pieces work

**Map.** A square grid, drawn by hand: each map is a blueprint in `civsim/map/designs`
(coastline, regions, ridges and passes, rivers, old bridges, capitals, mines, start slots)
built by `civsim/map/blueprint.py` and saved in `civsim/data/maps`, so a map never changes by
accident. Inside what is drawn, the blueprint's own seed adds the detail: the coast's wobble,
patches of forest and plain, heights, small deposits. A checker proves the built map keeps to
the drawing: every region touches exactly the regions drawn as touching it.
`.venv/bin/python -m civsim.mapmaker check|bake|preview` builds, checks, saves and draws the
maps; `.venv/bin/python -m civsim.fairness` compares the start slots by geography.

The tests also use generated maps: simplex-noise elevation (pulled down at the edges so
land forms continents), moisture and a north-south temperature gradient pick one
of eight biomes. Deposits (fertile soil, fish, game, stone, iron, gold) are
seeded on suitable biomes and grown into contiguous clusters. Each tile offers
work slots per resource from its biome plus any deposit. The seed also places
inland lakes (each at most 14 tiles) and rivers, which rise in hills and
mountains and run downhill to the sea, a lake or another river, widening from
size 1 to 3 along the way and swelling where a tributary joins. A river runs
through land tiles rather than replacing them, and makes plains, forest and
desert more fertile. Each river tile records the tile its water flows into,
so a river is one unbroken course that never doubles back on itself; the
viewer draws rivers along those links only.

**Regions.** A drawn map has 12 or 13 regions (small), 16 to 17 (medium) or 33 to 36
(large), each drawn with its name, capital and borders. Whoever holds a region's capital
holds the region. Each region is worth 1 to 3 **points**, from its land and its riches (shown
in the castle panel); domination is counted in points.

Each civ starts with two whole regions, its slot's home region (its capital) and second
region. Every other region belongs to **the Hinterfolk**, a native faction with no
strategist and no diplomacy. Each neutral capital has a garrison (6
soldier-equivalents at the start, growing to 60) that only fights armies sent
against it. A **stronghold** (marked on the map) keeps 1.5 to 3 times that garrison and
never opens its gates peacefully; once taken it is an ordinary region. A civ takes a neutral region in two ways:

- **Settling it.** Border expansion claims native land tile by tile, but never
  a capital. Every 25 ticks, once a civ holds over 30% of a neutral region,
  each native tile beside its land goes over to it with probability
  0.5 x (share - 0.3); over 60%, the capital itself joins with probability
  (share - 0.6), bringing the rest of the region with it.
- **Taking the capital.** A civ at peace, able to field about twice the
  garrison's defence, raises an expedition and storms the neutral capital worth most to
  it among those it can get at: touching or partly settled by it, or across water once it
  has ships and a harbour. This is rule-based: no declaration and no diplomacy points.

**What land is worth.** One valuation (`strategy/geography.py`) prices every region for every
civ: what it would yield, priced by what the civ lacks, plus mines and strategic weight
(passes, necks, crossroads, prizes, routes through it), discounted by distance and by water
it cannot yet cross, less the cost of taking it and of holding it against its neighbours.
Expansion, campaigns against the natives, which enemy capital an army makes for, the
strategist's wars ("which we want for its two gold mines") and where a harbour is built all
use it.

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
strategists follow this directly, and whatever one answers is corrected to the
first two rules (`strategy/checkin.py`).

**Crossing water and mountains.** One rule (`WorldMap.walkable` and `crossing_cost`)
governs how armies and villagers move, war reach, and how settling spreads:
- **No one walks on water,** deep or shallow, except over a **bridge**. Water is crossed by
  boat only (armies from near a harbour; villagers with boats from any shore). Shallows can
  still be claimed, as fishing grounds, but settling steps from them onto land only by boat.
- **Mountains are walls:** armies and villagers go round them or through a **pass**, which
  is as slow as climbing (2.5 times a plain). Land can still be settled on a mountain, but not
  from there on to the land beyond. Hills are walked. Every map has passes wherever its
  mountains would otherwise part the land, drawn ones and carved ones (`map/passes.py`).
- **High peaks** cannot be crossed, claimed or built on at all.
- **Rivers:** without Bridge Building a river tile costs three times as much to claim, to
  capture or to cross; with it, nothing extra. An **old bridge** drawn over a river is
  crossed at the plain cost by anyone.
- A villager with no way to a place stays where it is, and the place is left alone for 60
  days (a building site there waits without holding up the others).
Without Boatbuilding, lakes and deep sea block expansion and attack entirely;
with it a civ can claim land across up to 6 tiles of open water. Armies, and so
war, need more than boats: see **Ships** below. Boats are transport only.

**Demolition.** A civ tears down its own buildings in two cases: one whose
upkeep has gone unpaid for 60 ticks, and, when it has no free slot left, its
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

**Strategic layer.** Every tick the sim raises a
check-in for each civ: its own state, each neighbour's visible state and recent
dealings between them. A *brain* answers with one stance per neighbour -
`trade`, `ally`, `ignore` or `aggression` - plus terms (a resource to give and
one to want, or a troop commitment) and a short reason. `UtilityBrain` is
the strategist the game is played with; `RuleBrain` is a simpler deterministic
one for tests. Replies are validated and clamped (`strategy/checkin.py`); a missing
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
  within 4 tiles (further across water, by ship from a harbour); until then the aggressor's
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
  an army without Bridge Building, open water needs Boatbuilding and a harbour to sail from. An
  attacker that cannot get to the nearest enemy capital makes for the nearest one it can reach, and
  failing that goes home. Cavalry-only
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
- **Pursuit.** The victor chases a routed army if it is at least as fast, the
  loser is not already at its capital, and no other enemy army is within 3
  tiles. The chase lasts at most 8 days or 6 tiles. Each day the pursuer is
  within a tile, the fleeing army loses 15% of the soldiers it had when it
  broke and cannot fight back; below a fifth of that it is destroyed. It is
  safe once it reaches its capital or a friendly army, and fills no
  ranks while in flight. A pursuer fights at 80% strength during the
  chase and for 5 days after.
- **The fallen.** Of the soldiers a beaten army lost in the battle, and of
  those cut off in a pursuit, 60% are wounded (they go to hospital: see Hospitals above), 30% escape to the
  garrison and 10% die. Half of the winner's losses are wounded too, and half
  of an expedition's against natives. A beaten army's
  commander is killed (10%), captured (25%) or escapes (65%): rolled at every
  rout, and again if the army is then run down. A captured commander changes
  sides half the time (if the captor's roster has room); otherwise he is held
  prisoner until his civ ransoms him (20 gold plus 20 per level, paid to the
  captor, and only while it keeps 20 gold back) or the two civs make peace.
  A beaten army falls back on the nearest capital its civ holds.
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
  the army's strength and takes 2% off its losses. A commander whose army is
  run down in a pursuit may be killed or captured (see The fallen); otherwise
  they return to the civ's reserve after a war and the most experienced one
  leads the next army.
- **The roster.** A civ starts with 3 commanders and may have at most 20,
  counting those leading armies and those in reserve. A new one is promoted
  from the ranks for 20 gold, starting at level 1 (2 with Military Academy, 3
  with General Staff). With Military Academy a civ that has 140 gold appoints
  a trained officer instead, for 120 gold, two levels higher. An army whose
  civ cannot pay goes without a commander.
- **Holding capitals.** Commanders in reserve are stationed one to a capital,
  the most experienced at the capital nearest an enemy. A stationed commander
  adds 10% plus 2% per level to that capital's defence, both to the price of
  taking it and to armies fighting on it. If it falls he faces the same
  10/25/65 roll.

**Villagers.** Each civ has 2 to 12 villagers on the map, one per 25 people
(`economy/villagers.py`). A building only advances while a villager is standing
on its site, so building far from where they are takes longer. Villagers with
nothing to build walk out to work the land; that part is for show, since the
amounts gathered come from the worker allocation. Armies never harm villagers:
those on a captured tile change sides and wait for their new owner's orders.


## Armies, war and waiting for strategists

- **Standing armies.** At peace a civ keeps 10% of its population under arms,
  and recruits or stands down up to 2% of its population a day. The wartime
  cap is unchanged at 35%. An army that is not being paid takes no recruits.
- **No war without an army.** A civ cannot declare war on another civ with
  fewer than 20 soldiers or less than 10% of its population under arms. A
  hostile civ musters what it needs first; the strategist is told the figure
  (`soldiers_needed_to_declare_war`, `max_soldiers`). Expeditions against the
  native faction are not declarations and are unaffected.
- **Allied trade.** Allies open deals without a fee, and on a deal between
  allies 15% more arrives than was sent.
- **Nobody misses a decision.** Each civ's strategist call runs on its own
  thread. If a civ's next check-in falls due while its last is unanswered, the
  server holds the clock for everyone until it answers; the viewer shows who
  it is waiting for. With a slow model and a fast clock the game advances
  about one check-in interval per answer.
- **Army counts.** Unit counts are whole numbers that add up exactly to the
  army's size. The civ card lists each army with its own breakdown, and an
  army shows its breakdown on the map whether or not it has a commander.

## Horses, stables and ships

- **Stables** (Animal Husbandry; 90 wood, 30 stone, 20 days; upkeep 0.15 food
  and 0.05 water a day; a civ builds at most 2). Each working stable breeds one
  horse every 10 days and keeps up to 8, counting those out under riders.
- **Every horse eats and drinks twice what a person does** (0.16 food and 0.06
  water a day), whether it is in the stables or under a rider.
- **Cavalry need a horse each.** A cavalry recruit takes one from the stables;
  with none to be had, the recruit serves on foot as another unit type.
  Cavalry stood down return their horses; cavalry lost in battle do not.
- **Mounted villagers.** At peace, spare horses go to villagers, up to half of
  them. A mounted villager at work on the land adds the output of three more
  workers of whatever it is gathering. While the civ is at war or threatened
  no more villagers mount, so the army has first call on the herd. A mounted
  villager on a captured tile loses the horse and carries on as a plain
  villager: villagers are never killed.
- **Ships.** An army crosses open water (sea and lakes alike) only by ship, and
  can only put out from land within 3 tiles of one of its civ's working Harbours
  (`economy/harbours.py`); it is drawn as a ship from then until it lands, and
  may land anywhere. With no such harbour it cannot cross: its route goes round
  by land or it stays on its landmass, and war cannot be declared across water
  it could not cross. The range numbers are unchanged (6 tiles with
  Boatbuilding, one more per Harbour, four more with Navigation). An army already
  at sea when its harbour is lost sails on and lands. Villagers take ship the
  same way and are not drawn while at sea; one with no way to its work is still
  carried there, unseen, so that no building site is left without a builder.

## Villages and building slots

- **One building to a tile, each its own size.** A building stands on a square
  of tiles, `size` a side in `data/buildings.json`: most are 1, farms, stables,
  harbours, aqueducts, reservoirs, universities, banks, academies and factories
  are 2x2, and a fortress is 3x3. No two buildings' ground overlaps, across
  borders too. A capital's castle has its tile and the two rings around it (5 x 5), and
  nothing is built there. Stables can never stand on a capital's tile by any
  route: every placement goes through one rule (`placement_problem` and `place`
  in `economy/buildings.py`), and anything found on a castle's ground when it
  changes hands is not handed on. A building belongs to its own tile (the
  middle of an odd-sized square, the corner nearest the origin of an even one)
  for capture, villages and builders.
- **Growing outward.** When choosing a site a civ prefers ground beside
  something already built, or beside a castle, to breaking new ground;
  buildings placed by yield weigh that against the yield. With no room left it
  clears whatever stands on the least useful square the new building would fit.
- **Villages.** Every capital a civ holds is the centre of its own town. A
  building joins the nearest village or town of its civ within 4 tiles that
  still has room (a town holds 60 buildings, a village 40); if there is none
  it founds a new village on its own tile, named from a fixed list. A village belongs to whoever holds its centre tile, so it is taken
  whole when that tile is captured; buildings left on either side rejoin the
  nearest village of the civ that now has them (or found a new one). A
  village with no buildings left disappears; a capital's town does not.

## Protocol

JSON text frames, each an envelope `{"type", "version", "tick", "data"}`.

| Direction | Type | Content |
|---|---|---|
| sim -> viewer | `init` | Once on connect: map (heights, biomes, deposits, rivers, region id per tile), regions (name, capital), the native faction, biome/building/unit/tech definitions, civ names and colours |
| sim -> viewer | `tick` | After every tick: full state of every civ (including its buildings, each with an id and its village, its villages, army, stances and the strategist's reason), every army (position, unit counts, commander) and villager on the map, who holds each region, the territory grid (base64, one byte per tile: owner id, 255 = unowned), relations, deals, pause/speed status, events of that tick. No deltas |
| sim -> viewer | `status` | When pause or speed changes |
| sim -> viewer | `error` | Reply to a bad command |
| viewer -> sim | `command` | `data.action`: `pause`, `resume`, `toggle_pause`, `step`, `set_speed` (with `data.value` in ticks/s, clamped to 0.25-60) |

Field-level detail is in `bridge/protocol.py`.
