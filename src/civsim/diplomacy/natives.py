"""The native faction: holds every region no civ does.

It makes no decisions. Each neutral capital has a garrison that fights only
armies sent against it. A native region is taken whole, by beating that garrison;
there is no settling it tile by tile, and no winning it over without a fight.
"""

import random

from ..map import WorldMap
from . import rules


class Natives:
    def __init__(self, world: WorldMap, civs: list, diplomacy, rng: random.Random):
        self.world = world
        self.civs = {civ.id: civ for civ in civs}
        self.diplomacy = diplomacy
        self.rng = rng
        for region in world.regions:
            if region.neutral:
                region.garrison = self.garrison_size(0, region)

    def garrison_size(self, tick: int, region=None) -> float:
        """Full strength of a neutral capital's garrison at this point in the game. A stronghold
        (a drawn map's region with strength above 1) keeps that many times an ordinary one."""
        full = min(rules.NATIVE_GARRISON_MAX, rules.NATIVE_GARRISON + rules.NATIVE_GROWTH * tick)
        return full * (region.strength if region is not None else 1.0)

    def defence(self, region) -> float:
        """Strength an attacker must overcome: the garrison, fighting on its own ground."""
        return region.garrison * (1 + rules.HOME_BONUS)

    def after(self, region) -> list[int]:
        """The civs with an army on its way to take this region, or fighting for it."""
        return sorted(civ.id for civ in self.civs.values() if civ.alive
                      and any(army.target_region == region.id for army in civ.armies))

    def update(self, tick: int, events: list) -> None:
        for region in self.world.regions:
            full = self.garrison_size(tick, region)
            if region.neutral and region.under_attack < tick - 1 and region.garrison < full:
                region.garrison = min(full, region.garrison + rules.NATIVE_RECOVERY * full)
