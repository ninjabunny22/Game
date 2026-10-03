import json

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Stance
from civsim.economy import produce, water_growth_factor, water_urgency
from civsim.llm import LLMError
from civsim.simulation import Simulation
from civsim.strategy import LLMBrain, RuleBrain, parse_stances, prompt, stance_context
from civsim.strategy.checkin import WATER_PRIORITY, WATER_URGENT, CheckinRequest, default_offer


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def set_water(sim, civ, supply: float, use: float, stock: float = 250.0):
    """Put a civ in a given water position: supply and use per tick, and what is in store."""
    mods = sim.modifiers[civ.id]
    mods.income["water"] = supply
    civ.upkeep["water"] = use
    civ.imports["water"] = civ.exports["water"] = 0.0
    civ.resources["water"] = stock
    return mods


def entry(civ, stance, **fields):
    base = {"civ": civ, "stance": stance, "give": "none", "give_per_tick": 0, "want": "none",
            "want_per_tick": 0, "troop_commitment": 0}
    return {**base, **fields}


# -- 1. growth -----------------------------------------------------------------

@pytest.mark.parametrize("supply, use, factor", [
    (10, 2, 1.0),     # plenty to spare
    (10, 7.5, 1.0),   # a quarter spare: still unhindered
    (10, 8.75, 0.5),  # an eighth spare: half speed
    (10, 9.5, 0.2),
    (10, 10, 0.0),    # use has caught up with supply
    (10, 14, 0.0),
])
def test_growth_eases_off_as_water_use_nears_supply(sim, supply, use, factor):
    civ = sim.civs[0]
    assert water_growth_factor(civ, set_water(sim, civ, supply, use)) == pytest.approx(factor)


def test_a_civ_stops_growing_before_it_runs_dry_not_after(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    mods.housing = 2000.0
    mods.income["water"] = 6.0  # enough for 200 people
    civ.buildings = []
    civ.population = 50
    history = []
    for _ in range(1500):
        civ.resources.update(food=250, wood=250, water=250)
        produce(civ, mods, sim.building_defs)
        history.append(civ.population)
        assert not civ.thirsty, "it never hits the wall"
    assert 150 < civ.population <= 200, "it levels off at what its water supports, with housing to spare"
    early, late = history[300] - history[200], history[1400] - history[1300]
    assert early > 5 * late >= 0, "growth slowed well before the limit rather than stopping dead at it"
    assert civ.upkeep["water"] <= mods.income["water"]


def test_trade_imports_count_as_supply_for_growth(sim):
    civ = sim.civs[0]
    mods = set_water(sim, civ, supply=10, use=10)
    assert water_growth_factor(civ, mods) == 0
    civ.imports["water"] = 4.0
    assert water_growth_factor(civ, mods) > 0.9
    civ.imports["water"], civ.exports["water"] = 0.0, 4.0
    assert water_growth_factor(civ, mods) == 0, "and water sold abroad is water used"


def test_a_water_limited_civ_stops_wanting_houses(sim):
    civ = sim.civs[0]
    civ.population = sim.modifiers[civ.id].housing
    assert sim.ai.assess_needs(civ, set_water(sim, civ, 10, 2))["growth"] > 0.9
    assert sim.ai.assess_needs(civ, set_water(sim, civ, 10, 10))["growth"] == 0


# -- 2. urgency ----------------------------------------------------------------

@pytest.mark.parametrize("supply, use, stock, urgency", [
    (10, 5, 250, 0.0),      # comfortable
    (10, 8.75, 250, 0.25),  # margin thinning
    (10, 10, 250, 0.5),     # no margin, but not yet losing ground
    (10, 12, 2000, 0.5),    # in deficit with a thousand ticks in store
    (10, 12, 400, 0.75),    # 200 ticks left
    (10, 12, 0, 1.0),       # dry
])
def test_urgency_scales_with_how_close_the_civ_is_to_running_dry(sim, supply, use, stock, urgency):
    civ = sim.civs[0]
    assert water_urgency(civ, set_water(sim, civ, supply, use, stock)) == pytest.approx(urgency)


def test_the_strategist_is_told_where_it_stands_on_water(sim):
    civ = sim.civs[0]
    set_water(sim, civ, 10, 12, 400)
    report = stance_context(sim, civ)["you"]["water"]
    assert report == {"supply_per_tick": 10.0, "use_per_tick": 12.0, "ticks_until_dry": 200,
                      "urgency": 0.75, "status": "critical", "rich": False}
    set_water(sim, civ, 10, 3)
    report = stance_context(sim, civ)["you"]["water"]
    assert report["status"] == "comfortable" and report["ticks_until_dry"] is None and report["rich"]
    other = sim.civs[1]
    set_water(sim, other, 30, 5)
    seen = next(n for n in stance_context(sim, civ)["neighbors"] if n["id"] == other.id)
    assert seen["water_rich"] is True, "who has water to spare is public"


# -- trade offers --------------------------------------------------------------

def offer(sim, civ, supply, use, stock=250.0, neighbor=None):
    set_water(sim, civ, supply, use, stock)
    return default_offer(stance_context(sim, civ)["you"], neighbor)


def test_a_comfortable_civ_does_not_chase_water(sim):
    civ = sim.civs[0]
    civ.resources.update(food=100, wood=240, stone=100, ore=0, gold=100)
    civ.capacity.update(wood=20, stone=20, ore=0)
    assert offer(sim, civ, 10, 3)["want"] == "ore"


def test_water_is_wanted_first_and_for_more_as_it_gets_scarce(sim):
    civ = sim.civs[0]
    civ.resources.update(food=100, wood=240, stone=100, ore=0, gold=100)
    civ.capacity.update(wood=20, stone=20, ore=0)
    tightening = offer(sim, civ, 10, 9.4)
    short = offer(sim, civ, 10, 10.5, 2000)
    critical = offer(sim, civ, 10, 13, 50)
    assert tightening["want"] == short["want"] == critical["want"] == "water", "ahead of the ore it also lacks"
    assert tightening["want_per_tick"] < short["want_per_tick"] < critical["want_per_tick"]
    assert critical["want_per_tick"] == 2.0, "as much as a deal can carry"


def test_water_is_never_offered_once_it_is_tightening(sim):
    civ = sim.civs[0]
    for res in civ.resources:
        civ.resources[res] = 10
    assert offer(sim, civ, 10, 3, stock=250)["give"] == "water", "plenty to spare: it is the obvious thing to sell"
    for supply, use in ((10, 8.8), (10, 9.5), (10, 12)):
        assert offer(sim, civ, supply, use, stock=250)["give"] != "water"


def test_a_water_rich_civ_sells_water_to_a_neighbour_who_asks(sim):
    civ = sim.civs[0]
    civ.resources.update(food=100, wood=240, stone=100, ore=50, gold=100)
    asking = {"their_trade_offer": {"gives": "stone", "wants": "water"}}
    other = {"their_trade_offer": {"gives": "stone", "wants": "ore"}}
    assert offer(sim, civ, 30, 5, stock=120, neighbor=asking)["give"] == "water"
    assert offer(sim, civ, 30, 5, stock=120, neighbor=other)["give"] == "wood"
    assert offer(sim, civ, 10, 9.5, stock=120, neighbor=asking)["give"] != "water", "not if it is short itself"


# -- both strategists are held to it -------------------------------------------

def test_a_models_reply_is_corrected_when_water_is_critical(sim):
    civ = sim.civs[0]
    set_water(sim, civ, 10, 13, 50)
    context = stance_context(sim, civ)
    assert context["you"]["water"]["urgency"] >= WATER_URGENT
    a, b, c = context["neighbors"]
    reply = {"reason": "Gold first.", "stances": [
        entry(a["name"], "trade", give="water", give_per_tick=1.0, want="gold", want_per_tick=1.0),
        entry(b["name"], "ally", give="wood", give_per_tick=1.0, want="stone", want_per_tick=1.0),
        entry(c["name"], "aggression", troop_commitment=0.6),
    ]}
    intents, _ = parse_stances(reply, context, tick=1)
    assert intents[a["id"]].give != "water", "it cannot sell the water it is dying for"
    assert intents[a["id"]].want == "water" and intents[b["id"]].want == "water"
    assert intents[a["id"]].want_rate > 1.0
    assert intents[c["id"]].stance is Stance.AGGRESSION, "the stance itself is still the strategist's to choose"


def test_a_models_reply_is_left_alone_when_water_is_fine(sim):
    civ = sim.civs[0]
    set_water(sim, civ, 10, 3)
    context = stance_context(sim, civ)
    name, civ_id = context["neighbors"][0]["name"], context["neighbors"][0]["id"]
    reply = {"reason": "", "stances": [entry(name, "trade", give="water", give_per_tick=1.0, want="gold", want_per_tick=1.0)]}
    intents, _ = parse_stances(reply, context, tick=1)
    assert (intents[civ_id].give, intents[civ_id].want) == ("water", "gold")


def test_a_tightening_civ_keeps_its_water_but_may_still_want_other_things(sim):
    civ = sim.civs[0]
    set_water(sim, civ, 10, 9.4)
    context = stance_context(sim, civ)
    assert WATER_PRIORITY <= context["you"]["water"]["urgency"] < WATER_URGENT
    name, civ_id = context["neighbors"][0]["name"], context["neighbors"][0]["id"]
    reply = {"reason": "", "stances": [entry(name, "trade", give="water", give_per_tick=1.0, want="gold", want_per_tick=1.0)]}
    intents, _ = parse_stances(reply, context, tick=1)
    assert intents[civ_id].give != "water" and intents[civ_id].want == "gold"


def stances_of(sim, civ) -> dict[str, dict]:
    reply = RuleBrain().decide(CheckinRequest(civ.id, sim.tick, stance_context(sim, civ)))
    return {s["civ"]: s for s in reply["stances"]}, reply["reason"]


def test_rule_brain_courts_water_rich_neighbours_in_proportion_to_thirst(sim):
    civ, rich, poor = sim.civs[0], sim.civs[1], sim.civs[2]
    civ.personality.weights["military"] = 0.8  # not warlike
    set_water(sim, rich, 40, 5)
    set_water(sim, poor, 5, 5)

    set_water(sim, civ, 10, 3)
    calm, reason = stances_of(sim, civ)
    assert calm[rich.name]["stance"] == "trade" and calm[rich.name]["want"] != "water"
    assert "water" not in reason

    set_water(sim, civ, 10, 13, 50)
    urgent, reason = stances_of(sim, civ)
    assert urgent[rich.name]["stance"] == "ally", "it ties itself to whoever has water"
    assert urgent[rich.name]["want"] == "water" and urgent[poor.name]["want"] == "water"
    assert urgent[poor.name]["stance"] == "trade"
    assert "water is critical" in reason


def test_rule_brain_fights_for_water_only_as_a_last_resort(sim):
    civ, rich = sim.civs[0], sim.civs[1]
    civ.personality.weights["military"] = 0.8
    civ.population, rich.population = 600, 100  # clearly the stronger
    civ.diplomacy_points = 300
    set_water(sim, rich, 40, 5)
    set_water(sim, civ, 10, 13, 50)
    sim.diplomacy.in_reach = lambda a, b, tick: True

    hostile, _ = stances_of(sim, civ)
    assert hostile[rich.name]["stance"] == "aggression", "nobody will sell, and the wells are failing"

    # If the water-rich neighbour is willing to deal, there is nothing to fight over.
    sim.diplomacy.intents[(rich.id, civ.id)].stance = Stance.TRADE
    willing, _ = stances_of(sim, civ)
    assert willing[rich.name]["stance"] in ("trade", "ally")

    # And a comfortable civ never does this.
    sim.diplomacy.intents[(rich.id, civ.id)].stance = Stance.IGNORE
    set_water(sim, civ, 10, 3)
    calm, _ = stances_of(sim, civ)
    assert calm[rich.name]["stance"] == "trade"


class Recorder:
    name = "recorder"

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, schema):
        self.calls.append((system, user))
        raise LLMError("not answering")


def test_the_model_is_told_about_water_in_proportion_to_urgency(sim):
    civ = sim.civs[0]
    client = Recorder()
    brain = LLMBrain(client)

    set_water(sim, civ, 10, 3)
    brain.decide(CheckinRequest(civ.id, sim.tick, stance_context(sim, civ)))
    system, user = client.calls[-1]
    assert "urgency" in system and "as urgent as food" in system and "do not chase water" in system
    assert "WATER IS" not in user, "no alarm for a comfortable civ"
    shown = json.loads(user[user.index("{"): user.rindex("}") + 1])
    assert shown["you"]["water"]["status"] == "comfortable"
    assert all("water_rich" in n for n in shown["neighbors"])

    set_water(sim, civ, 10, 13, 50)
    brain.decide(CheckinRequest(civ.id, sim.tick, stance_context(sim, civ)))
    _, user = client.calls[-1]
    assert "WATER IS CRITICAL" in user and "run dry in about 16 ticks" in user
    assert prompt.STANCE_SCHEMA["properties"]["stances"]["items"]["properties"]["want"]["enum"].count("water") == 1


def test_a_thirsty_civ_and_a_rich_neighbour_end_up_trading_water(sim):
    """End to end with the rule strategist: need on one side, plenty on the other, a deal in between."""
    thirsty, rich = sim.civs[0], sim.civs[1]
    brain = RuleBrain()
    for civ in sim.civs:
        civ.personality.weights["military"] = 0.8
        civ.diplomacy_points = 300
    thirsty.resources.update(wood=250, stone=250)
    deal = None
    for _ in range(160):
        set_water(sim, rich, 60, 5, stock=sim.modifiers[rich.id].storage["water"])
        mods = sim.modifiers[thirsty.id]
        sim.step_with(brain)
        sim.modifiers[thirsty.id].income["water"] = 0.3
        thirsty.resources["water"] = min(thirsty.resources["water"], 40)
        deal = next((d for d in sim.diplomacy.deals if {d.a, d.b} == {thirsty.id, rich.id}
                     and "water" in (d.a_gives[0], d.b_gives[0])), None)
        if deal:
            break
        assert mods is not None
    assert deal, "the thirsty civ asked for water and the rich one sold it"
    giver = deal.a if deal.a_gives[0] == "water" else deal.b
    assert giver == rich.id
