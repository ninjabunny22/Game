"""Villages and towns, and several buildings to a tile."""

import json

import pytest

from civsim.bridge import protocol
from civsim.civ import VILLAGE_RANGE, Building
from civsim.config import SimConfig
from civsim.economy import advance_construction, manage_villagers
from civsim.economy.buildings import find_site
from civsim.map import BIOME_INFO
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def reach(sim, a, b):
    ax, ay = sim.world.xy(a)
    bx, by = sim.world.xy(b)
    return max(abs(ax - bx), abs(ay - by))


def tile_at(sim, civ, low, high=None):
    """A buildable tile of the civ's whose distance from every capital it holds is in [low, high]."""
    for tile in sorted(civ.territory):
        gaps = [reach(sim, tile, s.tile) for s in civ.settlements]
        if min(gaps) >= low and (high is None or min(gaps) <= high) and BIOME_INFO[sim.world.biomes[tile]].buildable:
            return tile
    raise AssertionError("no such tile")


# -- slots -------------------------------------------------------------------

def test_a_tile_holds_one_building(sim):
    civ = sim.civs[0]
    house, market = sim.building_defs["house"], sim.building_defs["market"]
    first = find_site(civ, sim.world, house)
    assert reach(sim, first, civ.capital.tile) == 2, "right beside the castle, which has its own ground"
    civ.buildings.append(Building("house", first))
    assert find_site(civ, sim.world, house) != first
    assert find_site(civ, sim.world, market) != first, "nothing shares a tile"


def test_sites_beside_what_is_built_are_taken_before_new_ground_is_broken(sim):
    civ = sim.civs[0]
    far = tile_at(sim, civ, 5)
    workshop = sim.building_defs["workshop"]
    assert reach(sim, find_site(civ, sim.world, workshop), civ.capital.tile) == 2
    civ.buildings.append(Building("house", far))
    # Fill the ground beside the castles: the next site is beside the far house.
    for _ in range(200):
        site = find_site(civ, sim.world, workshop)
        if min(reach(sim, site, s.tile) for s in civ.settlements) > 2 and reach(sim, site, far) == 1:
            break
        civ.buildings.append(Building("granary", site))
    else:
        raise AssertionError("never built beside the far house")
    assert all(reach(sim, b.tile, far) <= 1 or any(reach(sim, b.tile, o.tile) <= 1 or
               min(reach(sim, b.tile, s.tile) for s in civ.settlements) <= 2 for o in civ.buildings if o is not b)
               for b in civ.buildings), "the town grew outward from what stood, never off on its own"


def test_buildings_on_one_tile_each_need_their_own_villager(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    mods.build_slots = 3
    tile = civ.capital.tile
    sites = [Building(kind, tile) for kind in ("house", "market", "library")]
    civ.buildings += sites
    civ.population = 30  # two villagers, no more
    del civ.villagers[2:]
    for v in civ.villagers:
        v.tile, v.path = tile, []
    ids = iter(range(900, 999))
    manage_villagers(civ, sim.world, mods, lambda: next(ids))
    assert len(civ.villagers) == 2 and len({b.id for b in sites}) == 3 and all(b.id for b in sites)
    advance_construction(civ, mods, sim.building_defs, [])
    assert [b.progress > 0 for b in sites] == [True, True, False], "one villager builds one building"


def test_capturing_a_tile_takes_everything_on_it(sim):
    a, b = sim.civs[0], sim.civs[1]
    tile = tile_at(sim, b, 2)
    b.buildings += [Building("house", tile, 1.0, True), Building("market", tile, 1.0, True)]
    sim.diplomacy._transfer_tile(tile, a, b, 1, [])
    assert sorted(x.type for x in a.buildings if x.tile == tile) == ["house", "market"]
    assert not [x for x in b.buildings if x.tile == tile]


# -- villages ----------------------------------------------------------------

def test_every_capital_has_a_town_from_the_start(sim):
    for civ in sim.civs:
        towns = sim.villages.of(civ.id)
        assert sorted(v.tile for v in towns) == sorted(s.tile for s in civ.settlements)
        assert all(v.capital for v in towns)
        assert {v.name for v in towns} == {s.name for s in civ.settlements}


def test_a_building_joins_the_nearest_village_within_four_tiles(sim):
    civ = sim.civs[0]
    assert VILLAGE_RANGE == 4
    near = Building("house", tile_at(sim, civ, 1, 4))
    civ.buildings.append(near)
    events: list = []
    sim.villages.update(1, events)
    town = sim.villages.villages[near.village]
    assert town.capital and reach(sim, town.tile, near.tile) <= 4 and not events
    assert reach(sim, town.tile, near.tile) == min(reach(sim, s.tile, near.tile) for s in civ.settlements)


def test_a_building_far_from_any_village_founds_a_new_one(sim):
    civ = sim.civs[0]
    first = Building("farm", tile_at(sim, civ, 5))
    civ.buildings.append(first)
    events: list = []
    sim.villages.update(1, events)
    village = sim.villages.villages[first.village]
    assert not village.capital and village.tile == first.tile and village.civ == civ.id
    assert events == [{"civ": civ.id, "kind": "village", "text": f"{civ.name} founds the village of {village.name}"}]
    assert village.name not in {r.capital_name for r in sim.world.regions}
    # A neighbour joins it rather than founding another.
    beside = next(t for t in sim.world.neighbors(first.tile) if t in civ.territory)
    second = Building("house", beside)
    civ.buildings.append(second)
    sim.villages.update(2, events)
    assert second.village == village.id and len(events) == 1
    assert sim.villages.size(village.id) == 2


def test_a_village_goes_with_its_centre_tile_and_strays_rejoin_their_own_side(sim):
    a, b = sim.civs[0], sim.civs[1]
    centre = tile_at(sim, b, 6)
    beside = next(t for t in sim.world.neighbors(centre) if t in b.territory)
    heart, stray = Building("house", centre, 1.0, True), Building("farm", beside, 1.0, True)
    b.buildings += [heart, stray]
    sim.villages.update(1, [])
    village = sim.villages.villages[heart.village]
    assert stray.village == village.id

    sim.diplomacy._transfer_tile(centre, a, b, 2, [])
    events: list = []
    sim.villages.update(2, events)
    assert village.civ == a.id and heart in a.buildings and heart.village == village.id, "the village is taken whole"
    assert any(f"takes the village of {village.name}" in e["text"] for e in events)
    assert stray in b.buildings and stray.village != village.id, "what its old owner kept is no longer part of it"
    assert sim.villages.villages[stray.village].civ == b.id
    assert len([v for v in sim.villages.villages.values() if v.name == village.name]) == 1, "no splitting"


def test_a_captured_building_joins_the_captors_nearest_village(sim):
    a, b = sim.civs[0], sim.civs[1]
    centre = tile_at(sim, b, 6)
    beside = next(t for t in sim.world.neighbors(centre) if t in b.territory)
    heart, edge = Building("house", centre, 1.0, True), Building("farm", beside, 1.0, True)
    b.buildings += [heart, edge]
    sim.villages.update(1, [])
    village = heart.village
    sim.diplomacy._transfer_tile(beside, a, b, 2, [])  # only the edge falls
    sim.villages.update(2, [])
    assert sim.villages.villages[village].civ == b.id and heart.village == village
    assert edge in a.buildings and sim.villages.villages[edge.village].civ == a.id


def test_an_emptied_village_disappears_but_a_capitals_town_stays(sim):
    civ = sim.civs[0]
    lone = Building("farm", tile_at(sim, civ, 5))
    civ.buildings.append(lone)
    sim.villages.update(1, [])
    village = lone.village
    civ.buildings.remove(lone)
    sim.villages.update(2, [])
    assert village not in sim.villages.villages
    assert len(sim.villages.of(civ.id)) == len(civ.settlements)


def test_protocol_gives_buildings_ids_and_lists_villages(sim):
    civ = sim.civs[0]
    tile = civ.capital.tile
    civ.buildings += [Building("house", tile), Building("market", tile)]
    sim.villages.update(1, [])
    state = json.loads(protocol.tick_message(sim, [], 1.0))["data"]["civs"][0]
    here = [b for b in state["buildings"] if (b["x"], b["y"]) == sim.world.xy(tile)]
    assert len(here) == 2 and here[0]["id"] != here[1]["id"] and here[0]["village"] == here[1]["village"]
    town = next(v for v in state["villages"] if v["id"] == here[0]["village"])
    assert town == {"id": town["id"], "name": civ.capital.name, "x": state["settlements"][0]["x"],
                    "y": state["settlements"][0]["y"], "capital": True, "buildings": 2}


def test_long_games_keep_villages_consistent():
    for seed in (5, 11):
        sim = Simulation(SimConfig(seed=seed))
        brain = RuleBrain()
        for tick in range(1500):
            sim.step_with(brain)
            if tick % 50:
                continue
            villages = sim.villages.villages
            for civ in sim.civs:
                if not civ.alive:
                    continue
                for there in civ.buildings_by_tile().values():
                    assert len(there) == 1
                for b in civ.buildings:
                    assert b.id and villages[b.village].civ == civ.id
            for village in villages.values():
                assert sim.world.owner[village.tile] == village.civ
                assert village.capital or sim.villages.size(village.id) > 0
            names = [v.name for v in villages.values()]
            assert len(names) == len(set(names))
        assert any(not v.capital for v in villages.values()), "villages do form in play"


def test_a_full_town_takes_no_more_and_growth_founds_villages_beside_it(sim):
    from civsim.civ.villages import TOWN_CAP, VILLAGE_CAP
    civ = sim.civs[0]
    assert (TOWN_CAP, VILLAGE_CAP) == (60, 40)
    capital = civ.capital.tile
    near = [t for t in sorted(civ.territory) if reach(sim, t, capital) <= 4
            and min(reach(sim, t, s.tile) for s in civ.settlements) == reach(sim, t, capital)]
    kinds = ("house", "market", "library")
    civ.buildings = [Building(kinds[i % 3], near[i // 3]) for i in range(70)]
    events: list = []
    sim.villages.update(1, events)
    town = next(v for v in sim.villages.of(civ.id) if v.tile == capital)
    assert sim.villages.size(town.id) == TOWN_CAP
    overflow = {b.village for b in civ.buildings} - {town.id}
    assert overflow and all(not sim.villages.villages[v].capital for v in overflow)
    assert sum(sim.villages.size(v) for v in overflow) == 10
    assert any("founds the village" in e["text"] for e in events)
