"""Rule-based civ AI: utility scoring over needs, scaled by per-civ personality weights.

Every tick each civ
  1. assesses its needs (0..~1.5 per category),
  2. picks a research target, scoring each available tech by what its effects are worth,
  3. picks a project (a building or a territory expansion) and starts it if affordable,
     otherwise keeps it as the goal it is saving for,
  4. splits its workers across resources according to what the goal still requires.
It also tears down buildings: ones it has long been unable to keep up, and, when it
has run out of room, its least useful building to make way for a much better one.

Score of an option = personality weight for its category x current need, with
diminishing returns. The strategic layer steers a civ through the standing orders
on the Civilization (soldier_target, military_need, march_target, exports); this
module turns them into day-to-day decisions.
"""

import math
import random
from collections import deque
from collections.abc import Callable

from ..economy import (
    BuildingDef,
    Modifiers,
    demolish,
    find_site,
    food_need,
    recompute_capacity,
    water_growth_factor,
)
from ..economy.rules import LAKE_WATER, RESOURCES, RIVER_WATER, SETTLEMENT_YIELDS, WORK_RATE
from ..map import BIOME_INFO, BOAT_RANGE, Biome, WorldMap
from ..tech import Tech, TechTree
from .civilization import Building, Civilization, Goal, Research

CATEGORY_OF_RESOURCE = {
    "food": "food", "wood": "industry", "stone": "industry", "ore": "industry", "gold": "wealth",
    "water": "growth",
}
MATERIALS = ("wood", "stone", "ore", "gold")

MIN_SCORE = 0.12  # below this nothing is worth doing; just stockpile
GOAL_STICKINESS = 1.2  # bonus for the goal already being saved for, to avoid flip-flopping
COUNT_FALLOFF = 0.35  # each existing copy of a building makes another less attractive ...
FALLOFF_POWER = 0.6  # ... but gently: rising costs and upkeep are what really limit a civ
STORE_NEED = 0.4  # how much a completely full store makes the civ want more room for it
UPKEEP_CAUTION = 0.2  # don't add upkeep in a resource that is below this share of storage and not growing
TILES_PER_EXPANSION = 4  # claiming budget per expansion; a river tile without bridges uses more of it
STABLES_NEED = 0.5  # how much a civ at peace wants stables, on the scale of the other needs
NO_FOREST = 6  # wood work slots on the land (capitals aside) below which expansion stops costing wood
WATER_MARGIN = 1.15  # look for more water once supply is below this multiple of consumption
SEEK_RANGE = 35  # how far (in tiles) a civ will stretch its border to reach a missing resource
MARCH_RANGE = 60  # ... or to reach a civ it intends to attack
RESERVE_TICKS = 40  # stock kept on hand to cover upkeep, food and trade exports
MATERIAL_RESERVE = {"wood": 30.0, "stone": 15.0, "ore": 0.0, "gold": 0.0, "water": 0.0}
ABANDON_AFTER = 60  # ticks of unpaid upkeep after which a building is torn down
REPLACE_ADVANTAGE = 2.0  # a new building must score this many times its victim to displace it
DEMOLITION_COOLDOWN = 25  # ticks between demolitions, so a civ never churns its buildings
RESEARCH_RETHINK_TICKS = 60  # reconsider a research target that still isn't paid for


class CivAI:
    def __init__(self, world: WorldMap, building_defs: dict[str, BuildingDef], tech_tree: TechTree,
                 rng: random.Random):
        self.world = world
        self.building_defs = building_defs
        self.tech_tree = tech_tree
        self.rng = rng
        # civ id -> resources whose cap was too low for something the civ wanted last tick
        self._cap_blocked: dict[int, set[str]] = {}

    def plan(self, civ: Civilization, mods: Modifiers, tick: int, events: list) -> None:
        needs = self.assess_needs(civ, mods)
        self._choose_research(civ, mods, needs, tick)
        self._abandon_unaffordable(civ, mods, tick, events)
        self._choose_project(civ, mods, needs, tick, events)
        self._allocate_workers(civ, mods)

    # -- needs ---------------------------------------------------------------

    def assess_needs(self, civ: Civilization, mods: Modifiers) -> dict:
        fill = {res: min(1.0, civ.resources[res] / mods.storage[res]) for res in RESOURCES}
        scarcity = {res: 1 - fill[res] for res in RESOURCES}
        blocked = self._cap_blocked.pop(civ.id, set())
        # Share of the population that must farm just to break even.
        eaten = food_need(civ)
        farming_share = eaten / max(civ.population, 1.0) / (WORK_RATE * (1 + mods.yield_mult["food"]))
        reserve_ticks = civ.resources["food"] / max(eaten, 1e-9)
        # Resources the territory barely provides: a reason to expand toward them.
        # (Every capital offers a few slots of its own; it is the land that counts here.)
        capitals = len(civ.settlements)
        wanted = [res for res in ("wood", "stone", "ore")
                  if civ.capacity[res] - SETTLEMENT_YIELDS[res] * capitals < 4]
        # Water is not gathered, so "barely provided" means supply is not keeping up with use.
        if mods.income["water"] < WATER_MARGIN * civ.upkeep["water"] or fill["water"] < 0.3:
            wanted.insert(0, "water")
        idle_share = civ.idle / max(civ.workforce, 1.0)
        return {
            # No point housing people there is no water for.
            "growth": _clamp((civ.population / mods.housing - 0.6) / 0.4, 0, 1.2) * water_growth_factor(civ, mods),
            "food": 2 * farming_share + (0.5 if reserve_ticks < 25 else 0.0),
            "industry": 0.2 + 0.6 * sum(scarcity[r] for r in ("wood", "stone", "ore")) / 3,
            "infrastructure": 0.6 * max(fill.values()) ** 3,
            # More room for a resource: wanted as its store fills up, or when its cap is in the way.
            "store": {res: 1.0 if res in blocked else STORE_NEED * fill[res] ** 3 for res in RESOURCES},
            "science": 0.55,
            "wealth": 0.25 + 0.35 * scarcity["gold"],
            "military": 0.1 + 0.9 * civ.military_need,
            "expansion": (0.25 + 0.75 * _clamp(3 * idle_share, 0, 1) + (0.4 if wanted else 0.0)
                          + (0.5 if civ.march_target is not None else 0.0)),
            "resource": {res: 0.2 + 0.6 * scarcity[res] for res in RESOURCES},
            "scarcity": scarcity,
            "wanted": wanted,
        }

    # -- research ------------------------------------------------------------

    def _choose_research(self, civ: Civilization, mods: Modifiers, needs: dict, tick: int) -> None:
        if civ.research is not None:
            stuck = not civ.research.paid and tick % RESEARCH_RETHINK_TICKS == 0
            if not stuck:
                return
        best, best_score = None, 0.0
        for tech in self.tech_tree.available(civ.known_techs):
            if not self._feasible(civ, tech.materials, mods):
                continue
            score = self._tech_value(civ, tech, needs)
            if score > best_score:
                best, best_score = tech, score
        civ.research = Research(best.id) if best else None

    def _tech_value(self, civ: Civilization, tech: Tech, needs: dict) -> float:
        weights = civ.personality.weights
        effects = tech.effects
        value = 0.25 * weights["science"]
        for res, amount in effects.get("yield_mult", {}).items():
            targets = RESOURCES if res == "all" else (res,)
            for target in targets:
                category = CATEGORY_OF_RESOURCE[target]
                need = needs["food"] if target == "food" else needs["resource"][target]
                value += 2.5 * amount * weights[category] * need / math.sqrt(len(targets))
        for res, amount in effects.get("income", {}).items():
            value += 1.5 * amount * weights[CATEGORY_OF_RESOURCE[res]]
        value += 0.05 * effects.get("housing", 0) * weights["growth"] * (0.3 + needs["growth"])
        value += 2.0 * effects.get("growth", 0) * weights["growth"]
        value += 0.004 * effects.get("storage", 0) * weights["infrastructure"] * (0.3 + needs["infrastructure"])
        value += 3.0 * effects.get("science_mult", 0) * weights["science"]
        value += 1.5 * effects.get("build_speed", 0) * weights["industry"]
        value += 0.6 * effects.get("build_slots", 0) * weights["industry"]
        value += 3.0 * effects.get("demolition_refund", 0) * weights["infrastructure"]
        value -= 2.0 * effects.get("expand_cost", 0) * weights["expansion"]
        value += 0.4 * (effects.get("bridges", 0) + effects.get("boats", 0)) * weights["expansion"]
        value += (0.05 * effects.get("boat_range", 0) + 0.3 * effects.get("home_speed", 0)
                  + 0.2 * effects.get("reinforce", 0)) * weights["expansion"]
        warfare = (effects.get("commander_xp", 0) + 0.5 * effects.get("commander_start", 0)
                   + effects.get("capture_speed", 0) - 2 * effects.get("casualties", 0)
                   + 3 * effects.get("mobilization", 0))
        value += warfare * weights["military"] * (0.3 + needs["military"])
        value -= 0.6 * effects.get("deal_fee", 0) * weights["wealth"]
        value += 0.3 * effects.get("villager_speed", 0) * weights["industry"]
        value -= 2.0 * effects.get("water_use", 0) * weights["growth"] * (1 + 3 * needs["scarcity"]["water"])
        # Purification is worth what the coast it would tap is worth, and far more when water is short.
        coast_water = effects.get("purification", 0) * civ.water_access["coast"]
        value += (0.1 + 0.15 * coast_water) * weights["growth"] * (1 + 3 * needs["scarcity"]["water"]) * (
            1 if "purification" in effects else 0)
        value += 1.5 * effects.get("water_mult", 0) * weights["growth"] * (1 + 3 * needs["scarcity"]["water"])
        value += 2.0 * (effects.get("military", 0) + effects.get("defense", 0)) * weights["military"] * (
            0.3 + needs["military"])
        for bdef in self.building_defs.values():
            if bdef.requires_tech == tech.id:
                value += 0.5 * weights[bdef.category] * self._building_need(bdef, needs)
        # Cheaper techs first: value per unit of research effort.
        return value / math.sqrt(tech.science_cost / 30)

    # -- projects ------------------------------------------------------------

    def _choose_project(self, civ: Civilization, mods: Modifiers, needs: dict, tick: int, events: list) -> None:
        under_construction = sum(1 for b in civ.buildings if not b.complete)
        if under_construction >= mods.build_slots:
            civ.goal = None
            return

        weights = civ.personality.weights
        options: list[tuple[float, str, str, dict]] = []
        for bdef in self.building_defs.values():
            if bdef.requires_tech and bdef.requires_tech not in civ.known_techs:
                continue
            count = civ.count(bdef.id)
            if bdef.max_count is not None and count >= bdef.max_count:
                continue
            if bdef.need_resource and civ.capacity[bdef.need_resource] <= 0:
                continue
            cost = bdef.cost_for(count)
            if not self._feasible(civ, cost, mods) or not self._sustainable(civ, bdef, mods):
                continue
            options.append((self._building_score(civ, bdef, needs, count), "build", bdef.id, cost))

        expand_cost = self.expansion_cost(civ, mods)
        if self._feasible(civ, expand_cost, mods):
            added = max(0, len(civ.territory) - civ.base_territory)
            score = weights["expansion"] * needs["expansion"] / (1 + added / 250)
            options.append((score, "expand", "", expand_cost))

        previous = civ.goal
        if previous:
            options = [
                (score * GOAL_STICKINESS if (kind, target) == (previous.kind, previous.target or "") else score,
                 kind, target, cost)
                for score, kind, target, cost in options
            ]
        options.sort(key=lambda option: (-option[0], option[1], option[2]))

        civ.goal = None
        for score, kind, target, cost in options:
            if score < MIN_SCORE:
                break
            if kind == "build":
                site = find_site(civ, self.world, self.building_defs[target])
                if site is None and civ.can_afford(cost):
                    site = self._make_room(civ, mods, self.building_defs[target], score, needs, tick, events)
                if site is None:
                    continue
                civ.goal = Goal("build", target, cost)
                if civ.can_afford(cost):
                    civ.pay(cost)
                    civ.buildings.append(Building(target, site))
                    civ.goal = None
            else:
                border = self._border(civ, mods)
                if not border:
                    continue
                civ.goal = Goal("expand", None, cost)
                if civ.can_afford(cost):
                    civ.pay(cost)
                    self._expand(civ, mods, border, needs)
                    civ.goal = None
            return

    def _building_score(self, civ: Civilization, bdef: BuildingDef, needs: dict, count: int) -> float:
        """How much the civ wants a copy of this building when it already has `count`."""
        # Storage tapers off quickly: a full store alone justifies only a handful of buildings.
        falloff = (1 + COUNT_FALLOFF * count) ** (1.0 if bdef.stores else FALLOFF_POWER)
        return civ.personality.weights[bdef.category] * self._building_need(bdef, needs) / falloff

    # -- demolition ----------------------------------------------------------

    def _abandon_unaffordable(self, civ: Civilization, mods: Modifiers, tick: int, events: list) -> None:
        """Tear down one building whose upkeep has gone unpaid for a long time."""
        if tick - civ.last_demolition < DEMOLITION_COOLDOWN:
            return
        stale = [b for b in civ.buildings if b.unpaid_ticks >= ABANDON_AFTER]
        if stale:
            demolish(civ, max(stale, key=lambda b: (b.unpaid_ticks, b.tile)), mods, self.building_defs, events)
            civ.last_demolition = tick

    def _make_room(self, civ: Civilization, mods: Modifiers, wanted: BuildingDef, score: float, needs: dict,
                   tick: int, events: list) -> int | None:
        """With no room left, clear the civ's least useful building if `wanted` is far better.

        Returns the tile with the freed slot, or None if nothing is worth giving up.
        """
        if tick - civ.last_demolition < DEMOLITION_COOLDOWN:
            return None
        world = self.world
        resource = wanted.placement.partition(":")[2]
        cx, cy = world.xy(civ.capital.tile)

        def worth(building: Building) -> tuple[float, float, int]:
            # Value of the last copy of its type; among equals, give up the most remote one.
            bdef = self.building_defs[building.type]
            x, y = world.xy(building.tile)
            return (self._building_score(civ, bdef, needs, civ.count(bdef.id) - 1),
                    -math.hypot(x - cx, y - cy), building.tile)

        has_one = {b.tile for b in civ.buildings if b.type == wanted.id}  # no two of a type on a tile
        candidates = [
            b for b in civ.buildings
            if b.complete and b.type != wanted.id and b.tile not in has_one
            and BIOME_INFO[world.biomes[b.tile]].buildable
            and (not resource or world.yields[b.tile].get(resource, 0) > 0)
        ]
        if not candidates:
            return None
        victim = min(candidates, key=worth)
        if score < REPLACE_ADVANTAGE * worth(victim)[0]:
            return None
        demolish(civ, victim, mods, self.building_defs, events)
        civ.last_demolition = tick
        return victim.tile

    def _building_need(self, bdef: BuildingDef, needs: dict) -> float:
        if bdef.stores:
            return max(needs["store"][res] for res in bdef.stores)
        if bdef.need_resource:
            return needs["resource"][bdef.need_resource]
        if bdef.id == "stables":
            # Worth having in peace too: horses work the land as well as carrying cavalry.
            return max(needs["military"], STABLES_NEED)
        return needs[bdef.category]

    def _feasible(self, civ: Civilization, cost: dict[str, float], mods: Modifiers) -> bool:
        """False if the civ could never pay: over storage, or a resource it cannot produce."""
        for res, amount in cost.items():
            if amount > mods.storage[res]:
                self._cap_blocked.setdefault(civ.id, set()).add(res)
                return False
            if civ.resources[res] < amount and not self._obtainable(civ, res, mods):
                return False
        return True

    def _sustainable(self, civ: Civilization, bdef: BuildingDef, mods: Modifiers) -> bool:
        """False if the civ has no supply of a resource the building's upkeep needs, or is already short of it."""
        # Materials a tech is still waiting for: nothing new may eat into those.
        waiting = {}
        if civ.research and not civ.research.paid:
            waiting = self.tech_tree.techs[civ.research.tech_id].materials
        for res, amount in bdef.upkeep.items():
            if not self._obtainable(civ, res, mods):
                return False
            if civ.resources[res] < waiting.get(res, 0):
                return False
            # While stock is low, only take on upkeep that leaves the resource still clearly growing.
            if civ.resources[res] < UPKEEP_CAUTION * mods.storage[res] and civ.income[res] < 2 * amount:
                return False
        return True

    def _obtainable(self, civ: Civilization, res: str, mods: Modifiers) -> bool:
        return civ.capacity[res] > 0 or mods.income[res] > 0 or civ.imports[res] > 0 or res == "gold"

    # -- territory -----------------------------------------------------------

    def expansion_cost(self, civ: Civilization, mods: Modifiers) -> dict[str, float]:
        # Priced on land added since the start: the two home regions come free.
        size = max(0, len(civ.territory) - civ.base_territory)
        factor = max(0.3, 1 + mods.expand_cost)
        food, wood = (15 + 0.4 * size) * factor, (10 + 0.25 * size) * factor
        woodland = civ.capacity["wood"] - SETTLEMENT_YIELDS["wood"] * len(civ.settlements)
        if woodland < NO_FOREST:
            # A civ with next to no woodland could never save the timber, and so never reach
            # any: it expands on food alone, at twice the price.
            return {"food": round(2 * food)}
        return {"food": round(food), "wood": round(wood)}

    def _border(self, civ: Civilization, mods: Modifiers) -> list[int]:
        """Unowned, claimable tiles next to the civ's territory, or a boat trip away from it."""
        world = self.world
        border: set[int] = set()
        water: list[int] = []
        seen: set[int] = set()
        for tile in civ.territory:
            for n in world.neighbors(tile):
                if world.is_open_water(n):
                    if n not in seen:
                        seen.add(n)
                        water.append(n)
                elif world.owner[n] < 0 and n not in world.capital_tiles:
                    border.add(n)  # native land can be settled; a capital has to defect or be taken
        if mods.boats:
            # Boats: sail up to BOAT_RANGE tiles of open water and land on whatever lies beyond.
            for _ in range(BOAT_RANGE + mods.boat_range):
                further = []
                for tile in water:
                    for n in world.neighbors(tile):
                        if n in seen:
                            continue
                        seen.add(n)
                        if world.is_open_water(n):
                            further.append(n)
                        elif world.owner[n] < 0 and n not in world.capital_tiles:
                            border.add(n)
                water = further
        return sorted(border)

    def _water_value(self, tile: int, mods: Modifiers) -> float:
        """Water per tick that owning this tile would add."""
        world = self.world
        value = RIVER_WATER * world.rivers.get(tile, 0)
        value += LAKE_WATER * sum(1 for n in world.neighbors(tile) if world.biomes[n] == Biome.LAKE)
        if world.biomes[tile] == Biome.SHALLOWS:
            value += mods.purification
        return value

    def _expand(self, civ: Civilization, mods: Modifiers, border: list[int], needs: dict) -> None:
        world = self.world
        cx, cy = world.xy(civ.capital.tile)
        thirst = 2 + 6 * needs["scarcity"]["water"] + (6 if "water" in needs["wanted"] else 0)

        def appeal(tile: int) -> float:
            x, y = world.xy(tile)
            value = sum(
                amount * (1 + needs["scarcity"][res] + (2 if res in needs["wanted"] else 0))
                for res, amount in world.yields[tile].items()
            )
            value += thirst * self._water_value(tile, mods)
            return value - 0.08 * math.hypot(x - cx, y - cy) + 0.3 * self.rng.random()

        def provides(res: str):
            if res == "water":
                return lambda t: self._water_value(t, mods) > 0
            return lambda t: world.yields[t].get(res, 0) > 0

        # Head for a civ marked for attack or a resource the territory lacks,
        # then fill up with the most appealing tiles.
        route: list[int] = []
        if civ.march_target is not None:
            enemy = civ.march_target
            path = self._path_to(border, mods, lambda t: any(world.owner[n] == enemy for n in world.neighbors(t)))
            if 0 < len(path) <= MARCH_RANGE:
                route = path
        if not route:
            for res in needs["wanted"]:
                path = self._path_to(border, mods, provides(res))
                if 0 < len(path) <= SEEK_RANGE:
                    route = path
                    break
        ranked = sorted((tile for tile in border if tile not in route), key=appeal, reverse=True)

        # Spend the claiming budget along the route first, then on the most appealing tiles.
        # Fording a river without bridges uses up most of an expansion.
        budget = float(TILES_PER_EXPANSION)
        claimed = 0
        for tile in route + ranked:
            cost = world.crossing_cost(tile, bool(mods.bridges), bool(mods.boats)) or 1.0
            if cost > budget and claimed:
                if tile in route:
                    break  # a route is claimed in order; wait for the next expansion
                continue
            budget -= cost
            claimed += 1
            world.claim(tile, civ.id)
            civ.territory.add(tile)
            if budget <= 0:
                break
        recompute_capacity(civ, world)

    def _path_to(self, border: list[int], mods: Modifiers, is_goal: Callable[[int], bool]) -> list[int]:
        """Shortest chain of claimable tiles from the border to the nearest goal tile.

        With boats the search may cross open water; the water tiles are left out
        of the result, since only the land on either side can be claimed.
        """
        world = self.world
        parent: dict[int, int | None] = dict.fromkeys(border)
        queue = deque(border)
        while queue:
            tile = queue.popleft()
            if not world.is_open_water(tile) and is_goal(tile):
                path = []
                step: int | None = tile
                while step is not None:
                    if not world.is_open_water(step):
                        path.append(step)
                    step = parent[step]
                return path[::-1]
            for n in world.neighbors(tile):
                if n in parent or world.owner[n] >= 0 or n in world.capital_tiles:
                    continue
                if world.is_open_water(n) and not mods.boats:
                    continue
                parent[n] = tile
                queue.append(n)
        return []

    # -- workers -------------------------------------------------------------

    def _allocate_workers(self, civ: Civilization, mods: Modifiers) -> None:
        # What the civ wants in stock: a reserve covering upkeep and exports,
        # plus whatever it is saving for.
        eaten = food_need(civ)
        target = dict(MATERIAL_RESERVE)
        target["food"] = 0.0
        for res in RESOURCES:
            target[res] += RESERVE_TICKS * (civ.upkeep[res] + civ.exports[res])
        target["food"] = max(target["food"], RESERVE_TICKS * eaten)
        pending = [civ.goal.cost] if civ.goal else []
        if civ.research and not civ.research.paid:
            pending.append(self.tech_tree.techs[civ.research.tech_id].materials)
        for cost in pending:
            for res, amount in cost.items():
                target[res] += amount
        urgency = {
            res: _clamp((target[res] - civ.resources[res]) / max(target[res], 1.0), 0, 1) for res in RESOURCES
        }

        workers = dict.fromkeys(RESOURCES, 0.0)
        remaining = civ.workforce

        # Food first: enough farmers to break even, more when the reserve is low.
        break_even = (eaten + civ.exports["food"]) / (WORK_RATE * (1 + mods.yield_mult["food"]))
        workers["food"] = min(break_even * (0.9 + 0.7 * urgency["food"]), civ.capacity["food"], remaining)
        remaining -= workers["food"]

        # Split the rest by weighted urgency, spilling over when a resource runs out of work slots.
        weights = civ.personality.weights
        active = {
            res: weights[CATEGORY_OF_RESOURCE[res]] * (0.1 + urgency[res])
            for res in MATERIALS
            if civ.capacity[res] > 0 and civ.resources[res] < mods.storage[res]
        }
        while remaining > 1e-6 and active:
            total = sum(active.values())
            spill = 0.0
            for res, score in list(active.items()):
                share = remaining * score / total
                room = civ.capacity[res] - workers[res]
                if share >= room:
                    workers[res] += room
                    spill += share - room
                    del active[res]
                else:
                    workers[res] += share
            remaining = spill

        # Anyone still idle farms, if there is land and room to store the food.
        if remaining > 0 and civ.resources["food"] < mods.storage["food"]:
            extra = min(remaining, civ.capacity["food"] - workers["food"])
            workers["food"] += extra
            remaining -= extra

        civ.workers = workers
        civ.idle = max(0.0, remaining)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
