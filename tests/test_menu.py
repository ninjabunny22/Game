"""Starting games from the main menu: the three maps, how many civs each takes, and the lobby."""

import asyncio
import json

import pytest
from websockets.asyncio.client import connect

from civsim.bridge import SimServer, protocol
from civsim.config import MAP_SIZES, MAPS, MAX_CIVS, civ_range, game_config
from civsim.simulation import Simulation
from civsim.strategy import make_brain


def test_three_maps_each_with_a_recommended_number_of_civs():
    assert list(MAP_SIZES) == ["small", "medium", "large"]
    for size, spec in MAP_SIZES.items():
        assert 2 <= spec["min_civs"] <= spec["civs"] <= spec["max_civs"] <= MAX_CIVS == 5
        for entry in MAPS[size]:
            fewest, most = civ_range(size, entry)
            assert spec["min_civs"] <= fewest <= most <= spec["max_civs"]
            config = game_config(size, map=entry["id"])
            assert fewest <= config.num_civs <= most
            if entry.get("file"):
                assert (config.width, config.height) == (entry["width"], entry["height"])
            else:
                assert (config.width, config.height) == (spec["side"], spec["side"])


@pytest.mark.parametrize("size", list(MAP_SIZES))
def test_every_map_plays_with_its_fewest_and_its_most_civs(size):
    for entry in MAPS[size]:
        for civs in civ_range(size, entry):
            sim = Simulation(game_config(size, civs, seed=11, map=entry["id"]))
            brain = make_brain("utility")
            for _ in range(60):
                sim.step_with(brain)
            assert len(sim.civs) == civs and all(civ.alive for civ in sim.civs)
            assert len(sim.world.regions) > 2 * civs, "room left unclaimed at the start"


def test_a_random_map_takes_the_civs_asked_for():
    for seed in range(6):
        config = game_config("random", 5, seed=seed)
        assert config.num_civs == 5 and config.map_name
        assert game_config("small", 4, seed=seed, map="random").num_civs == 4


@pytest.mark.parametrize("size, civs", [("huge", 4), ("small", 5), ("medium", 6), ("large", 1), ("medium", True)])
def test_a_map_or_a_number_of_civs_that_does_not_exist_is_refused(size, civs):
    with pytest.raises(ValueError):
        game_config(size, civs)


def test_the_menu_starts_a_game_and_leaving_it_returns_to_the_menu():
    async def scenario():
        server = SimServer(Simulation(game_config("small", seed=1)), make_brain("utility"), port=0,
                           tick_rate=60.0, lobby=True)
        task = asyncio.create_task(server.run())
        await server.ready.wait()

        async def next_init(ws):
            while True:
                message = json.loads(await ws.recv())
                if message["type"] == "init":
                    return message["data"]

        def command(action, value=None):
            return json.dumps({"type": "command", "version": protocol.PROTOCOL_VERSION,
                               "data": {"action": action, "value": value}})

        async with connect(f"ws://127.0.0.1:{server.port}", max_size=None) as ws:
            first = await next_init(ws)
            assert [size["id"] for size in first["lobby"]["sizes"]] == ["small", "medium", "large"]
            await ws.send(command("new_game", {"size": "small", "civs": 9}))  # refused: nothing changes
            await ws.send(command("new_game", {"size": ["small"], "civs": 9}))  # malformed: refused, still connected
            await ws.send(command("new_game", {"size": "large", "civs": 5, "seed": 7, "mode": "rule"}))
            game = await next_init(ws)
            assert game["lobby"] is None and game["seed"] == 7
            chosen = next(m for m in MAPS["large"] if m["name"] == game["map_name"])
            assert (game["map"]["width"], len(game["civs"])) == (chosen["width"], 5)
            assert server.paused, "a game to be ruled waits for the player to choose a civ"
            await ws.send(command("take_control", {"civ": 2}))
            await ws.send(command("resume"))
            await ws.send(command("end_game"))
            back = await next_init(ws)
            assert back["lobby"] is not None and not server.paused
            assert server.sim.ruler.state() is None
        task.cancel()

    asyncio.run(scenario())


def test_a_map_can_take_only_some_numbers_of_civs():
    with pytest.raises(ValueError, match="2 or 4"):
        game_config("small", 3, map="highgate")
    assert game_config("small", 4, map="highgate").num_civs == 4
    for seed in range(6):  # a random small map for three civs is never one that refuses them
        assert game_config("small", 3, seed=seed, map="random").map_name != "Highgate"
