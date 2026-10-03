"""Builds what a civ's strategist gets to see at a check-in: its own state in full,
each neighbour's visible state, and a short history of recent dealings."""

from ..diplomacy.rules import ALLIANCE_COST, DEAL_FEE, SURPLUS_FILL, WAR_COST
from ..economy.rules import RESOURCES

HISTORY_LENGTH = 8


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
        surplus, lacking = _surplus_and_lacking(other, sim.modifiers[other_id])
        neighbors.append({
            "id": other_id,
            "name": other.name,
            "era": tree.eras[tree.era_of(other.known_techs)],
            "population": int(other.population),
            "territory": len(other.territory),
            "soldiers": int(other.soldiers),
            "military_power": round(diplomacy.power(other)),
            "relation": relation.status,
            "war_ticks": sim.tick - relation.war.start if relation.war else None,
            "truce": sim.tick < relation.truce_until,
            "in_reach": diplomacy.in_reach(civ.id, other_id, sim.tick),
            "active_deal": deal_text,
            "their_stance_toward_you": theirs.stance.value,
            "their_trade_offer": offer,
            "your_current_stance": diplomacy.intent(civ.id, other_id).stance.value,
            "surplus": surplus,
            "lacking": lacking,
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
            "soldiers": int(civ.soldiers),
            "military_power": round(diplomacy.power(civ)),
            "storage": {res: int(mods.storage[res]) for res in RESOURCES},
            "resources": {
                res: {"stock": int(civ.resources[res]), "per_tick": round(civ.income[res], 1)} for res in RESOURCES
            },
            "surplus": surplus,
            "lacking": lacking,
        },
        "neighbors": neighbors,
        "recent_events": [f"tick {e['tick']}: {e['text']}" for e in diplomacy.recent_history(civ.id, HISTORY_LENGTH)],
        "gold_costs": {"open_trade": DEAL_FEE, "form_alliance": ALLIANCE_COST, "declare_war": WAR_COST},
    }


def invention_context(sim, civ) -> dict:
    tree = sim.tech_tree
    mods = sim.modifiers[civ.id]
    rules = sim.invention_rules
    surplus, lacking = _surplus_and_lacking(civ, mods)
    return {
        "tick": sim.tick,
        "you": {
            "id": civ.id,
            "name": civ.name,
            "personality": civ.personality.name,
            "population": int(civ.population),
            "at_war": bool(sim.diplomacy.enemies(civ.id)),
            "resources": {res: int(civ.resources[res]) for res in RESOURCES},
            "storage": {res: int(mods.storage[res]) for res in RESOURCES},
            "surplus": surplus,
            "lacking": lacking,
        },
        "known_techs": [tree.techs[t].name for t in civ.known_techs],
        "already_invented": [t.name for t in tree.invented_by(civ.id)],
        "effect_caps": rules.caps,
        "max_effects": rules.max_effects,
    }


def _surplus_and_lacking(civ, mods) -> tuple[list[str], list[str]]:
    """Resources a civ is flush with, and ones it cannot produce or is nearly out of."""
    surplus = [res for res in RESOURCES if civ.resources[res] >= SURPLUS_FILL * mods.storage[res]]
    lacking = [
        res for res in RESOURCES
        if res not in surplus and (
            (civ.capacity[res] < 4 and res not in ("gold", "food")) or civ.resources[res] < 0.1 * mods.storage[res])
    ]
    return surplus, lacking
