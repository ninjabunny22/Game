"""Stables, horses, mounted villagers, cavalry that needs horses, and armies taking ship."""

import json

import pytest

from civsim.bridge import protocol
from civsim.civ import Building
from civsim.config import SimConfig
from civsim.economy import food_need, produce, tend_horses
from civsim.economy.rules import (HERD_PER_STABLE, HORSE_BREED_TICKS, HORSE_FOOD, HORSE_WATER, MOUNTED_WORKERS,
                                  WORK_RATE)
from civsim.economy.villagers import convert_villagers
from civsim.military import Army
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain

ALL_UNIT_TECHS = ["agriculture", "animal_husbandry", "the_wheel", "mining", "bronze_working", "iron_working"]


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def with_stables(sim, civ, count=1):
    for i in range(count):
        civ.buildings.append(Building("stables", civ.settlements[i % len(civ.settlements)].tile, 1.0, True))


def test_stables_are_a_building_unlocked_by_animal_husbandry(sim):
    stables = sim.building_defs["stables"]
    assert stables.requires_tech == "animal_husbandry" and stables.max_count == 2
    assert stables.upkeep == {"food": 0.15, "water": 0.05}


def test_a_stable_breeds_a_horse_every_ten_days_up_to_what_it_can_keep(sim):
    assert HORSE_BREED_TICKS == 10
    civ = sim.civs[0]
    civ.military_need = 1.0  # under threat, so the horses stay in the stables to be counted
    tend_horses(civ)
    assert civ.horses == 0, "no stables, no horses"
    with_stables(sim, civ)
    for _ in range(HORSE_BREED_TICKS - 1):
        tend_horses(civ)
    assert civ.horses == 0
    tend_horses(civ)
    assert civ.horses == 1
    for _ in range(HORSE_BREED_TICKS * 20):
        tend_horses(civ)
    assert civ.horses == HERD_PER_STABLE == civ.herd
    civ.buildings[-1].active = False  # upkeep unpaid: no breeding
    civ.horses = 0
    for _ in range(HORSE_BREED_TICKS * 2):
        tend_horses(civ)
    assert civ.horses == 0


def test_horses_eat_and_drink_twice_what_a_person_does(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    produce(civ, mods, sim.building_defs)
    hungry = food_need(civ)
    thirst = civ.upkeep["water"]
    civ.horses = 10
    assert food_need(civ) == pytest.approx(hungry + 10 * HORSE_FOOD)
    assert HORSE_FOOD == pytest.approx(2 * 0.08) and HORSE_WATER == pytest.approx(2 * 0.03)
    population = civ.population
    produce(civ, mods, sim.building_defs)
    grown = civ.population - population
    assert civ.upkeep["water"] == pytest.approx(thirst + 10 * HORSE_WATER + 0.03 * grown, abs=0.02)


def test_spare_horses_go_to_villagers_in_peace_and_stay_for_the_army_under_threat(sim):
    civ = sim.civs[0]
    civ.horses = 5
    civ.military_need = 0.6
    tend_horses(civ)
    assert not any(v.mounted for v in civ.villagers) and civ.horses == 5
    civ.military_need = 0.0
    tend_horses(civ)
    riding = sum(v.mounted for v in civ.villagers)
    assert riding == len(civ.villagers) // 2 >= 1, "at most half the villagers ride"
    assert civ.horses == 5 - riding and civ.herd == 5


def test_a_mounted_villager_does_the_work_of_three_more_on_the_land(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.resources["wood"] = 100  # enough that every charge is paid in full
    villager = civ.villagers[0]
    villager.task, villager.target, villager.gathers, villager.path = "gather", villager.tile, "wood", []

    def wood_gathered():
        before = civ.resources["wood"]
        produce(civ, mods, sim.building_defs)
        return civ.resources["wood"] - before + civ.upkeep["wood"]

    on_foot = wood_gathered()
    villager.mounted = True
    assert wood_gathered() - on_foot == pytest.approx(MOUNTED_WORKERS * WORK_RATE * (1 + mods.yield_mult["wood"]))
    villager.target = villager.tile + 1  # still on the way there: nothing extra yet
    assert wood_gathered() == pytest.approx(on_foot)


def test_a_mounted_villager_on_a_captured_tile_loses_the_horse_and_lives(sim):
    a, b = sim.civs[0], sim.civs[1]
    villager = b.villagers[0]
    villager.mounted = True
    assert convert_villagers(villager.tile, b, a) >= 1
    assert villager in a.villagers and not villager.mounted
    assert a.herd == 0, "the horse is gone, not captured"


def test_cavalry_need_a_horse_each(sim):
    civ = sim.civs[0]
    civ.known_techs = list(ALL_UNIT_TECHS)
    civ.soldiers = 100
    sim.military._sync(civ)
    counts = civ.unit_counts()
    assert counts.get("cavalry", 0) == 0, "no horses, no cavalry"
    assert sum(counts.values()) == pytest.approx(100), "the men serve on foot instead"

    civ.horses = 6
    civ.soldiers = 200
    sim.military._sync(civ)
    assert civ.unit_counts()["cavalry"] == pytest.approx(6) and civ.horses == pytest.approx(0)
    assert sum(civ.unit_counts().values()) == pytest.approx(200)
    assert civ.herd == pytest.approx(6)


def test_cavalry_stood_down_return_their_horses_and_cavalry_killed_do_not(sim):
    civ = sim.civs[0]
    civ.known_techs = list(ALL_UNIT_TECHS)
    civ.horses, civ.soldiers = 10, 100
    sim.military._sync(civ)
    riders = civ.unit_counts()["cavalry"]
    assert riders > 0 and civ.herd == pytest.approx(10)
    civ.soldiers = 50  # half the army is stood down
    sim.military._sync(civ)
    assert civ.unit_counts()["cavalry"] == pytest.approx(riders / 2) and civ.herd == pytest.approx(10)
    # Killed in battle: the soldiers and their horses are both gone.
    lost = civ.garrison.take(civ.garrison.size)
    civ.soldiers = 0
    sim.military._sync(civ)
    assert civ.herd == pytest.approx(10 - lost["cavalry"])


def test_an_army_takes_ship_when_its_civ_has_a_working_harbour(sim):
    world = sim.world
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    mods.boats = 1
    shore, sea = next((t, n) for t in sorted(civ.territory) if not world.is_open_water(t)
                      for n in world.neighbors(t) if world.is_open_water(n))
    army = Army(999, civ.id, shore, "field", units={"spearman": 20.0}, state="marching")
    civ.armies.append(army)

    def put_out() -> bool:
        army.tile, army.path, army.move_points = shore, [sea], 10.0
        sim.military._march(civ, army)
        assert army.tile == sea, "it crosses either way: that is the Navigation tech's business"
        return army.boat

    assert not put_out(), "no harbour, no ship to show"
    harbour = Building("harbour", civ.capital.tile, 1.0, True)  # wherever it stands
    civ.buildings.append(harbour)
    harbour.active = False
    assert not put_out(), "a harbour whose upkeep is unpaid launches nothing"
    harbour.active = True
    harbour.complete = False
    assert not put_out(), "nor does one still being built"
    harbour.complete = True
    assert put_out()
    army.path, army.move_points = [shore], 10.0
    sim.military._march(civ, army)
    assert army.tile == shore and not army.boat, "back on land it is on foot again"
    assert put_out()
    state = json.loads(protocol.tick_message(sim, False, 1.0))["data"]
    shown = next(a for a in state["armies"] if a["id"] == 999)
    assert shown["afloat"] and shown["boat"]


def test_protocol_reports_horses_and_riders(sim):
    civ = sim.civs[0]
    civ.horses = 3.7
    civ.villagers[0].mounted = True
    state = json.loads(protocol.tick_message(sim, False, 1.0))["data"]
    assert state["civs"][0]["horses"] == 3 and state["civs"][0]["herd"] == 4
    mine = [v for v in state["villagers"] if v["civ"] == civ.id]
    assert [v["mounted"] for v in mine].count(True) == 1
    assert {"gathers", "at_work", "task"} <= set(mine[0])


def test_civs_build_stables_and_use_horses_in_play():
    sim = Simulation(SimConfig(seed=7))
    brain = RuleBrain()
    built = mounted = cavalry = 0
    for tick in range(1500):
        sim.step_with(brain)
        for civ in sim.civs:
            if not civ.alive:
                continue
            assert civ.horses >= -1e-6
            riders = civ.unit_counts().get("cavalry", 0.0)
            assert civ.herd <= HERD_PER_STABLE * 2 + 1e-6, "never more than two stables can keep"
            built = max(built, civ.count("stables"))
            mounted = max(mounted, sum(v.mounted for v in civ.villagers))
            cavalry = max(cavalry, riders)
    assert built >= 1 and mounted >= 1
