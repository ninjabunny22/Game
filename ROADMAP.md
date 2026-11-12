# CivSim roadmap

CivSim has two directions that share one simulation:
- **an autonomous civilisation simulator** to be watched, where every civ plays itself and
  explains why;
- **a grand-strategy game** in which the player rules one civilisation while the others carry
  on autonomously.

Marked **agreed** = the user has approved it; **idea** = suggested, not approved. Current
state is in CIVSIM_STATUS.md.

## Immediate priorities (agreed)

1. **Finish the art pass, step 5:** the horse, cavalry, archers, mounted generals and the
   new attack animations (in progress). Then retire the custom Archer and cavalry Knight.
2. **Timing pass.** Put every duration in one table and tune them to fit together:
   - war length (50-day minimum, 100-day capital hold, peace terms from day 150, exhaustion at 400);
   - sickness (from day 250);
   - truces (50 / 150 days);
   - alliances (100-day minimum, lapse after 100 days of peace, 300 days before re-allying);
   - preparation for war, army training speed, restlessness;
   - game length per map size.

   Known oddities: games often end well before the last day, and rallies are rare. The first
   war used to come late; in the latest 3-game check it came on days 503–648.
3. **Tune by league.** Run `python -m civsim.league --evolve` on the settled timings, ideally
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
- **Variety:** hand-designed maps, random events beyond sickness, more ways to win.
- **Sound:** ambience, battle sounds, a sting when war is declared.
- **Strategist:** finer information than the rough strength bands, breaking truces, bluffing,
  attacks agreed with an ally for a chosen day, stockpiling for a planned war.
- **Armies:** more than two columns, flanking, defending a particular region.
- **Population:** a truly denser population (more people per tile, yields rebalanced), instead
  of only displaying four heads per unit.
- **Castle contents:** a forge that shows troop tier, and treasure piles that show gold.
  Suggested, not chosen.
- **Villager:** remade in the Adventurers style. Offered; the user hasn't answered.

## Long-term vision (direction, no commitments)

- As a **simulator:** long games that tell a readable story of rise, alliance, betrayal and
  fall, with every decision explained.
- As a **strategy game:** one civ ruled closely against autonomous rivals, at a chosen
  difficulty, with information the player has to earn (scouting, estimates).
- One coherent low-poly look across the whole map.

## Loose ends

- The map names were given without looking at the maps.
- Wyrmcoast (large) is slow to simulate.
- Labels crowd from afar.
- Trees can hide figures at close zoom.
