"""Relations between civs: carries out, every tick, what the strategic layer intends.

The strategic layer only sets an Intent per neighbour at its check-ins. Everything
mechanical happens here: opening and running trade deals, forming and dissolving
alliances and declaring wars. Fighting itself is done by the armies in
military/warfare.py; this module owns what a capture or a surrender means.
"""

import random

from ..civ.civilization import Settlement
from ..economy import may_stand, ports, recompute_capacity
from ..economy.villagers import convert_villagers
from ..military.units import tier_strength, unit_strength
from ..economy.rules import (
    GARRISON,
    MAX_MOBILIZATION,
    MIN_POPULATION,
    RESOURCES,
    UNPAID_QUALITY,
    UNSUPPLIED_QUALITY,
)
from ..map import BOAT_RANGE, WorldMap, load_faction
from . import rules
from .model import FRIENDLY, Deal, Intent, Relation, Stance, War
from .proclamations import PLAIN, proclaim
from .naming import alliance_name, war_name

REACH_CACHE_TICKS = 10
HISTORY_LIMIT = 200


class Diplomacy:
    def __init__(self, world: WorldMap, civs: list, modifiers: dict, building_defs: dict,
                 rng: random.Random | None = None):
        self.world = world
        self.rng = rng or random.Random(0)  # only used to pick names
        self.names_used: set[str] = set()
        self.building_defs = building_defs
        self.civs = {civ.id: civ for civ in civs}
        self.mods = modifiers  # civ id -> Modifiers; the simulation keeps this current
        ids = sorted(self.civs)
        self.intents: dict[tuple[int, int], Intent] = {(a, b): Intent() for a in ids for b in ids if a != b}
        self.relations: dict[tuple[int, int], Relation] = {(a, b): Relation() for a in ids for b in ids if a < b}
        self.deals: list[Deal] = []
        self.history: list[dict] = []  # {"tick", "civs", "text"}, oldest first
        # What each civ makes of each other, from what has passed between them: (a, b) is how a
        # regards b, from -3 (a bitter grudge) to 3 (a proven friend). It fades back toward 0.
        self.standing: dict[tuple[int, int], float] = {(a, b): 0.0 for a in ids for b in ids if a != b}
        self._next_deal_id = 1
        self._reach_cache: dict[tuple[int, int], tuple[int, bool]] = {}
        self.player: int | None = None  # the civ a human rules, if any: it is never made peace for
        self.now = 0
        self.refused_since: dict[tuple[int, int], tuple[int, str]] = {}  # (a, b) -> (tick, resource) b would not trade a
        self.wars_started = 0  # how many wars between civs there have been in the game
        self.caution: dict[tuple[int, int], float] = {}  # (civ, other) -> extra edge it wants before attacking it
        self.betrayed: set[tuple[int, int]] = set()  # (victim, betrayer): never forgotten
        self.demands: dict[tuple[int, int], int] = {}  # (demander, target) -> tick the demand was made
        self.tribute_paid: dict[tuple[int, int], int] = {}  # (payer, asker) -> tick tribute was last paid
        self._ills = random.Random(7 + sum(civ.capital.tile for civ in civs))  # its own dice: outbreaks never disturb the game's
        self._alliance_breaks: dict[tuple[int, int], int] = {}  # (breaker, former ally) -> tick it broke the alliance
        self.distrust_until: dict[int, int] = {}  # betrayer -> tick until which others hold it against them
        self.military = None  # set by the simulation; moves and fights the armies each tick
        self.natives = None  # set by the simulation; the native faction holding the neutral regions
        self.faction = load_faction()["name"]
        for civ in civs:
            civ.diplomacy_points = rules.DIPLOMACY_START

    # -- queries -------------------------------------------------------------

    def relation(self, a: int, b: int) -> Relation:
        return self.relations[(a, b) if a < b else (b, a)]

    def intent(self, a: int, b: int) -> Intent:
        """What `a` currently intends toward `b`."""
        return self.intents[(a, b)]

    def others(self, civ_id: int) -> list[int]:
        return [other for other, civ in self.civs.items() if other != civ_id and civ.alive]

    def allies(self, civ_id: int) -> list[int]:
        return [o for o in self.others(civ_id) if self.relation(civ_id, o).status == "alliance"]

    def enemies(self, civ_id: int) -> list[int]:
        return [o for o in self.others(civ_id) if self.relation(civ_id, o).status == "war"]

    def deal_between(self, a: int, b: int) -> Deal | None:
        return next((d for d in self.deals if {d.a, d.b} == {a, b}), None)

    def quality(self, civ) -> float:
        """Fighting strength of one soldier."""
        quality = 1 + self.mods[civ.id].military
        if civ.unpaid:
            quality *= UNPAID_QUALITY
        if civ.unsupplied:
            quality *= UNSUPPLIED_QUALITY
        return quality

    def strength(self, civ) -> float:
        """Strength of the army as it stands: soldiers x unit type x quality x commander skill."""
        if not civ.armies:
            return civ.soldiers * self.quality(civ)
        return self.quality(civ) * sum(
            unit_strength(army.units) * tier_strength(army.tier)
            * (1 + (army.commander.strength_bonus if army.commander else 0.0))
            for army in civ.armies)

    def power(self, civ) -> float:
        """Strength the civ could field if it mobilised fully."""
        mods = self.mods[civ.id]
        return civ.population * self.mobilization_cap(civ) * (1 + mods.military) * tier_strength(mods.tier)

    def mobilization_cap(self, civ) -> float:
        """Largest share of the population the civ can put under arms."""
        return MAX_MOBILIZATION + self.mods[civ.id].mobilization

    def in_reach(self, a: int, b: int, tick: int) -> bool:
        """True if `a` can get at `b`'s territory: close enough overland, or across water with boats."""
        key = (a, b)
        cached = self._reach_cache.get(key)
        if cached is None or tick - cached[0] >= REACH_CACHE_TICKS:
            cached = (tick, bool(self._nearest_tiles(self.civs[a], self.civs[b])))
            self._reach_cache[key] = cached
        return cached[1]

    def distrusted(self, civ_id: int, tick: int) -> bool:
        """True while other civs still hold a betrayal against this one."""
        return tick < self.distrust_until.get(civ_id, 0)

    def recent_history(self, civ_id: int, limit: int) -> list[dict]:
        return [entry for entry in self.history if civ_id in entry["civs"]][-limit:]

    # -- input from the strategic layer --------------------------------------

    def set_intents(self, civ_id: int, intents: dict[int, Intent]) -> None:
        if not self.civs[civ_id].alive:
            return
        for other, intent in intents.items():
            if other != civ_id and (civ_id, other) in self.intents and self.civs[other].alive:
                self.intents[(civ_id, other)] = intent

    def apply_modifiers(self, civ, mods) -> None:
        allies = len(self.allies(civ.id))
        mods.science_mult += rules.ALLY_SCIENCE * allies
        mods.defense += rules.ALLY_DEFENSE * allies
        if self.sick(civ):
            mods.military += rules.SICKNESS_MILITARY
            mods.growth += rules.SICKNESS_GROWTH
            for res in mods.yield_mult:
                mods.yield_mult[res] += rules.SICKNESS_YIELD

    # -- per-tick execution --------------------------------------------------

    def remember(self, who: int, of: int, amount: float) -> None:
        """`who` thinks better (amount > 0) or worse of `of` for something it has just done."""
        if who != of and (who, of) in self.standing:
            self.standing[(who, of)] = max(-3.0, min(3.0, self.standing[(who, of)] + amount))

    def shared_border(self, a, b) -> int:
        """How many of `a`'s tiles touch `b`'s land."""
        small, other = (a, b) if len(a.territory) <= len(b.territory) else (b, a)
        owner, neighbors = self.world.owner, self.world.neighbors
        return sum(1 for tile in small.territory if any(owner[n] == other.id for n in neighbors(tile)))

    def might(self, civ) -> float:
        """How strong a civ is, all told: its people, its land and the army it could field."""
        return civ.population + len(civ.territory) + self.power(civ)

    def rivals(self) -> tuple[int, int] | None:
        """The strongest civ and the second strongest, as things stand now."""
        living = sorted((civ for civ in self.civs.values() if civ.alive), key=lambda c: (-self.might(c), c.id))
        return (living[0].id, living[1].id) if len(living) >= 2 else None

    def _friction(self) -> None:
        """Neighbours at peace come to resent each other: over the border they share, and over
        native land both have armies out to take. Allies do not."""
        top = self.rivals()
        if top is not None:
            # Whatever else is between them, allies or not: there is room for only one at the top.
            self.remember(top[0], top[1], -rules.RIVALRY)
            self.remember(top[1], top[0], -rules.RIVALRY)
        for (a, b), relation in self.relations.items():
            civ_a, civ_b = self.civs[a], self.civs[b]
            if relation.status != "peace" or not (civ_a.alive and civ_b.alive):
                continue
            border = self.shared_border(civ_a, civ_b)
            if border:
                rub = rules.BORDER_FRICTION * min(1.0, border / rules.LONG_BORDER)
                self.remember(a, b, -rub)
                self.remember(b, a, -rub)
        if self.natives is None:
            return
        for region in self.world.regions:
            if not region.neutral:
                continue
            after = self.natives.after(region)
            for i, a in enumerate(after):
                for b in after[i + 1:]:
                    if self.relation(a, b).status == "peace":
                        self.remember(a, b, -rules.RIVAL_FRICTION)
                        self.remember(b, a, -rules.RIVAL_FRICTION)

    def learn(self, civ_id: int, other: int, amount: float) -> None:
        """What `civ_id` has learned about fighting `other`: more caution after a defeat, less after a win."""
        low, high = rules.CAUTION_RANGE
        self.caution[(civ_id, other)] = max(low, min(high, self.caution.get((civ_id, other), 0.0) + amount))

    def _demands(self, a, b, to_b: Intent, to_a: Intent, relation: Relation, tick: int, events: list) -> None:
        """Tribute demanded and paid between two civs at peace."""
        for asker, target, ask, answer in ((a, b, to_b, to_a), (b, a, to_a, to_b)):
            key = (asker.id, target.id)
            if key in self.demands and tick - self.demands[key] > rules.DEMAND_LAPSE:
                del self.demands[key]
            if ask.demand and ask.stance is Stance.AGGRESSION and key not in self.demands \
                    and tick >= relation.truce_until:
                self.demands[key] = tick
                self._log(tick, events, "diplomacy", [asker, target],
                          f"{asker.name} demands tribute from {target.name}, or it will be war")
            elif answer.pay and key in self.demands:
                self.pay_demand(target, asker, tick, events)

    def pay_demand(self, payer, asker, tick: int, events: list) -> bool:
        """`payer` hands over the tribute `asker` has demanded and is left in peace for a while."""
        if self.demands.pop((asker.id, payer.id), None) is None:
            return False
        relation = self.relation(payer.id, asker.id)
        self.tribute_paid[(payer.id, asker.id)] = tick
        self._pay_tribute(payer, {asker.id: 1.0}, rules.DEMAND_TRIBUTE)
        relation.truce_until = max(relation.truce_until, tick + rules.DEMAND_TRUCE)
        self.remember(payer.id, asker.id, -0.4)
        self._log(tick, events, "diplomacy", [payer, asker],
                  f"{payer.name} pays {asker.name} tribute to be left in peace")
        return True

    def sick(self, civ) -> bool:
        return self.now < civ.sick_until

    def _outbreaks(self, tick: int, events: list) -> None:
        """A civ long at war may be struck by sickness: it loses people at once and is weakened
        for a season. Everyone can see it, and not every neighbour is above using it."""
        for civ in self.civs.values():
            if not civ.alive:
                continue
            if civ.sickness and tick >= civ.sick_until:
                self._log(tick, events, "diplomacy", [civ], f"{civ.name} recovers from {civ.sickness}")
                civ.sickness = ""
            if tick % rules.SICKNESS_CHECK or civ.sickness or tick < civ.sick_rest:
                continue
            wars = [self.relation(civ.id, other).war for other in self.enemies(civ.id)]
            age = max((tick - war.start for war in wars if war), default=0)
            if age < rules.SICKNESS_AFTER:
                continue
            if self._ills.random() >= rules.SICKNESS_CHANCE * age / rules.SICKNESS_AFTER:
                continue
            civ.sickness = self._ills.choice(rules.SICKNESSES)
            civ.sick_until = tick + rules.SICKNESS_TICKS
            civ.sick_rest = civ.sick_until + rules.SICKNESS_REST
            share = rules.SICKNESS_DEATHS
            civ.population = max(MIN_POPULATION, civ.population * (1 - share))
            for army in civ.armies:
                army.scale(1 - share)
            civ.soldiers *= 1 - share
            self._log(tick, events, "war", [civ],
                      f"{civ.sickness.capitalize()} breaks out in {civ.name} after {age} days of war: "
                      f"its people sicken and its armies are weakened")

    def update(self, tick: int, events: list) -> None:
        self.now = tick
        self._outbreaks(tick, events)
        for civ in self.civs.values():
            if civ.alive and self.enemies(civ.id):
                civ.last_war = tick
        if tick % rules.FRICTION_INTERVAL == 0:
            self._friction()
        for pair in self.standing:
            self.standing[pair] *= rules.MEMORY_FADE  # old deeds count for less
        for civ in self.civs.values():
            if civ.alive:
                civ.diplomacy_points = min(rules.DIPLOMACY_CAP, civ.diplomacy_points + rules.DIPLOMACY_GAIN)
        for a, b in self.relations:
            if self.civs[a].alive and self.civs[b].alive:
                self._resolve_pair(a, b, tick, events)
        self._run_deals(tick, events)
        if self.military:
            self.military.update(tick, events)
        if self.natives:
            self.natives.update(tick, events)
        if tick % 10 == 0:
            self._track_refusals(tick)
        self._issue_orders(tick)

    def home_guard(self, civ, exclude=()) -> float:
        """Soldiers the civ keeps at home to hold off everyone it is not fighting (or about to
        fight): HOME_GUARD of the strongest other civ in reach that is not its ally, counted
        in full if it is at war with it or set on attacking it and at half otherwise."""
        return self.home_threat(civ, exclude)[0]

    def home_threat(self, civ, exclude=()) -> tuple[float, int | None]:
        """The home guard and the civ it watches for (None when nobody is in reach)."""
        worst, watched = 0.0, None
        for other_id in self.others(civ.id):
            other = self.civs[other_id]
            if other_id in exclude or not other.alive or self.relation(civ.id, other_id).status == "alliance":
                continue
            if not self.in_reach(other_id, civ.id, self.now):
                continue
            hostile = (self.relation(civ.id, other_id).status == "war"
                       or self.intent(other_id, civ.id).stance is Stance.AGGRESSION)
            threat = self.strength(other) * (1.0 if hostile else 0.5)
            if threat > worst:
                worst, watched = threat, other_id
        if watched is None:
            return 0.0, None
        per_soldier = self.strength(civ) / civ.soldiers if civ.soldiers >= 1 else self.quality(civ)
        return rules.HOME_GUARD * worst / max(per_soldier, 0.1), watched

    def _resolve_pair(self, a: int, b: int, tick: int, events: list) -> None:
        relation = self.relations[(a, b)]
        civ_a, civ_b = self.civs[a], self.civs[b]
        to_b, to_a = self.intents[(a, b)], self.intents[(b, a)]
        hostile = [civ for civ, intent in ((civ_a, to_b), (civ_b, to_a)) if intent.stance is Stance.AGGRESSION]

        if relation.status == "war":
            war = relation.war
            war.aggressors = {civ.id for civ in hostile}
            age = tick - war.start
            if war.guardian is not None:
                # A defensive obligation lasts exactly as long as the ally is under attack and still an ally.
                if (self.relation(war.defending, war.declarer).status == "war"
                        and self.relation(war.guardian, war.defending).status == "alliance"):
                    return
                guardian, defended = self.civs[war.guardian], self.civs[war.defending]
                war.guardian = war.defending = None
                if not hostile:
                    self._end_war(relation, tick, events, rules.TRUCE,
                                  f"{guardian.name} stands down, its duty to {defended.name} discharged")
                return  # otherwise it carries on as an ordinary war
            if age >= rules.MAX_WAR:
                self._make_peace(relation, tick, events, f"{civ_a.name} and {civ_b.name} are exhausted and stop fighting")
            elif age >= rules.MIN_WAR and not hostile:
                self._make_peace(relation, tick, events, f"{civ_a.name} and {civ_b.name} make peace")
            elif age >= rules.TERMS_AFTER and len(hostile) == 1:
                winner = hostile[0]
                loser = civ_b if winner is civ_a else civ_a
                if self.accepts_terms(war, winner, loser, tick):
                    self._make_peace(relation, tick, events, f"{loser.name} sues for peace and {winner.name} accepts")
            return

        if relation.status == "peace":
            self._demands(civ_a, civ_b, to_b, to_a, relation, tick, events)
        if hostile:
            if relation.status == "alliance":
                other = civ_b if hostile[0] is civ_a else civ_a
                self._set_status(relation, "peace", tick)
                self._alliance_breaks[(hostile[0].id, other.id)] = tick
                self._log(tick, events, "diplomacy", [hostile[0], other],
                          f"{hostile[0].name} breaks its alliance with {other.name}")
            # A civ still mustering, or waiting on a demand, holds its hand.
            striking = [civ for civ in hostile if not self.intents[(civ.id, (civ_b if civ is civ_a else civ_a).id)].hold]
            declarer = next((civ for civ in striking
                             if civ.diplomacy_points >= rules.WAR_COST), None)
            target = civ_b if declarer is civ_a else civ_a
            if declarer and tick >= relation.truce_until and self.in_reach(declarer.id, target.id, tick):
                declarer.diplomacy_points -= rules.WAR_COST
                broke = self._alliance_breaks.pop((declarer.id, target.id), None)
                betrayal = broke is not None and tick - broke <= rules.BETRAYAL_WINDOW
                name = war_name(self.world, declarer, target, self.rng, self.names_used, betrayal)
                self._start_war(declarer, target, tick, aggressors={civ.id for civ in hostile}, name=name)
                self._log(tick, events, "war", [declarer, target],
                          f"{declarer.name} declares war on {target.name}: {name} begins")
                events[-1].update(self._proclamation(declarer, target, name, tick))
                self.remember(target.id, declarer.id, -1.0)  # an attack is not forgotten quickly
                self.demands.pop((declarer.id, target.id), None)
                for ally in self.allies(declarer.id):
                    if self.relation(ally, target.id).status == "war":
                        self.remember(ally, declarer.id, rules.HELP_CAME)  # it came when it was needed
                if betrayal:
                    self._betray(relation.war, declarer, target, tick, events)
                for ally in self.allies(target.id):
                    self._join_defence(self.civs[ally], target, declarer, tick, events)
            return

        friendly = to_b.stance in FRIENDLY and to_a.stance in FRIENDLY
        if relation.status == "alliance":
            # An alliance lasts only while both still choose it: trading on is not enough.
            if not (to_b.stance is Stance.ALLY and to_a.stance is Stance.ALLY):
                self._set_status(relation, "peace", tick)
                # Walking away is no offence in itself, but attacking soon afterwards is betrayal.
                for civ, intent, other in ((civ_a, to_b, civ_b), (civ_b, to_a, civ_a)):
                    if intent.stance is not Stance.ALLY:
                        self._alliance_breaks[(civ.id, other.id)] = tick
                self._log(tick, events, "diplomacy", [civ_a, civ_b],
                          f"The alliance between {civ_a.name} and {civ_b.name} lapses")
            else:
                for civ in (civ_a, civ_b):
                    civ.diplomacy_points = max(0.0, civ.diplomacy_points - rules.ALLIANCE_UPKEEP)
        elif (to_b.stance is Stance.ALLY and to_a.stance is Stance.ALLY
              and not self.distrusted(a, tick) and not self.distrusted(b, tick)  # nobody allies with a betrayer
              and min(civ_a.diplomacy_points, civ_b.diplomacy_points) >= rules.ALLIANCE_COST):
            for civ in (civ_a, civ_b):
                civ.diplomacy_points -= rules.ALLIANCE_COST
            self._set_status(relation, "alliance", tick)
            deal = self.deal_between(a, b)
            relation.alliance_name = alliance_name(self.world, civ_a, civ_b, deal.a_gives[0] if deal else None,
                                                   self.rng, self.names_used)
            self._log(tick, events, "diplomacy", [civ_a, civ_b],
                      f"{civ_a.name} and {civ_b.name} form an alliance: {relation.alliance_name}")
            self.remember(a, b, 0.4)
            self.remember(b, a, 0.4)
            # The new ally takes on any war in which its partner is the one under attack.
            for partner, newcomer in ((civ_a, civ_b), (civ_b, civ_a)):
                for enemy in self.enemies(partner.id):
                    if self.relation(partner.id, enemy).war.declarer == enemy:
                        self._join_defence(newcomer, partner, self.civs[enemy], tick, events)

        if friendly and self.deal_between(a, b) is None:
            self._try_deal(civ_a, civ_b, to_b, to_a, relation, tick, events)

    def _start_war(self, declarer, target, tick: int, aggressors: set[int],
                   guardian: int | None = None, defending: int | None = None, name: str = "") -> None:
        a, b = sorted((declarer.id, target.id))
        relation = self.relations[(a, b)]
        self.deals = [d for d in self.deals if {d.a, d.b} != {a, b}]
        self._set_status(relation, "war", tick)
        self.wars_started += 1
        relation.war = War(a, b, tick, aggressors=aggressors, progress={a: 0.0, b: 0.0}, regions_taken={a: 0, b: 0},
                           casualties={a: 0.0, b: 0.0}, declarer=declarer.id, guardian=guardian, defending=defending,
                           name=name, last_gain=tick)

    def _join_defence(self, guardian, victim, aggressor, tick: int, events: list) -> None:
        """An ally of a civ that was attacked is at war with the attacker, whether it likes it or not.

        Wars an ally starts carry no such duty: joining those is the ally's own
        choice, made by taking an aggressive stance toward the same enemy.
        """
        if guardian is aggressor:
            return
        relation = self.relation(guardian.id, aggressor.id)
        if relation.status != "peace":
            return  # already fighting, or allied to both sides and so staying out
        main = self.relation(victim.id, aggressor.id).war
        name = main.name if main else ""
        self._start_war(aggressor, guardian, tick, aggressors={aggressor.id},
                        guardian=guardian.id, defending=victim.id, name=name)
        self._log(tick, events, "war", [guardian, aggressor, victim],
                  f"{guardian.name} joins {name or 'the war'} against {aggressor.name} in defence of its ally {victim.name}")
        self.remember(victim.id, guardian.id, 1.0)  # a friend who came when it counted
        self.remember(guardian.id, aggressor.id, -0.5)

    def _betray(self, war: War, betrayer, victim, tick: int, events: list) -> None:
        """The declarer broke an alliance to start this war: it gets a surprise opening and a bad name."""
        war.betrayer = betrayer.id
        war.surprise_until = tick + rules.SURPRISE_TICKS
        # A betrayal while already distrusted adds to the time rather than restarting it.
        self.distrust_until[betrayer.id] = max(self.distrust_until.get(betrayer.id, 0), tick) + rules.DISTRUST_TICKS
        self.remember(victim.id, betrayer.id, -1.5)
        self.betrayed.add((victim.id, betrayer.id))
        for other in self.civs:  # and everyone else has seen what its word is worth
            if other not in (betrayer.id, victim.id):
                self.remember(other, betrayer.id, -0.4)
        self._log(tick, events, "war", [betrayer, victim],
                  f"{betrayer.name} betrays its ally {victim.name}, catching it off guard; "
                  f"others will distrust {betrayer.name} for {self.distrust_until[betrayer.id] - tick} ticks")

    def _set_status(self, relation: Relation, status: str, tick: int) -> None:
        if relation.status == "alliance" and status != "alliance":
            relation.alliance_ended = tick
        relation.status = status
        relation.since = tick
        if status != "alliance":
            relation.alliance_name = ""

    # -- trade ---------------------------------------------------------------

    def _track_refusals(self, tick: int) -> None:
        """Since when each civ at peace has wanted something from another that will not trade it:
        (a, b) -> the tick a first asked b in vain. A deal, or no longer asking, clears it."""
        for a in self.civs:
            for b in self.others(a):
                mine, theirs = self.intents[(a, b)], self.intents[(b, a)]
                asking = (mine.stance in (Stance.TRADE, Stance.ALLY) and mine.want is not None
                          and self.relation(a, b).status != "war" and self.civs[b].alive)
                refused = asking and self.deal_between(a, b) is None and (
                    theirs.stance not in (Stance.TRADE, Stance.ALLY) or theirs.give != mine.want)
                if refused:
                    self.refused_since.setdefault((a, b), (tick, mine.want))
                else:
                    self.refused_since.pop((a, b), None)

    def _try_deal(self, civ_a, civ_b, a_offer: Intent, b_offer: Intent, relation: Relation,
                  tick: int, events: list) -> None:
        """Open a deal if each side's offer is something the other can use and both can pay the fee."""
        if not a_offer.give or not b_offer.give or a_offer.give == b_offer.give:
            return
        a_rate = self._deal_rate(civ_a, civ_b, a_offer, b_offer)
        b_rate = self._deal_rate(civ_b, civ_a, b_offer, a_offer)
        # A betrayer gets worse terms: its partner sends less, and opening the deal costs it more.
        shunned = {civ.id: self.distrusted(civ.id, tick) for civ in (civ_a, civ_b)}
        if shunned[civ_b.id]:
            a_rate = round(a_rate * rules.DISTRUST_RATE_FACTOR, 2)
        if shunned[civ_a.id]:
            b_rate = round(b_rate * rules.DISTRUST_RATE_FACTOR, 2)
        if a_rate < rules.MIN_RATE or b_rate < rules.MIN_RATE:
            return
        base_fee = 0 if relation.status == "alliance" else rules.DEAL_FEE
        fees = {civ.id: base_fee if not shunned[civ.id] else rules.DISTRUST_FEE_FACTOR * rules.DEAL_FEE
                for civ in (civ_a, civ_b)}
        for civ in (civ_a, civ_b):  # Banking and the like make deals cheaper to open
            fees[civ.id] *= max(0.1, 1 + self.mods[civ.id].deal_fee)
        if any(civ.diplomacy_points < fees[civ.id] for civ in (civ_a, civ_b)):
            return
        for civ in (civ_a, civ_b):
            civ.diplomacy_points -= fees[civ.id]
        deal = Deal(self._next_deal_id, civ_a.id, civ_b.id, (a_offer.give, a_rate), (b_offer.give, b_rate), tick)
        self._next_deal_id += 1
        self.deals.append(deal)
        self.remember(civ_a.id, civ_b.id, 0.15)  # trade makes for good neighbours
        self.remember(civ_b.id, civ_a.id, 0.15)
        self._log(tick, events, "trade", [civ_a, civ_b],
                  f"{civ_a.name} trades {a_rate:g} {a_offer.give}/tick to {civ_b.name} for {b_rate:g} {b_offer.give}/tick")

    def _deal_rate(self, giver, receiver, offer: Intent, request: Intent) -> float:
        """Per-tick amount of the giver's offered resource; 0 if the receiver has no use for it."""
        res = offer.give
        if receiver.resources[res] >= rules.SURPLUS_FILL * self.mods[receiver.id].storage[res]:
            return 0.0
        rate = min(offer.give_rate, rules.MAX_RATE, giver.resources[res] / rules.SUSTAIN_TICKS)
        if request.want == res and request.want_rate > 0:
            rate = min(rate, request.want_rate)
        return round(rate, 2)

    def _run_deals(self, tick: int, events: list) -> None:
        for deal in list(self.deals):
            defaulter = None
            for giver_id, receiver_id, res, rate in deal.flows():
                giver, receiver = self.civs[giver_id], self.civs[receiver_id]
                sent = min(rate, giver.resources[res])
                giver.resources[res] -= sent
                room = self.mods[receiver_id].storage[res] - receiver.resources[res]
                # Allies trade on better terms: more arrives than was sent.
                arrives = sent * (1 + rules.ALLY_TRADE_BONUS) if self.relation(deal.a, deal.b).status == "alliance" else sent
                receiver.resources[res] += max(0.0, min(arrives, room))
                deal.missed[giver_id] = deal.missed.get(giver_id, 0) + 1 if sent < 0.5 * rate else 0
                if deal.missed[giver_id] >= rules.DEAL_MISS_LIMIT:
                    defaulter = giver
            if defaulter:
                self.deals.remove(deal)
                other = self.civs[deal.b if defaulter.id == deal.a else deal.a]
                self._log(tick, events, "trade", [defaulter, other],
                          f"{defaulter.name} can no longer supply its trade with {other.name}; the deal is cancelled")
            elif tick >= deal.end:
                self.deals.remove(deal)
                self._log(tick, events, "trade", [self.civs[deal.a], self.civs[deal.b]],
                          f"The trade deal between {self.civs[deal.a].name} and {self.civs[deal.b].name} expires")

    # -- war -----------------------------------------------------------------

    def _transfer_tile(self, tile: int, captor, loser, tick: int, events: list, announce: bool = True) -> None:
        """Move a tile and everything standing on it to `captor`. `loser` is None for native land."""
        self.world.claim(tile, captor.id)
        captor.territory.add(tile)
        if loser is None:
            return
        loser.territory.discard(tile)
        # Whatever stands on the tile now belongs to the captor, finished or not.
        for building in [b for b in loser.buildings if b.tile == tile]:
            loser.buildings.remove(building)
            if not may_stand(self.world, building.type, tile):
                continue  # it could never have been built here, so it is not handed on either
            captor.buildings.append(building)
            bdef = self.building_defs[building.type]
            text = f"{captor.name} captures a {bdef.name} from {loser.name}"
            if building.complete:
                text += self._seize_stores(bdef, captor, loser)
            if announce:
                self._log(tick, events, "capture", [captor, loser], text)
        # Villagers are never harmed: those on the tile now work for the captor, once given a task.
        convert_villagers(tile, loser, captor)

    def _capture_tile(self, relation: Relation, attacker, defender, tile: int, tick: int, events: list) -> None:
        """An army takes an enemy capital in a war, and with it the whole region."""
        world = self.world
        self._transfer_tile(tile, attacker, defender, tick, events)
        recompute_capacity(attacker, world)
        recompute_capacity(defender, world)
        relation.war.regions_taken[attacker.id] += 1
        relation.war.last_gain = tick
        self._reach_cache.clear()
        region_id = world.capital_tiles.get(tile)
        if region_id is not None and world.regions[region_id].owner == defender.id:
            self.capture_region(attacker, world.regions[region_id], tick, events)

    def capture_region(self, captor, region, tick: int, events: list, peaceful: bool = False,
                       ceded: bool = False) -> None:
        """Whoever takes a region's capital takes the region: every tile its previous holder had there.

        Land that other civs hold inside the region stays theirs. A civ that loses
        its own capital this way pays tribute and moves its court to another
        capital it holds; one with no capital left is finished.
        """
        world = self.world
        loser = self.civs.get(region.owner) if region.owner is not None else None
        was_main = loser is not None and loser.capital.tile == region.capital
        if loser is None and self.natives is not None:
            # Whoever else had an army out to take a native region does not forgive being beaten to it.
            for other in self.natives.after(region):
                if other != captor.id:
                    self.remember(other, captor.id, -rules.BEATEN_TO_IT)
        shares = self.spoils_shares(captor, loser) if loser else {captor.id: 1.0}
        for tile in region.tiles:
            owner = world.owner[tile]
            if owner == captor.id or (owner >= 0 and (loser is None or owner != loser.id)):
                continue
            self._transfer_tile(tile, captor, loser if owner >= 0 else None, tick, events, announce=False)
        region.owner = captor.id
        captor.lost_regions.pop(region.id, None)  # won back
        if loser is not None:
            loser.lost_regions[region.id] = tick  # and not forgotten
        region.garrison = 0.0
        region.held_by, region.hold = None, 0
        captor.settlements.append(Settlement(region.capital_name, region.capital))
        recompute_capacity(captor, world)
        self._reach_cache.clear()
        if peaceful:
            self._log(tick, events, "region", [captor],
                      f"{region.capital_name} opens its gates: {region.name} joins {captor.name} without a fight")
        elif loser is None:
            self._log(tick, events, "region", [captor],
                      f"{captor.name} takes {region.capital_name} from {self.faction}; all of {region.name} falls with it")
        elif ceded:
            self._log(tick, events, "region", [captor, loser],
                      f"{region.capital_name} and all of {region.name} pass to {captor.name} by treaty")
        else:
            self._log(tick, events, "war", [captor, loser],
                      f"{captor.name} takes {region.capital_name}; all of {region.name} falls with it")
            self.remember(loser.id, captor.id, -0.5)
            self.learn(loser.id, captor.id, rules.LESSON_LOST)
            self.learn(captor.id, loser.id, rules.LESSON_WON)
        if loser is None:
            return
        military = getattr(self, "military", None)
        if military is not None:
            military.capital_fell(captor, loser, region.capital, tick, events)
        loser.settlements = [s for s in loser.settlements if s.tile != region.capital]
        recompute_capacity(loser, world)
        if not loser.settlements:
            self._eliminate(loser, captor, tick, events)
        elif was_main:
            self._capital_lost(captor, loser, shares, tick, events)

    def _capital_lost(self, winner, loser, shares: dict[int, float], tick: int, events: list) -> None:
        """A civ whose own capital falls pays tribute, moves its court, and is granted a truce."""
        self._pay_tribute(loser, shares, rules.TRIBUTE)
        text = (f"{loser.name} loses its capital to {winner.name}, pays tribute and moves its court to "
                f"{loser.capital.name}" + self._split_note(shares))
        relation = self.relation(winner.id, loser.id)
        if relation.war:
            self._end_war(relation, tick, events, rules.SURRENDER_TRUCE, text)
        else:
            self._log(tick, events, "war", [winner, loser], text)
        self.intents[(loser.id, winner.id)] = Intent(tick=tick)

    def ahead(self, war: War) -> int | None:
        """The side ahead in a war by castles taken, or None while it is even."""
        lead = war.regions_taken.get(war.a, 0) - war.regions_taken.get(war.b, 0)
        if abs(lead) < rules.PEACE_LEAD:
            return None
        return war.a if lead > 0 else war.b

    def accepts_terms(self, war: War, winner, loser, tick: int) -> bool:
        """Whether a civ still pressing a war it is winning would stop for tribute: only once its
        advance has stalled and it holds none of the other's capitals. A human ruler decides for
        himself, by calling off the attack."""
        if winner.id == self.player or self.ahead(war) != winner.id:
            return False
        if tick - war.last_gain < rules.STALL_TICKS:
            return False
        return not any(r.owner == loser.id and r.held_by == winner.id for r in self.world.regions)

    def _make_peace(self, relation: Relation, tick: int, events: list, text: str) -> None:
        """End a war. A side well ahead is paid tribute by the other; what was taken stays taken."""
        war = relation.war
        leader = self.ahead(war)
        ceded = None
        if leader is not None:
            winner = self.civs[leader]
            loser = self.civs[war.b if leader == war.a else war.a]
            lead = war.regions_taken.get(winner.id, 0) - war.regions_taken.get(loser.id, 0)
            ceded = self._region_to_cede(winner, loser) if lead >= rules.CEDE_LEAD else None
            self.learn(loser.id, winner.id, rules.LESSON_LOST)
            self.learn(winner.id, loser.id, rules.LESSON_WON)
            if ceded is not None:
                text += f"; {loser.name} cedes {ceded.name} to {winner.name}"
                self.remember(loser.id, winner.id, -0.5)
            else:
                self._pay_tribute(loser, {winner.id: 1.0}, rules.PEACE_TRIBUTE)
                text += f"; {loser.name} pays {winner.name} tribute"
                self.remember(loser.id, winner.id, -0.3)
        self._end_war(relation, tick, events, rules.TRUCE, text)
        if ceded is not None:
            self.capture_region(winner, ceded, tick, events, ceded=True)

    def _region_to_cede(self, winner, loser):
        """The region a beaten civ gives up: the one nearest the winner, never its home."""
        wx, wy = self.world.xy(winner.capital.tile)
        best, best_gap = None, None
        for region in self.world.regions:
            if region.owner != loser.id or region.capital == loser.capital.tile:
                continue
            x, y = self.world.xy(region.capital)
            gap = abs(x - wx) + abs(y - wy)
            if best_gap is None or gap < best_gap:
                best, best_gap = region, gap
        return best

    def _pay_tribute(self, loser, shares: dict[int, float], share: float) -> None:
        for res in RESOURCES:
            taken = share * loser.resources[res]
            loser.resources[res] -= taken
            for civ_id, part in shares.items():
                civ = self.civs[civ_id]
                room = self.mods[civ_id].storage[res] - civ.resources[res]
                civ.resources[res] += max(0.0, min(part * taken, room))

    def _eliminate(self, loser, captor, tick: int, events: list) -> None:
        """A civ with no capital left is finished: what remains of it goes to its conqueror."""
        world = self.world
        for tile in sorted(loser.territory):
            self._transfer_tile(tile, captor, loser, tick, events, announce=False)
        for villager in list(loser.villagers):
            loser.villagers.remove(villager)
            villager.task, villager.target, villager.path = "idle", None, []
            captor.villagers.append(villager)
        for res in RESOURCES:
            captor.resources[res] += loser.resources[res]
            loser.resources[res] = 0.0
        loser.alive = False
        loser.soldiers = 0.0
        loser.armies, loser.commanders = [], []
        loser.population = 0.0
        self.deals = [d for d in self.deals if loser.id not in (d.a, d.b)]
        for other in self.civs:
            if other == loser.id:
                continue
            relation = self.relation(loser.id, other)
            relation.war = None
            self._set_status(relation, "peace", tick)
            self.intents[(loser.id, other)] = Intent(tick=tick)
            self.intents[(other, loser.id)] = Intent(tick=tick)
        recompute_capacity(captor, world)
        self._reach_cache.clear()
        self._log(tick, events, "war", [captor, loser],
                  f"{loser.name} is no more: its last capital has fallen to {captor.name}")

    def _seize_stores(self, bdef, attacker, defender) -> str:
        """What a captured storage building holds goes with it. Returns a note for the log.

        Stock is taken to be spread evenly over the defender's capacity for that
        resource. The captor keeps all of it even above its own cap; it just
        produces no more of that resource until it is back under.
        """
        note = ""
        shares = self.spoils_shares(attacker, defender)
        for res, capacity in bdef.stores.items():
            held = defender.resources[res] * min(1.0, capacity / self.mods[defender.id].storage[res])
            defender.resources[res] -= held
            for civ_id, share in shares.items():
                self.civs[civ_id].resources[res] += share * held
            # Caps move with the building; keep them in step until modifiers refresh next tick.
            self.mods[defender.id].storage[res] -= capacity
            self.mods[attacker.id].storage[res] += capacity
            note += f" holding {held:.0f} {res}"
        return note + self._split_note(shares)

    def spoils_shares(self, captor, enemy) -> dict[int, float]:
        """How the divisible gains of a capture are divided: civ id -> share, summing to 1.

        A capture is joint when the captor has allies who are also at war with
        the same enemy. The spoils are then split by army strength as it stands
        right now, so the split follows the balance of power through the war.
        Shares that are all close to equal are made exactly equal, so a tiny edge
        does not tip the split.
        """
        partners = [captor] + [
            self.civs[ally] for ally in self.allies(captor.id) if self.relation(ally, enemy.id).status == "war"
        ]
        even = 1 / len(partners)
        strengths = {civ.id: self.strength(civ) for civ in partners}
        total = sum(strengths.values())
        if total <= 0:
            return dict.fromkeys(strengths, even)
        shares = {civ_id: strength / total for civ_id, strength in strengths.items()}
        if all(abs(share - even) <= rules.EVEN_SPLIT_BAND + 1e-9 for share in shares.values()):
            return dict.fromkeys(strengths, even)
        return shares

    def _split_note(self, shares: dict[int, float]) -> str:
        if len(shares) == 1:
            return ""
        parts = ", ".join(f"{self.civs[civ_id].name} {share:.0%}" for civ_id, share in shares.items())
        return f" (shared by strength: {parts})"

    def _end_war(self, relation: Relation, tick: int, events: list, truce: int, text: str) -> None:
        war = relation.war
        if tick - war.start >= rules.HELP_WAR:
            # Allies who sat a long war out are remembered for it.
            for side, enemy in ((war.a, war.b), (war.b, war.a)):
                for ally in self.allies(side):
                    if ally != enemy and self.relation(ally, enemy).status != "war":
                        self.remember(side, ally, rules.HELP_STAYED_AWAY)
        relation.war = None
        relation.truce_until = tick + truce
        self._set_status(relation, "peace", tick)
        self._log(tick, events, "war", [self.civs[war.a], self.civs[war.b]], text)

    def _nearest_tiles(self, attacker, defender) -> list[int]:
        """The defender's tiles closest to the attacker's territory, if it can reach them.

        Overland the gap may be up to REACH tiles. Open water (lakes, deep sea)
        cannot be crossed at all without boats, and then only by putting out from land
        near one of the attacker's working harbours; that way the gap may be wider.
        """
        world = self.world
        harbours = ports(attacker, world) if self.mods[attacker.id].boats else set()
        boats = bool(harbours)
        seen = set(attacker.territory)
        # Setting out from the land along its edge (inner tiles lead nowhere new), not from its waters.
        frontier = sorted(t for t in seen if world.walkable(t) and any(n not in seen for n in world.neighbors(t)))
        for _ in range(rules.REACH + BOAT_RANGE + self.mods[attacker.id].boat_range if boats else rules.REACH):
            found, reached = [], []
            for tile in frontier:
                embark = world.is_boat_water(tile) or tile in harbours
                for n in world.neighbors(tile):
                    if n in seen:
                        continue
                    if world.is_boat_water(n) if not embark else not (world.walkable(n) or world.is_boat_water(n)):
                        continue  # water is crossed by ship from a harbour; mountains not at all
                    seen.add(n)
                    if world.owner[n] == defender.id:
                        found.append(n)
                    else:
                        reached.append(n)
            if found:
                return found
            frontier = reached
        return []

    # -- standing orders for the economy and the AI --------------------------

    def _issue_orders(self, tick: int) -> None:
        for civ in self.civs.values():
            if not civ.alive:
                continue
            cap = self.mobilization_cap(civ)
            mobilisation = max(GARRISON, min(cap, civ.campaign_muster))  # a campaign against natives needs troops
            threat = 0.0
            civ.march_target = None
            for other_id in self.others(civ.id):
                other = self.civs[other_id]
                mine, theirs = self.intents[(civ.id, other_id)], self.intents[(other_id, civ.id)]
                if self.relation(civ.id, other_id).status == "war":
                    threat = 1.0
                    if mine.stance is Stance.AGGRESSION:
                        mobilisation = max(mobilisation, mine.commitment * cap)
                    # Always raise enough to answer the army actually in the field.
                    mobilisation = max(mobilisation, min(cap, 0.05 + other.soldiers / civ.population))
                elif Stance.AGGRESSION in (mine.stance, theirs.stance):
                    threat = max(threat, 0.6)
                    # Muster ahead of a war once the declaration itself is affordable, or if threatened.
                    if theirs.stance is Stance.AGGRESSION or civ.diplomacy_points >= rules.WAR_COST:
                        mobilisation = max(mobilisation, rules.MUSTER * cap)
                    if mine.stance is Stance.AGGRESSION and mine.hold:
                        # Preparing a war: raise the army it means to fight with, and the home guard besides.
                        guard = self.home_guard(civ, exclude={other_id}) / max(civ.population, 1.0)
                        mobilisation = max(mobilisation, min(cap, mine.commitment * cap + guard))
                    if (mine.stance is Stance.AGGRESSION and civ.march_target is None
                            and not self.in_reach(civ.id, other_id, tick)):
                        civ.march_target = other_id
            civ.soldier_target = mobilisation * civ.population
            civ.military_need = threat
            civ.exports = dict.fromkeys(RESOURCES, 0.0)
            civ.imports = dict.fromkeys(RESOURCES, 0.0)
        for deal in self.deals:
            for giver, receiver, res, rate in deal.flows():
                allied = self.relation(deal.a, deal.b).status == "alliance"
                self.civs[giver].exports[res] += rate
                self.civs[receiver].imports[res] += rate * (1 + rules.ALLY_TRADE_BONUS if allied else 1)

    def _proclamation(self, declarer, target, war: str, tick: int) -> dict:
        """What the declarer proclaims (diplomacy/proclamations.py): from the strategist's motive,
        unless that says little and their history says more. Goes with the declaration event
        and into the history."""
        intent = self.intents[(declarer.id, target.id)]
        motive, about = intent.motive, intent.about
        if motive in PLAIN:
            lost = [self.world.regions[r].name for r in sorted(declarer.lost_regions)
                    if self.world.regions[r].owner == target.id]
            if lost:
                motive, about = "lost_lands", lost[0]
            elif (declarer.id, target.id) in self.betrayed:
                motive, about = "faithless", None
            elif self.standing.get((declarer.id, target.id), 0.0) <= -0.8:
                motive, about = "grudge", None
        line = proclaim(declarer.name, target.name, motive, about,
                        random.Random(tick * 1009 + declarer.id * 31 + target.id))
        self.history.append({"tick": tick, "civs": [declarer.id, target.id], "text": f"{declarer.name}: \"{line}\""})
        return {"proclamation": line, "war_name": war, "target": target.id, "motive": motive}

    def _log(self, tick: int, events: list, kind: str, civs: list, text: str) -> None:
        self.history.append({"tick": tick, "civs": [civ.id for civ in civs], "text": text})
        del self.history[:-HISTORY_LIMIT]
        events.append({"civ": civs[0].id, "kind": kind, "text": text})
