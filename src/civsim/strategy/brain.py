"""Strategy brains: things that answer a check-in.

UtilityBrain (utility.py) is the strategist the game is played with. RuleBrain is a
simpler deterministic policy with the same inputs and outputs, used by the tests. Both
return the raw reply dict; the simulation validates it either way.
"""

from typing import Protocol

from .checkin import WATER_PRIORITY, WATER_URGENT, CheckinRequest, default_offer
from .context import BAND_RATIO


class Brain(Protocol):
    name: str

    def decide(self, request: CheckinRequest) -> dict | None:
        """The reply to a check-in, or None if no answer could be produced."""
        ...


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
        # No war without the influence to declare it.
        can_declare = you["diplomacy_points"] >= context["diplomacy_costs"]["declare_war"]
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


def make_brain(name: str = "utility") -> Brain:
    """"utility" for the built-in strategist, "rules" for the simple deterministic policy."""
    if name == "utility":
        from .utility import UtilityBrain

        return UtilityBrain()
    if name == "rules":
        return RuleBrain()
    raise ValueError(f'unknown strategist {name!r}: expected "utility" or "rules"')
