from civsim.civ import Building
from civsim.config import SimConfig
from civsim.economy import compute_modifiers, food_need, produce
from civsim.economy.rules import SCIENCE_BANK_CAP
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain


def test_unpaid_buildings_stop_working():
    sim = Simulation(SimConfig(seed=3))
    civ = sim.civs[0]
    civ.buildings.append(Building("library", tile=next(iter(civ.territory)), progress=1.0, complete=True))
    assert sim.building_defs["library"].upkeep == {"gold": 0.15}

    civ.resources["gold"] = 50
    produce(civ, sim.modifiers[civ.id], sim.building_defs)
    assert civ.buildings[-1].active
    assert compute_modifiers(civ, sim.building_defs, sim.tech_tree).science > 0

    civ.resources["gold"] = 0
    civ.workers["gold"] = 0
    civ.population = 5  # too few taxpayers to cover it
    produce(civ, sim.modifiers[civ.id], sim.building_defs)
    assert not civ.buildings[-1].active
    assert compute_modifiers(civ, sim.building_defs, sim.tech_tree).science == 0


def test_consumption_rises_with_technology():
    sim = Simulation(SimConfig(seed=3))
    civ = sim.civs[0]
    before = food_need(civ)
    civ.known_techs = list(sim.tech_tree.techs)
    assert food_need(civ) > 1.5 * before


def test_soldiers_cost_gold_and_desert_when_unpaid():
    sim = Simulation(SimConfig(seed=3))
    civ = sim.civs[0]
    civ.population, civ.soldier_target = 100, 30
    civ.resources.update(gold=200, food=250)
    for _ in range(40):
        produce(civ, sim.modifiers[civ.id], sim.building_defs)
    assert civ.soldiers > 25 and not civ.unpaid
    assert civ.upkeep["gold"] > 0.5

    civ.resources["gold"] = 0
    civ.workers["gold"] = 0
    civ.population = 40  # taxes no longer cover the army
    produce(civ, sim.modifiers[civ.id], sim.building_defs)
    before = civ.soldiers
    produce(civ, sim.modifiers[civ.id], sim.building_defs)
    assert civ.unpaid and civ.soldiers < before


def test_science_never_piles_up_once_the_tree_is_finished():
    sim = Simulation(SimConfig(seed=3))
    brain = RuleBrain()
    for civ in sim.civs:
        civ.known_techs = list(sim.tech_tree.techs)
        civ.population = 200
    raised = 0
    for _ in range(400):
        sim.step_with(brain)
        raised += len(sim._outbox)
        assert all(civ.science <= SCIENCE_BANK_CAP for civ in sim.civs)
    assert all(civ.research is None for civ in sim.civs), "nothing is left to research"
    assert len(sim.tech_tree.techs) == 36, "and nobody adds to the tree"
