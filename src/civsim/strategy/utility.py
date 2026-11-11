"""UtilityBrain: the built-in strategist.

No model and no waiting. At each check-in it weighs, for every neighbour, what attacking,
allying and trading would be worth to this civ as things stand, and takes the best. The
weights are the civ's own personality, so a warlike civ and a merchant read the same map
differently. It sees only what any strategist is shown (see context.py): exact numbers
for allies, a rough comparison for everyone else.
"""

from .checkin import WATER_PRIORITY, WATER_URGENT, CheckinRequest, default_offer
from .context import BAND_RATIO

ATTACK_THRESHOLD = 0.5  # an attack must be worth at least this to be launched
ALLY_THRESHOLD = 0.6
WAR_WEARY_TICKS = 300  # a war this old is only kept up from a position of strength
RUNAWAY = 1.5  # a neighbour this many times our size is running away with the game


class UtilityBrain:
    name = "utility"

    def decide(self, request: CheckinRequest) -> dict | None:
        context = request.context
        you = context["you"]
        neighbors = context["neighbors"]
        military = you["weights"].get("military", 1.0)
        thirst = you["water"]["urgency"]
        can_declare = (you["diplomacy_points"] >= context["diplomacy_costs"]["declare_war"]
                       and you["max_soldiers"] >= you["soldiers_needed_to_declare_war"])
        edges = {n["id"]: self._edge(you, n) for n in neighbors}
        my_wars = [n for n in neighbors if n["relation"] == "war"]
        my_enemies = {n["name"] for n in my_wars}
        # Who is dangerous: anyone already set on us, and anyone much stronger within reach.
        threats = {n["name"] for n in neighbors if n["relation"] != "alliance" and (
            n["relation"] == "war" or n["their_stance_toward_you"] == "aggression"
            or (n["in_reach"] and edges[n["id"]] < 0.6))}
        size = you["population"] + you["territory"]
        leader = max(neighbors, key=lambda n: (n["population"] + n["territory"], n["name"]), default=None)
        runaway = leader["name"] if leader and leader["population"] + leader["territory"] >= RUNAWAY * size else None
        supplier = any(n["water_rich"] and n["their_stance_toward_you"] in ("trade", "ally") for n in neighbors)

        stances, notes = [], []
        for n in neighbors:
            edge = edges[n["id"]]
            entry = {"civ": n["name"], "stance": "ignore", "give": "none", "give_per_tick": 0,
                     "want": "none", "want_per_tick": 0, "troop_commitment": 0}
            if n["relation"] == "war":
                weary = (n["war_ticks"] or 0) >= WAR_WEARY_TICKS
                if edge >= 1.3 or (edge >= 0.85 and not weary):
                    entry.update(stance="aggression", troop_commitment=self._commitment(edge, len(my_wars)))
                    notes.append((2, f"pressing the war on {n['name']}"))
                else:
                    notes.append((3, f"the war with {n['name']} is going badly: seeking peace"))
                stances.append(entry)
                continue

            attack, why_attack = self._attack(you, n, edge, military, thirst, supplier, can_declare,
                                              bool(my_wars), runaway)
            ally, why_ally = self._ally(n, edge, thirst, my_enemies, threats, runaway)
            if attack >= ATTACK_THRESHOLD and attack >= ally:
                entry.update(stance="aggression", troop_commitment=self._commitment(edge, len(my_wars) + 1))
                notes.append((4, f"{why_attack}: attacking {n['name']}"))
            elif ally >= ALLY_THRESHOLD:
                entry.update(default_offer(you, n), stance="ally")
                notes.append((1, f"{why_ally}: allying with {n['name']}"))
            elif n["their_stance_toward_you"] == "aggression" and n["relation"] != "alliance":
                notes.append((1, f"wary of {n['name']}"))  # no trade with someone about to attack
            else:
                entry.update(default_offer(you, n), stance="trade")
            stances.append(entry)

        reason = max(notes)[1] if notes else "trading with everyone"
        if thirst >= WATER_PRIORITY:
            reason += f"; water is {you['water']['status']}"
        return {"reason": reason[0].upper() + reason[1:] + ".", "stances": stances}

    @staticmethod
    def _edge(you: dict, n: dict) -> float:
        """Our military power over theirs: exact for an ally, otherwise from the rough comparison."""
        if n["intel"]:
            return you["military_power"] / max(n["intel"]["military_power"], 1)
        return 1 / BAND_RATIO[n["army_vs_yours"]]

    @staticmethod
    def _commitment(edge: float, wars: int) -> float:
        """More of the army against an equal than against a pushover, and less with every front."""
        share = 0.9 - 0.2 * (edge - 1.0)
        return round(max(0.4, min(0.9, share / max(1, wars) ** 0.5)), 2)

    @staticmethod
    def _attack(you, n, edge, military, thirst, supplier, can_declare, at_war, runaway) -> tuple[float, str]:
        if not (can_declare and n["in_reach"]) or n["truce"] or n["relation"] == "alliance":
            return 0.0, ""
        score, why = (edge - 1.0) * 1.2 * military, f"{n['name']} is weaker"
        if n["at_war_with"]:
            score += 0.4
            why = f"{n['name']} is weaker and already fighting {n['at_war_with'][0]}"
        if n["distrusted_ticks_left"]:
            score += 0.2  # nobody will come to its aid
        allies = [name for name in n["allied_with"] if name != you["name"]]
        score -= 0.5 * len(allies)
        if runaway == n["name"] and edge >= 1.0:
            score += 0.3
            why = f"{n['name']} is running away with it"
        if at_war:
            score -= 1.0 if edge < 2.2 else 0.3  # a second front only against the helpless
        if n["your_current_stance"] == "aggression":
            score += 0.2  # see a decision through rather than flip every check-in
        if thirst >= WATER_URGENT and n["water_rich"] and not supplier:
            score += 0.8
            why = f"the wells are failing and {n['name']} has water"
        elif thirst >= WATER_PRIORITY and n["water_rich"]:
            score = min(score, 0.0)  # whoever has water is courted, not fought, while there is a choice
        if edge < 1.15:
            score = min(score, 0.0)  # never start a war from parity
        return score, why

    @staticmethod
    def _ally(n, edge, thirst, my_enemies, threats, runaway) -> tuple[float, str]:
        if n["truce"] and n["relation"] != "alliance":
            return 0.0, ""
        score, why = 0.0, f"{n['name']} is a useful friend"
        if n["relation"] == "alliance":
            score += 0.7
            why = f"standing by {n['name']}"
        if n["their_stance_toward_you"] == "ally":
            score += 0.3
        shared = [name for name in n["at_war_with"] if name in my_enemies]
        if shared:
            score += 0.6
            why = f"{n['name']} is also fighting {shared[0]}"
        if threats - {n["name"]} and n["name"] not in threats and edge <= 2.0:
            score += 0.6
            why = f"threatened by {sorted(threats - {n['name']})[0]}"
        if runaway and runaway != n["name"] and edge <= 2.0:
            score += 0.4
            why = f"{runaway} is running away with it"
        if thirst >= WATER_URGENT and n["water_rich"]:
            score += 0.6
            why = f"{n['name']} has the water we need"
        if n["distrusted_ticks_left"]:
            score -= 0.5
        if n["name"] in threats:
            score -= 0.6
        return score, why
