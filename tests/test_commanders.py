"""Commanders as a roster: what they cost, their fate in defeat, and holding capitals."""

import json

import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.military import Commander, warfare
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain

from test_military import face_off, field, go_to_war, update
from test_pursuit import Fixed


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:
        civ.diplomacy_points = 300.0
    return sim


def test_every_civ_starts_with_three_commanders(sim):
    for civ in sim.civs:
        assert len(civ.commanders) == 3 and sim.military.roster(civ) == 3
        assert all(c.level == 1 for c in civ.commanders)
    names = [c.name for civ in sim.civs for c in civ.commanders]
    assert len(set(names)) > 6


def test_a_new_commander_costs_gold_and_none_comes_without_it(sim):
    civ = sim.civs[0]
    civ.commanders.clear()
    civ.resources["gold"] = 19
    assert sim.military._appoint(civ) is None
    civ.resources["gold"] = 25
    assert sim.military._appoint(civ) is not None and civ.resources["gold"] == 5


def test_the_roster_is_capped_at_twenty(sim):
    civ = sim.civs[0]
    civ.resources["gold"] = 5000
    civ.commanders[:] = [Commander(f"C{i}") for i in range(20)]
    assert sim.military._raise_commander(civ) is None and civ.resources["gold"] == 5000
    civ.commanders.pop()
    assert sim.military._raise_commander(civ) is not None, "a slot freed up"


def test_a_depleted_roster_is_topped_up_when_the_treasury_allows(sim):
    civ = sim.civs[0]
    civ.commanders.clear()
    civ.resources["gold"] = 39
    sim.military._organise(civ, sim.tick)
    assert len(civ.commanders) == 0, "not below the reserve it keeps back"
    civ.resources["gold"] = 40
    sim.military._organise(civ, sim.tick)
    assert len(civ.commanders) == 1 and civ.resources["gold"] == 20


@pytest.mark.parametrize("rolls, fate, keeps", [
    ((0.05,), "is killed", False),
    ((0.2, 0.9), "is taken prisoner", False),
    ((0.2, 0.1), "changes sides", False),
    ((0.5,), "", True),
])
def test_a_routed_commander_dies_is_captured_or_stays_with_the_army(sim, rolls, fate, keeps):
    winner, loser = face_off(sim, sim.civs[0], sim.civs[1], (100, 40))
    victor = sim.civs[winner.civ]
    commander = loser.commander
    reserve = len(victor.commanders)
    sim.military.rng = Fixed(*rolls)
    events: list = []
    sim.military._rout(loser, winner, sim.tick, events)
    assert (loser.commander is commander) == keeps
    assert fate in events[0]["text"]
    assert (len(victor.commanders) == reserve + 1) == (fate == "changes sides")
    assert bool(victor.captives) == (fate == "is taken prisoner")
    if not keeps:
        assert loser.leaderless_until > sim.tick


def test_a_defector_finding_the_roster_full_is_held_prisoner(sim):
    winner, loser = face_off(sim, sim.civs[0], sim.civs[1], (100, 40))
    victor = sim.civs[winner.civ]
    victor.commanders[:] = [Commander(f"C{i}") for i in range(19)]
    assert sim.military.roster(victor) == 20
    sim.military.rng = Fixed(0.2, 0.1)
    sim.military._rout(loser, winner, sim.tick, [])
    assert len(victor.commanders) == 19 and len(victor.captives) == 1


def test_most_of_a_beaten_armys_losses_are_wounded_or_got_away(sim):
    a, b = sim.civs[0], sim.civs[1]
    army, other = face_off(sim, a, b, (100, 60))
    sim.military.rng = Fixed(*[0.9] * 50)
    soldiers, population = b.soldiers, b.population
    dead_a = a.population
    for _ in range(400):
        sim.tick += 1
        sim.military._fight(sim.tick, [])
        if other.state == "retreating":
            break
    assert other.state == "retreating"
    lost = soldiers - b.soldiers - b.wounded  # soldiers gone who are not among the wounded: the dead
    fallen = b.wounded / 0.6
    assert b.wounded > 0
    assert population - b.population == pytest.approx(0.1 * fallen, rel=1e-6), "one in ten is dead"
    assert lost == pytest.approx(0.1 * fallen, rel=1e-6)
    assert a.wounded == 0 and a.population < dead_a, "the winner's losses are simply dead"
    assert sum(x.size for x in b.armies) == pytest.approx(b.soldiers)


def test_a_beaten_army_falls_back_on_the_nearest_capital_it_holds(sim):
    a, b = sim.civs[0], sim.civs[1]
    winner, loser = face_off(sim, a, b, (100, 40))
    civ = sim.civs[loser.civ]
    assert len(civ.settlements) >= 2
    far = max((s.tile for s in civ.settlements), key=lambda t: sim.military._gap(civ.capital.tile, t))
    assert far != civ.capital.tile
    loser.tile, loser.state, loser.path = next(sim.world.neighbors(far)), "retreating", []
    sim.military._plan(civ, loser, sim.tick)
    assert loser.path and loser.path[-1] == far
    loser.tile = far
    sim.military._plan(civ, loser, sim.tick)
    assert loser.state == "idle", "it rests there"
    assert not sim.military._can_pursue(winner, loser), "and is safe from pursuit"


def test_reserve_commanders_hold_the_capitals_nearest_the_enemy(sim):
    a, b = sim.civs[0], sim.civs[1]
    go_to_war(sim, a, b)
    sim.military._station(b)
    best = max(b.commanders, key=lambda c: (c.experience, c.name))
    capitals = [s.tile for s in b.settlements]
    threats = [r.capital for r in sim.world.regions if r.owner == a.id]
    nearest = min(capitals, key=lambda t: (min(sim.military._gap(t, x) for x in threats), t))
    posts = [c.post for c in b.commanders if c.post is not None]
    assert len(posts) == len(set(posts)) == min(len(b.commanders), len(capitals)), "one commander to a capital"
    assert nearest in posts
    veteran = Commander("Veteran", experience=400)
    b.commanders.append(veteran)
    sim.military._station(b)
    assert veteran.post == nearest, "the best commander takes the most exposed capital"


def test_a_stationed_commander_strengthens_his_capital(sim):
    a, b = sim.civs[0], sim.civs[1]
    tile = b.capital.tile
    for c in b.commanders:
        c.post = None
    price = sim.military.tile_price(a, tile)
    assert sim.military.post_defence(b, tile) == 0
    officer = b.commanders[0]
    officer.post, officer.experience = tile, 225  # level 4
    assert sim.military.post_defence(b, tile) == pytest.approx(0.10 + 0.02 * 4)
    assert sim.military.tile_price(a, tile) == pytest.approx(price * 1.18)
    sim.military._sync(b)
    garrison = b.garrison
    garrison.add({"spearman": 20})
    enemy = type(garrison)(999, a.id, tile, "field", units={"spearman": 20.0})
    with_him = sim.military._battle_strength(garrison, enemy, sim.tick)
    officer.post = None
    assert with_him == pytest.approx(1.18 * sim.military._battle_strength(garrison, enemy, sim.tick))


@pytest.mark.parametrize("rolls, gone, text", [
    ((0.05,), True, "is killed"), ((0.2, 0.9), True, "is taken prisoner"), ((0.5,), False, None)])
def test_the_commander_of_a_fallen_capital_faces_the_same_odds(sim, rolls, gone, text):
    a, b = sim.civs[0], sim.civs[1]
    region = next(r for r in sim.world.regions if r.owner == b.id and r.capital != b.capital.tile)
    officer = b.commanders[0]
    for c in b.commanders:
        c.post = None
    officer.post = region.capital
    sim.military.rng = Fixed(*rolls)
    events: list = []
    sim.diplomacy.capture_region(a, region, sim.tick, events)
    assert (officer not in b.commanders) == gone and officer.post is None
    assert (text is None) or any(text in e["text"] for e in events)
    assert bool(a.captives) == (text == "is taken prisoner")


def test_protocol_reports_the_roster_and_postings(sim):
    civ = sim.civs[0]
    sim.military._station(civ)
    state = json.loads(protocol.tick_message(sim, [], 1.0))["data"]["civs"][0]
    assert state["commanders"] == 3 and state["commander_cap"] == 20
    posts = [c["post"] for c in state["commanders_in_reserve"]]
    assert civ.capital.name in posts and posts.count(None) == 3 - len(civ.settlements)


def test_long_games_keep_rosters_and_armies_consistent():
    for seed in (5, 7):
        sim = Simulation(SimConfig(seed=seed))
        brain = RuleBrain()
        for _ in range(2000):
            sim.step_with(brain)
            for civ in sim.civs:
                if not civ.alive:
                    continue
                assert sim.military.roster(civ) <= warfare.ROSTER_CAP
                assert civ.wounded >= 0 and civ.resources["gold"] >= -1e-6
                assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers, abs=1e-3 + 0.02 * civ.soldiers)
                held = {s.tile for s in civ.settlements}
                assert all(c.post is None or c.post in held for c in civ.commanders)
