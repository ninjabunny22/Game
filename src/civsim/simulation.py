"""The simulation: owns the world and the civs and advances them one tick at a time.

Deterministic for a given SimConfig; it knows nothing about wall-clock time or the
network. The bridge decides when to call step().
"""

import math
import random

from .civ import CivAI, Civilization, Settlement, assign_personalities
from .config import SimConfig
from .economy import advance_construction, compute_modifiers, load_building_defs, produce, recompute_capacity
from .economy.rules import START_POPULATION, START_RESOURCES, START_TERRITORY_RADIUS
from .map import Biome, find_start_positions, generate_map
from .tech import TechTree, advance_research

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
        self.modifiers = {
            civ.id: compute_modifiers(civ, self.building_defs, self.tech_tree) for civ in self.civs
        }
        self.events: list[dict] = []  # what happened during the latest tick

    def step(self) -> list[dict]:
        self.tick += 1
        events: list[dict] = []
        # Rotate who acts first so no civ always wins the race for a contested tile.
        for offset in range(len(self.civs)):
            civ = self.civs[(self.tick + offset) % len(self.civs)]
            mods = compute_modifiers(civ, self.building_defs, self.tech_tree)
            self.modifiers[civ.id] = mods
            self.ai.plan(civ, mods, self.tick, events)
            produce(civ, mods)
            advance_construction(civ, mods, self.building_defs, events)
            advance_research(civ, self.tech_tree, events)
        self.events = events
        return events

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
