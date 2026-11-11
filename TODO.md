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
3. **Visuals with Blender.** Spearman and swordsman models, archer animations
   (`archer.glb` has none), battle and siege effects, a terrain pass.

Later:

- **Playing a civ:** click the map to give army orders, fog of war, save and load.
- **Watching:** a minimap, a "story so far" timeline, an end-of-game summary with graphs, a
  camera that follows the action.
- **Variety:** hand-designed maps (the nine generated ones are much alike), random events
  beyond sickness, more ways to win.
- **Sound:** ambience, battle sounds, a sting when war is declared.
- **Strategist:** finer information than the rough strength bands, breaking truces,
  bluffing, attacks agreed with an ally for a chosen day, stockpiling for a planned war.
- **Armies:** more than two columns, flanking, defending a particular region.
- **Loose ends:** the map names were given without looking at the maps; one large map
  (Wyrmcoast) is slow to simulate.
