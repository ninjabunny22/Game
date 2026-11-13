"""Who can go where: no one walks on water, shallow or deep, but over a bridge; mountains are
crossed only through passes, slowly; and a villager with no way to a place does not go."""

from civsim.config import SimConfig
from civsim.map import Biome, WorldMap, find_path
from civsim.map.passes import carve_passes
from civsim.map.pathfinding import PASS_COST, step_cost
from civsim.simulation import Simulation


def _strip(middle: Biome, width=9, height=5) -> tuple[WorldMap, int, int]:
    """Plains, with a column of `middle` down the centre."""
    world = WorldMap(width, height, 0)
    world.biomes = [Biome.PLAINS] * (width * height)
    for y in range(height):
        world.biomes[world.idx(width // 2, y)] = middle
    return world, world.idx(0, 2), world.idx(width - 1, 2)


def test_shallow_water_is_crossed_by_boat_or_by_bridge_only():
    world, a, b = _strip(Biome.SHALLOWS)
    assert find_path(world, a, b) is None
    assert find_path(world, a, b, boats=True) is not None
    world.bridges.add(world.idx(4, 2))
    path = find_path(world, a, b)
    assert path is not None and world.idx(4, 2) in path, "over the bridge"


def test_mountains_are_crossed_only_through_a_pass_and_slowly():
    world, a, b = _strip(Biome.MOUNTAIN)
    assert find_path(world, a, b, bridges=True, boats=True) is None
    gap = world.idx(4, 3)
    world.passes.add(gap)
    path = find_path(world, a, b)
    assert gap in path
    assert step_cost(world, gap, False, False) == PASS_COST > step_cost(world, world.idx(1, 1), False, False)
    world.biomes[world.idx(4, 0)] = Biome.HILLS
    assert world.walkable(world.idx(4, 0)), "hills are walked"


def test_passes_are_carved_wherever_mountains_alone_would_part_the_land():
    world, a, b = _strip(Biome.MOUNTAIN)
    carve_passes(world)
    assert len(world.passes) == 1 and find_path(world, a, b) is not None
    world2, _, _ = _strip(Biome.OCEAN)
    carve_passes(world2)
    assert not world2.passes, "the sea is not mountains: nothing to carve"




def test_a_villager_with_no_way_there_stays_and_leaves_the_place_alone():
    from civsim.economy import villagers as vmod
    sim = Simulation(SimConfig(seed=4))
    world, civ = sim.world, sim.civs[0]
    mods = sim.modifiers[civ.id]
    villager = civ.villagers[0]
    sea = next(i for i, b in enumerate(world.biomes) if b == Biome.OCEAN)
    target = next(n for n in world.neighbors(sea) if world.is_open_water(n))  # out at sea
    mods.boats = 0
    before = (villager.task, villager.tile, list(villager.path))
    assert vmod._send(civ, villager, world, mods, "gather", target) is False
    assert (villager.task, villager.tile, villager.path) == before
    assert civ.out_of_reach[target] == vmod.OUT_OF_REACH


def test_in_play_nobody_stands_on_water_or_mountains_but_afloat_or_on_a_bridge():
    sim = Simulation(SimConfig(seed=9))
    from civsim.strategy import make_brain
    brain = make_brain("rules")
    world = sim.world
    for _ in range(400):
        sim.step_with(brain)
        for civ in sim.civs:
            for villager in civ.villagers:
                tile = villager.tile
                assert world.walkable(tile) or world.is_boat_water(tile), f"villager on {world.biomes[tile]}"
            for army in civ.armies:
                tile = army.tile
                assert world.walkable(tile) or world.is_boat_water(tile) or tile in world.capital_tiles


def test_routes_go_eight_ways_and_a_slant_is_no_longer_than_straight_across():
    world = WorldMap(11, 11, 0)
    world.biomes = [Biome.PLAINS] * 121
    centre = world.idx(5, 5)
    straight = find_path(world, centre, world.idx(5, 0))
    slant = find_path(world, centre, world.idx(9, 1))
    assert len(straight) == 5 and len(slant) == 4, "diagonal steps"
    # Never through the corner between two tiles that cannot be entered.
    world.biomes[world.idx(5, 4)] = world.biomes[world.idx(6, 5)] = Biome.PEAKS
    path = find_path(world, centre, world.idx(6, 4))
    assert path and len(path) > 1
