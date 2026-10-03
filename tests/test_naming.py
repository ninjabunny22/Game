import json
import random

import pytest

from civsim.bridge import protocol
from civsim.config import SimConfig
from civsim.datafiles import load_json
from civsim.diplomacy import Intent, Stance
from civsim.diplomacy.naming import alliance_name, war_name
from civsim.simulation import Simulation


@pytest.fixture
def sim() -> Simulation:
    sim = Simulation(SimConfig(seed=3))
    for civ in sim.civs:
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


def touch(sim, a, b):
    world = sim.world
    edge = next(n for t in sorted(b.territory) for n in world.neighbors(t)
                if world.owner[n] < 0 and not world.is_open_water(n))
    world.claim(edge, a.id)
    a.territory.add(edge)


def test_war_names_come_from_the_land_being_fought_over(sim):
    attacker, defender = sim.civs[0], sim.civs[1]
    places = {r.name for r in sim.world.regions if r.owner == defender.id} | {
        r.capital_name for r in sim.world.regions if r.owner == defender.id}
    words = set(load_json("regions.json")["regions"]) | set(load_json("regions.json")["capitals"])
    seen = set()
    for i in range(60):
        name = war_name(sim.world, attacker, defender, random.Random(i), set())
        seen.add(name)
        assert name.startswith("The ") and "War" in name
        in_world = any(place in name for place in places)
        resource = any(word in name for word in ("Iron", "Gold", "Timber", "Quarry", "Water", "Harvest"))
        assert in_world or resource, name
        assert not any(w in name for w in words - places), "never a place that has nothing to do with it"
    assert len(seen) >= 3, "several styles, not one template"


def test_a_betrayal_is_remembered_as_one(sim):
    name = war_name(sim.world, sim.civs[0], sim.civs[1], random.Random(1), set(), betrayal=True)
    assert "Betrayal" in name


def test_alliance_names_come_from_the_members_own_lands(sim):
    a, b = sim.civs[0], sim.civs[1]
    places = {x for r in sim.world.regions if r.owner in (a.id, b.id) for x in (r.name, r.capital_name)}
    for i in range(40):
        name = alliance_name(sim.world, a, b, None, random.Random(i), set())
        assert any(kind in name for kind in ("Accord", "Pact", "Concord", "League"))
        assert any(place in name for place in places), name
    traded = {alliance_name(sim.world, a, b, "ore", random.Random(i), set()) for i in range(60)}
    assert "The Iron Compact" in traded, "what they trade can name it too"


def test_a_name_used_before_comes_back_numbered(sim):
    attacker, defender = sim.civs[0], sim.civs[1]
    taken: set[str] = set()
    first = war_name(sim.world, attacker, defender, random.Random(4), taken)
    second = war_name(sim.world, attacker, defender, random.Random(4), taken)
    third = war_name(sim.world, attacker, defender, random.Random(4), taken)
    assert second == first.replace("The ", "The Second ", 1)
    assert third == first.replace("The ", "The Third ", 1)
    assert len(taken) == 3


def test_wars_and_alliances_are_named_when_they_begin_and_allies_share_the_war(sim):
    attacker, victim, guardian, _ = sim.civs
    sim.diplomacy.set_intents(victim.id, {guardian.id: Intent(Stance.ALLY)})
    sim.diplomacy.set_intents(guardian.id, {victim.id: Intent(Stance.ALLY)})
    texts = update(sim)
    pact = sim.diplomacy.relation(victim.id, guardian.id)
    assert pact.alliance_name and any(pact.alliance_name in t for t in texts)

    touch(sim, attacker, victim)
    sim.diplomacy.set_intents(attacker.id, {victim.id: Intent(Stance.AGGRESSION, commitment=0.5)})
    texts = update(sim, 12)
    war = sim.diplomacy.relation(attacker.id, victim.id).war
    joined = sim.diplomacy.relation(attacker.id, guardian.id).war
    assert war.name and any(f"{war.name} begins" in t for t in texts)
    assert joined.name == war.name, "the ally fights in the same war, under the same name"
    assert any(f"joins {war.name}" in t for t in texts)

    data = json.loads(protocol.tick_message(sim, False, 2.0))["data"]
    by_pair = {(r["a"], r["b"]): r for r in data["relations"]}
    key = tuple(sorted((attacker.id, victim.id)))
    assert by_pair[key]["name"] == war.name and by_pair[key]["war"]["started"] == war.start
    assert by_pair[tuple(sorted((victim.id, guardian.id)))]["name"] == pact.alliance_name
    peaceful = next(r for r in data["relations"] if r["status"] == "peace")
    assert peaceful["name"] is None

    # When the alliance ends, so does its name.
    sim.diplomacy.set_intents(guardian.id, {victim.id: Intent(Stance.IGNORE)})
    update(sim, 2)
    assert pact.status == "peace" and pact.alliance_name == ""


def test_names_are_the_same_for_the_same_seed():
    def history(seed):
        from civsim.strategy import RuleBrain
        sim = Simulation(SimConfig(seed=seed))
        brain = RuleBrain()
        for _ in range(1500):
            sim.step_with(brain)
        return sorted(sim.diplomacy.names_used)

    assert history(11) == history(11)
    assert history(11), "something was named"
