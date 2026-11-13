import statistics

import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance, rules
from civsim.economy import compute_modifiers, find_site, footprint, manage_villagers, produce
from civsim.economy.rules import MAX_MOBILIZATION, WATER_PER_POP
from civsim.map import step_cost
from civsim.military import Army, Commander
from civsim.simulation import Simulation

NEW_ERAS = {4: "Renaissance", 5: "Age of Reason", 6: "Industrial"}
# The late techs raise buildings a level (a market becomes a bank, a workshop a factory) or open the harbour.
NEW_LEVELS = {("market", 2): "banking", ("barracks", 2): "military_academy", ("storehouse", 3): "waterworks",
              ("workshop", 3): "steam_power"}


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def mods_with(sim, civ, *techs):
    civ.known_techs = list(techs)
    return compute_modifiers(civ, sim.building_defs, sim.tech_tree)


# Added after the three new eras: the efficiency line (eras 3, 4 and 5) and the hospital line (1, 3 and 5).
EFFICIENCY = ("logistics", "quartermasters", "standing_army", "field_medicine", "surgeons", "military_hospitals")


def test_three_new_eras_of_six_techs_each_dearer_than_the_last(sim):
    tree = sim.tech_tree
    assert len(tree.techs) == 36 + len(EFFICIENCY)
    medians = []
    for era, name in NEW_ERAS.items():
        techs = [t for t in tree.techs.values() if t.era == era and t.id not in EFFICIENCY]
        assert tree.eras[era] == name and len(techs) == 6
        medians.append(statistics.median(t.science_cost for t in techs))
        for tech in techs:
            assert tech.effects and tech.materials
            assert all(tree.techs[p].era <= era for p in tech.prereqs)
    medieval = statistics.median(t.science_cost for t in tree.techs.values() if t.era == 3)
    assert medieval < medians[0] < medians[1] < medians[2]


def test_the_original_eighteen_techs_are_unchanged(sim):
    tree = sim.tech_tree
    old = [t for t in tree.techs.values() if t.era <= 3 and t.id not in EFFICIENCY]
    assert len(old) == 18
    assert tree.techs["agriculture"].cost == {"science": 30, "food": 20}
    assert tree.techs["guilds"].cost == {"science": 840, "stone": 60, "gold": 80}
    assert tree.techs["boatbuilding"].effects == {"boats": 1}


def test_new_levels_are_unlocked_by_their_techs(sim):
    for (building_id, level), tech_id in NEW_LEVELS.items():
        assert sim.building_defs[building_id].level_techs[str(level)] == tech_id
        assert sim.tech_tree.techs[tech_id].era >= 4
    assert sim.building_defs["harbour"].requires_tech == "navigation"
    assert sim.building_defs["storehouse"].level_bonus["3"]["store"] == {"water": 400}
    assert sim.building_defs["market"].level_bonus["2"]["income"]["gold"] > 0


def test_a_harbour_must_stand_on_the_water(sim):
    civ = sim.civs[0]
    world = sim.world
    harbour = sim.building_defs["harbour"]
    site = find_site(civ, world, harbour)
    if site is not None:
        assert any(world.is_water(n) for part in footprint(world, "harbour", site) for n in world.neighbors(part))
    inland = {t for t in civ.territory if not any(world.is_water(n) for n in world.neighbors(t))}
    civ.territory = inland | {civ.capital.tile}
    assert find_site(civ, world, harbour) is None


def test_water_and_sea_techs(sim):
    civ = sim.civs[0]
    civ.water_access = {"river": 0, "lake": 0, "coast": 10}
    base = mods_with(sim, civ, "pottery", "water_purification")
    assert base.income["water"] == pytest.approx(0.8 + 10 * 0.15)
    assert mods_with(sim, civ, "pottery", "water_purification", "desalination").purification == pytest.approx(0.4)
    works = mods_with(sim, civ, "pottery", "water_purification", "waterworks")
    assert works.income["water"] == pytest.approx(base.income["water"] * 1.25)
    assert works.storage["water"] == base.storage["water"] + 200
    assert mods_with(sim, civ, "boatbuilding", "navigation").boat_range == 4

    # Sanitation: people drink a fifth less.
    civ.population = 100
    civ.buildings = []
    civ.resources.update(water=250, food=250, wood=250)
    produce(civ, mods_with(sim, civ), sim.building_defs)
    plain = civ.upkeep["water"]
    produce(civ, mods_with(sim, civ, "sanitation"), sim.building_defs)
    assert plain == pytest.approx(WATER_PER_POP * 100)
    assert civ.upkeep["water"] == pytest.approx(0.8 * plain, rel=0.02)




def test_commander_training_techs(sim):
    civ = sim.civs[0]
    civ.commanders.clear()  # nobody in reserve, so each call raises a new commander
    civ.resources["gold"] = 20
    assert sim.military._appoint(civ).level == 1 and civ.resources["gold"] == 0, "promotion costs 20 gold"
    sim.modifiers[civ.id] = mods_with(sim, civ, "military_academy")
    civ.resources["gold"] = 100  # enough to promote, not to appoint a trained officer
    assert sim.military._appoint(civ).level == 2
    sim.modifiers[civ.id] = mods_with(sim, civ, "military_academy", "general_staff")
    civ.resources["gold"] = 100
    officer = sim.military._appoint(civ)
    assert officer.level == 3
    civ.resources["gold"] = 139
    assert sim.military._appoint(civ).level == 3, "not if it would take the treasury below its reserve"
    civ.resources["gold"] = 140
    assert sim.military._appoint(civ).level == 5, "an appointed officer starts two levels higher"
    assert civ.resources["gold"] == 20

    army = Army(1, civ.id, civ.capital.tile, "field", units={"spearman": 10.0}, commander=Commander("Test"))
    sim.military._gain(army, 10)
    assert army.commander.experience == pytest.approx(15), "experience comes 50% faster"
    assert sim.modifiers[civ.id].mobilization == pytest.approx(0.1)
    assert sim.diplomacy.mobilization_cap(civ) == pytest.approx(MAX_MOBILIZATION + 0.1)


def test_war_techs_change_the_fight(sim):
    civ = sim.civs[0]
    mods = mods_with(sim, civ, "gunpowder", "rifling", "siegecraft", "fortification", "railways")
    # Gunpowder arms troops a tier better instead of adding to their strength.
    assert mods.military == pytest.approx(0.1) and mods.tier == 2
    assert mods.casualties == pytest.approx(-0.1)
    assert mods.capture_speed == pytest.approx(0.5)
    assert mods.defense == pytest.approx(0.45), "fortification makes the castles fortresses"
    assert mods.home_speed == 1 and mods.reinforce == 1.0

    # On home ground a railway army covers two tiles where it used to cover one.
    sim.modifiers[civ.id] = mods
    home = sorted(civ.territory)
    start = civ.capital.tile
    path = [n for n in sim.world.neighbors(start)
            if n in civ.territory and step_cost(sim.world, n, False, False) == 1][:1]
    army = Army(2, civ.id, start, "field", units={"spearman": 10.0}, state="marching", path=list(path))
    sim.military._march(civ, army)
    assert army.tile == path[0] and army.move_points >= 0.5, "movement to spare after one step"
    assert home


def test_civil_engineering_and_banking(sim):
    civ = sim.civs[0]
    mods = mods_with(sim, civ, "civil_engineering")
    assert (mods.build_slots, mods.villager_speed) == (2, 1)
    tile = max((t for t in civ.territory if sim.world.walkable(t)),
               key=lambda t: abs(sim.world.xy(t)[0] - sim.world.xy(civ.capital.tile)[0])
               + abs(sim.world.xy(t)[1] - sim.world.xy(civ.capital.tile)[1]))
    civ.buildings = [Building("house", tile)]
    for v in civ.villagers:
        v.tile, v.task, v.target, v.path = civ.capital.tile, "idle", None, []
    manage_villagers(civ, sim.world, mods, iter(range(5000, 5100)).__next__)
    builder = next(v for v in civ.villagers if v.task == "build")
    walked = abs(sim.world.xy(builder.tile)[0] - sim.world.xy(civ.capital.tile)[0]) + abs(
        sim.world.xy(builder.tile)[1] - sim.world.xy(civ.capital.tile)[1])
    assert walked == 2 or builder.tile == tile, "villagers walk twice as fast"

    # Banking halves what a trade deal costs to open.
    a, b = sim.civs[0], sim.civs[1]
    sim.modifiers[a.id] = mods_with(sim, a, "banking")
    a.resources.update(wood=200, stone=0)
    b.resources.update(stone=200, wood=0)
    a.diplomacy_points = b.diplomacy_points = 100
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.TRADE, give="wood", give_rate=1.0)})
    sim.diplomacy.set_intents(b.id, {a.id: Intent(Stance.TRADE, give="stone", give_rate=1.0)})
    sim.diplomacy.update(1, [])
    assert sim.diplomacy.deals
    assert a.diplomacy_points == pytest.approx(100 + rules.DIPLOMACY_GAIN - 0.5 * rules.DEAL_FEE)
    assert b.diplomacy_points == pytest.approx(100 + rules.DIPLOMACY_GAIN - rules.DEAL_FEE)
