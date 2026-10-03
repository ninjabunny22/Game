import pytest

from civsim.civ import Building
from civsim.map import BIOME_INFO
from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance
from civsim.diplomacy import rules
from civsim.simulation import Simulation


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:  # plenty of influence, so tests are about the rule in question
        civ.diplomacy_points = 300.0
    return sim


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


def make_neighbours(sim: Simulation, a, b) -> int:
    """Give `a` a strip of land right up against `b`'s territory. Returns that tile."""
    world = sim.world
    edge = next(n for t in sorted(b.territory) for n in world.neighbors(t)
                if world.owner[n] < 0 and not world.is_open_water(n))
    world.claim(edge, a.id)
    a.territory.add(edge)
    return edge


def set_soldiers(sim: Simulation, civ, soldiers: float) -> None:
    """Set a civ's head count and bring its armies into line with it."""
    civ.soldiers = soldiers
    civ.unpaid = civ.unsupplied = False
    sim.military._sync(civ)
    sim.military._organise(civ, sim.tick)


def field_army(civ, enemy):
    return next(a for a in civ.armies if a.role == "field" and a.target_civ == enemy.id)


# -- trade -------------------------------------------------------------------

def test_mutual_trade_opens_a_deal_that_moves_resources_every_tick(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources.update(wood=200, ore=0, gold=50)
    b.resources.update(ore=200, wood=0, gold=50)
    a.diplomacy_points = b.diplomacy_points = 50
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
    assert a.diplomacy_points == b.diplomacy_points == 50 + 2 * rules.DIPLOMACY_GAIN - rules.DEAL_FEE
    assert a.resources["gold"] == b.resources["gold"] == 50, "diplomacy is paid in influence, not gold"
    assert a.resources["ore"] == pytest.approx(0.5) and b.resources["wood"] == pytest.approx(1.0)
    assert a.imports["ore"] == 0.5 and a.exports["wood"] == 1.0

    events_of(sim, 20)
    assert a.resources["ore"] == pytest.approx(0.5 * 21)
    assert a.resources["wood"] == pytest.approx(200 - 21)


def test_deal_expires_after_its_duration(sim):
    a, b = sim.civs[0], sim.civs[1]
    a.resources.update(wood=250, gold=15)
    b.resources.update(stone=250, wood=0, gold=15)
    a.diplomacy_points = b.diplomacy_points = rules.DEAL_FEE
    a.resources["stone"] = 0
    sim.diplomacy.set_intents(a.id, {b.id: trade("wood", 1.0)})
    sim.diplomacy.set_intents(b.id, {a.id: trade("stone", 1.0)})
    texts = []
    for _ in range(rules.DEAL_DURATION + 2):
        texts += events_of(sim, 1)
        a.diplomacy_points = 0  # spent: nothing left for a second deal
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
    a.diplomacy_points = b.diplomacy_points = 100
    gold = a.resources["gold"]
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.ALLY)})
    events_of(sim, 2)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"

    sim.diplomacy.set_intents(b.id, {a.id: Intent(Stance.ALLY)})
    texts = events_of(sim, 1)
    assert sim.diplomacy.relation(a.id, b.id).status == "alliance"
    assert any("form an alliance" in t for t in texts)
    assert a.diplomacy_points == 100 + 3 * rules.DIPLOMACY_GAIN - rules.ALLIANCE_COST
    assert a.resources["gold"] == gold
    assert sim.diplomacy.allies(a.id) == [b.id]

    sim.diplomacy.set_intents(b.id, {a.id: Intent(Stance.IGNORE)})
    events_of(sim, 1)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace"


# -- war ---------------------------------------------------------------------

def test_war_needs_reach_and_diplomacy_points(sim):
    a, b = sim.civs[0], sim.civs[1]
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace", "too far apart to fight"
    assert a.march_target == b.id, "so the border is told to creep toward the target"

    make_neighbours(sim, a, b)
    a.diplomacy_points = 0
    a.resources["gold"] = 250  # gold does not buy a war
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).status == "peace", "not enough influence to declare"

    a.diplomacy_points = rules.WAR_COST
    texts = events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).status == "war"
    assert any("declares war" in t for t in texts)
    assert a.diplomacy_points < 20, "the declaration used it up"
    assert a.resources["gold"] == 250
    assert a.soldier_target > 0.3 * a.population and b.military_need == 1.0


def test_stronger_attacker_marches_in_and_takes_a_region_by_its_capital(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.population, a.soldiers = 400, 140
    b.population, b.soldiers = 20, 0
    held = [r for r in sim.world.regions if r.owner == b.id]
    start_a, start_b = len(a.territory), len(b.territory)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})

    texts = []
    for _ in range(1500):
        texts += events_of(sim, 1)
        a.soldiers = 140  # keep the army topped up; recruitment is the economy's job
        a.unpaid = a.unsupplied = False
        if any("falls with it" in t for t in texts):
            break
    fallen = [r for r in held if r.owner == a.id]
    assert fallen, "the army reached a capital and the region fell with it"
    region = fallen[0]
    assert all(sim.world.owner[t] == a.id for t in region.tiles), "every tile of the region changed hands"
    assert region.capital in {s.tile for s in a.settlements}
    assert region.capital not in {s.tile for s in b.settlements}
    assert len(a.territory) + len(b.territory) == start_a + start_b, "nothing vanished"
    assert all(sim.world.owner[t] == a.id for t in a.territory)
    assert all(sim.world.owner[t] == b.id for t in b.territory)


def test_capturing_a_capital_flips_the_region_with_its_buildings(sim):
    a, b = sim.civs[0], sim.civs[1]
    second = next(r for r in sim.world.regions if r.owner == b.id and r.capital != b.capital.tile)
    tiles = [t for t in second.tiles if t != second.capital and BIOME_INFO[sim.world.biomes[t]].buildable][:5]
    b.buildings += [Building("farm", t, 1.0, True) for t in tiles]
    home_tiles = len([r for r in sim.world.regions if r.owner == b.id and r is not second][0].tiles)

    events: list = []
    sim.diplomacy.capture_region(a, second, sim.tick, events)
    assert second.owner == a.id
    assert all(sim.world.owner[t] == a.id for t in second.tiles)
    assert sorted(bld.tile for bld in a.buildings if bld.type == "farm") == sorted(tiles), "buildings come with it"
    assert not [bld for bld in b.buildings if bld.tile in tiles]
    assert len(b.territory) == home_tiles, "the loser keeps its other region"
    assert [s.tile for s in b.settlements] == [b.capital.tile] and b.alive
    assert any("falls with it" in e["text"] for e in events)
    assert not any("tribute" in e["text"] for e in events), "only losing your own capital costs tribute"


def test_losing_the_main_capital_means_tribute_and_a_new_capital(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, b.id).war
    home = next(r for r in sim.world.regions if r.capital == b.capital.tile)
    other = next(r for r in sim.world.regions if r.owner == b.id and r is not home)
    b.resources.update(wood=200, stone=100)
    a.resources.update(wood=0, stone=0)

    events: list = []
    sim.diplomacy.capture_region(a, home, sim.tick, events)
    assert b.alive and b.capital.tile == other.capital, "the court moves to the capital it still holds"
    assert b.resources["wood"] == pytest.approx(100) and a.resources["wood"] == pytest.approx(100)
    relation = sim.diplomacy.relation(a.id, b.id)
    assert relation.status == "peace" and relation.truce_until >= sim.tick + rules.SURRENDER_TRUCE
    assert any("moves its court" in e["text"] for e in events)


def test_a_civ_with_no_capital_left_is_destroyed(sim):
    a, b, c = sim.civs[0], sim.civs[1], sim.civs[2]
    extra = next(n for t in sorted(b.territory) for n in sim.world.neighbors(t)
                 if sim.world.owner[n] < 0 and n not in sim.world.capital_tiles)
    sim.world.claim(extra, b.id)  # land outside its two regions
    b.territory.add(extra)
    b.resources["wood"] = 80
    wood = a.resources["wood"]
    villagers = len(a.villagers) + len(b.villagers)
    sim.diplomacy.set_intents(c.id, {b.id: Intent(Stance.TRADE, give="wood", give_rate=1.0)})
    for region in [r for r in sim.world.regions if r.owner == b.id]:
        sim.diplomacy.capture_region(a, region, sim.tick, [])

    assert not b.alive and not b.settlements and not b.territory
    assert sim.world.owner[extra] == a.id, "what was left of it goes to the conqueror"
    assert len(a.villagers) == villagers and not b.villagers, "its villagers are taken in, not lost"
    assert a.resources["wood"] > wood
    assert b.id not in sim.diplomacy.others(a.id)
    assert all(sim.diplomacy.relation(b.id, o.id).status == "peace" for o in sim.civs if o is not b)

    # The world goes on without it.
    for _ in range(60):
        sim.step()
    assert not b.alive and not b.armies


def test_weaker_attacker_gains_nothing_and_bleeds(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    edge = make_neighbours(sim, a, b)
    a.population, a.soldiers = 100, 10
    b.population, b.soldiers = 300, 60
    a.resources["gold"] = 100
    size = len(b.territory)
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=1.0)})
    events_of(sim, 12)
    war = sim.diplomacy.relation(a.id, b.id).war
    assert war
    army = field_army(a, b)
    army.tile, army.path = edge, []  # the attacker's army arrives at the border
    texts = events_of(sim, 60)
    assert war.tiles_taken[a.id] == 0 and len(b.territory) >= size
    assert war.casualties[a.id] > war.casualties[b.id] > 0, "the defender's army came out to meet it"
    assert any("routs" in t for t in texts)
    assert field_army(a, b).state in ("retreating", "idle"), "the beaten army falls back"


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


# -- allies sharing the spoils ------------------------------------------------

def joint_war(sim, strengths: dict[int, float]):
    """Civs 0 and 2 allied, both at war with civ 1, with the given army sizes."""
    a, enemy, ally = sim.civs[0], sim.civs[1], sim.civs[2]
    for civ in (a, ally):
        make_neighbours(sim, civ, enemy)
        civ.resources["gold"] = 300
    sim.diplomacy.set_intents(a.id, {ally.id: Intent(Stance.ALLY), enemy.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    sim.diplomacy.set_intents(ally.id, {a.id: Intent(Stance.ALLY), enemy.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, ally.id).status == "alliance"
    assert sim.diplomacy.relation(a.id, enemy.id).war and sim.diplomacy.relation(ally.id, enemy.id).war
    for civ_id, soldiers in strengths.items():
        sim.civs[civ_id].population = 500
        set_soldiers(sim, sim.civs[civ_id], soldiers)
    return a, enemy, ally


@pytest.mark.parametrize("mine, theirs, expected", [
    (70, 30, 0.70),   # clear gap: proportional
    (30, 70, 0.30),
    (52, 48, 0.50),   # close: treated as even
    (55, 45, 0.50),   # edge of the band
    (56, 44, 0.56),   # just outside it
    (0, 0, 0.50),     # nobody under arms
])
def test_spoils_are_split_by_current_strength_with_an_even_band(sim, mine, theirs, expected):
    a, enemy, ally = joint_war(sim, {0: mine, 2: theirs})
    shares = sim.diplomacy.spoils_shares(a, enemy)
    assert shares[a.id] == pytest.approx(expected)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert sim.diplomacy.spoils_shares(ally, enemy)[ally.id] == pytest.approx(1 - expected), "same split whoever captures"


def test_a_capture_is_only_joint_with_allies_fighting_the_same_enemy(sim):
    a, enemy, bystander = sim.civs[0], sim.civs[1], sim.civs[2]
    make_neighbours(sim, a, enemy)
    for civ in (a, bystander):
        civ.resources["gold"] = 300
    sim.diplomacy.set_intents(a.id, {bystander.id: Intent(Stance.ALLY), enemy.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    sim.diplomacy.set_intents(bystander.id, {a.id: Intent(Stance.ALLY)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(a.id, bystander.id).status == "alliance"
    assert sim.diplomacy.relation(bystander.id, enemy.id).status == "peace"
    set_soldiers(sim, bystander, 400)
    assert sim.diplomacy.spoils_shares(a, enemy) == {a.id: 1.0}, "an ally who is not in the war gets nothing"


def test_captured_stores_are_shared_but_the_building_goes_to_the_captor(sim):
    a, enemy, ally = joint_war(sim, {0: 30, 2: 90})
    relation = sim.diplomacy.relation(a.id, enemy.id)
    tile = next(t for t in sorted(enemy.territory) if t != enemy.capital.tile
                and t not in set(sim.world.neighbors(enemy.capital.tile, diagonal=True))
                and BIOME_INFO[sim.world.biomes[t]].buildable)
    enemy.buildings.append(Building("granary", tile, 1.0, True))
    enemy.resources["food"] = 250
    sim.modifiers[enemy.id].storage["food"] = 600.0  # so this granary (300) holds half the stock
    a.resources["food"] = ally.resources["food"] = 0
    held = 250 * 300 / 600

    events: list = []
    sim.diplomacy._capture_tile(relation, a, enemy, tile, sim.tick, events)
    assert [b.type for b in a.buildings if b.tile == tile] == ["granary"], "the weaker ally took it, so it owns it"
    assert not [b for b in ally.buildings if b.tile == tile] and tile in a.territory
    assert a.resources["food"] == pytest.approx(0.25 * held)
    assert ally.resources["food"] == pytest.approx(0.75 * held), "the stronger ally gets the larger share"
    assert enemy.resources["food"] == pytest.approx(250 - held)
    assert "shared by strength" in events[0]["text"]

    # Power shifts; the next capture uses the new balance.
    set_soldiers(sim, a, 90)
    set_soldiers(sim, ally, 30)
    assert sim.diplomacy.spoils_shares(a, enemy)[a.id] == pytest.approx(0.75)


def test_tribute_for_a_fallen_capital_is_shared_the_same_way(sim):
    a, enemy, ally = joint_war(sim, {0: 80, 2: 20})
    for civ in (a, ally):
        for res in civ.resources:
            civ.resources[res] = 0
    enemy.resources.update(wood=200, stone=100)
    home = next(r for r in sim.world.regions if r.capital == enemy.capital.tile)
    sim.diplomacy.capture_region(a, home, sim.tick, [])
    assert a.resources["wood"] == pytest.approx(0.8 * 100) and ally.resources["wood"] == pytest.approx(0.2 * 100)
    assert a.resources["stone"] == pytest.approx(0.8 * 50) and ally.resources["stone"] == pytest.approx(0.2 * 50)
    assert enemy.resources["wood"] == pytest.approx(100)


def test_a_lone_captor_still_keeps_everything(sim):
    a, b = sim.civs[0], sim.civs[1]
    make_neighbours(sim, a, b)
    a.resources["gold"] = 100
    sim.diplomacy.set_intents(a.id, {b.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    assert sim.diplomacy.spoils_shares(a, b) == {a.id: 1.0}


# -- alliances as defensive pacts --------------------------------------------

def ally_up(sim, x, y):
    for civ in (x, y):
        civ.resources["gold"] = max(civ.resources["gold"], 300)
    sim.diplomacy.set_intents(x.id, {y.id: Intent(Stance.ALLY)})
    sim.diplomacy.set_intents(y.id, {x.id: Intent(Stance.ALLY)})
    events_of(sim, 1)
    assert sim.diplomacy.relation(x.id, y.id).status == "alliance"


def test_an_attacked_civs_ally_is_drawn_into_the_war(sim):
    attacker, victim, guardian, bystander = sim.civs
    ally_up(sim, victim, guardian)
    make_neighbours(sim, attacker, victim)
    attacker.resources["gold"] = 100
    influence = guardian.diplomacy_points
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    texts = events_of(sim, 12)

    assert sim.diplomacy.relation(attacker.id, victim.id).status == "war"
    relation = sim.diplomacy.relation(attacker.id, guardian.id)
    assert relation.status == "war", "the ally has no say in a defensive war"
    assert (relation.war.declarer, relation.war.guardian, relation.war.defending) == (attacker.id, guardian.id, victim.id)
    assert any("in defence of its ally" in t for t in texts)
    assert guardian.diplomacy_points >= influence - 1, "joining a defensive war costs nothing"
    assert sim.diplomacy.relation(attacker.id, bystander.id).status == "peace"
    assert guardian.id in sim.diplomacy.spoils_shares(victim, attacker), "and it shares in what the defence wins"

    # It lasts past the usual minimum even though the guardian was never hostile itself...
    events_of(sim, rules.MIN_WAR + 20)
    assert sim.diplomacy.relation(attacker.id, guardian.id).status == "war"

    # ...and ends when the war it was called into ends.
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.IGNORE)})
    texts = events_of(sim, 3)
    assert sim.diplomacy.relation(attacker.id, victim.id).status == "peace"
    assert sim.diplomacy.relation(attacker.id, guardian.id).status == "peace"
    assert any("stands down" in t for t in texts)


def test_an_aggressors_ally_is_free_to_stay_out_or_join(sim):
    attacker, victim, partner, _ = sim.civs
    ally_up(sim, attacker, partner)
    make_neighbours(sim, attacker, victim)
    make_neighbours(sim, partner, victim)
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5),
                                            partner.id: Intent(Stance.ALLY)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(attacker.id, victim.id).status == "war"
    assert sim.diplomacy.relation(partner.id, victim.id).status == "peace", "no duty to join a war your ally started"
    assert sim.diplomacy.spoils_shares(attacker, victim) == {attacker.id: 1.0}, "and no share for staying out"

    sim.diplomacy.set_intents(partner.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5),
                                           attacker.id: Intent(Stance.ALLY)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(partner.id, victim.id).status == "war", "it may opt in"
    assert set(sim.diplomacy.spoils_shares(attacker, victim)) == {attacker.id, partner.id}


def test_leaving_the_alliance_ends_the_obligation(sim):
    attacker, victim, guardian, _ = sim.civs
    ally_up(sim, victim, guardian)
    make_neighbours(sim, attacker, victim)
    attacker.resources["gold"] = 100
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(attacker.id, guardian.id).status == "war"

    sim.diplomacy.set_intents(guardian.id, {victim.id: Intent(Stance.IGNORE)})
    events_of(sim, 3)
    assert sim.diplomacy.relation(victim.id, guardian.id).status == "peace"
    assert sim.diplomacy.relation(attacker.id, guardian.id).status == "peace"
    assert sim.diplomacy.relation(attacker.id, victim.id).status == "war", "the original war goes on"


def test_a_civ_allied_to_both_sides_stays_out(sim):
    attacker, victim, friend, _ = sim.civs
    ally_up(sim, victim, friend)
    ally_up(sim, attacker, friend)
    make_neighbours(sim, attacker, victim)
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5),
                                            friend.id: Intent(Stance.ALLY)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(attacker.id, victim.id).status == "war"
    assert sim.diplomacy.relation(attacker.id, friend.id).status == "alliance"
    assert sim.diplomacy.relation(victim.id, friend.id).status == "alliance"


def test_allying_with_a_civ_under_attack_means_joining_its_defence(sim):
    attacker, victim, newcomer, _ = sim.civs
    make_neighbours(sim, attacker, victim)
    attacker.resources["gold"] = 100
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    events_of(sim, 12)
    assert sim.diplomacy.relation(attacker.id, newcomer.id).status == "peace"

    ally_up(sim, victim, newcomer)
    assert sim.diplomacy.relation(attacker.id, newcomer.id).status == "war"

    # Allying with the aggressor carries no such duty.
    other = sim.civs[3]
    ally_up(sim, attacker, other)
    assert sim.diplomacy.relation(victim.id, other.id).status == "peace"


# -- diplomacy points ----------------------------------------------------------

def test_every_civ_earns_diplomacy_points_automatically_up_to_a_cap():
    sim = Simulation(SimConfig(seed=3))
    assert all(civ.diplomacy_points == rules.DIPLOMACY_START for civ in sim.civs)
    for _ in range(40):
        sim.step()
    assert all(civ.diplomacy_points == rules.DIPLOMACY_START + 40 * rules.DIPLOMACY_GAIN for civ in sim.civs)
    for _ in range(400):
        sim.step()
    assert all(civ.diplomacy_points == rules.DIPLOMACY_CAP for civ in sim.civs)
    assert rules.WAR_COST == 100 and rules.WAR_COST > rules.ALLIANCE_COST > rules.DEAL_FEE
    assert "diplomacy_points" not in sim.civs[0].resources, "not a tradeable resource"
