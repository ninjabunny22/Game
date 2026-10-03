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
from .checkin import WATER_PRIORITY, WATER_URGENT, CheckinRequest, default_offer
from .context import BAND_RATIO

log = logging.getLogger(__name__)

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
        return self._stances(request.context)

    def _stances(self, context: dict) -> dict:
        you = context["you"]
        warlike = you["weights"]["military"] >= 1.15
        at_war = any(n["relation"] == "war" for n in context["neighbors"])
        thirst = you["water"]["urgency"]
        # No war without the influence to declare it and the people to raise an army worth the name.
        can_declare = (you["diplomacy_points"] >= context["diplomacy_costs"]["declare_war"]
                       and you["max_soldiers"] >= you["soldiers_needed_to_declare_war"])
        # Is anyone with water to spare willing to deal? If so, there is no call to fight for it.
        supplier = any(n["water_rich"] and n["their_stance_toward_you"] in ("trade", "ally")
                       for n in context["neighbors"])
        stances = []
        for n in context["neighbors"]:
            # Exact for allies; for everyone else only the rough comparison is known.
            if n["intel"]:
                edge = you["military_power"] / max(n["intel"]["military_power"], 1)
            else:
                edge = 1 / BAND_RATIO[n["army_vs_yours"]]
            entry = {"civ": n["name"], "stance": "ignore", "give": "none", "give_per_tick": 0,
                     "want": "none", "want_per_tick": 0, "troop_commitment": 0}
            offer = default_offer(you, n)
            peaceable = not n["truce"] and n["relation"] != "alliance"
            # Thirst changes who is worth courting and who is worth fighting.
            courting = thirst >= WATER_PRIORITY and n["water_rich"]
            desperate = (thirst >= WATER_URGENT and n["water_rich"] and not supplier and n["in_reach"]
                         and peaceable and not at_war and edge >= 1.2 and can_declare)
            if n["relation"] == "war":
                # Keep fighting while it is going well; otherwise seek peace.
                if edge >= 0.9 and (n["war_ticks"] or 0) < 250:
                    entry.update(stance="aggression", troop_commitment=0.7)
            elif desperate:
                # Nobody will sell and the wells are failing: take the water.
                entry.update(stance="aggression", troop_commitment=0.8)
            elif warlike and not at_war and peaceable and edge >= 1.4 and can_declare and not courting:
                entry.update(stance="aggression", troop_commitment=0.6)
            else:
                threatened = at_war or n["their_stance_toward_you"] == "ally" or n["relation"] == "alliance"
                # A civ in real need ties itself to whoever has water.
                bind = courting and thirst >= WATER_URGENT
                entry.update(offer, stance="ally" if threatened or bind else "trade")
            stances.append(entry)
        reason = "Rule-based policy."
        if thirst >= WATER_PRIORITY:
            reason = f"Rule-based policy; water is {you['water']['status']}."
        return {"reason": reason, "stances": stances}


def make_brain(provider: str, model: str | None = None, base_url: str | None = None) -> Brain:
    """"rules" for the deterministic policy, otherwise an LLM provider name (see llm.make_client)."""
    if provider == "rules":
        return RuleBrain()
    from ..llm import make_client

    return LLMBrain(make_client(provider, model, base_url))
