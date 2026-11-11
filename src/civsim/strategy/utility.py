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
ALLIANCE_FATIGUE = 0.6  # how much an alliance with no purpose left loses of its appeal ...
ALLIANCE_WEARS = 800  # ... over this many ticks
RIVAL_ATTACK = 0.3  # how much more a war with the other of the two strongest is worth
RIVAL_ALLY = 0.5  # ... and how much less an alliance with it
RIVAL_BETRAYAL = 0.8  # ... and the share of the usual edge at which that ally is turned on
BULLY = 1.4  # from this many times a neighbour's size a civ wants the war for its own sake ...
BULLY_MAX = 0.8  # ... more the bigger the gap, up to this
OVERBEARING = 1.6  # ... and from this, no past friendship stands in the way
LONG_PEACE = 350  # ticks at peace, divided by its taste for war, after which any civ starts to itch
RESTLESS_PER_TICK = 0.8 / 250  # ... more with every season that passes, up to RESTLESS_MAX
RESTLESS_MAX = 1.6
EXPOSED_EDGE = 1.3  # how much weaker a civ caught off balance is taken to be
SICK_EDGE = 1.3  # how much weaker a civ struck by sickness is taken to be
SICK_BETRAYAL = 0.75  # an ally laid low is turned on at this share of the usual edge and warlikeness
BETRAYAL_EDGE = 1.8  # how far ahead a warlike civ must be before it turns on an ally
BETRAYAL_MILITARY = 1.3  # ... and how warlike
STRATEGY_STICKINESS = 1.3  # a strategy already in hand counts for this much more than a new one
STRATEGY_FOCUS = {"conquest": "military", "survival": "military", "science": "science",
                  "prosperity": "economy", "expansion": "expansion"}


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
        strategy = self._strategy(context, edges, threats)
        # Allies count: what they bring to a fight, and the wars they are already in.
        friends = [n for n in neighbors if n["relation"] == "alliance"]
        backing = 1 + sum(n["intel"]["military_power"] for n in friends if n["intel"]) / max(you["military_power"], 1)
        friends_wars = {name: n["name"] for n in friends for name in n["at_war_with"]}

        stances, notes = [], []
        for n in neighbors:
            edge = edges[n["id"]]
            entry = {"civ": n["name"], "stance": "ignore", "give": "none", "give_per_tick": 0,
                     "want": "none", "want_per_tick": 0, "troop_commitment": 0}
            if n["relation"] == "war":
                weary = (n["war_ticks"] or 0) >= WAR_WEARY_TICKS or you.get("sick")
                if n.get("sick") and not you.get("sick"):
                    edge = max(edge, 1.0) * SICK_EDGE  # they are laid low: now is the time
                if edge >= 1.3 or (edge >= 0.85 and not weary):
                    entry.update(stance="aggression", troop_commitment=self._commitment(edge, len(my_wars)))
                    notes.append((2, f"pressing the war on {n['name']}"))
                else:
                    notes.append((3, f"the war with {n['name']} is going badly: seeking peace"))
                stances.append(entry)
                continue

            attack, why_attack = self._attack(you, n, edge, military, thirst, supplier, can_declare,
                                              bool(my_wars), runaway, strategy, backing, friends_wars)
            ally, why_ally = self._ally(n, edge, thirst, my_enemies, threats, runaway, len(friends))
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
        return {"reason": reason[0].upper() + reason[1:] + ".", "stances": stances, "strategy": strategy}

    # -- the long view ---------------------------------------------------------

    def _strategy(self, context: dict, edges: dict, threats: set) -> dict:
        """What the civ is working toward over the long run. It follows from the civ's own
        leanings and its position, and is kept from one check-in to the next unless something
        else has become clearly better: a civ that changed its mind every time would get nowhere."""
        you, neighbors = context["you"], context["neighbors"]
        weights = you["weights"]
        before = you.get("strategy") or {}
        options: dict[str, tuple[float, str | None]] = {
            "science": (0.9 * weights.get("science", 1.0), None),
            "prosperity": (0.85 * weights.get("wealth", 1.0), None),
            "expansion": (0.9 * weights.get("expansion", 1.0) if context.get("neutral_regions", 0) > 0 else 0.0, None),
        }
        # Conquest needs someone it can reach and beat; an old grudge points the way.
        prey = [n for n in neighbors if n["in_reach"] and n["relation"] != "alliance" and edges[n["id"]] >= 1.15]
        if prey:
            def worth(n: dict) -> float:
                return edges[n["id"]] - 0.9 + 0.2 * max(0.0, -n.get("standing", 0.0)) \
                    + (0.3 if before.get("kind") == "conquest" and before.get("target") == n["name"] else 0.0)
            target = max(prey, key=lambda n: (worth(n), n["name"]))
            options["conquest"] = (weights.get("military", 1.0) * min(worth(target), 1.6), target["name"])
        # Outmatched and under threat, nothing else matters.
        stronger = sorted(n["name"] for n in neighbors if n["name"] in threats and edges[n["id"]] < 0.8)
        if stronger:
            options["survival"] = (1.7, stronger[0])
        scores = {kind: score * (STRATEGY_STICKINESS if kind == before.get("kind") else 1.0)
                  for kind, (score, _) in options.items()}
        kind = max(scores, key=lambda k: (scores[k], k))
        target = options[kind][1]
        text = {"conquest": f"Conquer {target}", "survival": f"Survive {target}", "science": "Out-think the others",
                "prosperity": "Grow rich by trade", "expansion": "Settle the open land"}[kind]
        return {"kind": kind, "target": target, "focus": STRATEGY_FOCUS[kind], "text": text}

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
    def _attack(you, n, edge, military, thirst, supplier, can_declare, at_war, runaway, strategy,
                backing=1.0, friends_wars=None) -> tuple[float, str]:
        if not (can_declare and n["in_reach"]) or n["truce"] or you.get("sick"):
            return 0.0, ""  # nor does a civ that is itself sick start anything
        sick = bool(n.get("sick"))
        if sick:
            edge *= SICK_EDGE
        # Caught off balance: its army is away, or has just been beaten.
        exposed = bool(n.get("army_abroad")) or n.get("routed_ticks_ago") is not None
        if exposed:
            edge *= EXPOSED_EDGE
        if n["relation"] == "alliance":
            # Only the warlike turn on a friend, and only a lone one they can crush, with no
            # betrayal already against their name.
            lone = not [name for name in n["allied_with"] if name != you["name"]]
            ease = SICK_BETRAYAL if sick else 1.0  # a friend's weakness is some rulers' opportunity
            if n.get("rival") and not sick:
                # The two strongest working together: whoever strikes first takes it all.
                if (military >= 1.0 and edge >= BETRAYAL_EDGE * RIVAL_BETRAYAL and not at_war
                        and not you["distrusted_ticks_left"] and n.get("standing", 0.0) < 0.5):
                    return 1.0 + (edge - BETRAYAL_EDGE * RIVAL_BETRAYAL) * military, \
                        f"only {n['name']} stands between us and first place"
            if sick and military >= BETRAYAL_MILITARY * ease and edge >= BETRAYAL_EDGE * ease and lone \
                    and not at_war and not you["distrusted_ticks_left"] and n.get("standing", 0.0) < 1.5:
                return 1.1 + (edge - BETRAYAL_EDGE * ease) * military, f"{n['name']} is sick and cannot defend itself"
            if (military < BETRAYAL_MILITARY or edge < BETRAYAL_EDGE or not lone or at_war
                    or strategy["kind"] == "survival" or you["distrusted_ticks_left"]
                    or n.get("standing", 0.0) >= 1.5):
                return 0.0, ""
            return 0.9 + (edge - BETRAYAL_EDGE) * military, f"{n['name']} trusts us and is weak"
        friends_wars = friends_wars or {}
        joint = n["name"] in friends_wars or runaway == n["name"]
        together = edge * backing if joint else edge  # with allies beside us, when it is their fight too
        score, why = (edge - 1.0) * 1.2 * military, f"{n['name']} is weaker"
        if n["at_war_with"]:
            score += 0.4
            why = f"{n['name']} is weaker and already fighting {n['at_war_with'][0]}"
        if sick:
            score += 0.35
            why = f"{n['name']} is laid low by sickness"
        if n.get("rival"):
            score += RIVAL_ATTACK
            why = f"only {n['name']} stands between us and first place"
        if exposed and not sick:
            score += 0.3
            why = (f"{n['name']}'s army is away" if n.get("army_abroad") else f"{n['name']} has just lost a battle")
        if n["distrusted_ticks_left"]:
            score += 0.2  # nobody will come to its aid
        # The long view: the civ it has set out to conquer is attacked sooner, and a civ set on
        # something else is slower to fight at all.
        if strategy["kind"] == "conquest":
            score += 0.35 if strategy["target"] == n["name"] else 0.0
        else:
            score -= 0.6 if strategy["kind"] == "survival" else 0.3
        # Memory: a grudge is a reason, and a proven friend is not attacked lightly.
        # The big lean on the small: the wider the gap in people and land, the better a war looks,
        # and a civ far bigger than its neighbour forgets what it owes it.
        ratio = (you["population"] + you["territory"]) / max(1, n["population"] + n["territory"])
        if ratio >= BULLY:
            score += min(BULLY_MAX, 0.5 * (ratio - 1.0))
            why = f"{n['name']} is small and ours for the taking"
        standing = n.get("standing", 0.0)
        if ratio >= OVERBEARING:
            standing = min(standing, 0.0)
        score -= max(-0.6, min(0.6, 0.35 * standing))
        if standing <= -0.8:
            why = f"{n['name']} has wronged us and is weaker"
        allies = [name for name in n["allied_with"] if name != you["name"]]
        score -= 0.5 * len(allies)
        if n["name"] in friends_wars and together >= 1.15:
            score = max(score, 0.0) + 0.5
            why = f"{friends_wars[n['name']]} is fighting {n['name']} and we stand with our ally"
        if runaway == n["name"] and together >= 1.15:
            score = max(score, 0.0) + 0.4
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
        # A very long peace wears thin: an equal will do, where nobody weaker is to be had.
        # No peace lasts for ever: the longer a civ has gone without a war the more it wants
        # one, the warlike soonest, until even an equal will do.
        idle = you.get("peace_ticks", 0) - LONG_PEACE / max(military, 0.3)
        restless = idle > 0 and not at_war
        if restless:
            score += min(RESTLESS_MAX, idle * RESTLESS_PER_TICK)
            if score >= ATTACK_THRESHOLD and edge < 1.15:
                why = f"the long peace has run its course and {n['name']} is no stronger than we are"
        if together < (0.8 if restless else 1.15):
            score = min(score, 0.0)  # never start a war from parity
        return score, why

    @staticmethod
    def _ally(n, edge, thirst, my_enemies, threats, runaway, friends=0) -> tuple[float, str]:
        if n["truce"] and n["relation"] != "alliance":
            return 0.0, ""
        score, why = 0.0, f"{n['name']} is a useful friend"
        shared = [name for name in n["at_war_with"] if name in my_enemies]
        needed = bool(shared or threats - {n["name"]} or (runaway and runaway != n["name"]))
        if n["relation"] == "alliance":
            score += 0.5
            why = f"standing by {n['name']}"
            if not needed:
                # An alliance with nothing left to guard against wears thin with the years.
                score -= min(ALLIANCE_FATIGUE, ALLIANCE_FATIGUE * (n.get("alliance_ticks") or 0) / ALLIANCE_WEARS)
        else:
            score -= 0.3 * friends  # one good friend is worth more than many"
        if n["their_stance_toward_you"] == "ally":
            score += 0.3
        if shared:
            score += 0.6
            why = f"{n['name']} is also fighting {shared[0]}"
        if threats - {n["name"]} and n["name"] not in threats and edge <= 2.0:
            score += 0.6
            why = f"threatened by {sorted(threats - {n['name']})[0]}"
        if runaway and runaway != n["name"] and edge <= 2.0:
            score += 0.5  # the small stand together against a giant
            why = f"{runaway} is running away with it"
        if thirst >= WATER_URGENT and n["water_rich"]:
            score += 0.6
            why = f"{n['name']} has the water we need"
        if n["distrusted_ticks_left"]:
            score -= 0.5
        if n.get("rival") and not shared:
            score -= RIVAL_ALLY  # the two at the top do not stay friends for long
        score += max(-0.6, min(0.6, 0.3 * n.get("standing", 0.0)))  # friends are kept, enemies not courted
        if n["name"] in threats:
            score -= 0.6
        return score, why
