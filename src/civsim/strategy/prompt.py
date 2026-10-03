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
    DISTRUST_TICKS,
    MAX_RATE,
    MIN_RATE,
    WAR_COST,
)
from ..economy.rules import RESOURCES
from ..tech.invention import EFFECT_LABELS, NEEDS_RESOURCE
from .checkin import CHECKIN_INTERVAL, CheckinRequest

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

INVENTION_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(EFFECT_LABELS)},
                    "resource": {"type": "string", "enum": [*RESOURCES, "all", "none"]},
                    "amount": {"type": "number"},
                },
                "required": ["type", "resource", "amount"],
            },
        },
        "materials": {"type": "array", "items": {"type": "string", "enum": [r for r in RESOURCES if r != "food"]}},
    },
    "required": ["name", "description", "effects", "materials"],
}


def build(request: CheckinRequest) -> tuple[str, str, dict]:
    """(system prompt, user prompt, reply schema) for a check-in."""
    if request.kind == "invent":
        return _invention_prompt(request.context)
    return _stance_prompt(request.context)


def _stance_prompt(context: dict) -> tuple[str, str, dict]:
    you = context["you"]
    names = [n["name"] for n in context["neighbors"]]
    system = f"""You are the ruler of {you["name"]}, one of {len(names) + 1} civilizations competing in a strategy simulation. {TRAITS.get(you["personality"], "")}

Every {CHECKIN_INTERVAL} ticks you choose one stance toward each other civilization. Your advisers carry it out between check-ins; you only set intent.

Stances:
- trade: offer one resource ("give") and ask for another ("want"). A deal opens only if they also choose trade or ally toward you. Each side then sends what it offered every tick for {DEAL_DURATION} ticks. Opening costs {DEAL_FEE} gold. "storage" is the most you can hold of each resource. Give something from your "surplus"; want something from your "lacking". Gold can be given or wanted like any resource.
- ally: an alliance forms only if they also choose ally. It gives both sides stronger defence and faster science, costs {ALLIANCE_COST} gold to form and {ALLIANCE_UPKEEP} gold per tick, and trade terms still apply. An alliance is a defensive pact: if your ally is attacked you are automatically at war with the attacker until that war ends, and the same holds for them. A war your ally starts is your choice: choose aggression toward the same civilization to join it and share the spoils by army strength, or stay out and get nothing. Allies share "intel": exact army numbers, where their troops are committed and what they hold in store. About everyone else you only know "army_vs_yours", a rough comparison of their army to yours.
- ignore: no dealings.
- aggression: go to war for their land. Declaring costs {WAR_COST} gold, and soldiers cost gold, ore and food every tick. It only works if "in_reach" is true and there is no truce; otherwise your border creeps toward them first. "troop_commitment" from 0.1 to 1.0 is how much of your "military_power" to raise. Attacking a neighbour whose "army_vs_yours" is stronger loses land. A neighbour whose capital is reached surrenders and pays tribute. Choosing aggression toward an ally is betrayal: the alliance breaks and you catch them off guard for the opening of the war, but for {DISTRUST_TICKS} ticks afterwards ("distrusted_ticks_left") nobody will form an alliance with you and trade costs you more and brings in less.

Resources are {", ".join(RESOURCES)}. Amounts per tick are between {MIN_RATE} and {MAX_RATE}. For stances that do not use a field, put "none" or 0.

Reply with JSON only: "reason" (one or two sentences), then "stances" with exactly one entry for each of: {", ".join(names)}."""
    visible = {key: value for key, value in you.items() if key not in ("id", "weights")}
    shown = {**context, "you": visible,
             "neighbors": [{k: v for k, v in n.items() if k != "id"} for n in context["neighbors"]]}
    user = f"Tick {context['tick']}. The situation:\n{json.dumps(shown, indent=1)}\n\nChoose your stances."
    return system, user, STANCE_SCHEMA


def _invention_prompt(context: dict) -> tuple[str, str, dict]:
    you = context["you"]
    caps = context["effect_caps"]
    lines = []
    for effect_type in EFFECT_LABELS:
        needs = " (needs a resource)" if effect_type in NEEDS_RESOURCE else ""
        lines.append(f"- {effect_type}: amount up to {caps[effect_type]}{needs}")
    system = f"""You are the chief scholar of {you["name"]}, a {you["personality"].lower()} civilization that has mastered every known technology. Propose ONE new technology for your people to research next.

Choose a name that fits what the civilization already knows, a one-sentence description, {context["max_effects"]} or fewer effects, and up to two materials (from wood, stone, ore, gold) that it takes to develop. Prefer materials you have in surplus and effects that fix what you lack.

Effect types:
{chr(10).join(lines)}
For yield_mult, "resource" may also be "all" (amount up to {caps["yield_mult_all"]}). For other types put "none".

Amounts above the limits are reduced to them, and the game sets the research cost from how strong the effects are. Do not repeat a name from "known_techs" or "already_invented".

Reply with JSON only."""
    shown = {key: value for key, value in context.items() if key not in ("effect_caps", "max_effects")}
    shown["you"] = {key: value for key, value in you.items() if key != "id"}
    user = f"Your civilization:\n{json.dumps(shown, indent=1)}\n\nPropose the technology."
    return system, user, INVENTION_SCHEMA
