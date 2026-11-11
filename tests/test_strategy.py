import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Stance
from civsim.diplomacy.rules import MAX_RATE
from civsim.simulation import Simulation
from civsim.strategy import CHECKIN_INTERVAL, RuleBrain, make_brain, parse_stances, stance_context
from civsim.strategy.checkin import CheckinRequest


class ScriptedBrain:
    """A brain that answers every check-in with whatever the function it was given makes of it."""

    name = "scripted"

    def __init__(self, reply):
        self.reply = reply

    def decide(self, request):
        return self.reply(request.context)


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def entry(civ, stance, **fields):
    base = {"civ": civ, "stance": stance, "give": "none", "give_per_tick": 0, "want": "none",
            "want_per_tick": 0, "troop_commitment": 0}
    return {**base, **fields}


# -- validating replies ------------------------------------------------------

def test_well_formed_reply_becomes_intents(sim):
    civ = sim.civs[0]
    context = stance_context(sim, civ)
    a, b, c = (n["name"] for n in context["neighbors"])
    reply = {"reason": "  Trade with one,\nfight another.  ", "stances": [
        entry(a, "trade", give="wood", give_per_tick=0.8, want="ore", want_per_tick=0.4),
        entry(b.upper(), "aggression", troop_commitment=0.75),
        entry(c, "ally", give="food", give_per_tick=1, want="stone", want_per_tick=1),
    ]}
    intents, reason = parse_stances(reply, context, tick=7)
    ids = [n["id"] for n in context["neighbors"]]
    assert reason == "Trade with one, fight another."
    assert intents[ids[0]].stance is Stance.TRADE
    assert (intents[ids[0]].give, intents[ids[0]].give_rate, intents[ids[0]].want) == ("wood", 0.8, "ore")
    assert intents[ids[1]].stance is Stance.AGGRESSION and intents[ids[1]].commitment == 0.75
    assert intents[ids[2]].stance is Stance.ALLY and intents[ids[2]].give == "food"
    assert all(intent.tick == 7 for intent in intents.values())


@pytest.mark.parametrize("reply", [None, "war", [], {}, {"stances": "all of them"}, {"stances": [1, None, "x"]},
                                   {"stances": [{"civ": "Atlantis", "stance": "trade"}]},
                                   {"stances": [{"stance": "aggression"}]}])
def test_garbage_replies_change_nothing(sim, reply):
    intents, reason = parse_stances(reply, stance_context(sim, sim.civs[0]), tick=1)
    assert intents == {} and reason == ""


def test_out_of_range_values_are_clamped_and_gaps_filled(sim):
    civ = sim.civs[0]
    civ.resources.update(food=100, wood=240, stone=100, ore=0, gold=100, water=100)
    civ.capacity.update(wood=10, stone=10, ore=0)
    context = stance_context(sim, civ)
    a, b, c = (n["name"] for n in context["neighbors"])
    ids = [n["id"] for n in context["neighbors"]]
    reply = {"reason": 42, "stances": [
        entry(a, "trade", give="wood", give_per_tick=999, want="uranium", want_per_tick="lots"),
        entry(b, "WAR", troop_commitment=17),
        entry(c, "trade"),  # no offer at all
        entry(a, "aggression"),  # second entry for the same civ is ignored
    ]}
    intents, reason = parse_stances(reply, context, tick=1)
    assert reason == ""
    assert intents[ids[0]].stance is Stance.TRADE
    assert intents[ids[0]].give_rate == MAX_RATE and intents[ids[0]].want is None
    assert intents[ids[1]].stance is Stance.AGGRESSION and intents[ids[1]].commitment == 1.0
    # The empty trade falls back to "my fullest stockpile for what I lack".
    assert intents[ids[2]].give == "wood" and intents[ids[2]].want == "ore"
    assert "bogus" not in {i.stance.value for i in intents.values()}


def test_unknown_stance_means_ignore(sim):
    context = stance_context(sim, sim.civs[0])
    name, civ_id = context["neighbors"][0]["name"], context["neighbors"][0]["id"]
    intents, _ = parse_stances({"stances": [entry(name, "befriend")]}, context, tick=1)
    assert intents[civ_id].stance is Stance.IGNORE


# -- check-in scheduling -----------------------------------------------------

def test_each_civ_checks_in_once_per_interval_and_never_piles_up(sim):
    seen: dict[int, list[int]] = {civ.id: [] for civ in sim.civs}
    held = []
    for _ in range(3 * max(CHECKIN_INTERVAL, 2)):
        sim.step()
        for request in sim.take_requests():
            seen[request.civ_id].append(request.tick)
            held.append(request)
    assert all(len(ticks) == 1 for ticks in seen.values()), "unanswered check-ins are not repeated"
    assert all(civ.thinking for civ in sim.civs)

    for request in held:
        sim.submit(request, None)
    for _ in range(CHECKIN_INTERVAL):
        sim.step()
    assert len(sim.take_requests()) == len(sim.civs), "answering frees the civ for its next check-in"


def test_no_answer_keeps_previous_stances(sim):
    civ = sim.civs[0]
    context = stance_context(sim, civ)
    target = context["neighbors"][0]
    request = CheckinRequest(civ.id, sim.tick, context)
    sim.submit(request, {"reason": "x", "stances": [entry(target["name"], "aggression", troop_commitment=0.5)]})
    sim.step()
    assert sim.diplomacy.intent(civ.id, target["id"]).stance is Stance.AGGRESSION
    assert civ.last_reason == "x"

    sim.submit(request, None)
    sim.submit(request, {"stances": "nonsense"})
    sim.step()
    assert sim.diplomacy.intent(civ.id, target["id"]).stance is Stance.AGGRESSION


# -- brains ------------------------------------------------------------------

def test_a_scripted_run_forms_a_deal_and_fights_a_war():
    """A scripted brain that always trades with everyone except one civ, which it attacks."""
    sim = Simulation(SimConfig(seed=3))
    villain = sim.civs[0].name

    def reply(context: dict) -> dict:
        me = context["you"]["name"]
        stances = []
        # The villain picks on a neighbour it can actually get at.
        reachable = [n for n in context["neighbors"] if n["in_reach"]] or context["neighbors"]
        for n in context["neighbors"]:
            if me == villain and n == reachable[0]:
                stances.append(entry(n["name"], "aggression", troop_commitment=1.0))
            else:
                give, want = ("food", "wood") if me < n["name"] else ("wood", "food")  # so offers complement
                stances.append(entry(n["name"], "trade", give=give, give_per_tick=0.5, want=want, want_per_tick=0.5))
        return {"reason": f"{me} decides.", "stances": stances}

    brain = ScriptedBrain(reply)
    kinds: dict[str, int] = {}
    for _ in range(1500):
        for event in sim.step_with(brain):
            kinds[event["kind"]] = kinds.get(event["kind"], 0) + 1
    assert kinds.get("trade", 0) > 0
    assert kinds.get("war", 0) > 0, "the aggressor's border reached its target and war was declared"
    assert sim.civs[0].last_reason == f"{villain} decides."
    owned = [tile for civ in sim.civs for tile in civ.territory]
    assert len(owned) == len(set(owned))


def test_rule_brain_runs_are_deterministic_and_active():
    def run() -> tuple[list[dict], list[int]]:
        sim = Simulation(SimConfig(seed=5))
        brain = RuleBrain()
        for _ in range(800):
            sim.step_with(brain)
        return sim.diplomacy.history, [len(civ.territory) for civ in sim.civs]

    first, second = run(), run()
    assert first == second
    assert any("trades" in entry["text"] for entry in first[0])


def test_an_unknown_strategist_is_rejected():
    assert make_brain().name == "utility" and make_brain("rules").name == "rules"
    with pytest.raises(ValueError):
        make_brain("telepathy")
