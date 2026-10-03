"""Builds what a civ's strategist gets to see at a check-in: its own state in full,
each neighbour's visible state, and a short history of recent dealings.

How much is visible depends on the relationship. Everyone sees a neighbour's
public facts and a rough comparison of its army to their own. Only allies see
intel: exact army numbers, where the army is committed, and what is in store.
"""

import math

from ..diplomacy.rules import ALLIANCE_COST, DEAL_FEE, SURPLUS_FILL, WAR_COST
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


def stance_context(sim, civ) -> dict:
    diplomacy = sim.diplomacy
    tree = sim.tech_tree
    mods = sim.modifiers[civ.id]

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
        offer = None
        if theirs.give:
            offer = {"gives": theirs.give, "wants": theirs.want}
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
            "distrusted_ticks_left": max(0, diplomacy.distrust_until.get(other_id, 0) - sim.tick),
            "relation": relation.status,
            "war_ticks": sim.tick - relation.war.start if relation.war else None,
            "at_war_with": [sim.civs[e].name for e in diplomacy.enemies(other_id)],
            "allied_with": [sim.civs[e].name for e in diplomacy.allies(other_id)],
            "truce": sim.tick < relation.truce_until,
            "in_reach": diplomacy.in_reach(civ.id, other_id, sim.tick),
            "active_deal": deal_text,
            "their_stance_toward_you": theirs.stance.value,
            "their_trade_offer": offer,
            "your_current_stance": diplomacy.intent(civ.id, other_id).stance.value,
        })

    surplus, lacking = _surplus_and_lacking(civ, mods)
    return {
        "tick": sim.tick,
        "you": {
            "id": civ.id,
            "name": civ.name,
            "personality": civ.personality.name,
            "weights": civ.personality.weights,
            "era": tree.eras[tree.era_of(civ.known_techs)],
            "population": int(civ.population),
            "territory": len(civ.territory),
            "capitals": [s.name for s in civ.settlements],
            "soldiers": int(civ.soldiers),
            # War cannot be declared with fewer soldiers than this; max_soldiers is the most it can raise.
            "soldiers_needed_to_declare_war": math.ceil(diplomacy.war_army(civ)),
            "max_soldiers": int(diplomacy.mobilization_cap(civ) * civ.population),
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
        },
        "neighbors": neighbors,
        "neutral_regions": sum(1 for region in sim.world.regions if region.neutral),
        "recent_events": [f"tick {e['tick']}: {e['text']}" for e in diplomacy.recent_history(civ.id, HISTORY_LENGTH)],
        "diplomacy_costs": {"open_trade": DEAL_FEE, "form_alliance": ALLIANCE_COST, "declare_war": WAR_COST},
    }


WATER_RICH_RATIO = 1.5  # supply at least this multiple of use counts as water to spare


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
