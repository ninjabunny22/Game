"""A castle breached is a castle taken: the day an army breaks into an enemy castle, the castle
and its whole region are its (rules.CAPITAL_HOLD is 0); nothing is held for days first."""

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
    return sim, a, b, army, region


def test_a_breached_castle_falls_the_same_day(siege):
    sim, a, b, army, region = siege
    assert rules.CAPITAL_HOLD == 0
    events = []
    sim.military._besiege(a, army, 1, events)
    assert region.owner == a.id and region.held_by is None and region.hold == 0
    assert any("falls with it" in e["text"] for e in events)
    sent = json.loads(protocol.tick_message(sim, False, 1.0))["data"]["regions"]
    taken = next(r for r in sent if r["id"] == region.id)
    assert taken["owner"] == a.id and taken["held_by"] is None and taken["hold"] == 0
