"""The simulation: owns the world and the civs and advances them one tick at a time.

It knows nothing about wall-clock time, the network or who plays the civs. The driver
(the bridge server, the headless runner, a test) decides when to call step(), and
answers the strategic check-ins the sim emits: take_requests() hands them out,
submit() takes the answers back, and they are applied at the start of the next
tick. Given the same config and the same answers on the same ticks, a run is
deterministic.
"""

import itertools
import math
import random

from .civ import FOCUSES, CivAI, Civilization, Settlement, Villages, assign_personalities, with_focus
from .config import SimConfig
from .diplomacy import Diplomacy, Natives
from .economy import (
    advance_construction,
    compute_modifiers,
    load_building_defs,
    manage_villagers,
    produce,
    tend_horses,
    recompute_capacity,
)
from .economy.rules import MINE_GOLD, START_POPULATION, START_RESOURCES
from .map import generate_map, region_neighbours
from .map.saved import load_map
from .military.warfare import Military
from .ruler import Ruler
from .strategy.geography import Geography
from .strategy import CHECKIN_INTERVAL, Brain, CheckinRequest, parse_stances, stance_context
from .tech import TechTree, advance_research

EASY_INTERVAL = 10  # days between the other civs' decisions on the easy setting
# Domination: holding this share of the map's region points (1 to 3 a region: what it is
# worth) and at least DOMINATION_REGIONS of its regions wins the game.
DOMINATION_SHARE = 0.8
DOMINATION_REGIONS = 0.5
SCORE_PER_POINT = 60
SCORE_PER_TECH = 20

CIV_NAMES = ["Aurelia", "Kheshet", "Norvald", "Zhanlu", "Tamari", "Ossyria", "Valmere", "Iskandar"]
CIV_COLORS = ["#d9433b", "#3b7dd9", "#e8c33a", "#a04fd6", "#3bbf9a", "#e07b2e", "#e86fb0", "#f0f0f0"]


class Simulation:
    def __init__(self, config: SimConfig):
        self.config = config
        self.tick = 0
        self.rng = random.Random(config.seed)
        self.building_defs = load_building_defs()
        self.tech_tree = TechTree.load()
        if config.map_file:
            self.world = load_map(config.map_file)
        else:
            self.world = generate_map(config.seed if config.map_seed is None else config.map_seed,
                                      config.width, config.height)
        self.civs = self._create_civs()
        self.world.civs = self.civs  # placement rules look across borders
        self.ai = CivAI(self.world, self.building_defs, self.tech_tree, self.rng)
        self.modifiers = {
            civ.id: compute_modifiers(civ, self.building_defs, self.tech_tree) for civ in self.civs
        }
        for civ in self.civs:  # everyone starts with full water stores
            civ.resources["water"] = self.modifiers[civ.id].storage["water"]
        self.diplomacy = Diplomacy(self.world, self.civs, self.modifiers, self.building_defs,
                                   random.Random(self.config.seed + 7919))
        self._ids = itertools.count(1)  # ids for armies and villagers
        self.military = Military(self.world, self.civs, self.modifiers, self.diplomacy, self.rng,
                                 lambda: next(self._ids))
        self.diplomacy.military = self.military
        self.natives = Natives(self.world, self.civs, self.diplomacy, self.rng)
        self.villages = Villages(self.world, self.civs, lambda: next(self._ids), self.config.seed)
        self.villages.update(0, [])  # the towns around the starting capitals
        self.diplomacy.natives = self.natives
        # What each region is worth to each civ: one valuation for campaigns, war
        # targets, harbours and the strategist.
        self.geography = Geography(self.world, self.civs, self.diplomacy, self.military)
        self.ai.geography = self.military.geography = self.geography
        for civ in self.civs:
            manage_villagers(civ, self.world, self.modifiers[civ.id], lambda: next(self._ids))
        self.events: list[dict] = []  # what happened during the latest tick
        self._outbox: list[CheckinRequest] = []
        self._inbox: list[tuple[CheckinRequest, dict | None]] = []
        self._awaiting: set[int] = set()  # civs whose check-in is still unanswered
        self.ruler = Ruler(self)  # a human player's hand on one civ, if any
        self.victory: dict | None = None  # {"civ", "kind", "tick"} once the game is decided; play goes on

    def step(self) -> list[dict]:
        self.tick += 1
        events: list[dict] = []
        self._apply_answers(events)
        # Rotate who acts first so no civ always wins the race for a contested tile.
        for offset in range(len(self.civs)):
            civ = self.civs[(self.tick + offset) % len(self.civs)]
            if not civ.alive:
                continue
            mods = compute_modifiers(civ, self.building_defs, self.tech_tree)
            if "mining" in civ.known_techs:  # a mine is only worked by a civ that knows how
                mods.income["gold"] += MINE_GOLD * self.mines_held(civ)
            self.diplomacy.apply_modifiers(civ, mods)
            self.modifiers[civ.id] = mods
            self.ai.plan(civ, mods, self.tick, events)
            manage_villagers(civ, self.world, mods, lambda: next(self._ids))
            tend_horses(civ)
            produce(civ, mods, self.building_defs, self.tick)
            advance_construction(civ, mods, self.building_defs, events)
            advance_research(civ, self.tech_tree, events)
        self.diplomacy.update(self.tick, events)
        self.villages.update(self.tick, events)
        events.extend(self.ruler.notices())
        self._check_victory(events)
        self._schedule_checkins()
        self.events = events
        return events

    def mines_held(self, civ) -> int:
        """Gold mines in the regions the civ holds: each pays it MINE_GOLD a day."""
        world = self.world
        return sum(1 for tile in world.mines if world.region_of[tile] >= 0
                   and world.regions[world.region_of[tile]].owner == civ.id)

    # -- winning ---------------------------------------------------------------

    def points_held(self, civ) -> int:
        """The region points of the regions the civ holds."""
        return sum(region.points for region in self.world.regions if region.owner == civ.id)

    def domination_target(self) -> tuple[int, int]:
        """What domination takes: (points, regions)."""
        total = sum(region.points for region in self.world.regions)
        return math.ceil(DOMINATION_SHARE * total - 1e-9), math.ceil(DOMINATION_REGIONS * len(self.world.regions) - 1e-9)

    def score(self, civ) -> int:
        """How a civ stands: the points of its regions first, then its people and what it has learned."""
        if not civ.alive:
            return 0
        return round(SCORE_PER_POINT * self.points_held(civ) + civ.population + SCORE_PER_TECH * len(civ.known_techs))

    def _check_victory(self, events: list[dict]) -> None:
        """The game is won by the last civ standing, by whoever holds most of the map, or on the
        last day by the highest score. It is decided once; the world carries on afterwards."""
        if self.victory is not None:
            return
        living = [civ for civ in self.civs if civ.alive]
        if not living:
            return
        winner, kind = None, ""
        points = {civ.id: self.points_held(civ) for civ in living}
        regions = {civ.id: sum(1 for r in self.world.regions if r.owner == civ.id) for civ in living}
        leader = max(living, key=lambda civ: (points[civ.id], regions[civ.id], civ.id))
        need_points, need_regions = self.domination_target()
        if len(living) == 1 and len(self.civs) > 1:
            winner, kind = living[0], "conquest"
        elif points[leader.id] >= need_points and regions[leader.id] >= need_regions:
            winner, kind = leader, "domination"
        elif self.config.end_tick and self.tick >= self.config.end_tick and self.diplomacy.wars_started:
            # A game in which nobody has yet fought is not over: the age runs on until someone does.
            winner, kind = max(living, key=lambda civ: (self.score(civ), -civ.id)), "score"
        if winner is None:
            return
        self.victory = {"civ": winner.id, "kind": kind, "tick": self.tick}
        how = {"conquest": "is the last civ standing", "domination": "holds most of the known world",
               "score": "stands highest when the age ends"}[kind]
        events.append({"civ": winner.id, "kind": "era", "text": f"{winner.name} {how}: victory"})

    # -- strategic check-ins -------------------------------------------------

    def take_requests(self) -> list[CheckinRequest]:
        """Check-ins raised since the last call. The caller must answer each with submit()."""
        requests, self._outbox = self._outbox, []
        return requests

    def submit(self, request: CheckinRequest, reply: dict | None) -> None:
        """Hand back a brain's answer (None if it had none). Applied at the start of the next tick."""
        self._inbox.append((request, reply))

    def step_with(self, brain: Brain) -> list[dict]:
        """One tick, answering any check-ins it raises on the spot. For headless runs and tests."""
        events = self.step()
        for request in self.take_requests():
            self.submit(request, brain.decide(request))
        return events

    def waiting_for(self) -> list[int]:
        """Civs whose next check-in falls on the coming tick while their last is still unanswered.

        The clock must not move until they answer, or that civ would miss a decision.
        """
        interval = self.checkin_interval()
        spacing = interval // len(self.civs)
        answered = {request.civ_id for request, _ in self._inbox}
        return [civ.id for civ in self.civs
                if civ.alive and civ.id in self._awaiting and civ.id not in answered
                and (self.tick + 1 - civ.id * spacing) % interval == 0]

    def checkin_interval(self) -> int:
        """How often the civs reconsider: every day, or every ten on the easy setting while a
        human rules one of them."""
        return EASY_INTERVAL if self.config.difficulty == "easy" and self.ruler.civ_id is not None else CHECKIN_INTERVAL

    def _schedule_checkins(self) -> None:
        """Every civ checks in once per interval; they are staggered so the calls don't arrive at once."""
        interval = self.checkin_interval()
        spacing = interval // len(self.civs)
        for civ in self.civs:
            if (self.tick - civ.id * spacing) % interval != 0:
                continue
            if civ.id in self._awaiting or not civ.alive:
                continue  # the previous one is still unanswered (don't pile up), or the civ is gone
            self._awaiting.add(civ.id)
            civ.thinking = True
            self._outbox.append(CheckinRequest(civ.id, self.tick, stance_context(self, civ)))

    def _apply_answers(self, events: list[dict]) -> None:
        answers, self._inbox = self._inbox, []
        for request, reply in answers:
            civ = self.civs[request.civ_id]
            self._awaiting.discard(civ.id)
            civ.thinking = False
            if reply is None:
                continue  # no answer: previous stances stand
            intents, reason = parse_stances(reply, request.context, self.tick)
            self._adopt_strategy(civ, reply.get("strategy"), request.context)
            self._adopt_plan(civ, reply.get("plan"), request.context)
            self.diplomacy.set_intents(civ.id, self.ruler.overrule(civ.id, request.context, intents))
            civ.last_reason = reason

    def _adopt_plan(self, civ, plan: object, context: dict) -> None:
        """Remember the war a strategist says it is preparing, so it can be seen and stuck to."""
        names = {n["name"]: n["id"] for n in context["neighbors"]}
        target = names.get(plan.get("target")) if isinstance(plan, dict) else None
        if target is None:
            civ.plan_target, civ.plan = None, ""
            return
        if target != civ.plan_target:
            civ.plan_target, civ.plan_since = target, self.tick
        civ.plan = " ".join(str(plan.get("text") or "").split())[:120]

    def _adopt_strategy(self, civ, strategy: object, context: dict) -> None:
        """Take up the long-term strategy a strategist has settled on, if it sent a usable one.
        A civ in a human ruler's hands keeps the ruler's focus; the rest still applies."""
        if not isinstance(strategy, dict) or not isinstance(strategy.get("kind"), str):
            return
        names = {n["name"]: n["id"] for n in context["neighbors"]}
        if strategy["kind"][:40] != civ.strategy_kind:
            civ.strategy_since = self.tick
        civ.strategy_kind = strategy["kind"][:40]
        civ.strategy_target = names.get(strategy.get("target"))
        civ.strategy = " ".join(str(strategy.get("text") or "").split())[:120]
        focus = strategy.get("focus")
        if focus in FOCUSES and self.ruler.civ_id != civ.id and focus != civ.focus:
            civ.born = civ.born or civ.personality
            civ.focus = focus
            civ.personality = with_focus(civ.born, focus)

    def _create_civs(self) -> list[Civilization]:
        """Each civ starts holding two whole regions: a home region, whose capital is its
        own, and one next to it. Every other region stays with the native faction."""
        count = self.config.num_civs
        if count > len(CIV_NAMES):
            raise ValueError(f"at most {len(CIV_NAMES)} civilizations are supported")
        world = self.world
        if len(world.regions) < 2 * count:
            raise ValueError("map has too few regions for the requested number of civilizations")
        names = self.rng.sample(CIV_NAMES, count)
        personalities = assign_personalities(count, self.rng)
        if world.start_sets:
            # A drawn map: the slots it sets out for this many civs, each civ given one at random.
            if count not in world.start_sets:
                raise ValueError(f"this map takes {min(world.start_sets)} to {max(world.start_sets)} civilizations")
            options = world.start_sets[count]
            slots = list(options[self.rng.randrange(len(options))] if len(options) > 1 else options[0])
            self.rng.shuffle(slots)
            homes = [world.regions[world.starts[slot][0]] for slot in slots]
            seconds = [world.regions[world.starts[slot][1]] for slot in slots]
        else:
            homes = self._pick_home_regions(count)
            seconds = None
        touching = region_neighbours(world)
        taken = {region.id for region in homes}

        civs = []
        for civ_id, home in enumerate(homes):
            civ = Civilization(
                id=civ_id,
                name=names[civ_id],
                color=CIV_COLORS[civ_id],
                personality=personalities[civ_id],
                population=START_POPULATION,
                resources=dict(START_RESOURCES),
                settlements=[Settlement(home.capital_name, home.capital)],
            )
            civs.append(civ)

        for k, (civ, home) in enumerate(zip(civs, homes)):
            # The second region: the slot's own on a drawn map; else one that touches home if
            # any is free, else the nearest free one.
            free = sorted(r for r in touching[home.id] if r not in taken)
            if seconds is not None:
                second = seconds[k]
            elif free:
                second = world.regions[self.rng.choice(free)]
            else:
                second = min((r for r in world.regions if r.id not in taken),
                             key=lambda r: (self._capital_distance(home, r), r.id))
            taken.add(second.id)
            civ.settlements.append(Settlement(second.capital_name, second.capital))
            civ.home_region = home.id
            for region in (home, second):
                region.owner = civ.id
                for tile in region.tiles:
                    world.claim(tile, civ.id)
                    civ.territory.add(tile)
            recompute_capacity(civ, world)
        return civs

    def _pick_home_regions(self, count: int) -> list:
        """Home regions chosen at random but far apart, so no civ starts on top of another."""
        regions = self.world.regions
        homes = [self.rng.choice(regions)]
        while len(homes) < count:
            homes.append(max(
                (r for r in regions if r not in homes),
                key=lambda r: (min(self._capital_distance(r, h) for h in homes) + 3 * self.rng.random(), r.id)))
        self.rng.shuffle(homes)
        return homes

    def _capital_distance(self, a, b) -> int:
        ax, ay = self.world.xy(a.capital)
        bx, by = self.world.xy(b.capital)
        return abs(ax - bx) + abs(ay - by)
