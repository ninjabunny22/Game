# CivSim status

Last updated: 2026-11-13, branch `main`, with the nine drawn maps. Read this
first when resuming work.

## Stage

A playable, watchable simulation with a full economy, research, diplomacy and army war,
and a 3D viewer that is mid-way through an art pass (moving everything to the KayKit packs'
style). Balance and timing have not had their dedicated pass yet.

## Implemented and working (committed)

- **Maps:** nine hand-drawn maps, three per size (README table), built from blueprints in
  `map/designs`, checked against their drawing and saved in `data/maps`:
  - small 72² (12–13 regions), medium 96² (16–17), large about 25,000 tiles (34–36 regions,
    160², 256×112, 176×144);
  - fixed start slots for each number of civs (2–5, Confluence 2–3, small 2–4), civs given
    slots at random;
  - movement: no walking on water but over bridges, mountains only through (slow) passes,
    carved automatically where mountains would part the land; villagers never walk
    through what they cannot cross;
  - impassable high peaks with passes, old bridges, native strongholds (1.5–3× garrison,
    never defect), gold mines drawn where they matter, region points 1–3 (shown only);
  - tools: `civsim.mapmaker` (check, bake, preview), `civsim.fairness` (slots by geography),
    `civsim.balance` (slots by played games; not yet run at scale).
- **Region valuation** (`strategy/geography.py`): one value per region per civ, used by
  expansion, native campaigns (including across water), war targets, harbour siting and the
  strategist's war reasons.
- **Economy:** workers, six resources (food, wood, stone, ore, gold, water), buildings with
  upkeep and placement rules, storage, villagers, horses, harbours, trade deals, early
  growth bonus, gold mines on every gold vein (1 gold a day to the region's holder, once it
  knows Mining).
- **Research:** 42 techs in 7 eras, including soldier-cost efficiency, troop tiers (1–4) and
  castle hospital beds.
- **Military:** trained and paid soldiers, up to 5 field armies per civ under commanders with
  limited capacity, garrisons, unit counters, battles, routs, pursuit, captured commanders,
  sieges with a 60-day capital hold, rallies between allies, reinforcing an ally's
  capital, generals leaving part of their army to hold a threatened castle of their own,
  refitting only at home, hospitals (10-day healing), scouting.
- **Diplomacy:** stances, alliances (wear out after 100 days of peace), betrayal, peace terms
  and tribute, coalitions, friction at borders, rivalry between the top two, sickness in long
  wars, natives.
- **Strategist:** daily decisions by `UtilityBrain` with forecasts, war plans, lessons,
  personality tactics and difficulty (easy/normal/hard for a ruled game); a league tool
  for comparing tweaks (`civsim.league`, at most 6 games).
- **Player:** watch or rule from the main menu, on any of the nine maps or a random one; ruler orders, proposals and rally pop-ups;
  clicking a castle shows its garrison (an estimate within ±30 for other civs unless one of
  the player's armies attacked it in the last 30 days).
- **Victory:** conquest, domination (70% of regions) or score at the last day (6,000 /
  8,000 / 10,000 by size), only once a war has been fought.
- **Viewer art:**
  - six Adventurers generals; Knight foot soldiers, hooded-Rogue archers, Knight cavalry on a
    rigged horse (mounted generals for cavalry armies), all animated from the KayKit
    Character Animations pack by weapon;
  - castles built from Hexagon pieces that grow by era;
  - Blender-made gold mine, ship (shown alone when an army is at sea), fishing boat with oars
    (a villager crossing water is shown as one, rowing), harbour, stable,
    catapult and ram (beside armies besieging a capital), and spear;
  - still water and levelled ground under castles.

## In progress

Plan (agreed 2026-11-13): war on the AI's own judgement with a home guard; fights you can follow
(fight boxes, a battle alert); a top-left icon bar; a tech tree viewer. Done so far:
- **Land changes hands only as whole regions** (no settling tile by tile, no defection, no
  tile-by-tile capture in war); native regions are taken nearest first, and campaigns go on
  during a war far away. Three check games: Highgate 4 civs ends on score at day 6,000,
  Emberwaste 5 by domination at 5,794, Five Gates 5 on score at 10,000 (its heartland
  strongholds stay native, and nothing changed hands after day 4,000: watch for stalemates).
  The balance batch below predates this rule.
- **Castles:** nobody is drawn inside; clicking one opens a panel beside it with what is inside.
  **Minimap** at the bottom right.
- **War on the AI's own judgement:** no minimum army to declare war; a home guard (enough to
  hold off the strongest other civ in reach) stays home. Three check games: first wars on days
  631 (Highgate), 427 (Emberwaste), 387 (Five Gates); 19, 33 and 35 wars; all ended on score.
  Tuned against stalemates (3 games each): home guard 0.6 → 0.4 and the capital hold 100 → 60
  days. Castles taken in wars went from a handful to 5 / 8 / 5 (Highgate / Emberwaste / Five
  Gates). Still open: once two or three big civs remain they rarely take land from each other
  (Highgate after day ~3,900, Five Gates after ~4,700); all three games ended on score.
- **Fights you can follow** (boxes over battles and sieges, a battle alert), the **icon bar**,
  and the **tech tree** viewer, all while spectating.
- **Rich nodes** (a deposit yielding 3x, named, in about a third of the regions that start
  neutral; never in a start region) and **more reasons for war**: a rich node of something the
  civ lacks, lost lands (most of all its old home), no room to grow, a refused trade, a gate
  into its land. **War is proclaimed** in a banner mid-screen, in the declarer's voice, from the
  real reason or their history. Three check games: wars were started for 5-8 different reasons
  a game (grudges, bullying, gates, an ally's war, a runaway leader...); "no room to grow"
  named most of Highgate's wars until it was made to give way to more specific reasons.
- **A decluttered watch mode** (plan agreed 2026-11-13, four phases; ruler mode unchanged):
  1–2 done: one bar across the top with a scoreboard chip per civ, and one drawer per civ
  (Overview, Army, Diplomacy, Tech tabs; Follow; Rule it) in place of the civ cards, the
  "Rule a civ" panel and the diplomacy panel. 3 done: a fading ticker with the newest
  headline, and a chronicle (`L`) with every headline, filtered by civ. 4 done: a calmer
  map (smaller labels fading with distance, a shield for strongholds, arcs and deposit cubes
  by zoom, one fight box at a time, layer toggles over the minimap). Next: the same pass for
  ruler mode, if wanted. Note: `check_assets.gd` does not load `hud.gd`; check it with
  `--check-only --script res://scripts/hud.gd`.

- **Royal houses** (plan agreed 2026-11-13): `civ/family.py` with exact ageing, a Gompertz
  mortality curve calibrated on 2,000 lives per start age (README table), sudden deaths,
  murder by enemies, marriages, births, princes commanding armies, succession with a new
  personality and 60 days of unrest; portraits cut from the boards (`tools/cut_portraits.py`);
  a Family tab in the drawer, family banners and chronicle lines; protocol 21. The
  "Noble Houses Collage" board is not used (it contradicts the single-house boards).
- **Rebellions and more** (plan agreed 2026-11-13): plots by ambitious princes, rebel civs
  appearing mid-game (protocol 22, `roster`), regency and usurping regents, throne claims
  through marriage (war motive "inheritance"), prince ransoms, traits, a family tree view.
  Rebels find patrons, who keep their word (a sworn bond) or betray them; fallen rebels are
  locked away or ransomed to their fathers. Three check games: about 0.4 expected plots a
  game (0.48 / 0.37 / 0.35), so roughly one game in three sees a rebellion.
- **Main menu** (redesigned 2026-11-13): a side panel in three steps (how to play, map,
  options once a map is picked) with Start always in reach; choosing a map or civ count swaps
  the backdrop for that map on day 0 (`preview_map`, paused) and a card marks each civ's
  start; Start reuses the preview's seed, so the game is the one shown (the seed field is
  gone). New option: court intrigue (`SimConfig.intrigue`, `config.INTRIGUE`: off 0, rare
  0.5, normal 1, frequent 2.5 times the plot and murder chances).

- **Project cleanup** (2026-11-13): the launcher is `Play CivSim.command` in the root (it
  repairs a missing package, checks Python 3.11, and stops a simulation left running); the
  working docs are in `docs/`; the portrait boards are with the other source art in
  `art/portraits_royalty/`; the empty TODO.md stub, a dead HUD tech button, the unused
  `toggle_region_borders` and an unused server field are gone. No change to play or visuals.

## Balance batch (2026-11-13)

5 games per civ for every map and civ count (`civsim.balance`, 90% intervals). A slot is
flagged when its win rate is off by more than 15 points and outside its interval; with about
70 slots, a few flags are expected by chance.

| Map | Civs: wins per slot |
|---|---|
| Gilded Isle | 2: 4/6 · 3: 3/4/8 · 4: 6/4/7/3 |
| Confluence | 2: 5/5 · 3: 6/5/4 |
| Highgate | 2: 5/5 · 4: NE 4, NW 6, SE 8, SW 2 (SW falls most; an earlier run had NW 10) |
| Tidewalk Isles | 2: 6/4 · 3: 6/3/6 · 4: Corrie 9, Dunlin 1 (flagged) · 5: 6/5/3/5/6 |
| Emberwaste | 2: 6/4 · 3: S4 9 of 15 (flagged: beside the empty slots) · 4: 8/3/7/2 · 5: 7/3/5/3/7 |
| The Divide | 2: 5/5 · 4: 4/5/5/6 · 5: 5/5/4/7/4 |
| Five Gates | 2: 6/4 · 3: W4 1 of 15 (flagged) · 4: 6/6/5/3 · 5: W1 1 of 25 (flagged) |
| Long March | 2: 6/4 · 4: 4/6/4/6 |
| Narrow Sea | 2: 7/3 · 3: 6/6/3 · 4 (with the Skerry): 5/4/5/6 |

- **Changed from it:** the Narrow Sea's Skerry became the east's Neck (a fortress with a mine
  on causeways; before, the two western civs won 17 of 20 four-civ games); more iron in its
  south; the Long March offers 2 or 4 civs (the Middle won 11 of 15 and 11 of 25 with 3 and 5);
  the Narrow Sea offers 2–4 (a fifth civ in the Neck won 10 of 25 on both maps).
- **Leans left to watch:** Tidewalk with 4 (Dunlin weak, from which way its causeways turn),
  Highgate with 4 (SW, cause unknown), Five Gates (different wedges flagged at 3 and 5 civs
  though the wedges measure alike: probably chance), Emberwaste with 3 (S4's room).

`KayKit_ResourceBits_1.0_FREE` is unused and now kept with the other raw packs in `art/kaykit/`;
the old custom .glb files that lay at the root are in `art/legacy_models/` (both ignored by git).

## Known bugs, limits and technical debt

- **Viewer speed:** at the top speed (60 days a second) the viewer falls to 1–2 fps after
  about day 1,800, because it applies a full state message every tick. A paused late map
  draws at about 90 fps. This predates the art pass.
- **Labels crowd** from afar where a rally, a siege and a city meet.
- **The follow camera** (`CIVSIM_FOLLOW`) doesn't always centre on the army it picks.
- **Trees** in forests can still partly hide figures at close zoom.
- **Timing:** not yet tuned as a whole (see ROADMAP).
- **Water crossings are mid-game:** armies need a harbour, and harbours need Navigation
  (era 4), so island prizes fall late or not at all (in the first Gilded Isle check game the
  isle was never taken). Settlers cross with Boatbuilding.
- **Grid corners:** where three drawn regions meet, the grid sometimes lets two of them
  touch at a corner; these are drawn in as links (`may_touch`, or listed by hand), which
  leaves some rotations a tile or a link apart.
- **Older models:** Villager and Rider are older custom models in a different style
  (neither pack has a worker character; the animation pack's tool animations could serve one).
- **Horse:** modelled in Blender after the user's reference (`tools/blender/make_horse.py`):
  a faceted chestnut, smooth-shaded. It is more realistic than the chunky riders.
- **Head counts** are only a display scale; the economy itself isn't denser.

## Tests

- Python: **518 pass** (about 8½ minutes). No known failures.
- Viewer asset check: `assets ok`.
- The units picture scene (`godot/tests/units_view.gd`) also checks every frame that no boat's
  keel is under the water, and prints `boats above water: ok`.
- Timing check (one game per size, utility brain, points victory, new rally rule):
  - Confluence (3 civs): domination on day 3,189 of 6,000, first war day 471, 9 wars, 4 rallies;
  - Emberwaste (5): score on the last day, first war day 465, 3 wars, 17 alliances, no rallies;
  - Five Gates (5): score on the last day, first war day 400, 20 wars, 11 rallies, best 32 of 62 points.
- Speed: a fixed 2,100-day Five Gates game takes 16.7 s (it took 23.4 s before the neighbour cache).

## Latest important changes (newest first)

| Commit | Change |
|---|---|
| `363135d` | Villagers cross water as fishing boats, rowing |
| `874dde0` | Malformed commands refused instead of crashing |
| `c22bcbc` | The Narrow Sea's Skerry crossing; Narrow Sea 2–4 civs |
| `457c9dc`, `1de0466`, `9f27b23`, `9fe4b7b`, `dbe180b` | Balance fixes from the batch; eight-way movement |
| `826555f` | Victory by region points; the strategist plays to the race |
| `42ff52f` | About 30% faster simulation, identical games |
| `cc239e8` | Nobody walks on water (bridges only) or over mountains (passes only) |
| `8a56262`, `4dcb428` | The Long March 256 wide, civs in its four corners |
| `1004046` | Nine hand-drawn maps; one valuation of land for the AI |
| `08997b2` | Blender models: gold mine, ship, harbour, stable, siege engines, spear |
| `c441d5b` | Gold mines as fixed map sites; garrisons only shown by clicking a castle (with estimates); castles built from pack pieces |
| `67b0fc8` | Levelled ground under castles; 5×5 castle ground; hospitals inside castles with three research steps |
| `ef5ea66` | Still water |
| `d3a7160` | Generals are Adventurers characters; more Hexagon models on the map |
| `d470275` | Bigger armies sooner; hospitals, refits, troop tiers, reinforcing allies, scouting |

## Immediate next steps

1. Re-measure the leans above with fresh seeds (`civsim.balance --first-seed`) before changing
   those maps.
2. Look at the Narrow Sea's new Skerry causeways in the viewer (drawn by the same bridge code
   as Tidewalk's, not yet seen on screen).
3. Then ROADMAP "Next development stages".
