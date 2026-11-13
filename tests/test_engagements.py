"""Fights as a spectator follows them: each battle, siege and assault on a native capital has
a record with its sides, losses and notes, sent to the viewer only while nobody rules a civ."""

import json

from civsim.bridge import protocol
from civsim.config import game_config
from civsim.military.engagements import Engagements
from civsim.simulation import Simulation
from civsim.strategy import make_brain


def test_a_fight_is_followed_day_by_day_and_ends_with_its_result():
    book = Engagements()
    sides = [{"civ": 0, "name": "Zhanlu", "general": {"name": "Aldric", "level": 2}, "soldiers": 90, "lost": 10},
             {"civ": 1, "name": "Valmere", "general": None, "soldiers": 40, "lost": 20}]
    book.fight("battle:1:2", "battle", (5, 6), "Glasswater", 100, sides)
    record = book.records["battle:1:2"]
    assert [s.start for s in record.sides] == [100, 60], "it started with what it has plus what it lost"
    sides[0].update(soldiers=80, lost=10)
    sides[1].update(soldiers=25, lost=15)
    book.fight("battle:1:2", "battle", (5, 6), "Glasswater", 101, sides)
    assert record.sides[1].lost_today == 15 and record.sides[1].lost == 35
    book.end_of_day(101)
    assert "Valmere -15" in record.notes[-1]
    book.end("battle:1:2", 102, "Valmere's army breaks and runs")
    assert record.over == 102 and record.notes[-1].endswith("breaks and runs")
    book.end_of_day(110)
    assert "battle:1:2" not in book.records, "a finished fight is forgotten after a few days"


def test_fights_reach_a_spectator_but_not_a_ruler():
    sim = Simulation(game_config("small", 4, seed=11))
    brain = make_brain("utility")
    kinds = set()
    for _ in range(2500):
        sim.step_with(brain)
        kinds |= {r.kind for r in sim.military.engagements.records.values()}
        if {"storm", "battle"} <= kinds and sim.military.engagements.records:
            break
    assert "storm" in kinds and "battle" in kinds, f"saw only {kinds}"
    sent = json.loads(protocol.tick_message(sim, False, 1.0))["data"]["engagements"]
    assert sent and all(f["headline"] and f["sides"] and "notes" in f for f in sent)
    sim.ruler.command("take_control", {"civ": sim.civs[0].id})
    assert json.loads(protocol.tick_message(sim, False, 1.0))["data"]["engagements"] == []
