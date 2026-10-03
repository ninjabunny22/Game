"""Wire format between the sim (server) and a viewer (client). JSON text frames.

Every message is an envelope:  {"type", "version", "tick", "data"}

Server -> client
  init    sent once on connect: everything static (map, biome/building/tech
          definitions, civ identities).
  tick    sent after every sim tick, and once right after init: the full dynamic
          state of every civ plus the territory grid. No deltas; any tick message
          alone is enough to redraw.
  status  sent when pause/speed changes (ticks stop while paused).
  error   reply to a malformed or unknown command.

Client -> server
  command data = {"action": "pause" | "resume" | "toggle_pause" | "step" | "set_speed",
                  "value": <ticks per second, for set_speed>}
"""

import json

from ..economy.rules import RESOURCES
from ..map import BIOME_INFO, DEPOSIT_TYPES, Biome
from ..simulation import Simulation

PROTOCOL_VERSION = 1
COMMANDS = ("pause", "resume", "toggle_pause", "step", "set_speed")


class ProtocolError(ValueError):
    pass


def encode(message_type: str, tick: int, data: dict) -> str:
    envelope = {"type": message_type, "version": PROTOCOL_VERSION, "tick": tick, "data": data}
    return json.dumps(envelope, separators=(",", ":"))


def parse_command(raw: str | bytes) -> tuple[str, float | None]:
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("message is not valid JSON") from exc
    if not isinstance(message, dict) or message.get("type") != "command":
        raise ProtocolError('expected a message of type "command"')
    data = message.get("data")
    if not isinstance(data, dict) or data.get("action") not in COMMANDS:
        raise ProtocolError(f"unknown action; expected one of {', '.join(COMMANDS)}")
    action = data["action"]
    value = data.get("value")
    if action == "set_speed":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ProtocolError("set_speed needs a positive numeric value")
        return action, float(value)
    return action, None


def init_message(sim: Simulation) -> str:
    world = sim.world
    data = {
        "seed": sim.config.seed,
        "resources": list(RESOURCES),
        "map": {
            "width": world.width,
            "height": world.height,
            # Row-major. Heights: 0 = sea level, land (0, 1], sea floor [-0.5, 0).
            "heights": world.heights,
            "biomes": [int(b) for b in world.biomes],
            "deposits": [
                {"x": tile % world.width, "y": tile // world.width, "type": type_id}
                for tile, type_id in sorted(world.deposits.items())
            ],
        },
        "biomes": [
            {"id": int(biome), "name": BIOME_INFO[biome].name, "color": BIOME_INFO[biome].color,
             "water": BIOME_INFO[biome].water}
            for biome in Biome
        ],
        "deposit_types": {
            type_id: {"name": dtype.name, "color": dtype.color} for type_id, dtype in DEPOSIT_TYPES.items()
        },
        "buildings": {
            bdef.id: {"name": bdef.name, "color": bdef.color, "height": bdef.height,
                      "requires_tech": bdef.requires_tech}
            for bdef in sim.building_defs.values()
        },
        "tech_tree": {
            "eras": sim.tech_tree.eras,
            "techs": [
                {"id": tech.id, "name": tech.name, "era": tech.era, "prereqs": list(tech.prereqs),
                 "cost": tech.cost, "description": tech.description}
                for tech in sim.tech_tree.techs.values()
            ],
        },
        "civs": [
            {"id": civ.id, "name": civ.name, "color": civ.color, "personality": civ.personality.name}
            for civ in sim.civs
        ],
    }
    return encode("init", sim.tick, data)


def tick_message(sim: Simulation, paused: bool, speed: float) -> str:
    world = sim.world
    tree = sim.tech_tree
    civs = []
    for civ in sim.civs:
        mods = sim.modifiers[civ.id]
        era = tree.era_of(civ.known_techs)
        research = None
        if civ.research:
            tech = tree.techs[civ.research.tech_id]
            progress = min(1.0, civ.science / tech.science_cost) if civ.research.paid else 0.0
            research = {"id": tech.id, "paid": civ.research.paid, "progress": round(progress, 3)}
        civs.append({
            "id": civ.id,
            "population": int(civ.population),
            "housing": int(mods.housing),
            "storage": int(mods.storage),
            "resources": {res: round(civ.resources[res], 1) for res in RESOURCES},
            "income": {res: round(civ.income[res], 2) for res in RESOURCES},
            "workers": {res: round(civ.workers[res], 1) for res in RESOURCES},
            "idle": round(civ.idle, 1),
            "territory_size": len(civ.territory),
            "settlements": [
                {"name": s.name, "x": s.tile % world.width, "y": s.tile // world.width} for s in civ.settlements
            ],
            "buildings": [
                {"type": b.type, "x": b.tile % world.width, "y": b.tile // world.width,
                 "progress": round(b.progress, 2), "complete": b.complete}
                for b in civ.buildings
            ],
            "goal": {"kind": civ.goal.kind, "target": civ.goal.target} if civ.goal else None,
            "era": era,
            "era_name": tree.eras[era],
            "techs": list(civ.known_techs),
            "research": research,
            "science_rate": round(civ.science_rate, 2),
        })
    data = {
        "status": {"paused": paused, "speed": speed},
        # One char per tile, row-major: '.' unowned, otherwise the civ id digit.
        "territory": world.territory_string(),
        "territory_rev": world.territory_rev,
        "civs": civs,
        "events": sim.events,
    }
    return encode("tick", sim.tick, data)


def status_message(sim: Simulation, paused: bool, speed: float) -> str:
    return encode("status", sim.tick, {"paused": paused, "speed": speed})


def error_message(sim: Simulation, text: str) -> str:
    return encode("error", sim.tick, {"message": text})
