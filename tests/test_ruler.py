"""A human ruler: the orders a player can give one civ, and that everything else carries on."""

import json

import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.diplomacy import Stance
from civsim.simulation import Simulation
from civsim.strategy import make_brain


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    brain = make_brain("utility")
    for _ in range(120):
        sim.step_with(brain)
    return sim


def run(sim, ticks):
    brain = make_brain("utility")
    for _ in range(ticks):
        sim.step_with(brain)


def test_nobody_rules_until_a_civ_is_taken_and_it_can_be_handed_back(sim):
    ruler = sim.ruler
    assert ruler.state() is None
    assert json.loads(protocol.tick_message(sim, False, 1.0))["data"]["ruler"] is None
    assert ruler.command("set_focus", {"focus": "military"}) == "no civ is being ruled"
    assert ruler.command("take_control", {"civ": 99}) == "no such civ"
    assert ruler.command("take_control", {"civ": 0}) is None
    born = sim.civs[0].personality
    assert ruler.state()["civ"] == 0 and ruler.state()["focus"] == "balanced"
    ruler.command("set_focus", {"focus": "military"})
    ruler.command("set_build", {"building": "house"})
    assert ruler.command("release_control", {}) is None
    assert ruler.state() is None
    assert sim.civs[0].personality == born and sim.civs[0].build_order is None


def test_a_focus_shifts_what_the_civ_plans_by(sim):
    ruler = sim.ruler
    ruler.command("take_control", {"civ": 0})
    civ = sim.civs[0]
    before = dict(civ.personality.weights)
    assert ruler.command("set_focus", {"focus": "nonsense"}) is not None
    assert ruler.command("set_focus", {"focus": "military"}) is None
    assert civ.personality.weights["military"] == pytest.approx(1.8 * before["military"], rel=1e-3)
    assert civ.personality.weights["science"] == before["science"]
    ruler.command("set_focus", {"focus": "science"})
    assert civ.personality.weights["military"] == before["military"], "a new focus replaces the old one"


def test_a_stance_takes_effect_at_once_and_outlasts_the_strategist(sim):
    ruler = sim.ruler
    ruler.command("take_control", {"civ": 0})
    assert ruler.command("set_stance", {"civ": 0, "stance": "trade"}) == "no such civ"
    assert ruler.command("set_stance", {"civ": 1, "stance": "conquer"}) is not None
    assert ruler.command("set_stance", {"civ": 1, "stance": "aggression", "commitment": 0.8}) is None
    intent = sim.diplomacy.intent(0, 1)
    assert intent.stance is Stance.AGGRESSION and intent.commitment == pytest.approx(0.8)
    run(sim, 160)  # three check-ins by the strategist
    assert sim.diplomacy.intent(0, 1).stance is Stance.AGGRESSION
    assert ruler.command("set_stance", {"civ": 1, "stance": "auto"}) is None
    assert ruler.state()["stances"] == {}
    run(sim, 60)
    assert sim.diplomacy.intent(0, 1).stance is not Stance.AGGRESSION or sim.diplomacy.relation(0, 1).war


def test_research_and_building_orders_are_carried_out_then_cleared(sim):
    ruler = sim.ruler
    ruler.command("take_control", {"civ": 0})
    civ = sim.civs[0]
    state = ruler.state()
    tech = state["research_options"][-1]["id"]
    assert ruler.command("set_research", {"tech": "not_a_tech"}) is not None
    assert ruler.command("set_research", {"tech": tech}) is None
    assert ruler.command("set_build", {"building": "factory"}) == "that cannot be built", "its tech is unknown"
    assert ruler.command("set_build", {"building": "house"}) is None
    houses = civ.count("house")
    run(sim, 400)
    assert tech in civ.known_techs and civ.research_order is None
    assert civ.count("house") > houses and civ.build_order is None


def test_ruler_commands_go_through_the_protocol():
    action, value = protocol.parse_command(json.dumps(
        {"type": "command", "data": {"action": "set_stance", "value": {"civ": 2, "stance": "ally"}}}))
    assert (action, value) == ("set_stance", {"civ": 2, "stance": "ally"})
    assert protocol.parse_command('{"type": "command", "data": {"action": "release_control"}}') == ("release_control", {})
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_command('{"type": "command", "data": {"action": "set_focus", "value": 3}}')
