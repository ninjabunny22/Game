"""Builds what a civ's strategist gets to see at a check-in: its own state in full,
each neighbour's visible state, and a short history of recent dealings.

How much is visible depends on the relationship. Everyone sees a neighbour's
public facts and a rough comparison of its army to their own. Only allies see
intel: exact army numbers, where the army is committed, and what is in store.
"""

import math

from ..diplomacy.rules import ALLIANCE_COST, DEAL_FEE, SURPLUS_FILL, WAR_COST
from ..economy import training_rate
from ..economy import water_balance, water_urgency
from ..economy.rules import RESOURCES

HISTORY_LENGTH = 8

# Rough army comparison shown to non-allies: (upper bound of their power / yours, label).
ARMY_BANDS = ((0.5, "much weaker"), (0.8, "weaker"), (1.25, "comparable"), (2.0, "stronger"))
STRONGEST_BAND = "much stronger"
# The ratio each label stands for, for a strategist that needs a number.
BAND_RATIO = {"much weaker": 0.35, "weaker": 0.65, "comparable": 1.0, "stronger": 1.6, "much stronger": 2.5}


def army_band(their_power: float, your_power: float) -> str:
    ratio = their_power / max(your_power, 1e-9)
    return next((label for limit, label in ARMY_BANDS if ratio < limit), STRONGEST_BAND)


SCOUTED_SHARE = 0.5  # share of a neighbour's soldiers that must be in sight for its power to be known
MARCH_CACHE_TICKS = 50  # how long a measured march to a neighbour's capital is trusted
ROUT_MEMORY = 100  # ticks for which a lost battle is still plain for all to see


def _abroad(sim, civ) -> bool:
    """Whether most of a civ's soldiers are with armies off its own land."""
    away = sum(army.size for army in civ.armies if army.role == "field" and sim.world.owner[army.tile] != civ.id)
    return civ.soldiers >= 1 and away > 0.5 * civ.soldiers


def _unrest(sim, civ_id: int) -> bool:
    families = getattr(sim, "families", None)
    return families is not None and families.unrest(civ_id, sim.tick)


def _since(sim, tick: int | None) -> int | None:
    return None if tick is None else sim.tick - tick


def _march(sim, civ, other) -> tuple[int | None, float]:
    """How far an army of `civ` would have to go to the nearest capital of `other` it can get
    to (None if there is no way), and how strongly that capital is held."""
    cache = sim.__dict__.setdefault("_march_cache", {})
    known = cache.get((civ.id, other.id))
    if known is not None and sim.tick - known[0] < MARCH_CACHE_TICKS:
        return known[1], known[2]
    military = sim.military
    start = civ.capital.tile
    result: tuple[int | None, float] = (None, 0.0)
    for target in sorted((s.tile for s in other.settlements), key=lambda t: (military._gap(start, t), t)):
        path = military._route(civ, start, target)
        if path is not None:
            result = (len(path), round(military.tile_price(civ, target), 2))
            break
    cache[(civ.id, other.id)] = (sim.tick, *result)
    return result


def stance_context(sim, civ) -> dict:
    diplomacy = sim.diplomacy
    need_points, need_regions = sim.domination_target()
    tree = sim.tech_tree
    mods = sim.modifiers[civ.id]

    top = diplomacy.rivals() or ()
    neighbors = []
    for other_id in diplomacy.others(civ.id):
        other = sim.civs[other_id]
        relation = diplomacy.relation(civ.id, other_id)
        deal = diplomacy.deal_between(civ.id, other_id)
        deal_text = None
        if deal:
            mine, theirs = (deal.a_gives, deal.b_gives) if deal.a == civ.id else (deal.b_gives, deal.a_gives)
            deal_text = (f"you send {mine[1]:g} {mine[0]}/tick, you receive {theirs[1]:g} {theirs[0]}/tick, "
                         f"{deal.end - sim.tick} ticks left")
        theirs = diplomacy.intent(other_id, civ.id)
        march, walls = _march(sim, civ, other)
        demanded = diplomacy.demands.get((civ.id, other_id))
        offer = None
        if theirs.give:
            offer = {"gives": theirs.give, "wants": theirs.want}
        prize = _prize(sim, civ, other_id)
        guard, watched = diplomacy.home_threat(civ, exclude={other_id} | set(diplomacy.enemies(civ.id)))
        claims = _claims(sim, civ, other_id)
        neighbors.append({
            "id": other_id,
            "name": other.name,
            "era": tree.eras[tree.era_of(other.known_techs)],
            "population": int(other.population),
            "territory": len(other.territory),
            "capitals": [s.name for s in other.settlements],
            # Rivers, lakes and coast are plain to see: whether a neighbour has water to spare is public.
            "water_rich": _water_rich(other, sim.modifiers[other_id]),
            "army_vs_yours": army_band(diplomacy.power(other), diplomacy.power(civ)),
            # Exact numbers are shared between allies only.
            "intel": _intel(sim, other) if relation.status == "alliance" else None,
            # Scouting: with most of their soldiers in sight of your armies and capitals you can
            # count them, and know their power as it is (None while they are out of sight).
            "seen_power": (round(diplomacy.power(other)) if relation.status != "alliance"
                           and sim.military.sighted(civ, other) >= SCOUTED_SHARE else None),
            "distrusted_ticks_left": max(0, diplomacy.distrust_until.get(other_id, 0) - sim.tick),
            "relation": relation.status,
            "war_ticks": sim.tick - relation.war.start if relation.war else None,
            # How long the two have been at peace, if they are: a long peace makes the restless bold.
            "peace_ticks": sim.tick - relation.since if relation.status == "peace" else None,
            "alliance_ticks": sim.tick - relation.since if relation.status == "alliance" else None,
            "since_alliance": sim.tick - relation.alliance_ended,  # how long since they were last allies
            "at_war_with": [sim.civs[e].name for e in diplomacy.enemies(other_id)],
            "allied_with": [sim.civs[e].name for e in diplomacy.allies(other_id)],
            "truce": sim.tick < relation.truce_until,
            "in_reach": diplomacy.in_reach(civ.id, other_id, sim.tick),
            # In a war on them: the soldiers that would have to stay at home to hold off whoever
            # else is in reach (the home guard), and who that is.
            "home_guard": math.ceil(guard),
            # More reasons a war might be fought: its rich nodes, land it took from you (and
            # whether that includes your old home), how long it has refused you a trade you
            # asked for, and a pass, neck or crossing of its that opens into your land.
            **claims,
            "watching": sim.civs[watched].name if watched is not None else None,
            # What anyone can see of their army: whether most of it is away from home, and how
            # long ago it was last beaten in the field (None if not lately).
            "army_abroad": _abroad(sim, other),
            "routed_ticks_ago": sim.tick - other.last_rout if sim.tick - other.last_rout <= ROUT_MEMORY else None,
            # The way to their nearest capital an army could take, in tiles (None: no way there),
            # and how strongly it is held (terrain and walls; 1 is open ground).
            "march": march,
            "walls": walls,
            "holds_your_capital": any(r.owner == civ.id and r.held_by == other_id for r in sim.world.regions),
            "you_hold_their_capital": any(r.owner == other_id and r.held_by == civ.id for r in sim.world.regions),
            # What past wars with them have taught you: the extra edge you want before trying again.
            "caution": round(diplomacy.caution.get((civ.id, other_id), 0.0), 2),
            "betrayed_you": (civ.id, other_id) in diplomacy.betrayed,
            # Tribute: whether they are demanding it of you, and how long ago you demanded it of them.
            "demands_tribute": (other_id, civ.id) in diplomacy.demands,
            "your_demand_ticks": sim.tick - demanded if demanded is not None else None,
            "paid_you_ticks": _since(sim, diplomacy.tribute_paid.get((other_id, civ.id))),
            # Sickness is plain to see: a civ laid low by it fights worse until it passes.
            "sick": diplomacy.sick(other),
            # A new ruler not yet settled on the throne (civ/family.py): a realm off balance.
            "unrest": _unrest(sim, other_id),
            # True when you and they are the two strongest civs: each stands in the other's way.
            "rival": civ.id in top and other_id in top,
            "active_deal": deal_text,
            # What you make of them from what has passed between you: -3 a bitter grudge, 3 a proven friend.
            "standing": round(diplomacy.standing[(civ.id, other_id)], 2),
            "their_stance_toward_you": theirs.stance.value,
            "their_trade_offer": offer,
            "your_current_stance": diplomacy.intent(civ.id, other_id).stance.value,
            # Their region worth most to you (strategy/geography.py), and why.
            "prize": prize,
            # Region points they hold, as a share of what wins by domination (1.0: they have won).
            "victory_share": round(sim.points_held(other) / max(1, need_points), 2),
        })

    surplus, lacking = _surplus_and_lacking(civ, mods)
    return {
        "tick": sim.tick,
        "you": {
            "id": civ.id,
            "name": civ.name,
            "personality": civ.personality.name,
            # The civ's own leanings, before whatever it is concentrating on tilts them.
            "weights": (civ.born or civ.personality).weights,
            # The long-term strategy it settled on at its last check-in ("" at the start).
            "strategy": {"kind": civ.strategy_kind, "target": sim.civs[civ.strategy_target].name
                         if civ.strategy_target is not None else None, "since": civ.strategy_since},
            # The war it is preparing, if any: against whom and since when.
            "plan": {"target": sim.civs[civ.plan_target].name, "since": civ.plan_since}
            if civ.plan_target is not None else None,
            "routed_ticks_ago": sim.tick - civ.last_rout if sim.tick - civ.last_rout <= ROUT_MEMORY else None,
            # How long since it last paid anyone tribute (None: never).
            "paid_tribute_ticks": _since(sim, max((tick for (payer, _), tick in diplomacy.tribute_paid.items()
                                                   if payer == civ.id), default=None)),
            "era": tree.eras[tree.era_of(civ.known_techs)],
            "sick": diplomacy.sick(civ),
            "unrest": _unrest(sim, civ.id),
            # How long since it was last at war with anyone.
            "peace_ticks": sim.tick - civ.last_war,
            "population": int(civ.population),
            "territory": len(civ.territory),
            "capitals": [s.name for s in civ.settlements],
            "soldiers": int(civ.soldiers),
            # The most soldiers it can raise. (There is no minimum for declaring war.)
            "max_soldiers": int(diplomacy.mobilization_cap(civ) * civ.population),
            # Soldiers it can train per tick (a levy, plus its barracks); each costs gold and ore.
            "training_per_tick": round(training_rate(civ), 2),
            "army": {unit_id: int(count) for unit_id, count in civ.unit_counts().items() if count >= 1},
            "commanders": [{"name": c.name, "level": c.level}
                           for c in civ.commanders + [a.commander for a in civ.armies if a.commander]],
            "military_power": round(diplomacy.power(civ)),
            "diplomacy_points": int(civ.diplomacy_points),
            "distrusted_ticks_left": max(0, diplomacy.distrust_until.get(civ.id, 0) - sim.tick),
            "storage": {res: int(mods.storage[res]) for res in RESOURCES},
            "resources": {
                res: {"stock": int(civ.resources[res]), "per_tick": round(civ.income[res], 1)} for res in RESOURCES
            },
            "surplus": surplus,
            "lacking": lacking,
            "water": _water_report(civ, mods),
            # What it is short of (ore, stone, gold, food), and whether its people are crowded
            # with no free land left within reach.
            "short_of": _short_of(civ, mods),
            "crowded": _crowded(sim, civ, mods),
        },
        "neighbors": neighbors,
        # The civ a human rules, if any, and how hard the others are to go on it.
        "player": sim.civs[sim.ruler.civ_id].name if sim.ruler.civ_id is not None else None,
        "difficulty": sim.config.difficulty,
        "neutral_regions": sum(1 for region in sim.world.regions if region.neutral),
        # Domination: region points held, and what wins (that many points and regions).
        "points": {"held": sim.points_held(civ), "needed": need_points, "regions_needed": need_regions,
                   "share": round(sim.points_held(civ) / max(1, need_points), 2)},
        # The regions it does not hold that are worth most to it, and why (strategy/geography.py).
        "prizes": [{"region": sim.world.regions[r].name, "held_by": _holder(sim, r), "value": round(v.total, 1),
                    "why": v.reason} for r, v in sim.geography.prizes(civ, sim.tick)],
        "recent_events": [f"tick {e['tick']}: {e['text']}" for e in diplomacy.recent_history(civ.id, HISTORY_LENGTH)],
        "diplomacy_costs": {"open_trade": DEAL_FEE, "form_alliance": ALLIANCE_COST, "declare_war": WAR_COST},
    }


WATER_RICH_RATIO = 1.5  # supply at least this multiple of use counts as water to spare
RICH_RESOURCE = {"iron": "ore", "gold": "gold", "stone": "stone", "fertile_soil": "food", "fish": "food", "game": "food"}
CROWDED = 0.9  # people over housing from which a civ with no free land in reach is crowded
FREE_LAND_RINGS = 2  # native land this many regions away or nearer still counts as room


def _claims(sim, civ, other_id: int) -> dict:
    world = sim.world
    theirs = {r.id for r in world.regions if r.owner == other_id}
    rich = [{"name": name, "resource": RICH_RESOURCE.get(world.deposits.get(tile, ""), "food"),
             "region": world.regions[world.region_of[tile]].name}
            for tile, name in sorted(world.rich.items()) if world.region_of[tile] in theirs]
    lost = [world.regions[r].name for r in sorted(civ.lost_regions) if r in theirs]
    refused = sim.diplomacy.refused_since.get((civ.id, other_id))
    held = {r.id for r in world.regions if r.owner == civ.id}
    touching = sim.military._touching
    gate = next((world.regions[r].name for r in sorted(theirs)
                 if set(world.regions[r].tags) & {"gate", "neck", "bridge"} and touching[r] & held), None)
    return {"rich_nodes": rich, "holds_our_lost_lands": lost, "holds_our_home": civ.home_region in theirs,
            "refused_trade": ({"resource": refused[1], "days": sim.tick - refused[0]} if refused else None),
            "gate_into_our_land": gate}


def _short_of(civ, mods) -> list[str]:
    """Ore, stone and gold its land barely yields, and food when its stores are running down."""
    from ..economy.rules import SETTLEMENT_YIELDS
    capitals = len(civ.settlements)
    short = [res for res in ("ore", "stone") if civ.capacity[res] - SETTLEMENT_YIELDS[res] * capitals < 4]
    if civ.capacity["gold"] - SETTLEMENT_YIELDS["gold"] * capitals < 2:
        short.append("gold")
    if civ.resources["food"] < 0.2 * mods.storage["food"] and civ.income.get("food", 0.0) <= 0:
        short.append("food")
    return short


def _crowded(sim, civ, mods) -> bool:
    if civ.population < CROWDED * mods.housing:
        return False
    held = {r.id for r in sim.world.regions if r.owner == civ.id}
    rings = sim.military._rings(held)
    return not any(region.neutral and rings.get(region.id, 99) <= FREE_LAND_RINGS for region in sim.world.regions)


def _prize(sim, civ, other_id: int) -> dict | None:
    """The region of `other_id`'s worth most to `civ`, if any is worth anything."""
    values = sim.geography.values(civ, sim.tick)
    theirs = [r for r in values if sim.world.regions[r].owner == other_id and values[r].access > 0]
    if not theirs:
        return None
    best = max(theirs, key=lambda r: (values[r].total, -r))
    return {"region": sim.world.regions[best].name, "value": round(values[best].total, 1), "why": values[best].reason}


def _holder(sim, region_id: int) -> str:
    owner = sim.world.regions[region_id].owner
    return sim.civs[owner].name if owner is not None else "natives"


def _water_rich(civ, mods) -> bool:
    supply, use = water_balance(civ, mods)
    return supply >= WATER_RICH_RATIO * max(use, 0.1)


def water_status(urgency: float) -> str:
    if urgency >= 0.7:
        return "critical"
    if urgency >= 0.5:
        return "short"
    if urgency >= 0.3:
        return "tightening"
    return "comfortable"


def _water_report(civ, mods) -> dict:
    """Where the civ stands on water: the one resource it cannot simply put more workers on."""
    supply, use = water_balance(civ, mods)
    urgency = water_urgency(civ, mods)
    ticks_left = int(civ.resources["water"] / (use - supply)) if use > supply else None
    return {
        "supply_per_tick": round(supply, 1),
        "use_per_tick": round(use, 1),
        "ticks_until_dry": ticks_left,  # None while supply covers use
        "urgency": round(urgency, 2),  # 0 comfortable .. 1 dry or about to be
        "status": water_status(urgency),
        "rich": _water_rich(civ, mods),
    }


def _intel(sim, other) -> dict:
    """What an ally is allowed to know about `other`: its army in detail and its stores."""
    diplomacy = sim.diplomacy
    mods = sim.modifiers[other.id]
    enemies = diplomacy.enemies(other.id)
    surplus, lacking = _surplus_and_lacking(other, mods)
    return {
        "soldiers": int(other.soldiers),
        "army": {unit_id: int(count) for unit_id, count in other.unit_counts().items() if count >= 1},
        "army_strength": round(diplomacy.strength(other)),
        "military_power": round(diplomacy.power(other)),
        # No units on the map: "positions" are how the army is divided between its wars.
        "troops_committed": {sim.civs[e].name: int(other.soldiers / len(enemies)) for e in enemies},
        "resources": {res: {"stock": int(other.resources[res]), "cap": int(mods.storage[res])} for res in RESOURCES},
        "surplus": surplus,
        "lacking": lacking,
    }


def _surplus_and_lacking(civ, mods) -> tuple[list[str], list[str]]:
    """Resources a civ is flush with, and ones it cannot produce or is nearly out of."""
    surplus = [res for res in RESOURCES if civ.resources[res] >= SURPLUS_FILL * mods.storage[res]]
    lacking = [
        res for res in RESOURCES
        if res not in surplus and (
            (civ.capacity[res] < 4 and res not in ("gold", "food", "water"))
            or civ.resources[res] < 0.1 * mods.storage[res]
            or (res == "water" and mods.income["water"] < civ.upkeep["water"]))
    ]
    return surplus, lacking
