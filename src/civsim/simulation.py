"""The simulation: owns the world and the civs and advances them one tick at a time.

It knows nothing about wall-clock time, the network or language models. The driver
(the bridge server, the headless runner, a test) decides when to call step(), and
answers the strategic check-ins the sim emits: take_requests() hands them out,
submit() takes the answers back, and they are applied at the start of the next
tick. Given the same config and the same answers on the same ticks, a run is
deterministic.
"""

import itertools
import random

from .civ import CivAI, Civilization, Settlement, assign_personalities
from .config import SimConfig
from .diplomacy import Diplomacy, Natives
from .economy import (
    advance_construction,
    compute_modifiers,
    load_building_defs,
    manage_villagers,
    produce,
    recompute_capacity,
)
from .economy.rules import START_POPULATION, START_RESOURCES
from .map import generate_map, region_neighbours
from .military.warfare import Military
from .strategy import CHECKIN_INTERVAL, Brain, CheckinRequest, parse_stances, stance_context
from .tech import TechTree, advance_research

CIV_NAMES = ["Aurelia", "Kheshet", "Norvald", "Zhanlu", "Tamari", "Ossyria", "Valmere", "Iskandar"]
CIV_COLORS = ["#d9433b", "#3b7dd9", "#e8c33a", "#a04fd6", "#3bbf9a", "#e07b2e", "#e86fb0", "#f0f0f0"]


class Simulation:
    def __init__(self, config: SimConfig):
        self.config = config
        self.tick = 0
        self.rng = random.Random(config.seed)
        self.building_defs = load_building_defs()
        self.tech_tree = TechTree.load()
        self.world = generate_map(config.seed, config.width, config.height)
        self.civs = self._create_civs()
        self.ai = CivAI(self.world, self.building_defs, self.tech_tree, self.rng)
        self.modifiers = {
            civ.id: compute_modifiers(civ, self.building_defs, self.tech_tree) for civ in self.civs
        }
        for civ in self.civs:  # everyone starts with full water stores
            civ.resources["water"] = self.modifiers[civ.id].storage["water"]
        self.diplomacy = Diplomacy(self.world, self.civs, self.modifiers, self.building_defs)
        self._ids = itertools.count(1)  # ids for armies and villagers
        self.military = Military(self.world, self.civs, self.modifiers, self.diplomacy, self.rng,
                                 lambda: next(self._ids))
        self.diplomacy.military = self.military
        self.natives = Natives(self.world, self.civs, self.diplomacy, self.rng)
        self.diplomacy.natives = self.natives
        for civ in self.civs:
            manage_villagers(civ, self.world, self.modifiers[civ.id], lambda: next(self._ids))
        self.events: list[dict] = []  # what happened during the latest tick
        self._outbox: list[CheckinRequest] = []
        self._inbox: list[tuple[CheckinRequest, dict | None]] = []
        self._awaiting: set[int] = set()  # civs whose check-in is still unanswered

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
            self.diplomacy.apply_modifiers(civ, mods)
            self.modifiers[civ.id] = mods
            self.ai.plan(civ, mods, self.tick, events)
            manage_villagers(civ, self.world, mods, lambda: next(self._ids))
            produce(civ, mods, self.building_defs)
            advance_construction(civ, mods, self.building_defs, events)
            advance_research(civ, self.tech_tree, events)
        self.diplomacy.update(self.tick, events)
        self._schedule_checkins()
        self.events = events
        return events

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

    def _schedule_checkins(self) -> None:
        """Every civ checks in once per interval; they are staggered so the calls don't arrive at once."""
        spacing = CHECKIN_INTERVAL // len(self.civs)
        for civ in self.civs:
            if (self.tick - civ.id * spacing) % CHECKIN_INTERVAL != 0:
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
            self.diplomacy.set_intents(civ.id, intents)
            civ.last_reason = reason

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
        homes = self._pick_home_regions(count)
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

        for civ, home in zip(civs, homes):
            # The second region: one that touches home if any is free, else the nearest free one.
            free = sorted(r for r in touching[home.id] if r not in taken)
            if free:
                second = world.regions[self.rng.choice(free)]
            else:
                second = min((r for r in world.regions if r.id not in taken),
                             key=lambda r: (self._capital_distance(home, r), r.id))
            taken.add(second.id)
            civ.settlements.append(Settlement(second.capital_name, second.capital))
            for region in (home, second):
                region.owner = civ.id
                for tile in region.tiles:
                    world.claim(tile, civ.id)
                    civ.territory.add(tile)
            civ.base_territory = len(civ.territory)
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
