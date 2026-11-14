"""The built-in strategist: what it decides, and that whatever it says is a valid answer."""

import copy

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Stance
from civsim.simulation import Simulation
from civsim.strategy import CheckinRequest, make_brain, parse_stances, stance_context
from civsim.strategy.utility import UtilityBrain


@pytest.fixture
def context():
    sim = Simulation(SimConfig(seed=3))
    for _ in range(60):
        sim.step()
    context = stance_context(sim, sim.civs[0])
    you = context["you"]
    you["diplomacy_points"] = 10_000
    you["max_soldiers"] = 10_000
    you["weights"] = dict(you["weights"], military=1.3)
    you["water"].update(urgency=0.0, status="comfortable")
    you.update(personality="Scholar", plan=None, soldiers=you["max_soldiers"])  # no tactics of its own; army raised
    for n in context["neighbors"]:
        n.update(relation="peace", truce=False, in_reach=True, army_vs_yours="comparable", intel=None,
                 at_war_with=[], allied_with=[], distrusted_ticks_left=0, their_stance_toward_you="trade",
                 your_current_stance="trade", war_ticks=None, water_rich=False, standing=0.0,
                 march=10, walls=1.0, caution=0.0, alliance_ticks=None, peace_ticks=60,
                 population=you["population"], territory=you["territory"])
    return context


def decide(context) -> dict[str, dict]:
    reply = UtilityBrain().decide(CheckinRequest(context["you"]["id"], context["tick"], context))
    assert reply["reason"] and len(reply["stances"]) == len(context["neighbors"])
    return {entry["civ"]: entry for entry in reply["stances"]}


def test_it_is_the_default_brain_and_needs_no_model():
    assert make_brain("utility").name == "utility"


def test_it_trades_with_equals_and_attacks_the_weak_within_reach(context):
    first, second = context["neighbors"][:2]
    assert all(entry["stance"] == "trade" for entry in decide(context).values()), "no war from parity"
    first["army_vs_yours"] = "much weaker"
    stances = decide(context)
    assert stances[first["name"]]["stance"] == "aggression"
    assert 0.4 <= stances[first["name"]]["troop_commitment"] <= 0.9
    assert stances[second["name"]]["stance"] == "trade"


@pytest.mark.parametrize("change", [
    {"truce": True}, {"in_reach": False}, {"relation": "alliance"},
])
def test_it_does_not_attack_across_a_truce_out_of_reach_or_an_ally(context, change):
    target = context["neighbors"][0]
    target.update(army_vs_yours="much weaker", **change)
    context["you"]["weights"]["military"] = 1.2  # short of the warlike, who alone turn on allies
    assert decide(context)[target["name"]]["stance"] != "aggression"


def test_it_never_proposes_a_war_it_cannot_declare(context):
    target = context["neighbors"][0]
    target["army_vs_yours"] = "much weaker"
    for lack in ({"diplomacy_points": 0}, {"max_soldiers": 0}):
        poor = copy.deepcopy(context)
        poor["you"].update(lack)
        assert decide(poor)[target["name"]]["stance"] != "aggression"


def test_it_opens_no_second_front_unless_the_target_is_helpless(context):
    enemy, other = context["neighbors"][:2]
    enemy.update(relation="war", war_ticks=20)
    other["army_vs_yours"] = "weaker"
    stances = decide(context)
    assert stances[enemy["name"]]["stance"] == "aggression", "an even war is kept up while it is young"
    assert stances[other["name"]]["stance"] != "aggression"


def test_it_seeks_peace_in_a_war_that_is_lost_or_has_dragged_on(context):
    enemy = context["neighbors"][0]
    enemy.update(relation="war", war_ticks=20, army_vs_yours="stronger")
    assert decide(context)[enemy["name"]]["stance"] == "aggression", "a war is given a season first"
    context["you"]["routed_ticks_ago"] = 5
    assert decide(context)[enemy["name"]]["stance"] == "ignore", "unless the army has just been broken"
    context["you"]["routed_ticks_ago"] = None
    enemy["war_ticks"] = 60
    assert decide(context)[enemy["name"]]["stance"] == "ignore"
    enemy.update(army_vs_yours="comparable", war_ticks=400)
    assert decide(context)[enemy["name"]]["stance"] == "ignore"
    enemy.update(army_vs_yours="much weaker")
    assert decide(context)[enemy["name"]]["stance"] == "aggression", "but a winning war is finished"


def test_it_allies_against_a_shared_enemy_and_against_a_threat(context):
    enemy, friend = context["neighbors"][:2]
    enemy.update(relation="war", war_ticks=20)
    friend["at_war_with"] = [enemy["name"]]
    assert decide(context)[friend["name"]]["stance"] == "ally"

    enemy.update(relation="peace", war_ticks=None, their_stance_toward_you="aggression", army_vs_yours="stronger")
    friend["at_war_with"] = []
    stances = decide(context)
    assert stances[friend["name"]]["stance"] == "ally"
    assert stances[enemy["name"]]["stance"] == "ignore", "no trade with someone about to attack"


def test_a_thirsty_civ_courts_whoever_has_water_and_fights_for_it_only_as_a_last_resort(context):
    wet = context["neighbors"][0]
    wet.update(water_rich=True, army_vs_yours="much weaker")
    context["you"]["water"].update(urgency=0.5, status="short")
    assert decide(context)[wet["name"]]["stance"] != "aggression"
    context["you"]["water"].update(urgency=0.9, status="critical")
    wet["their_stance_toward_you"] = "ignore"
    assert decide(context)[wet["name"]]["stance"] == "aggression"


def test_whole_games_get_a_valid_answer_at_every_checkin():
    brain = make_brain("utility")
    for seed in (5, 11):
        sim = Simulation(SimConfig(seed=seed))
        answered = 0
        for _ in range(1500):
            sim.step()
            for request in sim.take_requests():
                reply = brain.decide(request)
                intents, reason = parse_stances(reply, request.context, request.tick)
                assert reason and len(intents) == len(request.context["neighbors"])
                assert all(isinstance(intent.stance, Stance) for intent in intents.values())
                sim.submit(request, reply)
                answered += 1
        assert answered >= 100


def test_it_settles_on_a_long_term_strategy_and_keeps_it(context):
    reply = UtilityBrain().decide(CheckinRequest(0, context["tick"], context))
    strategy = reply["strategy"]
    assert strategy["kind"] in ("science", "prosperity", "expansion") and strategy["target"] is None, "nobody to beat"
    weak = context["neighbors"][0]
    weak["army_vs_yours"] = "much weaker"
    strategy = UtilityBrain().decide(CheckinRequest(0, context["tick"], context))["strategy"]
    assert (strategy["kind"], strategy["target"], strategy["focus"]) == ("conquest", weak["name"], "military")
    assert strategy["text"] == f"Conquer {weak['name']}"
    # Once chosen it is kept while it still makes sense, even if another has drawn level.
    other = context["neighbors"][1]
    other["army_vs_yours"] = "much weaker"
    context["you"]["strategy"] = {"kind": "conquest", "target": other["name"]}
    assert UtilityBrain().decide(CheckinRequest(0, context["tick"], context))["strategy"]["target"] == other["name"]
    # Outmatched and threatened, survival comes first.
    for n in context["neighbors"]:
        n.update(army_vs_yours="much stronger", their_stance_toward_you="aggression")
    assert UtilityBrain().decide(CheckinRequest(0, context["tick"], context))["strategy"]["kind"] == "survival"


def test_a_grudge_makes_an_attack_likelier_and_a_friendship_makes_it_less(context):
    target = context["neighbors"][0]
    target["army_vs_yours"] = "weaker"
    context["you"]["weights"]["military"] = 0.75
    target["standing"] = 0.0
    assert decide(context)[target["name"]]["stance"] != "aggression", "not worth it on the numbers alone"
    target["standing"] = -1.5
    assert decide(context)[target["name"]]["stance"] == "aggression", "but it has not been forgiven"
    context["you"]["weights"]["military"] = 1.3
    target.update(army_vs_yours="much weaker", standing=0.0)
    assert decide(context)[target["name"]]["stance"] == "aggression"


def test_the_sim_remembers_deeds_and_takes_up_the_strategy():
    sim = Simulation(SimConfig(seed=3))
    diplomacy = sim.diplomacy
    assert all(value == 0.0 for value in diplomacy.standing.values())
    diplomacy.remember(0, 1, -1.0)
    diplomacy.remember(0, 1, -5.0)
    assert diplomacy.standing[(0, 1)] == -3.0 and diplomacy.standing[(1, 0)] == 0.0
    brain = make_brain("utility")
    for _ in range(200):
        sim.step_with(brain)
    # 200 days of fading alone leave about -2.2; what the two do meanwhile (a trade deal, say)
    # can soften it a little more, but not wipe it out.
    assert -3.0 < diplomacy.standing[(0, 1)] < -1.5, "it fades, slowly"
    assert stance_context(sim, sim.civs[0])["neighbors"][0]["standing"] == round(diplomacy.standing[(0, 1)], 2)
    for civ in sim.civs:
        assert civ.strategy and civ.strategy_kind and civ.focus in ("military", "science", "economy", "expansion")
        assert civ.born is not None and civ.personality.name == civ.born.name


def test_a_war_on_a_civ_close_to_ruling_the_map_is_not_given_up(context):
    enemy = context["neighbors"][0]
    enemy.update(relation="war", war_ticks=400, army_vs_yours="comparable")
    assert decide(context)[enemy["name"]]["stance"] == "ignore", "an ordinary long war is ended"
    enemy["victory_share"] = 0.9
    reply = UtilityBrain().decide(CheckinRequest(context["you"]["id"], context["tick"], context))
    assert {e["civ"]: e for e in reply["stances"]}[enemy["name"]]["stance"] == "aggression"
    assert "close to ruling the map" in reply["reason"]


def test_a_civ_close_to_winning_pushes_for_the_prizes_that_would_finish_it(context):
    target = context["neighbors"][0]
    target["prize"] = {"region": "Goldcrown", "value": 2.5, "why": "2 gold mines"}
    brain = UtilityBrain()
    args = lambda: (context["you"], target, 2.0, 2.0, 1.3, 0.0, False, True, False, None,  # noqa: E731
                    {"kind": "conquest", "target": None}, {})
    context["you"]["victory"] = {"regions": 5, "regions_needed": 20, "seats": [0, 3], "missing_seats": [], "share": 0.25}
    before, _ = brain._attack(*args())
    context["you"]["victory"]["share"] = 0.85
    after, why = brain._attack(*args())
    assert after == pytest.approx(before + brain.p.LAST_PUSH + brain.p.FINISH_PUSH)
    assert "Goldcrown" in why


def test_it_judges_a_war_by_how_it_is_going(context):
    enemy = context["neighbors"][0]
    course = {"castles_won": 0, "castles_lost": 0, "our_losses": 0, "their_losses": 0, "siege": 0.0}
    enemy.update(relation="war", war_ticks=400, army_vs_yours="comparable", war_course=dict(course))
    assert decide(context)[enemy["name"]]["stance"] == "ignore", "an even war that drags on is given up"
    enemy["war_course"] = course | {"siege": 0.6}
    assert decide(context)[enemy["name"]]["stance"] == "aggression", "but not with a castle nearly taken"
    enemy["war_course"] = course | {"castles_won": 2}
    assert decide(context)[enemy["name"]]["stance"] == "aggression", "nor while it is being won"
    enemy.update(war_ticks=100, war_course=course | {"castles_lost": 2})
    assert decide(context)[enemy["name"]]["stance"] == "ignore", "a war being lost is ended, though the odds look fair"


def test_unrest_from_a_long_endgame_peace_pushes_toward_war_not_away(context):
    target = context["neighbors"][0]
    brain = UtilityBrain()
    args = lambda: (context["you"], target, 2.0, 2.0, 1.3, 0.0, False, True, False, None,  # noqa: E731
                    {"kind": "conquest", "target": None}, {})
    calm, _ = brain._attack(*args())
    context["you"]["unrest"] = True
    assert brain._attack(*args())[0] == 0.0, "a new reign's unrest starts no war"
    context["you"]["idle_realm"] = True
    restless, _ = brain._attack(*args())
    assert restless == pytest.approx(calm + brain.p.IDLE_REALM)
