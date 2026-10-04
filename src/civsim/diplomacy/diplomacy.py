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
from ..military.units import unit_strength
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
        self._next_deal_id = 1
        self._reach_cache: dict[tuple[int, int], tuple[int, bool]] = {}
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
            unit_strength(army.units) * (1 + (army.commander.strength_bonus if army.commander else 0.0))
            for army in civ.armies)

    def power(self, civ) -> float:
        """Strength the civ could field if it mobilised fully."""
        return civ.population * self.mobilization_cap(civ) * (1 + self.mods[civ.id].military)

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

    # -- per-tick execution --------------------------------------------------

    def update(self, tick: int, events: list) -> None:
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
        self._issue_orders(tick)

    def war_army(self, civ) -> float:
        """Soldiers a civ must have under arms before it will declare war on another civ."""
        return max(rules.WAR_MIN_SOLDIERS, rules.WAR_MIN_SHARE * civ.population)

    def war_ready(self, civ) -> bool:
        return civ.soldiers >= self.war_army(civ)

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
                self._end_war(relation, tick, events, rules.TRUCE,
                              f"{civ_a.name} and {civ_b.name} are exhausted and stop fighting")
            elif age >= rules.MIN_WAR and not hostile:
                self._end_war(relation, tick, events, rules.TRUCE, f"{civ_a.name} and {civ_b.name} make peace")
            return

        if hostile:
            if relation.status == "alliance":
                other = civ_b if hostile[0] is civ_a else civ_a
                self._set_status(relation, "peace", tick)
                self._alliance_breaks[(hostile[0].id, other.id)] = tick
                self._log(tick, events, "diplomacy", [hostile[0], other],
                          f"{hostile[0].name} breaks its alliance with {other.name}")
            declarer = next((civ for civ in hostile
                             if civ.diplomacy_points >= rules.WAR_COST and self.war_ready(civ)), None)
            target = civ_b if declarer is civ_a else civ_a
            if declarer and tick >= relation.truce_until and self.in_reach(declarer.id, target.id, tick):
                declarer.diplomacy_points -= rules.WAR_COST
                broke = self._alliance_breaks.pop((declarer.id, target.id), None)
                betrayal = broke is not None and tick - broke <= rules.BETRAYAL_WINDOW
                name = war_name(self.world, declarer, target, self.rng, self.names_used, betrayal)
                self._start_war(declarer, target, tick, aggressors={civ.id for civ in hostile}, name=name)
                self._log(tick, events, "war", [declarer, target],
                          f"{declarer.name} declares war on {target.name}: {name} begins")
                if betrayal:
                    self._betray(relation.war, declarer, target, tick, events)
                for ally in self.allies(target.id):
                    self._join_defence(self.civs[ally], target, declarer, tick, events)
            return

        friendly = to_b.stance in FRIENDLY and to_a.stance in FRIENDLY
        if relation.status == "alliance":
            if not friendly:
                self._set_status(relation, "peace", tick)
                # Walking away is no offence in itself, but attacking soon afterwards is betrayal.
                for civ, intent, other in ((civ_a, to_b, civ_b), (civ_b, to_a, civ_a)):
                    if intent.stance not in FRIENDLY:
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
        relation.war = War(a, b, tick, aggressors=aggressors, progress={a: 0.0, b: 0.0}, tiles_taken={a: 0, b: 0},
                           casualties={a: 0.0, b: 0.0}, declarer=declarer.id, guardian=guardian, defending=defending,
                           name=name)

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

    def _betray(self, war: War, betrayer, victim, tick: int, events: list) -> None:
        """The declarer broke an alliance to start this war: it gets a surprise opening and a bad name."""
        war.betrayer = betrayer.id
        war.surprise_until = tick + rules.SURPRISE_TICKS
        # A betrayal while already distrusted adds to the time rather than restarting it.
        self.distrust_until[betrayer.id] = max(self.distrust_until.get(betrayer.id, 0), tick) + rules.DISTRUST_TICKS
        self._log(tick, events, "war", [betrayer, victim],
                  f"{betrayer.name} betrays its ally {victim.name}, catching it off guard; "
                  f"others will distrust {betrayer.name} for {self.distrust_until[betrayer.id] - tick} ticks")

    def _set_status(self, relation: Relation, status: str, tick: int) -> None:
        relation.status = status
        relation.since = tick
        if status != "alliance":
            relation.alliance_name = ""

    # -- trade ---------------------------------------------------------------

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
        """An army takes one tile in a war. Taking a region's capital takes the whole region."""
        world = self.world
        self._transfer_tile(tile, attacker, defender, tick, events)
        recompute_capacity(attacker, world)
        recompute_capacity(defender, world)
        relation.war.tiles_taken[attacker.id] += 1
        self._reach_cache.clear()
        region_id = world.capital_tiles.get(tile)
        if region_id is not None and world.regions[region_id].owner == defender.id:
            self.capture_region(attacker, world.regions[region_id], tick, events)

    def capture_region(self, captor, region, tick: int, events: list, peaceful: bool = False) -> None:
        """Whoever takes a region's capital takes the region: every tile its previous holder had there.

        Land that other civs hold inside the region stays theirs. A civ that loses
        its own capital this way pays tribute and moves its court to another
        capital it holds; one with no capital left is finished.
        """
        world = self.world
        loser = self.civs.get(region.owner) if region.owner is not None else None
        was_main = loser is not None and loser.capital.tile == region.capital
        shares = self.spoils_shares(captor, loser) if loser else {captor.id: 1.0}
        for tile in region.tiles:
            owner = world.owner[tile]
            if owner == captor.id or (owner >= 0 and (loser is None or owner != loser.id)):
                continue
            self._transfer_tile(tile, captor, loser if owner >= 0 else None, tick, events, announce=False)
        region.owner = captor.id
        region.garrison = 0.0
        captor.settlements.append(Settlement(region.capital_name, region.capital))
        recompute_capacity(captor, world)
        self._reach_cache.clear()
        if peaceful:
            self._log(tick, events, "region", [captor],
                      f"{region.capital_name} opens its gates: {region.name} joins {captor.name} without a fight")
        elif loser is None:
            self._log(tick, events, "region", [captor],
                      f"{captor.name} takes {region.capital_name} from {self.faction}; all of {region.name} falls with it")
        else:
            self._log(tick, events, "war", [captor, loser],
                      f"{captor.name} takes {region.capital_name}; all of {region.name} falls with it")
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
        for res in RESOURCES:
            taken = rules.TRIBUTE * loser.resources[res]
            loser.resources[res] -= taken
            for civ_id, share in shares.items():
                civ = self.civs[civ_id]
                room = self.mods[civ_id].storage[res] - civ.resources[res]
                civ.resources[res] += max(0.0, min(share * taken, room))
        text = (f"{loser.name} loses its capital to {winner.name}, pays tribute and moves its court to "
                f"{loser.capital.name}" + self._split_note(shares))
        relation = self.relation(winner.id, loser.id)
        if relation.war:
            self._end_war(relation, tick, events, rules.SURRENDER_TRUCE, text)
        else:
            self._log(tick, events, "war", [winner, loser], text)
        self.intents[(loser.id, winner.id)] = Intent(tick=tick)

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
        frontier = sorted(seen)
        for _ in range(rules.REACH + BOAT_RANGE + self.mods[attacker.id].boat_range if boats else rules.REACH):
            found, reached = [], []
            for tile in frontier:
                embark = world.is_open_water(tile) or tile in harbours
                for n in world.neighbors(tile):
                    if n in seen or (world.is_open_water(n) and not embark):
                        continue
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
                    if mine.stance is Stance.AGGRESSION:  # and enough to be allowed to declare at all
                        mobilisation = max(mobilisation, min(cap, 1.05 * self.war_army(civ) / max(civ.population, 1.0)))
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

    def _log(self, tick: int, events: list, kind: str, civs: list, text: str) -> None:
        self.history.append({"tick": tick, "civs": [civ.id for civ in civs], "text": text})
        del self.history[:-HISTORY_LIMIT]
        events.append({"civ": civs[0].id, "kind": kind, "text": text})
