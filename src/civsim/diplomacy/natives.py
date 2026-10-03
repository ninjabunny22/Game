"""The native faction: holds every region no civ does.

It makes no decisions. Each neutral capital has a garrison that fights only
armies sent against it, and its people can be won over without a fight: as a
civ settles more of a region, the natives beside its land start to go over to
it, and once most of the region is its, the capital may open its gates.
"""

import random

from ..economy import recompute_capacity
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
                region.garrison = self.garrison_size(0)

    def garrison_size(self, tick: int) -> float:
        """Full strength of a neutral capital's garrison at this point in the game."""
        return min(rules.NATIVE_GARRISON_MAX, rules.NATIVE_GARRISON + rules.NATIVE_GROWTH * tick)

    def defence(self, region) -> float:
        """Strength an attacker must overcome: the garrison, fighting on its own ground."""
        return region.garrison * (1 + rules.HOME_BONUS)

    def shares(self, region) -> dict[int, float]:
        """Share of the region's land (its capital aside) each civ has settled."""
        counts: dict[int, int] = {}
        for tile in region.tiles:
            owner = self.world.owner[tile]
            if owner >= 0 and tile != region.capital:
                counts[owner] = counts.get(owner, 0) + 1
        total = max(1, len(region.tiles) - 1)
        return {civ_id: count / total for civ_id, count in counts.items()}

    def update(self, tick: int, events: list) -> None:
        full = self.garrison_size(tick)
        for region in self.world.regions:
            if region.neutral and region.under_attack < tick - 1 and region.garrison < full:
                region.garrison = min(full, region.garrison + rules.NATIVE_RECOVERY * full)
        if tick % rules.DEFECTION_INTERVAL == 0:
            for region in self.world.regions:
                if region.neutral:
                    self._defections(region, tick, events)

    def _defections(self, region, tick: int, events: list) -> None:
        shares = self.shares(region)
        if not shares:
            return
        leader_id = max(sorted(shares), key=lambda civ_id: shares[civ_id])
        share = shares[leader_id]
        if share < rules.TILE_DEFECTION_SHARE:
            return
        world = self.world
        leader = self.civs[leader_id]

        # Natives living beside the leading civ's land go over to it.
        chance = rules.TILE_DEFECTION_RATE * (share - rules.TILE_DEFECTION_SHARE)
        joined = 0
        for tile in region.tiles:
            if world.owner[tile] >= 0 or tile == region.capital:
                continue
            if any(world.owner[n] == leader_id for n in world.neighbors(tile)) and self.rng.random() < chance:
                world.claim(tile, leader_id)
                leader.territory.add(tile)
                joined += 1
        if joined:
            recompute_capacity(leader, world)

        # And once most of the region is its, the capital itself may join.
        if share >= rules.CAPITAL_DEFECTION_SHARE and self.rng.random() < share - rules.CAPITAL_DEFECTION_SHARE:
            self.diplomacy.capture_region(leader, region, tick, events, peaceful=True)
