import json

import pytest

from civsim.bridge import protocol
from civsim.civ import Building
from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance
from civsim.economy import advance_construction, manage_villagers, produce
from civsim.economy.rules import SOLDIER_ORE
from civsim.map import BIOME_INFO
from civsim.military import UNIT_TYPES, Army, Commander, unit_strength
from civsim.military.army import MAX_COMMANDER_LEVEL
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain

ALL_UNIT_TECHS = ["agriculture", "animal_husbandry", "the_wheel", "mining", "bronze_working", "iron_working"]


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:  # plenty of influence, so tests are about the rule in question
        civ.diplomacy_points = 300.0
    return sim


def update(sim, ticks=1) -> list[str]:
    texts = []
    for _ in range(ticks):
        sim.tick += 1
        events: list = []
        sim.diplomacy.update(sim.tick, events)
        texts += [e["text"] for e in events]
    return texts


def go_to_war(sim, attacker, defender, soldiers=(60, 20)):
    """Declare war with the attacker's field army placed on the defender's border."""
    world = sim.world
    edge = next(n for t in sorted(defender.territory) for n in world.neighbors(t)
                if world.owner[n] < 0 and not world.is_open_water(n))
    world.claim(edge, attacker.id)
    attacker.territory.add(edge)
    attacker.resources["gold"] = 300
    attacker.population, defender.population = 400, 200
    attacker.soldiers, defender.soldiers = soldiers
    sim.diplomacy.set_intents(attacker.id, {defender.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    update(sim, 12)
    assert sim.diplomacy.relation(attacker.id, defender.id).war
    army = field(attacker, defender)
    army.tile, army.path = edge, []
    return army


def field(civ, enemy) -> Army:
    return next(a for a in civ.armies if a.role == "field" and a.target_civ == enemy.id)


# -- unit types --------------------------------------------------------------

def test_unit_roster_and_what_unlocks_it():
    assert set(UNIT_TYPES) == {"spearman", "archer", "swordsman", "cavalry"}
    assert UNIT_TYPES["spearman"].requires == ()
    assert UNIT_TYPES["archer"].requires == ("the_wheel",)
    assert UNIT_TYPES["swordsman"].requires == ("bronze_working",)
    assert set(UNIT_TYPES["cavalry"].requires) == {"animal_husbandry", "iron_working"}
    assert UNIT_TYPES["cavalry"].speed > UNIT_TYPES["spearman"].speed
    assert UNIT_TYPES["swordsman"].strength > UNIT_TYPES["archer"].strength > UNIT_TYPES["spearman"].strength
    assert UNIT_TYPES["swordsman"].upkeep["ore"] > UNIT_TYPES["spearman"].upkeep["ore"]
    assert UNIT_TYPES["archer"].upkeep["wood"] > 0


def test_counters_give_a_quarter_more_against_what_they_counter():
    assert unit_strength({"spearman": 10}) == 10
    assert unit_strength({"spearman": 10}, {"cavalry": 5}) == pytest.approx(12.5)
    assert unit_strength({"spearman": 10}, {"archer": 5}) == 10
    assert unit_strength({"cavalry": 10}, {"archer": 5}) == pytest.approx(25)
    assert unit_strength({"archer": 10}, {"spearman": 5, "swordsman": 5}) == pytest.approx(11 * 1.25)
    # Against a mixed enemy the edge is in proportion to how much of it is countered.
    assert unit_strength({"spearman": 10}, {"cavalry": 5, "archer": 5}) == pytest.approx(11.25)


def test_recruits_follow_the_techs_a_civ_has(sim):
    civ = sim.civs[0]
    civ.soldiers = 40
    sim.military._sync(civ)
    assert {u: round(n) for u, n in civ.unit_counts().items()} == {"spearman": 40}

    civ.known_techs = list(ALL_UNIT_TECHS)
    civ.soldiers = 400
    civ.horses = 100  # cavalry need horses from the stables
    sim.military._sync(civ)
    counts = civ.unit_counts()
    assert set(counts) == set(UNIT_TYPES)
    assert sum(counts.values()) == pytest.approx(400)
    for unit_id, unit in UNIT_TYPES.items():
        assert counts[unit_id] / 400 == pytest.approx(unit.share, abs=0.03)


def test_army_upkeep_depends_on_what_it_is_made_of(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.population, civ.soldiers, civ.soldier_target = 200, 50, 50
    civ.resources.update(gold=200, ore=200, wood=200, food=250, water=250)
    civ.armies = [Army(1, civ.id, civ.capital.tile, "garrison", units={"spearman": 50.0})]
    produce(civ, mods, sim.building_defs)
    spear_ore = civ.upkeep["ore"]
    civ.armies[0].units = {"swordsman": 50.0}
    produce(civ, mods, sim.building_defs)
    assert civ.upkeep["ore"] == pytest.approx(4 * spear_ore, rel=0.1)
    assert spear_ore == pytest.approx(0.5 * SOLDIER_ORE * civ.soldiers, rel=0.1)


# -- strength: the phase 3 formula, extended ---------------------------------

def test_plain_spearmen_are_exactly_the_old_soldier_strength(sim):
    civ = sim.civs[0]
    civ.soldiers = 30
    sim.military._sync(civ)
    assert sim.diplomacy.strength(civ) == pytest.approx(30 * sim.diplomacy.quality(civ))
    civ.unpaid = True
    assert sim.diplomacy.strength(civ) == pytest.approx(30 * 0.5), "pay still halves it"
    civ.unpaid = False
    sim.modifiers[civ.id].military = 0.3
    assert sim.diplomacy.strength(civ) == pytest.approx(30 * 1.3), "and military techs still multiply it"


def test_commander_skill_multiplies_army_strength(sim):
    civ = sim.civs[0]
    army = Army(99, civ.id, civ.capital.tile, "field", units={"swordsman": 20.0})
    base = sim.military.army_strength(army)
    assert base == pytest.approx(20 * 1.5)
    army.commander = Commander("Test")
    assert sim.military.army_strength(army) == pytest.approx(base), "a new commander adds nothing yet"
    army.commander.experience = 225  # level 4
    assert army.commander.level == 4
    assert sim.military.army_strength(army) == pytest.approx(base * 1.12)


def test_commander_levels_come_from_experience_and_are_capped():
    commander = Commander("Test")
    levels = []
    for experience in (0, 24, 25, 100, 225, 400, 2025, 99999):
        commander.experience = experience
        levels.append(commander.level)
    assert levels == [1, 1, 2, 3, 4, 5, 10, MAX_COMMANDER_LEVEL]
    assert commander.strength_bonus == pytest.approx(0.36)
    assert commander.casualty_reduction == pytest.approx(0.18)


# -- armies on the map -------------------------------------------------------

def test_a_civ_at_peace_has_only_a_garrison_without_a_commander(sim):
    civ = sim.civs[0]
    civ.soldiers = 12
    update(sim)
    assert [a.role for a in civ.armies] == ["garrison"]
    assert civ.garrison.commander is None and civ.garrison.tile == civ.capital.tile
    assert civ.garrison.size == pytest.approx(12)


def test_war_raises_a_field_army_with_a_commander_per_enemy(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b)
    assert army.commander is not None and army.commander.level == 1
    assert army.size == pytest.approx(0.8 * 60, abs=1), "a fifth of the soldiers stay to hold the capital"
    assert a.garrison.size == pytest.approx(0.2 * 60, abs=1)
    assert sum(x.size for x in a.armies) == pytest.approx(a.soldiers)
    defender_army = field(b, a)
    assert defender_army.commander is not None and defender_army.tile == b.capital.tile


def test_armies_march_tile_by_tile_and_take_the_ground_in_their_way(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b, soldiers=(150, 0))
    land = len(b.territory)
    positions = [army.tile]
    texts = []
    for _ in range(1500):
        texts += update(sim)
        a.soldiers = 150
        a.unpaid = a.unsupplied = False
        positions.append(army.tile)
        if any("falls with it" in t for t in texts):
            break
    assert any("falls with it" in t for t in texts), "it fought its way to a capital"
    assert len(b.territory) < land
    moves = [(p, q) for p, q in zip(positions, positions[1:]) if p != q]
    assert len(moves) > 3, "the army moved"
    for p, q in moves:
        (px, py), (qx, qy) = sim.world.xy(p), sim.world.xy(q)
        assert abs(px - qx) + abs(py - qy) == 1, "one tile at a time, never a jump"


@pytest.mark.usefixtures("no_war_minimum")  # this one is about the battle, not the declaration
def test_battle_the_stronger_army_wins_and_the_loser_falls_back(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b, soldiers=(20, 80))
    pop_a, pop_b = a.population, b.population
    texts = update(sim, 60)
    war = sim.diplomacy.relation(a.id, b.id).war
    assert any("routs" in t for t in texts)
    assert war.casualties[a.id] > 0 and war.casualties[b.id] > 0
    assert a.soldiers < 20 and a.population < pop_a and b.population < pop_b, "the dead come off the population"
    assert sum(x.size for x in a.armies) == pytest.approx(a.soldiers)
    assert army.state in ("retreating", "idle")
    winner = field(b, a).commander
    assert winner.wins >= 1 and winner.battles >= 1 and winner.experience >= 25
    assert winner.level >= 2, "winning battles is what raises a commander"


def test_a_better_commander_wins_an_otherwise_even_fight(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b, soldiers=(100, 100))
    other = field(b, a)
    other.tile, other.path = sim.world.neighbors(army.tile).__next__(), []
    for civ in (a, b):  # same population, so the same militia: only leadership differs
        civ.population = 300
    # Neutral ground for both: fight outside either territory.
    for tile in (army.tile, other.tile):
        owner = sim.world.owner[tile]
        if owner >= 0:
            sim.civs[owner].territory.discard(tile)
            sim.world.owner[tile] = -1
    army.commander.experience = 2025  # level 10
    lost = {army.id: army.size, other.id: other.size}
    for _ in range(300):
        sim.tick += 1
        busy = sim.military._fight(sim.tick, [])
        if army.state == "retreating" or other.state == "retreating":
            break
        assert busy
    assert other.state == "retreating" and army.state != "retreating"
    assert lost[other.id] - other.size > lost[army.id] - army.size, "and it loses fewer soldiers doing it"
    assert army.commander.wins == 1


def face_off(sim, a, b, soldiers=(100, 100)):
    """Two field armies side by side on ground neither civ owns."""
    army = go_to_war(sim, a, b, soldiers=soldiers)
    other = field(b, a)
    other.tile, other.path = next(sim.world.neighbors(army.tile)), []
    for civ in (a, b):
        civ.population = 300
    for tile in (army.tile, other.tile):
        owner = sim.world.owner[tile]
        if owner >= 0:
            sim.civs[owner].territory.discard(tile)
            sim.world.owner[tile] = -1
    return army, other


def battle_length(sim, army, other) -> int:
    for ticks in range(1, 2000):
        sim.tick += 1
        sim.military._fight(sim.tick, [])
        if "retreating" in (army.state, other.state):
            return ticks
    return 2000


def fresh_battle(soldiers) -> tuple[int, object, object]:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:
        civ.diplomacy_points = 300.0
    army, other = face_off(sim, sim.civs[0], sim.civs[1], soldiers)
    return battle_length(sim, army, other), army, other


def test_battle_length_follows_only_from_how_evenly_matched_the_armies_are():
    lengths = {theirs: fresh_battle((100, theirs))[0] for theirs in (30, 60, 80, 90, 95, 99)}
    assert lengths[30] == 1, "badly outmatched: broken at once, with no minimum to sit through"
    assert list(lengths.values()) == sorted(lengths.values()), "the closer the fight, the longer it runs"
    assert lengths[60] < 15
    for close in (90, 95, 99):
        assert 30 <= lengths[close] <= 100, f"a close battle grinds on, but not forever ({close}: {lengths[close]})"


def test_the_weaker_army_is_the_one_that_breaks_and_both_pay_for_a_long_fight():
    length, army, other = fresh_battle((100, 95))
    assert other.state == "retreating" and army.state != "retreating"
    assert army.size < 0.75 * 80 and other.size < army.size, "a long, close battle is costly for the winner too"
    quick, army, other = fresh_battle((100, 30))
    assert army.size > 0.99 * 80, "a walkover costs the winner almost nothing"
    assert quick < length


def test_nothing_ends_a_battle_but_one_side_breaking(sim):
    """No ceiling: two armies that stay level keep fighting for as long as they stay level."""
    a, b = sim.civs[0], sim.civs[1]
    army, other = face_off(sim, a, b, (100, 100))
    for _ in range(150):
        sim.tick += 1
        assert sim.military._fight(sim.tick, []), "still engaged"
        a.soldiers = b.soldiers = 80.0  # both sides keep their numbers up
        army.units, other.units = {"spearman": 80.0}, {"spearman": 80.0}
    assert "retreating" not in (army.state, other.state)


def test_a_beaten_garrison_is_scattered_not_routed(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b, soldiers=(150, 10))
    b.armies = [x for x in b.armies if x.role == "garrison"]  # only the garrison is home
    garrison = b.garrison
    garrison.units = {"spearman": 10.0}
    b.soldiers = 10.0
    army.tile, army.path = next(n for n in sim.world.neighbors(b.capital.tile) if not sim.world.is_water(n)), []
    events: list = []
    for _ in range(40):
        sim.tick += 1
        sim.military._fight(sim.tick, events)
        if events:
            break
    assert any("scatters the garrison" in e["text"] for e in events)
    assert garrison.tile == b.capital.tile and garrison.state != "retreating", "it has nowhere to fall back to"
    assert sim.military._broken(garrison, sim.tick), "and cannot fight again until it rallies"
    assert not sim.military._fight(sim.tick + 1, []), "so the attacker is free to press on"


def test_commanders_keep_their_experience_between_wars(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b)
    veteran = army.commander
    veteran.experience = 400
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.IGNORE)})
    update(sim, 60)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"
    for _ in range(1500):  # the army walks home and stands down
        update(sim)
        if all(x.role == "garrison" for x in a.armies):
            break
    assert [x.role for x in a.armies] == ["garrison"]
    assert veteran in a.commanders and veteran.level == 5
    assert a.garrison.size == pytest.approx(a.soldiers)
    assert sim.military._appoint(a) is veteran, "the next war goes to the most experienced commander"


def test_armies_cannot_cross_open_water_without_boats(sim):
    a = sim.civs[0]
    world = sim.world
    lake = next(i for i, biome in enumerate(world.biomes) if biome.name == "LAKE")
    shore = next(n for n in world.neighbors(lake) if not world.is_water(n))
    army = Army(77, a.id, shore, "field", units={"spearman": 10.0}, state="marching", path=[lake])
    sim.military._march(a, army)
    assert army.tile == shore and army.path == []
    sim.modifiers[a.id].boats = 1
    army.path = [lake]
    sim.military._march(a, army)
    assert army.tile == shore and army.path == [], "boats still need a harbour to put out from"
    a.buildings.append(Building("harbour", shore, 1.0, True))
    army.path = [lake]
    sim.military._march(a, army)
    assert army.tile == lake and army.boat


# -- what the viewer is told --------------------------------------------------

def test_protocol_describes_armies_for_the_map(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.known_techs = list(ALL_UNIT_TECHS)
    a.horses = 40  # so that there is cavalry to show
    go_to_war(sim, a, b, soldiers=(120, 40))
    init = json.loads(protocol.init_message(sim))
    assert set(init["data"]["unit_types"]) == set(UNIT_TYPES)
    data = json.loads(protocol.tick_message(sim, False, 2.0))["data"]
    mine = [x for x in data["armies"] if x["civ"] == a.id]
    led = next(x for x in mine if x["role"] == "field")
    assert led["commander"]["name"] and led["commander"]["level"] == 1
    assert sum(led["units"].values()) == pytest.approx(led["size"], abs=2)
    assert set(led["units"]) == set(UNIT_TYPES), "the count of each unit type, to show above the commander"
    home = next(x for x in mine if x["role"] == "garrison")
    assert home["commander"] is None
    assert home["dominant"] in UNIT_TYPES, "no commander: the viewer shows the dominant unit type"
    assert home["dominant"] == max(home["units"], key=home["units"].get)
    assert {"id", "civ", "x", "y", "state", "strength"} <= set(led)
    assert all(v["task"] in ("idle", "build", "gather") for v in data["villagers"])


# -- villagers ----------------------------------------------------------------

def site_at_distance(sim, civ, far: bool) -> int:
    world = sim.world
    cx, cy = world.xy(civ.capital.tile)
    tiles = [t for t in sorted(civ.territory) if t != civ.capital.tile and BIOME_INFO[world.biomes[t]].buildable]
    key = lambda t: abs(world.xy(t)[0] - cx) + abs(world.xy(t)[1] - cy)  # noqa: E731
    return max(tiles, key=key) if far else min(tiles, key=key)


def build_time(sim, civ, tile) -> int:
    civ.buildings = [Building("house", tile)]
    mods = sim.modifiers[civ.id]
    for v in civ.villagers:
        v.tile, v.task, v.target, v.path = civ.capital.tile, "idle", None, []
    for tick in range(1, 200):
        manage_villagers(civ, sim.world, mods, lambda: 10_000 + tick)
        advance_construction(civ, mods, sim.building_defs, [])
        if civ.buildings[0].complete:
            return tick
    raise AssertionError("never finished")


def test_every_civ_starts_with_villagers_and_gains_more_as_it_grows(sim):
    civ = sim.civs[0]
    assert len(civ.villagers) == 2
    civ.population = 200
    manage_villagers(civ, sim.world, sim.modifiers[civ.id], iter(range(500, 600)).__next__)
    assert len(civ.villagers) == 8
    civ.population = 20
    manage_villagers(civ, sim.world, sim.modifiers[civ.id], iter(range(600, 700)).__next__)
    assert len(civ.villagers) == 8, "villagers are never removed"


def test_a_building_only_advances_while_a_villager_is_on_site(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    tile = site_at_distance(sim, civ, far=True)
    civ.buildings = [Building("house", tile)]
    builders = list(civ.villagers)
    civ.villagers = []
    for _ in range(20):
        advance_construction(civ, mods, sim.building_defs, [])
    assert civ.buildings[0].progress == 0, "nobody there: nothing gets built"

    civ.villagers = builders
    manage_villagers(civ, sim.world, mods, iter(range(700, 800)).__next__)
    builder = next(v for v in civ.villagers if v.task == "build")
    assert builder.target == tile
    advance_construction(civ, mods, sim.building_defs, [])
    assert civ.buildings[0].progress == 0, "still walking there"
    while builder.tile != tile:
        manage_villagers(civ, sim.world, mods, iter(range(800, 900)).__next__)
    advance_construction(civ, mods, sim.building_defs, [])
    assert civ.buildings[0].progress > 0


def test_building_far_from_the_villagers_takes_longer(sim):
    civ = sim.civs[0]
    near = build_time(sim, civ, site_at_distance(sim, civ, far=False))
    far = build_time(sim, civ, site_at_distance(sim, civ, far=True))
    assert far > near
    assert near >= sim.building_defs["house"].build_time


def test_villagers_on_a_captured_tile_change_sides_and_wait_for_orders(sim):
    a, b = sim.civs[0], sim.civs[1]
    go_to_war(sim, a, b)
    relation = sim.diplomacy.relation(a.id, b.id)
    tile = site_at_distance(sim, b, far=True)
    b.buildings = [Building("house", tile, 0.5)]
    worker = b.villagers[0]
    worker.tile, worker.task, worker.target, worker.path = tile, "build", tile, []
    everyone = len(a.villagers) + len(b.villagers)

    sim.diplomacy._capture_tile(relation, a, b, tile, sim.tick, [])
    assert worker in a.villagers and worker not in b.villagers
    assert (worker.task, worker.target, worker.path) == ("idle", None, []), "it drops what it was doing"
    assert len(a.villagers) + len(b.villagers) == everyone, "nobody is killed or removed"
    assert worker.tile == tile

    # Its new owner puts it to work on its next turn: here, finishing the captured house.
    manage_villagers(a, sim.world, sim.modifiers[a.id], iter(range(900, 950)).__next__)
    assert worker.task in ("build", "gather")
    assert any(v.task == "build" and v.target == tile for v in a.villagers)


def test_armies_never_harm_villagers(sim):
    a, b = sim.civs[0], sim.civs[1]
    army = go_to_war(sim, a, b, soldiers=(150, 30))
    for villager in b.villagers:
        villager.tile, villager.path = army.tile, []
    count = len(a.villagers) + len(b.villagers)
    ids = {v.id for civ in (a, b) for v in civ.villagers}
    for _ in range(80):
        update(sim)
        a.soldiers = 150
    assert len(a.villagers) + len(b.villagers) == count
    assert {v.id for civ in (a, b) for v in civ.villagers} == ids


# -- the whole thing ----------------------------------------------------------

def test_long_game_keeps_armies_consistent():
    sim = Simulation(SimConfig(seed=5))  # a seed on which the rule-based strategists go to war
    brain = RuleBrain()
    wars = 0
    for _ in range(1500):
        for event in sim.step_with(brain):
            wars += "declares war" in event["text"]
        for civ in sim.civs:
            assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers, abs=1e-3 + 0.02 * civ.soldiers)
    assert wars > 0
    for civ in sim.civs:
        if not civ.alive:
            assert not civ.armies and civ.soldiers == 0, "a destroyed civ leaves no army behind"
            continue
        assert sum(1 for a in civ.armies if a.role == "garrison") == 1
        assert all(a.commander is None for a in civ.armies if a.role == "garrison")
        assert all(count >= -1e-9 for a in civ.armies for count in a.units.values())
        assert len(civ.villagers) >= 2
        tiles = [b.tile for b in civ.buildings]
        assert set(tiles) <= civ.territory
