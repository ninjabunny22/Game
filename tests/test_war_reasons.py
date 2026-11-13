"""More reasons for war, and what a civ proclaims when it declares one: each new reason adds to
the score of attacking a neighbour, is said in the strategist's reason and names its motive,
and the declaration speaks from it (diplomacy/proclamations.py)."""

import random

import pytest

from civsim.diplomacy import Intent, Stance
from civsim.diplomacy.proclamations import LINES, proclaim
from civsim.strategy.utility import UtilityBrain

from test_utility_brain import context  # noqa: F401


def _score(brain, context, target):  # noqa: F811
    return brain._attack(context["you"], target, 2.0, 2.0, 1.3, 0.0, False, True, False, None,
                         {"kind": "conquest", "target": None}, {})


@pytest.mark.parametrize("reason, setup, motive, weight", [
    ("resources", lambda you, n: (you.update(short_of=["ore"]),
                                  n.update(rich_nodes=[{"name": "the Great Iron Vein", "resource": "ore", "region": "X"}])),
     "resources", "RESOURCE_WAR"),
    ("lost lands", lambda you, n: n.update(holds_our_lost_lands=["Glasswater"]), "lost_lands", "LOST_LANDS"),
    ("land hunger", lambda you, n: you.update(crowded=True), "land_hunger", "LAND_HUNGER"),
    ("refused trade", lambda you, n: (you.update(short_of=["stone"]),
                                      n.update(refused_trade={"resource": "stone", "days": 150})), "refused", "TRADE_REFUSED"),
    ("a gate into our land", lambda you, n: n.update(gate_into_our_land="the Kingsgate"), "gate", "GATE_THREAT"),
])
def test_each_new_reason_adds_to_the_case_for_war_and_names_its_motive(context, reason, setup, motive, weight):  # noqa: F811
    brain = UtilityBrain()
    target = context["neighbors"][0]
    for key in ("rich_nodes", "holds_our_lost_lands", "refused_trade", "gate_into_our_land"):
        target.pop(key, None)
    context["you"].update(short_of=[], crowded=False)
    before, _ = _score(brain, context, target)
    setup(context["you"], target)
    after, why = _score(brain, context, target)
    assert after == pytest.approx(before + getattr(brain.p, weight)), reason
    assert brain._motive[0] == motive and why


def test_a_rich_node_of_something_we_have_plenty_of_is_no_reason(context):  # noqa: F811
    brain = UtilityBrain()
    target = context["neighbors"][0]
    context["you"].update(short_of=[], crowded=False)
    target.update(rich_nodes=[], holds_our_lost_lands=[], refused_trade=None, gate_into_our_land=None)
    before, _ = _score(brain, context, target)
    target["rich_nodes"] = [{"name": "the Golden Seam", "resource": "gold", "region": "X"}]
    assert _score(brain, context, target)[0] == pytest.approx(before)


def test_every_motive_has_words_and_they_name_names():
    rng = random.Random(1)
    for motive in LINES:
        line = proclaim("Zhanlu", "Ossyria", motive, "Glasswater", rng)
        assert line and "{" not in line
    assert "Ossyria" in proclaim("Zhanlu", "Ossyria", "lost_lands", "Glasswater", random.Random(0))
    assert "{" not in proclaim("Zhanlu", "Ossyria", "prize", None, rng), "a line needing a name is skipped without one"


def test_a_declaration_proclaims_from_its_motive_or_from_history(context):  # noqa: F811
    from civsim.config import SimConfig
    from civsim.simulation import Simulation
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    edge = next(n for t in sorted(b.territory) for n in sim.world.neighbors(t)
                if sim.world.owner[n] < 0 and sim.world.walkable(n))
    sim.world.claim(edge, a.id)
    a.territory.add(edge)
    a.diplomacy_points = 300.0
    region = next(r for r in sim.world.regions if r.owner == b.id)
    a.lost_regions[region.id] = 1  # b holds land it took from a
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0, motive="weaker")})
    events: list = []
    sim.diplomacy._resolve_pair(a.id, b.id, sim.tick, events)
    declared = next(e for e in events if "declares war" in e["text"])
    assert region.name in declared["proclamation"] or "lands" in declared["proclamation"], \
        "a plain motive gives way to the land it lost"
    assert declared["target"] == b.id and declared["war_name"]
