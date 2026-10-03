"""Strategy brains: things that answer a check-in.

LLMBrain asks a language model. RuleBrain is a deterministic stand-in with the
same inputs and outputs, used for tests and for running without a model. Both
return the raw reply dict; the simulation validates it either way.
"""

import logging
from typing import Protocol

from ..economy.rules import RESOURCES
from ..llm import LLMClient, LLMError
from . import prompt
from .checkin import CheckinRequest, default_offer
from .context import BAND_RATIO

log = logging.getLogger(__name__)

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


class Brain(Protocol):
    name: str

    def decide(self, request: CheckinRequest) -> dict | None:
        """The reply to a check-in, or None if no answer could be produced."""
        ...


class LLMBrain:
    def __init__(self, client: LLMClient):
        self.client = client
        self.name = client.name

    def decide(self, request: CheckinRequest) -> dict | None:
        system, user, schema = prompt.build(request)
        try:
            return self.client.complete_json(system, user, schema)
        except LLMError as exc:
            log.warning("check-in for civ %d at tick %d got no answer: %s", request.civ_id, request.tick, exc)
            return None


class RuleBrain:
    """Simple, personality-driven policy: fight the weak if warlike, otherwise trade, ally when threatened."""

    name = "rules"

    def decide(self, request: CheckinRequest) -> dict | None:
        if request.kind == "invent":
            return self._invent(request.context)
        return self._stances(request.context)

    def _stances(self, context: dict) -> dict:
        you = context["you"]
        warlike = you["weights"]["military"] >= 1.15
        at_war = any(n["relation"] == "war" for n in context["neighbors"])
        offer = default_offer(you)
        stances = []
        for n in context["neighbors"]:
            # Exact for allies; for everyone else only the rough comparison is known.
            if n["intel"]:
                edge = you["military_power"] / max(n["intel"]["military_power"], 1)
            else:
                edge = 1 / BAND_RATIO[n["army_vs_yours"]]
            entry = {"civ": n["name"], "stance": "ignore", "give": "none", "give_per_tick": 0,
                     "want": "none", "want_per_tick": 0, "troop_commitment": 0}
            if n["relation"] == "war":
                # Keep fighting while it is going well; otherwise seek peace.
                if edge >= 0.9 and (n["war_ticks"] or 0) < 250:
                    entry.update(stance="aggression", troop_commitment=0.7)
            elif (warlike and not at_war and not n["truce"] and n["relation"] != "alliance" and edge >= 1.4
                  and you["resources"]["gold"]["stock"] >= 2 * context["gold_costs"]["declare_war"]):
                entry.update(stance="aggression", troop_commitment=0.6)
            else:
                threatened = at_war or n["their_stance_toward_you"] == "ally" or n["relation"] == "alliance"
                entry.update(offer, stance="ally" if threatened else "trade")
            stances.append(entry)
        return {"reason": "Rule-based policy.", "stances": stances}

    def _invent(self, context: dict) -> dict:
        you = context["you"]
        caps = context["effect_caps"]
        fill = {res: you["resources"][res] / max(you["storage"][res], 1) for res in RESOURCES}
        scarce = min(RESOURCES, key=lambda res: (fill[res], res))
        second = "military" if you["at_war"] else "science_mult"
        materials = sorted((res for res in RESOURCES if res != "food"), key=lambda res: (-fill[res], res))[:2]
        number = len(context["already_invented"])
        return {
            "name": f"{you['name']} {scarce.capitalize()} Methods {ROMAN[number % len(ROMAN)]}",
            "description": f"Refined ways of working {scarce}.",
            "effects": [
                {"type": "yield_mult", "resource": scarce, "amount": 0.75 * caps["yield_mult"]},
                {"type": second, "resource": "none", "amount": 0.5 * caps[second]},
            ],
            "materials": materials,
        }


def make_brain(provider: str, model: str | None = None, base_url: str | None = None) -> Brain:
    """"rules" for the deterministic policy, otherwise an LLM provider name (see llm.make_client)."""
    if provider == "rules":
        return RuleBrain()
    from ..llm import make_client

    return LLMBrain(make_client(provider, model, base_url))
