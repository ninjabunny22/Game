import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.economy.rules import RESOURCES
from civsim.simulation import Simulation


@pytest.fixture(scope="module")
def played() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for _ in range(600):
        sim.step()
    return sim


def test_initial_state():
    sim = Simulation(SimConfig(seed=3))
    assert len(sim.civs) == 4
    assert len({civ.personality.name for civ in sim.civs}) == 4
    for civ in sim.civs:
        regions = [r for r in sim.world.regions if r.owner == civ.id]
        assert len(regions) == 2, "a home region and one more"
        assert [s.tile for s in civ.settlements] == [r.capital for r in regions] or (
            {s.tile for s in civ.settlements} == {r.capital for r in regions})
        assert civ.territory == {t for r in regions for t in r.tiles}, "every tile of both, from the start"
        assert civ.capital.tile in civ.territory
        assert civ.population > 0
        assert all(sim.world.owner[tile] == civ.id for tile in civ.territory)


def test_same_seed_plays_out_identically(played):
    other = Simulation(SimConfig(seed=3))
    for _ in range(600):
        other.step()
    assert protocol.tick_message(played, False, 2.0) == protocol.tick_message(other, False, 2.0)


def test_civs_grow_build_and_expand(played):
    fresh = Simulation(SimConfig(seed=3))
    for civ, start in zip(played.civs, fresh.civs):
        assert civ.population > start.population
        assert len(civ.territory) >= len(start.territory)
        assert any(b.complete for b in civ.buildings)


def test_invariants_hold(played):
    world = played.world
    owned = [tile for civ in played.civs for tile in civ.territory]
    assert len(owned) == len(set(owned)), "territories overlap"
    for civ in played.civs:
        mods = played.modifiers[civ.id]
        tiles = [b.tile for b in civ.buildings] + [s.tile for s in civ.settlements]
        for there in civ.buildings_by_tile().values():
            assert len(there) <= 3, "a tile holds at most three buildings"
            assert len({b.type for b in there}) == len(there), "and never two of the same type"
        ids = [b.id for b in civ.buildings]
        assert 0 not in ids and len(ids) == len(set(ids))
        assert set(tiles) <= civ.territory
        for res in RESOURCES:
            assert 0 <= civ.resources[res] <= mods.storage[res] + 1e-6
            assert civ.workers[res] <= civ.capacity[res] + 1e-6
        # Workers are assigned before the tick's recruitment and growth, hence the slack.
        employed = sum(civ.workers.values()) + civ.idle + civ.soldiers
        assert employed == pytest.approx(civ.population, abs=0.03 * civ.population + 1)
        assert 0 <= civ.soldiers <= civ.population
        assert all(world.owner[tile] == civ.id for tile in civ.territory)


def test_buildings_respect_tech_requirements(played):
    for civ in played.civs:
        for building in civ.buildings:
            required = played.building_defs[building.type].requires_tech
            assert required is None or required in civ.known_techs
