"""The game is played on a few chosen maps: the same map every time it is picked, with only
the civs and where they start differing from game to game."""

import json

import pytest

from civsim.bridge import protocol
from civsim.config import MAP_SIZES, MAPS, SimConfig, game_config
from civsim.simulation import Simulation


def test_every_size_has_three_maps_of_its_own():
    assert set(MAPS) == set(MAP_SIZES)
    for size, pool in MAPS.items():
        assert len(pool) == 3
        assert len({m["id"] for m in pool}) == 3
        seeds = [m["seed"] for m in pool if "seed" in m]
        assert len(set(seeds)) == len(seeds)
    ids = [m["id"] for pool in MAPS.values() for m in pool]
    assert len(set(ids)) == len(ids)


def test_a_named_map_is_the_same_land_whatever_the_games_seed():
    one = Simulation(game_config("medium", seed=1, map="emberwaste"))
    two = Simulation(game_config("medium", seed=2, map="emberwaste"))
    assert one.config.map_name == "Emberwaste"
    assert one.world.biomes == two.world.biomes and one.world.rivers == two.world.rivers
    assert [r.capital for r in one.world.regions] == [r.capital for r in two.world.regions]
    starts = lambda sim: [civ.capital.tile for civ in sim.civs]  # noqa: E731
    assert any(starts(Simulation(game_config("medium", seed=s, map="emberwaste"))) != starts(one) for s in range(2, 8)), \
        "but the civs start somewhere else"


def test_with_no_map_named_the_seed_picks_one_of_the_sizes_three():
    seen = {game_config("medium", seed=s).map_name for s in range(12)}
    assert seen == {m["name"] for m in MAPS["medium"]}
    with pytest.raises(ValueError):
        game_config("medium", map="highgate")  # a small map
    assert SimConfig(seed=5).map_seed is None, "a plain config still makes its map from its own seed"


def test_the_menu_is_told_the_maps_and_the_viewer_the_name():
    sim = Simulation(game_config("small", seed=3, map="highgate"))
    data = json.loads(protocol.init_message(sim, lobby=True))["data"]
    assert data["map_name"] == "Highgate"
    for size in data["lobby"]["sizes"]:
        assert [m["id"] for m in size["maps"]] == [m["id"] for m in MAPS[size["id"]]]
