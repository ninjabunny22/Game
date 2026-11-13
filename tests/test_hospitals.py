"""The wounded go to hospital, are healed in ten days and join the garrison; those there is no
bed for die. An army fills its ranks only in one of its civ's capitals."""

import pytest

from civsim.config import SimConfig
from civsim.economy import compute_modifiers
from civsim.economy import rules as economy
from civsim.military import Army
from civsim.military import warfare
from civsim.simulation import Simulation


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:
        sim.military._sync(civ)
    return sim


def field_army(sim, civ, size, tile=None, enemy=1):
    army = Army(sim.military.next_id(), civ.id, tile if tile is not None else civ.capital.tile, "field",
                target_civ=enemy, commander=sim.military._appoint(civ))
    army.add({"spearman": size})
    civ.armies.append(army)
    civ.soldiers += size
    civ.population += size
    return army


def away(sim, civ):
    """A tile of the civ's land that is not one of its capitals."""
    capitals = {s.tile for s in civ.settlements}
    return next(t for t in sorted(civ.territory) if t not in capitals and sim.world.walkable(t))


def test_the_wounded_are_healed_in_ten_days_and_join_the_garrison_not_their_army(sim):
    civ, military = sim.civs[0], sim.military
    army = field_army(sim, civ, 20, away(sim, civ))
    garrison, soldiers = civ.garrison.size, civ.soldiers
    assert economy.HEAL_TICKS == 10
    assert military.beds(civ) == economy.INFIRMARY_BEDS * len(civ.settlements)
    military._tick = 100
    assert military._admit(civ, {"spearman": 8.0}, 1.0) == 0.0
    assert civ.wounded == pytest.approx(8.0)
    military._heal(civ, 109)
    assert civ.wounded == pytest.approx(8.0), "not yet"
    military._heal(civ, 110)
    assert civ.wounded == 0
    assert civ.garrison.size == pytest.approx(garrison + 8.0)
    assert civ.soldiers == pytest.approx(soldiers + 8.0)
    assert army.size == pytest.approx(20), "they do not go back to their army by themselves"


def test_wounded_there_is_no_bed_for_die_and_research_adds_beds_to_every_castle(sim):
    civ, military = sim.civs[0], sim.military
    beds = military.beds(civ)
    military._tick = 50
    dead = military._admit(civ, {"spearman": beds + 6.0}, 1.0)
    assert dead == pytest.approx(6.0)
    assert civ.wounded == pytest.approx(beds)
    assert civ.beds_short == 50 and civ.hospital_deaths == pytest.approx(6.0)
    assert military._admit(civ, {"spearman": 4.0}, 1.0) == pytest.approx(4.0), "every bed is taken"

    assert "hospital" not in sim.building_defs, "the hospital is in the castle, not a building of its own"
    civ.known_techs = ["agriculture", "field_medicine", "mathematics", "surgeons"]
    sim.modifiers[civ.id] = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    military.mods = sim.modifiers
    assert military.beds(civ) == pytest.approx(beds + 20 * len(civ.settlements)), "10 more in every castle, twice"
    civ.settlements.append(type(civ.settlements[0])("Newhold", away(sim, civ)))
    assert military.beds(civ) == pytest.approx((economy.INFIRMARY_BEDS + 20) * len(civ.settlements))
    assert military._admit(civ, {"spearman": 4.0}, 1.0) == 0.0


def test_a_routed_armys_wounded_are_soldiers_again_once_healed(sim):
    civ, military = sim.civs[1], sim.military
    army = field_army(sim, civ, 30, away(sim, civ), enemy=0)
    soldiers, population = civ.soldiers, civ.population
    military._tick = 10
    military._scatter_soldiers(civ, army, 10.0, None)
    assert civ.wounded == pytest.approx(6.0)
    assert soldiers - civ.soldiers == pytest.approx(7.0), "the wounded and the dead are out of the ranks"
    assert population - civ.population == pytest.approx(1.0), "only the dead leave the population"
    military._heal(civ, 20)
    assert soldiers - civ.soldiers == pytest.approx(1.0)
    assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers)


def test_an_army_fills_its_ranks_only_in_one_of_its_capitals(sim):
    a, b = sim.civs[0], sim.civs[1]
    sim.diplomacy._start_war(a, b, 0, {a.id})
    a.soldiers = a.population = 0.0
    a.garrison.units = {}
    army = field_army(sim, a, 5, away(sim, a))
    a.garrison.add({"spearman": 60.0})
    a.soldiers += 60
    a.population += 200
    for tick in range(1, 6):
        sim.military._organise(a, tick)
    assert army.size == pytest.approx(5), "nobody is sent out to an army in the field"
    army.tile = a.settlements[-1].tile
    sim.military._organise(a, 6)
    assert army.size == pytest.approx(min(sim.military.capacity(army), 5 + 60 - warfare.GARRISON_KEEP * a.soldiers))


def test_a_worn_down_army_goes_home_for_more(sim):
    a, b = sim.civs[0], sim.civs[1]
    sim.diplomacy._start_war(a, b, 0, {a.id})
    a.soldiers = a.population = 0.0
    a.garrison.units = {}
    army = field_army(sim, a, 6, away(sim, a))
    a.population += 200
    assert not sim.military._worn_down(a, army), "nobody is waiting at home"
    a.garrison.add({"spearman": 40.0})
    a.soldiers += 40
    assert sim.military._worn_down(a, army)
    sim.military._plan(a, army, 5)
    assert army.refit and army.path and army.path[-1] in {s.tile for s in a.settlements}
    army.tile = army.path[-1]
    sim.military._organise(a, 6)
    assert not army.refit and army.size > 6
