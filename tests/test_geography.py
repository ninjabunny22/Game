"""One valuation of regions for the whole AI (strategy/geography.py): what a region would bring,
how hard it is to reach, and what it would cost to take and to hold."""

import pytest

from civsim.config import game_config
from civsim.economy.buildings import find_site, water_bodies
from civsim.economy.buildings import load_building_defs
from civsim.simulation import Simulation
from civsim.strategy import geography as geo_module
from civsim.strategy.geography import Geography


@pytest.fixture()
def isle_game():
    sim = Simulation(game_config("small", 2, seed=4, map="gilded_isle"))
    return sim, next(r for r in sim.world.regions if r.name == "Goldcrown")


def test_the_parts_add_up_to_the_total(isle_game):
    sim, _ = isle_game
    p = sim.geography.p
    for v in sim.geography.values(sim.civs[0], 0).values():
        if v.access > 0:
            reach = v.access / (1 + v.distance / p.distance_scale)
            assert v.total == pytest.approx((v.economic + v.strategic) * reach - v.take - v.hold, abs=0.01)


def test_gold_mines_make_a_region_worth_more(isle_game):
    sim, isle = isle_game
    values = sim.geography.values(sim.civs[0], 0)
    assert values[isle.id].economic > max(v.economic for r, v in values.items() if r != isle.id)
    assert "2 gold mines" in values[isle.id].reason


def test_across_the_water_counts_for_less_until_there_are_ships(isle_game, monkeypatch):
    sim, isle = isle_game
    civ = sim.civs[0]
    p = sim.geography.p
    assert sim.geography.values(civ, 0)[isle.id].access == p.later
    sim.modifiers[civ.id].boats = 1
    assert Geography(sim.world, sim.civs, sim.diplomacy).values(civ, 0)[isle.id].access == p.settle_only
    monkeypatch.setattr(geo_module, "ports", lambda civ, world: {civ.capital.tile})
    assert Geography(sim.world, sim.civs, sim.diplomacy).values(civ, 0)[isle.id].access == p.by_sea


def test_a_strongly_held_region_is_worth_less(isle_game):
    sim, _ = isle_game
    civ = sim.civs[0]
    region = next(r for r in sim.world.regions if r.neutral and r.name != "Goldcrown")
    before = Geography(sim.world, sim.civs, sim.diplomacy).values(civ, 0)[region.id]
    region.garrison *= 3
    after = Geography(sim.world, sim.civs, sim.diplomacy).values(civ, 0)[region.id]
    assert after.take > before.take and after.total < before.total


def test_a_nearer_region_is_worth_more():
    sim = Simulation(game_config("small", 2, seed=4, map="gilded_isle"))
    a, b = sim.civs
    values_a = sim.geography.values(a, 0)
    values_b = sim.geography.values(b, 0)
    # A native region next to one civ and across the ring from the other.
    near_a = next(r for r in sim.world.regions if r.neutral and values_a[r.id].distance < values_b[r.id].distance
                  and r.name != "Goldcrown")
    assert values_a[near_a.id].total > values_b[near_a.id].total


def test_a_fallen_civ_values_nothing(isle_game):
    sim, _ = isle_game
    civ = sim.civs[0]
    civ.settlements.clear()
    assert sim.geography.values(civ, 0) == {}


def test_a_harbour_faces_the_water_that_leads_to_its_goal(isle_game):
    sim, isle = isle_game
    civ = sim.civs[0]
    world = sim.world
    lagoon = water_bodies(world, isle.tiles)
    harbour = load_building_defs()["harbour"]
    civ.harbour_goal = isle.capital
    site = find_site(civ, world, harbour)
    assert site is not None and water_bodies(world, [site]) & lagoon


def test_a_campaign_does_not_wait_for_a_prize_it_could_never_take():
    sim = Simulation(game_config("medium", 2, seed=2, map="emberwaste"))
    civ = sim.civs[0]
    kesh = next(r for r in sim.world.regions if r.name == "Oasis of Kesh")
    target = sim.military._campaign_target(civ)
    kesh.garrison = 10_000  # far beyond anything it could field
    again = sim.military._campaign_target(civ)
    assert again is not kesh and (again is not None or target is kesh)
