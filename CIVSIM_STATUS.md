# CivSim status

Last updated: 2026-11-12, branch `menu-and-civ-logic`, with the nine drawn maps. Read this
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
  sieges with a 100-day capital hold, rallies between allies, reinforcing an ally's
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
  - Blender-made gold mine, ship (shown alone when an army is at sea), harbour, stable,
    catapult and ram (beside armies besieging a capital), and spear;
  - still water and levelled ground under castles.

## In progress

Finishing the to-do list (see ROADMAP "Immediate priorities"):
- done: victory by region points (80% and half the regions), the strategist playing to it,
  rallies called when an ally can reach the gathering city, the timing table;
- league tuning for entertaining games: 10 rounds kept PREP_MIN 29, WALLS_FREE 3.45 and
  PLAN_ABANDON 0.765 (watchability 0.873 → 0.921 over 6 games);
- next: the balance batch on all nine maps (approved), then fixes for the slots it flags;
- after that: the rest of the stabilisation review (the unused models are gone and the root
  is tidied).

`KayKit_ResourceBits_1.0_FREE` is unused and now kept with the other raw packs in `art/kaykit/`;
the old custom .glb files that lay at the root are in `art/legacy_models/` (both ignored by git).

## Known bugs, limits and technical debt

- **Viewer speed:** at the top speed (60 days a second) the viewer falls to 1–2 fps after
  about day 1,800, because it applies a full state message every tick. A paused late map
  draws at about 90 fps. This predates the art pass.
- **Labels crowd** from afar where a rally, a siege and a city meet.
- **The follow camera** (`CIVSIM_FOLLOW`) doesn't always centre on the army it picks.
- **Trees** in forests can still partly hide figures at close zoom.
- **Rallies are rare** (0–3 called a game).
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

- Python: about **500 pass** (about 8 minutes). No known failures.
- Viewer asset check: `assets ok`.
- Timing check (one game per size, utility brain, points victory, new rally rule):
  - Confluence (3 civs): domination on day 3,189 of 6,000, first war day 471, 9 wars, 4 rallies;
  - Emberwaste (5): score on the last day, first war day 465, 3 wars, 17 alliances, no rallies;
  - Five Gates (5): score on the last day, first war day 400, 20 wars, 11 rallies, best 32 of 62 points.
- Speed: a fixed 2,100-day Five Gates game takes 16.7 s (it took 23.4 s before the neighbour cache).

## Latest important changes (newest first)

| Commit | Change |
|---|---|
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

1. The balance batch on all nine maps; fix or drop the start setups it flags.
2. The rest of the stabilisation review: a pass for bugs.
