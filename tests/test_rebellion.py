"""Rebellions and the rest of the royal drama: a rebel civ appears whole and at war, a plotter
with no castle is executed, regencies begin and end, regents may usurp, a spent line is
claimed through marriage, traits change play, princes cost more to ransom."""

import json

import pytest

from civsim.bridge.protocol import tick_message
from civsim.civ import family
from civsim.civ.family import YEAR, Families
from civsim.config import game_config
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain

from test_family import _civs, _Diplomacy


def _realm_of_three(seed=3):
    """A game some days in (armies raised), whose civ 0 holds a third region, so a rebel has a
    castle to seize."""
    sim = Simulation(game_config("medium", 4, seed))
    brain = RuleBrain()
    for _ in range(200):
        sim.step_with(brain)
    king = sim.civs[0]
    region = next(r for r in sim.world.regions if r.owner is None)
    sim.diplomacy.capture_region(king, region, 0, [])
    return sim, king


def _prince(sim, civ):
    house = sim.families.house_of(civ.id)
    heir = sim.families.heir(house)
    return next(p for p in sim.families.line(house) if p is not heir and p.age(0) >= family.ADULT), house


def test_a_rebel_civ_appears_whole_and_at_war():
    sim, king = _realm_of_three()
    prince, house = _prince(sim, king)
    count, soldiers = len(sim.civs), king.soldiers
    regions_before = len(king.settlements)
    events = []
    sim.families._rebel(prince, house, king, 5, events, "caught in the act")
    assert len(sim.civs) == count + 1
    rebel = sim.civs[-1]
    assert rebel.id == count and rebel.alive and len(rebel.settlements) == 1
    assert len(king.settlements) == regions_before - 1
    region = sim.world.regions[sim.world.region_of[rebel.capital.tile]]
    assert region.owner == rebel.id and region.id in king.lost_regions
    assert all(sim.world.owner[t] == rebel.id for t in region.tiles if t in rebel.territory)
    assert sim.diplomacy.relation(rebel.id, king.id).status == "war"
    assert sim.families.ruler(rebel.id) is prince and prince.house != house.key
    assert rebel.soldiers > 0 and king.soldiers < soldiers
    for civ in (king, rebel):
        assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers, abs=1e-3 + 0.02 * civ.soldiers)
    kinds = [e.get("family", {}).get("type") for e in events]
    assert "rebellion" in kinds and any("declares war" in e["text"] for e in events)
    sent = json.loads(tick_message(sim, False, 1.0))["data"]
    assert any(c["id"] == rebel.id for c in sent["roster"])
    brain = RuleBrain()
    for _ in range(60):  # the world goes on with one more civ in it
        sim.step_with(brain)
    for civ in sim.civs:
        assert sum(a.size for a in civ.armies) == pytest.approx(civ.soldiers, abs=1e-3 + 0.02 * civ.soldiers)


def test_a_plotter_with_no_castle_is_executed():
    sim = Simulation(game_config("medium", 4, 3))
    king = sim.civs[0]
    king.settlements = king.settlements[:1]  # nowhere to flee
    prince, house = _prince(sim, king)
    events = []
    sim.families._rebel(prince, house, king, 5, events, "caught")
    assert not prince.alive and prince.cause == "executed for treason"
    assert len(sim.civs) == 4
    assert events[-1]["family"]["type"] == "execution"


def test_only_the_ambitious_plot_and_not_too_soon():
    families = Families(_civs(1), seed=1, diplomacy=_Diplomacy())
    house = families.house_of(0)
    families.civs[0].settlements = [object()] * 3
    prince = next(p for p in families.line(house) if families.heir(house) is not p and p.age(0) >= 18)
    prince.ambition = 0.9
    assert not families._may_plot(prince, house, families.civs[0], family.PLOT_FROM - 1)
    assert families._may_plot(prince, house, families.civs[0], family.PLOT_FROM)
    prince.ambition = 0.1
    assert not families._may_plot(prince, house, families.civs[0], family.PLOT_FROM)


def test_a_child_on_the_throne_rules_through_a_regent_until_sixteen():
    families = Families(_civs(1), seed=2, diplomacy=_Diplomacy())
    house = families.house_of(0)
    ruler = families.ruler(0)
    child = families._add(house, "Tam", "m", 0)
    child.parents = [ruler.id] + ([ruler.spouse] if ruler.spouse else [])
    for person in families.line(house):
        if person is not child:
            person.deposed = True  # only the child is left in the line
    families.die(ruler, 5 * family.CHILD_YEAR, [], "a stroke")  # the child is 5
    assert house.ruler == child.id and house.regent is not None
    families._regency(house, families.civs[0], 16 * family.CHILD_YEAR, events := [])
    assert house.regent is None and events and events[-1]["family"]["type"] == "regency"


def test_an_ambitious_regent_may_take_the_crown():
    families = Families(_civs(1), seed=3, diplomacy=_Diplomacy())
    house = families.house_of(0)
    child = families._add(house, "Tam", "m", 0)
    regent = families.ruler(0)
    house.ruler, house.regent = child.id, regent.id
    events = []
    families._usurp(regent, house, families.civs[0], 100, events)
    assert house.ruler == regent.id and regent.usurper
    assert child.deposed or not child.alive
    assert events[-1]["family"]["type"] == "usurpation"


def test_a_spent_line_is_claimed_by_blood_married_abroad():
    families = Families(_civs(2), seed=4, diplomacy=_Diplomacy())
    a, b = families.house_of(0), families.house_of(1)
    daughter = families._add(b, "Anwen", "f", family.born_aged(25))
    daughter.born = a.name  # born to house a, married into house b
    for member in a.members:
        if families.people[member].id != a.ruler:
            families.people[member].alive = False
    events = []
    families.die(families.people[a.ruler], 50, events, "old age")
    assert families.claim(1, 0, 60) == f"{families.title(daughter)} Anwen"
    assert any(e["family"]["type"] == "claim" for e in events)
    assert families.claim(1, 0, 60 + family.CLAIM_DAYS + 1) is None


def test_traits_change_play():
    families = Families(_civs(1), seed=5)
    ruler = families.ruler(0)
    ruler.traits = ["learned"]
    mods = type("Mods", (), {"science_mult": 0.0})()
    families.apply_modifiers(families.civs[0], mods)
    assert mods.science_mult == family.LEARNED
    sickly = [p for p in families.people.values() if "sickly" in p.traits]
    assert all(p.health >= 0.7 * family.SICKLY - 1e-9 for p in sickly)


def _rebellion_with_a_patron(betray: bool):
    sim, king = _realm_of_three()
    patron = sim.civs[1]
    sim.diplomacy.standing[(patron.id, king.id)] = -2.0  # it hates the king
    sim.families.rng.random = (lambda: 0.0) if betray else (lambda: 0.99)  # it means to betray, or not
    prince, house = _prince(sim, king)
    events = []
    sim.families._rebel(prince, house, king, 5, events, "caught")
    return sim, king, patron, sim.civs[-1], prince, events


def test_a_patron_takes_up_the_rebels_cause_and_one_that_keeps_its_word_is_sworn():
    sim, king, patron, rebel, prince, events = _rebellion_with_a_patron(betray=False)
    assert sim.diplomacy.relation(patron.id, rebel.id).status == "alliance"
    assert sim.diplomacy.relation(patron.id, king.id).status == "war"
    assert frozenset((patron.id, rebel.id)) in sim.families.bonds
    assert any(e.get("family", {}).get("type") == "pledge" for e in events)
    from civsim.strategy import stance_context
    assert next(n for n in stance_context(sim, patron)["neighbors"] if n["id"] == rebel.id)["sworn"]


def test_a_patron_that_betrays_falls_on_the_rebel_and_ransoms_him_to_his_father():
    sim, king, patron, rebel, prince, events = _rebellion_with_a_patron(betray=True)
    day = sim.families.betrayals[(patron.id, rebel.id)]
    sim.families._betrayals(day, events := [])
    assert sim.diplomacy.relation(patron.id, rebel.id).status == "war"
    assert any(e.get("family", {}).get("type") == "betrayal" for e in events)
    region = sim.world.regions[sim.world.region_of[rebel.capital.tile]]
    sim.diplomacy.capture_region(patron, region, day + 5, events := [])
    assert not rebel.alive and prince.alive and prince.captive_of == patron.id
    king.resources["gold"] = 1000
    gold = patron.resources["gold"]
    sim.families._ransoms(day + 30, events := [])
    assert prince.captive_of is None and prince.deposed and prince.house == sim.families.house_of(king.id).key
    assert patron.resources["gold"] == gold + family.ROYAL_RANSOM
    assert events[-1]["family"]["type"] == "ransom"


def test_a_rebel_taken_by_his_own_father_is_put_aside():
    sim, king = _realm_of_three()
    prince, house = _prince(sim, king)
    sim.families._rebel(prince, house, king, 5, [], "caught")
    rebel = sim.civs[-1]
    region = sim.world.regions[sim.world.region_of[rebel.capital.tile]]
    sim.diplomacy.capture_region(king, region, 50, events := [])
    assert prince.alive and prince.deposed and prince.captive_of is None
    assert prince not in sim.families.line(house)


def test_court_intrigue_off_means_no_plots_or_murders():
    sim = Simulation(game_config("medium", 4, 3, intrigue="off"))
    families = sim.families
    assert families.intrigue == 0.0
    house = families.house_of(0)
    prince = next(p for p in families.line(house) if families.heir(house) is not p)
    prince.ambition = 1.0
    assert families._plot_chance(prince, house, sim.civs[0], family.PLOT_FROM) == 0.0
    assert "poison" not in family.sudden_rates(40, enemies=2, royal=True, intrigue=0.0)
    busy = Simulation(game_config("medium", 4, 3, intrigue="frequent")).families
    assert busy.intrigue > 1.0


def test_the_kings_children_govern_his_other_castles_and_a_rebel_takes_the_one_they_rule():
    sim, king = _realm_of_three()
    families = sim.families
    families._govern(sim.tick)
    house = families.house_of(king.id)
    assert families.ruler_of(king.id, king.capital.tile) == families.full_name(families.ruler(king.id))
    governors = [p for p in families.line(house) if p.governs is not None]
    assert governors and all(p.governs in [s.tile for s in king.settlements[1:]] for p in governors)
    for settlement in king.settlements[1:]:
        assert families.ruler_of(king.id, settlement.tile) is not None
    rebel_prince = governors[0]
    ruled = rebel_prince.governs
    families._rebel(rebel_prince, house, king, sim.tick, [], "caught")
    assert sim.civs[-1].capital.tile == ruled  # the castle they ruled is the one they take


def test_a_governor_brings_their_own_bonus_and_a_young_king_invites_plots():
    sim, king = _realm_of_three()
    families = sim.families
    families._govern(sim.tick)
    governor = families.governors(king.id)[0]
    governor.traits, governor.personality = [], "Merchant"
    from civsim.economy.modifiers import Modifiers
    mods = Modifiers()
    gold = mods.yield_mult["gold"]
    families.apply_modifiers(king, mods)
    assert mods.yield_mult["gold"] == gold + family.GOVERNOR_PERSONALITIES["Merchant"][1]
    governor.traits = ["brave"]  # a brave governor's bonus is the defence of their own castle
    assert families.governor_defence(king.id, governor.governs) == family.GOVERNOR_TRAITS["brave"][1]
    assert sim.military.post_defence(king, governor.governs) >= family.GOVERNOR_TRAITS["brave"][1]
    ruler = families.ruler(king.id)
    ruler.birth_day = family.born_aged(30, sim.tick)
    calm = families._troubles(king, sim.tick)
    ruler.birth_day = family.born_aged(15, sim.tick)  # under 18: his competence is doubted
    assert families._troubles(king, sim.tick) > calm
    assert family.RULE_AGE == 12


def test_in_the_endgame_a_long_peace_breeds_unrest_and_governors_who_rise(monkeypatch):
    sim, king = _realm_of_three()
    families = sim.families
    families._govern(sim.tick)
    house = families.house_of(king.id)
    governors = [p for p in families.line(house) if p.governs is not None]
    assert governors
    tick = 3000
    king.last_war = 0
    events: list = []
    families._long_peace(house, king, 200, events)
    assert not events, "a short peace stirs nobody"
    monkeypatch.setattr(family, "RESTLESS_MONTHLY", 1.0)
    monkeypatch.setattr(family, "GOVERNOR_TURN", 1.0)
    before = len(sim.civs)
    families._long_peace(house, king, tick, events)
    assert families.unrest(king.id, tick)
    assert len(sim.civs) == before + 1, "a governor rose with his castle"
    assert any("tired of a king who will not fight" in e["text"] for e in events)


def test_the_endgame_begins_when_no_free_land_is_left_or_half_the_age_is_gone():
    sim = Simulation(game_config("small", 3, seed=3))
    assert not sim.endgame(10)
    assert sim.endgame(sim.config.end_tick // 2)
    for region in sim.world.regions:
        if region.owner is None:
            region.owner = 0
    assert sim.endgame(10)
