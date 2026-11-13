"""An army is trained, not conjured: a few soldiers a day, more with barracks, each paid for.
And a civ fields more than one army: a second column, a home force, and allies side by side."""

import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.diplomacy import rules
from civsim.economy import produce, training_rate
from civsim.economy import rules as economy
from civsim.military import Army
from civsim.military import warfare
from civsim.simulation import Simulation
from civsim.strategy import stance_context


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def raise_army(sim, civ, days):
    for _ in range(days):
        produce(civ, sim.modifiers[civ.id], sim.building_defs)


def test_soldiers_are_trained_a_few_a_day_and_barracks_train_more(sim):
    civ = sim.civs[0]
    civ.population, civ.soldiers, civ.soldier_target = 200, 0.0, 70
    civ.resources.update(gold=250, ore=250, food=250)
    levy = training_rate(civ)
    assert levy == pytest.approx(economy.TRAIN_LEVY + economy.TRAIN_LEVY_PER_POP * 200)
    raise_army(sim, civ, 10)
    assert civ.soldiers == pytest.approx(10 * levy, rel=0.05), "ten days of levy, not the whole army at once"

    civ.buildings += [Building("barracks", t, 1.0, True) for t in sorted(civ.territory)[:2]]
    assert training_rate(civ) == pytest.approx(levy + 2 * economy.TRAIN_PER_BARRACKS)
    assert stance_context(sim, civ)["you"]["training_per_tick"] == pytest.approx(training_rate(civ), abs=0.01)
    before = civ.soldiers
    raise_army(sim, civ, 10)
    assert civ.soldiers - before > 1.8 * 10 * levy


def test_every_recruit_is_paid_for_and_none_are_raised_without_gold(sim):
    civ = sim.civs[0]
    civ.population, civ.soldiers, civ.soldier_target = 200, 0.0, 70
    civ.workers = dict.fromkeys(civ.workers, 0)
    civ.resources.update(gold=200, ore=200, food=250)
    mods = sim.modifiers[civ.id]
    produce(civ, mods, sim.building_defs)
    raised = civ.soldiers
    assert raised > 0
    assert civ.resources["ore"] < 200 - 0.9 * raised * economy.RECRUIT_ORE * 0.5, "armed from its own ore"
    with_ore = civ.resources["gold"]

    civ.soldiers = 0.0
    civ.resources.update(gold=200, ore=0)
    produce(civ, mods, sim.building_defs)
    assert civ.soldiers == pytest.approx(raised), "a civ with no ore still raises soldiers"
    assert civ.resources["gold"] < with_ore, "but the arms are bought in, and cost more"

    civ.resources.update(gold=0)
    civ.population = 30  # and no taxes to speak of
    before = civ.soldiers
    produce(civ, mods, sim.building_defs)
    assert civ.soldiers - before < 0.5 * training_rate(civ), "next to nothing to pay them with"


def test_standing_down_is_quick(sim):
    civ = sim.civs[0]
    civ.population, civ.soldiers, civ.soldier_target = 200, 60.0, 0
    civ.resources.update(gold=250, food=250)
    raise_army(sim, civ, 15)
    assert civ.soldiers < 5


def test_the_planner_wants_barracks_when_the_army_lags(sim):
    civ = sim.civs[0]
    barracks = sim.building_defs["barracks"]
    mods = sim.modifiers[civ.id]
    civ.soldiers, civ.soldier_target = 10, 10
    calm = sim.ai._building_need(barracks, sim.ai.assess_needs(civ, mods))
    civ.soldier_target = 100
    pressed = sim.ai._building_need(barracks, sim.ai.assess_needs(civ, mods))
    assert pressed > calm >= 0.35 and pressed == pytest.approx(0.9)


# -- several armies -----------------------------------------------------------

def at_war(sim, a, b, soldiers):
    sim.diplomacy._start_war(a, b, 0, {a.id})
    for civ in (a, b):
        sim.military._sync(civ)
    a.soldiers = soldiers
    sim.military._sync(a)
    sim.military._organise(a, 1)
    a.soldiers *= 1.5  # and more have been raised since, who are still in the capital
    sim.military._sync(a)
    return [x for x in a.armies if x.role == "field" and x.target_civ == b.id]


def test_a_big_enough_army_sends_a_second_column_at_another_capital(sim):
    a, b = sim.civs[0], sim.civs[1]
    assert len(b.settlements) >= 2
    armies = at_war(sim, a, b, soldiers=300)
    assert [x.wing for x in armies] == [0]
    for _ in range(3):
        sim.military._sync(a)
        sim.military._organise(a, 2)
    armies = [x for x in a.armies if x.role == "field" and x.target_civ == b.id]
    assert sorted(x.wing for x in armies) == list(range(len(armies))) and 2 <= len(armies) <= warfare.MAX_ARMIES
    for army in armies:
        assert 0 < army.size <= sim.military.capacity(army) + 1e-6, "no more than its commander can lead"
    assert a.garrison.size > 0, "and the rest wait in the capitals"
    for army in armies:
        army.path_tick = -10_000
        sim.military._plan(a, army, 5)
    goals = {army.wing: army.path[-1] for army in armies if army.path}
    capitals = {s.tile for s in b.settlements}
    assert set(goals.values()) == capitals, "between them the columns go for every capital"

    small = Simulation(SimConfig(seed=3))
    armies = at_war(small, small.civs[0], small.civs[1], soldiers=14)
    for _ in range(3):
        small.military._organise(small.civs[0], 2)
    assert len([x for x in small.civs[0].armies if x.role == "field"]) == 1, "too few to split"


def test_an_intruder_far_from_every_army_gets_a_home_force_raised_against_it(sim):
    a, b = sim.civs[0], sim.civs[1]
    world, military = sim.world, sim.military
    armies = at_war(sim, a, b, soldiers=50)
    armies[0].tile = b.capital.tile  # the army is away at the enemy's capital
    home = next(t for t in world.neighbors(a.capital.tile) if not world.is_water(t))
    raider = Army(military.next_id(), b.id, home, "field", target_civ=a.id, units={"spearman": 10.0}, state="marching")
    b.armies.append(raider)
    military._organise(a, 2)
    guard = next(x for x in a.armies if x.duty == "defend")
    assert guard.target_civ == b.id and guard.size > 0
    military._plan(a, guard, 3)
    assert guard.state == "marching" and (guard.path[-1] == raider.tile if guard.path else guard.tile == raider.tile)
    # With the home force in being, the main army carries on with its attack.
    armies[0].path_tick = -10_000
    military._plan(a, armies[0], 3)
    assert not armies[0].path or armies[0].path[-1] in {s.tile for s in b.settlements}
    # The land clear again, the home force stands down.
    b.armies.remove(raider)
    military._organise(a, 4)
    assert guard.state == "returning"


def test_allies_make_for_the_same_capital_and_shorten_each_others_sieges(sim):
    a, b, c = sim.civs[0], sim.civs[1], sim.civs[2]
    military, world = sim.military, sim.world
    sim.diplomacy.relation(a.id, c.id).status = "alliance"
    sim.diplomacy._start_war(a, b, 0, {a.id})
    sim.diplomacy._start_war(c, b, 0, {c.id})
    target = max((s.tile for s in b.settlements), key=lambda t: military._gap(a.capital.tile, t))  # the far one
    ally = Army(military.next_id(), c.id, c.capital.tile, "field", target_civ=b.id, units={"spearman": 50.0},
                state="marching", path=[target])
    c.armies.append(ally)
    assert military._allied_targets(a, b) == {target}

    region = world.regions[world.capital_tiles[target]]
    region.held_by, region.hold = c.id, 10
    beside = next(t for t in world.neighbors(target) if not world.is_water(t))
    mine = Army(military.next_id(), a.id, beside, "field", target_civ=b.id, units={"spearman": 5000.0},
                state="marching", path=[target], siege_progress=1000.0, path_tick=10**9)
    a.armies.append(mine)
    a.soldiers += 5000
    for civ in (a, b):
        military._sync(civ)
    for tick in range(10, 20):
        military._besiege(a, mine, tick, [])
    assert region.held_by == c.id and region.hold == 15, "half a day's hold for every day the ally stands in the breach"
    assert region.hold < rules.CAPITAL_HOLD and region.owner == b.id
    assert warfare.JOINT_PULL > 0


# -- generals, garrisons and rallies ---------------------------------------------

def test_a_general_leads_only_so_many_and_more_as_he_rises(sim):
    from civsim.military import Commander
    from civsim.military.army import CAPACITY, CAPACITY_PER_LEVEL, XP_PER_LEVEL_STEP
    green, veteran = Commander("Green"), Commander("Veteran", experience=XP_PER_LEVEL_STEP * 16)
    assert green.capacity == CAPACITY and veteran.level == 5
    assert veteran.capacity == CAPACITY + 4 * CAPACITY_PER_LEVEL
    army = Army(1, 0, 0, "field", commander=green)
    assert sim.military.capacity(army) == CAPACITY
    army.commander = None
    assert sim.military.capacity(army) < CAPACITY, "few follow an army with no commander"


def test_a_civ_never_has_more_than_five_armies_out_and_the_rest_garrison_its_capitals(sim):
    a, b = sim.civs[0], sim.civs[1]
    at_war(sim, a, b, soldiers=2000)
    a.resources["gold"] = 10_000
    for tick in range(2, 30):
        sim.military._sync(a)
        sim.military._organise(a, tick)
    out = [x for x in a.armies if x.role == "field"]
    assert len(out) == warfare.MAX_ARMIES
    assert all(x.size <= sim.military.capacity(x) + 1e-6 for x in out)
    assert a.garrison.size > sum(x.size for x in out), "most of so large a host stays at home"

    # Those soldiers hold every capital, not only the civ's own: a regional capital is harder to take for them.
    region_capital = next(s.tile for s in a.settlements if s.tile != a.capital.tile)
    sim.diplomacy.relation(a.id, b.id).war.aggressors = {b.id}
    beside = next(t for t in sim.world.neighbors(region_capital) if not sim.world.is_water(t))
    raider = Army(sim.military.next_id(), b.id, beside, "field", target_civ=a.id, units={"spearman": 40.0},
                  state="marching", path=[region_capital], path_tick=10**9)
    b.armies.append(raider)
    b.soldiers += 40
    sim.military._besiege(b, raider, 40, [])
    assert raider.siege_progress == 0, "forty men make nothing of a capital with hundreds waiting in it"


@pytest.fixture
def allies(sim):
    """Civ 0 and civ 2 allied and both at war with civ 1, each with an army in its own capital."""
    a, b, c = sim.civs[0], sim.civs[1], sim.civs[2]
    military = sim.military
    sim.diplomacy.relation(a.id, c.id).status = "alliance"
    sim.diplomacy._start_war(a, b, 0, {a.id})
    sim.diplomacy._start_war(c, b, 0, {c.id})
    armies = {}
    for civ in (a, b, c):
        military._sync(civ)
    for civ, count in ((a, 20.0), (c, 12.0)):
        civ.soldiers += count
        civ.population += count
        army = Army(military.next_id(), civ.id, civ.capital.tile, "field", target_civ=b.id,
                    commander=military._appoint(civ), units={"spearman": count}, state="idle")
        civ.armies.append(army)
        armies[civ.id] = army
    return sim, a, b, c, armies


def test_allies_gather_in_a_city_and_march_on_an_enemy_city_as_one(allies):
    sim, a, b, c, armies = allies
    military = sim.military
    events = []
    rally = military.start_rally(a, b.id, 10, events)
    assert rally.city in {s.tile for s in a.settlements} and rally.target in {s.tile for s in b.settlements}
    assert armies[a.id].rally == rally.id and any("calls a rally" in e["text"] for e in events)
    assert military.start_rally(a, b.id, 11, []) == "you are already leading a rally"
    assert military.join_rally(c, rally, 11, events) is None and armies[c.id].rally == rally.id
    assert military.join_rally(sim.civs[3], rally, 11, []) == "only allies may join a rally"
    military._plan(c, armies[c.id], 12)
    assert armies[c.id].state == "marching" and armies[c.id].path[-1] == rally.city, "it makes for the city"

    # Both there when the gathering ends: one army under the leader's general, the head counts moved with it.
    for army in armies.values():
        army.tile, army.path = rally.city, []
    people = {civ.id: (civ.soldiers, civ.population) for civ in (a, c)}
    military._rallies(rally.departs, events)
    head = armies[a.id]
    assert rally.state == "marching" and rally.army == head.id
    assert head.size == pytest.approx(32.0) and armies[c.id].size == 0
    assert military.capacity(head) == float("inf")
    assert rally.shares == {c.id: pytest.approx(12 / 32)}
    assert a.soldiers == pytest.approx(people[a.id][0] + 12) and c.soldiers == pytest.approx(people[c.id][0] - 12)
    assert any("The rally marches on" in e["text"] for e in events)
    military._plan(a, head, rally.departs + 1)
    assert head.path[-1] == rally.target, "and it goes for the one city it was called against"

    # Half are lost on the way; the rest are divided as the army was made up, and go home.
    head.scale(0.5)
    a.soldiers -= 16
    head.state = "retreating"
    military._rallies(rally.departs + 5, events)
    assert rally not in military.rallies and head.rally is None and armies[c.id].rally is None
    assert armies[c.id].size == pytest.approx(6.0) and head.size == pytest.approx(10.0)
    assert c.soldiers == pytest.approx(people[c.id][0] - 6), "losses are shared in proportion"
    assert armies[c.id].state == "returning"


def test_a_rally_can_be_called_off_and_one_nobody_joins_is(allies):
    sim, a, b, c, armies = allies
    military = sim.military
    rally = military.start_rally(a, b.id, 10, [])
    military.join_rally(c, rally, 11, [])
    events = []
    military.cancel_rally(rally, 15, events)
    assert not military.rallies and armies[a.id].rally is None and armies[c.id].rally is None
    assert any("calls off its rally" in e["text"] for e in events)
    assert military.start_rally(a, sim.civs[3].id, 16, []) == "you are not at war with that civ"

    alone = military.start_rally(a, b.id, 300, [])
    armies[a.id].tile = alone.city
    events = []
    military._rallies(alone.departs, events)
    assert not military.rallies and any("too few came" in e["text"] for e in events)


def test_a_ruler_calls_rallies_and_is_asked_to_join_an_allys(allies):
    import json
    from civsim.bridge import protocol
    from civsim.config import HEADCOUNT
    sim, a, b, c, armies = allies
    ruler = sim.ruler
    ruler.command("take_control", {"civ": c.id})
    assert ruler.state()["rally_targets"] == [b.id]
    rally = sim.military.start_rally(a, b.id, sim.tick, [])
    sim.military._rallies(sim.tick + 1, [])
    assert armies[c.id].rally is None, "a ruler's armies join nothing unasked"
    asked = [p for p in ruler.proposals() if p["kind"] == "rally"]
    assert len(asked) == 1 and asked[0]["civ"] == a.id and asked[0]["popup"] is True
    sent = json.loads(protocol.tick_message(sim, False, 1.0))["data"]
    assert sent["rallies"][0]["leader"] == a.id and sent["rallies"][0]["soldiers"] == 20 * HEADCOUNT
    assert ruler.command("answer_proposal", {"civ": a.id, "kind": "rally", "accept": True}) is None
    assert armies[c.id].rally == rally.id and not [p for p in ruler.proposals() if p["kind"] == "rally"]

    sim.military.cancel_rally(rally, sim.tick, [])
    assert ruler.command("cancel_rally", {}) == "you are not leading a rally"
    assert ruler.command("start_rally", {"civ": b.id}) is None
    assert ruler.state()["rally"]["state"] == "gathering"
    assert ruler.command("cancel_rally", {}) is None and ruler.state()["rally"] is None


def test_a_civ_calls_a_rally_when_an_ally_could_reach_where_it_would_gather(allies):
    """Its own army need not be standing in a castle: one on the march, not yet fighting, will
    do. What counts is that an ally's army could get to the city the rally gathers in."""
    sim, a, b, c, armies = allies
    military = sim.military
    world = sim.world
    city, _ = military._rally_ground(a, b, [armies[a.id]])
    armies[a.id].state = "marching"
    armies[a.id].tile = next(t for t in world.neighbors(a.capital.tile) if world.walkable(t))
    armies[c.id].tile = city  # the ally's army is there already
    events = []
    military._rallies(20, events)
    assert military.rally_led_by(a.id) is not None or military.rally_led_by(c.id) is not None
    assert any("calls a rally" in e["text"] for e in events)
