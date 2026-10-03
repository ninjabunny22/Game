"""The simulation: owns the world and the civs and advances them one tick at a time.

It knows nothing about wall-clock time, the network or language models. The driver
(the bridge server, the headless runner, a test) decides when to call step(), and
answers the strategic check-ins the sim emits: take_requests() hands them out,
submit() takes the answers back, and they are applied at the start of the next
tick. Given the same config and the same answers on the same ticks, a run is
deterministic.
"""

import math
import random

from .civ import CivAI, Civilization, Research, Settlement, assign_personalities
from .config import SimConfig
from .diplomacy import Diplomacy
from .economy import advance_construction, compute_modifiers, load_building_defs, produce, recompute_capacity
from .economy.rules import START_POPULATION, START_RESOURCES, START_TERRITORY_RADIUS
from .map import Biome, find_start_positions, generate_map
from .strategy import CHECKIN_INTERVAL, Brain, CheckinRequest, invention_context, parse_stances, stance_context
from .tech import InventionRules, TechTree, advance_research, build_invented_tech

# (civ name, capital name)
CIV_NAMES = [
    ("Aurelia", "Solmere"), ("Kheshet", "Ankara-Tel"), ("Norvald", "Hrafnby"), ("Zhanlu", "Baiyun"),
    ("Tamari", "Oshiro"), ("Ossyria", "Calden"), ("Valmere", "Port Liss"), ("Iskandar", "Samara"),
]
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
        self.invention_rules = InventionRules.load()
        self.modifiers = {
            civ.id: compute_modifiers(civ, self.building_defs, self.tech_tree) for civ in self.civs
        }
        self.diplomacy = Diplomacy(self.world, self.civs, self.modifiers, self.building_defs)
        self.events: list[dict] = []  # what happened during the latest tick
        self._outbox: list[CheckinRequest] = []
        self._inbox: list[tuple[CheckinRequest, dict | None]] = []
        self._awaiting: set[tuple[str, int]] = set()  # (kind, civ id) of unanswered check-ins

    def step(self) -> list[dict]:
        self.tick += 1
        events: list[dict] = []
        self._apply_answers(events)
        # Rotate who acts first so no civ always wins the race for a contested tile.
        for offset in range(len(self.civs)):
            civ = self.civs[(self.tick + offset) % len(self.civs)]
            mods = compute_modifiers(civ, self.building_defs, self.tech_tree)
            self.diplomacy.apply_modifiers(civ, mods)
            self.modifiers[civ.id] = mods
            self.ai.plan(civ, mods, self.tick, events)
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
            self._raise("stance", civ, stance_context)
            exhausted = not self.tech_tree.available(civ.known_techs, civ.id)
            if exhausted and civ.research is None:
                self._raise("invent", civ, invention_context)

    def _raise(self, kind: str, civ: Civilization, build_context) -> None:
        if (kind, civ.id) in self._awaiting:
            return  # the previous one is still unanswered; don't pile up
        self._awaiting.add((kind, civ.id))
        civ.thinking = True
        self._outbox.append(CheckinRequest(civ.id, self.tick, kind, build_context(self, civ)))

    def _apply_answers(self, events: list[dict]) -> None:
        answers, self._inbox = self._inbox, []
        for request, reply in answers:
            civ = self.civs[request.civ_id]
            self._awaiting.discard((request.kind, civ.id))
            civ.thinking = any(civ_id == civ.id for _, civ_id in self._awaiting)
            if reply is None:
                continue  # no answer: previous stances stand, invention waits for the next check-in
            if request.kind == "stance":
                intents, reason = parse_stances(reply, request.context, self.tick)
                self.diplomacy.set_intents(civ.id, intents)
                civ.last_reason = reason
            elif civ.research is None:
                tech = build_invented_tech(reply, civ, self.tech_tree, self.invention_rules,
                                           self.modifiers[civ.id].storage)
                if tech:
                    self.tech_tree.add_invented(tech, self.invention_rules.era_name)
                    civ.research = Research(tech.id)
                    events.append({"civ": civ.id, "kind": "tech",
                                   "text": f"{civ.name}'s scholars begin work on {tech.name}"})

    def _create_civs(self) -> list[Civilization]:
        count = self.config.num_civs
        if count > len(CIV_NAMES):
            raise ValueError(f"at most {len(CIV_NAMES)} civilizations are supported")
        world = self.world
        starts = find_start_positions(world, count, self.rng)
        names = self.rng.sample(CIV_NAMES, count)
        personalities = assign_personalities(count, self.rng)

        civs = []
        for civ_id, start in enumerate(starts):
            civ_name, capital_name = names[civ_id]
            civ = Civilization(
                id=civ_id,
                name=civ_name,
                color=CIV_COLORS[civ_id],
                personality=personalities[civ_id],
                population=START_POPULATION,
                resources=dict(START_RESOURCES),
                settlements=[Settlement(capital_name, start)],
            )
            civs.append(civ)

        for civ in civs:
            sx, sy = world.xy(civ.capital.tile)
            reach = math.ceil(START_TERRITORY_RADIUS)
            for dy in range(-reach, reach + 1):
                for dx in range(-reach, reach + 1):
                    x, y = sx + dx, sy + dy
                    if not world.in_bounds(x, y) or math.hypot(dx, dy) > START_TERRITORY_RADIUS:
                        continue
                    tile = world.idx(x, y)
                    if world.owner[tile] < 0 and world.biomes[tile] != Biome.OCEAN:
                        world.claim(tile, civ.id)
                        civ.territory.add(tile)
            recompute_capacity(civ, world)
        return civs
