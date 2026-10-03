"""Procedural terrain: simplex-noise elevation, moisture and temperature -> biomes."""

import math
import random

from opensimplex import OpenSimplex

from .biomes import Biome
from .resources import compute_yields, place_deposits
from .world import WorldMap

WATER_FRACTION = 0.42
HILLS_QUANTILE = 0.76  # of land tiles, by elevation
MOUNTAIN_QUANTILE = 0.91


def generate_map(seed: int, width: int = 96, height: int = 96) -> WorldMap:
    world = WorldMap(width, height, seed)
    rng = random.Random(seed)
    size = width * height

    elevation = _noise_field(seed, width, height, frequency=3.0, octaves=5)
    moisture = _noise_field(seed + 1, width, height, frequency=4.0, octaves=4)
    temp_noise = _noise_field(seed + 2, width, height, frequency=2.5, octaves=3)

    # Pull the map edges down so land gathers into continents surrounded by sea.
    for i in range(size):
        x, y = world.xy(i)
        dx = 2 * x / (width - 1) - 1
        dy = 2 * y / (height - 1) - 1
        edge = max(abs(dx), abs(dy))
        elevation[i] -= 0.55 * edge**2.4

    sea_level = _quantile(elevation, WATER_FRACTION)
    land = [e for e in elevation if e > sea_level]
    hills_level = _quantile(land, HILLS_QUANTILE)
    mountain_level = _quantile(land, MOUNTAIN_QUANTILE)
    highest, lowest = max(elevation), min(elevation)

    for i in range(size):
        e = elevation[i]
        if e <= sea_level:
            world.biomes[i] = Biome.OCEAN
            world.heights[i] = round(-0.5 * (sea_level - e) / (sea_level - lowest), 3)
            continue
        land_height = (e - sea_level) / (highest - sea_level)
        world.heights[i] = round(0.02 + 0.98 * land_height**1.3, 3)
        # Cold north, hot south, colder with altitude.
        latitude = (i // width) / (height - 1)
        temperature = latitude + 0.5 * (temp_noise[i] - 0.5) - 0.3 * land_height
        if e >= mountain_level:
            world.biomes[i] = Biome.MOUNTAIN
        elif e >= hills_level:
            world.biomes[i] = Biome.HILLS
        elif temperature < 0.2:
            world.biomes[i] = Biome.TUNDRA
        elif temperature > 0.6 and moisture[i] < 0.42:
            world.biomes[i] = Biome.DESERT
        elif moisture[i] > 0.52:
            world.biomes[i] = Biome.FOREST
        else:
            world.biomes[i] = Biome.PLAINS

    # Water touching land becomes shallows.
    for i in range(size):
        if world.biomes[i] == Biome.OCEAN and any(
            world.biomes[n] not in (Biome.OCEAN, Biome.SHALLOWS) for n in world.neighbors(i, diagonal=True)
        ):
            world.biomes[i] = Biome.SHALLOWS
            world.heights[i] = max(world.heights[i], -0.06)

    place_deposits(world, rng)
    compute_yields(world)
    return world


def _noise_field(seed: int, width: int, height: int, frequency: float, octaves: int) -> list[float]:
    """Fractal simplex noise over the map, normalised to [0, 1]."""
    noise = OpenSimplex(seed)
    values = []
    for y in range(height):
        for x in range(width):
            nx, ny = x / width * frequency, y / height * frequency
            total, amplitude, scale = 0.0, 1.0, 1.0
            for _ in range(octaves):
                total += amplitude * noise.noise2(nx * scale, ny * scale)
                amplitude *= 0.5
                scale *= 2.0
            values.append(total)
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    return [(v - low) / span for v in values]


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.floor(q * len(ordered)))]
