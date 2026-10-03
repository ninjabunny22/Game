import pytest

from civsim.civ import Research
from civsim.config import SimConfig
from civsim.economy import load_building_defs
from civsim.simulation import Simulation
from civsim.tech import Tech, TechTree, advance_research


def test_tree_shape():
    tree = TechTree.load()
    assert 10 <= len(tree.techs) <= 15
    assert 3 <= len(tree.eras) <= 4
    assert {tech.era for tech in tree.techs.values()} == set(range(len(tree.eras)))
    for tech in tree.techs.values():
        assert tech.science_cost > 0 and tech.effects


def test_buildings_reference_real_techs():
    tree = TechTree.load()
    for bdef in load_building_defs().values():
        assert bdef.requires_tech is None or bdef.requires_tech in tree.techs


def test_cycle_is_rejected():
    a = Tech("a", "A", 0, ("b",), {"science": 1})
    b = Tech("b", "B", 0, ("a",), {"science": 1})
    with pytest.raises(ValueError):
        TechTree(["Ancient"], [a, b])


def test_available_respects_prerequisites():
    tree = TechTree.load()
    assert {t.id for t in tree.available([])} == {t.id for t in tree.techs.values() if not t.prereqs}
    assert "writing" not in {t.id for t in tree.available([])}
    assert "writing" in {t.id for t in tree.available(["pottery"])}


def test_research_is_gated_by_materials_then_science():
    sim = Simulation(SimConfig(seed=3))
    civ = sim.civs[0]
    tech = sim.tech_tree.techs["pottery"]
    civ.research = Research("pottery")
    civ.resources["wood"] = 0
    civ.science = 1000
    advance_research(civ, sim.tech_tree, [])
    assert civ.known_techs == [] and not civ.research.paid

    civ.resources["wood"] = 50
    civ.science = 0
    advance_research(civ, sim.tech_tree, [])
    assert civ.research.paid and civ.resources["wood"] == 50 - tech.materials["wood"]
    assert civ.known_techs == []

    civ.science = tech.science_cost
    events: list = []
    advance_research(civ, sim.tech_tree, events)
    assert civ.known_techs == ["pottery"] and civ.research is None
    assert events[0]["kind"] == "tech"


def test_civs_learn_techs_in_prerequisite_order():
    sim = Simulation(SimConfig(seed=3))
    for _ in range(900):
        sim.step()
    for civ in sim.civs:
        assert len(civ.known_techs) >= 4
        for position, tech_id in enumerate(civ.known_techs):
            assert set(sim.tech_tree.techs[tech_id].prereqs) <= set(civ.known_techs[:position])
    assert any(sim.tech_tree.era_of(civ.known_techs) > 0 for civ in sim.civs)
