"""Peace on terms, wars fought alongside allies, betrayal by the warlike, and what other
civs put to a human ruler."""

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance, rules
from civsim.simulation import Simulation
from civsim.strategy import make_brain

from test_utility_brain import context, decide  # noqa: F401  (the fixture and its helper)


@pytest.fixture
def war():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    sim.diplomacy._start_war(a, b, 0, {a.id})
    relation = sim.diplomacy.relation(a.id, b.id)
    for civ in (a, b):
        for res in civ.resources:
            civ.resources[res] = 100.0
    return sim, a, b, relation


def set_stances(sim, a, b, a_stance, b_stance):
    sim.diplomacy.intents[(a.id, b.id)] = Intent(stance=a_stance)
    sim.diplomacy.intents[(b.id, a.id)] = Intent(stance=b_stance)


def test_peace_between_equals_costs_nobody_anything(war):
    sim, a, b, relation = war
    set_stances(sim, a, b, Stance.IGNORE, Stance.IGNORE)
    sim.diplomacy._resolve_pair(a.id, b.id, rules.MIN_WAR, [])
    assert relation.war is None and b.resources["gold"] == 100.0


def test_the_side_well_behind_pays_tribute_when_peace_is_made(war):
    sim, a, b, relation = war
    relation.war.tiles_taken[a.id] = rules.PEACE_LEAD
    set_stances(sim, a, b, Stance.IGNORE, Stance.IGNORE)
    events = []
    sim.diplomacy._resolve_pair(a.id, b.id, rules.MIN_WAR, events)
    assert relation.war is None
    assert b.resources["gold"] == pytest.approx(100.0 * (1 - rules.PEACE_TRIBUTE))
    assert a.resources["gold"] > 100.0 or sim.modifiers[a.id].storage["gold"] <= 100.0
    assert any("pays" in e["text"] and "tribute" in e["text"] for e in events)
    assert sim.diplomacy.standing[(b.id, a.id)] < 0


def test_a_winner_whose_advance_has_stalled_takes_tribute_for_peace(war):
    sim, a, b, relation = war
    war_ = relation.war
    war_.tiles_taken[a.id] = rules.PEACE_LEAD + 2
    war_.last_gain = rules.TERMS_AFTER
    set_stances(sim, a, b, Stance.AGGRESSION, Stance.IGNORE)
    sim.diplomacy._resolve_pair(a.id, b.id, rules.TERMS_AFTER + rules.STALL_TICKS - 1, [])
    assert relation.war is war_, "still advancing: it fights on"
    # Nor while it holds one of the loser's capitals.
    region = next(r for r in sim.world.regions if r.owner == b.id)
    region.held_by = a.id
    sim.diplomacy._resolve_pair(a.id, b.id, rules.TERMS_AFTER + rules.STALL_TICKS, [])
    assert relation.war is war_
    region.held_by = None
    # Nor is peace made for a civ a human rules.
    sim.diplomacy.player = a.id
    sim.diplomacy._resolve_pair(a.id, b.id, rules.TERMS_AFTER + rules.STALL_TICKS, [])
    assert relation.war is war_
    sim.diplomacy.player = None
    events = []
    sim.diplomacy._resolve_pair(a.id, b.id, rules.TERMS_AFTER + rules.STALL_TICKS, events)
    assert relation.war is None and any("sues for peace" in e["text"] for e in events)
    assert b.resources["gold"] < 100.0


# -- the strategist ----------------------------------------------------------

def test_it_joins_an_allys_war_when_together_they_are_strong_enough(context):  # noqa: F811
    friend, foe = context["neighbors"][:2]
    power = context["you"]["military_power"]
    friend.update(relation="alliance", intel={"military_power": power}, at_war_with=[foe["name"]],
                  their_stance_toward_you="ally")
    assert decide(context)[foe["name"]]["stance"] == "aggression", "comparable alone, twice as strong together"
    friend["at_war_with"] = []
    assert decide(context)[foe["name"]]["stance"] != "aggression", "no fight of the ally's, no war from parity"


def test_only_the_warlike_turn_on_a_weak_and_lonely_ally(context):  # noqa: F811
    friend = context["neighbors"][0]
    power = context["you"]["military_power"]
    friend.update(relation="alliance", intel={"military_power": max(1, power // 4)}, their_stance_toward_you="ally",
                  standing=0.0)
    context["you"]["weights"]["military"] = 1.4
    assert decide(context)[friend["name"]]["stance"] == "aggression"
    for change in ({"allied_with": ["Someone"]}, {"standing": 2.0}):
        loyal = {**context, "neighbors": [dict(n, **change) if n is friend else n for n in context["neighbors"]]}
        assert decide(loyal)[friend["name"]]["stance"] == "ally"
    context["you"]["weights"]["military"] = 1.0
    assert decide(context)[friend["name"]]["stance"] == "ally", "a peaceable civ keeps its word"


# -- proposals to a human ruler ----------------------------------------------

def test_other_civs_put_alliances_trades_and_peace_to_the_ruler(war):
    sim, a, b, relation = war
    ruler, c = sim.ruler, sim.civs[2]
    assert ruler.command("take_control", {"civ": a.id}) is None
    assert sim.diplomacy.player == a.id
    set_stances(sim, a, c, Stance.IGNORE, Stance.ALLY)
    set_stances(sim, a, b, Stance.AGGRESSION, Stance.IGNORE)
    sim.tick = rules.MIN_WAR
    relation.war.tiles_taken[a.id] = rules.PEACE_LEAD
    offers = {(p["civ"], p["kind"]): p["text"] for p in ruler.proposals()}
    assert set(offers) == {(c.id, "alliance"), (b.id, "peace")}
    assert "tribute" in offers[(b.id, "peace")]
    assert ruler.state()["proposals"] == ruler.proposals()
    assert len(ruler.notices()) == 2 and ruler.notices() == [], "each is announced once"

    # Refusing puts it away for a while; accepting takes the stance that makes it happen.
    assert ruler.command("answer_proposal", {"civ": c.id, "kind": "alliance", "accept": False}) is None
    assert (c.id, "alliance") not in {(p["civ"], p["kind"]) for p in ruler.proposals()}
    assert ruler.command("answer_proposal", {"civ": c.id, "kind": "alliance", "accept": True}) is not None
    assert ruler.command("answer_proposal", {"civ": b.id, "kind": "peace", "accept": True}) is None
    assert sim.diplomacy.intent(a.id, b.id).stance is Stance.IGNORE
    gold = b.resources["gold"]
    sim.diplomacy._resolve_pair(min(a.id, b.id), max(a.id, b.id), sim.tick, [])
    assert relation.war is None and b.resources["gold"] < gold
    sim.tick += PROPOSAL_REST_PLUS
    assert (c.id, "alliance") in {(p["civ"], p["kind"]) for p in ruler.proposals()}, "and asks again later"
    ruler.command("release_control", {})
    assert sim.diplomacy.player is None and ruler.proposals() == []


PROPOSAL_REST_PLUS = 301


def test_whole_games_still_end_wars_and_some_on_terms():
    sim = Simulation(SimConfig(seed=2024))
    brain = make_brain("utility")
    texts = []
    for _ in range(3500):
        texts += [e.get("text", "") for e in sim.step_with(brain)]
    assert any("declares war" in t for t in texts)
    assert any("make peace" in t or "sues for peace" in t or "exhausted" in t or "loses its capital" in t for t in texts)
