"""Where buildings may stand: the one placement rule, the large buildings that take a whole
tile, and stables kept off every capital's tile whoever is doing the placing."""

import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.economy import EXCLUSIVE, find_site, place, placement_problem
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain
from civsim.survey import survey


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def own_everything(sim, civ):
    """Hand the civ every buildable tile, capitals included."""
    world = sim.world
    for other in sim.civs:
        other.territory = set()
    civ.territory = {t for t in range(world.width * world.height) if not world.is_open_water(t)}
    for tile in civ.territory:
        world.owner[tile] = civ.id


def test_stables_can_never_be_placed_on_a_capitals_tile(sim):
    civ = sim.civs[0]
    world = sim.world
    stables = sim.building_defs["stables"]
    own_everything(sim, civ)
    capitals = set(world.capital_tiles) | {s.tile for c in sim.civs for s in c.settlements}
    assert civ.capital.tile in capitals and len(capitals) > len(sim.civs), "civ and region capitals alike"
    for tile in sorted(capitals):
        assert placement_problem(civ, world, stables, tile) is not None
        with pytest.raises(ValueError):
            place(civ, world, stables, tile)
    assert not civ.buildings, "nothing was placed by the attempts"
    # Other buildings still go on a capital's tile, so it is the stables that are refused.
    assert placement_problem(civ, world, sim.building_defs["house"], civ.capital.tile) is None

    # Even when capitals are the only land the civ has, the site search finds nowhere.
    civ.territory = set(capitals)
    assert find_site(civ, world, stables) is None
    # Nor does clearing a building off a capital's tile make room for one there.
    mods = sim.modifiers[civ.id]
    civ.buildings = [Building("house", tile, 1.0, True) for tile in sorted(capitals)]
    needs = sim.ai.assess_needs(civ, mods)
    assert sim.ai._make_room(civ, mods, stables, 1e9, needs, tick=10_000, events=[]) is None
    assert civ.count("house") == len(capitals), "and nothing was torn down for it"


def test_a_stable_that_was_somehow_on_a_capital_is_not_handed_on_with_the_tile(sim):
    a, b = sim.civs[0], sim.civs[1]
    tile = b.capital.tile
    b.buildings += [Building("stables", tile, 1.0, True), Building("house", tile, 1.0, True)]
    sim.diplomacy._transfer_tile(tile, a, b, 1, [])
    assert [x.type for x in a.buildings if x.tile == tile] == ["house"]
    assert not [x for x in b.buildings if x.tile == tile]


@pytest.mark.parametrize("large", sorted(EXCLUSIVE))
def test_a_harbour_or_stables_has_its_tile_to_itself(sim, large):
    civ = sim.civs[0]
    world = sim.world
    bdef, house = sim.building_defs[large], sim.building_defs["house"]
    civ.buildings = []
    tile = find_site(civ, world, bdef)
    assert tile is not None and tile != civ.capital.tile
    place(civ, world, bdef, tile)
    assert placement_problem(civ, world, house, tile) is not None, "nothing joins it"
    with pytest.raises(ValueError):
        place(civ, world, house, tile)
    assert find_site(civ, world, house) != tile

    civ.buildings = [Building("house", tile)]
    assert placement_problem(civ, world, bdef, tile) is not None, "and it joins nothing"
    assert find_site(civ, world, bdef) != tile
    assert placement_problem(civ, world, bdef, civ.capital.tile) is not None, "nor a capital"


def test_the_builder_only_ever_places_where_the_rule_allows():
    """Whole games: no large building shares a tile or stands on a capital, at any tick."""
    sim = Simulation(SimConfig(seed=7))
    brain = RuleBrain()
    capitals = set(sim.world.capital_tiles)
    seen = 0
    for _ in range(2500):
        sim.step_with(brain)
        if sim.tick % 25:
            continue
        for civ in sim.civs:
            for tile, there in civ.buildings_by_tile().items():
                large = [b for b in there if b.type in EXCLUSIVE]
                seen += len(large)
                assert not large or len(there) == 1, f"{[b.type for b in there]} share tile {tile}"
                assert not large or tile not in capitals
    assert seen, "the game built harbours or stables at all"


def test_the_survey_counts_ships_and_large_buildings():
    result = survey(seed=31337, ticks=2500)
    assert result["army_ticks_afloat"] == result["army_ticks_aboard"], "nothing walks on water"
    assert result["embarkations"] == result["embarkations_from_port"], "every crossing starts near a harbour"
    assert result["large"]["harbour"] + result["large"]["stables"] > 0
    assert result["large"]["sharing_tile"] == 0 and result["large"]["on_capital"] == 0
