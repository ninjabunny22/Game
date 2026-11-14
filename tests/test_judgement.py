"""Better judgement: wars are forecast, prepared and stuck to, lessons are learned, tribute is
demanded and paid, and armies pick their fights."""

import pytest

from civsim.config import SimConfig, game_config
from civsim.diplomacy import Intent, Stance, rules
from civsim.military import Army
from civsim.military import warfare as military_rules
from civsim.simulation import Simulation
from civsim.strategy import CheckinRequest, parse_stances, stance_context
from civsim.strategy.utility import DEFAULT, UtilityBrain

from test_utility_brain import context, decide  # noqa: F401


def reply(context, **tweaks):  # noqa: F811
    return UtilityBrain(**tweaks).decide(CheckinRequest(context["you"]["id"], context["tick"], context))


def entry(context, name):  # noqa: F811
    return next(e for e in reply(context)["stances"] if e["civ"] == name)


# -- the forecast ------------------------------------------------------------

def test_a_war_is_judged_by_more_than_the_size_of_the_armies(context):  # noqa: F811
    target, other = context["neighbors"][:2]
    target["army_vs_yours"] = "weaker"
    context["you"]["weights"]["military"] = 1.3
    assert decide(context)[target["name"]]["stance"] == "aggression"
    for change in ({"march": None},  # no way to get an army there
                   {"march": 200},  # too far
                   {"allied_with": [other["name"]]},  # it has a friend our size
                   {"caution": 0.6}):  # it has beaten us before
        harder = {**context, "neighbors": [dict(n, **change) if n is target else n for n in context["neighbors"]]}
        assert decide(harder)[target["name"]]["stance"] != "aggression", change


def test_only_one_war_is_prepared_at_a_time(context):  # noqa: F811
    a, b = context["neighbors"][:2]
    a["army_vs_yours"] = b["army_vs_yours"] = "much weaker"
    context["you"]["weights"]["military"] = 1.4
    stances = decide(context)
    assert [s["stance"] for s in stances.values()].count("aggression") == 1


# -- preparing and striking --------------------------------------------------

def test_a_war_is_mustered_for_before_it_is_declared(context):  # noqa: F811
    target = context["neighbors"][0]
    you = context["you"]
    target["army_vs_yours"] = "weaker"
    you["weights"]["military"] = 1.4
    you["soldiers"] = 0
    first = reply(context)
    chosen = next(e for e in first["stances"] if e["civ"] == target["name"])
    assert chosen["stance"] == "aggression" and chosen["hold"] is True
    assert first["plan"]["target"] == target["name"] and "Mustering" in first["plan"]["text"]
    intents, _ = parse_stances(first, context, context["tick"])
    assert intents[target["id"]].hold is True

    # The army raised and the days served, it strikes.
    you.update(soldiers=you["max_soldiers"], plan={"target": target["name"], "since": context["tick"] - 60})
    later = reply(context)
    chosen = next(e for e in later["stances"] if e["civ"] == target["name"])
    assert chosen["stance"] == "aggression" and not chosen.get("hold")
    assert later["plan"]["since"] == context["tick"] - 60 and "Marching" in later["plan"]["text"]


def test_a_plan_is_stuck_to_but_not_for_ever(context):  # noqa: F811
    a, b = context["neighbors"][:2]
    you = context["you"]
    you["weights"]["military"] = 1.4
    a["army_vs_yours"], b["army_vs_yours"] = "weaker", "much weaker"
    assert reply(context)["plan"]["target"] == b["name"], "the weaker of the two, with nothing else to go on"
    you["plan"] = {"target": a["name"], "since": context["tick"] - 10}
    b["army_vs_yours"] = "weaker"
    assert reply(context)["plan"]["target"] == a["name"], "the war already being prepared is seen through"
    you["plan"] = {"target": a["name"], "since": context["tick"] - DEFAULT.PLAN_MAX - 1}
    a["army_vs_yours"] = "comparable"
    assert reply(context)["plan"]["target"] == b["name"], "an old plan is dropped"


def test_the_sim_holds_a_mustering_civ_back_and_raises_its_army():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    a.population, a.soldiers, a.diplomacy_points = 400, 100, 300
    relation = sim.diplomacy.relation(a.id, b.id)
    sim.diplomacy._reach_cache[(a.id, b.id)] = (0, True)
    sim.diplomacy.intents[(a.id, b.id)] = Intent(Stance.AGGRESSION, commitment=0.9, hold=True)
    sim.diplomacy._resolve_pair(a.id, b.id, 5, [])
    assert relation.status == "peace", "mustering: not yet"
    sim.diplomacy._issue_orders(5)
    assert a.soldier_target == pytest.approx(0.9 * sim.diplomacy.mobilization_cap(a) * a.population)
    sim.diplomacy.intents[(a.id, b.id)] = Intent(Stance.AGGRESSION, commitment=0.9)
    sim.diplomacy._resolve_pair(a.id, b.id, 6, [])
    assert relation.status == "war"


# -- tribute -------------------------------------------------------------------

def test_tribute_is_demanded_of_the_much_weaker_and_paid_by_the_meek(context):  # noqa: F811
    target = context["neighbors"][0]
    you = context["you"]
    target["army_vs_yours"] = "much weaker"
    you["weights"]["military"] = 1.0
    you["plan"] = {"target": target["name"], "since": context["tick"] - 60}
    asked = entry(context, target["name"])
    assert asked["stance"] == "aggression" and asked["demand"] is True and asked["hold"] is True
    target["your_demand_ticks"] = DEFAULT.DEMAND_PATIENCE
    refused = entry(context, target["name"])
    assert refused["stance"] == "aggression" and not refused.get("hold"), "unanswered: it is war"

    # On the other side of it: the weak and peaceable pay, the proud do not.
    target.update(army_vs_yours="much stronger", demands_tribute=True, your_demand_ticks=None)
    you["plan"] = None
    assert entry(context, target["name"])["pay_tribute"] is True
    you["weights"]["military"] = 1.4
    assert not entry(context, target["name"]).get("pay_tribute")


def test_paying_tribute_buys_a_truce():
    sim = Simulation(SimConfig(seed=3))
    d = sim.diplomacy
    a, b = sim.civs[0], sim.civs[1]
    relation = d.relation(a.id, b.id)
    for res in b.resources:
        b.resources[res] = 100.0
    d.intents[(a.id, b.id)] = Intent(Stance.AGGRESSION, commitment=0.8, hold=True, demand=True)
    events = []
    d._resolve_pair(a.id, b.id, 10, events)
    assert (a.id, b.id) in d.demands and any("demands tribute" in e["text"] for e in events)
    assert stance_context(sim, b)["neighbors"][0]["demands_tribute"] is True
    d.intents[(b.id, a.id)] = Intent(Stance.TRADE, pay=True)
    d._resolve_pair(a.id, b.id, 11, events)
    assert (a.id, b.id) not in d.demands and relation.status == "peace"
    assert b.resources["gold"] == pytest.approx(100.0 * (1 - rules.DEMAND_TRIBUTE))
    assert relation.truce_until == 11 + rules.DEMAND_TRUCE
    # A demand nobody answers is forgotten in time.
    d.demands[(b.id, a.id)] = 20
    d._resolve_pair(a.id, b.id, 21 + rules.DEMAND_LAPSE, [])
    assert (b.id, a.id) not in d.demands


def test_a_ruler_is_asked_for_tribute_and_may_pay_or_refuse():
    sim = Simulation(SimConfig(seed=3))
    d, ruler = sim.diplomacy, sim.ruler
    a, b = sim.civs[0], sim.civs[1]
    ruler.command("take_control", {"civ": b.id})
    d.demands[(a.id, b.id)] = sim.tick
    offers = {(p["civ"], p["kind"]) for p in ruler.proposals()}
    assert (a.id, "tribute") in offers
    gold = b.resources["gold"]
    assert ruler.command("answer_proposal", {"civ": a.id, "kind": "tribute", "accept": True}) is None
    assert (a.id, b.id) not in d.demands and b.resources["gold"] < gold
    assert any("pays" in e["text"] for e in ruler.notices())


# -- what wars teach -----------------------------------------------------------

def test_a_beaten_civ_grows_cautious_and_a_betrayed_one_never_trusts_again(context):  # noqa: F811
    sim = Simulation(SimConfig(seed=3))
    d = sim.diplomacy
    a, b = sim.civs[0], sim.civs[1]
    d._start_war(a, b, 0, {a.id})
    relation = d.relation(a.id, b.id)
    relation.war.regions_taken[a.id] = rules.PEACE_LEAD
    d._make_peace(relation, 100, [], "peace")
    assert d.caution[(b.id, a.id)] == pytest.approx(rules.LESSON_LOST)
    assert d.caution[(a.id, b.id)] == pytest.approx(rules.LESSON_WON)
    seen = next(n for n in stance_context(sim, b)["neighbors"] if n["id"] == a.id)
    assert seen["caution"] == pytest.approx(rules.LESSON_LOST)
    for _ in range(10):
        d.learn(b.id, a.id, rules.LESSON_LOST)
    assert d.caution[(b.id, a.id)] == rules.CAUTION_RANGE[1]

    d._start_war(a, b, 500, {a.id})
    d._betray(d.relation(a.id, b.id).war, a, b, 500, [])
    assert next(n for n in stance_context(sim, b)["neighbors"] if n["id"] == a.id)["betrayed_you"] is True
    friend = context["neighbors"][0]
    friend.update(their_stance_toward_you="ally", at_war_with=["X"])
    context["neighbors"][1].update(relation="war", war_ticks=10, name="X")
    assert decide(context)[friend["name"]]["stance"] == "ally"
    friend["betrayed_you"] = True
    assert decide(context)[friend["name"]]["stance"] != "ally"


def test_an_ally_who_joins_a_war_is_remembered_and_one_who_stays_out_too():
    sim = Simulation(SimConfig(seed=3))
    d = sim.diplomacy
    a, b, c = sim.civs[0], sim.civs[1], sim.civs[2]
    d.relation(a.id, c.id).status = "alliance"
    d._start_war(a, b, 0, {a.id})
    for pair in d.standing:
        d.standing[pair] = 0.0
    d._end_war(d.relation(a.id, b.id), rules.HELP_WAR, [], rules.TRUCE, "peace")
    assert d.standing[(a.id, c.id)] == pytest.approx(rules.HELP_STAYED_AWAY)


# -- keeping its word ----------------------------------------------------------

def test_a_goal_is_held_for_most_of_a_year(context):  # noqa: F811
    you = context["you"]
    you["weights"].update(science=2.0, wealth=0.5, expansion=0.5)
    you["strategy"] = {"kind": "prosperity", "target": None, "since": context["tick"] - 10}
    assert reply(context)["strategy"]["kind"] == "prosperity", "too soon to change"
    you["strategy"]["since"] = context["tick"] - DEFAULT.STRATEGY_MIN
    assert reply(context)["strategy"]["kind"] == "science"


def test_a_new_alliance_is_kept_for_a_season(context):  # noqa: F811
    friend = context["neighbors"][0]
    friend.update(relation="alliance", intel={"military_power": context["you"]["military_power"]},
                  their_stance_toward_you="trade", standing=-2.0, alliance_ticks=10)
    assert decide(context)[friend["name"]]["stance"] == "ally"
    friend["alliance_ticks"] = DEFAULT.ALLIANCE_MIN
    assert decide(context)[friend["name"]]["stance"] != "ally"


# -- variants, tactics and difficulty -----------------------------------------

def test_the_numbers_it_decides_by_can_be_changed_and_unknown_ones_are_refused(context):  # noqa: F811
    target = context["neighbors"][0]
    target["army_vs_yours"] = "weaker"
    context["you"]["weights"]["military"] = 1.3
    timid = reply(context, ATTACK_THRESHOLD=5.0)
    assert next(e for e in timid["stances"] if e["civ"] == target["name"])["stance"] != "aggression"
    with pytest.raises(ValueError):
        UtilityBrain(NOT_A_NUMBER=1)


def test_builders_wait_and_expansionists_raid(context):  # noqa: F811
    target = context["neighbors"][0]
    you = context["you"]
    target["army_vs_yours"] = "weaker"
    you["weights"]["military"] = 1.3
    you["plan"] = {"target": target["name"], "since": context["tick"] - 15}
    you["personality"] = "Expansionist"
    assert not entry(context, target["name"]).get("hold"), "fifteen days is plenty for a raider"
    you["personality"] = "Builder"
    assert entry(context, target["name"])["hold"] is True


def test_the_other_civs_go_easier_or_harder_on_a_human_ruler(context):  # noqa: F811
    target = context["neighbors"][0]
    target["army_vs_yours"] = "weaker"
    context["you"]["weights"]["military"] = 0.95
    context["player"] = target["name"]
    stances = {}
    for level in ("easy", "normal", "hard"):
        context["difficulty"] = level
        stances[level] = decide(context)[target["name"]]["stance"]
    assert stances["easy"] != "aggression" and stances["hard"] == "aggression"
    assert Simulation(game_config("small", seed=1, difficulty="easy")).config.difficulty == "easy"


# -- armies ----------------------------------------------------------------------

def test_an_army_falls_back_from_a_fight_it_cannot_win():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    military, world = sim.military, sim.world
    sim.diplomacy._start_war(a, b, 0, {a.id})
    spot = next(t for t in sorted(b.territory) if not world.is_water(t) and t not in world.capital_tiles)
    beside = next(t for t in world.neighbors(spot) if not world.is_open_water(t))
    mine = Army(military.next_id(), a.id, spot, "field", target_civ=b.id, units={"spearman": 20.0}, state="marching",
                commander=military._new_commander(a, 0))
    theirs = Army(military.next_id(), b.id, beside, "field", target_civ=a.id, units={"spearman": 200.0}, state="marching")
    a.armies.append(mine)
    b.armies.append(theirs)
    assert military._outmatched(a, mine) and not military._outmatched(b, theirs)
    military._plan(a, mine, 10)
    assert mine.state == "retreating"


def test_friends_beside_an_army_count_and_a_siege_is_not_lightly_given_up():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    military, world = sim.military, sim.world
    sim.diplomacy._start_war(a, b, 0, {a.id})
    spot = next(t for t in sorted(b.territory) if not world.is_water(t) and t not in world.capital_tiles)
    beside = next(t for t in world.neighbors(spot) if not world.is_open_water(t))
    mine = Army(military.next_id(), a.id, spot, "field", target_civ=b.id, units={"spearman": 20.0}, state="marching")
    theirs = Army(military.next_id(), b.id, beside, "field", target_civ=a.id, units={"spearman": 45.0}, state="marching")
    a.armies.append(mine)
    b.armies.append(theirs)
    assert military._outmatched(a, mine)
    mine.state = "besieging"
    assert not military._outmatched(a, mine), "at the walls it takes a greater threat"
    mine.state = "marching"
    a.armies.append(Army(military.next_id(), a.id, spot, "field", target_civ=b.id, units={"spearman": 20.0}, state="marching"))
    assert not military._outmatched(a, mine), "a second column beside it counts on its side"


def test_an_attacking_army_musters_at_home_and_keeps_to_its_castle():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    military = sim.military
    sim.diplomacy._start_war(a, b, 0, {a.id})
    army = Army(military.next_id(), a.id, a.capital.tile, "field", target_civ=b.id, units={"spearman": 5.0},
                commander=military._new_commander(a, 0))
    a.armies.append(army)
    a.soldiers = 5.0
    military._sync(a)  # its garrison, empty: nobody waiting at home to fill the ranks
    military._plan(a, army, 100)
    assert army.state == "idle" and army.muster_since == 100, "a few soldiers wait for the rest"
    military._plan(a, army, 100 + military_rules.MUSTER_DAYS)
    assert army.state == "marching", "but not for ever"
    target = army.objective
    assert target in {s.tile for s in b.settlements}
    army.tile = army.path[len(army.path) // 2] if army.path else army.tile
    military._plan(a, army, 200)
    assert army.objective == target, "on the way, it does not turn to another castle"


def test_columns_against_one_army_fight_as_one_side():
    def battle(columns):
        sim = Simulation(SimConfig(seed=3))
        a, b = sim.civs[0], sim.civs[1]
        military, world = sim.military, sim.world
        sim.diplomacy._start_war(a, b, 0, {a.id})
        spot, beside = next((t, n) for t in range(len(world.owner)) if world.owner[t] < 0 and world.walkable(t)
                            for n in world.neighbors(t) if world.owner[n] < 0 and world.walkable(n))  # open ground
        mine = [Army(military.next_id(), a.id, spot, "field", target_civ=b.id, units={"spearman": 30.0},
                     state="marching") for _ in range(columns)]
        theirs = Army(military.next_id(), b.id, beside, "field", target_civ=a.id, units={"spearman": 100.0},
                      state="marching")
        a.armies += mine
        b.armies.append(theirs)
        a.soldiers, b.soldiers = 30.0 * columns, 100.0  # what is on the field, and nobody else
        military._sync(a)
        military._sync(b)
        for tick in range(1, 4):
            military._fight(tick, [])
        return [x.state for x in mine]
    assert battle(1) == ["retreating"], "one column of 30 breaks at once against 100"
    assert "retreating" not in battle(3), "three of them stand together"


def test_a_castle_held_under_siege_starves_until_it_can_be_taken():
    sim = Simulation(SimConfig(seed=3))
    a, b = sim.civs[0], sim.civs[1]
    military, world = sim.military, sim.world
    sim.diplomacy._start_war(a, b, 0, {a.id})
    target = b.capital.tile
    b.population = 2000.0  # a strong militia: far more than the besiegers at first
    a.soldiers, b.soldiers = 30.0, 0.0
    military._sync(a)
    military._sync(b)
    army = Army(military.next_id(), a.id, next(iter(world.neighbors(target))), "field", target_civ=b.id,
                units={"spearman": 30.0}, state="marching", path=[target])
    a.armies.append(army)
    events: list = []
    military._besiege(a, army, 1, events)
    assert army.state == "besieging" and army.siege_progress == 0.0, "too strongly held at first"
    for day in range(2, 100):
        army.path = [target]
        military._besiege(a, army, day, events)
    assert army.siege_progress > 0.0, "but hunger tells in the end"
    assert any("are starving" in e["text"] for e in events)
