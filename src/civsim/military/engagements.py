"""Fights as a spectator follows them: one record per battle, siege or assault on a native
capital, kept up to date by the fighting itself (military/warfare.py) and sent to the viewer
while nobody rules a civ (bridge/protocol.py).

A record holds where the fight is, who fights it (each side's civ, general, soldiers now and at
the start, and its losses today and in all), for a siege how far the breach and the hold have
got, and its last few notes. A fight nobody touched today is over; its record stays a few days
so its ending can be read, then goes.
"""

from collections import deque
from dataclasses import dataclass, field

KEEP_AFTER = 5  # days a finished fight stays on show
NOTES = 6  # notes kept per fight


@dataclass
class Side:
    civ: int | None  # None for the native faction
    name: str  # the civ's (or the faction's) name
    general: dict | None  # {"name", "level"} of the commander leading it, if any
    soldiers: float
    start: float
    lost_today: float = 0.0
    lost: float = 0.0


@dataclass
class Engagement:
    id: str
    kind: str  # "battle" | "siege" | "storm"
    x: int
    y: int
    place: str  # the castle fought for, or the region the battle is in
    started: int
    sides: list[Side]
    siege: dict | None = None  # {"breach": 0-1, "held": days, "needed": days} for a siege
    notes: deque = field(default_factory=lambda: deque(maxlen=NOTES))
    touched: int = 0  # the last day it was fought
    over: int | None = None  # the day it ended
    result: str = ""


class Engagements:
    def __init__(self):
        self.records: dict[str, Engagement] = {}

    def fight(self, key: str, kind: str, tile: tuple[int, int], place: str, tick: int, sides: list[dict],
              siege: dict | None = None) -> Engagement:
        """Record a day of a fight. `sides` are dicts with civ, name, general, soldiers and lost
        (today's losses); a side first seen today starts with what it has plus what it lost."""
        record = self.records.get(key)
        if record is None or record.over is not None:
            record = Engagement(key, kind, tile[0], tile[1], place, tick, [])
            record.notes.append(f"Day {tick}: " + {"battle": "battle is joined", "siege": "the siege begins",
                                                     "storm": "the assault begins"}.get(kind, "the fighting begins"))
            self.records[key] = record
        if record.touched != tick:  # a new day: today's losses start again
            for side in record.sides:
                side.lost_today = 0.0
        by_civ = {side.civ: side for side in record.sides}
        for given in sides:
            side = by_civ.get(given["civ"])
            if side is None:
                side = Side(given["civ"], given["name"], given.get("general"), 0.0,
                            given["soldiers"] + given.get("lost", 0.0))
                record.sides.append(side)
                if record.touched:  # someone joins a fight already going on
                    record.notes.append(f"Day {tick}: {given['name']} joins with {round(side.start)}")
            side.soldiers = given["soldiers"]
            side.general = given.get("general") or side.general
            side.start = max(side.start, side.soldiers)
            side.lost_today += given.get("lost", 0.0)
            side.lost += given.get("lost", 0.0)
        record.siege = siege if siege is not None else record.siege
        record.x, record.y = tile
        record.touched = tick
        return record

    def note(self, key: str, tick: int, text: str) -> None:
        record = self.records.get(key)
        if record is not None:
            record.notes.append(f"Day {tick}: {text}")

    def end(self, key: str, tick: int, result: str) -> None:
        record = self.records.get(key)
        if record is not None and record.over is None:
            record.over, record.result = tick, result
            record.notes.append(f"Day {tick}: {result}")

    def end_of_day(self, tick: int) -> None:
        """A fight not fought today is over; one long over is forgotten. Each fight still going
        gets a line for the day's losses."""
        for key, record in list(self.records.items()):
            if record.over is None and record.touched < tick:
                record.over, record.result = tick, record.result or "The fighting stops"
            if record.over is not None and tick - record.over > KEEP_AFTER:
                del self.records[key]
                continue
            if record.over is None:
                lost = [f"{side.name} -{round(side.lost_today)}" for side in record.sides if side.lost_today >= 0.5]
                if lost:
                    text = f"Day {tick}: " + ", ".join(lost)
                    if not record.notes or record.notes[-1] != text:
                        record.notes.append(text)
