"""Sickness: a civ long at war may be struck down for a season, and its neighbours notice."""

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import rules
from civsim.economy import compute_modifiers
from civsim.simulation import Simulation
from civsim.strategy import stance_context

from test_utility_brain import context, decide  # noqa: F401


@pytest.fixture
def war():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    sim.diplomacy._start_war(a, b, 0, {a.id})
    return sim, a, b


def roll(sim, start, ticks):
    events = []
    for tick in range(start, start + ticks):
        sim.diplomacy.now = tick
        sim.diplomacy._outbreaks(tick, events)
    return events


def test_no_sickness_in_peace_or_in_a_short_war(war):
    sim, a, b = war
    assert not roll(sim, 1, rules.SICKNESS_AFTER - 1)
    assert not any(civ.sickness for civ in sim.civs)


def test_a_long_war_brings_sickness_that_weakens_and_then_passes(war):
    sim, a, b = war
    people = {civ.id: civ.population for civ in sim.civs}
    events = roll(sim, rules.SICKNESS_AFTER, 3000)
    struck = [civ for civ in (a, b) if civ.sick_rest]
    assert struck and any("breaks out" in e["text"] for e in events)
    assert all(not civ.sick_rest for civ in sim.civs[2:]), "only those at war"
    civ = struck[0]
    assert civ.population < people[civ.id]
    assert any("recovers" in e["text"] for e in events)

    # While it lasts the civ fights worse and grows slower, and everyone can see it.
    civ.sickness, civ.sick_until = "camp fever", 10_000
    sim.diplomacy.now = sim.tick = 5000
    well = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    ill = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    sim.diplomacy.apply_modifiers(civ, ill)
    allies = len(sim.diplomacy.allies(civ.id))
    assert ill.military == pytest.approx(well.military + rules.SICKNESS_MILITARY)
    assert ill.growth == pytest.approx(well.growth + rules.SICKNESS_GROWTH)
    assert ill.defense == pytest.approx(well.defense + rules.ALLY_DEFENSE * allies)
    other = next(c for c in sim.civs if c is not civ)
    seen = next(n for n in stance_context(sim, other)["neighbors"] if n["id"] == civ.id)
    assert seen["sick"] is True and stance_context(sim, civ)["you"]["sick"] is True


def test_one_outbreak_at_a_time_and_a_rest_after(war):
    sim, a, b = war
    a.sickness, a.sick_until, a.sick_rest = "the flux", 400, 400 + rules.SICKNESS_REST
    b.sick_rest = 10**9
    events = roll(sim, 300, 99)
    assert not any("breaks out" in e["text"] for e in events)
    events = roll(sim, 400, rules.SICKNESS_REST - 1)
    assert a.sickness == "" and not any("breaks out" in e["text"] for e in events)


# -- what the strategist makes of it -------------------------------------------

def test_a_sick_neighbour_is_attacked_sooner_and_a_sick_civ_attacks_nobody(context):  # noqa: F811
    target = context["neighbors"][0]
    target["army_vs_yours"] = "weaker"
    context["you"]["weights"]["military"] = 0.9
    assert decide(context)[target["name"]]["stance"] != "aggression"
    target["sick"] = True
    assert decide(context)[target["name"]]["stance"] == "aggression"
    context["you"]["sick"] = True
    assert decide(context)[target["name"]]["stance"] != "aggression"


def test_a_sick_ally_may_be_stabbed_in_the_back_by_the_warlike_only(context):  # noqa: F811
    friend = context["neighbors"][0]
    power = context["you"]["military_power"]
    friend.update(relation="alliance", intel={"military_power": round(power / 1.2)}, their_stance_toward_you="ally",
                  standing=0.0)
    context["you"]["weights"]["military"] = 1.3
    assert decide(context)[friend["name"]]["stance"] == "ally", "an ally in good health and near our strength is safe"
    friend["sick"] = True
    assert decide(context)[friend["name"]]["stance"] == "aggression"
    friend["standing"] = 2.0
    assert decide(context)[friend["name"]]["stance"] == "ally", "not one who has stood by us"
    friend["standing"] = 0.0
    context["you"]["weights"]["military"] = 0.9
    assert decide(context)[friend["name"]]["stance"] == "ally", "and not by a peaceable civ"
