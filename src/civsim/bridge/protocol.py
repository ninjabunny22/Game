"""Wire format between the sim (server) and a viewer (client). JSON text frames.

Every message is an envelope:  {"type", "version", "tick", "data"}

Server -> client
  init    sent once on connect: everything static (map, biome/building/tech
          definitions, civ identities).
  tick    sent after every sim tick, and once right after init: the full dynamic
          state of every civ, the territory grid, armies and villagers on the
          map, relations between civs, and trade deals. No deltas; any tick message alone is enough
          to redraw.
  status  sent when pause/speed changes (ticks stop while paused).
  error   reply to a malformed or unknown command.

Client -> server
  command data = {"action": "pause" | "resume" | "toggle_pause" | "step" | "set_speed",
                  "value": <ticks per second, for set_speed>}
"""

import json

from ..economy.rules import RESOURCES
from ..map import BIOME_INFO, DEPOSIT_TYPES, Biome, load_faction
from ..military import UNIT_TYPES
from ..simulation import Simulation

PROTOCOL_VERSION = 6
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
            # Region id per tile, row-major; -1 for open sea.
            "region_ids": world.region_of,
            # Rivers run through land tiles; size is 1 (stream) to 3 (wide river).
            "rivers": [
                {"x": tile % world.width, "y": tile // world.width, "size": size}
                for tile, size in sorted(world.rivers.items())
            ],
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
                      "requires_tech": bdef.requires_tech, "upkeep": bdef.upkeep}
            for bdef in sim.building_defs.values()
        },
        # Regions never change shape; who holds each one is in every tick message.
        "regions": [
            {"id": region.id, "name": region.name, "capital": region.capital_name,
             "x": region.capital % world.width, "y": region.capital // world.width}
            for region in world.regions
        ],
        "native_faction": load_faction(),
        "unit_types": {
            unit.id: {"name": unit.name, "strength": unit.strength, "speed": unit.speed,
                      "requires": list(unit.requires), "counters": list(unit.counters)}
            for unit in UNIT_TYPES.values()
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
    diplomacy = sim.diplomacy
    civs = []
    for civ in sim.civs:
        mods = sim.modifiers[civ.id]
        era = tree.era_of(civ.known_techs)
        research = None
        if civ.research:
            tech = tree.techs[civ.research.tech_id]
            progress = min(1.0, civ.research.progress / tech.science_cost)
            research = {"id": tech.id, "paid": civ.research.paid, "progress": round(progress, 3)}
        civs.append({
            "id": civ.id,
            "alive": civ.alive,
            "regions": [region.id for region in world.regions if region.owner == civ.id],
            "population": int(civ.population),
            "housing": int(mods.housing),
            "storage": {res: int(mods.storage[res]) for res in RESOURCES},  # hard cap per resource
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
                 "progress": round(b.progress, 2), "complete": b.complete, "active": b.active}
                for b in civ.buildings
            ],
            "goal": {"kind": civ.goal.kind, "target": civ.goal.target} if civ.goal else None,
            "era": era,
            "era_name": tree.eras[era],
            "techs": list(civ.known_techs),
            "research": research,
            "science_rate": round(civ.science_rate, 2),
            "demolition_refund": round(mods.demolition_refund, 2),
            "soldiers": int(civ.soldiers),
            "units": {unit_id: round(count) for unit_id, count in civ.unit_counts().items() if round(count) > 0},
            "commanders_in_reserve": [{"name": c.name, "level": c.level} for c in civ.commanders],
            "army_strength": round(diplomacy.strength(civ), 1),
            "unpaid": civ.unpaid,
            "unsupplied": civ.unsupplied,
            "diplomacy_points": int(civ.diplomacy_points),
            "thirsty": civ.thirsty,
            "water_access": civ.water_access,
            # Ticks for which others still hold a betrayal against this civ (0 = in good standing).
            "distrusted_for": max(0, diplomacy.distrust_until.get(civ.id, 0) - sim.tick),
            # Strategic layer: stance toward each other civ (keyed by civ id), and why.
            "stances": {str(other): diplomacy.intent(civ.id, other).stance.value for other in diplomacy.others(civ.id)},
            "reason": civ.last_reason,
            "thinking": civ.thinking,
        })
    armies = []
    villagers = []
    for civ in sim.civs:
        for army in civ.armies:
            if army.size < 0.5:
                continue  # an empty garrison is not drawn
            commander = army.commander
            armies.append({
                "id": army.id, "civ": civ.id, "x": army.tile % world.width, "y": army.tile // world.width,
                "role": army.role, "state": army.state, "target_civ": army.target_civ,
                # Whole soldiers per unit type; types rounding to zero are left out.
                "units": {unit_id: round(count) for unit_id, count in army.units.items() if round(count) > 0},
                "size": round(army.size),
                "dominant": army.dominant,
                "strength": round(sim.military.army_strength(army), 1),
                "commander": {"name": commander.name, "level": commander.level, "battles": commander.battles,
                              "wins": commander.wins} if commander else None,
            })
        for villager in civ.villagers:
            villagers.append({"id": villager.id, "civ": civ.id, "x": villager.tile % world.width,
                              "y": villager.tile // world.width, "task": villager.task})
    relations = []
    for (a, b), relation in diplomacy.relations.items():
        war = relation.war
        relations.append({
            "a": a, "b": b, "status": relation.status, "since": relation.since,
            # What history calls it: the war's name, or the alliance's; null at peace.
            "name": (war.name if war else relation.alliance_name) or None,
            "truce": sim.tick < relation.truce_until,
            "war": {
                "started": war.start,
                "aggressors": sorted(war.aggressors),
                "declarer": war.declarer,
                "defending": war.defending,  # set if one side was drawn in by an alliance
                "betrayer": war.betrayer,  # set if the declarer broke an alliance to attack
                "surprise": sim.tick < war.surprise_until,
                "tiles_taken": {str(civ_id): count for civ_id, count in war.tiles_taken.items()},
                "casualties": {str(civ_id): round(lost) for civ_id, lost in war.casualties.items()},
            } if war else None,
        })
    data = {
        "status": {"paused": paused, "speed": speed},
        # Base64 of one byte per tile, row-major: owning civ id, 255 = unowned.
        "territory": world.encode_territory(),
        "territory_rev": world.territory_rev,
        "civs": civs,
        "armies": armies,
        "villagers": villagers,
        # owner is a civ id, or null while the native faction holds the region.
        "regions": [
            {"id": region.id, "owner": region.owner, "garrison": round(region.garrison)}
            for region in world.regions
        ],
        "relations": relations,
        "deals": [
            {"id": deal.id, "a": deal.a, "b": deal.b, "ends": deal.end,
             "a_gives": {"resource": deal.a_gives[0], "rate": deal.a_gives[1]},
             "b_gives": {"resource": deal.b_gives[0], "rate": deal.b_gives[1]}}
            for deal in diplomacy.deals
        ],
        "events": sim.events,
    }
    return encode("tick", sim.tick, data)


def status_message(sim: Simulation, paused: bool, speed: float) -> str:
    return encode("status", sim.tick, {"paused": paused, "speed": speed})


def error_message(sim: Simulation, text: str) -> str:
    return encode("error", sim.tick, {"message": text})
