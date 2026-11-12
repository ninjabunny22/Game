# To do

Agreed next, in order:

1. **Timing pass.** Put every duration in one table and tune them to fit together: war
   length (50-day minimum, 100-day capital hold, peace terms from day 150, exhaustion at
   400), sickness (from day 250), truces (50 / 150), alliances (100-day minimum, lapse after
   100 days of peace, 300 days before re-allying), preparation for war, army training
   speed, restlessness, and game length per map size. Known oddities:
   - the first war comes around day 500-900, later than the 300-700 aimed for;
   - most games end between day 1,400 and 5,500, well before the last day.
2. **Tune by league.** Run `python -m civsim.league --evolve` on the settled timings,
   ideally to one set of numbers per personality. Decide first whether the aim is the
   strongest civs or the most entertaining games.
3. **Visuals with Blender.** What neither KayKit pack has, to be made in the packs' chunky
   style so it sits beside the generals:
   - a melee swing for the Adventurers rig (the free pack's nearest is an overarm throw) and
     a bow shot;
   - archer and cavalry soldiers, and a mounted general (the pack has no horses);
   - ship, harbour and stable in the same style (ours are more detailed than the rest);
   - a gold mine of its own (it is the mine with props), and a hospital building for the castle courtyard (now tents);
   - siege engines in the field, and battle and siege effects;
   - a spear for the spearman (now a pole and blade added in code).

Later:

- **Zoom tiers in the viewer:** far (territory, city and army markers only), mid (simplified
  towns, one figure per army), near (everything); draw only what is on screen. Measure
  frame rate on a late large game before and after.

- **Playing a civ:** click the map to give army orders, fog of war, save and load.
- **Watching:** a minimap, a "story so far" timeline, an end-of-game summary with graphs, a
  camera that follows the action.
- **Variety:** hand-designed maps (the nine generated ones are much alike), random events
  beyond sickness, more ways to win.
- **Sound:** ambience, battle sounds, a sting when war is declared.
- **Strategist:** finer information than the rough strength bands, breaking truces,
  bluffing, attacks agreed with an ally for a chosen day, stockpiling for a planned war.
- **Armies:** more than two columns, flanking, defending a particular region.
- **Rallies are rare** (0-3 called a game, few march): alliances are short and allied armies are
  often too far from the city to arrive in 40 days. To settle in the timing pass.
- **Population:** head counts are shown at four to the unit; the economy itself is unscaled.
  A denser population (more people per tile, with yields rebalanced) would be a real change.
- **Viewer at top speed:** at 60 days a second the viewer falls to 1-2 frames a second after
  about day 1,800 (it did before the KayKit change too); a paused late map draws at 90+. Each
  tick's full state is applied in one frame: spread the work, or send deltas.
- **Labels crowd** from afar where a rally, a siege and a city meet.
- **Loose ends:** the map names were given without looking at the maps; one large map
  (Wyrmcoast) is slow to simulate.
