import pytest

from civsim.civ import Research
from civsim.config import SimConfig
from civsim.economy.rules import RESOURCES
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain
from civsim.strategy.checkin import CheckinRequest
from civsim.tech import InventionRules, build_invented_tech


@pytest.fixture
def setup():
    sim = Simulation(SimConfig(seed=3))
    civ = sim.civs[0]
    civ.known_techs = list(sim.tech_tree.techs)
    return sim, civ, InventionRules.load()


def invent(setup, proposal, storage=1000.0):
    sim, civ, rules = setup
    return build_invented_tech(proposal, civ, sim.tech_tree, rules, dict.fromkeys(RESOURCES, storage))


def proposal(**overrides):
    base = {
        "name": "Crop Rotation", "description": "Fields rest in turn.",
        "effects": [{"type": "yield_mult", "resource": "food", "amount": 0.1}],
        "materials": ["wood", "stone"],
    }
    return {**base, **overrides}


def test_valid_proposal_becomes_a_private_tech(setup):
    sim, civ, rules = setup
    tech = invent(setup, proposal())
    assert tech.name == "Crop Rotation" and tech.owner == civ.id
    assert tech.effects == {"yield_mult": {"food": 0.1}}
    assert tech.era == len(sim.tech_tree.eras), "inventions form a new era after the base tree"
    assert set(tech.prereqs) <= set(civ.known_techs) and tech.prereqs
    assert tech.description.startswith("+10% food")
    assert set(tech.materials) == {"wood", "stone"}

    sim.tech_tree.add_invented(tech, rules.era_name)
    assert sim.tech_tree.eras[-1] == rules.era_name
    assert tech in sim.tech_tree.available(civ.known_techs, civ.id)
    other = sim.civs[1]
    assert tech not in sim.tech_tree.available(list(civ.known_techs), other.id), "only the inventor can research it"


def test_effects_are_clamped_to_the_caps(setup):
    _, _, rules = setup
    tech = invent(setup, proposal(effects=[
        {"type": "yield_mult", "resource": "ore", "amount": 50},
        {"type": "military", "resource": "none", "amount": 0.0001},
    ]))
    assert tech.effects["yield_mult"]["ore"] == rules.caps["yield_mult"]
    assert tech.effects["military"] == pytest.approx(rules.min_fraction * rules.caps["military"])

    spread = invent(setup, proposal(effects=[{"type": "yield_mult", "resource": "all", "amount": 1}]))
    assert spread.effects == {"yield_mult": {"all": rules.caps["yield_mult_all"]}}

    cheaper = invent(setup, proposal(effects=[{"type": "expand_cost", "resource": "none", "amount": 0.9}]))
    assert cheaper.effects == {"expand_cost": -rules.caps["expand_cost"]}, "always a discount, never a penalty"


def test_unusable_parts_of_a_proposal_are_dropped(setup):
    _, _, rules = setup
    tech = invent(setup, proposal(effects=[
        {"type": "build_slots", "resource": "none", "amount": 5},  # not an allowed effect
        {"type": "yield_mult", "resource": "mana", "amount": 0.1},  # not a resource
        {"type": "income", "resource": "gold", "amount": "plenty"},  # not a number
        "free stuff",
        {"type": "growth", "resource": "none", "amount": 0.1},
        {"type": "growth", "resource": "none", "amount": 0.2},  # duplicate
        {"type": "housing", "resource": "none", "amount": 10},
        {"type": "storage", "resource": "none", "amount": 100},  # over the effect limit
    ]))
    assert tech.effects == {"growth": 0.1, "housing": 10}
    assert len(tech.effects) <= rules.max_effects


@pytest.mark.parametrize("bad", [None, "a wheel but better", [], {}, {"name": "X"}, {"effects": "big"},
                                 {"effects": []}, {"effects": [{"type": "godmode", "amount": 1}]}])
def test_proposals_with_nothing_usable_are_rejected(setup, bad):
    assert invent(setup, bad) is None


def test_the_game_sets_the_price(setup):
    sim, civ, rules = setup
    weak = invent(setup, proposal(cost={"science": 1}, effects=[{"type": "yield_mult", "resource": "food", "amount": 0.05}]))
    strong = invent(setup, proposal(cost={"science": 1}, effects=[
        {"type": "yield_mult", "resource": "food", "amount": 0.2},
        {"type": "science_mult", "resource": "none", "amount": 0.25},
    ]))
    assert weak.science_cost >= 0.6 * rules.base_science, "a proposed cost is ignored"
    assert strong.science_cost > weak.science_cost
    assert sum(strong.materials.values()) > sum(weak.materials.values())

    sim.tech_tree.add_invented(strong, rules.era_name)
    civ.known_techs.append(strong.id)
    again = invent(setup, proposal(name="Second", effects=strong_effects()))
    assert again.science_cost == pytest.approx(strong.science_cost * rules.cost_growth, rel=0.02)
    assert again.id != strong.id


def strong_effects():
    return [{"type": "yield_mult", "resource": "food", "amount": 0.2},
            {"type": "science_mult", "resource": "none", "amount": 0.25}]


def test_material_costs_fit_in_storage_and_use_obtainable_resources(setup):
    sim, civ, _ = setup
    civ.capacity["ore"] = 0
    civ.resources["ore"] = 0
    tech = invent(setup, proposal(materials=["ore", "food", "plutonium", "gold"], effects=strong_effects()), storage=100)
    assert "ore" not in tech.materials and "food" not in tech.materials and "gold" in tech.materials
    assert all(amount <= 80 for amount in tech.materials.values())

    civ.imports["ore"] = 0.5  # now supplied by trade
    assert "ore" in invent(setup, proposal(materials=["ore"])).materials


def test_names_are_cleaned_and_kept_unique(setup):
    sim, _, rules = setup
    tech = invent(setup, proposal(name="  <b>Steam</b>   Power!!{}" + "x" * 80, description="A" * 500))
    assert tech.name.startswith("bSteamb Power!!") and len(tech.name) <= 40
    assert len(tech.description) < 200

    clash = invent(setup, proposal(name="agriculture"))
    assert clash.name == "agriculture 2"
    assert invent(setup, proposal(name="")).name == "Untitled Discovery"


def test_invention_flows_through_a_check_in(setup):
    sim, civ, _ = setup
    civ.population = 150
    civ.resources.update(wood=250, stone=250, gold=250)
    request = CheckinRequest(civ.id, sim.tick, "invent", {})
    sim.submit(request, proposal(name="Printing Press"))
    events = sim.step()
    tech = sim.tech_tree.invented_by(civ.id)[0]
    assert civ.research.tech_id == tech.id
    assert any("Printing Press" in e["text"] for e in events)

    # A second proposal while one is in progress is discarded.
    sim.submit(request, proposal(name="Telescope"))
    sim.step()
    assert len(sim.tech_tree.invented_by(civ.id)) == 1

    civ.research = Research(tech.id, paid=True, progress=tech.science_cost)
    sim.step()
    assert tech.id in civ.known_techs
    assert sim.tech_tree.eras[sim.tech_tree.era_of(civ.known_techs)] == "Enlightenment"
    assert sim.modifiers[civ.id].yield_mult["food"] >= 0.1 or sim.step() is not None


def test_rule_brain_invents_once_the_base_tree_is_exhausted(setup):
    sim, civ, _ = setup
    brain = RuleBrain()
    civ.population = 150
    for _ in range(120):
        sim.step_with(brain)
    invented = sim.tech_tree.invented_by(civ.id)
    assert invented and all(t.owner == civ.id for t in invented)
    assert not any(sim.tech_tree.invented_by(other.id) for other in sim.civs[1:]), "others are still on the base tree"
