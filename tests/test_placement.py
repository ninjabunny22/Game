"""Where buildings may stand: the one placement rule, each building on its own square of
tiles, castles on theirs, and stables kept off every capital's tile whoever is placing."""

import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.economy import castle_ground, find_site, footprint, place, placement_problem
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
    b.buildings += [Building("stables", tile, 1.0, True)]
    sim.diplomacy._transfer_tile(tile, a, b, 1, [])
    assert not [x for x in a.buildings if x.tile == tile]
    assert not [x for x in b.buildings if x.tile == tile]


@pytest.mark.parametrize("kind, side", [("house", 1), ("farm", 2), ("stables", 2), ("harbour", 2), ("fortress", 3)])
def test_a_building_stands_on_its_own_square_of_tiles(sim, kind, side):
    civ = sim.civs[0]
    world = sim.world
    bdef, house = sim.building_defs[kind], sim.building_defs["house"]
    assert bdef.size == side
    civ.buildings = []
    tile = find_site(civ, world, bdef)
    assert tile is not None
    ground = footprint(world, kind, tile)
    assert len(set(ground)) == side * side and tile in ground
    place(civ, world, bdef, tile)
    for part in ground:
        assert placement_problem(civ, world, house, part) is not None, "one building to a tile"
        with pytest.raises(ValueError):
            place(civ, world, house, part)
    assert find_site(civ, world, house) not in ground
    # Nor may a larger building's square reach onto ground that is taken.
    for big in ("farm", "fortress"):
        site = find_site(civ, world, sim.building_defs[big])
        assert site is not None and not set(footprint(world, big, site)) & set(ground)


def test_nothing_is_built_where_a_castle_stands(sim):
    civ = sim.civs[0]
    world = sim.world
    house = sim.building_defs["house"]
    capital = civ.capital.tile
    for tile in [capital, *world.neighbors(capital, diagonal=True)]:
        assert castle_ground(world, tile)
        assert placement_problem(civ, world, house, tile) is not None
    civ.buildings = []
    for _ in range(30):
        place(civ, world, house, find_site(civ, world, house))
    assert not any(castle_ground(world, b.tile) for b in civ.buildings)


def test_the_builder_only_ever_places_where_the_rule_allows():
    """Whole games: no two buildings share a tile and none stands on a castle's ground, at any tick."""
    sim = Simulation(SimConfig(seed=7))
    brain = RuleBrain()
    world = sim.world
    seen = 0
    for _ in range(2500):
        sim.step_with(brain)
        if sim.tick % 25:
            continue
        under: set[int] = set()
        for civ in sim.civs:
            for building in civ.buildings:
                ground = footprint(world, building.type, building.tile)
                seen += len(ground) > 1
                assert not under & set(ground), f"{building.type} at {building.tile} stands on taken ground"
                assert not any(castle_ground(world, part) for part in ground)
                under |= set(ground)
    assert seen, "the game built larger buildings at all"


def test_the_survey_counts_ships_and_footprints():
    result = survey(seed=31337, ticks=2500)
    assert result["army_ticks_afloat"] == result["army_ticks_aboard"], "nothing walks on water"
    assert result["embarkations"] == result["embarkations_from_port"], "every crossing starts near a harbour"
    assert result["large"]["multi_tile"] > 0
    assert result["large"]["overlapping_tiles"] == 0 and result["large"]["on_castle_ground"] == 0
