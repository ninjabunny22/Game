import json

import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.datafiles import load_json
from civsim.diplomacy import rules
from civsim.map import BIOME_INFO, generate_map, region_neighbours
from civsim.map.regions import MAX_SHARE, MIN_SHARE, REGION_COUNT
from civsim.military import Army
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain, stance_context


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def neutral_neighbour(sim, civ):
    """A neutral region touching the civ's land."""
    touching = region_neighbours(sim.world)
    held = {r.id for r in sim.world.regions if r.owner == civ.id}
    return next(r for r in sim.world.regions if r.neutral and touching[r.id] & held)




# -- the map -------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3, 5, 7, 11, 42, 99])
def test_sixteen_regions_of_fair_size_cover_all_the_land(seed):
    world = generate_map(seed)
    assert len(world.regions) == REGION_COUNT == 16
    land = [i for i in range(len(world.biomes)) if not world.is_water(i)]
    assert all(world.region_of[t] >= 0 for t in land), "no land outside a region"
    sizes = [sum(1 for t in region.tiles if not world.is_water(t)) for region in world.regions]
    mean = sum(sizes) / len(sizes)
    assert min(sizes) >= MIN_SHARE * mean, "no region tiny compared to the others"
    assert max(sizes) <= MAX_SHARE * mean, "and none dominating the map"
    assert sum(len(region.tiles) for region in world.regions) == len({t for r in world.regions for t in r.tiles})


@pytest.mark.parametrize("seed", [1, 3, 42])
def test_each_region_has_a_capital_inside_it(seed):
    world = generate_map(seed)
    for region in world.regions:
        assert world.region_of[region.capital] == region.id
        assert BIOME_INFO[world.biomes[region.capital]].buildable
        assert world.capital_tiles[region.capital] == region.id
    assert len(world.capital_tiles) == 16


def test_names_come_from_a_fixed_list_assigned_by_the_seed():
    names = load_json("regions.json")
    assert len(names["regions"]) >= 28 and len(names["capitals"]) >= 28, "spare names beyond the 16 needed"
    assert len(set(names["regions"])) == len(names["regions"]) and len(set(names["capitals"])) == len(names["capitals"])
    assert names["faction"]["name"] == "the Hinterfolk"
    a, b, c = generate_map(11), generate_map(11), generate_map(12)
    assert [(r.name, r.capital_name) for r in a.regions] == [(r.name, r.capital_name) for r in b.regions]
    assert [r.name for r in a.regions] != [r.name for r in c.regions]
    for region in a.regions:
        assert region.name in names["regions"] and region.capital_name in names["capitals"]
    assert len({r.name for r in a.regions}) == 16 and len({r.capital_name for r in a.regions}) == 16


# -- the start -----------------------------------------------------------------

@pytest.mark.parametrize("seed", [3, 7, 42])
def test_each_civ_starts_with_two_whole_regions_and_the_rest_are_neutral(seed):
    sim = Simulation(SimConfig(seed=seed))
    world = sim.world
    assert sum(r.neutral for r in world.regions) == 8
    for civ in sim.civs:
        held = [r for r in world.regions if r.owner == civ.id]
        assert len(held) == 2
        assert civ.capital.tile in {r.capital for r in held}, "its capital is one of the region capitals"
        assert civ.capital.name in {r.capital_name for r in held}
        assert civ.territory == {t for r in held for t in r.tiles}
        assert len(civ.settlements) == 2
    for region in world.regions:
        if region.neutral:
            assert all(world.owner[t] < 0 for t in region.tiles), "native land belongs to no civ"
            assert region.garrison == rules.NATIVE_GARRISON
    homes = [world.xy(civ.capital.tile) for civ in sim.civs]
    assert min(abs(ax - bx) + abs(ay - by) for i, (ax, ay) in enumerate(homes) for bx, by in homes[i + 1:]) >= 15


def test_land_changes_hands_only_as_whole_regions(sim):
    """Nobody settles native land tile by tile: a civ holds every tile of its regions and
    nothing else, however long it plays, until it takes another region whole."""
    brain = RuleBrain()
    world = sim.world
    for _ in range(300):
        sim.step_with(brain)
        for civ in sim.civs:
            held = {r.id for r in world.regions if r.owner == civ.id}
            assert all(world.region_of[t] in held for t in civ.territory)
            assert all(world.owner[t] == civ.id for r in held for t in world.regions[r].tiles)
    for region in world.regions:
        if region.neutral:
            assert all(world.owner[t] < 0 for t in region.tiles), "native land belongs to no civ until taken"


# -- the Hinterfolk ------------------------------------------------------------

def test_garrisons_grow_with_the_game_but_stay_weaker_than_a_civ(sim):
    natives = sim.natives
    assert natives.garrison_size(0) == rules.NATIVE_GARRISON
    assert natives.garrison_size(1000) == pytest.approx(18)
    assert natives.garrison_size(100_000) == rules.NATIVE_GARRISON_MAX
    region = next(r for r in sim.world.regions if r.neutral)
    region.garrison = 1.0
    sim.natives.update(1, [])
    assert 1.0 < region.garrison < rules.NATIVE_GARRISON, "it recovers when left alone, gradually"
    for tick in (1000, 2000, 3000):
        typical_field_army = 0.8 * 0.35 * (200 + 0.3 * tick)  # a mid-sized civ fully mobilised
        assert natives.garrison_size(tick) < 0.5 * typical_field_army


def test_natives_take_no_part_in_diplomacy(sim):
    civ = sim.civs[0]
    context = stance_context(sim, civ)
    assert len(context["neighbors"]) == 3 and context["neutral_regions"] == 8
    assert all("Hinterfolk" not in n["name"] for n in context["neighbors"])
    brain = RuleBrain()
    for _ in range(200):
        sim.step_with(brain)
    assert all(request.civ_id in range(4) for request in sim.take_requests())








def test_natives_never_go_over_without_a_fight(sim):
    region = neutral_neighbour(sim, sim.civs[0])
    for check in range(1, 200):
        sim.natives.update(check * 25, [])
    assert region.neutral and all(sim.world.owner[t] < 0 for t in region.tiles)


# -- campaigns -----------------------------------------------------------------

def test_a_strong_civ_takes_a_neighbouring_native_capital_by_force(sim):
    civ = sim.civs[0]
    region = neutral_neighbour(sim, civ)
    civ.population = 400
    civ.resources.update(gold=250, ore=250, food=250)
    points = civ.diplomacy_points
    need = 2 * sim.natives.defence(region)

    sim.military._sync(civ)
    sim.military._campaign(civ, sim.tick)
    assert civ.campaign_muster > 0, "it starts raising troops"
    assert not [a for a in civ.armies if a.target_region is not None], "but does not march under strength"

    events: list = []
    for _ in range(1200):
        sim.step()
        civ.resources.update(gold=250, ore=250, food=250, water=250)
        events += sim.events
        if not region.neutral:
            break
    assert region.owner == civ.id
    assert any("from the Hinterfolk" in e["text"] for e in events)
    # Every native tile is taken; land another civ had already settled there stays its own.
    assert all(sim.world.owner[t] == civ.id or sim.world.owner[t] in {c.id for c in sim.civs if c is not civ}
               for t in region.tiles)
    assert sum(sim.world.owner[t] == civ.id for t in region.tiles) > len(region.tiles) / 2
    assert civ.diplomacy_points >= points, "no declaration and no diplomacy cost"
    assert need > 0 and not sim.diplomacy.enemies(civ.id)


def test_an_expedition_only_marches_at_about_twice_the_garrison(sim):
    civ = sim.civs[0]
    region = neutral_neighbour(sim, civ)
    civ.population = 400
    civ.resources["gold"] = 250
    defence = sim.natives.defence(region)
    for soldiers, marches in ((1.5 * defence / 0.8, False), (2.1 * defence / 0.8, True)):
        civ.armies = [a for a in civ.armies if a.role == "garrison"]
        civ.soldiers = soldiers
        civ.unpaid = civ.unsupplied = False
        sim.military._sync(civ)
        sim.military._campaign(civ, sim.tick)
        assert bool([a for a in civ.armies if a.target_region is not None]) is marches


def test_a_failed_attack_is_beaten_off_and_not_repeated_at_once(sim):
    civ = sim.civs[0]
    region = neutral_neighbour(sim, civ)
    civ.population = 200
    capital = region.capital
    beside = next(n for n in sim.world.neighbors(capital) if not sim.world.is_water(n))
    army = Army(500, civ.id, beside, "field", units={"spearman": 4.0}, target_region=region.id, state="marching")
    civ.armies.append(army)
    civ.soldiers = 4.0
    region.garrison = 30.0
    events: list = []
    for tick in range(1, 30):
        sim.military._storm(civ, army, tick, events)
        if army.state == "retreating":
            break
    assert army.state == "retreating" and region.neutral
    assert any("beaten off by the Hinterfolk" in e["text"] for e in events)
    assert civ.campaign_cooldown > 100
    assert region.garrison < 30.0, "the garrison took losses too"
    sim.military._campaign(civ, 50)
    assert civ.campaign_muster == 0


def test_an_expedition_carries_on_through_a_distant_war_but_comes_home_to_defend(sim):
    civ, enemy = sim.civs[0], sim.civs[1]
    region = neutral_neighbour(sim, civ)
    army = Army(501, civ.id, civ.capital.tile, "field", units={"spearman": 30.0}, target_region=region.id, state="marching")
    civ.armies.append(army)
    civ.soldiers = 30.0
    relation = sim.diplomacy.relation(civ.id, enemy.id)
    sim.diplomacy._start_war(enemy, civ, 1, aggressors={enemy.id})
    assert relation.war
    sim.military._campaign(civ, 2)
    assert army.state == "marching", "a war far away does not stop it"
    # An enemy army at the gates of one of its castles does.
    raider = Army(502, enemy.id, civ.capital.tile, "field", units={"spearman": 40.0}, target_civ=civ.id, state="marching")
    enemy.armies.append(raider)
    sim.military._campaign(civ, 3)
    assert army.state == "returning"


# -- protocol ------------------------------------------------------------------

def test_protocol_carries_regions_and_who_holds_them(sim):
    init = json.loads(protocol.init_message(sim))["data"]
    size = init["map"]["width"] * init["map"]["height"]
    assert len(init["map"]["region_ids"]) == size
    assert len(init["regions"]) == 16
    assert {"id", "name", "capital", "x", "y"} <= set(init["regions"][0])
    assert init["native_faction"] == {"name": "the Hinterfolk", "color": "#9c8f7a"}
    tick = json.loads(protocol.tick_message(sim, False, 2.0))["data"]
    owners = [r["owner"] for r in tick["regions"]]
    assert owners.count(None) == 8 and sorted(o for o in owners if o is not None) == [0, 0, 1, 1, 2, 2, 3, 3]
    for civ in tick["civs"]:
        assert civ["alive"] and len(civ["regions"]) == 2 and len(civ["settlements"]) == 2


def test_long_game_keeps_regions_consistent():
    sim = Simulation(SimConfig(seed=42))
    brain = RuleBrain()
    for _ in range(2500):
        sim.step_with(brain)
    world = sim.world
    for region in world.regions:
        holders = [civ for civ in sim.civs if region.capital in {s.tile for s in civ.settlements}]
        if region.neutral:
            assert not holders and world.owner[region.capital] < 0
        else:
            assert [civ.id for civ in holders] == [region.owner]
            assert world.owner[region.capital] == region.owner
    for civ in sim.civs:
        assert civ.alive == bool(civ.settlements)
        assert all(world.owner[t] == civ.id for t in civ.territory)
    owned = [t for civ in sim.civs for t in civ.territory]
    assert len(owned) == len(set(owned))
    assert sum(not r.neutral for r in world.regions) > 8, "regions changed hands"
