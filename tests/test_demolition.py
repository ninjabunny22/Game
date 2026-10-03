import pytest

from civsim.civ import Building
from civsim.civ.ai import ABANDON_AFTER, DEMOLITION_COOLDOWN
from civsim.config import SimConfig
from civsim.economy import demolish, find_site
from civsim.economy.buildings import DEMOLITION_REFUND
from civsim.map import BIOME_INFO
from civsim.simulation import Simulation


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def buildable_tiles(sim, civ):
    return [t for t in sorted(civ.territory)
            if t != civ.capital.tile and BIOME_INFO[sim.world.biomes[t]].buildable]


def test_demolishing_frees_the_tile_and_refunds_part_of_the_cost(sim):
    civ = sim.civs[0]
    tile = buildable_tiles(sim, civ)[0]
    library = Building("library", tile, 1.0, True)
    civ.buildings.append(library)
    civ.resources.update(wood=0, stone=0)
    assert tile in civ.occupied()

    events: list = []
    demolish(civ, library, sim.building_defs, events)
    cost = sim.building_defs["library"].cost
    assert library not in civ.buildings and tile not in civ.occupied()
    assert civ.resources["wood"] == pytest.approx(DEMOLITION_REFUND * cost["wood"])
    assert civ.resources["stone"] == pytest.approx(DEMOLITION_REFUND * cost["stone"])
    assert events == [{"civ": civ.id, "kind": "demolition", "text": f"{civ.name} demolished a Library"}]


def test_unfinished_buildings_refund_in_proportion_to_progress(sim):
    civ = sim.civs[0]
    half_built = Building("library", buildable_tiles(sim, civ)[0], 0.5, False)
    civ.buildings.append(half_built)
    civ.resources["wood"] = 0
    demolish(civ, half_built, sim.building_defs, [])
    assert civ.resources["wood"] == pytest.approx(0.5 * DEMOLITION_REFUND * sim.building_defs["library"].cost["wood"])


def test_buildings_the_civ_cannot_keep_up_are_eventually_torn_down(sim):
    civ = sim.civs[0]
    tiles = buildable_tiles(sim, civ)
    civ.buildings += [Building("university", tiles[0], 1.0, True), Building("university", tiles[1], 1.0, True)]
    events: list = []
    for tick in range(1, ABANDON_AFTER + DEMOLITION_COOLDOWN + 5):
        civ.resources["gold"] = 0  # never enough for their upkeep
        for building in civ.buildings:
            building.unpaid_ticks += 1
        sim.ai._abandon_unaffordable(civ, tick, events)
        if tick == ABANDON_AFTER - 2:
            assert civ.count("university") == 2, "not before it has been unpaid for a long while"
        if tick == ABANDON_AFTER + 2:
            assert civ.count("university") == 1, "one at a time"
    assert civ.count("university") == 0
    assert [e["kind"] for e in events] == ["demolition", "demolition"]


def test_a_full_territory_gives_up_its_least_useful_building_for_a_much_better_one(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.known_techs = ["pottery"]
    # Fill every buildable tile with lumber camps, then make housing the pressing need.
    civ.buildings = [Building("lumber_camp", t, 1.0, True) for t in buildable_tiles(sim, civ)]
    house = sim.building_defs["house"]
    assert find_site(civ, sim.world, house) is None
    civ.population = mods.housing
    civ.resources.update(wood=mods.storage["wood"], food=200)
    camps = civ.count("lumber_camp")

    events: list = []
    needs = sim.ai.assess_needs(civ, mods)
    sim.ai._choose_project(civ, mods, needs, tick=100, events=events)
    assert civ.count("lumber_camp") == camps - 1
    assert civ.count("house") == 1, "the house goes up on the freed tile"
    assert any(e["kind"] == "demolition" for e in events)
    tiles = [b.tile for b in civ.buildings]
    assert len(tiles) == len(set(tiles))

    # Not again until the cooldown has passed.
    civ.buildings[-1].complete = True
    sim.ai._choose_project(civ, mods, sim.ai.assess_needs(civ, mods), tick=101, events=events)
    assert civ.count("lumber_camp") == camps - 1


def test_nothing_is_demolished_for_a_marginal_gain(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.buildings = [Building("house", t, 1.0, True) for t in buildable_tiles(sim, civ)]
    needs = sim.ai.assess_needs(civ, mods)
    house, farm = sim.building_defs["house"], sim.building_defs["farm"]
    last_house = sim.ai._building_score(civ, house, needs, civ.count("house") - 1)
    assert last_house > 0
    before = len(civ.buildings)

    events: list = []
    assert sim.ai._make_room(civ, farm, 1.5 * last_house, needs, tick=100, events=events) is None
    assert len(civ.buildings) == before and not events

    freed = sim.ai._make_room(civ, farm, 2.5 * last_house, needs, tick=100, events=events)
    assert freed is not None and freed not in civ.occupied()
    assert sim.world.yields[freed].get("food", 0) > 0, "the freed tile suits the new building"
    assert len(civ.buildings) == before - 1
