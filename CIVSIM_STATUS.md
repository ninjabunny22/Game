# CivSim status

Last updated: 2026-11-12, branch `menu-and-civ-logic`. The code is as of `08997b2`; these
documents were added in the commit after it. Read this first when resuming work.

## Stage

A playable, watchable simulation with a full economy, research, diplomacy and army war,
and a 3D viewer that is mid-way through an art pass (moving everything to the KayKit packs'
style). Balance and timing have not had their dedicated pass yet.

## Implemented and working (committed)

- **Map:** three fixed seeds per size (small 64², medium 96², large 128²), biomes, rivers,
  lakes, deposits, regions with native-held capitals; 2–5 civs at random starts.
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
- **Player:** watch or rule from the main menu; ruler orders, proposals and rally pop-ups;
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

Nothing half-done in the working tree. The newest work is committed:
- **The art pass's last step** (`c35c41a`, `b285534`):
  - every Adventurers figure animated from the KayKit Character Animations pack, each kind
    as its weapon suits;
  - archers are the hooded Rogue with a bow;
  - cavalry are Knights on a rigged horse modelled after the user's reference picture;
  - generals of mostly-cavalry armies ride.
- **Holding castles**: a general near a threatened castle of his own, too weakly held, leaves
  part of his army there to hold it.

`KayKit_ResourceBits_1.0_FREE` (added by the user, at the repository root) is still unused.

## Known bugs, limits and technical debt

- **Viewer speed:** at the top speed (60 days a second) the viewer falls to 1–2 fps after
  about day 1,800, because it applies a full state message every tick. A paused late map
  draws at about 90 fps. This predates the art pass.
- **Labels crowd** from afar where a rally, a siege and a city meet.
- **The follow camera** (`CIVSIM_FOLLOW`) doesn't always centre on the army it picks.
- **Trees** in forests can still partly hide figures at close zoom.
- **Rallies are rare** (0–3 called a game).
- **Timing:** not yet tuned as a whole (see ROADMAP).
- **Maps:** the map names were given without looking at the maps, and the large map
  Wyrmcoast is slow to simulate.
- **Older models:** Villager and Rider are older custom models in a different style
  (neither pack has a worker character; the animation pack's tool animations could serve one).
- **Horse:** modelled in Blender after the user's reference (`tools/blender/make_horse.py`):
  a faceted chestnut, smooth-shaded. It is more realistic than the chunky riders.
- **README:** a few lines in the opening are out of date: it says four civs, Godot 4.3+,
  and 60% for domination; the code has 2–5 civs, Godot 4.7 and 70%.
- **Head counts** are only a display scale; the economy itself isn't denser.

## Tests

- Python: **440 passed** with the castle-holding change (about 9 minutes). No known failures.
- Viewer asset check: `assets ok` with the latest horse.
- Last balance check (3 games, with castle holding):
  - generals left a force to hold a castle 4, 31 and 48 times (small, medium, large);
  - first wars came on days 503–648, and armies went unpaid on 2–7% of days;
  - every game ended by domination (days 1,395, 3,982 and 4,943).

## Latest important changes (newest first)

| Commit | Change |
|---|---|
| `08997b2` | Blender models: gold mine, ship, harbour, stable, siege engines, spear |
| `c441d5b` | Gold mines as fixed map sites; garrisons only shown by clicking a castle (with estimates); castles built from pack pieces |
| `67b0fc8` | Levelled ground under castles; 5×5 castle ground; hospitals inside castles with three research steps |
| `ef5ea66` | Still water |
| `d3a7160` | Generals are Adventurers characters; more Hexagon models on the map |
| `d470275` | Bigger armies sooner; hospitals, refits, troop tiers, reinforcing allies, scouting |

## Immediate next steps

1. Finish step 5:
   - check the bow shot and the swings;
   - compare the new `KayKit_Character_Animations_1.1` pack and use its animations if they're better;
   - run the asset check and a real game;
   - commit.
2. Remove the custom Archer and cavalry Knight models once step 5 is verified.
3. Then the agreed timing pass (ROADMAP).
