from collections import Counter

import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance
from civsim.economy import compute_modifiers, produce, recompute_capacity
from civsim.economy.rules import (
    BASE_STORAGE, LAKE_WATER, MIN_POPULATION, RESOURCES, RIVER_WATER, WATER_PER_POP, WELL_WATER,
)
from civsim.map import BIOME_INFO, BOAT_RANGE, Biome, find_path, generate_map, step_cost
from civsim.map.water import MAX_LAKE_TILES, MAX_RIVER_SIZE
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:  # plenty of influence, so tests are about the rule in question
        civ.diplomacy_points = 300.0
    return sim


def lakes_of(world) -> list[set[int]]:
    """Connected groups of lake tiles."""
    seen: set[int] = set()
    lakes = []
    for start, biome in enumerate(world.biomes):
        if biome != Biome.LAKE or start in seen:
            continue
        lake = {start}
        stack = [start]
        while stack:
            for n in world.neighbors(stack.pop()):
                if world.biomes[n] == Biome.LAKE and n not in lake:
                    lake.add(n)
                    stack.append(n)
        seen |= lake
        lakes.append(lake)
    return lakes


# -- map ---------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3, 5, 42])
def test_lakes_are_inland_and_capped_in_size(seed):
    world = generate_map(seed)
    lakes = lakes_of(world)
    assert lakes
    assert all(len(lake) <= MAX_LAKE_TILES for lake in lakes)
    assert sum(len(lake) for lake in lakes) < 0.03 * len(world.biomes), "lakes never dominate the map"
    for lake in lakes:
        for tile in lake:
            assert not any(world.biomes[n] in (Biome.OCEAN, Biome.SHALLOWS) for n in world.neighbors(tile, diagonal=True))
        assert len({world.heights[t] for t in lake}) == 1, "a lake surface is flat"


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 42])
def test_rivers_run_over_land_from_high_ground_to_water(seed):
    world = generate_map(seed)
    assert world.rivers
    assert all(not world.is_water(tile) for tile in world.rivers), "rivers are a feature of land tiles"
    assert set(world.rivers.values()) <= set(range(1, MAX_RIVER_SIZE + 1))
    # Every river tile continues to another river tile or reaches water.
    for tile in world.rivers:
        assert any(n in world.rivers or world.is_water(n) for n in world.neighbors(tile))
    mouths = [t for t in world.rivers if any(world.is_water(n) for n in world.neighbors(t))]
    assert mouths, "rivers reach the sea or a lake"


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 7, 11, 42])
def test_every_river_is_one_clean_course_to_water(seed):
    world = generate_map(seed)
    assert set(world.river_flow) == set(world.rivers), "every river tile says where its water goes"
    for tile, into in world.river_flow.items():
        assert into in set(world.neighbors(tile)), "to a tile right beside it"
        assert world.is_water(into) or into in world.rivers
    # Following the flow from anywhere reaches the sea or a lake, without ever looping.
    for start in world.rivers:
        seen = set()
        tile = start
        while tile in world.rivers:
            assert tile not in seen, "a river never runs in a circle"
            seen.add(tile)
            tile = world.river_flow[tile]
        assert world.is_water(tile)
    # Width never shrinks on the way down.
    for tile, into in world.river_flow.items():
        if into in world.rivers:
            assert world.rivers[into] >= world.rivers[tile]


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 7, 11, 42])
def test_a_river_does_not_coil_back_against_itself(seed):
    """The knot seen in the viewer: a river touching its own earlier course."""
    world = generate_map(seed)
    upstream: dict[int, list[int]] = {}
    for tile, into in world.river_flow.items():
        upstream.setdefault(into, []).append(tile)
    touching = 0
    for tile in world.rivers:
        linked = set(upstream.get(tile, [])) | {world.river_flow[tile]}
        # River tiles right beside this one that are neither upstream nor downstream of it.
        strangers = [n for n in world.neighbors(tile) if n in world.rivers and n not in linked]
        touching += len(strangers)
    assert touching <= 0.06 * len(world.rivers), "rivers rarely even brush past each other"


def test_the_viewer_is_told_the_flow(sim):
    import json
    from civsim.bridge import protocol
    rivers = json.loads(protocol.init_message(sim))["data"]["map"]["rivers"]
    assert len(rivers) == len(sim.world.rivers)
    for river in rivers:
        tile = sim.world.idx(river["x"], river["y"])
        assert sim.world.idx(*river["to"]) == sim.world.river_flow[tile]


def test_water_features_follow_the_seed():
    a, b, c = generate_map(11), generate_map(11), generate_map(12)
    assert a.rivers == b.rivers and a.biomes == b.biomes
    assert a.rivers != c.rivers
    counts = {seed: (len(generate_map(seed).rivers), Counter(generate_map(seed).biomes)[Biome.LAKE]) for seed in (1, 2, 3)}
    assert len(set(counts.values())) > 1, "river length and lake count vary from seed to seed"


def test_rivers_make_farmland_more_fertile():
    world = generate_map(5)
    tile = next(t for t in world.rivers if world.biomes[t] == Biome.PLAINS and t not in world.deposits)
    assert world.yields[tile]["food"] == BIOME_INFO[Biome.PLAINS].yields["food"] + 1


# -- water as a resource ------------------------------------------------------

def test_every_civ_starts_with_full_water(sim):
    assert "water" in RESOURCES
    for civ in sim.civs:
        assert civ.resources["water"] == sim.modifiers[civ.id].storage["water"] >= BASE_STORAGE


def test_supply_and_cap_follow_access(sim):
    civ = sim.civs[0]
    world = sim.world
    civ.water_access = {"river": 0, "lake": 0, "coast": 0}
    dry = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    assert dry.income["water"] == pytest.approx(WELL_WATER), "only the capital's well"
    assert dry.storage["water"] == BASE_STORAGE

    civ.water_access = {"river": 10, "lake": 4, "coast": 6}
    wet = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    assert wet.income["water"] == pytest.approx(WELL_WATER + 10 * RIVER_WATER + 4 * LAKE_WATER)
    assert wet.storage["water"] == BASE_STORAGE + 10 * 14, "coast counts for nothing without purification"

    civ.known_techs = ["pottery", "water_purification"]
    pure = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    assert pure.income["water"] == pytest.approx(wet.income["water"] + 6 * 0.15)
    assert pure.storage["water"] == BASE_STORAGE + 100 + 10 * 20

    # Access is read off the map: river tiles owned, lake tiles on the shore, coast tiles owned.
    river = next(iter(world.rivers))
    civ.territory.add(river)
    recompute_capacity(civ, world)
    assert civ.water_access["river"] >= world.rivers[river]


def test_people_and_farms_drink(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.population = 100
    civ.resources.update(water=200, food=250, wood=250)
    civ.buildings = []
    produce(civ, mods, sim.building_defs)
    people_only = civ.upkeep["water"]
    assert people_only == pytest.approx(WATER_PER_POP * 100)

    tile = next(t for t in sorted(civ.territory) if t != civ.capital.tile and BIOME_INFO[sim.world.biomes[t]].buildable)
    civ.buildings = [Building("farm", tile, 1.0, True)]
    produce(civ, mods, sim.building_defs)
    assert civ.upkeep["water"] > people_only, "irrigation draws on it too"
    assert sim.building_defs["farm"].upkeep["water"] > 0
    assert all("water" in sim.building_defs[b].upkeep for b in ("farm", "mine", "quarry", "workshop"))
    assert "water" not in sim.building_defs["house"].upkeep


def test_running_dry_shrinks_the_population_slowly_and_stops_farms(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    mods.income["water"] = 0.0
    civ.population = 200
    civ.resources.update(water=0, food=250, wood=250)
    tile = next(t for t in sorted(civ.territory) if t != civ.capital.tile and BIOME_INFO[sim.world.biomes[t]].buildable)
    civ.buildings = [Building("farm", tile, 1.0, True)]

    produce(civ, mods, sim.building_defs)
    assert civ.thirsty and not civ.buildings[0].active
    one_tick = 200 - civ.population
    assert 0 < one_tick < 2, "a slow decline, not a collapse"
    for _ in range(99):
        civ.resources.update(food=250, wood=250)
        produce(civ, mods, sim.building_defs)
    assert 100 < civ.population < 180, "after 100 dry ticks most people are still there"
    assert civ.population >= MIN_POPULATION

    # Partial supply hurts proportionally less.
    civ.population = 200
    civ.resources["water"] = 0.5 * WATER_PER_POP * 200
    civ.buildings = []
    produce(civ, mods, sim.building_defs)
    assert 0 < 200 - civ.population < one_tick


def test_a_watered_population_does_not_shrink(sim):
    civ = sim.civs[0]
    civ.population = 25
    civ.resources.update(water=250, food=250, wood=250)
    produce(civ, sim.modifiers[civ.id], sim.building_defs)
    assert not civ.thirsty and civ.population >= 25


def test_a_thirsty_civ_expands_toward_water(sim):
    civ = sim.civs[0]
    world = sim.world
    mods = sim.modifiers[civ.id]
    civ.water_access = {"river": 0, "lake": 0, "coast": 0}
    civ.upkeep["water"] = 5.0  # using far more than the well gives
    needs = sim.ai.assess_needs(civ, compute_modifiers(civ, sim.building_defs, sim.tech_tree))
    assert needs["wanted"][0] == "water"

    civ.resources.update(food=250, wood=250)
    before = civ.water_access["river"] + civ.water_access["lake"]
    for _ in range(12):
        civ.upkeep["water"] = 5.0
        needs = sim.ai.assess_needs(civ, mods)
        border = sim.ai._border(civ, mods)
        sim.ai._expand(civ, mods, border, needs)
    assert civ.water_access["river"] + civ.water_access["lake"] > before
    assert all(world.owner[t] == civ.id for t in civ.territory)


def test_water_can_be_traded(sim):
    wet, dry = sim.civs[0], sim.civs[1]
    wet.resources.update(water=250, gold=50, stone=0)
    dry.resources.update(water=0, gold=50, stone=200)
    sim.diplomacy.set_intents(wet.id, {dry.id: Intent(Stance.TRADE, give="water", give_rate=1.0)})
    sim.diplomacy.set_intents(dry.id, {wet.id: Intent(Stance.TRADE, give="stone", give_rate=1.0)})
    sim.diplomacy.update(1, [])
    deal = sim.diplomacy.deal_between(wet.id, dry.id)
    assert deal and "water" in (deal.a_gives[0], deal.b_gives[0])
    assert dry.resources["water"] == pytest.approx(1.0)


# -- techs and crossing -------------------------------------------------------

def test_the_three_water_techs_are_in_the_bronze_age_and_open_to_everyone(sim):
    tree = sim.tech_tree
    for tech_id, effect in (("water_purification", "purification"), ("bridge_building", "bridges"), ("boatbuilding", "boats")):
        tech = tree.techs[tech_id]
        assert tech.era == 1 and effect in tech.effects
        peers = [t.science_cost for t in tree.techs.values() if t.era == 1]
        assert min(peers) <= tech.science_cost <= max(peers)
        assert all(tree.techs[p].era <= 1 for p in tech.prereqs)


def test_crossing_rule(sim):
    world = sim.world
    river = next(iter(world.rivers))
    lake = next(i for i, b in enumerate(world.biomes) if b == Biome.LAKE)
    sea = next(i for i, b in enumerate(world.biomes) if b == Biome.OCEAN)
    land = next(i for i, b in enumerate(world.biomes) if b == Biome.PLAINS and i not in world.rivers)
    shallows = next(i for i, b in enumerate(world.biomes) if b == Biome.SHALLOWS)
    assert world.crossing_cost(land, False, False) == world.crossing_cost(shallows, False, False) == 1
    assert world.crossing_cost(river, bridges=False, boats=False) == 3
    assert world.crossing_cost(river, bridges=True, boats=False) == 1
    for water in (lake, sea):
        assert world.crossing_cost(water, bridges=True, boats=False) is None
        assert world.crossing_cost(water, bridges=True, boats=True) == 1


def test_rivers_slow_expansion_until_bridges(sim):
    civ = sim.civs[0]
    world = sim.world
    mods = sim.modifiers[civ.id]
    river_tiles = [t for t in sorted(world.rivers) if world.owner[t] < 0 and t not in world.capital_tiles][:6]
    needs = sim.ai.assess_needs(civ, mods)

    def claimed_from(border, bridges):
        mods.bridges = bridges
        before = set(civ.territory)
        sim.ai._expand(civ, mods, list(border), needs)
        new = civ.territory - before
        for tile in new:  # undo
            civ.territory.discard(tile)
            world.owner[tile] = -1
        return len(new)

    free = [t for t in river_tiles if world.owner[t] < 0]
    assert claimed_from(free, bridges=0) == 1, "fording one river tile uses most of an expansion"
    assert claimed_from(free, bridges=1) == 4


def test_open_water_blocks_expansion_until_boats(sim):
    civ = sim.civs[0]
    world = sim.world
    mods = sim.modifiers[civ.id]
    without = set(sim.ai._border(civ, mods))
    assert all(not world.is_open_water(t) for t in without), "lakes and deep sea are never claimed"

    # Put the civ on a shore and look across.
    shore = next(t for t in range(len(world.biomes)) if world.owner[t] < 0 and not world.is_water(t)
                 and any(world.is_open_water(n) for n in world.neighbors(t)))
    world.claim(shore, civ.id)
    civ.territory.add(shore)
    near = set(sim.ai._border(civ, mods))
    mods.boats = 1
    far = set(sim.ai._border(civ, mods))
    assert near <= far and len(far) > len(near), "boats reach land across the water"
    for tile in far - near:
        assert not world.is_open_water(tile) and world.owner[tile] < 0
    x0, y0 = world.xy(shore)
    assert any(abs(world.xy(t)[0] - x0) + abs(world.xy(t)[1] - y0) > 1 for t in far - near)
    assert BOAT_RANGE == 6


def test_war_across_open_water_needs_boats(sim):
    a, b = sim.civs[0], sim.civs[1]
    world = sim.world
    # Rebuild both civs as two shores facing each other across a strip of deep sea.
    width = world.width
    row = 40 * width
    for x in range(20, 30):
        world.biomes[row + x] = Biome.PLAINS if x in (20, 21, 28, 29) else Biome.OCEAN
        world.owner[row + x] = -1
    for civ, tiles in ((a, (row + 20, row + 21)), (b, (row + 28, row + 29))):
        for tile in civ.territory:
            world.owner[tile] = -1
        civ.territory = set(tiles)
        civ.settlements[0].tile = tiles[0] if civ is a else tiles[1]
        for tile in tiles:
            world.owner[tile] = civ.id
    for y in (39, 41):  # no way round
        for x in range(19, 31):
            world.biomes[y * width + x] = Biome.OCEAN
            world.owner[y * width + x] = -1

    assert not sim.diplomacy._nearest_tiles(a, b), "six tiles of deep sea: out of reach"
    sim.modifiers[a.id].boats = 1
    assert not sim.diplomacy._nearest_tiles(a, b), "boats with no harbour to sail from cross nothing"
    a.buildings.append(Building("harbour", row + 21, 1.0, True))
    assert sim.diplomacy._nearest_tiles(a, b) == [row + 28]
    assert not sim.diplomacy._nearest_tiles(b, a), "the side without boats still cannot cross"
    # An army goes the same way: by ship from the harbour, or not at all.
    assert sim.military._route(a, row + 20, row + 28) == [row + x for x in range(21, 29)]
    a.buildings[-1].active = False
    assert sim.military._route(a, row + 20, row + 28) is None


def test_rivers_are_harder_to_capture_without_bridges(sim):
    attacker, defender = sim.civs[0], sim.civs[1]
    world = sim.world
    tile = next(t for t in sorted(defender.territory) if t not in world.rivers)
    plain = sim.military.tile_price(attacker, tile)
    world.rivers[tile] = 1
    assert sim.military.tile_price(attacker, tile) == 3 * plain, "a river is a defensive line"
    sim.modifiers[attacker.id].bridges = 1
    assert sim.military.tile_price(attacker, tile) == plain, "until the attacker can bridge it"


def test_armies_route_around_water_or_across_it_with_boats(sim):
    world = sim.world
    lake = next(i for i, b in enumerate(world.biomes) if b == Biome.LAKE)
    shore = [n for n in world.neighbors(lake) if not world.is_water(n)]
    start = shore[0]
    across = find_path(world, start, lake, boats=False)
    assert across is None, "a lake cannot be entered without boats"
    assert find_path(world, start, lake, boats=True) == [lake]
    river = next(t for t in world.rivers if any(not world.is_water(n) and n not in world.rivers
                                                for n in world.neighbors(t)))
    bank = next(n for n in world.neighbors(river) if not world.is_water(n) and n not in world.rivers)
    assert step_cost(world, river, bridges=False, boats=False) == 3 * step_cost(world, river, bridges=True, boats=False)
    assert find_path(world, bank, river) == [river]


def test_long_run_water_stays_consistent():
    sim = Simulation(SimConfig(seed=7))
    brain = RuleBrain()
    for _ in range(1500):
        sim.step_with(brain)
    for civ in sim.civs:
        assert civ.resources["water"] >= 0
        assert civ.population >= MIN_POPULATION
        assert not any(sim.world.is_open_water(t) for t in civ.territory)
    assert any(sim.modifiers[c.id].purification > 0 for c in sim.civs)
