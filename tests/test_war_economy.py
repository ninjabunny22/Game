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
    assert sorted(x.wing for x in armies) == [0, 1]
    main, column = sorted(armies, key=lambda x: x.wing)
    assert main.size > column.size > 0
    for army in armies:
        army.path_tick = -10_000
        sim.military._plan(a, army, 5)
    goals = {army.wing: army.path[-1] for army in armies if army.path}
    capitals = {s.tile for s in b.settlements}
    assert set(goals.values()) <= capitals and len(set(goals.values())) == len(goals) == 2, "two capitals, one each"

    small = Simulation(SimConfig(seed=3))
    armies = at_war(small, small.civs[0], small.civs[1], soldiers=40)
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
