"""A whole stretch of a game with the state checked every day: whatever the civs do, the
books must balance and nobody may stand where nothing can."""

import json
import math

from civsim.bridge import protocol
from civsim.config import game_config
from civsim.simulation import Simulation
from civsim.strategy import make_brain

DAYS = 1500  # long enough for wars, sieges and captured castles on a small map


def _breaches(sim) -> list[str]:
    world, found, owners = sim.world, [], {}
    for civ in sim.civs:
        found += [f"{civ.name} has {amount} {name}" for name, amount in civ.resources.items()
                  if not math.isfinite(amount) or amount < -1e-6]
        if not math.isfinite(civ.population) or min(civ.population, civ.soldiers, civ.wounded, civ.horses) < -1e-6:
            found.append(f"{civ.name}: a head count below nothing")
        if not civ.alive:
            if civ.settlements or any(a.size > 0 for a in civ.armies) or any(r.owner == civ.id for r in world.regions):
                found.append(f"{civ.name} has fallen but still holds something")
            continue
        if abs(sum(a.size for a in civ.armies) - civ.soldiers) > 0.01 + 1e-6 * civ.soldiers:
            found.append(f"{civ.name}: its armies do not add up to its soldiers")
        for castle in civ.settlements:
            region = world.regions[world.region_of[castle.tile]]
            if region.owner != civ.id or region.capital != castle.tile or castle.tile not in civ.territory:
                found.append(f"{civ.name}: {castle.name} is not the capital of a region it owns")
        for tile in civ.territory:
            if owners.setdefault(tile, civ.id) != civ.id:
                found.append(f"tile {tile} is owned twice")
        for army in civ.armies:
            if any(n < -1e-6 or not math.isfinite(n) for n in army.units.values()):
                found.append(f"{civ.name}: an army with {army.units}")
            if not world.walkable(army.tile) and not world.is_boat_water(army.tile):
                found.append(f"{civ.name}: an army at {world.xy(army.tile)}, where nothing can be")
            if army.rally is not None and all(r.id != army.rally for r in sim.military.rallies):
                found.append(f"{civ.name}: an army in a rally that is over")
        found += [f"{civ.name}: a villager at {world.xy(v.tile)}, where nothing can be" for v in civ.villagers
                  if not world.walkable(v.tile) and not world.is_boat_water(v.tile)]
        found += [f"{civ.name}: a {b.type} off its own land" for b in civ.buildings if b.tile not in civ.territory]
    for region in world.regions:
        if region.owner is not None and not sim.civs[region.owner].alive:
            found.append(f"{region.name} belongs to a fallen civ")
        if not math.isfinite(region.garrison) or region.garrison < -1e-6:
            found.append(f"{region.name}: a garrison of {region.garrison}")
    return found


def test_a_game_stays_consistent_day_by_day():
    config = game_config("small", 4, seed=11)
    sim, brain = Simulation(config), make_brain("utility")
    wars = 0
    while sim.tick < DAYS and not sim.victory:
        wars += sum("declares war" in e.get("text", "") for e in sim.step_with(brain))
        assert not _breaches(sim), f"day {sim.tick}"
        if sim.tick % 100 == 0:
            text = protocol.tick_message(sim, False, 1.0)
            assert "NaN" not in text and "Infinity" not in text
            json.loads(text)
    assert wars, "the stretch should include a war, or it checks little"
