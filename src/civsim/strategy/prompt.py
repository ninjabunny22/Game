"""Prompts and reply schemas for the language-model strategist.

One call per civ per check-in. The system prompt fixes the role and the rules; the
user prompt is the check-in context as JSON. The reply must match a JSON schema,
with the free-text reason first so the model reasons before it commits.
"""

import json

from ..diplomacy import Stance
from ..diplomacy.rules import (
    ALLIANCE_COST,
    ALLIANCE_UPKEEP,
    DEAL_DURATION,
    DEAL_FEE,
    DIPLOMACY_GAIN,
    DISTRUST_TICKS,
    MAX_RATE,
    MIN_RATE,
    WAR_COST,
)
from ..economy.rules import RESOURCES
from .checkin import CHECKIN_INTERVAL, WATER_PRIORITY, WATER_URGENT, CheckinRequest

TRAITS = {
    "Expansionist": "You want land above all and see weaker neighbours as territory to be taken.",
    "Builder": "You value industry and infrastructure, and prefer stable neighbours you can build beside.",
    "Scholar": "You value knowledge above all and avoid wars that would distract from it.",
    "Merchant": "You value wealth and see every neighbour as a customer first.",
    "Agrarian": "You value a large, well-fed population and defend your farmland fiercely.",
}

_RESOURCE_OR_NONE = [*RESOURCES, "none"]

STANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "stances": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "civ": {"type": "string"},
                    "stance": {"type": "string", "enum": [stance.value for stance in Stance]},
                    "give": {"type": "string", "enum": _RESOURCE_OR_NONE},
                    "give_per_tick": {"type": "number"},
                    "want": {"type": "string", "enum": _RESOURCE_OR_NONE},
                    "want_per_tick": {"type": "number"},
                    "troop_commitment": {"type": "number"},
                },
                "required": ["civ", "stance", "give", "give_per_tick", "want", "want_per_tick", "troop_commitment"],
            },
        },
    },
    "required": ["reason", "stances"],
}

def build(request: CheckinRequest) -> tuple[str, str, dict]:
    """(system prompt, user prompt, reply schema) for a check-in."""
    return _stance_prompt(request.context)


def _water_alert(you: dict) -> str:
    """A line a small model will not miss, only when water actually needs attention."""
    water = you["water"]
    if water["urgency"] < WATER_PRIORITY:
        return ""
    left = water["ticks_until_dry"]
    when = "you are already dry" if left == 0 else (
        f"your stores run dry in about {left} ticks" if left is not None else "you have almost no margin left")
    return (f"WATER IS {water['status'].upper()} (urgency {water['urgency']}): you use {water['use_per_tick']} "
            f"per tick against a supply of {water['supply_per_tick']}, and {when}. ")


def _stance_prompt(context: dict) -> tuple[str, str, dict]:
    you = context["you"]
    names = [n["name"] for n in context["neighbors"]]
    system = f"""You are the ruler of {you["name"]}, one of {len(names) + 1} civilizations competing in a strategy simulation. {TRAITS.get(you["personality"], "")}

Every {CHECKIN_INTERVAL} ticks you choose one stance toward each other civilization. Your advisers carry it out between check-ins; you only set intent. Diplomatic actions are paid for with "diplomacy_points": you earn {DIPLOMACY_GAIN:g} per tick automatically and they cannot be traded.

Stances:
- trade: offer one resource ("give") and ask for another ("want"). A deal opens only if they also choose trade or ally toward you. Each side then sends what it offered every tick for {DEAL_DURATION} ticks. Opening costs {DEAL_FEE} diplomacy points. "storage" is the most you can hold of each resource. Give something from your "surplus"; want something from your "lacking". Gold can be given or wanted like any resource.
- ally: an alliance forms only if they also choose ally. It gives both sides stronger defence and faster science, costs {ALLIANCE_COST} diplomacy points to form and {ALLIANCE_UPKEEP} per tick, and trade terms still apply. An alliance is a defensive pact: if your ally is attacked you are automatically at war with the attacker until that war ends, and the same holds for them. A war your ally starts is your choice: choose aggression toward the same civilization to join it and share the spoils by army strength, or stay out and get nothing. Allies share "intel": exact army numbers, where their troops are committed and what they hold in store. About everyone else you only know "army_vs_yours", a rough comparison of their army to yours.
- ignore: no dealings.
- aggression: go to war for their land. Declaring costs {WAR_COST} diplomacy points, and soldiers cost gold, ore and food every tick. It only works if "in_reach" is true and there is no truce; otherwise your border creeps toward them first. "troop_commitment" from 0.1 to 1.0 is how much of your "military_power" to raise. Attacking a neighbour whose "army_vs_yours" is stronger loses land. The map is divided into regions, each with a capital ("capitals" lists the ones a civilization holds, its own capital first). Taking a region's capital takes the whole region. A civilization that loses its own capital pays tribute and moves to another capital it holds; one with no capitals left is destroyed. Regions no civilization holds belong to natives, which your advisers deal with on their own. Choosing aggression toward an ally is betrayal: the alliance breaks and you catch them off guard for the opening of the war, but for {DISTRUST_TICKS} ticks afterwards ("distrusted_ticks_left") nobody will form an alliance with you and trade costs you more and brings in less.

Resources are {", ".join(RESOURCES)}. Water is not gathered by workers: it comes from rivers, lakes and (with Water Purification) coast inside your borders, your people and farms drink it every tick, and your population shrinks while you are out of it. Your "water" block gives supply, use, "ticks_until_dry" and an "urgency" from 0 to 1. Let urgency decide how much water matters: below {WATER_PRIORITY} you are comfortable, do not chase water you do not need (and if you are "rich" in it, sell it to neighbours who want it). From {WATER_PRIORITY} up, ask for water before anything else, never give yours away, and favour trade with neighbours marked "water_rich". From {WATER_URGENT} up it is as urgent as food: want water in every trade, seek alliance with a water_rich neighbour, and if none will deal and one is weaker and in reach, taking their land is a legitimate answer. Amounts per tick are between {MIN_RATE} and {MAX_RATE}. For stances that do not use a field, put "none" or 0.

Reply with JSON only: "reason" (one or two sentences), then "stances" with exactly one entry for each of: {", ".join(names)}."""
    visible = {key: value for key, value in you.items() if key not in ("id", "weights")}
    shown = {**context, "you": visible,
             "neighbors": [{k: v for k, v in n.items() if k != "id"} for n in context["neighbors"]]}
    user = f"Tick {context['tick']}. The situation:\n{json.dumps(shown, indent=1)}\n\n{_water_alert(you)}Choose your stances."
    return system, user, STANCE_SCHEMA
