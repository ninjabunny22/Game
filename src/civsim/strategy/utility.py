"""UtilityBrain: the built-in strategist.

Every day it weighs, for every neighbour, what attacking, allying and trading would be worth
to this civ as things stand, and takes the best. The weights are the civ's own personality,
so a warlike civ and a merchant read the same map differently. It sees only what any
strategist is shown (see context.py): exact numbers for allies, a rough comparison for
everyone else.

Thinking daily, it also has to keep its word to itself. A war is fought for a season before
peace is sought, an alliance is kept for one, a long-term goal is held for most of a year,
and a war is prepared against one chosen target (the army raised first, tribute demanded
where that might do) rather than declared on a whim and regretted the next morning.

Every number it decides by is a field of `Params`, so a variant of the strategist is just a
set of changed numbers (see league.py, which plays variants against each other).
"""

from dataclasses import dataclass, fields, replace

from .checkin import WATER_PRIORITY, WATER_URGENT, CheckinRequest, default_offer
from .context import BAND_RATIO

STRATEGY_FOCUS = {"conquest": "military", "survival": "military", "science": "science",
                  "prosperity": "economy", "expansion": "expansion"}


@dataclass(frozen=True)
class Params:
    ATTACK_THRESHOLD: float = 0.5  # an attack must be worth at least this to be launched
    ALLY_THRESHOLD: float = 0.6
    PARITY: float = 1.15  # the forecast a war must have before it is started ...
    RESTLESS_PARITY: float = 0.8  # ... or after a long peace
    WAR_WEARY_TICKS: int = 300  # a war this old is only kept up from a position of strength
    RUNAWAY: float = 1.5  # a neighbour this many times our size is running away with the game
    ALLIANCE_WEARS: int = 100  # ticks an alliance lasts with neither ally at war: after that it is let go
    RIVAL_ATTACK: float = 0.3  # how much more a war with the other of the two strongest is worth
    RIVAL_ALLY: float = 0.5  # ... and how much less an alliance with it
    RIVAL_BETRAYAL: float = 0.8  # ... and the share of the usual edge at which that ally is turned on
    BULLY: float = 1.4  # from this many times a neighbour's size a civ wants the war for its own sake ...
    BULLY_MAX: float = 0.8  # ... more the bigger the gap, up to this
    OVERBEARING: float = 1.6  # ... and from this, no past friendship stands in the way
    LONG_PEACE: float = 350  # ticks at peace, divided by its taste for war, after which any civ starts to itch
    RESTLESS_PER_TICK: float = 0.8 / 250  # ... more with every season that passes, up to RESTLESS_MAX
    RESTLESS_MAX: float = 1.6
    EXPOSED_EDGE: float = 1.3  # how much weaker a civ caught off balance is taken to be
    SICK_EDGE: float = 1.3  # how much weaker a civ struck by sickness is taken to be
    SICK_BETRAYAL: float = 0.75  # an ally laid low is turned on at this share of the usual edge and warlikeness
    BETRAYAL_EDGE: float = 1.8  # how far ahead a warlike civ must be before it turns on an ally
    BETRAYAL_MILITARY: float = 1.3  # ... and how warlike
    STRATEGY_STICKINESS: float = 1.3  # a strategy already in hand counts for this much more than a new one
    # Keeping its word to itself.
    WAR_MIN: int = 50  # ticks a war is fought before peace is sought, unless it is going disastrously
    ALLIANCE_MIN: int = 100  # ticks an alliance is kept, whatever else comes up
    ALLIANCE_REST: int = 300  # ticks before two civs whose alliance ended form another, unless they share a war
    STRATEGY_MIN: int = 200  # ticks a long-term goal is held before another may replace it
    PLAN_MAX: int = 150  # ticks a war is prepared against one target before the plan is dropped
    PLAN_BONUS: float = 0.4  # how much the target already being prepared against is preferred
    PLAN_ABANDON: float = 0.9  # forecast below which a plan is given up: the target has grown too strong
    # Forecasting a war: what the simple comparison of strength leaves out.
    MARCH_FREE: int = 20  # tiles an army marches without it counting against the attack ...
    MARCH_SCALE: float = 100.0  # ... and the further distance that halves it
    WALLS_FREE: float = 3.0  # how strongly a capital may be held before it counts against the attack ...
    WALLS_WEIGHT: float = 0.03  # ... and how much each point above that does
    ALLY_WEIGHT: float = 0.6  # how much of an ally's strength is counted, theirs or ours
    RESERVE: float = 0.25  # share of the army kept at home while another neighbour is hostile
    # Preparing and striking.
    PREP_MIN: int = 25  # ticks spent mustering before a war is declared ...
    PREP_READY: float = 0.8  # ... and the share of the army meant for it that must be under arms
    DEMAND_EDGE: float = 1.5  # forecast from which tribute is demanded before attacking ...
    DEMAND_MILITARY: float = 1.3  # ... by civs less warlike than this; the rest just attack
    DEMAND_PATIENCE: int = 20  # ticks a demand is given to be answered
    DEMAND_REST: int = 600  # ticks before a civ that paid is asked again, or will pay again: after that it is war
    PAY_EDGE: float = 0.7  # a civ this much weaker than whoever demands tribute pays it ...
    PAY_MILITARY: float = 1.2  # ... unless it is this warlike
    # What it has learned, and who it is playing against.
    CAUTION_WEIGHT: float = 0.5  # how much a lesson learned in war counts against trying again
    # Land worth fighting for: a rival's region valued (strategy/geography.py) above PRIZE_FREE
    # makes a war against it look better, by PRIZE_WEIGHT a unit of value, at most PRIZE_MAX.
    PRIZE_FREE: float = 2.0
    PRIZE_WEIGHT: float = 0.1
    PRIZE_MAX: float = 0.4
    # The race to domination (80% of the map's region points): a civ this close to the target
    # is everyone's runaway, a war against it is not given up while it can be fought, and a
    # civ this close itself pushes for the prizes that would finish it.
    NEAR_VICTORY: float = 0.75
    LAST_PUSH: float = 0.4
    HOLD_THE_LEADER: float = 0.6  # the edge at which a war on a near-winner is still fought on
    EASY: float = -0.3  # added to the worth of attacking a human ruler on the easy setting ...
    HARD: float = 0.2  # ... and on the hard one


DEFAULT = Params()
# How each kind of civ makes war: (forecast it wants beyond the usual, ticks of preparation as
# a multiple of the usual, share of the army it commits beyond the usual).
TACTICS = {
    "Expansionist": (-0.1, 0.4, 0.1),  # raiders: quick to strike, with nearly everything
    "Builder": (0.15, 1.6, -0.15),  # fortify and wait: slow, sure, and well guarded at home
    "Merchant": (0.1, 1.0, -0.05),  # would rather pay someone else to do it
}


class UtilityBrain:
    name = "utility"

    def __init__(self, **tweaks: float):
        """`tweaks` change any of the numbers in Params, for playing variants against each other."""
        unknown = set(tweaks) - {f.name for f in fields(Params)}
        if unknown:
            raise ValueError(f"unknown strategist parameters: {', '.join(sorted(unknown))}")
        self.p = replace(DEFAULT, **tweaks)

    def decide(self, request: CheckinRequest) -> dict | None:
        p = self.p
        context = request.context
        you = context["you"]
        neighbors = context["neighbors"]
        tick = context["tick"]
        military = you["weights"].get("military", 1.0)
        thirst = you["water"]["urgency"]
        need, prep, zeal = TACTICS.get(you.get("personality"), (0.0, 1.0, 0.0))
        can_declare = (you["diplomacy_points"] >= context["diplomacy_costs"]["declare_war"]
                       and you["max_soldiers"] >= you["soldiers_needed_to_declare_war"])
        edges = {n["id"]: self._edge(you, n) for n in neighbors}
        by_name = {n["name"]: n for n in neighbors}
        my_wars = [n for n in neighbors if n["relation"] == "war"]
        my_enemies = {n["name"] for n in my_wars}
        # Who is dangerous: anyone already set on us, and anyone much stronger within reach.
        threats = {n["name"] for n in neighbors if n["relation"] != "alliance" and (
            n["relation"] == "war" or n["their_stance_toward_you"] == "aggression"
            or (n["in_reach"] and edges[n["id"]] < 0.6))}
        size = you["population"] + you["territory"]
        leader = max(neighbors, key=lambda n: (n["population"] + n["territory"], n["name"]), default=None)
        runaway = leader["name"] if leader and leader["population"] + leader["territory"] >= p.RUNAWAY * size else None
        # Whoever is close to winning outright is the runaway, whatever its size.
        closing = max(neighbors, key=lambda n: (n.get("victory_share", 0.0), n["name"]), default=None)
        if closing and closing.get("victory_share", 0.0) >= p.NEAR_VICTORY:
            runaway = closing["name"]
        supplier = any(n["water_rich"] and n["their_stance_toward_you"] in ("trade", "ally") for n in neighbors)
        strategy = self._strategy(context, edges, threats)
        # Allies count: what they bring to a fight, and the wars they are already in.
        friends = [n for n in neighbors if n["relation"] == "alliance"]
        backing = sum(n["intel"]["military_power"] for n in friends if n["intel"]) / max(you["military_power"], 1)
        friends_wars = {name: n["name"] for n in friends for name in n["at_war_with"]}
        plan = you.get("plan") or {}
        if plan and (tick - plan.get("since", tick) > p.PLAN_MAX or plan.get("target") not in by_name):
            plan = {}

        stances, notes = [], []
        candidates: list[tuple[float, str, dict, float, dict]] = []  # worth, why, neighbour, forecast, entry
        for n in neighbors:
            edge = edges[n["id"]]
            entry = {"civ": n["name"], "stance": "ignore", "give": "none", "give_per_tick": 0,
                     "want": "none", "want_per_tick": 0, "troop_commitment": 0}
            stances.append(entry)
            if n["relation"] == "war":
                self._wage(you, n, edge, entry, notes, len(my_wars), zeal)
                continue
            paid = you.get("paid_tribute_ticks")
            if (n.get("demands_tribute") and edge <= p.PAY_EDGE and military < p.PAY_MILITARY
                    and (paid is None or paid >= p.DEMAND_REST)):  # nobody pays twice in a row
                # Outmatched and no fighter: buy them off.
                entry.update(default_offer(you, n), stance="trade", pay_tribute=True)
                notes.append((3, f"paying {n['name']} the tribute it demands rather than fight"))
                continue

            others = [m for m in neighbors if m is not n]
            forecast = self._forecast(n, edge, others, edges, backing if n["name"] in friends_wars else 0.0)
            attack, why_attack = self._attack(you, n, edge, forecast, military, thirst, supplier, can_declare,
                                              bool(my_wars), runaway, strategy, friends_wars, need,
                                              context.get("player"), context.get("difficulty"))
            if plan.get("target") == n["name"] and attack > 0:
                # See a war already being prepared through, unless the target has grown too strong.
                attack = attack + p.PLAN_BONUS if forecast >= p.PLAN_ABANDON else 0.0
            ally, why_ally = self._ally(n, edge, thirst, my_enemies, threats, runaway, len(friends))
            kept = n["relation"] == "alliance" and (n.get("alliance_ticks") or 0) < p.ALLIANCE_MIN
            if attack >= p.ATTACK_THRESHOLD and attack >= ally:  # a betrayal waits for no season
                candidates.append((attack, why_attack, n, forecast, entry))
            if ally >= p.ALLY_THRESHOLD or kept:
                entry.update(default_offer(you, n), stance="ally")
                notes.append((1, f"{why_ally}: allying with {n['name']}"))
            elif n["their_stance_toward_you"] == "aggression" and n["relation"] != "alliance":
                notes.append((1, f"wary of {n['name']}"))  # no trade with someone about to attack
            else:
                entry.update(default_offer(you, n), stance="trade")
                self._subsidise(you, n, by_name, runaway, entry, notes)

        # One war at a time is prepared: the best of those worth starting.
        new_plan = None
        if candidates:
            attack, why, n, forecast, entry = max(candidates, key=lambda c: (c[0], c[2]["name"]))
            new_plan = self._prepare(you, n, forecast, why, entry, notes, plan, tick, military,
                                     len(my_wars) + 1, prep, zeal)

        notes.sort(reverse=True)
        reason = "; ".join(text for _, text in notes[:2]) if notes else "trading with everyone"
        if thirst >= WATER_PRIORITY:
            reason += f"; water is {you['water']['status']}"
        return {"reason": reason[0].upper() + reason[1:] + ".", "stances": stances, "strategy": strategy,
                "plan": new_plan}

    # -- wars in hand ----------------------------------------------------------

    def _wage(self, you, n, edge, entry, notes, wars, zeal) -> None:
        """Press a war or seek peace. A war is given a season before it is given up, unless a
        capital is already lost to it or the army has just been broken."""
        p = self.p
        age = n["war_ticks"] or 0
        weary = age >= p.WAR_WEARY_TICKS or you.get("sick")
        if n.get("sick") and not you.get("sick"):
            edge = max(edge, 1.0) * p.SICK_EDGE  # they are laid low: now is the time
        disaster = n.get("holds_your_capital") or you.get("routed_ticks_ago") is not None
        committed = age < p.WAR_MIN and not disaster
        if n.get("victory_share", 0.0) >= p.NEAR_VICTORY and edge >= p.HOLD_THE_LEADER and not disaster:
            entry.update(stance="aggression", troop_commitment=self._commitment(edge, wars, zeal))
            notes.append((3, f"{n['name']} is close to ruling the map: the war goes on"))
            return
        if n.get("you_hold_their_capital") or committed or edge >= 1.3 or (edge >= 0.85 and not weary):
            entry.update(stance="aggression", troop_commitment=self._commitment(edge, wars, zeal))
            notes.append((2, f"pressing the war on {n['name']}"))
        else:
            notes.append((3, f"the war with {n['name']} is going badly: seeking peace"))

    # -- preparing a war -------------------------------------------------------

    def _prepare(self, you, n, forecast, why, entry, notes, plan, tick, military, wars, prep, zeal) -> dict:
        """Muster first; demand tribute where the gap is wide enough that it might be paid;
        strike when the army is raised. Returns the plan as it now stands."""
        p = self.p
        commitment = self._commitment(forecast, wars, zeal)
        since = plan["since"] if plan.get("target") == n["name"] else tick
        days = tick - since
        raised = you["soldiers"] / max(1.0, commitment * you["max_soldiers"])
        ready = raised >= p.PREP_READY and days >= p.PREP_MIN * prep
        entry.update(stance="aggression", troop_commitment=commitment, give="none", give_per_tick=0,
                     want="none", want_per_tick=0)
        asked = n.get("your_demand_ticks")
        got = n.get("paid_you_ticks")
        asks = (n["relation"] != "alliance" and forecast >= p.DEMAND_EDGE and military < p.DEMAND_MILITARY
                and (got is None or got >= p.DEMAND_REST))  # it has paid lately: this time it is war
        if n["relation"] == "alliance":
            text = f"Turning on {n['name']}"  # a betrayal gives no warning
            notes.append((4, f"{why}: attacking {n['name']}"))
        elif not ready:
            entry["hold"] = True
            text = f"Mustering against {n['name']} ({min(99, round(100 * min(raised / p.PREP_READY, days / max(1.0, p.PREP_MIN * prep))))}% ready)"
            notes.append((4, f"{why}: preparing for war with {n['name']}"))
        elif asks and (asked is None or asked < p.DEMAND_PATIENCE):
            entry.update(hold=True, demand=True)
            text = f"Demanding tribute from {n['name']}"
            notes.append((4, f"{why}: demanding tribute from {n['name']}"))
        else:
            text = f"Marching on {n['name']}"
            notes.append((4, f"{why}: attacking {n['name']}"))
        return {"target": n["name"], "since": since, "text": text}

    def _subsidise(self, you, n, by_name, runaway, entry, notes) -> None:
        """A merchant pays others to do its fighting: gold, freely, to whoever is at war with
        someone it has reason to fear or to hate."""
        if you.get("personality") != "Merchant" or you["resources"]["gold"]["stock"] < 60:
            return
        for foe in n["at_war_with"]:
            other = by_name.get(foe)
            if other and other["relation"] != "alliance" and (
                    foe == runaway or other.get("rival") or other.get("standing", 0.0) <= -0.5):
                entry.update(give="gold", give_per_tick=1.5)
                notes.append((2, f"paying {n['name']} to fight {foe}"))
                return

    # -- the long view ---------------------------------------------------------

    def _strategy(self, context: dict, edges: dict, threats: set) -> dict:
        """What the civ is working toward over the long run. It follows from the civ's own
        leanings and its position, and once chosen is held for most of a year: a civ that
        changed its mind every day would get nowhere. Only the need to survive overrides that."""
        p = self.p
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
        scores = {kind: score * (p.STRATEGY_STICKINESS if kind == before.get("kind") else 1.0)
                  for kind, (score, _) in options.items()}
        kind = max(scores, key=lambda k: (scores[k], k))
        held = before.get("kind")
        if (held in options and held != kind and kind != "survival" and scores[held] > 0
                and context["tick"] - before.get("since", 0) < p.STRATEGY_MIN):
            kind = held  # not yet: see the present goal through
        target = options[kind][1]
        text = {"conquest": f"Conquer {target}", "survival": f"Survive {target}", "science": "Out-think the others",
                "prosperity": "Grow rich by trade", "expansion": "Settle the open land"}[kind]
        return {"kind": kind, "target": target, "focus": STRATEGY_FOCUS[kind], "text": text}

    @staticmethod
    def _edge(you: dict, n: dict) -> float:
        """Our military power over theirs: exact for an ally or an army our scouts can count,
        otherwise from the rough comparison."""
        if n["intel"]:
            return you["military_power"] / max(n["intel"]["military_power"], 1)
        if n.get("seen_power"):
            return you["military_power"] / max(n["seen_power"], 1)
        return 1 / BAND_RATIO[n["army_vs_yours"]]

    def _commitment(self, edge: float, wars: int, zeal: float = 0.0) -> float:
        """More of the army against an equal than against a pushover, and less with every front."""
        share = 0.9 - 0.2 * (edge - 1.0) + zeal
        return round(max(0.4, min(0.95, share / max(1, wars) ** 0.5)), 2)

    def _forecast(self, n: dict, edge: float, others: list, edges: dict, backing: float) -> float:
        """How a war on this neighbour would go, as our strength over theirs once everything
        is counted: the march to its capital and how well that is held, who would stand with
        it and with us, and what has to stay at home because someone else is hostile. Equal
        to the plain comparison of strength for a lone neighbour next door; 0 if no army
        could get there at all."""
        p = self.p
        if n.get("march") is None:
            return 0.0
        hostile = any(m["relation"] != "alliance" and m["in_reach"]
                      and (m["relation"] == "war" or m["their_stance_toward_you"] == "aggression") for m in others)
        ours = 1.0 - (p.RESERVE if hostile else 0.0) + p.ALLY_WEIGHT * backing
        theirs = 1.0
        for m in others:  # whoever is allied to them and not to us
            if m["name"] in n["allied_with"] and m["relation"] != "alliance":
                theirs += p.ALLY_WEIGHT * edge / max(edges[m["id"]], 0.05)
        far = 1.0 + max(0, n["march"] - p.MARCH_FREE) / p.MARCH_SCALE
        held = 1.0 + p.WALLS_WEIGHT * max(0.0, n.get("walls", 0.0) - p.WALLS_FREE)
        return edge * ours / (theirs * far * held)

    def _attack(self, you, n, edge, forecast, military, thirst, supplier, can_declare, at_war, runaway, strategy,
                friends_wars, need=0.0, player=None, difficulty="normal") -> tuple[float, str]:
        p = self.p
        if not (can_declare and n["in_reach"]) or n["truce"] or you.get("sick"):
            return 0.0, ""  # nor does a civ that is itself sick start anything
        sick = bool(n.get("sick"))
        # Caught off balance: its army is away, or has just been beaten.
        exposed = bool(n.get("army_abroad")) or n.get("routed_ticks_ago") is not None
        swing = (p.SICK_EDGE if sick else 1.0) * (p.EXPOSED_EDGE if exposed else 1.0)
        edge, forecast = edge * swing, forecast * swing
        if n["relation"] == "alliance":
            # Only the warlike turn on a friend, and only a lone one they can crush, with no
            # betrayal already against their name.
            lone = not [name for name in n["allied_with"] if name != you["name"]]
            ease = p.SICK_BETRAYAL if sick else 1.0  # a friend's weakness is some rulers' opportunity
            if n.get("rival") and not sick:
                # The two strongest working together: whoever strikes first takes it all.
                if (military >= 1.0 and edge >= p.BETRAYAL_EDGE * p.RIVAL_BETRAYAL and not at_war
                        and not you["distrusted_ticks_left"] and n.get("standing", 0.0) < 0.5):
                    return 1.0 + (edge - p.BETRAYAL_EDGE * p.RIVAL_BETRAYAL) * military, \
                        f"only {n['name']} stands between us and first place"
            if sick and military >= p.BETRAYAL_MILITARY * ease and edge >= p.BETRAYAL_EDGE * ease and lone \
                    and not at_war and not you["distrusted_ticks_left"] and n.get("standing", 0.0) < 1.5:
                return 1.1 + (edge - p.BETRAYAL_EDGE * ease) * military, f"{n['name']} is sick and cannot defend itself"
            if (military < p.BETRAYAL_MILITARY or edge < p.BETRAYAL_EDGE or not lone or at_war
                    or strategy["kind"] == "survival" or you["distrusted_ticks_left"]
                    or n.get("standing", 0.0) >= 1.5):
                return 0.0, ""
            return 0.9 + (edge - p.BETRAYAL_EDGE) * military, f"{n['name']} trusts us and is weak"
        score, why = (forecast - 1.0) * 1.2 * military, f"{n['name']} is weaker"
        if n["at_war_with"]:
            score += 0.4
            why = f"{n['name']} is weaker and already fighting {n['at_war_with'][0]}"
        if sick:
            score += 0.35
            why = f"{n['name']} is laid low by sickness"
        if n.get("rival"):
            score += p.RIVAL_ATTACK
            why = f"only {n['name']} stands between us and first place"
        if exposed and not sick:
            score += 0.3
            why = (f"{n['name']}'s army is away" if n.get("army_abroad") else f"{n['name']} has just lost a battle")
        if n["distrusted_ticks_left"]:
            score += 0.2  # nobody will come to its aid
        prize = n.get("prize")
        if prize and prize["value"] > p.PRIZE_FREE:
            score += min(p.PRIZE_MAX, p.PRIZE_WEIGHT * (prize["value"] - p.PRIZE_FREE))
            why = f"{n['name']} holds {prize['region']}, which we want for {prize['why']}"
        if prize and you.get("points", {}).get("share", 0.0) >= p.NEAR_VICTORY:
            score += p.LAST_PUSH
            why = f"{prize['region']} would bring the map within our grasp"
        # The long view: the civ it has set out to conquer is attacked sooner, and a civ set on
        # something else is slower to fight at all.
        if strategy["kind"] == "conquest":
            score += 0.35 if strategy["target"] == n["name"] else 0.0
        else:
            score -= 0.6 if strategy["kind"] == "survival" else 0.3
        # The big lean on the small: the wider the gap in people and land, the better a war looks,
        # and a civ far bigger than its neighbour forgets what it owes it.
        ratio = (you["population"] + you["territory"]) / max(1, n["population"] + n["territory"])
        if ratio >= p.BULLY:
            score += min(p.BULLY_MAX, 0.5 * (ratio - 1.0))
            why = f"{n['name']} is small and ours for the taking"
        # Memory: a grudge is a reason, and a proven friend is not attacked lightly.
        standing = n.get("standing", 0.0)
        if ratio >= p.OVERBEARING:
            standing = min(standing, 0.0)
        score -= max(-0.6, min(0.6, 0.35 * standing))
        if standing <= -0.8:
            why = f"{n['name']} has wronged us and is weaker"
        # What past wars with this civ have taught: beaten once, it takes more to try again.
        caution = n.get("caution", 0.0)
        score -= p.CAUTION_WEIGHT * caution
        if n["name"] in friends_wars and forecast >= p.PARITY:
            score = max(score, 0.0) + 0.5
            why = f"{friends_wars[n['name']]} is fighting {n['name']} and we stand with our ally"
        if runaway == n["name"] and forecast >= p.PARITY:
            score = max(score, 0.0) + 0.4
            why = f"{n['name']} is running away with it"
        if at_war:
            score -= 1.0 if edge < 2.2 else 0.3  # a second front only against the helpless
        if n["your_current_stance"] == "aggression":
            score += 0.2  # see a decision through rather than flip every day
        if n["name"] == player:
            score += p.EASY if difficulty == "easy" else p.HARD if difficulty == "hard" else 0.0
        if thirst >= WATER_URGENT and n["water_rich"] and not supplier:
            score += 0.8
            why = f"the wells are failing and {n['name']} has water"
        elif thirst >= WATER_PRIORITY and n["water_rich"]:
            score = min(score, 0.0)  # whoever has water is courted, not fought, while there is a choice
        # No peace lasts for ever: the longer a civ has gone without a war the more it wants
        # one, the warlike soonest, until even an equal will do.
        idle = you.get("peace_ticks", 0) - p.LONG_PEACE / max(military, 0.3)
        restless = idle > 0 and not at_war
        if restless:
            score += min(p.RESTLESS_MAX, idle * p.RESTLESS_PER_TICK)
            if score >= p.ATTACK_THRESHOLD and forecast < p.PARITY:
                why = f"the long peace has run its course and {n['name']} is no stronger than we are"
        if forecast < (p.RESTLESS_PARITY if restless else p.PARITY) + need + caution:
            score = min(score, 0.0)  # never start a war it does not expect to win
        return score, why

    def _ally(self, n, edge, thirst, my_enemies, threats, runaway, friends=0) -> tuple[float, str]:
        p = self.p
        if (n["truce"] and n["relation"] != "alliance") or n.get("betrayed_you"):
            return 0.0, ""  # and whoever betrayed us once is never trusted again
        score, why = 0.0, f"{n['name']} is a useful friend"
        shared = [name for name in n["at_war_with"] if name in my_enemies]
        if n["relation"] == "alliance":
            # An alliance is for fighting beside each other: with neither at war it is let go
            # after a season, whatever else speaks for it.
            if not (my_enemies or n["at_war_with"]) and (n.get("alliance_ticks") or 0) >= p.ALLIANCE_WEARS:
                return 0.0, ""
            score += 0.5
            why = f"standing by {n['name']}"
        else:
            if not shared and n.get("since_alliance", 10**9) < p.ALLIANCE_REST:
                return 0.0, ""  # they have only just parted
            score -= 0.3 * friends  # one good friend is worth more than many
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
            score -= p.RIVAL_ALLY  # the two at the top do not stay friends for long
        score += max(-0.6, min(0.6, 0.3 * n.get("standing", 0.0)))  # friends are kept, enemies not courted
        if n["name"] in threats:
            score -= 0.6
        return score, why
