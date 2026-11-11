"""Starting games from the main menu: the three maps, how many civs each takes, and the lobby."""

import asyncio
import json

import pytest
from websockets.asyncio.client import connect

from civsim.bridge import SimServer, protocol
from civsim.config import MAP_SIZES, MAX_CIVS, game_config
from civsim.simulation import Simulation
from civsim.strategy import make_brain


def test_three_maps_each_with_a_recommended_number_of_civs():
    assert list(MAP_SIZES) == ["small", "medium", "large"]
    sides = [spec["side"] for spec in MAP_SIZES.values()]
    assert sides == sorted(sides) == [64, 96, 128]
    for size, spec in MAP_SIZES.items():
        assert 2 <= spec["min_civs"] <= spec["civs"] <= spec["max_civs"] <= MAX_CIVS == 5
        config = game_config(size)
        assert (config.width, config.height, config.num_civs) == (spec["side"], spec["side"], spec["civs"])


@pytest.mark.parametrize("size", list(MAP_SIZES))
def test_every_map_plays_with_its_fewest_and_its_most_civs(size):
    spec = MAP_SIZES[size]
    for civs in (spec["min_civs"], spec["max_civs"]):
        sim = Simulation(game_config(size, civs, seed=11))
        brain = make_brain("utility")
        for _ in range(60):
            sim.step_with(brain)
        assert len(sim.civs) == civs and all(civ.alive for civ in sim.civs)
        assert len(sim.world.regions) > 2 * civs, "room left unclaimed at the start"


@pytest.mark.parametrize("size, civs", [("huge", 4), ("small", 4), ("medium", 6), ("large", 1), ("medium", True)])
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
            await ws.send(command("new_game", {"size": "large", "civs": 5, "seed": 7, "mode": "rule"}))
            game = await next_init(ws)
            assert game["lobby"] is None and game["seed"] == 7
            assert (game["map"]["width"], len(game["civs"])) == (128, 5)
            assert server.paused, "a game to be ruled waits for the player to choose a civ"
            await ws.send(command("take_control", {"civ": 2}))
            await ws.send(command("resume"))
            await ws.send(command("end_game"))
            back = await next_init(ws)
            assert back["lobby"] is not None and not server.paused
            assert server.sim.ruler.state() is None
        task.cancel()

    asyncio.run(scenario())
