# CivSim roadmap

CivSim has two directions that share one simulation:
- **an autonomous civilisation simulator** to be watched, where every civ plays itself and
  explains why;
- **a grand-strategy game** in which the player rules one civilisation while the others carry
  on autonomously.

Marked **agreed** = the user has approved it; **idea** = suggested, not approved. Current
state is in CIVSIM_STATUS.md.

## Immediate priorities (agreed)

- ~~**Next: an AI that sees its attacks through.**~~ Done 2026-11-14 (mustering, a fixed
  castle per column, friends counted, war judged by its course). Still open: deeper values.
- **An AI that understands the game.** Armies often
  attack a castle, then give up mid-fight though they have the troops: find why (campaign or
  siege abandonment, intent flips, home-guard recalls) and fix it. Then rework what the
  strategist values (`Params`, context, region values) so its choices follow the game's real
  economy, war odds, regions and alliances.

0. ~~**The nine drawn maps: judge them by play.**~~ Done: the balance batch (5 games per civ,
   every map and civ count) is in CIVSIM_STATUS.md; victory is by region points (80% and half
   the regions). Fixed from it: eight-way movement, centrality, Gilded Isle's 4-civ homes,
   The Divide's mines, the Long March's corners, the Narrow Sea's Skerry; dropped: the Long
   March with 3 or 5 civs, the Narrow Sea with 5. Left as leans to watch (see STATUS).
1. **Timing pass.** The durations are in one table (README "Timing"). Measured with the new
   victory rule: first wars on days 400–471, games running to 53–100% of the last day. Rallies
   were never called (an ally had to be near the caller's capital); now they are, when an ally
   can reach the city the rally gathers in. Nothing else retuned until the balance batch shows
   a pattern rather than one game.
2. **Tune by league** for entertaining games in which civs play to the objectives:
   `python -m civsim.league --aim fun --evolve N` (every civ plays the variant; kept if games
   are better to watch: length, wars, alliances, rallies, lead changes, prizes taken, someone
   near winning, varied winners). First 10 rounds kept PREP_MIN 29, WALLS_FREE 3.45,
   PLAN_ABANDON 0.765; more rounds can be run on top.

## Next development stages

- **Agreed, for later:** zoom tiers in the viewer.
  - Far: territory, city and army markers only. Mid: simplified towns, one figure per army.
    Near: everything.
  - Draw only what is on screen.
  - Measure the frame rate on a late large game before and after.
- **Agreed direction:** use Blender, by script, for what the packs lack. Still open:
  battle and siege effects (dust only so far), a gold mine model of its own, and a hospital
  building for the castle courtyard (tents for now).
- **Idea:** fix the viewer's slowdown at top speed by spreading each tick's work over frames
  or sending only changes.

## Medium-term features (ideas, not yet approved)

- **Playing a civ:** click the map to give army orders, fog of war, save and load.
- **Watching:** a minimap, a "story so far" timeline, an end-of-game summary with graphs, a
  camera that follows the action.
- **Variety:** random events beyond sickness, more ways to win, more drawn maps (alternates
  already designed: Wildwood, Caldera, The Broken Crown).
- **Sound:** ambience, battle sounds, a sting when war is declared.
- **Strategist:** finer information than the rough strength bands, breaking truces, bluffing,
  attacks agreed with an ally for a chosen day, stockpiling for a planned war.
- **Armies:** more than two columns, flanking, defending a particular region.
- **Population:** a truly denser population (more people per tile, yields rebalanced), instead
  of only displaying four heads per unit.
- **Castle contents:** a forge that shows troop tier, and treasure piles that show gold.
  Suggested, not chosen.
- **Villager:** remade in the Adventurers style. Offered; the user hasn't answered. The
  animation pack's tool animations (hammering, digging, pickaxing, working) would fit it.
- **Deaths and hits:** use the animation pack's hit and death animations in battle.

## Long-term vision (direction, no commitments)

- As a **simulator:** long games that tell a readable story of rise, alliance, betrayal and
  fall, with every decision explained.
- As a **strategy game:** one civ ruled closely against autonomous rivals, at a chosen
  difficulty, with information the player has to earn (scouting, estimates).
- One coherent low-poly look across the whole map.

## Loose ends

- Labels crowd from afar.
- Harbours need Navigation (era 4), so no army can cross water before the mid-game: the
  Gilded Isle, Pearl Reef and the Drowned Crown are mid-game prizes. Settlers can cross with
  Boatbuilding. Decide whether that is the timing wanted.
- The old bridges are drawn with the pack's bridge model laid across the river; check how it
  sits at close zoom.
- Trees can hide figures at close zoom.
