"""How a game is won: last civ standing, most of the map, or the highest score on the last day."""

import json

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.simulation import DOMINATION_SHARE, Simulation


def test_nothing_is_decided_at_the_start_and_every_civ_has_a_score():
    sim = Simulation(SimConfig(seed=3))
    sim.step()
    assert sim.victory is None
    data = json.loads(protocol.tick_message(sim, False, 1.0))["data"]
    assert data["victory"] is None
    assert all(civ["score"] == sim.score(sim.civs[civ["id"]]) > 0 for civ in data["civs"])


def test_the_last_civ_standing_wins_by_conquest():
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs[1:]:
        civ.alive = False
    events = sim.step()
    assert sim.victory == {"civ": 0, "kind": "conquest", "tick": 1}
    assert any("victory" in event["text"] for event in events)
    assert sim.score(sim.civs[1]) == 0
    sim.step()
    assert sim.victory["tick"] == 1, "decided once"


def test_holding_most_of_the_map_wins_by_domination():
    sim = Simulation(SimConfig(seed=3))
    regions = sim.world.regions
    need = next(n for n in range(len(regions) + 1) if n >= DOMINATION_SHARE * len(regions))
    others = [region for region in regions if region.owner != 2]  # civ 2 keeps the ones it starts with
    short = need - 1 - (len(regions) - len(others))
    for i, region in enumerate(others):
        region.owner = 2 if i < short else None
    sim.step()
    assert sim.victory is None, "one region short"
    others[short].owner = 2
    sim.step()
    assert sim.victory["civ"] == 2 and sim.victory["kind"] == "domination"


def test_the_highest_score_wins_on_the_last_day():
    sim = Simulation(SimConfig(seed=3, end_tick=5))
    sim.civs[3].population += 500
    for _ in range(4):
        sim.step()
    assert sim.victory is None
    sim.step()
    assert sim.victory is None, "a game nobody has fought in runs on past its last day"
    sim.diplomacy.wars_started = 1
    sim.step()
    assert sim.victory == {"civ": 3, "kind": "score", "tick": 6}
    assert Simulation(SimConfig(seed=3, end_tick=0)).config.end_tick == 0
