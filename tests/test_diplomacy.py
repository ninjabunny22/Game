import pytest

from civsim.civ import Building
from civsim.map import BIOME_INFO
from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance
from civsim.diplomacy import rules
from civsim.simulation import Simulation


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def trade(give: str, rate: float, want: str | None = None) -> Intent:
    return Intent(Stance.TRADE, give=give, give_rate=rate, want=want, want_rate=rules.MAX_RATE)


def events_of(sim: Simulation, ticks: int) -> list[str]:
    texts = []
    for tick in range(sim.tick + 1, sim.tick + 1 + ticks):
        sim.tick = tick
        events: list = []
        sim.diplomacy.update(tick, events)
        texts += [e["text"] for e in events]
    return texts


def make_neighbours(sim: Simulation, a, b) -> None:
    """Give `a` a strip of land right up against `b`'s territory."""
    world = sim.world
    edge = next(n for t in sorted(b.territory) for n in world.neighbors(t) if world.owner[n] < 0)
    world.claim(edge, a.id)
    a.territory.add(edge)


# -- trade -------------------------------------------------------------------

def test_mutual_trade_opens_a_deal_that_moves_resources_every_tick(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources.update(wood=200, ore=0, gold=50)
    b.resources.update(ore=200, wood=0, gold=50)
    a.capacity["ore"] = 0  # no ore of its own
    sim.diplomacy.set_intents(a.id, {b.id: trade("wood", 1.0, want="ore")})
    assert not sim.diplomacy.deals, "one-sided interest is not a deal"
    events_of(sim, 1)
    assert not sim.diplomacy.deals

    sim.diplomacy.set_intents(b.id, {a.id: trade("ore", 0.5, want="wood")})
    texts = events_of(sim, 1)
    deal = sim.diplomacy.deal_between(a.id, b.id)
    assert deal and deal.a_gives == ("wood", 1.0) and deal.b_gives == ("ore", 0.5)
    assert any("trades" in t for t in texts)
    assert a.resources["gold"] == b.resources["gold"] == 50 - rules.DEAL_FEE
    assert a.resources["ore"] == pytest.approx(0.5) and b.resources["wood"] == pytest.approx(1.0)
    assert a.imports["ore"] == 0.5 and a.exports["wood"] == 1.0

    events_of(sim, 20)
    assert a.resources["ore"] == pytest.approx(0.5 * 21)
    assert a.resources["wood"] == pytest.approx(200 - 21)


def test_deal_expires_after_its_duration(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources.update(wood=250, gold=15)
    b.resources.update(stone=250, wood=0, gold=15)
    a.resources["stone"] = 0
    sim.diplomacy.set_intents(a.id, {b.id: trade("wood", 1.0)})
    sim.diplomacy.set_intents(b.id, {a.id: trade("stone", 1.0)})
    texts = events_of(sim, rules.DEAL_DURATION + 2)
    assert sum("trades" in t for t in texts) == 1, "they cannot afford the fee a second time"
    assert any("expires" in t for t in texts)
    assert not sim.diplomacy.deals


def test_deal_is_cancelled_when_a_side_cannot_deliver(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources.update(wood=250, stone=0, gold=50)
    b.resources.update(stone=250, wood=0, gold=50)
    sim.diplomacy.set_intents(a.id, {b.id: trade("wood", 2.0)})
    sim.diplomacy.set_intents(b.id, {a.id: trade("stone", 2.0)})
    events_of(sim, 1)
    assert sim.diplomacy.deals
    sim.diplomacy.set_intents(a.id, {b.id: Intent()})  # so it is not simply reopened
    a.resources["wood"] = 0
    texts = events_of(sim, rules.DEAL_MISS_LIMIT + 1)
    assert any("cancelled" in t for t in texts)
    assert not sim.diplomacy.deals


def test_no_deal_for_a_resource_the_receiver_is_full_of(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources.update(wood=200, gold=50)
    b.resources.update(stone=200, wood=sim.modifiers[b.id].storage["wood"], gold=50)
    sim.diplomacy.set_intents(a.id, {b.id: trade("wood", 1.0)})
    sim.diplomacy.set_intents(b.id, {a.id: trade("stone", 1.0)})
    events_of(sim, 3)
    assert not sim.diplomacy.deals


# -- alliance ----------------------------------------------------------------

def test_alliance_needs_both_sides_and_lapses_when_one_walks_away(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources["gold"] = b.resources["gold"] = 100
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.ALLY)})
    events_of(sim, 2)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"

    sim.diplomacy.set_intents(b.id, {a.id: Intent(Stance.ALLY)})
    texts = events_of(sim, 1)
    assert sim.diplomacy.relation(a.id, b.id).status == "alliance"
    assert any("form an alliance" in t for t in texts)
    assert a.resources["gold"] == 100 - rules.ALLIANCE_COST
    assert sim.diplomacy.allies(a.id) == [b.id]

    sim.diplomacy.set_intents(b.id, {a.id: Intent(Stance.IGNORE)})
    events_of(sim, 1)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"


# -- war ---------------------------------------------------------------------

def test_war_needs_reach_and_gold(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources["gold"] = 100
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace", "too far apart to fight"
    assert a.march_target == b.id, "so the border is told to creep toward the target"

    make_neighbours(sim, a, b)
    a.resources["gold"] = 0
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace", "cannot afford to declare"

    a.resources["gold"] = 100
    texts = events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).status == "war"
    assert any("declares war" in t for t in texts)
    assert a.resources["gold"] == 100 - rules.WAR_COST
    assert a.soldier_target > 0.3 * a.population and b.military_need == 1.0


def test_stronger_attacker_takes_land_until_the_defender_surrenders(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.population, a.soldiers = 400, 140
    b.population, b.soldiers = 20, 0
    a.resources["gold"] = 100
    b.resources.update(wood=100, gold=40)
    farm_tiles = [t for t in sorted(b.territory) if t != b.capital.tile and BIOME_INFO[sim.world.biomes[t]].buildable]
    b.buildings += [Building("farm", t, 1.0, True) for t in farm_tiles]
    start_a, start_b = len(a.territory), len(b.territory)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})

    texts = []
    for _ in range(400):
        texts += events_of(sim, 1)
        a.soldiers = 140  # keep the army topped up; recruitment is the economy's job
        if any("surrenders" in t for t in texts):
            break
    assert any("surrenders" in t for t in texts)
    relation = sim.diplomacy.relation(a.id, b.id)
    assert relation.status == "peace" and relation.truce_until > sim.tick
    lost = start_b - len(b.territory)
    assert lost > 0 and len(a.territory) == start_a + lost
    assert b.capital.tile in b.territory, "the capital itself is never taken"
    assert all(sim.world.owner[t] == a.id for t in a.territory)
    assert all(sim.world.owner[t] == b.id for t in b.territory)
    assert all(sim.world.owner[bld.tile] == b.id for bld in b.buildings)
    assert all(sim.world.owner[bld.tile] == a.id for bld in a.buildings)
    captured = [t for t in farm_tiles if sim.world.owner[t] == a.id]
    assert captured, "some farmland was taken"
    assert sorted(bld.tile for bld in a.buildings if bld.type == "farm") == captured, "with the farms on it"
    assert len(b.buildings) == len(farm_tiles) - len(captured), "nothing was destroyed"
    assert b.resources["wood"] == pytest.approx(100 * (1 - rules.TRIBUTE))

    # The truce holds even though the winner is still hostile.
    events_of(sim, 20)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"


def test_weaker_attacker_gains_nothing_and_bleeds(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.population, a.soldiers = 100, 10
    b.population, b.soldiers = 300, 60
    a.resources["gold"] = 100
    size = len(b.territory)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    events_of(sim, 60)
    war = sim.diplomacy.relation(a.id, b.id).war
    assert war and war.tiles_taken[a.id] == 0 and len(b.territory) >= size
    assert war.casualties[a.id] > war.casualties[b.id] > 0


def test_war_ends_when_nobody_wants_it_any_more(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.resources["gold"] = 100
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.IGNORE)})
    events_of(sim, rules.MIN_WAR - 20)
    assert sim.diplomacy.relation(a.id, b.id).status == "war", "wars last at least a check-in"
    texts = events_of(sim, 30)
    assert any("make peace" in t for t in texts)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"


def test_attacking_an_ally_breaks_the_alliance_and_cancels_trade(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.resources.update(gold=200, wood=200, stone=0)
    b.resources.update(gold=200, stone=200, wood=0)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.ALLY, give="wood", give_rate=1.0)})
    sim.diplomacy.set_intents(b.id, {a.id: Intent(Stance.ALLY, give="stone", give_rate=1.0)})
    events_of(sim, 2)
    assert sim.diplomacy.relation(a.id, b.id).status == "alliance" and sim.diplomacy.deals

    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    texts = events_of(sim, 12)
    assert any("breaks its alliance" in t for t in texts)
    assert sim.diplomacy.relation(a.id, b.id).status == "war"
    assert not sim.diplomacy.deals


def test_buildings_on_a_tile_follow_the_tile_both_ways(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.resources["gold"] = 100
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    relation = sim.diplomacy.relation(a.id, b.id)
    assert relation.war

    far = [t for t in sorted(b.territory) if t not in set(sim.world.neighbors(b.capital.tile, diagonal=True))
           and t != b.capital.tile and BIOME_INFO[sim.world.biomes[t]].buildable]
    done, unfinished = far[0], far[1]
    # A building the captor has no tech for, and one still under construction.
    b.buildings += [Building("university", done, 1.0, True), Building("house", unfinished, 0.4, False)]
    assert "education" not in a.known_techs

    events: list = []
    for tile in (done, unfinished):
        sim.diplomacy._capture_tile(relation, a, b, tile, sim.tick, events)
    assert not b.buildings
    assert {(bld.type, bld.tile, bld.progress, bld.complete) for bld in a.buildings} == {
        ("university", done, 1.0, True), ("house", unfinished, 0.4, False)}
    assert sum("captures a" in e["text"] for e in events) == 2

    # The captor now runs them: it gets the output and pays the upkeep.
    a.resources["gold"] = 50
    sim.step()
    assert sim.modifiers[a.id].science >= 2.0 and sim.modifiers[b.id].science == 0
    assert a.upkeep["gold"] >= sim.building_defs["university"].upkeep["gold"]

    for tile in (done, unfinished):
        sim.diplomacy._capture_tile(relation, b, a, tile, sim.tick, events)
    assert not [bld for bld in a.buildings if bld.tile in (done, unfinished)]
    assert {bld.type for bld in b.buildings if bld.tile in (done, unfinished)} == {"university", "house"}
    assert all(sim.world.owner[bld.tile] == b.id for bld in b.buildings)
