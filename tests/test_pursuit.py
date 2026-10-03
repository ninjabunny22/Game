"""Pursuit of a routed army, what becomes of its soldiers, and captured commanders."""

import json

import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.military import Captive, Commander
from civsim.military import warfare
from civsim.simulation import Simulation

from test_military import face_off, field, update


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:
        civ.diplomacy_points = 300.0
    return sim


def routed(sim, soldiers=(100, 40)):
    """A battle already decided: returns (winner, loser) just after the rout."""
    a, b = sim.civs[0], sim.civs[1]
    winner, loser = face_off(sim, a, b, soldiers)
    sim.military._tick = sim.tick
    dice, sim.military.rng = sim.military.rng, Fixed(0.9)  # the beaten commander gets away
    sim.military._rout(loser, winner, sim.tick, [])
    sim.military.rng = dice
    return winner, loser


class Fixed:
    """Stands in for the random generator, returning the given rolls in turn."""

    def __init__(self, *rolls):
        self.rolls = list(rolls)

    def random(self):
        return self.rolls.pop(0)


def test_the_victor_gives_chase(sim):
    winner, loser = routed(sim)
    assert loser.state == "retreating" and loser.rout_size == pytest.approx(loser.size)
    assert winner.state == "pursuing" and winner.pursuing == loser.id
    assert winner.pursuit_until == sim.tick + warfare.PURSUIT_DAYS


def test_a_slower_victor_lets_them_go(sim):
    winner, loser = routed(sim, soldiers=(100, 40))
    winner.state, winner.pursuing = "marching", None
    loser.units = {"cavalry": loser.size}
    assert loser.speed > winner.speed
    assert not sim.military._can_pursue(winner, loser)
    winner.units = {"cavalry": winner.size}
    assert sim.military._can_pursue(winner, loser), "cavalry can run down cavalry"


def test_no_chase_with_another_enemy_army_close_by(sim):
    winner, loser = routed(sim)
    assert sim.military._can_pursue(winner, loser)
    garrison = sim.civs[loser.civ].garrison
    garrison.add({"spearman": 10})
    garrison.tile = loser.tile
    assert not sim.military._can_pursue(winner, loser)


def test_a_caught_army_is_cut_down_and_its_soldiers_mostly_wounded(sim):
    winner, loser = routed(sim)
    civ = sim.civs[loser.civ]
    size, soldiers, population, home = loser.size, civ.soldiers, civ.population, civ.garrison.size
    sim.tick += 1
    sim.military._tick = sim.tick
    sim.military._pursue(sim.civs[winner.civ], winner, sim.tick, [])
    lost = size - loser.size
    assert lost == pytest.approx(warfare.PURSUIT_LOSS * size)
    assert civ.wounded == pytest.approx(0.6 * lost)
    assert civ.garrison.size - home == pytest.approx(0.3 * lost), "those who escape rejoin the garrison"
    assert population - civ.population == pytest.approx(0.1 * lost), "only the dead leave the population"
    assert soldiers - civ.soldiers == pytest.approx(0.7 * lost)
    assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers)


def test_a_fleeing_army_that_cannot_get_away_is_destroyed(sim):
    winner, loser = routed(sim)
    civ, victor = sim.civs[loser.civ], sim.civs[winner.civ]
    wins = winner.commander.wins
    loser.path = []
    texts = []
    for _ in range(warfare.PURSUIT_DAYS):
        sim.tick += 1
        sim.military._tick = sim.tick
        events: list = []
        sim.military._pursue(victor, winner, sim.tick, events)  # the loser never moves: it is held in place
        texts += [e["text"] for e in events]
        if loser not in civ.armies:
            break
    assert loser not in civ.armies
    assert any("runs down and destroys" in t for t in texts)
    assert winner.commander.wins == wins + 1, "running an army down counts as a win"
    assert winner.state == "marching" and winner.pursuing is None
    assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers)


def test_the_chase_is_called_off_after_a_few_days_and_leaves_the_pursuer_disordered(sim):
    winner, loser = routed(sim)
    full = sim.military.army_strength(winner) / warfare.DISORDER
    assert sim.military.army_strength(winner) == pytest.approx(warfare.DISORDER * full)
    sim.tick = winner.pursuit_until
    sim.military._tick = sim.tick
    sim.military._pursue(sim.civs[winner.civ], winner, sim.tick, [])
    assert winner.state == "marching" and winner.pursuing is None
    assert loser in sim.civs[loser.civ].armies, "it got away"
    assert sim.military.army_strength(winner) == pytest.approx(warfare.DISORDER * full), "still out of formation"
    sim.military._tick = sim.tick + warfare.DISORDER_DAYS
    assert sim.military.army_strength(winner) == pytest.approx(full)


def test_an_army_that_reaches_its_capital_is_safe(sim):
    winner, loser = routed(sim)
    loser.tile = sim.civs[loser.civ].capital.tile
    sim.military._pursue(sim.civs[winner.civ], winner, sim.tick + 1, [])
    assert winner.pursuing is None and loser in sim.civs[loser.civ].armies


@pytest.mark.parametrize("rolls, fate", [
    ((0.05,), "killed"),
    ((0.2, 0.9), "prisoner"),
    ((0.2, 0.1), "changes sides"),
    ((0.5,), "escapes"),
])
def test_the_commander_of_a_destroyed_army_dies_is_captured_or_escapes(sim, rolls, fate):
    winner, loser = routed(sim)
    civ, victor = sim.civs[loser.civ], sim.civs[winner.civ]
    commander = loser.commander
    sim.military.rng = Fixed(*rolls)
    events: list = []
    sim.military._finish_off(loser, winner, sim.tick, events)
    assert fate in events[-1]["text"]
    assert (commander in civ.commanders) == (fate == "escapes")
    assert (commander in victor.commanders) == (fate == "changes sides")
    assert ([c.commander for c in victor.captives] == [commander]) == (fate == "prisoner")


def test_the_odds_are_ten_dead_twenty_five_captured_sixty_five_escaped():
    assert warfare.COMMANDER_DEATH_CHANCE == 0.10 and warfare.CAPTURE_CHANCE == 0.25
    assert warfare.SWITCH_SIDES_CHANCE == 0.5
    assert warfare.WOUNDED_SHARE + warfare.ESCAPE_SHARE + warfare.DEAD_SHARE == pytest.approx(1.0)
    assert (warfare.WOUNDED_SHARE, warfare.ESCAPE_SHARE, warfare.DEAD_SHARE) == (0.6, 0.3, 0.1)


def test_a_prisoner_is_ransomed_when_his_side_can_pay(sim):
    winner, loser = routed(sim)
    home, captor = sim.civs[loser.civ], sim.civs[winner.civ]
    commander = Commander("Test of Nowhere", experience=225)
    captor.captives.append(Captive(commander, home.id, sim.tick))
    price = sim.military.ransom(commander)
    home.resources["gold"] = price + warfare.GOLD_RESERVE - 1
    sim.military._hold_captives(captor, sim.tick, [])
    assert captor.captives, "not while it would empty the treasury"
    home.resources["gold"], before = price + warfare.GOLD_RESERVE, captor.resources["gold"]
    events: list = []
    sim.military._hold_captives(captor, sim.tick, events)
    assert not captor.captives and commander in home.commanders
    assert home.resources["gold"] == warfare.GOLD_RESERVE and captor.resources["gold"] == before + price
    assert "ransoms" in events[0]["text"]


def test_ransom_is_twenty_gold_and_twenty_a_level(sim):
    assert sim.military.ransom(Commander("Test")) == 40
    assert sim.military.ransom(Commander("Test", experience=225)) == 100


def test_prisoners_go_home_at_peace(sim):
    home, captor = sim.civs[2], sim.civs[3]
    commander = Commander("Test of Nowhere")
    captor.captives.append(Captive(commander, home.id, sim.tick))
    home.resources["gold"] = 0
    sim.military._hold_captives(captor, sim.tick, [])
    assert not captor.captives and commander in home.commanders


def test_the_wounded_do_not_work_and_recover_in_time(sim):
    civ = sim.civs[0]
    workforce = civ.workforce
    civ.wounded = 20.0
    assert civ.workforce == pytest.approx(workforce - 20)
    for _ in range(400):
        sim.step()
    assert civ.wounded < 1.0


def test_protocol_reports_wounded_and_prisoners(sim):
    captor, home = sim.civs[0], sim.civs[1]
    captor.wounded = 7.4
    captor.captives.append(Captive(Commander("Test of Nowhere", experience=100), home.id, 0))
    state = json.loads(protocol.tick_message(sim, [], 1.0))["data"]["civs"][0]
    assert state["wounded"] == 7
    assert state["captives"] == [{"name": "Test of Nowhere", "level": state["captives"][0]["level"], "home": home.id}]


def test_no_reinforcements_reach_an_army_in_flight(sim):
    winner, loser = routed(sim)
    civ = sim.civs[loser.civ]
    civ.garrison.add({"spearman": 50})
    civ.soldiers += 50
    size = loser.size
    sim.military._organise(civ, sim.tick)
    assert loser.size == pytest.approx(size)
