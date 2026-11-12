# CivSim roadmap

CivSim has two directions that share one simulation:
- **an autonomous civilisation simulator** to be watched, where every civ plays itself and
  explains why;
- **a grand-strategy game** in which the player rules one civilisation while the others carry
  on autonomously.

Marked **agreed** = the user has approved it; **idea** = suggested, not approved. Current
state is in CIVSIM_STATUS.md.

## Immediate priorities (agreed)

0. **The nine drawn maps: finish judging them.** They are built and playable (see
   CIVSIM_STATUS.md). Still to do:
   - **balance batch** (`civsim.balance`), about 70 games per map, once you approve running
     more than 3 games at a time; then adjust the maps whose slots it flags;
   - **victory by region points**, if approved: 70% of the map's points and at least half the
     regions (points are already worked out and shown; victory still counts regions);
   - decide whether to keep the uneven setups the fairness report flags (Highgate with 3,
     the rings of five with 3 or 4, The Divide with 3 or 5, the Narrow Sea's Neck slot).
1. **Timing pass.** Put every duration in one table and tune them to fit together:
   - war length (50-day minimum, 100-day capital hold, peace terms from day 150, exhaustion at 400);
   - sickness (from day 250);
   - truces (50 / 150 days);
   - alliances (100-day minimum, lapse after 100 days of peace, 300 days before re-allying);
   - preparation for war, army training speed, restlessness;
   - game length per map size.

   Known oddities: games often end well before the last day, and rallies are rare. The first
   war used to come late; in the latest 3-game check it came on days 503–648.
2. **Tune by league.** Run `python -m civsim.league --evolve` on the settled timings, ideally
   to one set of numbers per personality. First decide whether the aim is the strongest civs
   or the most entertaining games.

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
