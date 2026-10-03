import pytest

from civsim.civ import Building
from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance
from civsim.economy import compute_modifiers, produce
from civsim.economy.rules import BASE_STORAGE, RESOURCES
from civsim.map import BIOME_INFO
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain

STORES = {"granary": "food", "lumber_yard": "wood", "stone_yard": "stone", "ore_depot": "ore", "treasury": "gold",
          "cistern": "water"}


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:  # plenty of influence, so tests are about the rule in question
        civ.diplomacy_points = 300.0
    return sim


def free_tiles(sim, civ):
    taken = civ.buildings_by_tile()
    return [t for t in sorted(civ.territory) if t not in taken and BIOME_INFO[sim.world.biomes[t]].buildable]


def test_each_storage_building_raises_only_its_own_cap(sim):
    civ = sim.civs[0]
    civ.water_access = {"river": 0, "lake": 0, "coast": 0}  # the water cap also grows with access; keep it out of this
    assert compute_modifiers(civ, sim.building_defs, sim.tech_tree).storage == dict.fromkeys(RESOURCES, BASE_STORAGE)
    assert "storehouse" not in sim.building_defs
    tiles = free_tiles(sim, civ)
    for building_id, res in STORES.items():
        assert sim.building_defs[building_id].stores == {res: 300}
    civ.buildings += [Building("granary", tiles[0], 1.0, True), Building("granary", tiles[1], 1.0, True),
                      Building("ore_depot", tiles[2], 1.0, True), Building("treasury", tiles[3], 0.5, False)]
    storage = compute_modifiers(civ, sim.building_defs, sim.tech_tree).storage
    assert storage == {"food": BASE_STORAGE + 600, "wood": BASE_STORAGE, "stone": BASE_STORAGE,
                       "ore": BASE_STORAGE + 300, "gold": BASE_STORAGE, "water": BASE_STORAGE}, "unfinished buildings hold nothing"


def test_production_stops_at_the_cap_and_workers_move_on(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.capacity.update(wood=50, stone=50)
    civ.resources.update(wood=BASE_STORAGE - 0.5, stone=0)
    civ.workers = dict.fromkeys(RESOURCES, 0.0) | {"wood": 10.0}
    produce(civ, mods, sim.building_defs)
    assert civ.resources["wood"] <= BASE_STORAGE, "nothing is produced past the cap"

    civ.resources["wood"] = BASE_STORAGE
    sim.ai._allocate_workers(civ, mods)
    assert civ.workers["wood"] == 0, "no workers are put on a full resource"
    assert civ.workers["stone"] > 0, "they go where there is room"


def test_everything_full_means_idle_workers(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.population = 60
    for res in RESOURCES:
        civ.resources[res] = mods.storage[res]
    sim.ai._allocate_workers(civ, mods)
    assert civ.idle > 0
    assert sum(civ.workers[res] for res in RESOURCES if res != "food") == 0


def test_a_full_store_makes_the_civ_build_room_for_that_resource(sim):
    civ = sim.civs[0]
    civ.known_techs = ["pottery"]
    for _ in range(300):
        sim.step()
    built = {b.type for b in civ.buildings}
    assert built & set(STORES), "storage buildings appear once stores fill up"
    mods = sim.modifiers[civ.id]
    for building_id, res in STORES.items():
        count = sum(1 for b in civ.buildings if b.type == building_id and b.complete and b.active)
        if res == "water":
            continue  # its cap also follows river, lake and coast access; covered in test_water
        assert mods.storage[res] == BASE_STORAGE + 100 + 300 * count  # pottery adds 100 to every cap


def test_a_cost_above_the_cap_makes_the_civ_want_more_room(sim):
    civ = sim.civs[0]
    mods = sim.modifiers[civ.id]
    civ.resources["stone"] = 0  # nowhere near full
    assert sim.ai.assess_needs(civ, mods)["store"]["stone"] == 0
    assert not sim.ai._feasible(civ, {"stone": BASE_STORAGE + 1}, mods)
    assert sim.ai.assess_needs(civ, mods)["store"]["stone"] == 1.0


def test_capturing_a_storage_building_transfers_its_share_of_the_stock(sim):
    a, b = sim.civs[0], sim.civs[1]
    world = sim.world
    edge = next(n for t in sorted(b.territory) for n in world.neighbors(t) if world.owner[n] < 0)
    world.claim(edge, a.id)
    a.territory.add(edge)

    # A granary on every free tile the defender has: wherever the attacker breaks in, it takes one.
    tiles = [t for t in free_tiles(sim, b) if t not in set(world.neighbors(b.capital.tile, diagonal=True))]
    b.buildings += [Building("granary", t, 1.0, True) for t in tiles]
    sim.modifiers[b.id] = compute_modifiers(b, sim.building_defs, sim.tech_tree)
    cap = sim.modifiers[b.id].storage["food"]
    assert cap == BASE_STORAGE + 300 * len(tiles)
    b.resources["food"] = cap
    b.population, b.soldiers = 20, 0
    a.population, a.soldiers = 400, 140
    a.resources.update(gold=100, food=BASE_STORAGE)  # the attacker's own granary is already full
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})

    texts = []
    for tick in range(1, 400):
        events: list = []
        sim.tick = tick
        sim.diplomacy.update(tick, events)
        texts += [e["text"] for e in events]
        a.soldiers = 140
        a.unpaid = a.unsupplied = False
        army = next((x for x in a.armies if x.role == "field"), None)
        if army and tick == 15:
            army.tile, army.path = edge, []  # the army has marched to the border
        if any("captures a Granary" in t for t in texts):
            break
    assert any("captures a Granary" in t for t in texts)
    # A breach can take the granaries on either side of it too, so count what was captured.
    captured = len([bld for bld in a.buildings if bld.type == "granary"])
    assert captured >= 1, "the granary itself changes hands"
    share = 300 * captured  # the stores were full, so each granary held its full 300
    assert b.resources["food"] == pytest.approx(cap - share)
    assert a.resources["food"] == pytest.approx(BASE_STORAGE + share), "all of it arrives"
    assert sim.modifiers[b.id].storage["food"] == cap - share
    assert len([bld for bld in b.buildings if bld.type == "granary"]) == len(tiles) - captured
    assert sim.modifiers[a.id].storage["food"] == BASE_STORAGE + share, "and raises the captor's cap"
    assert compute_modifiers(a, sim.building_defs, sim.tech_tree).storage["food"] == BASE_STORAGE + share

    # Stock above the cap is kept: no more is produced, but nothing is thrown away.
    a.resources["food"] += 200
    a.workers = dict.fromkeys(RESOURCES, 0.0) | {"food": 50.0}
    a.capacity["food"] = 100
    before = a.resources["food"]
    produce(a, sim.modifiers[a.id], sim.building_defs)
    assert a.resources["food"] < before, "only upkeep comes off"
    assert a.resources["food"] > before - 60


def test_long_run_keeps_stock_within_caps():
    sim = Simulation(SimConfig(seed=5))
    brain = RuleBrain()
    for _ in range(1200):
        sim.step_with(brain)
    wars = any("war" in entry["text"] for entry in sim.diplomacy.history)
    for civ in sim.civs:
        mods = sim.modifiers[civ.id]
        assert all(civ.resources[res] >= 0 for res in RESOURCES)
        if not wars:
            assert all(civ.resources[res] <= mods.storage[res] + 1e-6 for res in RESOURCES)
