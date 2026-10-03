import base64
import random

import pytest

from civsim.map import BIOME_INFO, DEPOSIT_TYPES, Biome, find_start_positions, generate_map


def test_same_seed_gives_same_map():
    a, b = generate_map(11), generate_map(11)
    assert a.heights == b.heights
    assert a.biomes == b.biomes
    assert a.deposits == b.deposits


def test_different_seeds_differ():
    assert generate_map(1).biomes != generate_map(2).biomes


def test_map_has_every_biome_and_matching_heights():
    world = generate_map(5)
    assert set(world.biomes) == set(Biome)
    for i, biome in enumerate(world.biomes):
        if BIOME_INFO[biome].water:
            assert world.heights[i] <= 0
        else:
            assert 0 < world.heights[i] <= 1


def test_deposits_sit_on_allowed_biomes_and_form_clusters():
    world = generate_map(5)
    assert set(world.deposits.values()) == set(DEPOSIT_TYPES)
    touching = 0
    for tile, type_id in world.deposits.items():
        assert world.biomes[tile] in DEPOSIT_TYPES[type_id].biomes
        if any(world.deposits.get(n) == type_id for n in world.neighbors(tile, diagonal=True)):
            touching += 1
    # Scattered at random almost no deposit would touch another of its kind.
    assert touching / len(world.deposits) > 0.8


def test_start_positions_are_on_land_and_spread_out():
    world = generate_map(5)
    starts = find_start_positions(world, 4, random.Random(5))
    assert len(set(starts)) == 4
    for tile in starts:
        assert BIOME_INFO[world.biomes[tile]].buildable
    points = [world.xy(t) for t in starts]
    for i, (ax, ay) in enumerate(points):
        for bx, by in points[i + 1:]:
            assert abs(ax - bx) + abs(ay - by) >= 15


def test_territory_encoding_is_one_byte_per_tile_for_any_civ_id():
    world = generate_map(5, 16, 16)
    world.claim(0, 3)
    world.claim(1, 12)
    world.claim(2, 254)
    owners = base64.b64decode(world.encode_territory())
    assert len(owners) == 16 * 16
    assert list(owners[:4]) == [3, 12, 254, 255]
    with pytest.raises(ValueError):
        world.claim(3, 255)
