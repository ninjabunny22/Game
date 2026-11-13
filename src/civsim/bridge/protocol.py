"""Wire format between the sim (server) and a viewer (client). JSON text frames.

Every message is an envelope:  {"type", "version", "tick", "data"}

Server -> client
  init    sent once on connect: everything static (map, biome/building/tech
          definitions, civ identities).
  tick    sent after every sim tick, and once right after init: the full dynamic
          state of every civ, the territory grid, armies and villagers on the
          map, relations between civs, and trade deals. No deltas; any tick message alone is enough
          to redraw.
  status  sent when pause/speed changes (ticks stop while paused), and when the clock starts
          or stops waiting for a strategist's answer.
  error   reply to a malformed or unknown command.

Client -> server
  command data = {"action": "pause" | "resume" | "toggle_pause" | "step" | "set_speed",
                  "value": <ticks per second, for set_speed>}
"""

import json

from ..economy.buildings import castle_square
from ..economy.production import soldier_cost
from ..economy.rules import RESOURCES
from ..map import BIOME_INFO, DEPOSIT_TYPES, Biome, load_faction
from ..military import UNIT_TYPES
from ..military.warfare import ROSTER_CAP
from ..simulation import Simulation
from ..config import HEADCOUNT, MAP_SIZES, MAPS, civ_counts, civ_range
from ..diplomacy import rules

PROTOCOL_VERSION = 20
RULER_COMMANDS = ("take_control", "release_control", "set_stance", "set_focus", "set_research", "set_build",
                  "answer_proposal", "start_rally", "cancel_rally", "reinforce_ally", "recall_reinforcement")
GAME_COMMANDS = ("new_game", "end_game")  # start a game from the menu; go back to the menu
COMMANDS = ("pause", "resume", "toggle_pause", "step", "set_speed", *RULER_COMMANDS, *GAME_COMMANDS)


class ProtocolError(ValueError):
    pass


def encode(message_type: str, tick: int, data: dict) -> str:
    envelope = {"type": message_type, "version": PROTOCOL_VERSION, "tick": tick, "data": data}
    return json.dumps(envelope, separators=(",", ":"))


def parse_command(raw: str | bytes) -> tuple[str, float | dict | None]:
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
    if action in RULER_COMMANDS or action in GAME_COMMANDS:
        # A ruler's command carries its details as an object; the ruler checks what is in it.
        if value is not None and not isinstance(value, dict):
            raise ProtocolError(f"{action} needs an object value")
        return action, value or {}
    return action, None


def _lobby_map(size: str, entry: dict) -> dict:
    """What the menu shows of a map: its name and size, the civs it takes, and what it is about."""
    spec = MAP_SIZES[size]
    fewest, most = civ_range(size, entry)
    return {"id": entry["id"], "name": entry["name"], "width": entry.get("width", spec["side"]),
            "height": entry.get("height", spec["side"]), "min_civs": fewest, "max_civs": most,
            "counts": civ_counts(size, entry),
            "best": entry.get("best", ""), "premise": entry.get("premise", "")}


def init_message(sim: Simulation, lobby: bool = False) -> str:
    world = sim.world
    data = {
        # Set while no game has been started: the map behind the main menu is only a backdrop,
        # and this is what a game can be started with.
        # Each size lists the maps it can be played on; a game takes the one asked for, or any.
        "lobby": {"sizes": [{"id": size, **spec, "maps": [_lobby_map(size, m) for m in MAPS[size]]}
                            for size, spec in MAP_SIZES.items()]} if lobby else None,
        "seed": sim.config.seed,
        "map_name": sim.config.map_name,  # "" for a map made from the game's own seed
        "resources": list(RESOURCES),
        "map": {
            "width": world.width,
            "height": world.height,
            # Row-major. Heights: 0 = sea level, land (0, 1], sea floor [-0.5, 0).
            "heights": world.heights,
            "biomes": [int(b) for b in world.biomes],
            # Region id per tile, row-major; -1 for open sea.
            "region_ids": world.region_of,
            # Rivers run through land tiles; size is 1 (stream) to 3 (wide river). "to" is the
            # tile the water flows into next: more river, or the sea or lake at the mouth.
            "rivers": [
                {"x": tile % world.width, "y": tile // world.width, "size": size,
                 "to": [world.river_flow[tile] % world.width, world.river_flow[tile] // world.width]}
                for tile, size in sorted(world.rivers.items())
            ],
            "deposits": [
                {"x": tile % world.width, "y": tile // world.width, "type": type_id}
                for tile, type_id in sorted(world.deposits.items())
            ],
            # Old bridges: river tiles anyone crosses as if bridged.
            "bridges": [{"x": tile % world.width, "y": tile // world.width} for tile in sorted(world.bridges)],
            # Long bridges over water, each drawn whole from one shore to the other.
            "spans": [{"from": [x0, y0], "to": [x1, y1]} for x0, y0, x1, y1 in world.spans],
            # Passes: mountain tiles (and gaps in ridges) armies and villagers can get through.
            "passes": [{"x": tile % world.width, "y": tile // world.width} for tile in sorted(world.passes)],
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
            # "size": tiles a side of the square the building stands on.
            bdef.id: {"name": bdef.name, "color": bdef.color, "height": bdef.height, "size": bdef.size,
                      "requires_tech": bdef.requires_tech, "upkeep": bdef.upkeep}
            for bdef in sim.building_defs.values()
        },
        # Regions never change shape; who holds each one is in every tick message.
        "regions": [
            {"id": region.id, "name": region.name, "capital": region.capital_name,
             "x": region.capital % world.width, "y": region.capital // world.width,
             # What holding it is worth (1 to 3), and whether its natives hold a stronghold.
             "points": region.points, "stronghold": region.strength > 1, "tags": list(region.tags)}
            for region in world.regions
        ],
        # Gold mines: fixed sites, each paying the owner of its region (see "regions" in each tick).
        "mines": [{"x": tile % world.width, "y": tile // world.width, "region": world.region_of[tile]}
                  for tile in world.mines],
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
            {"id": civ.id, "name": civ.name, "color": civ.color, "personality": civ.personality.name,
             "capital_name": civ.capital.name}
            for civ in sim.civs
        ],
    }
    return encode("init", sim.tick, data)


def _castles(sim: Simulation) -> dict[int, int]:
    """Every tile a capital's castle stands on (economy.castle_ground), mapped to that capital's tile."""
    return {tile: capital for capital in sim.world.capital_tiles for tile in castle_square(sim.world, capital)}


def _in_castle(sim: Simulation, castles: dict[int, int], civ_id: int, tile: int) -> bool:
    """Whether someone of `civ_id` on `tile` is inside a castle: on the castle ground of a capital
    held by its own civ or an ally. An army at an enemy's or the natives' walls is besieging it,
    not inside, and stays in sight."""
    capital = castles.get(tile)
    if capital is None:
        return False
    holder = sim.world.regions[sim.world.capital_tiles[capital]].owner
    if holder is None:
        return False
    return holder == civ_id or sim.diplomacy.relation(civ_id, holder).status == "alliance"


def _settlement(sim: Simulation, civ, settlement, watcher) -> dict:
    """A capital as the viewer may see it: where it is, and who holds its castle."""
    world, military = sim.world, sim.military
    entry = {"name": settlement.name, "x": settlement.tile % world.width, "y": settlement.tile // world.width}
    actual = heads(military.castle_defenders(civ, settlement.tile))  # its garrison, and any force holding it
    known = watcher is None or military.garrison_known(watcher, settlement.tile)
    if known:
        entry["garrison"] = actual
    else:
        entry["about"] = military.garrison_guess(watcher, settlement.tile, actual)
    # Its generals in reserve, its hospital (all the civ's wounded and beds, spread through its
    # castles) and, if an enemy has broken in, who and how far the hold has gone.
    entry["generals"] = [{"name": c.name, "level": c.level} for c in civ.commanders if c.post == settlement.tile]
    # Who is inside its walls, none of whom is drawn on the map: the civ's villagers on its
    # castle ground, its soldiers (the garrison's share and the civ's armies standing there) and
    # its generals (those in reserve, and those leading the armies inside). For another civ's
    # castle the player has not counted, the soldiers are only "about" as many, and the
    # generals leading armies inside are left out, as their armies are.
    ground = set(castle_square(world, settlement.tile))
    inside_armies = [a for a in civ.armies if a.role != "garrison" and a.size >= 0.5 and a.tile in ground]
    soldiers = heads(military.castle_garrison(civ) + sum(a.size for a in inside_armies))
    generals = list(entry["generals"])
    if known:
        generals += [{"name": a.commander.name, "level": a.commander.level} for a in inside_armies if a.commander]
    entry["inside"] = {
        "villagers": sum(1 for v in civ.villagers if v.tile in ground),
        "soldiers": soldiers if known else military.garrison_guess(watcher, settlement.tile, soldiers),
        "about": not known,
        "generals": generals,
    }
    entry["beds"] = heads(military.beds(civ) / max(1, len(civ.settlements)))
    entry["wounded"] = heads(civ.wounded / max(1, len(civ.settlements)))
    region = world.regions[world.capital_tiles[settlement.tile]] if settlement.tile in world.capital_tiles else None
    entry["held_by"] = region.held_by if region is not None else None
    entry["hold"] = round(region.hold / rules.CAPITAL_HOLD, 3) if region is not None else 0.0
    return entry


def tick_message(sim: Simulation, paused: bool, speed: float) -> str:
    world = sim.world
    tree = sim.tech_tree
    diplomacy = sim.diplomacy
    watcher = sim.ruler.civ if sim.ruler.civ is not None and sim.ruler.civ.alive else None
    civs = []
    for civ in sim.civs:
        mods = sim.modifiers[civ.id]
        era = tree.era_of(civ.known_techs)
        research = None
        if civ.research:
            tech = tree.techs[civ.research.tech_id]
            progress = min(1.0, civ.research.progress / tech.science_cost)
            research = {"id": tech.id, "paid": civ.research.paid, "progress": round(progress, 3)}
        posts = {s.tile: s.name for s in civ.settlements}
        civs.append({
            "id": civ.id,
            "alive": civ.alive,
            "score": sim.score(civ),
            # What it is working toward, in words, and what the realm concentrates on.
            "strategy": civ.strategy,
            "focus": civ.focus,
            # The war it is preparing, in words ("" when it is not).
            "plan": civ.plan,
            # The sickness a long war has brought on the civ, and how many days it has left; null when well.
            "sickness": {"name": civ.sickness, "days": max(0, civ.sick_until - sim.tick)} if civ.sickness else None,
            "regions": [region.id for region in world.regions if region.owner == civ.id],
            "points": sim.points_held(civ),  # region points held: domination is counted in these
            "mines": sim.mines_held(civ),  # gold mines in its regions, each paying it gold every day
            "population": heads(civ.population),
            "housing": heads(mods.housing),
            "storage": {res: int(mods.storage[res]) for res in RESOURCES},  # hard cap per resource
            "resources": {res: round(civ.resources[res], 1) for res in RESOURCES},
            "income": {res: round(civ.income[res], 2) for res in RESOURCES},
            "workers": {res: round(civ.workers[res], 1) for res in RESOURCES},
            "idle": round(civ.idle, 1),
            "territory_size": len(civ.territory),
            # Each capital, with the soldiers holding its castle: "garrison" exactly, or, when a
            # human rules another civ that has not attacked this castle lately, only "about"
            # (within 30 of the truth). The viewer never gets the number it is not meant to see.
            "settlements": [_settlement(sim, civ, s, watcher) for s in civ.settlements],
            # "x", "y" is the building's tile: the middle of an odd-sized building's square,
            # and the corner nearest the origin of an even-sized one. "village" is the id of
            # the village or town it belongs to.
            "buildings": [
                {"id": b.id, "type": b.type, "x": b.tile % world.width, "y": b.tile // world.width,
                 "village": b.village,
                 "progress": round(b.progress, 2), "complete": b.complete, "active": b.active}
                for b in civ.buildings
            ],
            # Villages and towns: named groups of buildings. "capital" marks the town around
            # a region capital; "buildings" is how many belong to it.
            "villages": [
                {"id": v.id, "name": v.name, "x": v.tile % world.width, "y": v.tile // world.width,
                 "capital": v.capital, "buildings": sim.villages.size(v.id)}
                for v in sim.villages.of(civ.id)
            ],
            "goal": {"kind": civ.goal.kind, "target": civ.goal.target} if civ.goal else None,
            "era": era,
            "era_name": tree.eras[era],
            "techs": list(civ.known_techs),
            "research": research,
            "science_rate": round(civ.science_rate, 2),
            "demolition_refund": round(mods.demolition_refund, 2),
            # Totals over all the civ's armies; the armies themselves are listed under "armies".
            "soldiers": heads(civ.soldiers),
            "units": whole(shown(civ.unit_counts())),
            # "post" is the capital a reserve commander is stationed at, which he helps defend,
            # and x, y where it stands (null when he has no post).
            "commanders_in_reserve": [{"name": c.name, "level": c.level, "post": posts.get(c.post),
                                       "x": c.post % world.width if c.post is not None else None,
                                       "y": c.post // world.width if c.post is not None else None}
                                      for c in civ.commanders],
            "commanders": sim.military.roster(civ),
            "commander_cap": ROSTER_CAP,
            "army_strength": round(diplomacy.strength(civ), 1),
            # Soldiers in hospital (they join the garrison when healed), the beds there are for
            # them, and how many have died in all for want of one.
            "wounded": heads(civ.wounded),
            "beds": heads(sim.military.beds(civ)),
            "hospital_deaths": heads(civ.hospital_deaths),
            # How well the civ can arm its soldiers, 1 to 4, and what a soldier costs it (1 = the usual).
            "tier": int(sim.military.best_tier(civ)),
            "soldier_cost": round(soldier_cost(mods), 2),
            # Horses standing in the stables, and the whole herd including those under riders.
            "horses": int(civ.horses),
            "herd": int(civ.herd),
            # Enemy commanders this civ holds prisoner.
            "captives": [{"name": c.commander.name, "level": c.commander.level, "home": c.home} for c in civ.captives],
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
    castles = _castles(sim)
    for civ in sim.civs:
        for army in civ.armies:
            if army.size < 0.5:
                continue  # an empty garrison is not drawn
            if army.role == "garrison" and watcher is not None and civ.id != watcher.id:
                continue  # how many hold another civ's castles is shown only roughly, by castle
            commander = army.commander
            armies.append({
                "id": army.id, "civ": civ.id, "x": army.tile % world.width, "y": army.tile // world.width,
                "role": army.role, "state": army.state, "target_civ": army.target_civ,
                # duty: "attack" (out after the enemy's capitals), "defend" (a home force on its own
                # land) or "reinforce" (standing in an ally's capital). refit: going home to fill its ranks.
                "duty": army.duty,
                "refit": army.refit,
                # How well its soldiers are armed, 1 to 4 (an average when they differ).
                "tier": round(army.tier, 1),
                # False when a human rules a civ whose armies and capitals are too far off to
                # count this army: the viewer then shows its size only roughly.
                "scouted": watcher is None or sim.military.scouted(watcher, army),
                # Whole soldiers per unit type, adding up exactly to "size".
                "units": whole(shown(army.units)),
                "size": heads(army.size),
                # How many its commander can lead (null for a rally, which has no limit), and the rally it is with.
                "capacity": heads(sim.military.capacity(army)) if sim.military.capacity(army) < 1e8 else None,
                "rally": army.rally,
                "dominant": army.dominant,
                # afloat: on open water. boat: aboard ship, which an army on open water always is,
                # having put out from near one of its civ's harbours; drawn as a ship until it lands.
                "afloat": world.is_boat_water(army.tile),
                "boat": army.boat,
                # Inside a castle of its own civ or an ally: not drawn (click the castle to count it).
                "in_castle": _in_castle(sim, castles, civ.id, army.tile),
                "strength": round(sim.military.army_strength(army), 1),
                "commander": {"name": commander.name, "level": commander.level, "battles": commander.battles,
                              "wins": commander.wins} if commander else None,
            })
        for villager in civ.villagers:
            villagers.append({"id": villager.id, "civ": civ.id, "x": villager.tile % world.width,
                              "y": villager.tile // world.width, "task": villager.task,
                              # What a gatherer is working, whether it has reached its place of work,
                              # and whether it rides a horse from the stables.
                              "gathers": villager.gathers, "at_work": villager.tile == villager.target,
                              "mounted": villager.mounted,
                              # On open water it is aboard a ship and is not drawn.
                              "afloat": world.is_boat_water(villager.tile),
                              # Inside a castle's walls: not drawn.
                              "in_castle": _in_castle(sim, castles, civ.id, villager.tile)})
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
                "regions_taken": {str(civ_id): count for civ_id, count in war.regions_taken.items()},
                "casualties": {str(civ_id): round(lost) for civ_id, lost in war.casualties.items()},
            } if war else None,
        })
    data = {
        "status": _status(sim, paused, speed),
        # Base64 of one byte per tile, row-major: owning civ id, 255 = unowned.
        "territory": world.encode_territory(),
        "territory_rev": world.territory_rev,
        "civs": civs,
        # Who has won, how ("conquest", "domination" or "score") and when; null while undecided.
        "victory": sim.victory,
        # What domination takes: region points and regions.
        "domination": dict(zip(("points", "regions"), sim.domination_target())),
        # The civ a human rules and the orders in force, or null when every civ plays itself.
        "ruler": sim.ruler.state(),
        "armies": armies,
        "villagers": villagers,
        # owner is a civ id, or null while the native faction holds the region.
        "regions": [
            # held_by: the civ whose army has broken into the capital, hold: how far (0 to 1) it is to taking it.
            {"id": region.id, "owner": region.owner, "garrison": heads(region.garrison),
             "held_by": region.held_by, "hold": round(region.hold / rules.CAPITAL_HOLD, 3)}
            for region in world.regions
        ],
        # Rallies gathering or on the march: who leads, where it gathers, what it is for, how long
        # until it sets out (0 once it has), who has joined and how many soldiers it has.
        "rallies": [_rally(sim, rally) for rally in sim.military.rallies],
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
    return encode("status", sim.tick, _status(sim, paused, speed))


def _status(sim: Simulation, paused: bool, speed: float) -> dict:
    # waiting_for: civs whose strategist has not answered in time; the clock holds until it does.
    return {"paused": paused, "speed": speed, "waiting_for": sim.waiting_for()}


def heads(count: float) -> int:
    """A head count as it is shown: each unit in the simulation stands for HEADCOUNT people."""
    return round(count * HEADCOUNT)


def _rally(sim: Simulation, rally) -> dict:
    world = sim.world
    armies = [a for civ in sim.civs for a in civ.armies if a.rally == rally.id]
    return {
        "id": rally.id, "leader": rally.leader, "enemy": rally.enemy, "state": rally.state,
        "city": {"x": rally.city % world.width, "y": rally.city // world.width, "name": sim.military._city_name(rally.city)},
        "target": {"x": rally.target % world.width, "y": rally.target // world.width,
                   "name": sim.military._city_name(rally.target)},
        "days_left": max(0, rally.departs - sim.tick) if rally.state == "gathering" else 0,
        "members": sorted({a.civ for a in armies} | set(rally.shares)),
        "soldiers": heads(sum(a.size for a in armies)),
    }


def shown(units: dict[str, float]) -> dict[str, float]:
    """Soldiers per unit type as head counts to show."""
    return {unit: count * HEADCOUNT for unit, count in units.items()}


def whole(units: dict[str, float]) -> dict[str, int]:
    """Soldiers per unit type as whole numbers that add up to the rounded total."""
    total = round(sum(units.values()))
    counts = {unit: int(count) for unit, count in units.items()}
    by_fraction = sorted(units, key=lambda unit: (-(units[unit] - counts[unit]), unit))
    for unit in by_fraction[: max(0, total - sum(counts.values()))]:
        counts[unit] += 1
    return {unit: count for unit, count in counts.items() if count > 0}


def error_message(sim: Simulation, text: str) -> str:
    return encode("error", sim.tick, {"message": text})
