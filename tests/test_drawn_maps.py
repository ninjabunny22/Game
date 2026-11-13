"""The hand-drawn maps: built from their blueprints exactly as drawn, saved, and played on as
saved; and the rules they bring: high peaks, old bridges, native strongholds."""

import random

import pytest

from civsim.config import MAPS, game_config
from civsim.diplomacy.natives import Natives
from civsim.diplomacy import rules
from civsim.map import Biome, WorldMap, find_path
from civsim.map.blueprint import build, check, walking_links
from civsim.map.designs import DESIGNS, blueprint
from civsim.map.regions import Region
from civsim.map.saved import from_data, load_map, to_data
from civsim.simulation import Simulation

DRAWN = [(size, m["id"]) for size, pool in MAPS.items() for m in pool if m.get("file")]


def test_every_listed_drawn_map_has_a_design_that_agrees_with_its_entry():
    assert {map_id for _, map_id in DRAWN} <= set(DESIGNS)
    for size, pool in MAPS.items():
        for entry in pool:
            if entry.get("file"):
                bp = blueprint(entry["id"])
                assert (bp.width, bp.height, bp.civs, bp.name) == (entry["width"], entry["height"],
                                                                   tuple(entry["civs"]), entry["name"])
                assert entry["premise"] == bp.premise and entry["best"] == bp.best


@pytest.mark.parametrize("map_id", DESIGNS)
def test_a_drawn_map_keeps_to_its_drawing_and_is_saved_as_built(map_id):
    bp = blueprint(map_id)
    world = build(bp)
    assert check(world, bp) == []
    assert to_data(world) == to_data(load_map(map_id)), "the saved map is out of date: bake it again"
    assert to_data(from_data(to_data(world))) == to_data(world)


@pytest.mark.parametrize("size, map_id", DRAWN)
def test_each_number_of_civs_starts_on_its_slots(size, map_id):
    world = load_map(map_id)
    for count, options in world.start_sets.items():
        sim = Simulation(game_config(size, count, seed=3, map=map_id))
        held = {frozenset(r.id for r in sim.world.regions if r.owner == civ.id) for civ in sim.civs}
        slots = next(s for s in options if held == {frozenset(world.starts[slot]) for slot in s})
        for civ in sim.civs:
            assert sim.world.region_of[civ.capital.tile] == next(
                world.starts[s][0] for s in slots if sim.world.region_of[civ.capital.tile] in world.starts[s])


@pytest.mark.parametrize("size, map_id", DRAWN)
def test_which_civ_takes_which_slot_differs_from_game_to_game(size, map_id):
    count = max(load_map(map_id).start_sets)
    homes = {tuple(civ.capital.tile for civ in Simulation(game_config(size, count, seed=s, map=map_id)).civs)
             for s in range(6)}
    assert len(homes) > 1


def _strip(width=9, height=5) -> WorldMap:
    world = WorldMap(width, height, 0)
    world.biomes = [Biome.PLAINS] * (width * height)
    return world


def test_high_peaks_cannot_be_crossed_or_claimed():
    world = _strip()
    for y in range(world.height):
        world.biomes[world.idx(4, y)] = Biome.PEAKS
    a, b = world.idx(0, 2), world.idx(8, 2)
    assert world.crossing_cost(world.idx(4, 2), bridges=True, boats=True) is None
    assert not world.claimable(world.idx(4, 2))
    assert find_path(world, a, b, bridges=True, boats=True) is None
    world.biomes[world.idx(4, 2)] = Biome.HILLS  # a pass
    assert find_path(world, a, b, bridges=True, boats=True) is not None


def test_an_old_bridge_crosses_a_river_at_the_plain_cost():
    world = _strip()
    river = world.idx(4, 2)
    world.rivers[river] = 2
    assert world.crossing_cost(river, bridges=False, boats=False) > 1.0
    world.bridges.add(river)
    assert world.crossing_cost(river, bridges=False, boats=False) == 1.0


def test_a_stronghold_keeps_a_bigger_garrison():
    world = _strip()
    plain = Region(0, "Plain", "Plainsby", world.idx(1, 2), [world.idx(x, y) for x in range(4) for y in range(5)])
    fort = Region(1, "Fort", "Fortby", world.idx(7, 2), [world.idx(x, y) for x in range(4, 9) for y in range(5)],
                  strength=2.0, defects=False)
    world.regions = [plain, fort]
    world.capital_tiles = {plain.capital: 0, fort.capital: 1}
    natives = Natives(world, [], None, random.Random(1))
    assert fort.garrison == 2 * plain.garrison == 2 * rules.NATIVE_GARRISON
    assert natives.garrison_size(1000, fort) == pytest.approx(2 * natives.garrison_size(1000))



@pytest.mark.parametrize("map_id", DESIGNS)
def test_no_two_regions_touch_unless_drawn_so(map_id):
    world = load_map(map_id)
    drawn = {(min(a, b), max(a, b)) for a, b, kind in world.links if not kind.startswith("sea:")}
    assert walking_links(world) == drawn
