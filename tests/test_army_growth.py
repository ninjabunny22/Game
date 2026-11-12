"""Gold mines, research that makes soldiers cheaper, troop tiers, standing with an ally, scouting."""

import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.economy import compute_modifiers, produce
from civsim.economy import rules as economy
from civsim.economy.production import early_growth, soldier_cost
from civsim.military import Army
from civsim.military import warfare
from civsim.military.units import tier_cost, tier_strength
from civsim.simulation import Simulation
from civsim.strategy import stance_context


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:
        sim.military._sync(civ)
    return sim


def mods_with(sim, civ, *techs):
    civ.known_techs = list(techs)
    sim.modifiers[civ.id] = compute_modifiers(civ, sim.building_defs, sim.tech_tree)
    sim.military.mods = sim.diplomacy.mods = sim.modifiers
    return sim.modifiers[civ.id]


def test_a_young_civ_starts_larger_and_grows_faster_for_a_while():
    assert economy.START_POPULATION == 40 and economy.BASE_HOUSING == 60
    assert early_growth(1) == economy.EARLY_GROWTH == early_growth(economy.EARLY_GROWTH_UNTIL)
    assert 0 < early_growth(economy.EARLY_GROWTH_UNTIL + economy.EARLY_GROWTH_FADE // 2) < economy.EARLY_GROWTH
    assert early_growth(economy.EARLY_GROWTH_UNTIL + economy.EARLY_GROWTH_FADE) == 0 == early_growth(None)


def test_a_gold_mine_is_built_on_gold_and_raises_what_it_yields(sim):
    mine = sim.building_defs["gold_mine"]
    assert mine.placement == "yield:gold" and mine.need_resource == "gold" and mine.requires_tech == "mining"
    civ = sim.civs[0]
    before = compute_modifiers(civ, sim.building_defs, sim.tech_tree).yield_mult["gold"]
    civ.buildings.append(Building("gold_mine", sorted(civ.territory)[0], 1.0, True))
    assert compute_modifiers(civ, sim.building_defs, sim.tech_tree).yield_mult["gold"] == pytest.approx(before + 0.5)
    needs = sim.ai.assess_needs(civ, sim.modifiers[civ.id])
    calm = sim.ai._building_need(mine, needs)
    civ.unpaid = True
    assert sim.ai._building_need(mine, sim.ai.assess_needs(civ, sim.modifiers[civ.id])) == 1.0 > calm


def test_barracks_need_no_research_and_no_ore(sim):
    barracks = sim.building_defs["barracks"]
    assert not barracks.requires_tech and "ore" not in barracks.cost


def test_efficiency_research_makes_soldiers_cheaper_to_arm_and_to_pay(sim):
    civ = sim.civs[0]
    civ.buildings = []
    civ.workers = dict.fromkeys(civ.workers, 0)
    civ.population, civ.soldiers, civ.soldier_target = 200.0, 50.0, 50.0
    civ.resources.update(gold=200, ore=200, food=250)
    plain = mods_with(sim, civ)
    assert soldier_cost(plain) == 1.0
    produce(civ, plain, sim.building_defs)
    usual = civ.upkeep["gold"]
    cheap = mods_with(sim, civ, "logistics", "quartermasters", "standing_army")
    assert soldier_cost(cheap) == pytest.approx(0.55)
    produce(civ, cheap, sim.building_defs)
    assert civ.upkeep["gold"] == pytest.approx(0.55 * usual)

    civ.soldiers, civ.soldier_target = 0.0, 50.0
    civ.resources.update(gold=200, ore=200)
    produce(civ, plain, sim.building_defs)
    dear = 200 - civ.resources["ore"]
    civ.soldiers = 0.0
    civ.resources.update(gold=200, ore=200)
    produce(civ, cheap, sim.building_defs)
    assert 200 - civ.resources["ore"] == pytest.approx(0.55 * dear, rel=0.02)


def test_research_arms_troops_a_tier_better_and_a_better_tier_is_stronger(sim):
    civ, military = sim.civs[0], sim.military
    assert (tier_strength(1), tier_strength(4)) == (1.0, 1.9)
    assert tier_strength(2.5) == pytest.approx(1.4) and tier_cost(2) == pytest.approx(1.15)
    assert mods_with(sim, civ).tier == 1
    assert mods_with(sim, civ, "bronze_working", "iron_working").tier == 2
    assert mods_with(sim, civ, "iron_working", "machinery", "gunpowder").tier == 4

    army = Army(military.next_id(), civ.id, civ.capital.tile, "field")
    army.add({"spearman": 20.0})
    base = military.army_strength(army)
    army.tier = 4.0
    assert military.army_strength(army) == pytest.approx(1.9 * base)
    army.add({"spearman": 20.0}, 2.0)
    assert army.tier == pytest.approx(3.0), "a mixed army is as good as the average of its soldiers"


def test_better_arms_are_handed_out_in_a_capital_and_paid_for(sim):
    civ, military = sim.civs[0], sim.military
    mods_with(sim, civ, "iron_working")
    civ.resources.update(gold=200, ore=200)
    garrison = civ.garrison
    garrison.units, garrison.tier = {"spearman": 4.0}, 1.0
    capitals = {s.tile for s in civ.settlements}
    out = Army(military.next_id(), civ.id, next(t for t in sorted(civ.territory) if t not in capitals), "field")
    out.add({"spearman": 4.0})
    civ.armies.append(out)
    military._upgrade(civ)
    assert garrison.tier == pytest.approx(1.0 + warfare.UPGRADE_PER_TICK / 4.0)
    assert civ.resources["gold"] == pytest.approx(200 - warfare.UPGRADE_PER_TICK * warfare.UPGRADE_GOLD)
    military._upgrade(civ)
    assert garrison.tier == 2.0
    assert out.tier == 1.0, "an army in the field keeps the arms it has"
    civ.resources["gold"] = 0.0
    out.tile = civ.capital.tile
    military._upgrade(civ)
    assert out.tier == 1.0, "nothing is re-armed without gold"


def three(sim):
    a, b, c = sim.civs[:3]
    sim.diplomacy.relation(a.id, c.id).status = "alliance"
    sim.diplomacy._start_war(b, c, 0, {b.id})
    a.soldiers, a.population = 60.0, 300.0
    a.garrison.units = {"spearman": 60.0}
    return a, b, c


def test_an_army_is_sent_to_stand_in_an_allys_threatened_capital(sim, monkeypatch):
    monkeypatch.setattr(warfare, "REINFORCE_REACH", 10_000)
    a, b, c = three(sim)
    military = sim.military
    military._support(a, 1, [])
    assert military.reinforcing(a) is None, "the ally is in no danger"
    region = sim.world.regions[sim.world.capital_tiles[c.capital.tile]]
    region.held_by = b.id
    events: list = []
    military._support(a, 2, events)
    army = military.reinforcing(a)
    if army is None:
        pytest.skip("no way from one capital to the other on this map")
    assert army.post == c.capital.tile and army.size >= warfare.MIN_FIELD_ARMY
    assert any("stand with" in e["text"] for e in events)
    assert military._guests(c.capital.tile) == [], "it is not there yet"
    military._plan(a, army, 3)
    assert army.path and army.path[-1] == c.capital.tile
    army.tile, army.path = c.capital.tile, []
    assert military._guests(c.capital.tile) == [army]

    region.held_by = None
    military._support(a, 4, [])
    assert army.state != "returning", "it stays a while after the danger has passed"
    military._support(a, 4 + warfare.REINFORCE_STAY + 1, [])
    assert army.state == "returning"


def test_a_ruler_sends_and_calls_back_his_own_reinforcement(sim, monkeypatch):
    monkeypatch.setattr(warfare, "REINFORCE_REACH", 10_000)
    a, b, c = three(sim)
    ruler = sim.ruler
    ruler.command("take_control", {"civ": a.id})
    assert ruler.command("reinforce_ally", {"civ": b.id}) == "you can only send an army to stand with an ally"
    assert ruler.command("reinforce_ally", {"civ": c.id}) is None
    assert ruler.state()["reinforcing"] == {"civ": c.id, "city": None}
    sim.military._support(a, 1, [])
    army = sim.military.reinforcing(a)
    if army is None:
        pytest.skip("no way from one capital to the other on this map")
    assert ruler.state()["reinforcing"]["civ"] == c.id and ruler.state()["reinforce_targets"] == []
    sim.military._support(a, 500, [])
    assert army.state != "returning", "a ruler's army stays until he calls it back"
    assert ruler.command("recall_reinforcement", {}) is None
    sim.military._support(a, 501, [])
    assert army.state == "returning"


def test_an_army_is_counted_only_from_close_by_and_scouting_gives_exact_power(sim):
    a, b = sim.civs[0], sim.civs[1]
    military, world = sim.military, sim.world
    far = max(sorted(b.territory), key=lambda t: min(military._reach(t, s.tile) for s in a.settlements))
    assert min(military._reach(far, s.tile) for s in a.settlements) > warfare.SCOUT_RANGE
    army = Army(military.next_id(), b.id, far, "field", target_civ=a.id)
    army.add({"spearman": 40.0})
    b.armies.append(army)
    b.garrison.units = {}
    b.soldiers = 40.0
    assert not military.scouted(a, army) and military.sighted(a, b) == 0.0
    neighbour = next(n for n in stance_context(sim, a)["neighbors"] if n["id"] == b.id)
    assert neighbour["seen_power"] is None

    army.tile = next(t for t in world.neighbors(a.capital.tile))
    assert military.scouted(a, army) and military.sighted(a, b) == 1.0
    sim.__dict__.pop("_march_cache", None)
    neighbour = next(n for n in stance_context(sim, a)["neighbors"] if n["id"] == b.id)
    assert neighbour["seen_power"] == round(sim.diplomacy.power(b))
    sim.diplomacy.relation(a.id, b.id).status = "alliance"
    army.tile = far
    assert military.scouted(a, army), "allies show each other everything"
