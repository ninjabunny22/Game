"""How a game is won: last civ standing, most of the map, or the highest score on the last day."""

import json
import math

from civsim.bridge import protocol
from civsim.config import SimConfig, game_config
from civsim.simulation import Simulation


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


def test_ninety_percent_of_the_regions_and_every_rival_seat_win_by_domination():
    sim = Simulation(SimConfig(seed=3))
    regions = sim.world.regions
    need = sim.domination_target()
    assert need == math.ceil(0.9 * len(regions))
    winner = sim.civs[2]
    seats = {r.id for r in sim.rival_seats(winner)}
    assert len(seats) == len(sim.civs) - 1 and winner.home_region not in seats
    # Every region but the ones it needs least: one short of the target, every seat held.
    order = sorted(regions, key=lambda r: (r.id not in seats and r.id != winner.home_region, r.id))
    for i, region in enumerate(order):
        region.owner = winner.id if i < need - 1 else None
    assert sim.seats_held(winner) == (len(seats), len(seats))
    sim.step()
    assert sim.victory is None, "one region short"
    order[need - 1].owner = winner.id
    sim.step()
    assert sim.victory["civ"] == winner.id and sim.victory["kind"] == "domination"


def test_the_land_alone_is_not_enough_without_every_rival_seat():
    sim = Simulation(SimConfig(seed=3))
    winner, rival = sim.civs[0], sim.civs[1]
    seat = sim.world.regions[rival.home_region]
    for region in sim.world.regions:
        region.owner = winner.id
    seat.owner = rival.id
    assert sim.regions_held(winner) >= sim.domination_target()
    assert sim.victory_share(winner) < 1.0
    sim.step()
    assert sim.victory is None, "a rival still holds its home seat"
    seat.owner = winner.id
    sim.step()
    assert sim.victory["kind"] in ("domination", "conquest")


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


def test_every_rival_home_seat_is_a_prize_worth_more_as_the_map_is_won():
    sim = Simulation(SimConfig(seed=3))
    civ, rival = sim.civs[0], sim.civs[1]
    seat = rival.home_region
    value = sim.geography.value(civ, seat, sim.tick)
    assert "home seat" in value.reasons[0]
    others = [r for r in sim.world.regions if r.owner is None][:4]
    for region in others:
        region.owner = civ.id  # more of the map held: the race is closer
    later = sim.geography.value(civ, seat, sim.tick + 100)
    assert later.strategic > value.strategic
