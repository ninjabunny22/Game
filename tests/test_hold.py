"""A civ's capital does not fall the moment an army breaks in: the army has to hold it for
rules.CAPITAL_HOLD ticks, and the defender can drive it out before then."""

import json

import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.diplomacy import rules
from civsim.military import Army
from civsim.simulation import Simulation


@pytest.fixture
def siege():
    """Civ 0 at war with civ 1, with a huge army standing beside civ 1's capital, its walls already breached."""
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    world, military = sim.world, sim.military
    relation = sim.diplomacy.relation(a.id, b.id)
    sim.diplomacy._start_war(a, b, 0, {a.id})
    target = b.capital.tile
    beside = next(t for t in world.neighbors(target) if not world.is_water(t))
    sim.military._sync(a)
    sim.military._sync(b)
    b.soldiers = 0.0
    for army in b.armies:
        army.units = {}
    army = Army(military.next_id(), a.id, beside, "field", target_civ=b.id, state="marching",
                units={"spearman": 5000.0}, path=[target], siege_progress=1000.0, path_tick=10**9)
    a.armies = [x for x in a.armies if x.role != "field"] + [army]
    a.soldiers += army.size
    region = world.regions[world.capital_tiles[target]]
    return sim, a, b, army, region, relation


def press(sim, a, army, ticks, start=1):
    events = []
    for tick in range(start, start + ticks):
        sim.military._relieve(tick, events)
        if army in a.armies:
            sim.military._besiege(a, army, tick, events)
    return events


def test_a_breached_capital_has_to_be_held_before_it_falls(siege):
    sim, a, b, army, region, _ = siege
    events = press(sim, a, army, rules.CAPITAL_HOLD - 1)
    assert region.owner == b.id and region.held_by == a.id and region.hold == rules.CAPITAL_HOLD - 1
    assert any("breaks into" in e["text"] for e in events)
    sent = json.loads(protocol.tick_message(sim, False, 1.0))["data"]["regions"]
    held = next(r for r in sent if r["id"] == region.id)
    assert held["held_by"] == a.id and 0.9 < held["hold"] < 1.0
    press(sim, a, army, 1, start=rules.CAPITAL_HOLD)
    assert region.owner == a.id and region.held_by is None and region.hold == 0


def test_driving_the_army_off_breaks_the_hold(siege):
    sim, a, b, army, region, _ = siege
    press(sim, a, army, 40)
    assert region.held_by == a.id and region.hold == 40
    army.state = "retreating"  # beaten by a relief
    events = press(sim, a, army, 0) or []
    sim.military._relieve(41, events)
    assert region.owner == b.id and region.held_by is None and region.hold == 0
    assert any("relieves" in e["text"] for e in events)
    # A fresh assault starts the count again from nothing.
    army.state = "marching"
    press(sim, a, army, 5, start=42)
    assert region.held_by == a.id and region.hold == 5


def test_the_defender_marches_to_relieve_a_held_capital(siege):
    sim, a, b, army, region, _ = siege
    press(sim, a, army, 3)
    relief = Army(sim.military.next_id(), b.id, b.capital.tile, "field", target_civ=a.id,
                  units={"spearman": 200.0}, state="idle")
    b.armies.append(relief)
    sim.military._plan(b, relief, 10)
    assert relief.state == "marching"
    assert sim.military._besieger(b, a) is army


def test_peace_lifts_the_hold(siege):
    sim, a, b, army, region, relation = siege
    press(sim, a, army, 10)
    sim.diplomacy._end_war(relation, 20, [], rules.TRUCE, "peace")
    sim.military._relieve(21, [])
    assert region.held_by is None and region.owner == b.id
