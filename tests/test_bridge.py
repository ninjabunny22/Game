import asyncio
import base64
import json

import pytest
from websockets.asyncio.client import connect

from civsim.bridge import SimServer, protocol
from civsim.config import SimConfig
from civsim.simulation import Simulation
from civsim.strategy import RuleBrain


def test_messages_are_enveloped_json():
    sim = Simulation(SimConfig(seed=3))
    sim.step()
    init = json.loads(protocol.init_message(sim))
    tick = json.loads(protocol.tick_message(sim, False, 2.0))
    for message, kind in ((init, "init"), (tick, "tick")):
        assert message["type"] == kind
        assert message["version"] == protocol.PROTOCOL_VERSION
        assert message["tick"] == 1
    size = init["data"]["map"]["width"] * init["data"]["map"]["height"]
    assert len(init["data"]["map"]["heights"]) == len(init["data"]["map"]["biomes"]) == size
    owners = base64.b64decode(tick["data"]["territory"])
    assert len(owners) == size
    assert set(owners) == {0, 1, 2, 3, 255}
    assert len(tick["data"]["civs"]) == len(init["data"]["civs"]) == 4
    assert len(init["data"]["tech_tree"]["techs"]) == len(sim.tech_tree.techs)


@pytest.mark.parametrize("raw", [
    "not json",
    '{"type": "tick"}',
    '{"type": "command", "data": {"action": "explode"}}',
    '{"type": "command", "data": {"action": "set_speed"}}',
    '{"type": "command", "data": {"action": "set_speed", "value": -1}}',
])
def test_bad_commands_are_rejected(raw):
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_command(raw)


def test_server_pushes_state_and_obeys_commands():
    async def scenario():
        sim = Simulation(SimConfig(seed=3))
        server = SimServer(sim, RuleBrain(), port=0, tick_rate=50, paused=True)
        task = asyncio.create_task(server.run())
        await server.ready.wait()

        async def receive(ws, kind):
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if message["type"] == kind:
                    return message

        def command(action, value=None):
            return json.dumps({"type": "command", "version": protocol.PROTOCOL_VERSION, "data": {"action": action, "value": value}})

        try:
            async with connect(f"ws://127.0.0.1:{server.port}") as ws:
                assert (await receive(ws, "init"))["tick"] == 0
                first = await receive(ws, "tick")
                assert first["tick"] == 0 and first["data"]["status"]["paused"]

                await ws.send(command("step"))
                assert (await receive(ws, "tick"))["tick"] == 1

                await ws.send(command("resume"))
                assert not (await receive(ws, "status"))["data"]["paused"]
                while (await receive(ws, "tick"))["tick"] < 5:
                    pass

                await ws.send(command("set_speed", 1000))
                assert (await receive(ws, "status"))["data"]["speed"] == 60.0

                await ws.send("garbage")
                assert "JSON" in (await receive(ws, "error"))["data"]["message"]

                await ws.send(command("pause"))
                assert (await receive(ws, "status"))["data"]["paused"]
                stopped_at = sim.tick
                await asyncio.sleep(0.2)
                assert sim.tick == stopped_at
        finally:
            task.cancel()

    asyncio.run(scenario())


def test_army_unit_counts_add_up_to_the_army_size():
    from civsim.bridge.protocol import whole
    assert whole({"spearman": 3.4, "archer": 3.4, "swordsman": 3.4}) == {"archer": 4, "spearman": 3, "swordsman": 3}
    assert whole({"spearman": 0.4, "archer": 0.4, "swordsman": 0.4, "cavalry": 0.4}) == {"archer": 1, "cavalry": 1}
    assert whole({"spearman": 12.0}) == {"spearman": 12}
    for units in ({"a": 0.5, "b": 0.5}, {"a": 7.49, "b": 2.2, "c": 0.31}, {"a": 0.2}):
        assert sum(whole(units).values()) == round(sum(units.values()))


def test_the_clock_waits_for_a_strategist_who_has_not_answered():
    from civsim.config import SimConfig
    from civsim.simulation import Simulation
    from civsim.strategy import CHECKIN_INTERVAL
    sim = Simulation(SimConfig(seed=3))
    held = []
    while not held:  # run until someone has a check-in outstanding, and never answer it
        sim.step()
        held += sim.take_requests()
    request = held[0]
    assert CHECKIN_INTERVAL == 1
    for other in held[1:]:  # everyone else answers at once
        sim.submit(other, None)
    assert sim.waiting_for() == [request.civ_id], "its next check-in is due and the last is unanswered"
    sim.submit(request, None)
    assert sim.waiting_for() == [], "answered: the clock may move again"
    status = json.loads(protocol.status_message(sim, False, 1.0))["data"]
    assert status == {"paused": False, "speed": 1.0, "waiting_for": []}


def test_nobody_is_drawn_inside_a_castle_and_the_castle_says_who_is_in_it():
    from civsim.economy import castle_ground
    sim = Simulation(SimConfig(seed=3))
    for _ in range(10):
        sim.step()
    world = sim.world
    civ, other = sim.civs[0], sim.civs[1]
    home = civ.settlements[0].tile
    civ.villagers[0].tile = home + 1  # at work just inside its own castle's walls
    other.villagers[0].tile = home - 1  # a stranger on its castle ground is not inside it
    data = json.loads(protocol.tick_message(sim, False, 1.0))["data"]
    for kind in ("villagers", "armies"):
        for unit in data[kind]:
            if unit["in_castle"]:
                assert castle_ground(world, unit["y"] * world.width + unit["x"])
    by_id = {(v["civ"], v["id"]): v for v in data["villagers"]}
    assert by_id[(civ.id, civ.villagers[0].id)]["in_castle"]
    assert not by_id[(other.id, other.villagers[0].id)]["in_castle"]
    inside = data["civs"][0]["settlements"][0]["inside"]
    assert inside["villagers"] >= 1 and not inside["about"], "anyone may count every castle while nobody rules"
    assert inside["soldiers"] >= protocol.heads(sim.military.castle_garrison(civ)) - 1
    assert inside["generals"] == data["civs"][0]["settlements"][0]["generals"], "no army stands inside yet"


def test_another_civs_castle_is_counted_only_roughly_by_a_ruler():
    sim = Simulation(SimConfig(seed=3))
    sim.step()
    sim.ruler.civ_id = 0
    data = json.loads(protocol.tick_message(sim, False, 1.0))["data"]
    own = data["civs"][0]["settlements"][0]
    assert not own["inside"]["about"] and "garrison" in own
    other = data["civs"][1]["settlements"][0]
    assert other["inside"]["about"] and "about" in other
    assert other["inside"]["soldiers"] % 10 == 0
