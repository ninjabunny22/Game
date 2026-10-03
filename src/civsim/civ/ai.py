"""Rule-based civ AI: utility scoring over needs, scaled by per-civ personality weights.

Every tick each civ
  1. assesses its needs (0..~1.5 per category),
  2. picks a research target, scoring each available tech by what its effects are worth,
  3. picks a project (a building or a territory expansion) and starts it if affordable,
     otherwise keeps it as the goal it is saving for,
  4. splits its workers across resources according to what the goal still requires.

Score of an option = personality weight for its category x current need, with
diminishing returns. A later strategy layer can steer a civ by changing its weights.
"""

import math
import random
from collections import deque

from ..economy import BuildingDef, Modifiers, find_site, recompute_capacity
from ..economy.rules import FOOD_PER_POP, RESOURCES, WORK_RATE
from ..map import Biome, WorldMap
from ..tech import Tech, TechTree
from .civilization import Building, Civilization, Goal, Research

CATEGORY_OF_RESOURCE = {
    "food": "food", "wood": "industry", "stone": "industry", "ore": "industry", "gold": "wealth",
}
MATERIALS = ("wood", "stone", "ore", "gold")

MIN_SCORE = 0.12  # below this nothing is worth doing; just stockpile
GOAL_STICKINESS = 1.2  # bonus for the goal already being saved for, to avoid flip-flopping
COUNT_FALLOFF = 0.35  # each existing copy of a building makes another less attractive
TILES_PER_EXPANSION = 4
SEEK_RANGE = 20  # how far (in tiles) a civ will stretch its border to reach a missing resource
FOOD_RESERVE_TICKS = 40
MATERIAL_RESERVE = {"wood": 30.0, "stone": 15.0, "ore": 0.0, "gold": 0.0}
RESEARCH_RETHINK_TICKS = 60  # reconsider a research target that still isn't paid for


class CivAI:
    def __init__(self, world: WorldMap, building_defs: dict[str, BuildingDef], tech_tree: TechTree,
                 rng: random.Random):
        self.world = world
        self.building_defs = building_defs
        self.tech_tree = tech_tree
        self.rng = rng

    def plan(self, civ: Civilization, mods: Modifiers, tick: int, events: list) -> None:
        needs = self.assess_needs(civ, mods)
        self._choose_research(civ, mods, needs, tick)
        self._choose_project(civ, mods, needs, events)
        self._allocate_workers(civ, mods)

    # -- needs ---------------------------------------------------------------

    def assess_needs(self, civ: Civilization, mods: Modifiers) -> dict:
        scarcity = {res: 1 - min(1.0, civ.resources[res] / mods.storage) for res in RESOURCES}
        # Share of the population that must farm just to break even.
        farming_share = FOOD_PER_POP / (WORK_RATE * (1 + mods.yield_mult["food"]))
        reserve_ticks = civ.resources["food"] / max(civ.population * FOOD_PER_POP, 1e-9)
        # Resources the territory barely provides: a reason to expand toward them.
        wanted = [res for res in ("wood", "stone", "ore") if civ.capacity[res] < 4]
        idle_share = civ.idle / max(civ.population, 1.0)
        return {
            "growth": _clamp((civ.population / mods.housing - 0.6) / 0.4, 0, 1.2),
            "food": 2 * farming_share + (0.5 if reserve_ticks < 25 else 0.0),
            "industry": 0.2 + 0.6 * sum(scarcity[r] for r in ("wood", "stone", "ore")) / 3,
            "infrastructure": 0.6 * max(1 - scarcity[r] for r in RESOURCES) ** 3,
            "science": 0.55,
            "wealth": 0.25 + 0.35 * scarcity["gold"],
            "expansion": 0.25 + 0.75 * _clamp(3 * idle_share, 0, 1) + (0.4 if wanted else 0.0),
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
        value -= 2.0 * effects.get("expand_cost", 0) * weights["expansion"]
        for bdef in self.building_defs.values():
            if bdef.requires_tech == tech.id:
                value += 0.5 * weights[bdef.category] * self._building_need(bdef, needs)
        # Cheaper techs first: value per unit of research effort.
        return value / math.sqrt(tech.science_cost / 30)

    # -- projects ------------------------------------------------------------

    def _choose_project(self, civ: Civilization, mods: Modifiers, needs: dict, events: list) -> None:
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
            if not self._feasible(civ, cost, mods):
                continue
            score = weights[bdef.category] * self._building_need(bdef, needs) / (1 + COUNT_FALLOFF * count)
            options.append((score, "build", bdef.id, cost))

        expand_cost = self.expansion_cost(civ, mods)
        if self._feasible(civ, expand_cost, mods):
            score = weights["expansion"] * needs["expansion"] / (1 + len(civ.territory) / 250)
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
                if site is None:
                    continue
                civ.goal = Goal("build", target, cost)
                if civ.can_afford(cost):
                    civ.pay(cost)
                    civ.buildings.append(Building(target, site))
                    civ.goal = None
            else:
                border = self._border(civ)
                if not border:
                    continue
                civ.goal = Goal("expand", None, cost)
                if civ.can_afford(cost):
                    civ.pay(cost)
                    self._expand(civ, border, needs)
                    civ.goal = None
            return

    def _building_need(self, bdef: BuildingDef, needs: dict) -> float:
        if bdef.need_resource:
            return needs["resource"][bdef.need_resource]
        return needs[bdef.category]

    def _feasible(self, civ: Civilization, cost: dict[str, float], mods: Modifiers) -> bool:
        """False if the civ could never pay: over storage, or a resource it cannot produce."""
        for res, amount in cost.items():
            if amount > mods.storage:
                return False
            producible = civ.capacity[res] > 0 or mods.income[res] > 0 or res == "gold"
            if civ.resources[res] < amount and not producible:
                return False
        return True

    # -- territory -----------------------------------------------------------

    def expansion_cost(self, civ: Civilization, mods: Modifiers) -> dict[str, float]:
        size = len(civ.territory)
        factor = max(0.3, 1 + mods.expand_cost)
        return {"food": round((15 + 0.4 * size) * factor), "wood": round((10 + 0.25 * size) * factor)}

    def _border(self, civ: Civilization) -> list[int]:
        """Unowned, claimable tiles next to the civ's territory."""
        world = self.world
        border = {
            n
            for tile in civ.territory
            for n in world.neighbors(tile)
            if world.owner[n] < 0 and world.biomes[n] != Biome.OCEAN
        }
        return sorted(border)

    def _expand(self, civ: Civilization, border: list[int], needs: dict) -> None:
        world = self.world
        cx, cy = world.xy(civ.capital.tile)

        def appeal(tile: int) -> float:
            x, y = world.xy(tile)
            value = sum(
                amount * (1 + needs["scarcity"][res] + (2 if res in needs["wanted"] else 0))
                for res, amount in world.yields[tile].items()
            )
            return value - 0.08 * math.hypot(x - cx, y - cy) + 0.3 * self.rng.random()

        # Head for a resource the territory lacks, then fill up with the most appealing tiles.
        picks: list[int] = []
        for res in needs["wanted"]:
            path = self._path_to_resource(border, res)
            if 0 < len(path) <= SEEK_RANGE:
                picks = path[:TILES_PER_EXPANSION]
                break
        ranked = sorted((tile for tile in border if tile not in picks), key=appeal, reverse=True)
        picks += ranked[: TILES_PER_EXPANSION - len(picks)]
        for tile in picks:
            world.claim(tile, civ.id)
            civ.territory.add(tile)
        recompute_capacity(civ, world)

    def _path_to_resource(self, border: list[int], resource: str) -> list[int]:
        """Shortest chain of claimable tiles from the border to the nearest tile yielding `resource`."""
        world = self.world
        parent: dict[int, int | None] = dict.fromkeys(border)
        queue = deque(border)
        while queue:
            tile = queue.popleft()
            if world.yields[tile].get(resource, 0) > 0:
                path = []
                step: int | None = tile
                while step is not None:
                    path.append(step)
                    step = parent[step]
                return path[::-1]
            for n in world.neighbors(tile):
                if n not in parent and world.owner[n] < 0 and world.biomes[n] != Biome.OCEAN:
                    parent[n] = tile
                    queue.append(n)
        return []

    # -- workers -------------------------------------------------------------

    def _allocate_workers(self, civ: Civilization, mods: Modifiers) -> None:
        # What the civ wants in stock: a reserve, plus whatever it is saving for.
        target = dict(MATERIAL_RESERVE)
        target["food"] = civ.population * FOOD_PER_POP * FOOD_RESERVE_TICKS
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
        remaining = civ.population

        # Food first: enough farmers to break even, more when the reserve is low.
        break_even = civ.population * FOOD_PER_POP / (WORK_RATE * (1 + mods.yield_mult["food"]))
        workers["food"] = min(break_even * (0.9 + 0.7 * urgency["food"]), civ.capacity["food"], remaining)
        remaining -= workers["food"]

        # Split the rest by weighted urgency, spilling over when a resource runs out of work slots.
        weights = civ.personality.weights
        active = {
            res: weights[CATEGORY_OF_RESOURCE[res]] * (0.1 + urgency[res])
            for res in MATERIALS
            if civ.capacity[res] > 0 and civ.resources[res] < mods.storage
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
        if remaining > 0 and civ.resources["food"] < mods.storage:
            extra = min(remaining, civ.capacity["food"] - workers["food"])
            workers["food"] += extra
            remaining -= extra

        civ.workers = workers
        civ.idle = max(0.0, remaining)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
