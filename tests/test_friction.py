"""More war: neighbours rub, the big lean on the small, peace wears thin, and an alliance
lasts only while both sides still choose it."""

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Intent, Stance, rules
from civsim.simulation import Simulation
from civsim.strategy import CHECKIN_INTERVAL

from test_utility_brain import context, decide  # noqa: F401


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def neighbours(sim):
    """Two civs that share a border, and one that touches neither if there is one."""
    d = sim.diplomacy
    pairs = [(a, b) for a in sim.civs for b in sim.civs if a.id < b.id]
    touching = [(a, b) for a, b in pairs if d.shared_border(a, b)]
    apart = [(a, b) for a, b in pairs if not d.shared_border(a, b)]
    return touching, apart


def test_civs_think_every_ten_days():
    assert CHECKIN_INTERVAL == 10


def test_neighbours_at_peace_come_to_resent_each_other_and_distant_civs_do_not(sim, monkeypatch):
    monkeypatch.setattr(rules, "RIVALRY", 0.0)  # the border alone
    d = sim.diplomacy
    world = sim.world
    a, b = sim.civs[0], sim.civs[1]
    # Give the two a long border by handing `a` a strip of `b`'s edge.
    edge = [t for t in sorted(b.territory) if any(world.owner[n] not in (b.id,) for n in world.neighbors(t))
            and t not in world.capital_tiles][:30]
    for tile in edge:
        b.territory.discard(tile)
        a.territory.add(tile)
        world.owner[tile] = a.id
    assert d.shared_border(a, b) > 0 and d.shared_border(a, b) == d.shared_border(b, a)
    touching, apart = neighbours(sim)
    for pair in d.standing:
        d.standing[pair] = 0.0
    d._friction()
    assert d.standing[(a.id, b.id)] < 0 and d.standing[(b.id, a.id)] < 0
    assert d.standing[(a.id, b.id)] >= -rules.BORDER_FRICTION
    for x, y in apart:
        assert d.standing[(x.id, y.id)] == 0.0
    # Allies do not rub.
    d.relation(a.id, b.id).status = "alliance"
    before = d.standing[(a.id, b.id)]
    d._friction()
    assert d.standing[(a.id, b.id)] == before


def test_two_civs_after_the_same_native_land_fall_out_over_it(sim, monkeypatch):
    monkeypatch.setattr(rules, "RIVALRY", 0.0)
    d, world = sim.diplomacy, sim.world
    a, b = sim.civs[0], sim.civs[1]
    region = next(r for r in world.regions if r.neutral)
    land = [t for t in region.tiles if t != region.capital]
    half = len(land) // 2
    for civ, tiles in ((a, land[:half]), (b, land[half:])):
        for tile in tiles:
            world.owner[tile] = civ.id
            civ.territory.add(tile)
    for pair in d.standing:
        d.standing[pair] = 0.0
    d._friction()
    assert d.standing[(a.id, b.id)] <= -rules.RIVAL_FRICTION
    # ... and whoever takes it is not forgiven by the other.
    before = d.standing[(b.id, a.id)]
    d.capture_region(a, region, 100, [])
    assert d.standing[(b.id, a.id)] == pytest.approx(before - rules.BEATEN_TO_IT)


def test_an_alliance_lapses_once_either_side_stops_choosing_it(sim):
    d = sim.diplomacy
    a, b = sim.civs[0], sim.civs[1]
    relation = d.relation(a.id, b.id)
    relation.status = "alliance"
    d.intents[(a.id, b.id)] = Intent(stance=Stance.ALLY)
    d.intents[(b.id, a.id)] = Intent(stance=Stance.ALLY)
    d._resolve_pair(a.id, b.id, 10, [])
    assert relation.status == "alliance"
    d.intents[(b.id, a.id)] = Intent(stance=Stance.TRADE)  # still friendly, but no longer an ally
    events = []
    d._resolve_pair(a.id, b.id, 11, events)
    assert relation.status == "peace" and any("lapses" in e["text"] for e in events)


def test_truces_are_short():
    assert rules.TRUCE == 50 and rules.SURRENDER_TRUCE == 150


# -- the strategist ----------------------------------------------------------

def test_a_much_bigger_civ_attacks_a_small_neighbour_whatever_its_temper(context):  # noqa: F811
    small = context["neighbors"][0]
    you = context["you"]
    you["weights"]["military"] = 0.8  # no warmonger
    small.update(army_vs_yours="weaker", standing=1.5)  # and an old friend
    assert decide(context)[small["name"]]["stance"] != "aggression"
    small.update(population=you["population"] // 3, territory=you["territory"] // 3)
    assert decide(context)[small["name"]]["stance"] == "aggression"


def test_a_long_peace_ends_in_war_even_between_equals_the_warlike_first(context):  # noqa: F811
    you = context["you"]
    assert all(e["stance"] != "aggression" for e in decide(context).values())

    def first_war(military: float) -> int:
        you["weights"]["military"] = military
        for days in range(0, 3000, 50):
            you["peace_ticks"] = days
            if any(e["stance"] == "aggression" for e in decide(context).values()):
                return days
        return 10**9

    warlike, peaceable = first_war(1.4), first_war(0.7)
    assert 250 <= warlike <= 700 and warlike < peaceable <= 1200


def test_an_alliance_with_nothing_to_guard_against_wears_out(context):  # noqa: F811
    friend = context["neighbors"][0]
    power = context["you"]["military_power"]
    context["you"]["weights"]["military"] = 1.0
    friend.update(relation="alliance", intel={"military_power": power}, their_stance_toward_you="ally",
                  alliance_ticks=0)
    assert decide(context)[friend["name"]]["stance"] == "ally"
    friend["alliance_ticks"] = 2000
    assert decide(context)[friend["name"]]["stance"] != "ally"
    friend["at_war_with"] = ["Someone"]
    enemy = context["neighbors"][1]
    enemy.update(relation="war", war_ticks=20, name="Someone")
    assert decide(context)[friend["name"]]["stance"] == "ally", "but not while they share an enemy"


# -- the two at the top ------------------------------------------------------

def test_the_two_strongest_resent_each_other_and_it_follows_who_they_are(sim):
    d = sim.diplomacy
    a, b, c = sim.civs[0], sim.civs[1], sim.civs[2]
    a.population, b.population = 900, 700
    assert d.rivals() == (a.id, b.id)
    d.relation(a.id, b.id).status = "alliance"  # allies or not
    for pair in d.standing:
        d.standing[pair] = 0.0
    d._friction()
    assert d.standing[(a.id, b.id)] == pytest.approx(-rules.RIVALRY) == d.standing[(b.id, a.id)]
    assert d.standing[(a.id, c.id)] > -rules.RIVALRY and d.standing[(c.id, b.id)] > -rules.RIVALRY
    # The strongest falls behind: now the other two are the rivals.
    a.population, c.population = 20, 800
    assert d.rivals() == (c.id, b.id)
    before = d.standing[(b.id, c.id)], d.standing[(b.id, a.id)]
    d._friction()
    assert d.standing[(b.id, c.id)] <= before[0] - rules.RIVALRY
    assert d.standing[(b.id, a.id)] > before[1] - rules.RIVALRY, "the old grudge is no longer fed"
    from civsim.strategy import stance_context
    seen = {n["id"]: n["rival"] for n in stance_context(sim, b)["neighbors"]}
    assert seen[c.id] is True and seen[a.id] is False


def test_rivals_fight_sooner_ally_less_and_stab_each_other_in_the_back(context):  # noqa: F811
    other = context["neighbors"][0]
    you = context["you"]
    you["weights"]["military"] = 1.0
    other["army_vs_yours"] = "weaker"
    plain = decide(context)[other["name"]]["stance"]
    other["rival"] = True
    assert plain != "aggression" and decide(context)[other["name"]]["stance"] == "aggression"

    # Allied, the stronger of the two turns on the other once it is clearly ahead ...
    power = you["military_power"]
    other.update(relation="alliance", intel={"military_power": round(power / 1.5)}, their_stance_toward_you="ally",
                 alliance_ticks=100, rival=False, army_vs_yours="comparable")
    assert decide(context)[other["name"]]["stance"] == "ally"
    other["rival"] = True
    assert decide(context)[other["name"]]["stance"] == "aggression"
    # ... and even short of that the alliance does not hold.
    other["intel"] = {"military_power": power}
    assert decide(context)[other["name"]]["stance"] != "ally"
