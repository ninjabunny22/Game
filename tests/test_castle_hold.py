"""A general near a threatened castle of his own leaves part of his army to hold it."""

import pytest

from civsim.config import SimConfig
from civsim.military import Army
from civsim.military import warfare
from civsim.simulation import Simulation


@pytest.fixture
def setup():
    """Civ 1 at war with civ 0; an army of civ 1 beside civ 0's second capital, and a general
    of civ 0's close by with a large army. Civ 0's garrison is small."""
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    military, world = sim.military, sim.world
    for civ in (a, b):
        military._sync(civ)
    sim.diplomacy._start_war(b, a, 0, {b.id})
    castle = a.settlements[1].tile
    x, y = world.xy(castle)
    a.garrison.units, a.soldiers = {"spearman": 4.0}, 4.0
    general = Army(military.next_id(), a.id, world.idx(x + 3, y), "field", target_civ=b.id,
                   commander=military._appoint(a), state="idle")
    general.add({"spearman": 120.0})
    a.armies.append(general)
    a.soldiers += 120
    a.population = max(a.population, 400.0)
    enemy = Army(military.next_id(), b.id, world.idx(x - 2, y), "field", target_civ=a.id,
                 commander=military._appoint(b), state="marching")
    enemy.add({"spearman": 60.0})
    b.armies.append(enemy)
    b.soldiers += 60
    b.population = max(b.population, 400.0)
    military._tick = 10
    return sim, a, b, castle, general, enemy


def test_a_general_leaves_part_of_his_army_to_hold_a_threatened_castle(setup):
    sim, a, b, castle, general, enemy = setup
    events: list = []
    sim.military._hold_castles(a, 10, events)
    holders = [x for x in a.armies if x.duty == "hold"]
    assert len(holders) == 1, "one force is left behind"
    force = holders[0]
    assert force.post == castle and force.commander is None
    assert warfare.MIN_FIELD_ARMY <= force.size <= warfare.DETACH_MAX * 120 + 1e-6
    assert general.size == pytest.approx(120 - force.size), "the soldiers come out of his army"
    assert sum(x.size for x in a.armies) == pytest.approx(a.soldiers), "nobody is made or lost"
    assert any("to hold" in e["text"] for e in events)
    # It makes for the castle, and counts in its defence and in what the castle panel shows.
    sim.military._plan(a, force, 11)
    assert force.path and force.path[-1] == castle
    force.tile, force.path = castle, []
    assert sim.military._guests(castle) == [force]
    assert sim.military.castle_defenders(a, castle) == pytest.approx(sim.military.castle_garrison(a) + force.size)
    sim.military._hold_castles(a, 12, [])
    assert len([x for x in a.armies if x.duty == "hold"]) == 1, "nor is a second force left while one holds"


def test_the_force_joins_the_garrison_once_the_danger_has_passed(setup):
    sim, a, b, castle, general, enemy = setup
    sim.military._hold_castles(a, 10, [])
    force = next(x for x in a.armies if x.duty == "hold")
    force.tile = castle
    size, garrison = force.size, a.garrison.size
    b.armies.remove(enemy)  # the enemy is gone
    sim.military._hold_castles(a, 10 + warfare.HOLD_STAY - 1, [])
    assert force in a.armies, "it stays a while"
    sim.military._hold_castles(a, 10 + warfare.HOLD_STAY + 1, [])
    assert force not in a.armies
    assert a.garrison.size == pytest.approx(garrison + size)


def test_no_one_is_left_where_the_castle_is_held_well_enough(setup):
    sim, a, b, castle, general, enemy = setup
    a.garrison.units = {"spearman": 400.0}
    a.soldiers += 396
    sim.military._hold_castles(a, 10, [])
    assert not [x for x in a.armies if x.duty == "hold"]
