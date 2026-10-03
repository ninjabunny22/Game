import json

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance, rules
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain, prompt, stance_context
from civsim.strategy.checkin import CheckinRequest
from civsim.strategy.context import army_band

pytestmark = pytest.mark.usefixtures("no_war_minimum")  # these tests are about other rules


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:  # plenty of influence, so tests are about the rule in question
        civ.diplomacy_points = 300.0
    return sim


def tick(sim, ticks=1) -> list[str]:
    texts = []
    for _ in range(ticks):
        sim.tick += 1
        events: list = []
        sim.diplomacy.update(sim.tick, events)
        texts += [e["text"] for e in events]
    return texts


def ally_up(sim, x, y):
    for civ in (x, y):
        civ.resources["gold"] = max(civ.resources["gold"], 300)
    sim.diplomacy.set_intents(x.id, {y.id: Intent(Stance.ALLY)})
    sim.diplomacy.set_intents(y.id, {x.id: Intent(Stance.ALLY)})
    tick(sim)
    assert sim.diplomacy.relation(x.id, y.id).status == "alliance"


def make_neighbours(sim, a, b):
    world = sim.world
    edge = next(n for t in sorted(b.territory) for n in world.neighbors(t) if world.owner[n] < 0)
    world.claim(edge, a.id)
    a.territory.add(edge)


def betray(sim, traitor, victim) -> list[str]:
    make_neighbours(sim, traitor, victim)
    traitor.resources["gold"] = max(traitor.resources["gold"], 300)
    sim.diplomacy.set_intents(traitor.id, {victim.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    return tick(sim, 12)


def neighbour(context, civ):
    return next(n for n in context["neighbors"] if n["id"] == civ.id)


# -- 1. intel ----------------------------------------------------------------

def test_only_allies_see_exact_army_and_stores(sim):
    me, friend, stranger, _ = sim.civs
    ally_up(sim, me, friend)
    friend.soldiers, friend.resources["ore"] = 17, 123
    context = stance_context(sim, me)

    seen = neighbour(context, stranger)
    assert seen["intel"] is None
    for hidden in ("soldiers", "military_power", "surplus", "lacking", "resources"):
        assert hidden not in seen
    assert seen["army_vs_yours"] in ("much weaker", "weaker", "comparable", "stronger", "much stronger")
    assert {"era", "population", "territory", "at_war_with", "allied_with"} <= set(seen)

    intel = neighbour(context, friend)["intel"]
    assert intel["soldiers"] == 17
    assert intel["resources"]["ore"] == {"stock": 123, "cap": 250}
    assert {"army_strength", "military_power", "troops_committed", "surplus", "lacking"} <= set(intel)
    assert neighbour(stance_context(sim, friend), me)["intel"] is not None, "it goes both ways"


def test_intel_ends_with_the_alliance(sim):
    me, friend = sim.civs[0], sim.civs[1]
    ally_up(sim, me, friend)
    sim.diplomacy.set_intents(friend.id, {me.id: Intent(Stance.IGNORE)})
    tick(sim)
    assert neighbour(stance_context(sim, me), friend)["intel"] is None


def test_troop_commitments_are_part_of_intel(sim):
    me, friend, enemy, _ = sim.civs
    ally_up(sim, me, friend)
    betray_free_war(sim, friend, enemy)
    friend.soldiers = 40
    intel = neighbour(stance_context(sim, me), friend)["intel"]
    assert intel["troops_committed"] == {enemy.name: 40}


def betray_free_war(sim, attacker, target):
    make_neighbours(sim, attacker, target)
    attacker.resources["gold"] = 300
    sim.diplomacy.set_intents(attacker.id, {target.id: Intent(Stance.AGGRESSION, commitment=0.5),
                                            **{o: sim.diplomacy.intent(attacker.id, o) for o in sim.diplomacy.allies(attacker.id)}})
    tick(sim, 12)
    assert sim.diplomacy.relation(attacker.id, target.id).status == "war"


@pytest.mark.parametrize("theirs, yours, band", [
    (10, 100, "much weaker"), (70, 100, "weaker"), (100, 100, "comparable"), (124, 100, "comparable"),
    (150, 100, "stronger"), (300, 100, "much stronger"), (50, 0, "much stronger"),
])
def test_army_comparison_bands(theirs, yours, band):
    assert army_band(theirs, yours) == band


def test_the_model_is_not_shown_what_the_civ_cannot_see(sim):
    me, friend, stranger, _ = sim.civs
    ally_up(sim, me, friend)
    stranger.soldiers = 4321
    stranger.population = 20000
    friend.soldiers = 1234
    _, user, _ = prompt.build(CheckinRequest(me.id, sim.tick, stance_context(sim, me)))
    assert "4321" not in user and "1234" in user
    shown = json.loads(user[user.index("{"): user.rindex("}") + 1])
    assert all("army_vs_yours" in n for n in shown["neighbors"])


def test_rule_brain_copes_with_rough_estimates(sim):
    brain = RuleBrain()
    for civ in sim.civs:
        reply = brain.decide(CheckinRequest(civ.id, sim.tick, stance_context(sim, civ)))
        assert len(reply["stances"]) == 3


# -- 2. betrayal bonus -------------------------------------------------------

def test_attacking_an_ally_is_betrayal_with_a_short_surprise(sim):
    traitor, victim = sim.civs[0], sim.civs[1]
    ally_up(sim, traitor, victim)
    texts = betray(sim, traitor, victim)
    war = sim.diplomacy.relation(traitor.id, victim.id).war
    assert war and war.betrayer == traitor.id
    assert any("betrays its ally" in t for t in texts)
    assert war.surprise_until == war.start + rules.SURPRISE_TICKS == war.start + 10


def test_a_war_between_civs_that_were_never_allied_is_not_betrayal(sim):
    a, b = sim.civs[0], sim.civs[1]
    texts = betray(sim, a, b)
    war = sim.diplomacy.relation(a.id, b.id).war
    assert war and war.betrayer is None and war.surprise_until == 0
    assert not any("betrays" in t for t in texts)
    assert not sim.diplomacy.distrusted(a.id, sim.tick)


def siege(sim, attacker, defender, ticks) -> float:
    """Capture progress a small army makes against the tile in front of it, over `ticks`."""
    army = next(a for a in attacker.armies if a.role == "field" and a.target_civ == defender.id)
    target = next(t for t in sorted(defender.territory) if t != defender.capital.tile
                  and t not in set(sim.world.neighbors(defender.capital.tile, diagonal=True)))
    army.units = {"spearman": 8.0}
    attacker.soldiers = 8.0 + attacker.garrison.size
    attacker.unpaid = attacker.unsupplied = False
    defender.population = 300  # its militia outweighs eight spearmen, if it has time to muster
    army.siege_progress = 0.0
    taken = sim.diplomacy.relation(attacker.id, defender.id).war.tiles_taken[attacker.id]
    for _ in range(ticks):
        sim.tick += 1
        army.state, army.path = "marching", [target]
        if sim.diplomacy.relation(attacker.id, defender.id).war is None:
            break
        sim.military._besiege(attacker, army, sim.tick, [])
    war = sim.diplomacy.relation(attacker.id, defender.id).war
    return army.siege_progress + ((war.tiles_taken[attacker.id] - taken) if war else 1.0)


def test_the_betrayed_civ_is_off_guard_only_for_the_opening(sim):
    traitor, victim = sim.civs[0], sim.civs[1]
    ally_up(sim, traitor, victim)
    make_neighbours(sim, traitor, victim)
    traitor.resources["gold"] = 300
    sim.diplomacy.set_intents(traitor.id, {victim.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    tick(sim)
    war = sim.diplomacy.relation(traitor.id, victim.id).war
    assert war.betrayer == traitor.id

    assert siege(sim, traitor, victim, 3) > 0, "off guard, the defender gives ground"
    assert sim.tick < war.surprise_until

    # Once the surprise has passed, the same army is held off by the militia on home ground.
    sim.tick = war.surprise_until
    assert siege(sim, traitor, victim, 10) == 0


def test_without_betrayal_the_same_attacker_makes_no_headway(sim):
    a, b = sim.civs[0], sim.civs[1]
    betray(sim, a, b)  # never allied: an ordinary war
    assert siege(sim, a, b, 10) == 0


def test_walking_away_then_attacking_soon_after_still_counts(sim):
    traitor, victim = sim.civs[0], sim.civs[1]
    ally_up(sim, traitor, victim)
    sim.diplomacy.set_intents(traitor.id, {victim.id: Intent(Stance.IGNORE)})
    tick(sim, 5)
    assert sim.diplomacy.relation(traitor.id, victim.id).status == "peace"
    assert not sim.diplomacy.distrusted(traitor.id, sim.tick), "ending an alliance is not itself punished"
    betray(sim, traitor, victim)
    assert sim.diplomacy.relation(traitor.id, victim.id).war.betrayer == traitor.id


def test_attacking_a_long_ago_ally_is_an_ordinary_war(sim):
    a, b = sim.civs[0], sim.civs[1]
    ally_up(sim, a, b)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.IGNORE)})
    tick(sim, rules.BETRAYAL_WINDOW + 5)
    betray(sim, a, b)
    assert sim.diplomacy.relation(a.id, b.id).war.betrayer is None
    assert not sim.diplomacy.distrusted(a.id, sim.tick)


# -- 3. reputation -----------------------------------------------------------

def test_betrayers_are_distrusted_for_fifty_ticks_and_nobody_else_is(sim):
    traitor, victim, third, fourth = sim.civs
    ally_up(sim, traitor, victim)
    ally_up(sim, third, fourth)
    betray(sim, traitor, victim)
    start = sim.diplomacy.relation(traitor.id, victim.id).war.start
    assert rules.DISTRUST_TICKS == 50
    assert sim.diplomacy.distrust_until[traitor.id] == start + 50
    assert sim.diplomacy.distrusted(traitor.id, start + 49) and not sim.diplomacy.distrusted(traitor.id, start + 50)
    for civ in (victim, third, fourth):
        assert not sim.diplomacy.distrusted(civ.id, sim.tick)
    assert sim.diplomacy.relation(third.id, fourth.id).status == "alliance", "honest alliances are untouched"
    context = stance_context(sim, third)
    assert neighbour(context, traitor)["distrusted_ticks_left"] > 0
    assert neighbour(context, victim)["distrusted_ticks_left"] == 0


def test_nobody_allies_with_a_betrayer_until_the_distrust_passes(sim):
    traitor, victim, third, _ = sim.civs
    ally_up(sim, traitor, victim)
    betray(sim, traitor, victim)
    for civ in (traitor, third):
        civ.resources["gold"] = 300
    sim.diplomacy.set_intents(traitor.id, {third.id: Intent(Stance.ALLY), victim.id: sim.diplomacy.intent(traitor.id, victim.id)})
    sim.diplomacy.set_intents(third.id, {traitor.id: Intent(Stance.ALLY)})
    tick(sim, 5)
    assert sim.diplomacy.relation(traitor.id, third.id).status == "peace"

    sim.tick = sim.diplomacy.distrust_until[traitor.id]
    tick(sim)
    assert sim.diplomacy.relation(traitor.id, third.id).status == "alliance"


def test_a_betrayer_pays_more_and_gets_less_in_trade(sim):
    traitor, victim, third, fourth = sim.civs
    ally_up(sim, traitor, victim)
    betray(sim, traitor, victim)
    for civ, give in ((traitor, "wood"), (third, "stone"), (fourth, "wood")):
        civ.resources.update(gold=100, wood=0, stone=0)
        civ.resources[give] = 200
    keep = {victim.id: sim.diplomacy.intent(traitor.id, victim.id)}
    sim.diplomacy.set_intents(traitor.id, {third.id: Intent(Stance.TRADE, give="wood", give_rate=1.0), **keep})
    sim.diplomacy.set_intents(fourth.id, {third.id: Intent(Stance.TRADE, give="wood", give_rate=1.0)})
    sim.diplomacy.set_intents(third.id, {traitor.id: Intent(Stance.TRADE, give="stone", give_rate=1.0),
                                         fourth.id: Intent(Stance.TRADE, give="stone", give_rate=1.0)})
    for civ in (traitor, third, fourth):
        civ.diplomacy_points = 200
    tick(sim)

    shunned = sim.diplomacy.deal_between(traitor.id, third.id)
    honest = sim.diplomacy.deal_between(third.id, fourth.id)
    assert shunned and honest
    to_traitor = shunned.b_gives if shunned.a == traitor.id else shunned.a_gives
    from_traitor = shunned.a_gives if shunned.a == traitor.id else shunned.b_gives
    assert to_traitor == ("stone", 0.5), "the partner sends half of what it offered"
    assert from_traitor == ("wood", 1.0), "while the betrayer still sends in full"
    assert honest.a_gives[1] == honest.b_gives[1] == 1.0
    gain = rules.DIPLOMACY_GAIN
    assert traitor.diplomacy_points == pytest.approx(200 + gain - 4 * rules.DEAL_FEE)
    assert fourth.diplomacy_points == pytest.approx(200 + gain - rules.DEAL_FEE)


def test_a_second_betrayal_while_distrusted_adds_to_the_sentence(sim):
    traitor, first, second, _ = sim.civs
    ally_up(sim, traitor, first)
    ally_up(sim, traitor, second)
    betray(sim, traitor, first)
    until = sim.diplomacy.distrust_until[traitor.id]
    keep = {first.id: sim.diplomacy.intent(traitor.id, first.id)}
    make_neighbours(sim, traitor, second)
    traitor.resources["gold"] = 300
    sim.diplomacy.set_intents(traitor.id, {second.id: Intent(Stance.AGGRESSION, commitment=1.0), **keep})
    tick(sim, 12)
    assert sim.diplomacy.relation(traitor.id, second.id).war.betrayer == traitor.id
    assert sim.diplomacy.distrust_until[traitor.id] == until + rules.DISTRUST_TICKS
