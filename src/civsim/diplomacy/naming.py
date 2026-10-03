"""Names for wars and alliances, drawn from the world they happen in.

A war is named for the region being fought over, its capital, the kind of land
it is, or the resource the attacker is short of and that region has. An
alliance is named for a capital or region of its members, or for what they
trade. Names are picked with the simulation's seeded generator, so a seed
always tells the same history.
"""

import random

from ..economy.rules import RESOURCES
from ..map import Biome, WorldMap

RESOURCE_WORDS = {"food": "Harvest", "wood": "Timber", "stone": "Quarry", "ore": "Iron", "gold": "Gold",
                  "water": "Water"}
LAND_WORDS = {Biome.FOREST: "Woods", Biome.HILLS: "Hills", Biome.MOUNTAIN: "Peaks", Biome.PLAINS: "Plains",
              Biome.DESERT: "Sands", Biome.TUNDRA: "Frost", Biome.SHALLOWS: "Coast"}
ORDINALS = ("Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth")


def war_name(world: WorldMap, attacker, defender, rng: random.Random, taken: set[str],
             betrayal: bool = False) -> str:
    """Named for the defender's region nearest the attacker: where the fighting will be."""
    region = _contested_region(world, attacker, defender)
    land = _land_word(world, region)
    prize = _prize(world, attacker, region)
    options = [f"The {region.name} War", f"The War of {region.capital_name}"]
    if land:
        options.append(f"The War of the {region.name} {land}")
    if prize:
        options += [f"The {region.name} {RESOURCE_WORDS[prize]} War", f"The {RESOURCE_WORDS[prize]} War"]
    if betrayal:
        options = [f"The {region.capital_name} Betrayal", f"The Betrayal of {region.name}"]
    return _unique(rng.choice(options), taken)


def alliance_name(world: WorldMap, one, other, traded: str | None, rng: random.Random, taken: set[str]) -> str:
    """Named for a capital or region of the members, as if for where it was sworn."""
    host = rng.choice(sorted((one, other), key=lambda civ: civ.id))
    regions = [r for r in world.regions if r.owner == host.id] or list(world.regions)
    region = rng.choice(regions)
    options = [f"The {region.capital_name} Accord", f"The {region.name} Pact", f"The {region.name} Concord",
               f"The League of {region.capital_name}"]
    if traded:
        options.append(f"The {RESOURCE_WORDS[traded]} Compact")
    return _unique(rng.choice(options), taken)


def _contested_region(world: WorldMap, attacker, defender):
    ax, ay = world.xy(attacker.capital.tile)
    held = [r for r in world.regions if r.owner == defender.id] or list(world.regions)
    return min(held, key=lambda r: (abs(world.xy(r.capital)[0] - ax) + abs(world.xy(r.capital)[1] - ay), r.id))


def _land_word(world: WorldMap, region) -> str | None:
    """What the region mostly is: its commonest kind of land, or its coast if it has a long one."""
    counts: dict[Biome, int] = {}
    for tile in region.tiles:
        counts[world.biomes[tile]] = counts.get(world.biomes[tile], 0) + 1
    if not counts:
        return None
    if counts.get(Biome.SHALLOWS, 0) >= 0.25 * len(region.tiles):
        return LAND_WORDS[Biome.SHALLOWS]
    land = {biome: n for biome, n in counts.items() if biome != Biome.SHALLOWS}
    return LAND_WORDS.get(max(sorted(land), key=lambda b: land[b])) if land else None


def _prize(world: WorldMap, attacker, region) -> str | None:
    """The resource the attacker is shortest of that this region would give it, if any stands out."""
    offered = dict.fromkeys(RESOURCES, 0.0)
    for tile in region.tiles:
        for res, amount in world.yields[tile].items():
            offered[res] += amount
        offered["water"] += world.rivers.get(tile, 0)
    scarce = sorted((res for res in RESOURCES if res != "food"),
                    key=lambda res: (attacker.capacity[res] if res != "water" else attacker.water_access["river"] * 4,
                                     res))
    for res in scarce[:2]:
        if offered[res] >= 20:
            return res
    return None


def _unique(name: str, taken: set[str]) -> str:
    """History repeats: a name already used comes back as 'The Second ... War'."""
    candidate = name
    for ordinal in ORDINALS:
        if candidate not in taken:
            break
        candidate = name.replace("The ", f"The {ordinal} ", 1)
    taken.add(candidate)
    return candidate
