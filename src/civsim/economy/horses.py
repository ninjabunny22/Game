"""Horses: bred at stables, then ridden by cavalry or by villagers.

A civ's `horses` are the ones standing in the stables with no rider. Raising a
cavalryman takes one; so does mounting a villager, who then does the work of
several on the land he works. Every horse, ridden or not, eats and drinks more
than a person, so a herd is a real cost whichever way it is used. A cavalryman
who is lost takes his horse with him; a mounted villager on a captured tile
loses the horse and carries on as an ordinary villager.
"""

from .rules import HERD_PER_STABLE, HORSE_BREED_TICKS, MOUNTED_SHARE

STABLES = "stables"


def stables(civ) -> int:
    """Working stables: built and with their upkeep paid."""
    return sum(1 for b in civ.buildings if b.type == STABLES and b.complete and b.active)


def tend_horses(civ) -> None:
    """Breed toward what the stables can hold, and put spare horses under villagers in peacetime."""
    working = stables(civ)
    room = HERD_PER_STABLE * working - civ.herd
    if working and room >= 1:
        civ.horse_progress += working / HORSE_BREED_TICKS
        while civ.horse_progress >= 1 - 1e-9 and room >= 1:
            civ.horse_progress = max(0.0, civ.horse_progress - 1)
            civ.horses += 1
            room -= 1
    else:
        civ.horse_progress = 0.0

    # The army has first call on the herd: villagers only ride when nothing threatens.
    if civ.military_need > 0:
        return
    riding = sum(1 for v in civ.villagers if v.mounted)
    for villager in civ.villagers:
        if civ.horses < 1 or riding >= MOUNTED_SHARE * len(civ.villagers):
            break
        if not villager.mounted:
            villager.mounted = True
            civ.horses -= 1
            riding += 1
