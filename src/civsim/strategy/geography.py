"""What a region is worth to a civ: one valuation that expansion, campaigns against the
natives, war targets, the strategist and harbour building all use, so the AI wants the same
places for the same reasons.

A region's value is what it would bring, priced by what the civ lacks, plus its strategic
weight; discounted by how hard it is to get to; less what it would cost to take and to hold:

    total = (economic + strategic) * access / (1 + distance / DISTANCE_SCALE) - take - hold

Fixed facts about each region (yields, mines, terrain, ways in, drawn tags, how many routes
between other regions pass through it, which regions it touches by land or across water) are
worked out once per map. Each civ's values are refreshed every VALUE_INTERVAL days, or sooner
when the regions it holds change.
"""

import heapq
import math
from collections import deque
from dataclasses import dataclass, field

from ..diplomacy import rules
from ..economy.harbours import ports
from ..map import WorldMap
from ..map.blueprint import walking_links

RESOURCES = ("food", "wood", "stone", "ore", "gold")
RICHEST = 3.0  # a region counts as at most this many typical regions' worth of any one resource
SEA_DETOUR = 3.0  # for the routes between regions, a sea crossing counts this many times its length
VALUE_INTERVAL = 25
SEA_EDGE_MAX = 24  # regions further apart over open water than this are not neighbours by sea


@dataclass(frozen=True)
class ValuationParams:
    scarce: float = 1.5  # added to a resource's price at an empty store
    lacking: float = 1.5  # added when the civ's land barely yields it at all
    mine: float = 2.0  # one gold mine, in typical-region units
    tag: dict = field(default_factory=lambda: {"prize": 2.0, "gate": 1.5, "neck": 2.0, "crossroads": 2.0,
                                               "bridge": 1.0})
    centrality: float = 2.0  # for the region most routes between the others pass through
    distance_scale: float = 40.0  # tiles of travel at which a region is worth half as much
    by_sea: float = 0.85  # access across water, with boats and a harbour
    settle_only: float = 0.6  # across water with boats but no harbour: settlers can go, armies not
    later: float = 0.3  # across water before boats: a reason to want them
    take: float = 1.2  # per unit of (force needed / force it has)
    hold: float = 1.0  # per unit of (rivals' strength nearby / its own), on open ground
    terrain_shelter: float = 0.5  # how much defensive terrain eases holding


@dataclass
class Valuation:
    region: int
    economic: float
    strategic: float
    access: float  # 1 by land; less across water; 0 unreachable
    distance: float  # tiles of travel from the civ's nearest region
    take: float
    hold: float
    total: float
    by_sea: bool
    reasons: list[str]

    @property
    def reason(self) -> str:
        return ", ".join(self.reasons[:2]) if self.reasons else "its land"


class Geography:
    def __init__(self, world: WorldMap, civs: list, diplomacy, military=None, params: ValuationParams | None = None):
        self.world = world
        self.civs = {civ.id: civ for civ in civs}
        self.diplomacy = diplomacy
        self.military = military
        self.p = params or ValuationParams()
        self._cache: dict[int, tuple[int, frozenset, dict[int, Valuation]]] = {}
        self._study()

    # -- fixed facts -----------------------------------------------------------

    def _study(self) -> None:
        world = self.world
        n = len(world.regions)
        self.potential = [{res: 0.0 for res in RESOURCES} for _ in range(n)]
        self.mines = [0] * n
        defence = [[] for _ in range(n)]
        for region in world.regions:
            for t in region.tiles:
                for res, amount in world.yields[t].items():
                    if res in self.potential[region.id]:
                        self.potential[region.id][res] += amount
                if not world.is_water(t):
                    defence[region.id].append(rules.TILE_DEFENSE.get(world.biomes[t], 1.0))
        for tile in world.mines:
            if world.region_of[tile] >= 0:
                self.mines[world.region_of[tile]] += 1
        self.mean = {res: max(1e-6, sum(p[res] for p in self.potential) / max(1, n)) for res in RESOURCES}
        self.defence = [sum(d) / len(d) if d else 1.0 for d in defence]
        self.land = {pair for pair in walking_links(world)}
        self.sea = self._sea_neighbours()
        self.neighbours: list[dict[int, tuple[float, bool]]] = [{} for _ in range(n)]
        for a, b in self.land:
            d = self._gap(a, b)
            self.neighbours[a][b] = self.neighbours[b][a] = (d, False)
        for (a, b), gap in self.sea.items():
            if b not in self.neighbours[a]:
                d = self._gap(a, b)
                self.neighbours[a][b] = self.neighbours[b][a] = (d, True)
        self.ways_in = [sum(1 for _, (_, sea) in self.neighbours[r].items() if not sea) for r in range(n)]
        self.centrality = self._betweenness()

    def _gap(self, a: int, b: int) -> float:
        ax, ay = self.world.xy(self.world.regions[a].capital)
        bx, by = self.world.xy(self.world.regions[b].capital)
        return math.hypot(ax - bx, ay - by)

    def _sea_neighbours(self) -> dict[tuple[int, int], int]:
        """Pairs of regions facing each other across open water, with the fewest water tiles
        between their shores."""
        world = self.world
        label: dict[int, tuple[int, int]] = {}  # water tile -> (nearest region, water tiles from its shore)
        queue = deque()
        for t, r in enumerate(world.region_of):
            if r < 0 or not world.claimable(t):
                continue
            for n in world.neighbors(t):
                if world.is_open_water(n) and n not in label:
                    label[n] = (r, 1)
                    queue.append(n)
        while queue:
            t = queue.popleft()
            r, d = label[t]
            if d >= SEA_EDGE_MAX:
                continue
            for n in world.neighbors(t):
                if world.is_open_water(n) and n not in label:
                    label[n] = (r, d + 1)
                    queue.append(n)
        pairs: dict[tuple[int, int], int] = {}
        for t, (r, d) in label.items():
            for n in world.neighbors(t):
                other = None
                if n in label and label[n][0] != r:
                    other, gap = label[n][0], d + label[n][1]
                elif world.region_of[n] >= 0 and world.region_of[n] != r and world.claimable(n):
                    other, gap = world.region_of[n], d
                if other is not None and gap <= SEA_EDGE_MAX:
                    key = (min(r, other), max(r, other))
                    pairs[key] = min(gap, pairs.get(key, gap))
        return pairs

    def _betweenness(self) -> list[float]:
        """How many of the shortest routes between other regions pass through each one, 0 to 1."""
        n = len(self.world.regions)
        through = [0.0] * n
        for s in range(n):
            dist = self._dijkstra({s}, lambda a, b, sea: True, SEA_DETOUR)[0]
            for t in range(s + 1, n):
                if t not in dist:
                    continue
                # Walk back along one shortest route and credit what lies between.
                node = t
                while node != s:
                    prev = min((m for m in self.neighbours[node] if m in dist),
                               key=lambda m: dist[m] + self.neighbours[node][m][0]
                               * (SEA_DETOUR if self.neighbours[node][m][1] else 1.0))
                    if prev != s:
                        through[prev] += 1
                    node = prev
        top = max(through) or 1.0
        return [x / top for x in through]

    def _dijkstra(self, sources: set[int], allowed, sea_detour: float = 1.0) -> tuple[dict[int, float], dict[int, bool]]:
        dist = {s: 0.0 for s in sources}
        sea = {s: False for s in sources}
        heap = [(0.0, s) for s in sources]
        while heap:
            d, a = heapq.heappop(heap)
            if d > dist[a]:
                continue
            for b, (step, by_sea) in self.neighbours[a].items():
                if not allowed(a, b, by_sea):
                    continue
                step = step * sea_detour if by_sea else step
                if d + step < dist.get(b, math.inf):
                    dist[b] = d + step
                    sea[b] = sea[a] or by_sea
                    heapq.heappush(heap, (d + step, b))
        return dist, sea

    # -- a civ's view ------------------------------------------------------------

    def values(self, civ, tick: int) -> dict[int, Valuation]:
        """Every region's value to the civ; empty for a civ that has fallen."""
        if not civ.alive or not civ.settlements:
            return {}
        held = frozenset(r.id for r in self.world.regions if r.owner == civ.id)
        cached = self._cache.get(civ.id)
        if cached and cached[1] == held and tick - cached[0] < VALUE_INTERVAL:
            return cached[2]
        values = self._value_all(civ, held)
        self._cache[civ.id] = (tick, held, values)
        return values

    def value(self, civ, region_id: int, tick: int) -> Valuation:
        return self.values(civ, tick)[region_id]

    def _prices(self, civ, mods) -> dict[str, float]:
        p = self.p
        prices = {}
        for res in RESOURCES:
            store = mods.storage[res] if mods is not None else 100.0
            scarcity = 1.0 - min(1.0, civ.resources.get(res, 0.0) / max(store, 1.0))
            lacking = civ.capacity.get(res, 0) < 4 if res != "food" else civ.income.get("food", 0.0) < 0
            prices[res] = 0.5 + p.scarce * scarcity + (p.lacking if lacking else 0.0)
        return prices

    def _value_all(self, civ, held: frozenset) -> dict[int, Valuation]:
        world, p, diplomacy = self.world, self.p, self.diplomacy
        mods = diplomacy.mods[civ.id] if diplomacy is not None else None
        boats = bool(mods and mods.boats)
        harbour = boats and bool(ports(civ, world))
        sources = set(held) or {world.region_of[civ.capital.tile]}
        by_land, _ = self._dijkstra(sources, lambda a, b, sea: not sea)
        by_water, _ = self._dijkstra(sources, lambda a, b, sea: True)
        prices = self._prices(civ, mods)
        # Forces measured by what each civ could field fully mobilised: at the start, nobody has
        # an army yet, but some are plainly stronger than others.
        ours = max(1.0, diplomacy.power(civ)) if diplomacy is not None else 1.0
        natives = getattr(diplomacy, "natives", None)
        friends = set(diplomacy.allies(civ.id)) if diplomacy is not None else set()
        values = {}
        for region in world.regions:
            r = region.id
            reasons = []
            economic = sum(prices[res] * min(RICHEST, self.potential[r][res] / self.mean[res])
                           for res in RESOURCES) / len(RESOURCES)
            richest = max(RESOURCES, key=lambda res: self.potential[r][res] / self.mean[res])
            if self.potential[r][richest] / self.mean[richest] >= 1.5:
                reasons.append({"food": "rich farmland", "wood": "rich timber", "stone": "rich stone",
                                "ore": "rich iron", "gold": "gold"}[richest])
            if self.mines[r]:
                economic += p.mine * self.mines[r] * (0.5 + prices["gold"] / 2)
                reasons.insert(0, f"{'a gold mine' if self.mines[r] == 1 else f'{self.mines[r]} gold mines'}")
            strategic = sum(p.tag.get(tag, 0.0) for tag in region.tags) + p.centrality * self.centrality[r]
            for tag in region.tags:
                if tag in ("gate", "neck", "crossroads", "bridge"):
                    reasons.append({"gate": "it holds a pass", "neck": "it holds the only land bridge",
                                    "crossroads": "it is the crossroads", "bridge": "it holds a crossing"}[tag])
            if r in held:
                access, distance, sea = 1.0, 0.0, False
            elif r in by_land:
                access, distance, sea = 1.0, by_land[r], False
            elif r in by_water:
                distance, sea = by_water[r], True
                access = p.by_sea if harbour else p.settle_only if boats else p.later
                reasons.append("it needs ships" if not harbour else "across the water")
            else:
                access, distance, sea = 0.0, math.inf, False
            take = 0.0
            if region.owner is None and natives is not None and r not in held:
                need = 2.0 * natives.defence(region)
                settled = natives.shares(region).get(civ.id, 0.0)
                take = p.take * min(4.0, need / ours) * (1.0 - settled)
            elif region.owner is not None and region.owner != civ.id and diplomacy is not None:
                holder = self.civs[region.owner]
                regions_held = max(1, sum(1 for x in world.regions if x.owner == holder.id))
                need = rules.CAPITAL_DEFENSE * diplomacy.power(holder) / regions_held
                take = p.take * min(4.0, need / ours)
            exposure = 0.0
            for other_id, other in self.civs.items():
                if other_id == civ.id or other_id in friends or not other.alive:
                    continue
                if any(world.regions[b].owner == other_id for b in self.neighbours[r]):
                    exposure += (diplomacy.power(other) if diplomacy is not None else 1.0) / ours
            shelter = 1.0 + p.terrain_shelter * (self.defence[r] - 1.0) + 1.0 / max(1, self.ways_in[r])
            hold = p.hold * min(4.0, exposure) / shelter
            reach = access / (1.0 + distance / p.distance_scale) if access > 0 else 0.0
            total = (economic + strategic) * reach - take - hold
            values[r] = Valuation(r, round(economic, 3), round(strategic, 3), access,
                                  round(distance, 1) if distance != math.inf else math.inf,
                                  round(take, 3), round(hold, 3), round(total, 3), sea, reasons)
        return values

    def harbour_goal(self, civ, tick: int) -> int | None:
        """The capital of the most valuable region the civ can only reach across water, if it is
        worth reaching: where its harbour should face."""
        world = self.world
        best, best_total = None, 0.0
        for r, v in self.values(civ, tick).items():
            if v.by_sea and v.access > 0 and world.regions[r].owner != civ.id and v.total > best_total:
                best, best_total = world.regions[r].capital, v.total
        return best

    def prizes(self, civ, tick: int, count: int = 3) -> list[tuple[int, Valuation]]:
        """The regions it does not hold that are worth most to it."""
        values = self.values(civ, tick)
        ranked = sorted((r for r in values if self.world.regions[r].owner != civ.id and values[r].access > 0),
                        key=lambda r: (-values[r].total, r))
        return [(r, values[r]) for r in ranked[:count]]
